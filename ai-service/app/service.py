"""业务编排层：mokc 结果兜底 + real 模式由 DeepSeek 覆盖文本字段。

原则：
- 规则/检索/判分/出题等确定性逻辑始终走 mock.*（可复现、可验收）；
- 仅当 settings.llm_ready 且业务允许时，调用 DeepSeek 润色/生成自然语言字段；
- 任一 LLM 调用失败只记录日志并回退 mock，响应 mode 如实标注，绝不向前端抛 500。
"""
from __future__ import annotations

import logging
import re

from . import mock, prompts
from .config import settings
from .knowledge import (
    BuiltinDocumentError,
    DocumentNotFoundError,
    KnowledgeBase,
    UploadValidationError,
)
from .gate import gate_store, record_to_vo
from .kp import registry as kp_registry
from .llm import LLMError, client_for
from .llm import client as llm_client
from .retrieval import retriever
from .rules import (
    SOFT_SCOPE_WARNING,
    check_scope,
    hard_scope_hit,
    is_homework_question,
    normalize_teacher_config,
    teacher_scope_hit,
)
from .vector_store import vector_index
from .schemas import (
    ClassAnalysisRequest,
    ClassAnalysisResponse,
    ConfigExtractRequest,
    ConfigExtractResponse,
    DeleteResponse,
    DiagnoseQuestionsRequest,
    DocumentVO,
    DocumentsResponse,
    GateAnswerItem,
    GateCheckRequest,
    GateCheckResponse,
    Gate,
    GradeRequest,
    GradeResponse,
    HealthResponse,
    HintRequest,
    HintResponse,
    IntentRequest,
    IntentResponse,
    PlanRequest,
    PlanResponse,
    PracticeQuestionsRequest,
    PracticeQuestionsResponse,
    QARequest,
    QAResponse,
    QuestionsResponse,
    RebuildResponse,
    RetrieveRequest,
    RetrieveResponse,
    Teaching,
    UploadResponse,
)

logger = logging.getLogger("ams.ai.service")

kb = KnowledgeBase()


# --------------------------------------------------------------------------
# 启动与索引
# --------------------------------------------------------------------------
def rebuild_index() -> dict:
    """重建知识库分块，并刷新向量索引（旧检索器保留作对照）。"""
    stats = kb.rebuild()
    chunks = kb.chunks()
    retriever.rebuild_from(chunks)
    stats.update(vector_index.rebuild(chunks))
    return stats


def _refresh_indexes() -> None:
    """知识库发生上传/启停/删除后刷新两类索引。"""
    chunks = kb.chunks()
    retriever.rebuild_from(chunks)
    vector_index.rebuild(chunks)


def ensure_ready() -> dict:
    """启动时调用：校验配置、加载文档状态、构建索引。"""
    settings.validate()
    stats = rebuild_index()
    info = vector_index.info()
    logger.info(
        "AI 服务就绪：mode=%s model=%s llm_ready=%s embedding=%s/%s 文档=%s 分块=%s 向量=%s 维度=%s 耗时=%sms",
        settings.mode,
        settings.deepseek_model,
        settings.llm_ready,
        info.get("embeddingProvider", "local"),
        info.get("embeddingModel", ""),
        stats["documentCount"],
        stats["chunkCount"],
        info["vectorCount"],
        info["vectorDim"],
        stats["durationMs"],
    )
    return stats


def health() -> HealthResponse:
    documents = kb.documents()
    info = vector_index.info()
    return HealthResponse(
        status="UP",
        mode=settings.mode,
        knowledge_documents=len(documents),
        knowledge_chunks=retriever.size(),
        model=settings.deepseek_model,
        llm_ready=settings.llm_ready,
        vector_store=info["vectorStore"],
        embedding=info["embedding"],
        vector_dim=info["vectorDim"],
        vector_count=info["vectorCount"],
        embedding_provider=info.get("embeddingProvider", "local"),
        embedding_model=info.get("embeddingModel", info.get("embedding", "")),
        embedding_dim=int(info.get("embeddingDim", info["vectorDim"])),
        retrieval_mode="hybrid",
        supports_user_key=settings.supports_user_key,
        vision_provider=settings.vision_provider_name,
        vision_model=settings.vision_model,
        vision_ready=settings.vision_ready,
    )


