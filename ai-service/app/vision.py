"""v1.3 图片识别（视觉大模型）客户端。

契约 §1.2：POST /vision/extract 用硅基流动（SiliconFlow）OpenAI 兼容接口调用
Qwen/Qwen3-VL-8B-Instruct 做 OCR，把讲义/题目图片原样转成文字（公式转 LaTeX），
不做解答、不改写。key 默认读 VISION_API_KEY，留空时回退 EMBEDDING_API_KEY。
任何失败都由调用方转成 ok=false + 中文 message，绝不抛出到路由层。
"""
from __future__ import annotations

import base64
import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# 未配置视觉模型时的固定文案（契约 §1.2）
NOT_CONFIGURED_MESSAGE = (
    "未配置识图模型：请在 ai-service/.env 配置 VISION_API_KEY"
    "（或复用 EMBEDDING_API_KEY）后重启服务。"
)
# 调用失败时的固定文案（契约 §1.2）
FAILED_MESSAGE = "图片识别失败，请重试或改为文字输入。"

ALLOWED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/webp": "webp",
    "image/gif": "gif",
}

VISION_SYSTEM_PROMPT = (
    "你是一个只做文字识别（OCR）的助手。把图片中的内容原样转写为文字，"
    "不要解答题目、不要总结、不要评论、不要补全看不清的内容。"
    "数学公式请用 LaTeX 表示（行内用 $...$，独立公式用 $$...$$）；"
    "表格按 Markdown 表格输出；题干、选项、编号保持原有结构。"
    "看不清的局部用 [不清] 标记。只输出识别结果本身。"
)

VISION_USER_PROMPT = (
    "请识别这张图片中的全部文字与公式，原样输出。"
    "如果是题目，保留题号、题干、选项；不要给出答案或解析。"
)


class VisionError(Exception):
    """视觉模型调用/解析失败。"""


class VisionClient:
    """OpenAI 兼容的视觉模型客户端（当前对接硅基流动）。"""

    def __init__(self, config=settings) -> None:
        self.config = config

    # ---- 配置视图 -------------------------------------------------------
    @property
    def provider(self) -> str:
        return self.config.vision_provider_name

    @property
    def model(self) -> str:
        return self.config.vision_model

    @property
    def available(self) -> bool:
        return self.config.vision_ready

    @property
    def api_key(self) -> str:
        return self.config.resolved_vision_api_key

    @property
    def chat_url(self) -> str:
        return self.config.vision_chat_completions_url

    # ---- 调用 -----------------------------------------------------------
    def extract(self, image_bytes: bytes, content_type: str) -> str:
        """识别图片文字；失败抛 VisionError（调用方负责转 ok=false）。"""
        if not self.available:
            raise VisionError(NOT_CONFIGURED_MESSAGE)
        if not image_bytes:
            raise VisionError("图片内容为空，请重新上传。")
        fmt = ALLOWED_IMAGE_TYPES.get((content_type or "").split(";")[0].strip().lower())
        if not fmt:
            raise VisionError("图片格式不支持，请上传 png/jpeg/webp/gif 图片。")
        data_url = "data:image/%s;base64,%s" % (
            "jpeg" if fmt == "jpg" else fmt,
            base64.b64encode(image_bytes).decode("ascii"),
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "stream": False,
        }
        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self.config.vision_timeout_seconds, connect=10)
        last_error: Exception | None = None
        attempts = max(1, int(self.config.llm_retries) + 1)
        for attempt in range(1, attempts + 1):
            try:
                response = httpx.post(
                    self.chat_url, json=payload, headers=headers, timeout=timeout
                )
                if response.status_code >= 400:
                    raise VisionError(
                        "视觉接口返回 HTTP %s" % response.status_code
                    )
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise VisionError("视觉接口返回内容为空")
                message = choices[0].get("message") or {}
                text = (message.get("content") or "").strip()
                if not text:
                    raise VisionError("视觉接口未识别出文字")
                logger.info(
                    "识图成功 provider=%s model=%s attempt=%s chars=%s",
                    self.provider,
                    self.model,
                    attempt,
                    len(text),
                )
                return text
            except VisionError as exc:
                last_error = exc
                logger.warning("识图失败 attempt=%s: %s", attempt, exc)
            except Exception as exc:  # 网络/解析异常统一重试
                last_error = exc
                logger.warning("识图异常 attempt=%s: %s: %s", attempt, type(exc).__name__, exc)
        raise VisionError(FAILED_MESSAGE) from last_error


client = VisionClient()
