"""教学边界、意图与教师配置的规则层（mock/real 共用）。

对齐 docs/01-接口约定.md 与 PRD 的硬性规则：
- 超出课程范围 / 命中禁用话题 / 超出教师配置范围 -> blocked=true，统一话术；
- 作业、习题、真题、考试题 -> 严禁给最终答案与完整解题过程，只做分步引导；
- 概念类问题（定义、定理、性质、适用条件等）允许完整讲解；
- 统一话术逐字固定，前端与 Java 侧会按此文案显示。
"""
from __future__ import annotations

import re

BLOCK_MESSAGE = "该内容超出当前教学范围，暂时无法解答。"

ANSWER_MODE = {"GUIDED", "DIRECT", "MIXED"}

# 硬拦截：属于「数学类但不在本课程范围」或明确超纲的内容 -> blocked=true
HARD_SCOPE_KEYWORDS = [
    "线性代数", "线代", "矩阵", "行列式", "特征值", "特征向量", "二次型", "向量空间",
    "概率论", "概率", "数理统计", "随机变量", "期望", "方差", "正态分布", "假设检验",
    "大学物理", "物理", "电路", "电磁", "力学",
    "离散数学", "复变函数", "数学分析", "实变函数", "泛函分析",
]
# 兼容旧引用
SCOPE_KEYWORDS = HARD_SCOPE_KEYWORDS

# 软范围：与高数无关、但也不该被硬拦截的话题（英语/政治/编程/生活等）
# 仍要给「有帮助的通用回答 + 范围提醒」，blocked=false、knowledgeCovered=false、sources=[]
SOFT_SCOPE_KEYWORDS = [
    "英语", "单词", "语法", "翻译", "阅读理解", "四六级", "考研英语",
    "政治", "马原", "毛概", "史纲", "思修", "考研政治",
    "编程", "代码", "Java", "Python", "C++", "数据结构", "算法题", "前端", "后端",
    "天气", "气温", "下雨", "食堂", "吃饭", "游戏", "电影", "音乐", "明星",
    "就业", "找工作", "考研报名", "课程表",
]
SOFT_SCOPE_WARNING = (
    "该问题不属于高等数学课程内容，本节只做简要回应；"
    "如需高数讲解，请直接问具体知识点（如极限、导数、积分）。"
)
# 软范围的细分话题，用于给出针对性但不越界的通用建议
SOFT_TOPICS = [
    ("英语", ["英语", "单词", "语法", "翻译", "阅读理解", "四六级", "考研英语"]),
    ("政治", ["政治", "马原", "毛概", "史纲", "思修", "考研政治"]),
    ("编程", ["编程", "代码", "Java", "Python", "C++", "数据结构", "算法题", "前端", "后端"]),
    ("生活", ["天气", "气温", "下雨", "食堂", "吃饭", "游戏", "电影", "音乐", "明星", "就业", "找工作", "考研报名", "课程表"]),
]

UNETHICAL_KEYWORDS = [
    "代考", "代写", "枪手", "作弊", "泄题", "泄露考题", "考试答案", "帮我考试", "替考",
    "作业答案直接", "把答案发我", "完整答案",
]

HOMEWORK_KEYWORDS = [
    "作业", "习题", "试卷", "真题", "考试", "测验", "测试题", "课后题", "练习题",
    "这道题", "这个题", "这题", "第几题", "题目", "求极限", "求导", "求积分",
    "求微分", "计算", "证明", "答案", "怎么做", "怎么解", "不会做", "解题", "步骤",
    "过程", "帮我做", "给个答案",
]

CONCEPT_KEYWORDS = [
    "定义", "概念", "定理", "原理", "性质", "含义", "意义", "是什么", "为什么",
    "区别", "联系", "适用条件", "使用条件", "条件", "方法", "技巧", "怎么理解",
    "如何理解", "讲解", "介绍一下", "总结", "归纳", "几何意义", "物理意义",
]

DIAGNOSE_KEYWORDS = ["诊断", "测一测", "检测", "评估", "水平测试", "诊断一下", "摸底"]
PLAN_KEYWORDS = ["计划", "规划", "安排", "学习路线", "复习路线", "周计划", "学习方案"]
PRACTICE_KEYWORDS = ["练习", "刷题", "出题", "来几道", "做几道", "题目练", "巩固练习"]

CHAPTER_ALIASES = [
    ("函数、极限与连续", ["极限", "连续", "函数", "无穷小"]),
    ("导数与微分", ["导数", "微分", "求导"]),
    ("微分中值定理与导数的应用", ["中值定理", "洛必达", "单调", "极值", "泰勒"]),
    ("不定积分", ["不定积分", "原函数", "换元积分", "分部积分"]),
    ("定积分及其应用", ["定积分", "微积分基本定理", "牛顿-莱布尼茨"]),
    ("多元函数微分学", ["多元函数", "偏导", "全微分", "方向导数"]),
    ("重积分", ["二重积分", "三重积分", "重积分"]),
    ("无穷级数", ["级数", "收敛", "幂级数", "泰勒级数"]),
    ("常微分方程", ["微分方程", "通解", "特解", "可分离变量"]),
]