# --------------------------------------------------------------------------
# 知识库管理（AI12~AI16）
# --------------------------------------------------------------------------
def list_documents(class_id: str | None = None) -> DocumentsResponse:
    docs = kb.documents(class_id=class_id)
    return DocumentsResponse(
        documents=[DocumentVO(**kb.document_vo(doc)) for doc in docs],
        stats=kb.stats(class_id=class_id),
    )


def upload_document(
    filename: str,
    content: bytes,
    kb_name: str = "KB4",
    class_id: str | None = None,
    uploaded_by: str | None = None,
) -> UploadResponse:
    doc, chunks = kb.add_upload(
        filename=filename,
        content=content,
        kb=kb_name,
        class_id=class_id,
        uploaded_by=uploaded_by,
    )
    _refresh_indexes()
    return UploadResponse(document=DocumentVO(**kb.document_vo(doc)), chunks=chunks)


def set_document_enabled(document_id: str, enabled: bool) -> DocumentVO:
    doc = kb.set_enabled(document_id, enabled)
    _refresh_indexes()
    return DocumentVO(**kb.document_vo(doc))


def delete_document(document_id: str) -> DeleteResponse:
    kb.delete(document_id)
    _refresh_indexes()
    return DeleteResponse(deleted=True)


def rebuild_knowledge() -> RebuildResponse:
    stats = rebuild_index()
    return RebuildResponse(
        documentCount=stats["documentCount"],
        chunkCount=stats["chunkCount"],
        durationMs=stats["durationMs"],
        mode=settings.mode,
    )


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _fallback_mode(result: dict, exc: Exception | None = None, action: str = "") -> dict:
    result["mode"] = "mock"
    if exc is not None:
        logger.warning("%s 调用真实模型失败，已降级 mock：%s: %s", action, type(exc).__name__, exc)
    return result


