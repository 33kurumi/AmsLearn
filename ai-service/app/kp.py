"""知识点目录（knowledge_points.json，67 个 kp）的加载、查询与文本匹配。

出题、计划、报告、配置抽取都需要 kpId -> kpName/chapter/difficulty 的映射，
因此单独抽成注册表，避免各模块重复读文件。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings


@dataclass(frozen=True)
class KnowledgePoint:
    kp_id: str
    kp_name: str
    chapter: str
    difficulty: int
    hours: int = 2
    objectives: str = ""
    key_points: str = ""


# 常用口语/教材简称 -> kpId。名称匹配已覆盖大部分情况，别名用于处理简称与同义说法。
ALIASES: list[tuple[str, str]] = [
    (r"罗尔|拉格朗日|柯西中值|中值定理", "kp019"),
    (r"洛必达", "kp021"),
    (r"泰勒|麦克劳林", "kp026"),
    (r"等价无穷小|无穷小|无穷大", "kp006"),
    (r"夹逼|单调有界|两个重要极限|重要极限", "kp005"),
    (r"间断点|连续性", "kp007"),
    (r"零点定理|介值定理|最值定理", "kp008"),
    (r"导数定义|导数的几何意义|切线斜率", "kp011"),
    (r"链式|求导公式|求导法则", "kp012"),
    (r"高阶导数|莱布尼茨", "kp013"),
    (r"隐函数|参数方程", "kp014"),
    (r"微分方程", "kp062"),
    (r"分离变量", "kp063"),
    (r"偏导数|偏导", "kp042"),
    (r"二重积分", "kp048"),
    (r"级数|收敛半径|幂级数", "kp055"),
    (r"分部积分|分步积分", "kp031"),
    (r"换元积分|凑微分", "kp029"),
    (r"不定积分|原函数", "kp028"),
    (r"定积分", "kp033"),
    (r"牛顿-莱布尼茨|微积分基本定理", "kp034"),
    (r"单调性|极值", "kp022"),
]


def _clean_phrase(text: str) -> str:
    return re.sub(r"[，。；：、（）()“”\"'·\s]|重点|难点|是|的", "", text)


class KnowledgePointRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings.kp_file
        self._items: dict[str, KnowledgePoint] = {}
        self._order: list[str] = []
        self._phrase_index: list[tuple[str, str]] = []
        self.load()

    def load(self) -> None:
        self._items = {}
        self._order = []
        self._phrase_index = []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        for raw in data:
            kp = KnowledgePoint(
                kp_id=str(raw.get("kpId", "")).strip(),
                kp_name=str(raw.get("kpName", "")).strip(),
                chapter=str(raw.get("chapter", "")).strip(),
                difficulty=int(raw.get("difficulty", 1) or 1),
                hours=int(raw.get("hours", 2) or 2),
                objectives=str(raw.get("objectives", "") or ""),
                key_points=str(raw.get("keyPoints", "") or ""),
            )
            if not kp.kp_id:
                continue
            self._items[kp.kp_id] = kp
            self._order.append(kp.kp_id)
        # 关键词索引：从 keyPoints 的「重点/难点」句中抽取短语，辅助匹配
        for kp in self._items.values():
            for phrase in re.split(r"[；;，,。]", kp.key_points or ""):
                cleaned = _clean_phrase(phrase)
                if 4 <= len(cleaned) <= 12:
                    self._phrase_index.append((cleaned, kp.kp_id))

    # ---- 基础查询 ----
    def all(self) -> list[KnowledgePoint]:
        return [self._items[kp_id] for kp_id in self._order]

    def get(self, kp_id: str) -> KnowledgePoint | None:
        return self._items.get((kp_id or "").strip())

    def name(self, kp_id: str, default: str = "") -> str:
        kp = self.get(kp_id)
        return kp.kp_name if kp else default

    def chapter(self, kp_id: str, default: str = "") -> str:
        kp = self.get(kp_id)
        return kp.chapter if kp else default

    def difficulty(self, kp_id: str, default: int = 2) -> int:
        kp = self.get(kp_id)
        return kp.difficulty if kp else default

    def chapters(self) -> list[str]:
        seen: list[str] = []
        for kp in self.all():
            if kp.chapter and kp.chapter not in seen:
                seen.append(kp.chapter)
        return seen

    def kps_in_chapter(self, chapter: str) -> list[KnowledgePoint]:
        return [kp for kp in self.all() if kp.chapter == chapter]

    def chapter_of_text(self, text: str) -> str:
        """粗判文本涉及的章节：按章节标题关键词命中数取最高。"""
        best, best_hits = "", 0
        for chapter in self.chapters():
            hits = sum(1 for token in re.split(r"[、与及]", chapter) if token and token in text)
            if hits > best_hits:
                best, best_hits = chapter, hits
        return best

    # ---- 文本匹配 ----
    def match(self, text: str, limit: int = 5) -> list[str]:
        """从自然语言中识别知识点，按命中强度返回 kpId 列表。"""
        if not text:
            return []
        text = text.strip()
        scores: dict[str, float] = {}
        pos: dict[str, int] = {}

        for kp_id in re.findall(r"kp\d{3}", text):
            if kp_id in self._items:
                scores[kp_id] = max(scores.get(kp_id, 0.0), 2.0)
                pos.setdefault(kp_id, text.find(kp_id))

        for kp in self.all():
            name = kp.kp_name
            if len(name) >= 3 and name in text:
                scores[kp.kp_id] = max(scores.get(kp.kp_id, 0.0), 1.4)
                pos.setdefault(kp.kp_id, text.find(name))
        for pattern, kp_id in ALIASES:
            if kp_id in self._items and re.search(pattern, text):
                scores[kp_id] = max(scores.get(kp_id, 0.0), 1.0)
                pos.setdefault(kp_id, len(text))
        for phrase, kp_id in self._phrase_index:
            if phrase and phrase in text:
                scores[kp_id] = max(scores.get(kp_id, 0.0), 0.6)
                pos.setdefault(kp_id, text.find(phrase))

        ordered = sorted(scores, key=lambda kid: (-scores[kid], pos.get(kid, 999)))
        return ordered[:limit]

    def names(self, kp_ids: list[str]) -> list[str]:
        out: list[str] = []
        for kp_id in kp_ids:
            name = self.name(kp_id)
            if name and name not in out:
                out.append(name)
        return out

    def __len__(self) -> int:  # pragma: no cover - 调试用
        return len(self._items)


registry = KnowledgePointRegistry()
