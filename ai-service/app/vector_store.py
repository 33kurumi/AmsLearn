"""向量检索层：LangChain InMemoryVectorStore + 本地哈希 Embeddings + 引用（citation）。

设计要点（见 task-5）：
- 不依赖外部 embedding API：自定义 LocalHashingEmbeddings，字符 1~3-gram 有符号哈希，
  离线、确定性、可整体替换为远程 embedding（只需改 VectorIndex 的 embeddings 属性）；
- 用 langchain-text-splitters 的 RecursiveCharacterTextSplitter 把知识库分块再切成
  ~420 字的检索单元，兼顾召回精度与引用上下文；
- 向量库用 langchain_core.vectorstores.InMemoryVectorStore（余弦相似度），
  叠加 KB 优先级与知识点命中加权，阈值按 embedding 方案取（本地 0.15 / 语义 0.40）；
- 每个命中片段都带 chapter / section / citation，例如
  《高等数学教材讲义》第3章·第3节 洛必达法则；
- 索引清单持久化到 data/vector_index.json（含维度、数量、chunk->章节映射），
  供验收取证；向量本身在启动时按同一算法确定性重建。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import KB_PRIORITY, settings
from .embeddings import EmbeddingInfo, resolve_embeddings
from .knowledge import Chunk
from .kp import registry as kp_registry
from .query import plan_query

logger = logging.getLogger("ams.ai.vector")

VECTOR_DIM = 1024
VECTOR_STORE_NAME = "InMemoryVectorStore"
EMBEDDING_NAME = "LocalHashingEmbeddings(char-ngram-1~3, blake2b-signed, dim=1024)"
ALLOWED_KBS = ("KB1", "KB2", "KB3", "KB4")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[a-zA-Z]+|\d+(?:\.\d+)?")
_KP_RE = re.compile(r"kp\d{3}")

_STOP_CHARS = set("的了是在和与及或就都也还很非常这那有对为以于其之而但如把被从到地得着个我你他她它们吗呢吧啊么什怎")
_STOP_BIGRAMS = {
    "我们", "你们", "他们", "什么", "怎么", "如何", "可以", "这个", "那个", "一个",
    "没有", "就是", "还是", "但是", "因为", "所以", "如果", "然后", "现在", "老师",
    "同学", "问题", "请问", "一下", "帮我", "告诉", "知道", "需要", "应该", "是不",
    "不是", "有没", "有什", "为什", "怎样", "这样", "那样", "一些", "这些", "那些",
}


# --------------------------------------------------------------------------
# 分词与本地 embedding
# --------------------------------------------------------------------------
def _add(weights: dict[str, float], token: str, weight: float) -> None:
    if not token:
        return
    weights[token] = weights.get(token, 0.0) + weight


def token_weights(text: str) -> dict[str, float]:
    """中文 1~3-gram + 英文/数字词，返回 {token: 权重}。

    单字权重低（召回用），bigram 权重 1.0，trigram 权重 1.5（更具体、噪声更小）；
    停用字/停用二元组直接丢弃，避免「的、是、怎么」这类虚词主导相似度。
    """
    weights: dict[str, float] = {}
    for run in _CJK_RE.findall((text or "").lower()):
        if len(run) == 1:
            if run not in _STOP_CHARS:
                _add(weights, run, 0.5)
            continue
        for char in run:
            if char not in _STOP_CHARS:
                _add(weights, char, 0.2)
        for idx in range(len(run) - 1):
            bigram = run[idx:idx + 2]
            if bigram in _STOP_BIGRAMS:
                continue
            if bigram[0] in _STOP_CHARS and bigram[1] in _STOP_CHARS:
                continue
            _add(weights, bigram, 1.0)
        for idx in range(len(run) - 2):
            trigram = run[idx:idx + 3]
            if trigram[1] in _STOP_CHARS:
                continue
            _add(weights, trigram, 1.5)
    for word in _ASCII_RE.findall((text or "").lower()):
        _add(weights, "w:" + word, 1.2)
    return weights


def _hash(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dim, (1.0 if (value >> 63) & 1 else -1.0)


class LocalHashingEmbeddings(Embeddings):
    """离线确定性哈希 embedding：同样文本永远得到同样向量。"""

    def __init__(self, dim: int = VECTOR_DIM) -> None:
        self.dim = dim

    @property
    def name(self) -> str:
        return EMBEDDING_NAME

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = np.zeros(self.dim, dtype=np.float32)
        for token, weight in token_weights(text).items():
            index, sign = _hash(token, self.dim)
            vector[index] += sign * weight
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()


# --------------------------------------------------------------------------
# 知识点 -> 章/节/citation
# --------------------------------------------------------------------------
class _KpLocator:
    """从 knowledge_points.json 推导章号与节号（chapter 字段只有章名，无编号）。"""

    def __init__(self) -> None:
        self.chapter_no: dict[str, int] = {}
        self.section_no: dict[str, int] = {}
        self._section_counter: dict[str, int] = {}
        for kp in kp_registry.all():
            chapter = kp.chapter or "高等数学"
            if chapter not in self.chapter_no:
                self.chapter_no[chapter] = len(self.chapter_no) + 1
                self._section_counter[chapter] = 0
            self._section_counter[chapter] += 1
            self.section_no[kp.kp_id] = self._section_counter[chapter]

    def locate(self, kp_id: str | None, title: str) -> dict:
        kp_id = (kp_id or "").strip()
        kp = kp_registry.get(kp_id) if kp_id else None
        if not kp:
            return {
                "kpName": "",
                "chapter": "",
                "section": "",
                "citation": f"《{title}》" if title else "",
            }
        chapter_no = self.chapter_no.get(kp.chapter, 0)
        section_no = self.section_no.get(kp.kp_id, 0)
        chapter_label = f"第{chapter_no}章 {kp.chapter}" if chapter_no else kp.chapter
        section_label = f"第{section_no}节 {kp.kp_name}" if section_no else kp.kp_name
        return {
            "kpName": kp.kp_name,
            "chapter": chapter_label,
            "section": section_label,
            "citation": f"《{title}》第{chapter_no}章·第{section_no}节 {kp.kp_name}",
        }


_locator = _KpLocator()


def describe_source(kp_id: str | None, title: str) -> dict:
    """返回某个知识点在指定文档中的 chapter / section / citation 描述。"""
    return _locator.locate(kp_id, title)


def _kp_in_text(text: str) -> str | None:
    """取文本中第一个合法知识点编号（用于单元级引用定位）。"""
    match = _KP_RE.search(text or "")
    if match and kp_registry.get(match.group(0)):
        return match.group(0)
    return None


def _kp_near(text: str, query_terms: list[str]) -> str | None:
    """取查询词命中位置之前最近的知识点编号，让引用与展示片段对齐。

    一个检索单元最多 420 字，可能横跨两个知识点；索引时记录的是单元首知识点，
    展示摘录却围绕查询词截取，二者错位会造成「片段讲洛必达、引用却写阶段测验」。
    """
    flat = text or ""
    lowered = flat.lower()
    position: int | None = None
    for term in query_terms:
        clean = term.replace("w:", "")
        if len(clean) < 2:
            continue
        found = lowered.find(clean)
        if found >= 0:
            position = found if position is None else min(position, found)
    if position is None:
        return None
    best: str | None = None
    for match in _KP_RE.finditer(flat):
        if match.start() <= position + 20 and kp_registry.get(match.group(0)):
            best = match.group(0)
    return best


def _kp_of(chunk: Chunk) -> str | None:
    if chunk.kp_id and kp_registry.get(chunk.kp_id):
        return chunk.kp_id
    match = _KP_RE.search(chunk.text)
    if match and kp_registry.get(match.group(0)):
        return match.group(0)
    heading = chunk.heading or chunk.text[:120]
    matched = kp_registry.match(heading, 1)
    return matched[0] if matched else None


# --------------------------------------------------------------------------
# 检索结果
# --------------------------------------------------------------------------
@dataclass
class VectorSearchResult:
    items: list[dict]
    enough: bool
    top_score: float
    kp_ids: list[str]


_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=420,
    chunk_overlap=60,
    keep_separator=True,
    separators=["\n\n", "\n", "。", "；", "！", "？", "，", " "],
)


def _excerpt(text: str, query_terms: list[str], limit: int = 180) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    if not flat:
        return ""
    start = 0
    lowered = flat.lower()
    for term in query_terms:
        term = term.replace("w:", "")
        if len(term) < 2:
            continue
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


_KP_LINE_RE = re.compile(r"(?m)^\s*(kp\d{3})(?=[\s　])", re.I)


def _kp_blocks(text: str) -> list[tuple[str, str]]:
    """按行首 kpNNN 切分正文，让每个检索单元尽量只覆盖一个知识点（citation 才准确）。"""
    text = text or ""
    matches = list(_KP_LINE_RE.finditer(text))
    if not matches:
        return [("", text)]
    blocks: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        blocks.append(("", text[: matches[0].start()]))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1).lower(), text[start:end]))
    return blocks


_INTERNAL_KP_RE = re.compile(r"kp\d{3}", re.I)


def _clean_excerpt(text: str) -> str:
    """摘录里不暴露内部编号（kpNNN），统一换成知识点名称（v1.2 契约 §3.3）。"""
    def _replace(match: re.Match) -> str:
        kp_id = match.group(0).lower()
        name = kp_registry.name(kp_id)
        return name or "本知识点"

    cleaned = _INTERNAL_KP_RE.sub(_replace, text or "")
    return cleaned.replace("片段", "资料").strip()


class VectorIndex:
    """知识库向量索引：构建、检索、状态持久化。"""

    def __init__(self, embeddings: Embeddings | None = None) -> None:
        if embeddings is None:
            # v1.2：按 EMBEDDING_PROVIDER 选择 local/openai，失败自动回退 local
            self.embeddings, info = resolve_embeddings()
        else:
            self.embeddings = embeddings
            info = EmbeddingInfo()
        self.embedding_info = info
        self.vector_dim = info.dim
        self._store = InMemoryVectorStore(self.embeddings)
        self._built = False
        self.vector_count = 0
        self.chunk_count = 0
        self.last_build_ms = 0
        # 混合检索用的词表缓存：vectorId -> 该检索单元的 token 集合
        self._doc_tokens: dict[str, set[str]] = {}
        self._documents: list[Document] = []

    # ---- 构建 ----
    def rebuild(self, chunks: Iterable[Chunk]) -> dict:
        start = time.perf_counter()
        chunk_list = list(chunks)
        documents: list[Document] = []
        for chunk in chunk_list:
            chunk_kp = _kp_of(chunk)
            # v1.2：先按行首 kpNNN 对齐知识点，再按长度二次切分，避免引用落到相邻章节
            units: list[tuple[str, str]] = []
            for block_kp, block_text in _kp_blocks(chunk.text):
                parts = [part.strip() for part in _SPLITTER.split_text(block_text) if part.strip()]
                for part in parts:
                    units.append((block_kp or _kp_in_text(part), part))
            if not units:
                units = [(chunk_kp, chunk.text.strip())]
            for unit_index, (unit_kp, part) in enumerate(units):
                # 引用按「检索单元」定位知识点：单元已按 kp 对齐，缺失时退回单元内首个 kp
                kp_id = unit_kp or _kp_in_text(part) or chunk_kp
                located = describe_source(kp_id, chunk.title)
                documents.append(
                    Document(
                        id=f"{chunk.chunk_id}-u{unit_index:02d}",
                        page_content=part,
                        metadata={
                            "chunkId": chunk.chunk_id,
                            "unitIndex": unit_index,
                            "unitCount": len(units),
                            "documentId": chunk.document_id,
                            "kb": chunk.kb,
                            "title": chunk.title,
                            "scope": chunk.scope,
                            "classId": chunk.class_id,
                            "heading": chunk.heading,
                            "kpId": kp_id or "",
                            "kpName": located["kpName"],
                            "chapter": located["chapter"],
                            "section": located["section"],
                            "citation": located["citation"],
                        },
                    )
                )
        store = InMemoryVectorStore(self.embeddings)
        if documents:
            store.add_documents(documents)
        self._store = store
        self._documents = documents
        self._doc_tokens = {
            document.id: set(token_weights(document.page_content))
            for document in documents
        }
        self._built = True
        self.vector_count = len(documents)
        self.chunk_count = len(chunk_list)
        self.last_build_ms = int((time.perf_counter() - start) * 1000)
        self._persist(documents)
        logger.info(
            "向量索引重建完成：分块=%s 检索单元=%s 维度=%s embedding=%s 耗时=%sms",
            self.chunk_count,
            self.vector_count,
            self.vector_dim,
            self.embedding_info.provider,
            self.last_build_ms,
        )
        return {
            "vectorCount": self.vector_count,
            "chunkCount": self.chunk_count,
            "vectorDim": self.vector_dim,
            "durationMs": self.last_build_ms,
        }

    # ---- 检索 ----
    def info(self) -> dict:
        return {
            "vectorStore": VECTOR_STORE_NAME,
            "embedding": self.embedding_info.name,
            "embeddingProvider": self.embedding_info.provider,
            "embeddingModel": self.embedding_info.model,
            "embeddingDim": self.vector_dim,
            "vectorDim": self.vector_dim,
            "vectorCount": self.vector_count,
        }

    def size(self) -> int:
        return self.vector_count

    def default_min_score(self) -> float:
        """当前实际生效 embedding 方案对应的「命中」阈值（本地 0.15 / 语义 0.40）。"""
        return settings.effective_min_score(self.embedding_info.provider)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        kb_scope: Iterable[str] | None = None,
        class_id: str | None = None,
    ) -> VectorSearchResult:
        query = (query or "").strip()
        top_k = int(top_k or settings.top_k)
        min_score = self.default_min_score() if min_score is None else float(min_score)
        scope = {str(kb).upper() for kb in kb_scope} if kb_scope else {"KB1", "KB2", "KB3"}
        allowed = scope & set(ALLOWED_KBS)
        if not allowed:
            allowed = {"KB2"}
        # v1.2：先做查询归一化 + 规则同义扩展，数学符号与隐含考点才能进入检索
        plan = plan_query(query)
        if not query or not self._built or self.vector_count == 0:
            return VectorSearchResult(
                items=[], enough=False, top_score=0.0, kp_ids=list(plan.kp_ids[:3])
            )

        def _keep(document: Document) -> bool:
            meta = document.metadata
            if meta.get("kb") not in allowed:
                return False
            if meta.get("scope") == "CLASS" and meta.get("classId") != class_id:
                return False
            return True

        retrieval_text = plan.embedding_text or query
        vector_scores: dict[str, float] = {}
        try:
            candidates = self._store.similarity_search_with_score(
                retrieval_text, k=max(top_k * 6, 48), filter=_keep
            )
            for document, similarity in candidates:
                vector_scores[document.id] = max(0.0, float(similarity))
        except Exception as exc:  # pragma: no cover - 防御：向量库异常降级为纯词法检索
            logger.warning("向量检索失败，退化为词法检索：%s: %s", type(exc).__name__, exc)

        # 主知识点只来自原问题（不含扩展词），扩展词命中只给较低加分，避免“不定积分”抢走“分部积分法”
        primary_kps = set(kp_registry.match(plan.normalized or query, 4))
        if not primary_kps:
            primary_kps = set(plan.kp_ids[:1])
        query_kps = set(plan.kp_ids) | primary_kps
        query_weights = token_weights(plan.normalized or query)
        for term, weight in (plan.weighted_expansions or {}).items():
            for token, base in token_weights(term).items():
                query_weights[token] = max(query_weights.get(token, 0.0), weight * base)
        primary_names = [name for name in (kp_registry.name(kp) for kp in primary_kps) if name]
        total_weight = sum(query_weights.values()) or 1.0
        # 词法命中按「查询 token 权重和 / 查询总权重」归一，避免长文档天然占优
        scored: list[tuple[float, Document]] = []
        for document in self._documents:
            if not _keep(document):
                continue
            cosine = vector_scores.get(document.id, 0.0)
            tokens = self._doc_tokens.get(document.id) or set()
            lexical = 0.0
            if tokens:
                lexical = (
                    sum(weight for token, weight in query_weights.items() if token in tokens)
                    / total_weight
                )
            if cosine <= 0 and lexical <= 0:
                continue
            meta = document.metadata
            score = (0.55 * cosine + 0.45 * lexical) * KB_PRIORITY.get(meta.get("kb", ""), 0.9)
            kp_id = meta.get("kpId") or ""
            if kp_id and kp_id in primary_kps:
                score += 0.20
            elif kp_id and kp_id in query_kps:
                score += 0.08
            elif meta.get("kpName") and meta["kpName"] in document.page_content:
                score += 0.06
            if primary_names and any(name in document.page_content for name in primary_names):
                score += 0.12
            heading = (meta.get("heading") or "").lower()
            for term in list(query_weights.keys())[:12]:
                clean = term.replace("w:", "")
                if len(clean) >= 2 and clean in heading:
                    score += 0.04
                    break
            if score > 0:
                scored.append((min(score, 0.99), document))

        # 同一分块只保留得分最高的检索单元：sources 数量与实际入库片段一一对应
        best_by_chunk: dict[str, tuple[float, Document]] = {}
        for score, document in scored:
            chunk_id = document.metadata.get("chunkId", "")
            current = best_by_chunk.get(chunk_id)
            if current is None or score > current[0]:
                best_by_chunk[chunk_id] = (score, document)
        ranked = sorted(
            best_by_chunk.values(),
            key=lambda item: (-item[0], item[1].metadata.get("chunkId", "")),
        )
        top_score = ranked[0][0] if ranked else 0.0
        if top_score < min_score:
            # 低于阈值判定为「知识库无相关内容」，不向前端展示无关片段
            return VectorSearchResult(
                items=[], enough=False, top_score=round(top_score, 4), kp_ids=sorted(query_kps)[:6]
            )

        items: list[dict] = []
        for score, document in ranked[: max(0, top_k)]:
            meta = document.metadata
            excerpt = _clean_excerpt(_excerpt(document.page_content, list(query_weights.keys())))
            # 展示摘录围绕查询词截取，引用也要取摘录位置所在的知识点
            kp_id = _kp_near(document.page_content, list(query_weights.keys())) or meta.get("kpId") or ""
            located = describe_source(kp_id, meta.get("title", ""))
            items.append(
                {
                    "documentId": meta.get("documentId", ""),
                    "kb": meta.get("kb", ""),
                    "title": meta.get("title", ""),
                    "excerpt": excerpt,
                    "score": round(score, 4),
                    "kpId": kp_id or None,
                    "chunkId": meta.get("chunkId", ""),
                    "chapter": located.get("chapter") or None,
                    "section": located.get("section") or None,
                    "citation": located.get("citation", ""),
                }
            )

        kp_ids: list[str] = []
        for item in items:
            kp_id = item.get("kpId")
            if kp_id and kp_id not in kp_ids:
                kp_ids.append(kp_id)
        for kp_id in query_kps:
            if kp_id not in kp_ids:
                kp_ids.append(kp_id)
        return VectorSearchResult(items=items, enough=True, top_score=round(top_score, 4), kp_ids=kp_ids[:6])

    # ---- 持久化（索引清单，供验收取证）----
    def _persist(self, documents: list[Document]) -> None:
        path = settings.data_dir / "vector_index.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "vectorStore": VECTOR_STORE_NAME,
                "embedding": EMBEDDING_NAME,
                "vectorDim": VECTOR_DIM,
                "vectorCount": len(documents),
                "chunkCount": self.chunk_count,
                "durationMs": self.last_build_ms,
                "documents": [
                    {
                        "vectorId": document.id,
                        "chunkId": document.metadata.get("chunkId", ""),
                        "documentId": document.metadata.get("documentId", ""),
                        "kb": document.metadata.get("kb", ""),
                        "kpId": document.metadata.get("kpId", ""),
                        "chapter": document.metadata.get("chapter", ""),
                        "section": document.metadata.get("section", ""),
                    }
                    for document in documents
                ],
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:  # pragma: no cover - 持久化失败不影响检索
            logger.warning("向量索引清单写入失败：%s: %s", type(exc).__name__, exc)


vector_index = VectorIndex()


def search(
    query: str,
    top_k: int | None = None,
    min_score: float | None = None,
    kb_scope: Iterable[str] | None = None,
    class_id: str | None = None,
) -> VectorSearchResult:
    """便捷入口：对全局 vector_index 检索。"""
    return vector_index.search(
        query=query,
        top_k=top_k,
        min_score=min_score,
        kb_scope=kb_scope,
        class_id=class_id,
    )
