"""知识库管理路由：AI12~AI16。"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import service
from ..knowledge import BuiltinDocumentError, DocumentNotFoundError, UploadValidationError
from ..schemas import (
    DeleteResponse,
    DocumentVO,
    DocumentsResponse,
    KnowledgePatchRequest,
    RebuildResponse,
    UploadResponse,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/documents", response_model=DocumentsResponse, summary="AI12 文件列表")
def list_documents(classId: str | None = None) -> DocumentsResponse:
    return service.list_documents(class_id=classId)


@router.post("/upload", response_model=UploadResponse, summary="AI13 上传知识库文件")
async def upload_document(
    file: UploadFile = File(..., description="仅支持 UTF-8 的 .md/.txt，≤2MB"),
    kb: str = Form("KB4", description="KB1~KB4"),
    classId: str | None = Form(None),
    uploadedBy: str | None = Form(None),
) -> UploadResponse:
    content = await file.read()
    try:
        return service.upload_document(
            filename=file.filename or "资料.md",
            content=content,
            kb_name=kb,
            class_id=classId,
            uploaded_by=uploadedBy,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="上传失败：" + str(exc)) from exc


@router.patch("/documents/{document_id}", response_model=DocumentVO, summary="AI14 启停文档")
def patch_document(document_id: str, req: KnowledgePatchRequest) -> DocumentVO:
    try:
        return service.set_document_enabled(document_id, req.enabled)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BuiltinDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/documents/{document_id}", response_model=DeleteResponse, summary="AI15 删除文档")
def delete_document(document_id: str) -> DeleteResponse:
    try:
        return service.delete_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BuiltinDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/rebuild", response_model=RebuildResponse, summary="AI16 重建索引")
def rebuild() -> RebuildResponse:
    return service.rebuild_knowledge()
