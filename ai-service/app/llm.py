"""DeepSeek（OpenAI 兼容）客户端。

仅在 AI_MODE=real（或 auto 且配置了 key）时真正发起请求；所有异常统一抛
LLMError，由 service 层降级到 mock，保证接口不返回 500。

设计要点：
- /chat/completions + response_format={"type": "json_object"}，要求模型只输出 JSON；
- 自动剥离 markdown 代码块与模型可能加的前后缀，再 json.loads；
- 网络/限流/解析失败按 settings.llm_retries 重试（指数退避），仍失败抛 LLMError。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger("ams.ai.llm")

_CODE_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)


class LLMError(RuntimeError):
    """LLM 调用或 JSON 解析失败。"""


def parse_json_content(content: str) -> dict[str, Any]:
    """把模型输出解析为 dict：剥代码块、截取首尾大括号、失败抛 LLMError。"""
    text = (content or "").strip()
    if not text:
        raise LLMError("模型返回内容为空")
    fence = _CODE_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("模型返回内容不是 JSON：" + (content or "")[:200])
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("模型返回 JSON 解析失败：" + str(exc)) from exc
    if isinstance(data, list):
        raise LLMError("模型返回了 JSON 数组，期望对象")
    if not isinstance(data, dict):
        raise LLMError("模型返回 JSON 不是对象")
    return data


class DeepSeekClient:
    """最小可用的 DeepSeek Chat Completions 封装。"""

    def __init__(self, config=settings) -> None:
        self.config = config

    @property
    def available(self) -> bool:
        return bool(self.config.llm_ready)

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 2400,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """请求一次 JSON 输出；失败按配置重试，最终抛 LLMError。"""
        if not self.available:
            raise LLMError("未配置 DEEPSEEK_API_KEY，无法调用真实模型")
        url = self.config.chat_completions_url
        payload = {
            "model": self.config.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": "Bearer " + str(self.config.deepseek_api_key or ""),
            "Content-Type": "application/json",
        }
        read_timeout = float(timeout or self.config.llm_timeout_seconds)
        attempts = max(1, int(self.config.llm_retries) + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=httpx.Timeout(read_timeout, connect=10.0)) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    body = response.json()
                content = body["choices"][0]["message"]["content"]
                data = parse_json_content(content)
                logger.info(
                    "DeepSeek 调用成功 model=%s attempt=%s chars=%s",
                    self.config.deepseek_model,
                    attempt + 1,
                    len(content or ""),
                )
                return data
            except Exception as exc:  # noqa: BLE001 - 任何异常都要转成 LLMError
                last_error = exc
                logger.warning(
                    "DeepSeek 调用失败 attempt=%s/%s：%s: %s",
                    attempt + 1,
                    attempts,
                    type(exc).__name__,
                    exc,
                )
                if attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 4))
        raise LLMError("DeepSeek 调用失败：" + str(last_error))



class LLMConfig:
    """一次请求内的 LLM 配置（v1.2 §3.1：用户自带 key/模型，仅本次有效）。

    与 Settings 保持同名属性，DeepSeekClient 不需要区分系统配置还是用户覆盖；
    日志只打印 model / attempt，绝不打印 api_key。
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        timeout: float | None = None,
        retries: int | None = None,
    ) -> None:
        self.deepseek_api_key = (api_key or "").strip()
        self.deepseek_model = (model or settings.deepseek_model or "deepseek-flash").strip()
        self.deepseek_base_url = (base_url or settings.deepseek_base_url or "https://api.deepseek.com").strip().rstrip("/")
        self.llm_timeout_seconds = float(timeout if timeout is not None else settings.llm_timeout_seconds)
        self.llm_retries = int(retries if retries is not None else settings.llm_retries)

    @property
    def llm_ready(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def chat_completions_url(self) -> str:
        base = self.deepseek_base_url
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def __repr__(self) -> str:  # pragma: no cover - 调试用，仍然不泄露 key
        return f"LLMConfig(model={self.deepseek_model!r}, key=***)"


def client_for(override=None) -> DeepSeekClient | None:
    """按请求里的 llm 覆盖创建临时客户端；没有 apiKey 返回 None（走系统 key）。"""
    if override is None:
        return None
    api_key = getattr(override, "apiKey", "") or ""
    if not str(api_key).strip():
        return None
    base_url = getattr(override, "baseUrl", "") or ""
    model = getattr(override, "model", "") or ""
    return DeepSeekClient(LLMConfig(api_key=str(api_key), base_url=str(base_url), model=str(model)))


client = DeepSeekClient()
