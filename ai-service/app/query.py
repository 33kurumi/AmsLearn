"""查询归一化与同义扩展（v1.2 召回增强 A 轨，契约 §1 / §2）。

用户实测问题：「求∫2xe^xdx」在旧版检索里命中「微分方程」，并声称知识库没有分部积分。
原因是本地哈希 embedding 只按字符 n-gram 计分，数学符号（∫、^、dx）被丢弃，
而「分部积分」这个方法名根本没出现在问题里，向量空间无法把它拉近。

本模块做两件确定性的、可离线复现的事：
1. 归一化：全角转半角、数学符号转中文词（∫ -> 积分、∑ -> 级数、∞ -> 无穷 …），
   统一口语/错别字（洛比达/罗必达 -> 洛必达，taylor -> 泰勒）；
2. 规则扩展：按「知识点同义词典 + 题型结构」把隐含考点补成检索词，
   例如 ∫ + x·e^x 结构 -> 分部积分法 / 凑微分 / 不定积分；
   定积分 + 几何意义 -> 定积分的概念与性质 / 曲边梯形面积。

real 模式下 service 还会额外调用 DeepSeek 做一次 query 改写（QUERY_EXPANSION=auto），
失败时直接用本模块的结果，保证 mock/real 行为一致、可测试。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .config import settings
from .kp import registry as kp_registry

# 数学符号 -> 中文词：让「∫」「∑」这类符号在中文检索里也有语义
_SYMBOL_MAP = {
    "∫": " 积分 ",
    "∬": " 二重积分 ",
    "∮": " 曲线积分 ",
    "∑": " 级数 ",
    "√": " 根号 ",
    "∞": " 无穷 ",
    "π": " 圆周率 ",
    "≤": " 小于等于 ",
    "≥": " 大于等于 ",
    "≠": " 不等于 ",
    "→": " 趋于 ",
    "×": " 乘 ",
    "·": " 乘 ",
    "∂": " 偏导 ",
    "θ": " theta ",
    "α": " alpha ",
    "β": " beta ",
}

# 错别字 / 英文口语 -> 规范术语
_SYNONYMS = {
    "洛比达": "洛必达",
    "罗必达": "洛必达",
    "罗比塔": "洛必达",
    "洛必塔": "洛必达",
    "taylor": "泰勒",
    "泰勒展开": "泰勒公式",
    "麦克劳林展开": "麦克劳林公式",
    "求导": "导数",
    "积分中值": "积分中值定理",
    "微分中值": "微分中值定理",
    "定积分几何意义": "定积分的几何意义",
    "分部积": "分部积分",
    "凑微": "凑微分",
}

# 结构判定：被积函数是「幂函数 × 指数/三角/对数/反三角」时，首选分部积分法
_PRODUCT_INTEGRAND_RE = re.compile(
    r"x\s*[\*·]?\s*(?:e\^?\s*x|e\^\s*\(|sin|cos|ln|arctan|arcsin)"
    r"|(?:e\^?\s*x|sin|cos|ln|arctan)\s*[\*·]?\s*x",
    re.I,
)
_INTEGRAL_RE = re.compile(r"积分|∫|\\int", re.I)

# (正则, 扩展词列表, 说明)。规则按顺序命中，全部累加（去重保序）。
_EXPANSIONS: list[tuple[str, list[str]]] = [
    # ---- 积分学 ----
    (r"分部积分", ["分部积分法", "不定积分", "反对幂指三"]),
    (r"凑微分|第一类换元|换元积分", ["第一类换元积分法（凑微分法）", "不定积分", "凑微分"]),
    (r"三角代换|第二类换元|根式代换", ["第二类换元积分法", "不定积分", "三角代换"]),
    (r"不定积分|原函数", ["不定积分", "原函数", "基本积分公式"]),
    (r"定积分|曲边梯形|面积", ["定积分的概念与性质", "定积分", "几何意义"]),
    (r"牛顿|莱布尼茨|微积分基本定理", ["牛顿-莱布尼茨公式", "定积分"]),
    (r"二重积分|重积分", ["二重积分", "累次积分", "极坐标"]),
    (r"反常积分|广义积分", ["反常积分", "收敛性"]),
    # ---- 极限与微分 ----
    (r"洛必达|未定式", ["洛必达法则", "0/0型", "无穷比无穷"]),
    (r"泰勒|麦克劳林", ["泰勒公式", "麦克劳林公式", "高阶无穷小"]),
    (r"中值定理|罗尔|拉格朗日|柯西定理", ["罗尔中值定理与拉格朗日中值定理", "柯西中值定理", "构造辅助函数"]),
    (r"极限|趋于", ["函数的极限与极限运算法则", "极限"]),
    (r"无穷小|无穷大", ["无穷小与无穷大", "等价无穷小"]),
    (r"连续|间断点", ["函数的连续性与间断点"]),
    (r"导数|求导|切线", ["导数与微分", "导数"]),
    (r"极值|单调", ["函数的单调性与极值"]),
    (r"凹凸|拐点", ["曲线的凹凸性与拐点"]),
    (r"渐近线|函数图形", ["函数图形的描绘与渐近线"]),
    (r"最值|优化", ["函数的最值问题"]),
    # ---- 级数与微分方程 ----
    (r"级数|收敛半径|幂级数|傅里叶", ["无穷级数", "收敛半径", "幂级数"]),
    (r"微分方程|通解|特解", ["常微分方程", "一阶微分方程", "二阶常系数"]),
    (r"偏导|全微分|多元函数", ["多元函数微分学", "偏导数", "全微分"]),
]

# 数学符号上下文里「求 ∫…dx」的默认扩展（没有更具体规则时）
_DEFAULT_INTEGRAL_TERMS = ["不定积分", "积分", "基本积分公式"]


def normalize_text(text: str) -> str:
    """全角转半角 + 数学符号转中文 + 错别字归一。"""
    raw = unicodedata.normalize("NFKC", str(text or "")).strip()
    for symbol, word in _SYMBOL_MAP.items():
        raw = raw.replace(symbol, word)
    lowered = raw.lower()
    for wrong, right in _SYNONYMS.items():
        if wrong in lowered:
            lowered = lowered.replace(wrong, right)
    return re.sub(r"\s+", " ", lowered).strip()


@dataclass
class QueryPlan:
    """一次检索的查询计划：原文、归一化文本、送入向量的文本、扩展词、命中知识点。"""

    original: str
    normalized: str
    embedding_text: str
    expansions: list[str] = field(default_factory=list)
    kp_ids: list[str] = field(default_factory=list)
    # 扩展词权重：规则命中组的核心词 1.0，同组补充词 0.4；用于检索时区分主次
    weighted_expansions: dict[str, float] = field(default_factory=dict)

    @property
    def keyword_terms(self) -> list[str]:
        return list(dict.fromkeys(self.expansions))


def expand_weighted(normalized: str) -> list[tuple[str, float]]:
    """按规则补全隐含考点，返回 (词, 权重)：组内第一个词为核心词（权重 1.0），其余 0.4。"""
    if settings.query_expansion == "off":
        return []
    text = normalized or ""
    groups: list[list[str]] = []
    has_integral = bool(_INTEGRAL_RE.search(text))
    # 只有“没有更具体积分方法词”时才套用默认积分扩展，否则“定积分”会被误扩成“不定积分”
    specific_integral = re.search(
        r"定积分|不定积分|二重积分|三重积分|反常积分|广义积分|分部积分|换元|凑微分|原函数|曲边梯形", text
    )
    if has_integral and not specific_integral:
        if _PRODUCT_INTEGRAND_RE.search(text):
            groups.append(["分部积分法", "不定积分", "凑微分", "反对幂指三"])
        else:
            groups.append(list(_DEFAULT_INTEGRAL_TERMS))
    elif _PRODUCT_INTEGRAND_RE.search(text) or re.search(r"分部", text):
        groups.append(["分部积分法", "不定积分", "凑微分", "反对幂指三"])
    for pattern, words in _EXPANSIONS:
        if re.search(pattern, text, re.I):
            groups.append(list(words))
    weighted: dict[str, float] = {}
    for group in groups:
        for index, term in enumerate(group):
            term = term.strip()
            if not term:
                continue
            weight = 1.0 if index == 0 else 0.4
            weighted[term] = max(weighted.get(term, 0.0), weight)
    return list(weighted.items())


def expand_terms(normalized: str) -> list[str]:
    """按规则补全隐含考点，返回去重后的扩展词列表。"""
    return [term for term, _ in expand_weighted(normalized)]


def plan_query(query: str) -> QueryPlan:
    """把用户问题转成检索计划（离线、确定性）。"""
    original = str(query or "").strip()
    normalized = normalize_text(original)
    weighted = expand_weighted(normalized)
    expansions = [term for term, _ in weighted]
    embedding_text = normalized
    if expansions:
        embedding_text = normalized + " " + " ".join(expansions)
    kp_ids = kp_registry.match(embedding_text or normalized, 6)
    return QueryPlan(
        original=original,
        normalized=normalized,
        embedding_text=embedding_text or normalized,
        expansions=expansions,
        kp_ids=kp_ids,
        weighted_expansions=dict(weighted),
    )


def rewrite_fragment(plan: QueryPlan) -> str:
    """给 real 模式 DeepSeek 改写查询用的紧凑提示（只回传词语，不改变原意）。"""
    return (
        '高等数学检索词改写。请只输出 JSON：{"terms": ["概念词1", "概念词2"]}，'
        "把学生问题里的隐含考点补成 2~5 个教材术语（例如 ∫2x·e^x dx -> 分部积分法、不定积分）。\n"
        "学生问题：" + plan.normalized
    )
