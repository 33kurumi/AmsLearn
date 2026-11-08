"""知识库管理：分块、文档注册、上传/启停/删除/重建、状态持久化、启动重建。

- 内置 5 份资料 scope=GLOBAL，不可删除，可启停；
- 教师上传资料 scope=CLASS，按 classId 隔离，落盘 knowledge/uploads/<classId>/；
- 文档元数据持久化到 data/knowledge_state.json，索引在进程内重建（数据量小，重建成本可接受）；
- 分块 600~800 字、重叠约 100 字（任务书 B），按段落/句子边界切分。
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import KB_TITLES, SEED_DOCUMENTS, settings


class KnowledgeError(Exception):
    """知识库操作异常基类。"""


class BuiltinDocumentError(KnowledgeError):
    """内置资料不允许该操作（如删除）。"""


class DocumentNotFoundError(KnowledgeError):
    """文档不存在。"""


class UploadValidationError(KnowledgeError):
    """上传文件不合法。"""


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    kb: str
    title: str
    scope: str
    class_id: str | None
    text: str
    heading: str
    kp_id: str | None
    index: int = 0


# --------------------------------------------------------------------------
# 文本归一化与分块
# --------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    text = (text or "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_sentences(paragraph: str, hard_limit: int) -> list[str]:
    """把超长段落切成句子；单句仍超长则硬切。"""
    parts = re.split(r"(?<=[。！？；!?;])", paragraph)
    parts = [p.strip() for p in parts if p.strip()]
    units: list[str] = []
    for part in parts:
        if len(part) <= hard_limit:
            units.append(part)
        else:
            for start in range(0, len(part), hard_limit):
                units.append(part[start:start + hard_limit])
    return units or [paragraph]


def split_units(text: str, max_chars: int) -> list[str]:
    units: list[str] = []
    for paragraph in _split_paragraphs(text):
        if len(paragraph) <= max_chars:
            units.append(paragraph)
        else:
            units.extend(_split_sentences(paragraph, max_chars // 2))
    return units


def chunk_text(
    text: str,
    min_chars: int | None = None,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """按段落/句子边界做 600~800 字、重叠约 100 字的分块。"""
    min_chars = min_chars or settings.chunk_min_chars
    max_chars = max_chars or settings.chunk_max_chars
    overlap = overlap or settings.chunk_overlap_chars
    units = split_units(normalize_text(text), max_chars)
    chunks: list[str] = []
    i, n = 0, len(units)
    while i < n:
        window: list[str] = []
        length = 0
        j = i
        while j < n:
            unit_len = len(units[j])
            if window and length + unit_len + 2 > max_chars:
                break
            if not window and unit_len > max_chars:
                break
            window.append(units[j])
            length += unit_len + 2
            j += 1
        if not window:  # 单段异常超长时兜底
            window = [units[i][:max_chars]]
            j = i + 1
        chunk = "\n\n".join(window).strip()
        if chunk:
            chunks.append(chunk)
        if j >= n:
            break
        # 重叠：从窗口尾部回收累计不超过 overlap 的完整单元作为下一块开头
        tail: list[str] = []
        tail_len = 0
        for unit in reversed(window):
            if tail and tail_len + len(unit) + 2 > overlap:
                break
            tail.insert(0, unit)
            tail_len += len(unit) + 2
        next_start = j - len(tail)
        if next_start <= i:
            next_start = j
        i = next_start
    return chunks


def _heading_of(text: str) -> str:
    first_line = text.split("\n", 1)[0].strip()
    if not first_line:
        return ""
    return re.sub(r"^#+\s*", "", first_line)[:60]


def _kp_of(text: str) -> str | None:
    match = re.search(r"kp\d{3}", text)
    return match.group(0) if match else None


# --------------------------------------------------------------------------
# 知识库管理
# --------------------------------------------------------------------------
class KnowledgeBase:
    def __init__(self, config=settings) -> None:
        self.config = config
        self._documents: dict[str, dict] = {}
        self._chunks: list[Chunk] = []
        self.last_rebuild_ms = 0
        self._load_state()
        self._ensure_seed_documents()

    # ---- 状态读写 ----
    def _load_state(self) -> None:
        path: Path = self.config.state_file
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        for raw in data.get("documents", []):
            doc_id = str(raw.get("documentId", "")).strip()
            if doc_id:
                self._documents[doc_id] = dict(raw)

    def _save_state(self) -> None:
        path = self.config.state_file
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "documents": list(self._documents.values()),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ---- 内置资料 ----
    def _seed_path(self, seed: dict) -> Path:
        return self.config.knowledge_dir / seed["dir"] / seed["name"]

    def _ensure_seed_documents(self) -> None:
        changed = False
        for seed in SEED_DOCUMENTS:
            doc_id = seed["documentId"]
            if doc_id in self._documents:
                self._documents[doc_id]["builtin"] = True
                self._documents[doc_id].setdefault("title", seed["title"])
                continue
            path = self._seed_path(seed)
            doc = {
                "documentId": doc_id,
                "name": seed["name"],
                "title": seed["title"],
                "kb": seed["kb"],
                "scope": "GLOBAL",
                "classId": None,
                "enabled": True,
                "size": path.stat().st_size if path.exists() else 0,
                "uploadedAt": None,
                "uploadedBy": None,
                "builtin": True,
                "relativePath": str(path.relative_to(self.config.knowledge_dir)).replace("\\", "/"),
                "chunks": 0,
            }
            self._documents[doc_id] = doc
            changed = True
        if changed:
            self._save_state()

    def _doc_path(self, doc: dict) -> Path:
        relative = doc.get("relativePath") or ""
        path = self.config.knowledge_dir / relative
        return path

    def _ordered_documents(self) -> list[dict]:
        seed_order = {seed["documentId"]: idx for idx, seed in enumerate(SEED_DOCUMENTS)}
        docs = list(self._documents.values())
        docs.sort(key=lambda d: (0 if d.get("builtin") else 1, seed_order.get(d["documentId"], 99), d.get("uploadedAt") or "", d["documentId"]))
        return docs

    # ---- 重建索引 ----
    def rebuild(self) -> dict:
        start = time.perf_counter()
        chunks: list[Chunk] = []
        for doc in self._ordered_documents():
            if not doc.get("enabled", True):
                doc["chunks"] = 0
                continue
            path = self._doc_path(doc)
            if not path.exists():
                doc["chunks"] = 0
                continue
            try:
                text = normalize_text(path.read_text(encoding="utf-8"))
            except Exception:
                doc["chunks"] = 0
                continue
            title = doc.get("title") or KB_TITLES.get(doc["kb"], doc["name"])
            parts = chunk_text(text)
            for idx, part in enumerate(parts):
                chunks.append(
                    Chunk(
                        chunk_id=f"c-{doc['documentId']}-{idx:03d}",
                        document_id=doc["documentId"],
                        kb=doc["kb"],
                        title=title,
                        scope=doc.get("scope", "GLOBAL"),
                        class_id=doc.get("classId"),
                        text=part,
                        heading=_heading_of(part),
                        kp_id=_kp_of(part),
                        index=idx,
                    )
                )
            doc["chunks"] = len(parts)
        self._chunks = chunks
        self.last_rebuild_ms = int((time.perf_counter() - start) * 1000)
        self._save_state()
        return {
            "documentCount": len(self._documents),
            "chunkCount": len(self._chunks),
            "durationMs": self.last_rebuild_ms,
        }

    # ---- 查询 ----
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def documents(self, class_id: str | None = None, include_all_uploads: bool = True) -> list[dict]:
        result = []
        for doc in self._ordered_documents():
            if doc.get("scope") == "GLOBAL":
                result.append(doc)
            elif class_id is not None and doc.get("classId") == class_id:
                result.append(doc)
            elif class_id is None and include_all_uploads:
                result.append(doc)
        return result

    def document_vo(self, doc: dict) -> dict:
        return {
            "documentId": doc["documentId"],
            "name": doc.get("name", ""),
            "kb": doc.get("kb", "KB4"),
            "scope": doc.get("scope", "GLOBAL"),
            "classId": doc.get("classId"),
            "chunks": int(doc.get("chunks", 0)),
            "enabled": bool(doc.get("enabled", True)),
            "size": int(doc.get("size", 0)),
            "uploadedAt": doc.get("uploadedAt"),
            "uploadedBy": doc.get("uploadedBy"),
        }

    def stats(self, class_id: str | None = None) -> dict:
        docs = self.documents(class_id=class_id)
        by_kb: dict[str, int] = {}
        chunk_count = 0
        for doc in docs:
            by_kb[doc["kb"]] = by_kb.get(doc["kb"], 0) + int(doc.get("chunks", 0))
            chunk_count += int(doc.get("chunks", 0))
        return {"documentCount": len(docs), "chunkCount": chunk_count, "byKb": by_kb}

    def get_document(self, document_id: str) -> dict:
        doc = self._documents.get(document_id)
        if not doc:
            raise DocumentNotFoundError(f"文档不存在：{document_id}")
        return doc

    # ---- 上传 ----
    def add_upload(self, filename: str, content: bytes, kb: str = "KB4", class_id: str | None = None, uploaded_by: str | None = None) -> tuple[dict, int]:
        safe_name = Path(filename or "资料.md").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in {".md", ".txt"}:
            raise UploadValidationError("仅支持 .md / .txt 文件")
        if not content:
            raise UploadValidationError("上传文件为空")
        if len(content) > self.config.upload_max_bytes:
            raise UploadValidationError("文件大小超过 2MB 限制")
        kb = (kb or "KB4").upper()
        if kb not in {"KB1", "KB2", "KB3", "KB4"}:
            raise UploadValidationError("kb 仅支持 KB1~KB4")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise UploadValidationError("文件必须为 UTF-8 编码的文本")
        if not normalize_text(text):
            raise UploadValidationError("文件内容为空")

        class_dir = re.sub(r"[^0-9A-Za-z_-]", "_", class_id or "_shared")
        target_dir = self.config.upload_dir / class_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(safe_name).stem
        target = target_dir / safe_name
        if target.exists():
            target = target_dir / f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"
        target.write_bytes(content)

        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        doc_id = f"{kb.lower()}-{uuid.uuid4().hex[:8]}"
        relative = target.relative_to(self.config.knowledge_dir).as_posix()
        doc = {
            "documentId": doc_id,
            "name": safe_name,
            "title": stem,
            "kb": kb,
            "scope": "CLASS",
            "classId": class_id,
            "enabled": True,
            "size": len(content),
            "uploadedAt": now,
            "uploadedBy": uploaded_by,
            "builtin": False,
            "relativePath": relative,
            "chunks": 0,
        }
        self._documents[doc_id] = doc
        self.rebuild()
        return doc, int(doc.get("chunks", 0))

    # ---- 启停 / 删除 ----
    def set_enabled(self, document_id: str, enabled: bool) -> dict:
        doc = self.get_document(document_id)
        doc["enabled"] = bool(enabled)
        self.rebuild()
        return doc

    def delete(self, document_id: str) -> None:
        doc = self.get_document(document_id)
        if doc.get("builtin"):
            raise BuiltinDocumentError("内置知识库资料不可删除，仅可停用")
        path = self._doc_path(doc)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
        self._documents.pop(document_id, None)
        self.rebuild()
