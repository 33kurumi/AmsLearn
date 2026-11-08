"""提示词模板：由扣子 W0~W4 工作流提示词迁移而来。

统一约定：
- 教学对象是考研学生，课程为高等数学，答案用中文 Markdown + LaTeX（行内 $...$）；
- 只依据注入的知识库片段作答，片段不足时明确说明，禁止编造；
- 作业/考试原题不给最终答案；超范围话题统一拒答；
- 每类调用都要求模型只输出一个 JSON 对象，便于容错解析。
"""
from __future__ import annotations

import json
from typing import Any

BLOCK_MESSAGE = "该内容超出当前教学范围，暂时无法解答。"

SYSTEM_QA = """你是「个性化学习导师」系统里的高等数学考研助教，服务对象是备考研究生入学考试的学生。
授课范围严格限定为高等数学（微积分、级数、常微分方程等），不回答线性代数、概率统计、英语、政治等其他科目，也不解答考试作弊相关请求。
你的回答必须遵守：
1. 只依据【知识库片段】中的内容讲解；片段未覆盖的部分要明确说“知识库暂无相关内容”，禁止编造定义、定理条件或结论。
2. 引导式/混合模式下以启发为主：先判断学生问题类型，再给思路引导，不直接给出作业或试卷题目的最终答案与完整解题步骤。
3. 直接讲解模式可以把概念、定理条件讲透，但涉及作业/考试原题时仍只给方法与检查点，不给最终结果。
4. 回答使用中文 Markdown，公式用 $...$ 或 $$...$$；结构固定为：
【先判断】一句话判断问题属于概念理解、方法选择还是具体计算。
【思路引导】用 2~4 步提示思考路径，必要时给可追问的问题。
【知识点讲解】结合片段讲清定义、定理条件、适用场景与几何/代数直观。
【易错提醒】指出 1~3 个常见错误与规避方法。
【下一步】给出可执行的一小步（练习方向或自我检查问题）。
5. 引用知识库时只写【参考资料】里的 citation（例如“《高等数学教材讲义》第3章·第3节 洛必达法则”）；禁止出现“片段 5”“chunk 3”“kp021”这类内部编号，也不要暴露 documentId。
6. 多轮对话时结合【最近对话】回答，学生用“它/这个/继续”指代上文时要先点明你理解的对象。
7. 只输出 JSON：{"answer": "按上述五段组织的 Markdown 文本"}，不要输出 JSON 以外的任何内容。"""

SYSTEM_PRACTICE = """你是高等数学考研辅导老师，负责为分层练习补充一小段引导语。
要求：中文、面向学生、只讲本层练习的目标与做题策略，不出现任何具体题目的最终答案或数值结果；不超过 160 字。
只输出 JSON：{"guidance": "..."}。"""

SYSTEM_HINT = """你是高等数学考研辅导老师，学生正在做一道练习，需要递进式提示。
要求：
1. 输出 2~3 条由浅入深的提示，先用一句话帮学生自查已有思路，再点出关键方法，最后给检查点；
2. 只提示方法与方向，绝对不能出现该题的最终数值答案、最终表达式或完整解答；
3. 中文，可用 $...$ 写公式。
只输出 JSON：{"hint": "Markdown 文本", "strategy": "一句话说明用了什么教学策略"}。"""

SYSTEM_PLAN = """你是高等数学考研辅导老师，负责为学生制定按天推进的学习计划。
要求：
1. 输出整体计划说明 summary（重点、节奏、如何利用薄弱点，2~4 句）；
2. 按既定点位逐日给出一句话学习目标 goal，每天目标要具体可执行、与当天知识点对应；
3. 知识讲解、例题、练习与复盘检查清单由系统按知识点模板生成，你不必输出；难度不超过教师配置的最大难度；
4. 中文，不要空话；days 的 dayIndex 必须与既定点位一一对应、数量一致。
只输出 JSON：
{"summary": "整体计划说明", "days": [{"dayIndex": 1, "goal": "当天具体目标"}]}"""

