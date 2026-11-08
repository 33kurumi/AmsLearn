"""mock 模式确定性演示逻辑：不依赖外部模型即可完整演示 AI2~AI11 语义。

设计原则：
- 路由层只做参数装配，所有演示内容都在本模块生成，便于测试与验收；
- 回答严格遵循契约：无内容如实告知、作业/考试不给最终答案、超范围统一话术；
- 确定性输出：同样的请求得到同样的题目与建议，方便演示复现。
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from . import builtin_questions
from .config import settings
from .kp import registry as kp_registry
from .gate import GATE_ACTION, gate_intro, gate_store, record_to_vo
from .rules import (
    BLOCK_MESSAGE,
    SOFT_SCOPE_WARNING,
    action_for_intent,
    check_scope,
    check_soft_scope,
    hard_scope_hit,
    teacher_scope_hit,
    clamp,
    clean_excerpt,
    detect_intent,
    guess_difficulty_from_layer,
    is_concept_question,
    is_homework_question,
    kb_scope_from_config,
    normalize_teacher_config,
    soft_scope_topic,
)
from .vector_store import VectorSearchResult, vector_index

ERROR_TYPES = ["概念混淆", "计算失误", "审题偏差", "方法不当"]


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _layer_of(difficulty: int) -> str:
    if difficulty <= 2:
        return "A"
    return "B" if difficulty == 3 else "C"


def _mastery_map(items) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in items or []:
        if isinstance(item, dict):
            kp_id = _text(item.get("kpId"))
            raw = item.get("mastery", 0)
        else:
            kp_id = _text(getattr(item, "kpId", ""))
            raw = getattr(item, "mastery", 0)
        if not kp_id:
            continue
        result[kp_id] = max(0.0, min(1.0, _num(raw)))
    return result


def _kp_name(kp_id: str, fallback: str = "") -> str:
    return kp_registry.name(kp_id, fallback) if kp_id else fallback


def _safe_excerpt(text: str, limit: int = 240) -> str:
    """截取教材片段：去掉“解/证明/答案/解析”之后的解题过程，避免泄露最终答案。"""
    body = re.sub(r"(?:^|\n)\s*(?:解|证明|答案|解析)\s*[:：][\s\S]*$", "", text or "")
    body = re.sub(r"^#+\s*[^\n]*\n", "", body)
    return clean_excerpt(body.strip(), limit=limit)


def _format_excerpts(sources: list[dict], limit: int = 240) -> str:
    parts: list[str] = []
    for item in sources[:2]:
        excerpt = _safe_excerpt(str(item.get("excerpt", "")), limit=limit)
        if excerpt:
            parts.append(excerpt)
    return "\n".join(parts) if parts else "教材中对该知识点的描述较少，建议结合课堂笔记复习。"


# --------------------------------------------------------------------------
# AI3 /intent、AI4 /retrieve
# --------------------------------------------------------------------------
def intent(req) -> dict:
    message = _text(getattr(req, "message", ""))
    name, confidence, reason = detect_intent(message)
    kp_ids = kp_registry.match(message, 4)
    return {
        "intent": name,
        "confidence": round(confidence, 2),
        "kpIds": kp_ids,
        "reason": reason,
        "mode": "mock",
    }


def retrieve(req, retriever=None) -> dict:
    """AI4：向量检索（retriever 参数仅为兼容旧调用，检索统一走向量索引）。"""
    raw_min = getattr(req, "minScore", None)
    default_min = vector_index.default_min_score()
    result = vector_index.search(
        query=_text(getattr(req, "query", "")),
        top_k=clamp(getattr(req, "topK", 8) or 8, 1, 50, 8),
        min_score=default_min if raw_min is None else max(0.0, _num(raw_min, default_min)),
        kb_scope=getattr(req, "kbScope", None),
        class_id=getattr(req, "classId", None),
    )
    return {
        "items": result.items,
        "enough": result.enough,
        "topScore": result.top_score,
        "mode": "mock",
    }


# --------------------------------------------------------------------------
# AI2 /qa
# --------------------------------------------------------------------------
def _guidance_steps(kp_name: str, message: str) -> list[str]:
    topic = kp_name or "本题涉及的高等数学知识点"
    steps = [
        f"明确考点：这道题主要考查「{topic}」，先把相关定义、定理的成立条件写出来。",
        "对照条件选择方法：能直接套公式就套公式；不能直接套时，先做恒等变形、换元或分类讨论。",
        "按步骤书写并标注依据：每一步说明用了哪条定义/定理/法则，最后检查符号、取值范围和特殊情况。",
    ]
    if re.search(r"洛必达|极限", message):
        steps[1] = "先判断极限类型：只有 0/0 或 ∞/∞ 型才能直接用洛必达法则，其他类型要先转化；使用前还要确认分子分母在去心邻域内可导且分母导数不为零。"
    elif re.search(r"积分", message):
        steps[1] = "先观察被积函数结构：能凑微分就换元，分式优先考虑拆项或部分分式，定积分注意上下限与对称性。"
    elif re.search(r"导数|求导", message):
        steps[1] = "先识别复合结构：外层函数乘以内层导数；隐函数方程两边同时对自变量求导，把因变量看成自变量的函数。"
    return steps


# 常见知识点的核心公式（mock 模式下用于演示 KaTeX 公式渲染，真实模式由大模型输出）
FORMULA_BLOCK = {
    "洛必达": "$$\\lim_{x\\to a}\\frac{f(x)}{g(x)}=\\lim_{x\\to a}\\frac{f'(x)}{g'(x)}$$",
    "泰勒": "$$f(x)=\\sum_{k=0}^{n}\\frac{f^{(k)}(x_0)}{k!}(x-x_0)^k+R_n(x)$$",
    "定积分": "$$\\int_a^b f(x)\\,\\mathrm{d}x=F(b)-F(a)$$",
    "导数": "$$\\left(f(g(x))\\right)'=f'(g(x))\\,g'(x)$$",
}


def _formula_block(kp_name: str, message: str) -> str:
    topic = f"{kp_name or ''} {message or ''}"
    for key, tex in FORMULA_BLOCK.items():
        if key in topic:
            return f"\n\n【核心公式】\n{tex}\n（公式由 KaTeX 渲染，使用前请先核对成立条件）"
    return ""


def _build_qa_answer(message: str, plan: str, sources: list[dict], kp_id: str, kp_name: str, chapter: str) -> str:
    excerpt_block = _format_excerpts(sources)
    steps = _guidance_steps(kp_name, message)
    topic = kp_name or "高等数学基础概念"
    chapter_line = f"所属章节：{chapter}。" if chapter else ""

    if plan == "homework":
        return (
            "【先判断】\n"
            f"这是作业/考试类请求，按学习规范我不能直接给出最终答案。本题主要考查「{topic}」，{chapter_line}"
            "我们先把思路拆开，你可以按步骤自己完成计算。\n\n"
            "【思路引导】\n"
            + "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(steps))
            + "\n\n【知识点讲解】\n"
            + excerpt_block
            + "\n\n【易错提醒】\n"
            "- 注意定理/公式的适用条件，条件不满足时不能直接套用；\n"
            "- 变形过程要保证等价，约分、开方、取对数等操作注意定义域；\n"
            "- 最后代回原题检验，避免符号和计算错误。\n\n"
            "【下一步】\n"
            "先按上面的步骤写出你的第一步，我可以帮你检查思路是否正确；也可以把这题拆成小问，我逐步给提示。"
        )

    if plan == "direct":
        return (
            "【先判断】\n"
            f"这是一个概念理解类问题，核心是「{topic}」。{chapter_line}\n\n"
            "【知识点讲解】\n"
            + excerpt_block
            + _formula_block(kp_name, message)
            + "\n\n【要点梳理】\n"
            "- 定义：先明确概念的内涵与记号，区分它与相近概念；\n"
            "- 条件：定理成立的前提要逐条核对，缺一不可；\n"
            "- 方法：常见题型对应固定处理套路，先判断类型再选方法；\n"
            "- 几何/物理意义：结合直观背景理解结论，便于记忆与迁移。\n\n"
            "【易错提醒】\n"
            "- 只记结论不看条件，是最常见的失分点；\n"
            "- 概念之间的区别与联系要能自己举例说明。\n\n"
            "【下一步】\n"
            "建议做 1~2 道该知识点的 A 层基础题检验理解；需要的话我可以按你的掌握度生成分层练习。"
        )

    return (
        "【先判断】\n"
        f"你的问题围绕「{topic}」展开。{chapter_line}"
        "下面先给出概念层面的讲解，再给可执行的分析步骤；具体题目请先自己动笔，我不直接给最终答案。\n\n"
        "【思路引导】\n"
        + "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(steps))
        + "\n\n【知识点讲解】\n"
        + excerpt_block
        + _formula_block(kp_name, message)
        + "\n\n【易错提醒】\n"
        "- 套用公式前先核对条件（如连续性、可导性、极限类型）；\n"
        "- 注意符号、绝对值与定义域，含参数的题要分类讨论；\n"
        "- 计算完回代检验，避免低级失误。\n\n"
        "【下一步】\n"
        "你可以把自己的解题步骤发给我，我按步骤指出问题；也可以回复“诊断”生成针对性练习。"
    )


_NO_KNOWLEDGE_ANSWER = (
    "知识库暂无相关内容，我不能凭空编造答案。\n\n"
    "建议换一种问法：直接问某个知识点（例如“洛必达法则的使用条件”“定积分的几何意义”），"
    "或补充章节、条件与你的思路，我再基于课程资料为你讲解。"
)

# 非数学话题（软范围）的通用建议：不拦截，但不假装是课程内容
_SOFT_HINTS = {
    "英语": [
        "先做一套真题定位薄弱项，再按“词汇—长难句—题型”拆开训练。",
        "背单词用高频词表 + 例句 + 间隔重复，每天固定 30 分钟比突击更有效。",
        "阅读与翻译靠精读：逐句翻译真题文章，整理长难句和固定搭配。",
    ],
    "政治": [
        "按“马原—毛中特—史纲—思修”模块推进，先搭框架再背细节。",
        "选择题靠刷题总结易混点，分析题背模板并结合材料。",
        "关注当年考研大纲变化，新增考点优先复习。",
    ],
    "编程": [
        "先选一门语言（如 Python）打牢语法，再刷基础题培养调试习惯。",
        "每学一个概念就写一个可运行的小例子，遇到报错先读错误信息。",
        "项目驱动学习：从命令行小工具开始，逐步增加功能。",
    ],
    "生活": [
        "这类问题建议用对应的生活服务或搜索引擎获取实时信息。",
        "复习阶段注意作息与节奏，固定时段学习比熬夜更有效。",
        "需要放松时安排短时休息，避免长时间中断学习状态。",
    ],
}


def _soft_answer(message: str) -> str:
    topic = soft_scope_topic(message) or "该话题"
    hints = _SOFT_HINTS.get(topic) or [
        "先确认问题背景与目标，再拆成可执行的小步骤。",
        "把问题描述得越具体，越容易得到有用的答复。",
    ]
    body = "\n".join(f"- {hint}" for hint in hints)
    return (
        f"「{topic}」不属于本课程的高等数学教学内容，我不能展开讲解，但可以给你一些通用建议：\n"
        f"{body}\n\n"
        f"{SOFT_SCOPE_WARNING}\n"
        "如果你需要高数辅导，可以直接问具体知识点，我会基于课程资料讲解。"
    )


_FOLLOWUP_RE = re.compile(r"^(继续|接着|然后|那么?|那|它|这个|这道|上面|刚才|再)")
# v1.2 联调修复：短追问/换题式追问也要沿用上一轮问题做检索，否则多轮里检索会「失忆」
_FOLLOWUP_HINT_RE = re.compile(
    r"(再来|再出|再给|再讲|再练|再问|难一点|难点的|更难|简单点|容易点|"
    r"下一题|下一道|换一个|换个|换一道|继续|接着|还有|类似的|同类|出题|练一练)"
)


def _history_items(req) -> list[tuple[str, str]]:
    items = getattr(req, "history", None) or []
    out: list[tuple[str, str]] = []
    for item in list(items)[-10:]:
        if isinstance(item, dict):
            role, content = item.get("role", "user"), item.get("content", "")
        else:
            role, content = getattr(item, "role", "user"), getattr(item, "content", "")
        content = _text(content)
        if content:
            out.append((str(role or "user"), content))
    return out


def _history_context(req) -> str:
    """v1.2 多轮上下文：mock 答案也要体现「结合上文」，支持指代追问。"""
    items = _history_items(req)
    if not items:
        return ""
    last_user = ""
    for role, content in reversed(items):
        if role == "user":
            last_user = content
            break
    if not last_user:
        return ""
    return f"（结合上文，你上一轮在问「{last_user[:60]}」，本次回答延续同一知识点的讲解。）\n\n"


def last_user_message(req) -> str:
    """取最近一条 user 历史（用于多轮检索）。"""
    for role, content in reversed(_history_items(req)):
        if role == "user":
            return content
    return ""


def is_followup_question(message: str, req) -> bool:
    """判断是否指代式/换题式追问：短句（<=12 字）或命中追问关键词，且有历史。"""
    msg = _text(message or "").strip()
    if not msg or not _history_items(req):
        return False
    return bool(_FOLLOWUP_RE.search(msg) or _FOLLOWUP_HINT_RE.search(msg) or len(msg) <= 12)


def build_retrieval_query(req, message: str | None = None) -> str:
    """v1.2：多轮追问的检索 query = 当前问题 + 最近一条 user 历史。

    历史只参与检索，不进入 sources/citation；若 service 层已合并过（历史片段已在
    message 中），则不重复拼接。
    """
    text = _text(message if message is not None else getattr(req, "message", ""))
    if not is_followup_question(text, req):
        return text
    last_user = last_user_message(req)
    if not last_user or last_user[:20] in text:
        return text
    return text + " " + last_user[:120]


def _references_block(sources: list[dict], limit: int = 3) -> str:
    """回答末尾附教材引用（citation），便于学生回看原文。"""
    citations: list[str] = []
    for item in sources or []:
        citation = _text(item.get("citation"))
        if citation and citation not in citations:
            citations.append(citation)
    if not citations:
        return ""
    return "\n\n【参考资料】\n" + "\n".join(f"- {item}" for item in citations[:limit])


def _dedupe_sources(items: list[dict]) -> list[dict]:
    """按 chunkId 去重，保留首次出现（已按分数排序）。"""
    seen: set[str] = set()
    out: list[dict] = []
    for item in items or []:
        key = _text(item.get("chunkId")) or _text(item.get("citation")) or _text(item.get("documentId"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(item)
    return out


def _search_chunks(query: str, config: dict, class_id, query_terms=None):
    """向量检索：查询改写词只做扩展召回，不改变原问题的排序。

    v1.2 联调：把改写词直接拼进 query 会让「不定积分」压过原问题的「分部积分」
    语境（∫2xe^xdx 的 top1 被顶到第4章第1节）。因此原问题结果优先，扩展结果
    只补充新命中的片段；原问题无命中时才整体采用扩展结果。
    """
    kwargs = dict(
        top_k=settings.top_k,
        min_score=vector_index.default_min_score(),
        kb_scope=kb_scope_from_config(config),
        class_id=class_id,
    )
    primary = vector_index.search(query=query, **kwargs)
    extra = " ".join(term for term in (query_terms or []) if term and term not in query)[:120]
    if not extra:
        return primary
    expanded = vector_index.search(query=query + " " + extra, **kwargs)
    if not primary.enough:
        return expanded if expanded.enough else primary
    items = _dedupe_sources(primary.items + expanded.items)[: settings.top_k]
    kp_ids: list[str] = []
    for item in items:
        kp_id = _text(item.get("kpId"))
        if kp_id and kp_id not in kp_ids:
            kp_ids.append(kp_id)
    return VectorSearchResult(
        items=items,
        enough=True,
        top_score=max(primary.top_score, expanded.top_score),
        kp_ids=kp_ids,
    )


def qa(req, retriever=None, query_terms=None) -> dict:
    """AI2 /qa：范围判定 -> 向量检索 -> 按回答模式组织答案。

    行为矩阵（契约 v1.1）：
    - 硬拦截：blocked=true、统一话术、sources=[]、knowledgeCovered=false；
    - 软范围（英语/政治/编程/生活）：不拦截、给通用建议 + scopeWarning；
    - 数学范围内但知识库无命中：如实告知 + 建议换问法，knowledgeCovered=false；
    - 命中：knowledgeCovered=true，sources 带 citation。
    """
    config = normalize_teacher_config(getattr(req, "teacherConfig", None))
    message = _text(getattr(req, "message", ""))
    intent_name, _, _ = detect_intent(message)
    kp_ids = kp_registry.match(message, 4)
    action = action_for_intent(intent_name)

    # v1.3 ①硬拦截：线代/矩阵/概率等课程外数学 + 不当请求，直接统一话术
    blocked, block_reason = hard_scope_hit(message)
    if blocked:
        return {
            "answer": BLOCK_MESSAGE,
            "sources": [],
            "blocked": True,
            "blockReason": block_reason or "该内容超出当前教学范围",
            "intent": intent_name,
            "action": action,
            "kpIds": kp_ids,
            "knowledgeCovered": False,
            "scopeWarning": None,
            "mode": "mock",
        }

    # v1.3 ②教师配置命中（禁用话题/进度范围外/边界规则）：先过前置自测，
    # 通过后（同一 conversationId + topic，TTL 2h）才正常检索答疑。
    topic, gate_reason = teacher_scope_hit(message, config)
    if topic and not gate_store.is_passed(getattr(req, "conversationId", None), topic):
        record = gate_store.create(
            topic,
            gate_reason,
            getattr(req, "conversationId", None),
            message=message,
            topic_kp_ids=kp_ids,
        )
        return {
            "answer": gate_intro(record.topic),
            "sources": [],
            "blocked": False,
            "blockReason": None,
            "intent": "qa",
            "action": dict(GATE_ACTION),
            "kpIds": (record.topic_kp_ids or kp_ids)[:6],
            "knowledgeCovered": False,
            "scopeWarning": None,
            "mode": "mock",
            "gate": record_to_vo(record),
        }

    is_soft, warning = check_soft_scope(message)
    if is_soft:
        return {
            "answer": _soft_answer(message),
            "sources": [],
            "blocked": False,
            "blockReason": None,
            "intent": intent_name,
            "action": action,
            "kpIds": kp_ids,
            "knowledgeCovered": False,
            "scopeWarning": warning,
            "mode": "mock",
        }

    # v1.2：指代式/换题式追问把上一轮问题并入检索，避免多轮上下文断裂
    query = build_retrieval_query(req, message)
    if kp_ids:
        query = query + " " + " ".join(kp_registry.names(kp_ids))
    result = _search_chunks(query, config, getattr(req, "classId", None), query_terms)

    if not result.enough:
        return {
            "answer": _NO_KNOWLEDGE_ANSWER,
            "sources": [],
            "blocked": False,
            "blockReason": None,
            "intent": intent_name,
            "action": action,
            "kpIds": kp_ids or result.kp_ids,
            "knowledgeCovered": False,
            "scopeWarning": None,
            "mode": "mock",
        }

    top = result.items[0]
    kp_id = _text(top.get("kpId")) or (kp_ids[0] if kp_ids else "")
    kp_name = _kp_name(kp_id)
    chapter = kp_registry.chapter(kp_id)

    homework = is_homework_question(message)
    concept = is_concept_question(message)
    mode = config["answerMode"]
    if homework:
        plan = "homework"
    elif concept and mode == "DIRECT":
        plan = "direct"
    else:
        plan = "guided"

    answer = (
        _history_context(req)
        + _build_qa_answer(message, plan, result.items, kp_id, kp_name, chapter)
        + _references_block(result.items)
    )
    kp_out = kp_ids or result.kp_ids
    return {
        "answer": answer,
        "sources": result.items,
        "blocked": False,
        "blockReason": None,
        "intent": intent_name,
        "action": action,
        "kpIds": kp_out[:6],
        "knowledgeCovered": True,
        "scopeWarning": None,
        "mode": "mock",
    }


# --------------------------------------------------------------------------
# v1.3 前置自测通过后的三步教学（mock 文案固定含「第 1 步/第 2 步/第 3 步」）
# --------------------------------------------------------------------------
def gate_passed_lead_in(topic: str) -> str:
    return (
        "你已通过「%s」的前置自测。下面用三步带你学会它：先补齐前置，"
        "再建立概念，最后带做一题；作业/考试原题我仍不会直接给最终答案。" % topic
    )


def gate_failed_feedback(weak_names: list[str], topic: str) -> str:
    names = "」「".join([name for name in weak_names if name][:2])
    if names:
        return (
            "你在前置知识「%s」上还不够稳，建议先复习对应的定义与例题，"
            "再重新提问「%s」。本次先不展开教学。" % (names, topic)
        )
    return "前置自测未通过，建议先复习相关基础知识点，再重新提问「%s」。" % topic


def gate_teaching(record) -> dict:
    """把 gate 记录转成三步教学（只讲方法，不给题目最终答案）。"""
    topic = record.topic
    kp_id = (record.topic_kp_ids or [""])[0]
    kp = kp_registry.get(kp_id)
    chapter = ""
    if kp is not None:
        chapter = getattr(kp, "chapter", "") or kp_registry.chapter(kp_id)
    if not chapter:
        chapter = kp_registry.chapter(kp_id)
    points = [str(item) for item in (getattr(kp, "key_points", []) or []) if str(item).strip()]
    objectives = [str(item) for item in (getattr(kp, "objectives", []) or []) if str(item).strip()]
    prerequisites = [p.get("kpName") for p in record.prerequisites if p.get("kpName")]
    prereq_text = "」「".join(prerequisites[:3]) or "相关基础知识点"
    point_text = "；".join(points[:3]) or "定义、判定条件与标准解法"
    goal_text = objectives[0] if objectives else "能独立完成基础题并说明每一步依据"

    step1 = (
        "先补「%s」。回到教材对应小节，逐个说出它们的定义与适用条件，"
        "并各做 1 道课本基础题；卡住的地方记下来，这是后面「%s」的地基。"
        % (prereq_text, topic)
    )
    step2 = (
        "建立「%s」的概念框架：它属于%s。核心是 %s。"
        "先用自己的话复述判定条件，再对照教材例题确认每一步为什么成立。"
        % (topic, chapter or "高等数学", point_text)
    )
    step3 = (
        "带做一题（只给思路，不替你写最终答案）：先判断题目属于哪类结构，"
        "再写出第一步变形/换元/求导的依据，最后检查条件是否满足。"
        "完成后再对照答案，重点看「为什么想到这一步」。"
    )
    return {
        "steps": [
            {"title": "第 1 步：补齐前置", "content": step1},
            {"title": "第 2 步：建立概念", "content": step2},
            {"title": "第 3 步：带做一题", "content": step3},
        ],
        "practice": "建议自测：围绕「%s」做 2 道基础题 + 1 道变式题，目标：%s" % (topic, goal_text),
    }


# --------------------------------------------------------------------------
# AI5 /diagnose/questions
# --------------------------------------------------------------------------
def _question_vo(raw: dict, index: int, with_answer: bool = True) -> dict:
    difficulty = clamp(raw.get("difficulty", 1), 1, 4, 1)
    vo = {
        "questionId": _text(raw.get("qid")),
        "index": index,
        "kpId": _text(raw.get("kpId")),
        "kpName": _kp_name(_text(raw.get("kpId"))),
        "difficulty": difficulty,
        "type": _text(raw.get("type")) or "SINGLE",
        "stem": _text(raw.get("stem")),
        "options": [dict(option) for option in raw.get("options", [])],
        "hint": _text(raw.get("hint")),
        "layer": _layer_of(difficulty),
        "errorType": None,
    }
    if with_answer:
        vo["answerKey"] = raw.get("answerKey")
        vo["analysis"] = _text(raw.get("analysis"))
    return vo


def select_diagnostic(req) -> list[dict]:
    config = normalize_teacher_config(getattr(req, "teacherConfig", None))
    exam_mode = _text(getattr(req, "mode", "QUICK")).upper() or "QUICK"
    difficulty_max = clamp(
        getattr(req, "difficultyMax", 0) or config["maxDifficulty"], 1, 4, config["maxDifficulty"]
    )
    count = clamp(
        getattr(req, "count", 0) or (15 if exam_mode == "FULL" else 5), 1, 50, 5
    )
    scope = [kp for kp in (getattr(req, "kpIds", None) or config["effectiveKpIds"]) if kp]
    pool = [
        raw
        for raw in builtin_questions.all_questions()
        if raw["difficulty"] <= difficulty_max and (not scope or raw["kpId"] in scope)
    ]
    if not pool:
        return []
    mastery = _mastery_map(getattr(req, "mastery", None))
    order_index = {kp.kp_id: idx for idx, kp in enumerate(kp_registry.all())}
    groups: dict[str, list[dict]] = {}
    for raw in pool:
        groups.setdefault(raw["kpId"], []).append(raw)
    for items in groups.values():
        items.sort(key=lambda q: (0 if q["type"] == "SINGLE" else 1, q["difficulty"], q["qid"]))
    ordered = sorted(
        groups,
        key=lambda kp_id: (mastery.get(kp_id, 0.55), order_index.get(kp_id, 999)),
    )
    cursors = {kp_id: 0 for kp_id in ordered}
    selected: list[dict] = []
    while len(selected) < count:
        progressed = False
        for kp_id in ordered:
            if len(selected) >= count:
                break
            cursor = cursors[kp_id]
            if cursor < len(groups[kp_id]):
                selected.append(groups[kp_id][cursor])
                cursors[kp_id] = cursor + 1
                progressed = True
        if not progressed:
            break
    return [_question_vo(raw, idx + 1, with_answer=True) for idx, raw in enumerate(selected)]


def diagnose_questions(req) -> dict:
    return {"questions": select_diagnostic(req), "mode": "mock"}


# --------------------------------------------------------------------------
# AI6 /diagnose/grade
# --------------------------------------------------------------------------
_SUPERSCRIPT = {"⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
                "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9"}
_PUNCT_MAP = str.maketrans({"，": ",", "。": ".", "；": ";", "：": ":", "（": "(", "）": ")",
                            "＝": "=", "＋": "+", "－": "-", "×": "*", "÷": "/",
                            "＜": "<", "＞": ">", "　": " ", "、": ","})
_CHOICE_WORDS = {"正确": "T", "对": "T", "是": "T", "√": "T", "✓": "T",
                 "错误": "F", "错": "F", "否": "F", "×": "F"}


def _normalize_answer(value) -> str:
    text = _text(value).replace("−", "-").replace("–", "-")
    for sup, repl in _SUPERSCRIPT.items():
        text = text.replace(sup, repl)
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.translate(_PUNCT_MAP).replace("**", "^")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^(?:答案|答|解|y=|dydx)", "", text)
    return text.strip(".,;:")


def _choice_key(value) -> str:
    text = _normalize_answer(value).upper()
    if not text:
        return ""
    if text in {"T", "F"}:
        return text
    if text in _CHOICE_WORDS:
        return _CHOICE_WORDS[text]
    match = re.match(r"^([A-D])", text)
    return match.group(1) if match else text[:1]


def check_answer(question_type: str, student: str, correct: str, aliases: list[str] | None = None) -> bool:
    qtype = _text(question_type).upper() or "SINGLE"
    if qtype in {"SINGLE", "JUDGE"}:
        student_key = _choice_key(student)
        return bool(student_key) and student_key == _choice_key(correct)
    student_norm = _normalize_answer(student)
    if not student_norm:
        return False
    for candidate in [correct] + list(aliases or []):
        cand = _normalize_answer(candidate)
        if cand and student_norm == cand:
            return True
    try:
        expected = float(_normalize_answer(correct))
        actual = float(student_norm)
        return abs(actual - expected) < 1e-6
    except (TypeError, ValueError):
        return False


def _grade_level(score: int) -> str:
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "一般"
    return "待提升"


def _grade_advice(score: int, error_counts: dict[str, int], kp_names: list[str]) -> list[str]:
    if score >= 85:
        advice = ["整体掌握良好：保持节奏，用 C 层拓展题巩固综合运用能力，并注意书写规范。"]
    elif score >= 70:
        advice = ["整体较好：针对错题知识点做 2~3 道同类变式，把正确率稳定在 85% 以上。"]
    elif score >= 55:
        advice = ["基础尚可：先回到教材梳理定义、定理条件，再用 A/B 层题夯实基础，暂不追求难题。"]
    else:
        advice = ["基础较薄弱：按知识点逐个补齐概念与公式，先做课本例题与 A 层基础题，再逐步提高。"]
    rules = {
        "概念混淆": "辨析概念：把相近概念列成对照表，用反例说明条件不满足时的结论变化。",
        "计算失误": "计算专项：每天 10 分钟限时基础计算训练，写清每一步并回代检验。",
        "审题偏差": "审题训练：读题时圈出条件、目标与范围，先复述题意再动笔。",
        "方法不当": "方法归纳：按题型整理“识别特征—对应方法—易错点”卡片，做完题复盘方法选择。",
    }
    for error_type, _count in sorted(error_counts.items(), key=lambda pair: -pair[1]):
        if error_type in rules:
            advice.append(rules[error_type])
    if kp_names:
        advice.append("本次错题集中在：" + "、".join(kp_names[:3]) + "。建议优先复习这些知识点，并记录到错题本。")
    return advice[:4]


def grade(req) -> dict:
    raw_by_id = {raw["qid"]: raw for raw in builtin_questions.all_questions()}
    answer_map = {
        _text(getattr(item, "questionId", "")): _text(getattr(item, "answer", ""))
        for item in getattr(req, "answers", None) or []
    }
    results: list[dict] = []
    correct_count = 0
    error_counts: dict[str, int] = {}
    wrong_kp_names: list[str] = []

    for question in getattr(req, "questions", None) or []:
        qid = _text(getattr(question, "questionId", ""))
        qtype = _text(getattr(question, "type", "SINGLE")).upper() or "SINGLE"
        raw = raw_by_id.get(qid, {})
        correct_answer = _text(getattr(question, "answerKey", "")) or _text(raw.get("answerKey"))
        aliases = list(raw.get("answerAliases") or [])
        student_answer = answer_map.get(qid, "")
        is_correct = check_answer(qtype, student_answer, correct_answer, aliases)
        error_type = None
        if is_correct:
            correct_count += 1
        else:
            suggested = _text(getattr(question, "errorType", "")) or _text(raw.get("errorType"))
            if not _text(student_answer):
                error_type = "审题偏差"
            elif suggested in ERROR_TYPES:
                error_type = suggested
            elif qtype in {"SINGLE", "JUDGE"}:
                error_type = "概念混淆"
            else:
                error_type = "计算失误"
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
            kp_name = _kp_name(_text(getattr(question, "kpId", "")) or _text(raw.get("kpId")))
            if kp_name and kp_name not in wrong_kp_names:
                wrong_kp_names.append(kp_name)
        results.append(
            {
                "questionId": qid,
                "kpId": _text(getattr(question, "kpId", "")) or _text(raw.get("kpId")) or None,
                "kpName": _kp_name(_text(getattr(question, "kpId", "")) or _text(raw.get("kpId"))) or None,
                "correct": is_correct,
                "errorType": error_type,
                "analysis": _text(getattr(question, "analysis", "")) or _text(raw.get("analysis")),
                "studentAnswer": student_answer,
                "correctAnswer": correct_answer,
            }
        )

    total = len(results)
    score = round(correct_count * 100 / total) if total else 0
    level = _grade_level(score)
    error_summary = [
        {"errorType": error_type, "count": count, "ratio": round(count / total, 2) if total else 0.0}
        for error_type, count in sorted(error_counts.items(), key=lambda pair: -pair[1])
    ]
    return {
        "total": total,
        "correctCount": correct_count,
        "score": score,
        "level": level,
        "results": results,
        "errorSummary": error_summary,
        "advice": _grade_advice(score, error_counts, wrong_kp_names),
        "mode": "mock",
    }


# --------------------------------------------------------------------------
# AI7 /practice/questions
# --------------------------------------------------------------------------
_KB3_POOL: list[dict] | None = None
_KB3_HEADER = re.compile(r"题(\d{3})\s*\|\s*(kp\d{3})\s*\|\s*难度\s*([1-4])\s*\|\s*题型\s*[:：]\s*([^\n]+)")
_TYPE_MAP = {
    "选择题": "SINGLE",
    "判断题": "JUDGE",
    "填空题": "FILL",
    "计算题": "FILL",
    "证明题": "FILL",
    "讨论题": "FILL",
    "解答题": "FILL",
}


def _kb3_source_text() -> str:
    path = settings.knowledge_dir / "kb3_questions" / "高等数学题库-知识库版.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def kb3_pool() -> list[dict]:
    global _KB3_POOL
    if _KB3_POOL is not None:
        return _KB3_POOL
    text = _kb3_source_text()
    pool: list[dict] = []
    if text:
        blocks = re.split(r"\n(?=题\d{3}\s*\|)", text)
        for block in blocks:
            header = _KB3_HEADER.match(block)
            if not header:
                continue
            number, kp_id, difficulty, type_label = header.groups()
            body = block[header.end():]
            stem_match = re.search(r"题目\s*[:：]\s*(.+)", body)
            hint_match = re.search(r"解题思路\s*[:：]\s*(.+)", body)
            if not stem_match:
                continue
            hints = re.findall(r"提示\d+\s*[:：]\s*([^；;。\n]+)", hint_match.group(1) if hint_match else "")
            hint = "；".join(hints[:2]) or (clean_excerpt(hint_match.group(1), 120) if hint_match else "先回到定义，再选择对应方法。")
            pool.append(
                {
                    "qid": f"kb3-{number}-{kp_id}",
                    "kpId": kp_id,
                    "difficulty": int(difficulty),
                    "type": _TYPE_MAP.get(type_label.strip(), "FILL"),
                    "stem": clean_excerpt(stem_match.group(1), 220),
                    "hint": hint,
                    "options": [],
                    "answerKey": None,
                    "analysis": "",
                }
            )
    _KB3_POOL = pool
    return pool


def _practice_pool_for(low: int, high: int, difficulty_max: int, scope: list[str]) -> list[dict]:
    def match(item: dict) -> bool:
        return (
            low <= item["difficulty"] <= high
            and item["difficulty"] <= difficulty_max
            and (not scope or item["kpId"] in scope)
        )

    preferred = [item for item in kb3_pool() if match(item)]
    fallback = [
        raw for raw in builtin_questions.all_questions() if match(raw)
    ]
    combined: list[dict] = []
    seen: set[str] = set()
    for item in preferred + fallback:
        key = item.get("stem", "")
        if key and key not in seen:
            seen.add(key)
            combined.append(item)
    return combined


def _pick_diverse(pool: list[dict], count: int) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in pool:
        groups.setdefault(item["kpId"], []).append(item)
    ordered = list(groups.keys())
    cursors = {kp_id: 0 for kp_id in ordered}
    selected: list[dict] = []
    while len(selected) < count:
        progressed = False
        for kp_id in ordered:
            if len(selected) >= count:
                break
            cursor = cursors[kp_id]
            if cursor < len(groups[kp_id]):
                selected.append(groups[kp_id][cursor])
                cursors[kp_id] = cursor + 1
                progressed = True
        if not progressed:
            break
    return selected


def practice_questions(req) -> dict:
    config = normalize_teacher_config(getattr(req, "teacherConfig", None))
    layer = _text(getattr(req, "layer", "A")).upper() or "A"
    low, high = guess_difficulty_from_layer(layer)
    difficulty_max = clamp(getattr(req, "difficultyMax", 0) or 4, 1, 4, 4)
    difficulty_max = min(difficulty_max, config["maxDifficulty"])
    count = clamp(getattr(req, "count", 0) or 3, 1, 10, 3)
    scope = [kp for kp in (getattr(req, "kpIds", None) or config["effectiveKpIds"]) if kp]
    pool = _practice_pool_for(low, high, difficulty_max, scope)
    if not pool:
        # 难度上限优先：C/B 层在 maxDifficulty 被教师调低后可能无题可出，
        # 此时在「≤ 上限」的全部难度中挑最接近本层难度的题目，保证仍然可练习。
        fallback_pool = _practice_pool_for(1, difficulty_max, difficulty_max, scope)
        fallback_pool.sort(key=lambda item: (-item["difficulty"], item["kpId"], item.get("qid") or ""))
        pool = fallback_pool
    selected = _pick_diverse(pool, count)
    questions = [
        _question_vo({**item, "qid": item.get("qid") or f"practice-{idx + 1}"}, idx + 1, with_answer=False)
        for idx, item in enumerate(selected)
    ]
    for question in questions:
        question["layer"] = layer
    guidance = {
        "A": "A 层以基础题为主：先回顾定义与公式，再模仿例题步骤独立完成，重点是把过程写完整。",
        "B": "B 层开始综合：先判断题型与适用条件，再组合 2~3 个基本方法，做完后总结方法选择依据。",
        "C": "C 层面向拓展：注意一题多解与跨章节综合，先写思路框架再计算，控制单题时间。",
    }.get(layer, "先判断题型与适用条件，再选择方法动手。")
    return {"questions": questions, "guidance": guidance, "mode": "mock"}


# --------------------------------------------------------------------------
# AI8 /practice/hint
# --------------------------------------------------------------------------
_METHOD_HINTS = [
    (r"极限|lim|洛必达", "先判断极限类型（0/0、∞/∞、1^∞ 等），再决定用等价无穷小、洛必达法则或重要极限。"),
    (r"积分|∫|原函数", "观察被积函数结构：能凑微分就换元，分式考虑拆项，定积分注意上下限与对称性。"),
    (r"导数|求导|dy|微分", "识别复合结构与隐函数关系，外层函数乘以内层导数，必要时两边同时求导。"),
    (r"二重积分|∬", "先画积分区域，确定是 X 型还是 Y 型，再定积分次序与上下限。"),
    (r"级数|收敛|发散", "先看通项是否趋于 0，再选择比较判别法、比值判别法或根值判别法。"),
    (r"中值定理|罗尔|拉格朗日", "先验证闭区间连续、开区间可导等条件，再构造辅助函数或列等式。"),
    (r"偏导|多元", "对一个变量求偏导时把其余变量视为常数，注意复合函数链式法则。"),
    (r"微分方程", "先判断阶数与类型（可分离变量、一阶线性等），再套对应通解公式。"),
]


def practice_hint(req, retriever) -> dict:
    question = getattr(req, "question", None)
    stem = _text(getattr(question, "stem", "")) if question is not None else ""
    kp_id = _text(getattr(question, "kpId", "")) if question is not None else ""
    if not kp_id:
        matched = kp_registry.match(stem, 1)
        kp_id = matched[0] if matched else ""
    kp_name = _kp_name(kp_id) or "本题知识点"
    student_answer = _text(getattr(req, "studentAnswer", ""))

    steps: list[str] = []
    if student_answer:
        steps.append(
            f"先自查你写下的结果「{student_answer[:40]}」：逐条对照题目条件，确认每一步变形都是等价的，再继续往下走。"
        )
    steps.append(f"第 1 步（识别考点）：这道题主要考查「{kp_name}」，先把相关定义、定理的适用条件列出来。")
    method = ""
    for pattern, tip in _METHOD_HINTS:
        if re.search(pattern, stem) or re.search(pattern, kp_name):
            method = tip
            break
    steps.append("第 2 步（选择方法）：" + (method or "先判断题型与条件，再选择对应的基本方法，写出关键变形或等式。"))
    steps.append("第 3 步（自查完善）：检查符号、范围与特殊情况，确认每一步都有依据，再整理成完整过程。")

    result = retriever.search(
        query=stem + " " + kp_name,
        top_k=3,
        min_score=vector_index.default_min_score(),
        kb_scope=["KB1", "KB2", "KB4"],
        class_id=getattr(req, "classId", None),
    )
    return {
        "hint": "\n".join(steps[:3]),
        "strategy": "分步启发：只提供考点、方法与检查点，不直接给出最终结果",
        "sources": result.items,
        "mode": "mock",
    }


# --------------------------------------------------------------------------
# AI9 /plan
# --------------------------------------------------------------------------
def _chunk_for_kp(kp_id: str, retriever, kb: str = "KB2"):
    for chunk in retriever.chunks():
        if chunk.kp_id == kp_id and chunk.kb == kb:
            return chunk
    return None


def _study_points(kp, chunk) -> list[str]:
    points: list[str] = []
    for raw in re.split(r"[；;\n]", kp.key_points or ""):
        cleaned = raw.strip(" 　-·")
        if 4 <= len(cleaned) <= 40:
            points.append(cleaned)
    if len(points) < 3 and chunk is not None:
        for sentence in re.split(r"(?<=[。！？])", chunk.text):
            sentence = sentence.strip()
            if 10 <= len(sentence) <= 60 and not re.search(r"例题|解[:：]|答案", sentence):
                points.append(sentence)
            if len(points) >= 3:
                break
    if not points:
        points = [
            f"理解{kp.kp_name}的定义与记号",
            f"掌握{kp.kp_name}相关定理的成立条件",
            "完成 2 道基础题并复盘错因",
        ]
    return points[:3]


def _study_example(chunk) -> str:
    if chunk is None:
        return "以教材例题为模板：先写条件，再选方法，最后按步骤计算并检验。"
    text = chunk.text
    match = re.search(r"(例\s*\d*[\s\S]{0,160})", text)
    if match:
        example = re.sub(r"(?:解|证明|答案|解析)\s*[:：][\s\S]*$", "", match.group(1)).strip()
        if example:
            return clean_excerpt(example, 160)
    return "以教材例题为模板：先写条件，再选方法，最后按步骤计算并检验。"


def _daily_goal(kp, mastery: float | None) -> str:
    if mastery is None:
        return f"理解{kp.kp_name}的核心概念，能独立完成基础题。"
    if mastery < 0.3:
        return f"补齐{kp.kp_name}的概念与公式，正确完成 A 层基础题。"
    if mastery < 0.7:
        return f"巩固{kp.kp_name}，能处理 B 层常规综合题并说清方法依据。"
    return f"拓展{kp.kp_name}的综合应用，尝试 C 层题目并总结一题多解。"


def _practice_for_plan(kp_id: str, mastery: float | None, config: dict) -> list[dict]:
    if mastery is None or mastery < 0.3:
        layer = "A"
    elif mastery < 0.7:
        layer = "B"
    else:
        layer = "C"
    low, high = guess_difficulty_from_layer(layer)
    difficulty_max = min(4, config["maxDifficulty"])
    pool = [item for item in kb3_pool() if item["kpId"] == kp_id and low <= item["difficulty"] <= high and item["difficulty"] <= difficulty_max]
    if len(pool) < 3:
        pool = [item for item in kb3_pool() if item["kpId"] == kp_id and item["difficulty"] <= difficulty_max]
    if len(pool) < 3:
        pool = [raw for raw in builtin_questions.all_questions() if raw["kpId"] == kp_id and raw["difficulty"] <= difficulty_max]
    selected = list(pool[:3])
    # 若该知识点题目不足 3 题，用同难度区间的其他题目补足，保证每日练习 3 题左右
    if len(selected) < 3:
        used = {item.get("qid") or item.get("questionId") for item in selected}
        extras = [
            item for item in kb3_pool()
            if item["difficulty"] <= difficulty_max and (item.get("qid") or item.get("questionId")) not in used
        ]
        extras += [
            raw for raw in builtin_questions.all_questions()
            if raw["difficulty"] <= difficulty_max and raw["qid"] not in used
        ]
        for item in extras:
            if len(selected) >= 3:
                break
            qid = item.get("qid") or item.get("questionId")
            if qid in used:
                continue
            used.add(qid)
            selected.append(item)
    return [
        _question_vo({**item, "qid": item.get("qid") or f"plan-{kp_id}-{idx + 1}"}, idx + 1, with_answer=False)
        for idx, item in enumerate(selected)
    ]


def _plan_kp_order(req) -> list[str]:
    focus = [kp for kp in (getattr(req, "focusKpIds", None) or []) if kp_registry.get(kp)]
    mastery = _mastery_map(getattr(req, "mastery", None))
    weak = [kp for kp, value in sorted(mastery.items(), key=lambda pair: pair[1]) if kp_registry.get(kp)]
    kb3_ids = {item["kpId"] for item in kb3_pool()}
    covered = [kp.kp_id for kp in kp_registry.all() if kp.kp_id in kb3_ids]
    rest = [kp.kp_id for kp in kp_registry.all()]
    order: list[str] = []
    for kp_id in focus + weak + covered + rest:
        if kp_id not in order:
            order.append(kp_id)
    return order


def plan(req, retriever) -> dict:
    config = normalize_teacher_config(getattr(req, "teacherConfig", None))
    period = _text(getattr(req, "period", "WEEK")).upper() or "WEEK"
    default_days = 7 if period != "MONTH" else 30
    days_count = clamp(getattr(req, "days", 0) or default_days, 1, 31, default_days)
    mastery = _mastery_map(getattr(req, "mastery", None))
    order = _plan_kp_order(req)
    goal_text = _text(getattr(req, "goal", ""))
    start = date.today()
    days: list[dict] = []
    for index in range(days_count):
        kp_id = order[index % len(order)] if order else ""
        kp = kp_registry.get(kp_id)
        if kp is None:
            continue
        chunk = _chunk_for_kp(kp_id, retriever)
        day_goal = _daily_goal(kp, mastery.get(kp_id))
        if goal_text and index == 0:
            day_goal = goal_text + "；" + day_goal
        summary = kp.objectives or f"本日聚焦{kp.kp_name}，先理解概念与条件，再通过练习固化方法。"
        days.append(
            {
                "dayIndex": index + 1,
                "date": (start + timedelta(days=index)).isoformat(),
                "kpId": kp_id,
                "kpName": kp.kp_name,
                "goal": day_goal,
                "study": {
                    "summary": summary,
                    "points": _study_points(kp, chunk),
                    "example": _study_example(chunk),
                },
                "practiceQuestions": _practice_for_plan(kp_id, mastery.get(kp_id), config),
                "review": {
                    "summary": f"复盘{kp.kp_name}：用 3 分钟复述定义与条件，整理 1 条易错点，重做 1 道错题。",
                    "checklist": [
                        f"能不看资料说出{kp.kp_name}的定义与适用条件",
                        "完成当日练习并标注错因（概念/计算/审题/方法）",
                        "把新发现的易错点补充进错题本",
                    ],
                },
            }
        )
    weak_names = [
        _kp_name(kp_id)
        for kp_id, value in sorted(mastery.items(), key=lambda pair: pair[1])
        if value < 0.7 and _kp_name(kp_id)
    ][:3]
    if focus_names := [_kp_name(kp) for kp in (getattr(req, "focusKpIds", None) or []) if kp_registry.get(kp)]:
        focus_line = "优先覆盖你指定的知识点：" + "、".join(focus_names[:3]) + "。"
    elif weak_names:
        focus_line = "先突破掌握度较低的知识点：" + "、".join(weak_names) + "。"
    else:
        focus_line = "按课程章节顺序推进，兼顾基础与综合。"
    summary = (
        f"本计划共 {len(days)} 天，每天聚焦 1 个知识点：先学概念与方法，再做约 3 道分层练习，最后复盘。"
        f"{focus_line}"
    )
    return {
        "summary": summary,
        "days": days,
        "period": period,
        "daysCount": len(days),
        "title": f"个性化高数学习计划（{len(days)} 天）",
        "mode": "mock",
    }



# --------------------------------------------------------------------------
# AI10 /class-analysis
# --------------------------------------------------------------------------
def _accuracy_ratio(value) -> float:
    ratio = _num(value)
    if ratio > 1:
        ratio = ratio / 100.0
    return max(0.0, min(1.0, ratio))


def _distribution_avg(distribution: list[dict]) -> float:
    total = 0.0
    count = 0
    for item in distribution or []:
        if not isinstance(item, dict):
            continue
        amount = int(_num(item.get("count")))
        label = _text(item.get("range") or item.get("label"))
        numbers = [float(part) for part in re.findall(r"\d+(?:\.\d+)?", label)]
        if not numbers:
            mapping = {"薄弱": 0.2, "一般": 0.5, "良好": 0.8, "优秀": 0.9}
            mid = next((value for key, value in mapping.items() if key in label), 0.5)
        elif len(numbers) >= 2:
            low, high = numbers[0], numbers[1]
            if high <= 1:
                mid = (low + high) / 2
            else:
                mid = (low + high) / 200.0
        else:
            mid = numbers[0] / 100.0 if numbers[0] > 1 else numbers[0]
        total += mid * amount
        count += amount
    return round(total / count, 2) if count else 0.0


def _normalize_weak_kps(items: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        kp_id = _text(item.get("kpId"))
        if not kp_id:
            continue
        normalized.append(
            {
                "kpId": kp_id,
                "kpName": _text(item.get("kpName")) or _kp_name(kp_id),
                "avgMastery": round(max(0.0, min(1.0, _num(item.get("avgMastery", item.get("mastery"))))), 2),
                "studentCount": int(_num(item.get("studentCount", item.get("count")))),
            }
        )
    normalized.sort(key=lambda row: row["avgMastery"])
    return normalized[:10]


def _normalize_errors(items: list[dict], total: int) -> list[dict]:
    rows: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        error_type = _text(item.get("errorType"))
        if not error_type:
            continue
        count = int(_num(item.get("count")))
        ratio = _num(item.get("ratio"))
        if ratio <= 0 and total:
            ratio = count / total
        examples = [_text(example) for example in item.get("examples", []) or []][:2]
        rows.append({"errorType": error_type, "count": count, "ratio": round(ratio, 2), "examples": examples})
    rows.sort(key=lambda row: -row["count"])
    return rows


def _normalize_hot(items: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in items or []:
        if isinstance(item, dict):
            question = _text(item.get("question"))
            if question:
                rows.append(
                    {
                        "question": question,
                        "count": int(_num(item.get("count"))),
                        "lastAskedAt": item.get("lastAskedAt"),
                    }
                )
        elif isinstance(item, str) and item.strip():
            rows.append({"question": item.strip(), "count": 1, "lastAskedAt": None})
    rows.sort(key=lambda row: -row["count"])
    return rows[:10]


def _normalize_ranking(items: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "studentId": item.get("studentId"),
                "displayName": _text(item.get("displayName") or item.get("studentName")),
                "mastery": round(max(0.0, min(1.0, _num(item.get("mastery")))), 2),
                "interactions": int(_num(item.get("interactions"))),
            }
        )
    rows.sort(key=lambda row: -row["mastery"])
    return rows


def class_analysis(req) -> dict:
    student_count = int(_num(getattr(req, "studentCount", 0)))
    total_interactions = int(_num(getattr(req, "totalInteractions", 0)))
    active_students = int(_num(getattr(req, "activeStudents", 0)))
    ratio = _accuracy_ratio(getattr(req, "accuracy", 0))
    distribution = getattr(req, "masteryDistribution", None) or []
    weak_top10 = _normalize_weak_kps(getattr(req, "weakKps", None) or [])
    errors = _normalize_errors(getattr(req, "errorStats", None) or [], total_interactions)
    hot = _normalize_hot(getattr(req, "hotQuestions", None) or [])
    ranking = _normalize_ranking(getattr(req, "ranking", None) or [])
    avg_mastery = _distribution_avg(distribution)
    if not avg_mastery and weak_top10:
        avg_mastery = round(sum(row["avgMastery"] for row in weak_top10) / len(weak_top10), 2)
    active_rate = round(active_students / student_count, 2) if student_count else 0.0

    overview = {
        "studentCount": student_count,
        "avgMastery": avg_mastery,
        "interactionCount": total_interactions,
        "activeStudents": active_students,
        "accuracy": round(ratio, 2),
    }
    if active_rate:
        overview["activeRate"] = active_rate

    advice: list[dict] = []
    if weak_top10:
        names = [row["kpName"] for row in weak_top10[:3]]
        advice.append(
            {
                "title": "薄弱知识点优先安排专题复习",
                "content": "本班掌握度最低的知识点为：" + "、".join(names) + "。建议安排 1 次专题课：先用 10 分钟梳理概念与定理条件，再用 2 道例题示范方法选择，最后用 A/B 层题当堂检测。",
                "priority": "HIGH",
            }
        )
    if errors:
        top_error = errors[0]
        error_actions = {
            "概念混淆": "概念辨析：制作相近概念对照表，每讲一个概念配一个反例，课前提问抽查。",
            "计算失误": "计算规范：课堂设置 10 分钟限时基础计算训练，要求写出关键步骤并当堂互评。",
            "审题偏差": "审题训练：讲解例题前先让学生圈条件、复述目标，再讨论解法。",
            "方法不当": "方法归纳：按题型整理“识别特征—对应方法—易错点”清单，布置变式题对比练习。",
        }
        advice.append(
            {
                "title": "针对主要错因调整讲评重点",
                "content": f"错因占比最高的是「{top_error['errorType']}」（{top_error['count']} 次，占 {int(top_error['ratio'] * 100)}%）。"
                + error_actions.get(top_error["errorType"], "建议在讲评时放慢关键步骤，增加同类变式训练。"),
                "priority": "HIGH",
            }
        )
    if ratio < 0.55:
        advice.append(
            {
                "title": "正确率偏低，先降难度保基础",
                "content": "本班整体正确率约 {0}%。建议近期练习以 A/B 层为主，控制难题比例，先确保基础题正确率达到 75% 以上，再逐步提高难度。".format(int(ratio * 100)),
                "priority": "MEDIUM",
            }
        )
    elif ratio >= 0.75:
        advice.append(
            {
                "title": "整体较好，增加综合与拓展训练",
                "content": f"本班整体正确率约 {int(ratio * 100)}%，基础较扎实。建议每周加入 1 次 C 层综合训练，并让学生讲解题思路，训练表达与迁移能力。",
                "priority": "MEDIUM",
            }
        )
    advice.append(
        {
            "title": "用课堂互动数据做分层辅导",
            "content": f"本周期活跃学生 {active_students} 人，累计互动 {total_interactions} 次。建议对互动少且掌握度低的学生安排个别谈话，对高互动高掌握学生布置拓展任务，形成分层作业。",
            "priority": "MEDIUM",
        }
    )
    if len(advice) < 3:
        advice.append(
            {
                "title": "建立错题本与周复盘机制",
                "content": "建议要求学生按知识点记录错题、错因与正确思路，每周用 1 次课集中复盘高频错题，教师抽查并给出改进建议。",
                "priority": "LOW",
            }
        )
    if len(advice) < 3:
        advice.append(
            {
                "title": "用周测数据跟踪掌握度变化",
                "content": "建议每周安排一次 20 分钟限时小测，覆盖本周讲授的核心知识点，记录班级平均分与各知识点正确率，用连续两周的数据判断教学调整是否有效。",
                "priority": "LOW",
            }
        )
    if len(advice) < 3:
        advice.append(
            {
                "title": "课堂提问覆盖不同层次学生",
                "content": "建议每节课至少设计 3 个不同难度的问题，分别面向基础、中等与拔高学生，保证每名学生每周至少被提问一次，及时暴露理解偏差。",
                "priority": "LOW",
            }
        )

    summary = (
        f"本{_period_label(getattr(req, 'period', '7D'))}班级共 {student_count} 名学生，{active_students} 人活跃，"
        f"累计互动 {total_interactions} 次，平均掌握度 {avg_mastery}，整体正确率约 {int(ratio * 100)}%。"
    )
    if weak_top10:
        summary += "薄弱知识点集中在" + "、".join(row["kpName"] for row in weak_top10[:3]) + "；"
        summary += "建议优先安排概念梳理与分层练习，并结合错因讲评。"
    else:
        summary += "暂无明显薄弱知识点数据，建议继续积累互动与答题记录后再分析。"
    return {
        "overview": overview,
        "weakTop10": weak_top10,
        "errorSummary": errors,
        "hotQuestions": hot,
        "ranking": ranking,
        "advice": advice[:5],
        "summary": summary,
        "mode": "mock",
    }


def _period_label(period) -> str:
    return {"7D": "周", "30D": "月", "TERM": "学期"}.get(_text(period).upper(), "周")


# --------------------------------------------------------------------------
# AI11 /config/extract
# --------------------------------------------------------------------------
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "1": 1, "2": 2, "3": 3, "4": 4}
_KB_NAMES = {
    "大纲": "kb1",
    "教材": "kb2",
    "题库": "kb3",
    "教师资料": "kb4",
    "教师授权": "kb4",
    "教师资料库": "kb4",
}


def _default_kb_access(current: dict) -> dict:
    raw = current.get("kbAccess") if isinstance(current, dict) else None
    base = {"kb1": True, "kb2": True, "kb3": True, "kb4": False}
    if isinstance(raw, dict):
        for key in base:
            if key in raw:
                base[key] = bool(raw[key])
    return base


def _chapter_alias(text: str) -> str:
    for chapter in kp_registry.chapters():
        for token in re.split(r"[、与及]", chapter):
            token = token.strip()
            if token and token in text:
                return chapter
    return ""


def config_extract(req) -> dict:
    text = _text(getattr(req, "text", ""))
    current = getattr(req, "current", None) or {}
    if not isinstance(current, dict):
        current = {}
    patch: dict = {}
    explanations: list[str] = []
    consumed: list[str] = []
    segments = [segment.strip() for segment in re.split(r"[，,；;。\n]", text) if segment.strip()]

    # 回答模式
    if re.search(r"引导式|引导着|引导", text) and not re.search(r"不要引导", text):
        patch["answerMode"] = "GUIDED"
        explanations.append("回答模式改为引导式")
    elif re.search(r"直接讲解|直接讲|讲透|详细讲|直接给", text):
        patch["answerMode"] = "DIRECT"
        explanations.append("回答模式改为直接讲解")
    elif re.search(r"混合模式|混合", text):
        patch["answerMode"] = "MIXED"
        explanations.append("回答模式改为混合")

    # 最大难度
    difficulty_match = re.search(r"难度[^0-9一二三四]{0,8}(?:调到|调为|调成|调整到|调整成|改为|改为|设为|设成|到|为|成|不超过|最多)?\s*([1-4一二三四])", text)
    if difficulty_match:
        value = _CN_NUM[difficulty_match.group(1)]
        patch["maxDifficulty"] = value
        explanations.append(f"最大难度调为 {value}")
    else:
        easier = re.search(r"(简单|容易|基础)点|降低难度|降难度|难度降", text)
        harder = re.search(r"(难|拔高|提高)点|提高难度|增加难度|难度提", text)
        if easier or harder:
            base = int(_num(current.get("maxDifficulty"), 3)) if isinstance(current, dict) else 3
            value = clamp(base - 1 if easier else base + 1, 1, 4, base)
            patch["maxDifficulty"] = value
            explanations.append(f"最大难度调为 {value}")

    # 知识库开关
    kb_access = _default_kb_access(current)
    kb_changed = False
    for keyword, key in _KB_NAMES.items():
        if keyword == "教师授权":
            continue
        close_pattern = re.compile(r"(?:关闭|停用|禁用|不用|先关|暂时关闭)" + re.escape(keyword))
        open_pattern = re.compile(r"(?:开启|启用|打开|恢复|使用)" + re.escape(keyword))
        close_rev = re.compile(re.escape(keyword) + r"[^，,。；;]{0,4}(?:关闭|停用|禁用|不用|先关)")
        open_rev = re.compile(re.escape(keyword) + r"[^，,。；;]{0,4}(?:开启|启用|打开|恢复|使用)")
        if close_pattern.search(text) or close_rev.search(text):
            kb_access[key] = False
            kb_changed = True
            explanations.append(f"关闭{keyword}")
        elif open_pattern.search(text) or open_rev.search(text):
            kb_access[key] = True
            kb_changed = True
            explanations.append(f"开启{keyword}")
    if kb_changed:
        patch["kbAccess"] = kb_access

    # 知识范围章节
    scope_match = re.search(r"只(?:讲|学|复习|考|涉及)?第?([一二三四五六七八九十\d]{1,2})章", text)
    if scope_match:
        number = scope_match.group(1)
        chapters = kp_registry.chapters()
        index = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                 "七": 7, "八": 8, "九": 9, "十": 10}.get(number)
        index = index or int(number) if number.isdigit() else index
        if index and 1 <= index <= len(chapters):
            patch["knowledgeScope"] = {"mode": "CHAPTER", "chapters": [chapters[index - 1]], "kpIds": []}
            explanations.append(f"知识范围限定为第{index}章 {chapters[index - 1]}")

    # 禁用话题（“级数先别讲”）
    disabled = list(current.get("disabledTopics") or []) if isinstance(current, dict) else []
    for segment in segments:
        if re.search(r"先别讲|先不讲|别讲|不要讲|不用讲|暂停|跳过|暂时不学|先不学", segment):
            topic = re.sub(r"(?:先别讲|先不讲|别讲|不要讲|不用讲|暂停|跳过|暂时不学|先不学).*$", "", segment)
            topic = re.sub(r"^(?:暂时|先|把|将|请|老师)+", "", topic).strip(" 　，。")
            if 2 <= len(topic) <= 10 and topic not in disabled:
                disabled.append(topic)
                consumed.append(segment)
    if disabled and disabled != list(current.get("disabledTopics") or []):
        patch["disabledTopics"] = disabled
        explanations.append("禁用话题：" + "、".join(disabled))

    # 边界规则
    boundary_match = re.search(r"(仅解答|只解答|只回答|不讨论|禁止讨论|不要讨论)[^，,；;。]{0,60}", text)
    if boundary_match:
        patch["boundaryRules"] = boundary_match.group(0).strip()
        explanations.append("更新边界规则")
        consumed.append(boundary_match.group(0))

    recognized_patterns = (
        r"引导式|引导|直接讲解|直接讲|讲透|详细讲|直接给|混合模式|混合",
        r"难度[^0-9一二三四]{0,8}[1-4一二三四]|简单点|容易点|基础点|降低难度|降难度|难度降|难点|拔高点|提高难度|增加难度|难度提",
        r"(?:关闭|停用|禁用|不用|先关|暂时关闭|开启|启用|打开|恢复)(?:大纲|教材|题库|教师资料|教师授权)",
        r"(?:大纲|教材|题库|教师资料|教师授权)[^，,。；;]{0,4}(?:关闭|停用|禁用|不用|先关|开启|启用|打开|恢复)",
        r"只(?:讲|学|复习|考|涉及)?第?[一二三四五六七八九十\d]{1,2}章",
        r"先别讲|先不讲|别讲|不要讲|不用讲|暂停|跳过|暂时不学|先不学",
        r"仅解答|只解答|只回答|不讨论|禁止讨论|不要讨论",
    )
    unrecognized = []
    for segment in segments:
        if segment in consumed:
            continue
        if any(re.search(pattern, segment) for pattern in recognized_patterns):
            continue
        if re.search(r"改|调|关闭|开启|停用|禁用|别|不要|只|优先|难度|模式|资料|章节|级数", segment):
            unrecognized.append(segment)

    if not patch:
        return {
            "patch": {},
            "explanation": "未能从描述中识别出可自动应用的配置项，请检查表述（例如“把最大难度调到2”“暂时关闭教师资料”“级数先别讲”）。",
            "unrecognized": unrecognized or ([text] if text else []),
            "mode": "mock",
        }
    explanation = "识别到 " + str(len(explanations)) + " 项修改：" + "；".join(explanations) + "。"
    if unrecognized:
        explanation += "另有 " + str(len(unrecognized)) + " 处表述未识别，请确认。"
    return {"patch": patch, "explanation": explanation, "unrecognized": unrecognized, "mode": "mock"}