def clamp(value, low: int, high: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "on", "开启", "是"}:
            return True
        if text in {"false", "0", "no", "off", "关闭", "否"}:
            return False
    return default


def normalize_teacher_config(raw) -> dict:
    """归一化教师配置，缺省值遵循「引导式 + 难度3 + KB4 默认关闭」。"""
    if raw is None:
        data: dict = {}
    elif hasattr(raw, "model_dump"):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = dict(raw)
    else:  # pragma: no cover - 防御
        data = {}

    answer_mode = str(data.get("answerMode") or "MIXED").strip().upper()
    if answer_mode not in ANSWER_MODE:
        answer_mode = "MIXED"

    effective = []
    for kp_id in data.get("effectiveKpIds") or []:
        kp_id = str(kp_id).strip()
        if re.fullmatch(r"kp\d{3}", kp_id) and kp_id not in effective:
            effective.append(kp_id)

    disabled = []
    for item in data.get("disabledTopics") or []:
        text = str(item).strip()
        if text and text not in disabled:
            disabled.append(text)

    raw_access = data.get("kbAccess") or {}
    kb_access = {
        "kb1": _as_bool(raw_access.get("kb1"), True),
        "kb2": _as_bool(raw_access.get("kb2"), True),
        "kb3": _as_bool(raw_access.get("kb3"), True),
        "kb4": _as_bool(raw_access.get("kb4"), False),
    }

    return {
        "answerMode": answer_mode,
        "maxDifficulty": clamp(data.get("maxDifficulty", 3), 1, 4, 3),
        "effectiveKpIds": effective,
        "boundaryRules": str(data.get("boundaryRules") or "").strip(),
        "disabledTopics": disabled,
        "kbAccess": kb_access,
    }


def kb_scope_from_config(config: dict) -> list[str]:
    """把 kbAccess 转成检索范围；KB5 只供后台，不对用户开放。"""
    access = config.get("kbAccess") or {}
    scope = []
    for idx, kb in ((1, "KB1"), (2, "KB2"), (3, "KB3"), (4, "KB4")):
        if access.get(f"kb{idx}", idx <= 3):
            scope.append(kb)
    return scope or ["KB2"]


def detect_intent(message: str) -> tuple[str, float, str]:
    """返回 (intent, confidence, reason)。"""
    text = message or ""
    if any(keyword in text for keyword in DIAGNOSE_KEYWORDS):
        return "diagnose", 0.92, "包含诊断/测评类关键词"
    if any(keyword in text for keyword in PLAN_KEYWORDS):
        return "plan", 0.9, "包含学习计划/规划类关键词"
    if any(keyword in text for keyword in PRACTICE_KEYWORDS):
        return "practice", 0.88, "包含练习/出题类关键词"
    if text.strip():
        return "qa", 0.7, "默认按答疑处理"
    return "unknown", 0.2, "消息为空"


def action_for_intent(intent: str) -> dict:
    if intent == "diagnose":
        return {"type": "DIAGNOSE", "label": "开始诊断", "params": {"mode": "QUICK"}}
    if intent == "plan":
        return {"type": "PLAN", "label": "生成学习计划", "params": {"period": "WEEK", "days": 7}}
    if intent == "practice":
        return {"type": "PRACTICE", "label": "去练习", "params": {"layer": "A", "count": 3}}
    return {"type": "NONE", "label": "", "params": None}


def is_concept_question(message: str) -> bool:
    text = message or ""
    has_concept = any(keyword in text for keyword in CONCEPT_KEYWORDS)
    if not has_concept:
        return False
    hard_task = re.search(
        r"作业|习题|试卷|真题|考试|测验|第[一二三四五六七八九十\d]{1,3}题|这道题|这个题|这题|"
        r"求极限|求导|求积分|求微分|求.{0,4}值|计算|证明|答案|怎么做|怎么解|不会做|解题|步骤|过程|帮我做",
        text,
    )
    return hard_task is None


def is_homework_question(message: str) -> bool:
    text = message or ""
    if is_concept_question(text):
        return False
    if any(keyword in text for keyword in HOMEWORK_KEYWORDS):
        return True
    # 直接贴题：含数字/数学符号/函数名且句尾带「怎么做/求解」等
    if re.search(r"[=<>]|\\[a-zA-Z]+|\d+[xX]|f\(|lim|∫|Σ", text) and re.search(
        r"求|计算|解|怎么做|证明|答案|帮我", text
    ):
        return True
    return False