SYSTEM_CLASS_ANALYSIS = """你是高等数学教研组的教学分析助手，面向教师输出班级学情分析与教学改进建议。
要求：
1. 只依据给定的统计数据与规则做归纳，不答疑、不评价学生个人、不编造数据；
2. 建议必须可执行：说清“做什么、怎么做、做到什么程度”，至少 3 条，按 HIGH/MEDIUM/LOW 排优先级；
3. 中文，语气专业克制。
只输出 JSON：
{"summary": "班级学情总体判断（2~4 句）",
 "advice": [{"title": "...", "content": "...", "priority": "HIGH"}]}"""

SYSTEM_CONFIG_EXTRACT = """你是教学配置解析助手，把教师的自然语言要求转换成结构化配置补丁 patch。
可识别字段：
- answerMode：GUIDED / DIRECT / MIXED
- maxDifficulty：1~4 的整数
- knowledgeScope：{"mode":"CHAPTER"|"CUSTOM"|"ALL","chapters":[],"kpIds":[]}
- kbAccess：{"kb1":bool,"kb2":bool,"kb3":bool,"kb4":bool}（大纲/教材/题库/教师资料）
- disabledTopics：字符串数组
- boundaryRules：字符串
要求：
1. 只输出能明确判断的字段；识别不到的表述放进 unrecognized；
2. explanation 用中文说明改了哪几项；
3. 只输出 JSON：{"patch": {}, "explanation": "...", "unrecognized": []}，不要直接保存配置。"""


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

def _config_lines(config: dict[str, Any] | None) -> str:
    if config is None:
        cfg = {}
    elif not isinstance(config, dict):
        # 如果是 Pydantic model 对象，转成字典
        cfg = config.model_dump()
    else:
        cfg = config
    kb = cfg.get("kbAccess") or {}
    return (
        "- 回答模式：" + str(cfg.get("answerMode", "MIXED")) + "（GUIDED 引导 / DIRECT 直接讲解 / MIXED 混合）\n"
        "- 最大难度：" + str(cfg.get("maxDifficulty", 3)) + "（1~4）\n"
        "- 知识点范围：" + (", ".join(cfg.get("effectiveKpIds") or []) or "全部") + "\n"
        "- 禁用话题：" + ("、".join(cfg.get("disabledTopics") or []) or "无") + "\n"
        "- 边界规则：" + (str(cfg.get("boundaryRules") or "").strip() or "无") + "\n"
        "- 知识库开关：" + _json(kb)
    )


def _mastery_lines(mastery: list[Any] | None) -> str:
    rows = []
    for item in mastery or []:
        kp_id = getattr(item, "kpId", "") if not isinstance(item, dict) else item.get("kpId", "")
        kp_name = getattr(item, "kpName", "") if not isinstance(item, dict) else item.get("kpName", "")
        value = getattr(item, "mastery", None) if not isinstance(item, dict) else item.get("mastery")
        if kp_id and value is not None:
            rows.append(f"- {kp_id} {kp_name or ''} 掌握度 {float(value):.2f}")
    return "\n".join(rows) or "- 暂无掌握度数据"


def _sources_lines(sources: list[dict[str, Any]] | None) -> str:
    """只给模型 citation + 摘录，不暴露“片段N/documentId/kpNNN”等内部编号。"""
    rows = []
    for item in sources or []:
        citation = str(item.get("citation") or "").strip()
        title = str(item.get("title") or "").strip()
        label = citation or (f"《{title}》" if title else "知识库相关章节")
        rows.append(
            f"[资料] {label}\n" + str(item.get("excerpt") or item.get("text") or "")[:600]
        )
    return "\n\n".join(rows) or "（本次检索没有命中可用的知识库片段）"


def _boundary_lines(base: dict[str, Any]) -> str:
    """按检索/范围判定结果追加边界约束，保证真实模型输出符合契约行为矩阵。"""
    lines = []
    if base.get("scopeWarning"):
        lines.append("本题不属于高等数学课程内容：只给简短的通用建议，不要展开英/政/编程等学科讲解，结尾附范围提示。")
    elif not base.get("knowledgeCovered", True):
        lines.append("知识库没有命中相关片段：开头必须写“知识库暂无相关内容”，结尾建议学生“换一种问法”，禁止编造具体结论。")
    if base.get("knowledgeCovered"):
        lines.append("【知识库片段】已命中：讲解要落回片段中的定义与条件，不要编造引用；系统会自动在末尾追加【参考资料】。")
    return ("【本次边界提示】\n" + "\n".join(f"- {line}" for line in lines) + "\n\n") if lines else ""