def _text(data: dict, key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


_HINT_STEP_RE = re.compile(r"(?m)^[ \t]*([1-9])[.、)]\s*")


def _normalize_hint(text: str) -> str:
    """把「1. 2. 3.」形式的步骤统一成「第 N 步」，与契约和前端展示一致。"""
    if not text:
        return text
    return _HINT_STEP_RE.sub(lambda match: f"第 {match.group(1)} 步：", text)


def _strip_internal_ids(answer: str, sources: list[dict]) -> str:
    """v1.2 §3.3：答案里不允许出现「片段 5」「chunk 3」「kp021」等内部编号。"""
    if not answer:
        return answer
    citations = [str(item.get("citation") or "").strip() for item in sources or []]

    def _frag(match: re.Match) -> str:
        index = int(match.group(1)) - 1
        if 0 <= index < len(citations) and citations[index]:
            return citations[index]
        return "知识库相关章节"

    answer = re.sub(r"片段\s*(\d+)", _frag, answer)
    answer = re.sub(r"(?i)chunk\s*\d+", "知识库相关章节", answer)
    answer = re.sub(r"(?i)documentId\s*[:：]?\s*[\w\-]+", "", answer)

    def _kp(match: re.Match) -> str:
        name = kp_registry.name(match.group(0))
        return name or "本知识点"

    answer = re.sub(r"kp\d{3}", _kp, answer, flags=re.I)
    return answer


def _postprocess_qa(req: QARequest, base: dict, answer: str) -> str:
    """把真实模型输出收敛到契约话术，避免模式切换导致行为漂移。"""
    answer = _strip_internal_ids(answer.strip(), base.get("sources") or [])
    if not answer:
        return answer
    if is_homework_question(req.message) and "不能直接给出最终答案" not in answer:
        notice = (
            "这是作业/考试类请求，按学习规范我不能直接给出最终答案，下面只提供思路与检查点。"
        )
        if answer.startswith("【先判断】"):
            # 模型自己已经写了【先判断】：把规范话术并进该段，避免出现两个重复标题
            rest = answer[len("【先判断】"):].lstrip("\n")
            answer = "【先判断】\n" + notice + (" " + rest if rest else "")
        else:
            answer = "【先判断】\n" + notice + "\n\n" + answer
    if base.get("knowledgeCovered") and "【参考资料】" not in answer:
        refs = mock._references_block(base.get("sources") or [])
        if refs:
            answer = answer.rstrip() + refs
    scope_warning = base.get("scopeWarning")
    if scope_warning:
        if scope_warning not in answer:
            answer = answer.rstrip() + "\n\n" + scope_warning
    elif not base.get("knowledgeCovered"):
        if "知识库暂无相关内容" not in answer:
            answer = "知识库暂无相关内容，以下仅给一般性思路。\n\n" + answer
        if "换一种问法" not in answer:
            answer = answer.rstrip() + "\n\n建议换一种问法：直接问具体知识点（例如“洛必达法则的使用条件”）。"
    return answer


# --------------------------------------------------------------------------
# AI2 /qa
# --------------------------------------------------------------------------
_QUERY_REWRITE_SYSTEM = (
    "你是高等数学检索查询改写助手。只输出 JSON：{\"terms\": [\"关键词\", \"...\"]}。"
    "terms 为 2~5 个中文检索关键词（知识点名/方法名/章节名），不要解释，不要回答题目。"
)


def _llm_query_terms(message: str) -> list[str]:
    """v1.2 §1 双轨 A：真实模式下用 DeepSeek 做查询改写，失败静默回退规则扩展。"""
    if not settings.llm_ready or settings.query_expansion == "off":
        return []
    user = "学生问题：" + message + "\n请给出用于检索课程资料的关键词。"
    try:
        data = llm_client.chat_json(_QUERY_REWRITE_SYSTEM, user, temperature=0.1, max_tokens=200)
    except Exception as exc:  # noqa: BLE001 - 改写失败不影响主流程
        logger.info("查询改写失败，回退规则扩展：%s: %s", type(exc).__name__, exc)
        return []
    terms = _as_str_list(data.get("terms"))
    return [term for term in terms if len(term) <= 20][:5]


def qa(req: QARequest) -> QAResponse:
    message = _text({"message": getattr(req, "message", "")}, "message")
    config = normalize_teacher_config(getattr(req, "teacherConfig", None))
    # v1.3 ①硬拦截是纯规则判断：先判范围，超范围问题不浪费一次查询改写/模型调用
    scope_blocked, _reason = hard_scope_hit(message)
    # v1.3 ②教师配置命中且未通过前置自测时直接出 gate 题，同样不做查询改写
    teacher_topic, _gate_reason = teacher_scope_hit(message, config)
    gated = bool(teacher_topic) and not gate_store.is_passed(
        getattr(req, "conversationId", None), teacher_topic or ""
    )
    terms: list[str] = []
    if not scope_blocked and not gated:
        # v1.2 联调修复：多轮追问时检索 query 与查询改写都基于「当前问题 + 上一轮用户问题」
        retrieval_message = mock.build_retrieval_query(req, message)
        # 查询改写词作为「扩展召回」单独传入，不拼进展示用 message，避免改写词压过原问题
        terms = _llm_query_terms(retrieval_message)
    base = mock.qa(req, retriever, query_terms=terms)
    base["conversationId"] = getattr(req, "conversationId", None)

    # v1.3：前置自测是确定性出题（不调 LLM），mode/model 如实反映服务配置
    if base.get("gate"):
        base["mode"] = settings.mode
        base["model"] = settings.deepseek_model if settings.llm_ready else ""
        base["modelSource"] = "system" if settings.llm_ready else "mock"
        return QAResponse(**base)

    if base.get("blocked"):
        # v1.2 联调：规则硬拦截不调用任何模型，但服务模式如实返回 real，
        # modelSource=none（非 system/user/mock），避免真实服务下被标成 mock。
        base["mode"] = settings.mode
        base["model"] = settings.deepseek_model if settings.llm_ready else ""
        base["modelSource"] = "none"
        return QAResponse(**base)

    # v1.2 §3.1：优先本次请求携带的用户 key，失败降级系统 key，再失败降级 mock
    candidates: list[tuple[object, str]] = []
    try:
        override_client = client_for(getattr(req, "llm", None))
    except Exception as exc:  # noqa: BLE001 - 非法覆盖配置不影响主流程
        logger.warning("用户 LLM 配置无效，回退系统 key：%s: %s", type(exc).__name__, exc)
        override_client = None
    if override_client is not None:
        candidates.append((override_client, "user"))
    if settings.llm_ready:
        candidates.append((llm_client, "system"))
    if not candidates:
        base["modelSource"] = "mock"
        return QAResponse(**base)

    system, user = prompts.qa_messages(req, base)
    last_error: Exception | None = None
    for client, source in candidates:
        try:
            data = client.chat_json(system, user, temperature=0.4, max_tokens=2600)
        except LLMError as exc:
            last_error = exc
            logger.warning("qa 真实模型调用失败（modelSource=%s）：%s", source, exc)
            continue
        answer = _text(data, "answer")
        if not answer:
            last_error = LLMError("answer 字段为空")
            continue
        base["answer"] = _postprocess_qa(req, base, answer)
        kp_ids = _as_str_list(data.get("kpIds"))
        if kp_ids:
            base["kpIds"] = kp_ids
        base["mode"] = "real"
        base["modelSource"] = source
        base["model"] = str(getattr(client.config, "deepseek_model", "") or settings.deepseek_model)
        return QAResponse(**base)

    base["modelSource"] = "mock"
    return QAResponse(**_fallback_mode(base, last_error or LLMError("真实模型不可用"), "qa"))


# --------------------------------------------------------------------------
# v1.3 /qa/gate/check：前置自测判分 + 通过后的三步教学
# --------------------------------------------------------------------------
def _gate_sources(record) -> list[dict]:
    """通过后给教学附上知识库引用（无命中则返回空）。"""
    query = record.topic + " " + " ".join(
        [p.get("kpName") or "" for p in record.prerequisites]
    )
    try:
        result = vector_index.search(
            query=query.strip(),
            top_k=4,
            min_score=vector_index.default_min_score(),
            kb_scope=["KB1", "KB2", "KB3", "KB4"],
            class_id=None,
        )
    except Exception as exc:  # noqa: BLE001 - 引用缺失不影响教学
        logger.info("gate 引用检索失败：%s: %s", type(exc).__name__, exc)
        return []
    return list(result.items) if result.enough else []


def gate_check(req: GateCheckRequest) -> GateCheckResponse:
    record = gate_store.get(req.gateId)
    if record is None:
        # 契约 §1.4：gateId 不存在/过期也返回 HTTP 200，state=EXPIRED
        return GateCheckResponse(
            passed=False,
            score=0,
            total=0,
            state="EXPIRED",
            feedback="前置测试已过期，请重新提问。",
            answer="",
            sources=[],
            knowledgeCovered=False,
            gate=None,
            teaching=None,
            mode="mock",
            model=None,
            modelSource="mock",
        )

    answers = [
        {"questionId": item.questionId, "choice": item.choice}
        for item in req.answers
    ]
    result = gate_store.score(record, answers)
    gate_vo = record_to_vo(record)
    conversation_id = req.conversationId if req.conversationId is not None else record.conversation_id

    if not result["passed"]:
        # 未通过：不生成教学答案，也不调用任何模型
        return GateCheckResponse(
            passed=False,
            score=result["score"],
            total=result["total"],
            state="FAILED",
            feedback=mock.gate_failed_feedback(result["weakKpNames"], record.topic),
            answer="",
            sources=[],
            knowledgeCovered=False,
            gate=Gate(**gate_vo),
            teaching=None,
            mode=settings.mode,
            model=settings.deepseek_model if settings.llm_ready else None,
            modelSource="system" if settings.llm_ready else "mock",
        )

    gate_store.mark_passed(conversation_id, record.topic)
    sources = _gate_sources(record)
    teaching = mock.gate_teaching(record)
    mode = "mock"
    model_source = "mock"
    model: str | None = None
    if settings.llm_ready:
        try:
            data = llm_client.chat_json(
                *prompts.gate_teaching_messages(record, gate_vo, sources, teaching),
                temperature=0.5,
                max_tokens=2400,
            )
            steps = [
                {"title": _text(step, "title"), "content": _text(step, "content")}
                for step in (data.get("steps") or [])
                if isinstance(step, dict)
            ]
            steps = [step for step in steps if step["title"] and step["content"]]
            practice = _text(data, "practice")
            if len(steps) >= 3:
                teaching = {
                    "steps": steps[:3],
                    "practice": practice or teaching.get("practice", ""),
                }
                mode = "real"
                model_source = "system"
                model = settings.deepseek_model
        except LLMError as exc:
            logger.warning("gate 教学真实模型调用失败，回退 mock：%s", exc)

    return GateCheckResponse(
        passed=True,
        score=result["score"],
        total=result["total"],
        state="PASSED",
        feedback="前置自测通过：%d/%d。已解锁「%s」的三步教学。"
        % (result["score"], result["total"], record.topic),
        answer=mock.gate_passed_lead_in(record.topic),
        sources=sources,
        knowledgeCovered=bool(sources),
        gate=Gate(**record_to_vo(record)),
        teaching=Teaching(**teaching),
        mode=mode,
        model=model,
        modelSource=model_source,
    )


# --------------------------------------------------------------------------
# AI3 /intent 与 AI4 /retrieve（确定性，无需 LLM）
# --------------------------------------------------------------------------
def detect_intent(req: IntentRequest) -> IntentResponse:
    return IntentResponse(**mock.intent(req))


def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    return RetrieveResponse(**mock.retrieve(req, retriever))


# --------------------------------------------------------------------------
# AI5 /diagnose/questions 与 AI6 /diagnose/grade（确定性）
# --------------------------------------------------------------------------
def diagnose_questions(req: DiagnoseQuestionsRequest) -> QuestionsResponse:
    return QuestionsResponse(**mock.diagnose_questions(req))


def grade(req: GradeRequest) -> GradeResponse:
    return GradeResponse(**mock.grade(req))


# --------------------------------------------------------------------------
# AI7 /practice/questions
# --------------------------------------------------------------------------
def practice_questions(req: PracticeQuestionsRequest) -> PracticeQuestionsResponse:
    base = mock.practice_questions(req)
    if settings.llm_ready and base.get("questions"):
        try:
            data = llm_client.chat_json(*prompts.practice_messages(req, base), temperature=0.5, max_tokens=500)
            guidance = _text(data, "guidance")
            if guidance:
                base["guidance"] = guidance
                base["mode"] = "real"
        except LLMError as exc:
            _fallback_mode(base, exc, "practice/questions")
    return PracticeQuestionsResponse(**base)


# --------------------------------------------------------------------------
# AI8 /practice/hint
# --------------------------------------------------------------------------
def practice_hint(req: HintRequest) -> HintResponse:
    base = mock.practice_hint(req, retriever)
    if settings.llm_ready:
        try:
            data = llm_client.chat_json(*prompts.hint_messages(req), temperature=0.4, max_tokens=700)
            hint = _text(data, "hint")
            if hint:
                base["hint"] = _normalize_hint(hint)
                strategy = _text(data, "strategy")
                if strategy:
                    base["strategy"] = strategy
                base["mode"] = "real"
        except LLMError as exc:
            _fallback_mode(base, exc, "practice/hint")
    return HintResponse(**base)


# --------------------------------------------------------------------------
# AI9 /plan
# --------------------------------------------------------------------------
_PLAN_DAY_FIELDS = {"goal", "study", "review"}


def _merge_plan_days(base: dict, data: dict) -> bool:
    days = data.get("days")
    if not isinstance(days, list) or len(days) != len(base.get("days") or []):
        return False
    by_index = {}
    for item in days:
        if isinstance(item, dict) and isinstance(item.get("dayIndex"), int):
            by_index[item["dayIndex"]] = item
    if len(by_index) != len(base["days"]):
        return False
    for day in base["days"]:
        patch = by_index.get(day.get("dayIndex"))
        if not patch:
            return False
        goal = _text(patch, "goal")
        if goal:
            day["goal"] = goal
        study = patch.get("study")
        if isinstance(study, dict):
            summary = _text(study, "summary")
            if summary:
                day.setdefault("study", {})["summary"] = summary
            points = _as_str_list(study.get("points"))
            if points:
                day.setdefault("study", {})["points"] = points[:6]
            example = _text(study, "example")
            if example:
                day.setdefault("study", {})["example"] = example
        review = patch.get("review")
        if isinstance(review, dict):
            summary = _text(review, "summary")
            if summary:
                day.setdefault("review", {})["summary"] = summary
            checklist = _as_str_list(review.get("checklist"))
            if checklist:
                day.setdefault("review", {})["checklist"] = checklist[:6]
    return True


def plan(req: PlanRequest) -> PlanResponse:
    base = mock.plan(req, retriever)
    if settings.llm_ready and base.get("days"):
        try:
            data = llm_client.chat_json(*prompts.plan_messages(req, base), temperature=0.4, max_tokens=1200)
            summary = _text(data, "summary")
            if summary:
                base["summary"] = summary
            if _merge_plan_days(base, data):
                base["mode"] = "real"
            elif summary:
                base["mode"] = "real"
        except LLMError as exc:
            _fallback_mode(base, exc, "plan")
    return PlanResponse(**base)


# --------------------------------------------------------------------------
# AI10 /class-analysis
# --------------------------------------------------------------------------
def _merge_advice(base: dict, data: dict) -> bool:
    raw = data.get("advice")
    if not isinstance(raw, list):
        return False
    merged = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = _text(item, "title")
        content = _text(item, "content")
        if not title or not content:
            continue
        priority = str(item.get("priority") or "MEDIUM").upper()
        if priority not in {"HIGH", "MEDIUM", "LOW"}:
            priority = "MEDIUM"
        merged.append({"title": title, "content": content, "priority": priority})
    if len(merged) < 3:
        return False
    base["advice"] = merged[:6]
    return True


def class_analysis(req: ClassAnalysisRequest) -> ClassAnalysisResponse:
    base = mock.class_analysis(req)
    if settings.llm_ready:
        try:
            data = llm_client.chat_json(
                *prompts.class_analysis_messages(req, base), temperature=0.4, max_tokens=2000
            )
            summary = _text(data, "summary")
            if summary:
                base["summary"] = summary
            if _merge_advice(base, data) or summary:
                base["mode"] = "real"
        except LLMError as exc:
            _fallback_mode(base, exc, "class-analysis")
    return ClassAnalysisResponse(**base)


# --------------------------------------------------------------------------
# AI11 /config/extract
# --------------------------------------------------------------------------
_PATCH_KEYS = {"answerMode", "maxDifficulty", "knowledgeScope", "kbAccess", "disabledTopics", "boundaryRules"}


def _sanitize_patch(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    patch: dict = {}
    mode = raw.get("answerMode")
    if isinstance(mode, str) and mode.upper() in {"GUIDED", "DIRECT", "MIXED"}:
        patch["answerMode"] = mode.upper()
    difficulty = raw.get("maxDifficulty")
    if isinstance(difficulty, (int, float)) and 1 <= int(difficulty) <= 4:
        patch["maxDifficulty"] = int(difficulty)
    scope = raw.get("knowledgeScope")
    if isinstance(scope, dict) and str(scope.get("mode", "")).upper() in {"ALL", "CHAPTER", "CUSTOM"}:
        patch["knowledgeScope"] = {
            "mode": str(scope["mode"]).upper(),
            "chapters": _as_str_list(scope.get("chapters")),
            "kpIds": _as_str_list(scope.get("kpIds")),
        }
    kb_access = raw.get("kbAccess")
    if isinstance(kb_access, dict):
        allowed = {key: bool(value) for key, value in kb_access.items() if key in {"kb1", "kb2", "kb3", "kb4"}}
        if allowed:
            patch["kbAccess"] = allowed
    disabled = _as_str_list(raw.get("disabledTopics"))
    if disabled:
        patch["disabledTopics"] = disabled
    boundary = raw.get("boundaryRules")
    if isinstance(boundary, str) and boundary.strip():
        patch["boundaryRules"] = boundary.strip()
    return patch


_KB_ACCESS_DEFAULTS = {"kb1": True, "kb2": True, "kb3": True, "kb4": False}


def _expand_kb_access(patch: dict, current: dict) -> dict:
    """真实模型可能只返回被改动的 kb 开关，这里补全为完整 4 键，避免前端整体覆盖配置。"""
    kb = patch.get("kbAccess")
    if not isinstance(kb, dict):
        return patch
    merged = dict(_KB_ACCESS_DEFAULTS)
    cur = current.get("kbAccess") if isinstance(current, dict) else None
    if isinstance(cur, dict):
        for key in merged:
            if isinstance(cur.get(key), bool):
                merged[key] = cur[key]
    for key, value in kb.items():
        if key in merged:
            merged[key] = bool(value)
    patch["kbAccess"] = merged
    return patch


def config_extract(req: ConfigExtractRequest) -> ConfigExtractResponse:
    base = mock.config_extract(req)
    if settings.llm_ready:
        try:
            data = llm_client.chat_json(
                *prompts.config_extract_messages(req), temperature=0.1, max_tokens=1200
            )
            patch = _expand_kb_access(_sanitize_patch(data.get("patch")), req.current or {})
            if patch:
                merged = dict(base.get("patch") or {})
                merged.update(patch)
                base["patch"] = merged
                base["mode"] = "real"
            explanation = _text(data, "explanation")
            if explanation:
                base["explanation"] = explanation
            unrecognized = _as_str_list(data.get("unrecognized"))
            if unrecognized:
                merged_unrecognized = list(dict.fromkeys(list(base.get("unrecognized") or []) + unrecognized))
                base["unrecognized"] = merged_unrecognized
        except LLMError as exc:
            _fallback_mode(base, exc, "config/extract")
    return ConfigExtractResponse(**base)
