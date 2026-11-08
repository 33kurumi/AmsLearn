"""个性化学习导师 · AI 服务（FastAPI）入口。

只做装配：配置 CORS、注册路由、启动时校验配置并重建知识库索引。
业务实现见 app/service.py 与 app/mock.py（演示兜底）/ app/llm.py（DeepSeek）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import service
from .config import settings
from .routers import ai, knowledge

class Utf8JSONResponse(JSONResponse):
    """显式声明 charset=utf-8，避免 Windows PowerShell 5.1 等客户端按本地编码解析中文。"""

    media_type = "application/json; charset=utf-8"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ams.ai")


@asynccontextmanager
async def lifespan(_: FastAPI):
    stats = service.ensure_ready()
    logger.info(
        "启动完成：mode=%s model=%s llm_ready=%s documents=%s chunks=%s rebuild=%sms",
        settings.mode,
        settings.deepseek_model,
        settings.llm_ready,
        stats["documentCount"],
        stats["chunkCount"],
        stats["durationMs"],
    )
    yield
    logger.info("AI 服务关闭")


app = FastAPI(
    title="个性化学习导师 · AI 服务",
    description="高等数学考研个性化学习导师系统的 AI 能力层：RAG 答疑、诊断出题、分层练习、学习计划、学情建议与知识库管理。",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=Utf8JSONResponse,
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> Utf8JSONResponse:
    """错误响应同样使用 UTF-8 声明，保证 {"detail": "..."} 中文不乱码。"""
    return Utf8JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ai.router)
app.include_router(knowledge.router)


@app.get("/", include_in_schema=False)
def index() -> dict:
    return {
        "service": "ams-ai",
        "status": "UP",
        "mode": settings.mode,
        "docs": "/docs",
        "health": "/health",
    }