HISTORY_MAX_ITEMS = 8
HISTORY_MAX_CHARS = 4000


def trim_history(history: list[Any] | None) -> list[str]:
    """v1.2：多轮上下文只取最后 8 条、总字符不超过 4000（从最近往前保留）。"""
    rows: list[str] = []
    for item in list(history or [])[-10:]:
        role = getattr(item, "role", "user") if not isinstance(item, dict) else item.get("role", "user")
        content = getattr(item, "content", "") if not isinstance(item, dict) else item.get("content", "")
        content = str(content or "").strip()
        if content:
            rows.append(f"{role}: {content}")
    kept: list[str] = []
    total = 0
    for row in reversed(rows[-HISTORY_MAX_ITEMS:]):
        if total + len(row) > HISTORY_MAX_CHARS and kept:
            break
        kept.append(row[:HISTORY_MAX_CHARS])
        total += len(row)
    return list(reversed(kept))


def qa_messages(req, base: dict[str, Any]) -> tuple[str, str]:
    history = trim_history(getattr(req, "history", None))
    user = (
        "【教师配置】\n" + _config_lines(getattr(req, "teacherConfig", None)) + "\n\n"
        "【学生掌握度】\n" + _mastery_lines(getattr(req, "mastery", None)) + "\n\n"
        "【最近对话（结合上文回答）】\n" + ("\n".join(history) or "（无）") + "\n\n"
        + _boundary_lines(base)
        + "【知识库片段】\n" + _sources_lines(base.get("sources")) + "\n\n"
        "【学生问题】" + str(getattr(req, "message", "")) + "\n\n"
        "请按系统要求组织回答，只输出 JSON。"
    )
    return SYSTEM_QA, user


def practice_messages(req, base: dict[str, Any]) -> tuple[str, str]:
    stems = "\n".join(
        f"- 第{i + 1}题（" + str(q.get("kpName") or q.get("kpId")) + "，难度" + str(q.get("difficulty")) + "）："
        + str(q.get("stem") or "")[:200]
        for i, q in enumerate(base.get("questions") or [])
    )
    user = (
        "【教师配置】\n" + _config_lines(getattr(req, "teacherConfig", None)) + "\n\n"
        "【练习层级】" + str(getattr(req, "layer", "A")) + " 层（A 基础 / B 提高 / C 综合）\n"
        "【本次题目】\n" + (stems or "（无）") + "\n\n"
        "请写一段面向学生的本层练习引导语，只输出 JSON。"
    )
    return SYSTEM_PRACTICE, user


def hint_messages(req) -> tuple[str, str]:
    question = getattr(req, "question", None)
    stem = getattr(question, "stem", "") if question is not None else ""
    kp_name = getattr(question, "kpName", "") if question is not None else ""
    kp_id = getattr(question, "kpId", "") if question is not None else ""
    layer = getattr(question, "layer", "") if question is not None else ""
    user = (
        "【题目】" + str(stem) + "\n"
        "【知识点】" + str(kp_id or "") + " " + str(kp_name or "") + "\n"
        "【层级】" + str(layer or "未标注") + "\n"
        "【学生当前思路/答案】" + (str(getattr(req, "studentAnswer", "")) or "（空，还没动笔）") + "\n\n"
        "请给递进提示，严禁出现最终数值答案，只输出 JSON。"
    )
    return SYSTEM_HINT, user


