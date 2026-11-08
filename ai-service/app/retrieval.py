"""中文轻量检索：字符 bigram + TF-IDF 余弦 + 术语/标题加权 + KB 优先级。

不依赖 jieba/langchain（任务书 B 要求）。中文按连续汉字段取字符 bigram，
英文/数字按词切分；对知识点命中（kpId、术语别名）与标题命中额外加权；
最终按 KB2 教材 > KB1 大纲 > KB3 题库 > KB4 教师资料 的优先级微调。
默认 Top8、minScore=0.15，低于阈值判定为「知识库无相关内容」（enough=false）。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from .config import KB_PRIORITY, settings
from .knowledge import Chunk
from .kp import registry as kp_registry

CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
ASCII_TOKEN = re.compile(r"[a-zA-Z]+|\d+(?:\.\d+)?")
STOP_CHARS = set("的了是在和与及或就都也还很非常这那有对为以于其之而但如把被从到地得着")
STOP_TERMS = {
    "我们", "你们", "他们", "什么", "怎么", "如何", "可以", "这个", "那个", "一个",
    "没有", "就是", "还是", "但是", "因为", "所以", "如果", "然后", "现在", "老师",
    "同学", "问题", "请问", "一下", "帮我", "告诉", "知道", "需要", "应该",
}


def tokenize(text: str) -> list[str]:
    """中文 bigram（单字保留）+ 英文/数字小写词。"""
    text = (text or "").lower()
    tokens: list[str] = []
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        for idx in range(len(run) - 1):
            bigram = run[idx:idx + 2]
            if bigram in STOP_TERMS:
                continue
            if bigram[0] in STOP_CHARS and bigram[1] in STOP_CHARS:
                continue
            tokens.append(bigram)
    for word in ASCII_TOKEN.findall(text):
        tokens.append(word)
    return tokens


def _excerpt(text: str, query_terms: list[str], limit: int = 180) -> str:
    """截取片段：优先围绕首个命中词，控制长度。"""
    flat = re.sub(r"\s+", " ", text).strip()
    start = 0
    lowered = flat.lower()
    for term in query_terms:
        pos = lowered.find(term)
        if pos > 0:
            start = max(0, pos - 40)
            break
    piece = flat[start:start + limit]
    if start > 0:
        piece = "…" + piece
    if start + limit < len(flat):
        piece = piece + "…"
    return piece


@dataclass
class RetrievalResult:
    items: list[dict]
    enough: bool
    top_score: float
    kp_ids: list[str]


class Retriever:
    def __init__(self, chunks: Iterable[Chunk] | None = None) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: list[dict[str, float]] = []
        self._norms: list[float] = []
        self._idf: dict[str, float] = {}
        self._built = False
        if chunks is not None:
            self.build(list(chunks))

    # ---- 索引构建 ----
    def build(self, chunks: Iterable[Chunk]) -> None:
        self._chunks = list(chunks)
        self._vectors = []
        self._norms = []
        self._idf = {}
        self._built = False
        if not self._chunks:
            return
        docs_tokens = [tokenize(chunk.text) for chunk in self._chunks]
        total = len(docs_tokens)
        df: dict[str, int] = {}
        for tokens in docs_tokens:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        # 文档频率过高的虚词不作为有效检索词
        for term, count in df.items():
            self._idf[term] = math.log((total + 1) / (count + 0.5)) + 0.5
        for chunk, tokens in zip(self._chunks, docs_tokens):
            tf: dict[str, int] = {}
            for term in tokens:
                tf[term] = tf.get(term, 0) + 1
            vector: dict[str, float] = {}
            for term, count in tf.items():
                if term not in self._idf:
                    continue
                weight = (1 + math.log(count)) * self._idf[term]
                if weight > 0:
                    vector[term] = weight
            heading_tokens = set(tokenize(chunk.heading))
            for term in heading_tokens:
                if term in vector:
                    vector[term] *= 1.15
            norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
            self._vectors.append(vector)
            self._norms.append(norm)
        self._built = True

    def rebuild_from(self, chunks: Iterable[Chunk]) -> None:
        self.build(chunks)

    def size(self) -> int:
        return len(self._chunks)

    def chunks(self) -> list[Chunk]:
        """返回当前索引中的全部块（mock 出题/计划需要读取 KB2/KB3 原文）。"""
        return list(self._chunks)

    # ---- 检索 ----
    def search(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        kb_scope: Iterable[str] | None = None,
        class_id: str | None = None,
        include_disabled_scopes: bool = False,
    ) -> RetrievalResult:
        query = (query or "").strip()
        top_k = top_k or settings.top_k
        min_score = settings.min_score if min_score is None else min_score
        scope = {str(kb).upper() for kb in kb_scope} if kb_scope else {"KB1", "KB2", "KB3"}
        if not query or not self._built:
            return RetrievalResult(items=[], enough=False, top_score=0.0, kp_ids=kp_registry.match(query, 3) if query else [])
        terms = tokenize(query)
        counts: dict[str, int] = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
        query_vector: dict[str, float] = {}
        for term, count in counts.items():
            if term in self._idf:
                query_vector[term] = (1 + math.log(count)) * self._idf[term]
        query_norm = math.sqrt(sum(v * v for v in query_vector.values())) or 1.0
        query_kps = set(kp_registry.match(query, 4))
        query_term_list = list(query_vector.keys())

        scored: list[tuple[float, int]] = []
        for idx, chunk in enumerate(self._chunks):
            if chunk.kb not in scope:
                continue
            if chunk.scope == "CLASS" and chunk.class_id != class_id:
                continue
            vector = self._vectors[idx]
            common = query_vector.keys() & vector.keys()
            if not common:
                continue
            dot = sum(query_vector[t] * vector[t] for t in common)
            cosine = dot / (query_norm * self._norms[idx])
            score = cosine * KB_PRIORITY.get(chunk.kb, 0.9)
            if chunk.kp_id and chunk.kp_id in query_kps:
                score += 0.16
            else:
                for kp_id in query_kps:
                    kp = kp_registry.get(kp_id)
                    if kp and kp.kp_name and kp.kp_name in chunk.text:
                        score += 0.06
                        break
            # 命中点名称中的词（如「导数」之于「导数的概念与几何意义」）额外加分
            kp = kp_registry.get(chunk.kp_id) if chunk.kp_id else None
            if kp and kp.kp_name:
                for term in query_term_list[:10]:
                    if len(term) >= 2 and term in kp.kp_name:
                        score += 0.12
                        break
            # 章节/标题命中轻加分
            for term in query_term_list[:8]:
                if term in chunk.heading.lower():
                    score += 0.03
                    break
            if score > 0:
                scored.append((score, idx))

        scored.sort(key=lambda item: (-item[0], -KB_PRIORITY.get(self._chunks[item[1]].kb, 0.0)))
        selected = scored[: max(0, top_k)]
        items: list[dict] = []
        for score, idx in selected:
            chunk = self._chunks[idx]
            items.append(
                {
                    "documentId": chunk.document_id,
                    "kb": chunk.kb,
                    "title": chunk.title,
                    "excerpt": _excerpt(chunk.text, query_term_list),
                    "score": round(min(score, 0.99), 4),
                    "kpId": chunk.kp_id,
                    "chunkId": chunk.chunk_id,
                }
            )
        top_score = items[0]["score"] if items else 0.0
        enough = bool(items) and top_score >= min_score
        kp_ids: list[str] = []
        for item in items:
            kp_id = item.get("kpId")
            if kp_id and kp_id not in kp_ids:
                kp_ids.append(kp_id)
        for kp_id in query_kps:
            if kp_id not in kp_ids:
                kp_ids.append(kp_id)
        return RetrievalResult(items=items, enough=enough, top_score=round(top_score, 4), kp_ids=kp_ids[:6])


retriever = Retriever()