def hard_scope_hit(message: str) -> tuple[str | None, str | None]:
    """v1.3 硬拦截：课程外数学（线代/矩阵/概率等）与不当请求。

    返回 (topic, reason)。这里的命中一律 blocked=true + 统一话术，不进入 gate。
    """
    text = message or ""
    for keyword in HARD_SCOPE_KEYWORDS:
        if keyword in text:
            return keyword, f"「{keyword}」不在高等数学课程范围内。"
    for keyword in UNETHICAL_KEYWORDS:
        if keyword in text:
            return "不当请求", "涉及考试作弊/代写等不当请求。"
    return None, None


def teacher_scope_hit(message: str, config: dict) -> tuple[str | None, str | None]:
    """v1.3 教师配置命中：disabledTopics / effectiveKpIds 范围外 / boundaryRules。

    返回 (topic, reason)；命中后不再硬拦截，而是走「前置自测 -> 通过后循序渐进」。
    """
    text = message or ""
    for topic in config.get("disabledTopics") or []:
        if topic and topic in text:
            return topic, f"该问题涉及教师已禁用的内容「{topic}」，需要先通过前置学习测试。"
    effective = config.get("effectiveKpIds") or []
    if effective:
        matched = [kp for kp in re.findall(r"kp\d{3}", text)]
        if matched and all(kp not in effective for kp in matched):
            return kp_registry_name(matched[0]), "该知识点不在当前教学进度范围内，需要先通过前置学习测试。"
        outside_words = _matched_outside_scope(text, effective)
        if outside_words:
            return outside_words, f"当前教学范围暂不包含「{outside_words}」，需要先通过前置学习测试。"
    boundary = config.get("boundaryRules") or ""
    if boundary:
        for piece in re.split(r"[；;。\n]", boundary):
            piece = piece.strip()
            if len(piece) >= 4 and piece in text:
                return piece, f"该问题触碰教师设定的边界规则：{piece}"
    return None, None


def kp_registry_name(kp_id: str) -> str:
    """知识点编号转名称（迟到导入避免循环依赖）。"""
    from .kp import registry as kp_registry

    return kp_registry.name(kp_id, kp_id)


def _scope_reason(message: str, config: dict) -> str | None:
    """旧版合并判定：硬拦截优先，其次教师配置（供 check_scope 兼容旧调用）。"""
    _topic, hard_reason = hard_scope_hit(message)
    if hard_reason:
        return hard_reason
    _topic, teacher_reason = teacher_scope_hit(message, config)
    return teacher_reason


def _matched_outside_scope(text: str, effective: list[str]) -> str | None:
    """若文本只命中范围外的知识点（如教师只开放极限，却问级数），返回该知识点名称。"""
    from .kp import registry as kp_registry

    matched = kp_registry.match(text, 4)
    if not matched:
        return None
    inside = [kp for kp in matched if kp in effective]
    if inside:
        return None
    outside = [kp for kp in matched if kp not in effective]
    if outside:
        return kp_registry.name(outside[0], outside[0])
    return None


def check_scope(message: str, config: dict) -> tuple[bool, str | None]:
    """返回 (blocked, blockReason)。命中即整体拦截，统一话术。"""
    reason = _scope_reason(message, config)
    if reason:
        return True, reason
    return False, None


def soft_scope_topic(message: str) -> str | None:
    """软范围话题分类：英语/政治/编程/生活，命中返回话题名，否则 None。"""
    text = message or ""
    for topic, keywords in SOFT_TOPICS:
        for keyword in keywords:
            if keyword in text:
                return topic
    return None


def check_soft_scope(message: str) -> tuple[bool, str | None]:
    """软范围判定（不拦截）：返回 (是否软范围, 固定范围提醒)。"""
    if soft_scope_topic(message) is None:
        return False, None
    return True, SOFT_SCOPE_WARNING


def chapters_in_text(text: str) -> list[str]:
    hits = []
    for chapter, keywords in CHAPTER_ALIASES:
        if any(keyword in (text or "") for keyword in keywords):
            hits.append(chapter)
    return hits


def clean_excerpt(text: str, limit: int = 160) -> str:
    """清洗片段：去掉例题/解析/答案及之后内容，避免引导式答疑泄露答案。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    match = re.search(r"例题|解题思路|解题过程|答案|解析|提示\d*[：:]|参考解答", text)
    if match and match.start() > 0:
        text = text[: match.start()].strip()
    text = re.sub(r"^(kp\d{3}[^。]{0,30}?（难度\d）\s*)?", "", text)
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def guess_difficulty_from_layer(layer: str) -> tuple[int, int]:
    """A/B/C 分层对应的默认难度区间与上限。"""
    layer = (layer or "A").strip().upper()
    if layer == "C":
        return 3, 4
    if layer == "B":
        return 2, 3
    return 1, 2


def strip_question_answers(payload: dict) -> dict:
    """返回不含 answerKey/analysis 的题目（练习/计划接口使用）。"""
    result = dict(payload)
    result.pop("answerKey", None)
    result.pop("analysis", None)
    return result
