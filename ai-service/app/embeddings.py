"""可插拔 embedding provider（v1.2 契约 §1 B 轨）。

背景事实：DeepSeek 没有 embeddings 接口（2026-11-07 实测 POST /embeddings -> 404，
/models 只有 deepseek-flash、deepseek-v4-pro），所以「Embeddings 直接接 DeepSeek」不可行。

双轨方案：
- local（默认）：LocalHashingEmbeddings，字符 1~3-gram 有符号哈希，离线、确定性、零依赖；
- openai：任何 OpenAI 兼容的 /embeddings 服务（硅基流动 BGE-M3、OpenAI、自建 vLLM 等），
  由 EMBEDDING_BASE_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL 指定；
  缺 key、调用失败或返回维度异常时**自动回退 local**，保证服务永远起得来。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from langchain_core.embeddings import Embeddings

from .config import settings

logger = logging.getLogger("ams.ai.embeddings")

LOCAL_DIM = 1024


class EmbeddingError(RuntimeError):
    """远程 embedding 调用失败（用于触发 local 回退）。"""


@dataclass
class EmbeddingInfo:
    """当前生效的 embedding 方案（Health 接口直接暴露这些字段）。"""

    provider: str = "local"
    model: str = "LocalHashingEmbeddings"
    dim: int = LOCAL_DIM
    name: str = "LocalHashingEmbeddings(char-ngram-1~3, blake2b-signed, dim=1024)"

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "dim": self.dim,
            "name": self.name,
        }


def _normalize_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/embeddings"):
        return base
    return base + "/embeddings"


class OpenAICompatibleEmbeddings(Embeddings):
    """OpenAI 兼容 /embeddings 客户端（只做最小实现，失败抛 EmbeddingError）。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0) -> None:
        self.url = _normalize_base(base_url)
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = float(timeout)

    def _request(self, texts: list[str]) -> list[list[float]]:
        if not self.url or not self.api_key or not self.model:
            raise EmbeddingError("embedding provider=openai 但缺少 BASE_URL/API_KEY/MODEL")
        payload = {"model": self.model, "input": texts, "encoding_format": "float"}
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10.0)) as client:
                response = client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except Exception as exc:  # noqa: BLE001 - 统一转成可回退的错误
            raise EmbeddingError(f"embedding 调用失败：{type(exc).__name__}: {exc}") from exc
        rows = body.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise EmbeddingError("embedding 返回结构异常（data 数量不匹配）")
        out: list[list[float]] = []
        for row in rows:
            vector = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError("embedding 返回向量为空")
            out.append([float(value) for value in vector])
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch = 32
        for start in range(0, len(texts), batch):
            vectors.extend(self._request(texts[start : start + batch]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._request([text])[0]


def local_info() -> EmbeddingInfo:
    from .vector_store import EMBEDDING_NAME, LocalHashingEmbeddings  # 避免循环导入

    return EmbeddingInfo(
        provider="local",
        model="LocalHashingEmbeddings",
        dim=LOCAL_DIM,
        name=EMBEDDING_NAME,
    )


def resolve_embeddings(
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    probe: bool = True,
) -> tuple[Embeddings, EmbeddingInfo]:
    """返回 (embeddings, info)；openai 配置不完整或探测失败时回退 local。

    probe=True 时会用一句「高等数学」真实调用一次，确认可用并拿到真实维度；
    服务启动、索引重建都走这里，因此 Health 的 embedding_* 永远是实际生效值。
    """
    from .vector_store import LocalHashingEmbeddings  # 避免循环导入

    requested = (provider or settings.embedding_provider or "local").strip().lower()
    if requested != "openai":
        return LocalHashingEmbeddings(LOCAL_DIM), local_info()

    base = (base_url if base_url is not None else settings.embedding_base_url) or ""
    key = (api_key if api_key is not None else settings.embedding_api_key) or ""
    name = (model if model is not None else settings.embedding_model) or ""
    if not (base and key and name):
        logger.warning(
            "EMBEDDING_PROVIDER=openai 但缺少 EMBEDDING_BASE_URL/API_KEY/MODEL，已回退本地哈希 embedding"
        )
        return LocalHashingEmbeddings(LOCAL_DIM), local_info()

    candidate = OpenAICompatibleEmbeddings(
        base_url=base,
        api_key=key,
        model=name,
        timeout=float(timeout if timeout is not None else settings.embedding_timeout_seconds),
    )
    if probe:
        try:
            vector = candidate.embed_query("高等数学")
        except EmbeddingError as exc:
            logger.warning("embedding 服务探测失败，已回退本地哈希 embedding：%s", exc)
            return LocalHashingEmbeddings(LOCAL_DIM), local_info()
        dim = len(vector)
        if dim <= 0:
            return LocalHashingEmbeddings(LOCAL_DIM), local_info()
        info = EmbeddingInfo(
            provider="openai",
            model=name,
            dim=dim,
            name=f"OpenAICompatibleEmbeddings({name}, dim={dim})",
        )
        logger.info("embedding provider=openai 已生效 model=%s dim=%s", name, dim)
        return candidate, info

    return candidate, EmbeddingInfo(
        provider="openai",
        model=name,
        dim=LOCAL_DIM,
        name=f"OpenAICompatibleEmbeddings({name})",
    )