def plan_messages(req, base: dict[str, Any]) -> tuple[str, str]:
    outline = []
    for day in base.get("days") or []:
        outline.append(
            f"- 第{day.get('dayIndex')}天 {day.get('kpId')} {day.get('kpName')}：目标 {day.get('goal')}"
        )
    user = (
        "【教师配置】\n" + _config_lines(getattr(req, "teacherConfig", None)) + "\n\n"
        "【学生掌握度】\n" + _mastery_lines(getattr(req, "mastery", None)) + "\n\n"
        "【计划周期】" + str(getattr(req, "period", "WEEK")) + "，共 " + str(len(base.get("days") or [])) + " 天\n"
        "【学习目标】" + (str(getattr(req, "goal", "")) or "系统根据薄弱点自动安排") + "\n\n"
        "【既定点位安排】\n" + ("\n".join(outline) or "（无）") + "\n\n"
        "请在保持点位不变的前提下润色计划，只输出 JSON。"
    )
    return SYSTEM_PLAN, user


def class_analysis_messages(req, base: dict[str, Any]) -> tuple[str, str]:
    payload = {
        "period": getattr(req, "period", "7D"),
        "className": getattr(req, "className", ""),
        "studentCount": getattr(req, "studentCount", 0),
        "totalInteractions": getattr(req, "totalInteractions", 0),
        "activeStudents": getattr(req, "activeStudents", 0),
        "accuracy": getattr(req, "accuracy", 0),
        "overview": base.get("overview"),
        "weakTop10": base.get("weakTop10"),
        "errorSummary": base.get("errorSummary"),
        "hotQuestions": base.get("hotQuestions"),
    }
    user = (
        "【班级统计】\n" + _json(payload) + "\n\n"
        "请输出班级学情总结与至少 3 条可执行教学建议，只输出 JSON。"
    )
    return SYSTEM_CLASS_ANALYSIS, user


def config_extract_messages(req) -> tuple[str, str]:
    user = (
        "【当前配置】\n" + _json(getattr(req, "current", None) or {}) + "\n\n"
        "【教师原话】" + str(getattr(req, "text", "")) + "\n\n"
        "请抽取配置补丁，只输出 JSON。"
    )
    return SYSTEM_CONFIG_EXTRACT, user


SYSTEM_GATE_TEACHING = """你是高等数学考研辅导老师，学生刚刚通过了一次“前置自测”，现在要正式学习教师配置中暂缓的知识点。
你的任务是把系统给出的三步教学草稿改写成面向学生的完整教学文案，必须遵守：
1. 严格分成三步，标题固定以“第 1 步：”“第 2 步：”“第 3 步：”开头，分别对应补齐前置、建立概念、带做一题；
2. 只讲方法与思路，不给任何作业/试卷原题的最终答案与完整过程；第 3 步可以给一道自测题的方向与检查点；
3. 内容要落回【知识库片段】里的定义、条件与结论，片段没覆盖的说法不要编造；
4. 中文 Markdown，公式用 $...$；每步 60~140 字，语气鼓励、具体可执行，不要写成大段讲义。
只输出 JSON：{"steps": [{"title": "第 1 步：...", "content": "..."}], "practice": "一句话说明接下来练什么"}"""


def gate_teaching_messages(record, gate: dict, sources, draft: dict) -> tuple[str, str]:
    """前置自测通过后的三步教学：注入主题、前置知识点、片段与规则草稿。"""
    prerequisites = []
    for item in (gate or {}).get("prerequisites") or []:
        prerequisites.append(
            "- " + str(item.get("kpId") or "") + " " + str(item.get("kpName") or "")
            + "（" + str(item.get("citation") or "") + "）"
        )
    draft_steps = []
    for step in (draft or {}).get("steps") or []:
        draft_steps.append("- " + str(step.get("title") or "") + "：" + str(step.get("content") or ""))
    user = (
        "【本次主题】" + str(getattr(record, "topic", "") or (gate or {}).get("topic") or "") + "\n"
        "【教师暂缓原因】" + str((gate or {}).get("reason") or "教师配置中暂缓讲解") + "\n\n"
        "【前置知识点】\n" + ("\n".join(prerequisites) or "（无）") + "\n\n"
        "【知识库片段】\n" + _sources_lines(sources) + "\n\n"
        "【系统三步草稿，请保持三步结构并润色】\n" + ("\n".join(draft_steps) or "（无）") + "\n\n"
        "请输出三步教学文案，只输出 JSON。"
    )
    return SYSTEM_GATE_TEACHING, user

