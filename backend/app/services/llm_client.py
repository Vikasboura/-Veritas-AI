"""
app/services/llm_client.py
───────────────────────────
OpenAI-compatible async LLM client with configurable base URL,
exponential backoff retry via tenacity, and streaming token generation.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()


class LLMClient:
    """Async wrapper around OpenAI-compatible API endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.base_url = base_url or settings.LLM_BASE_URL
        self.api_key = api_key or settings.LLM_API_KEY
        self.timeout = timeout if timeout is not None else float(settings.LLM_TIMEOUT_SECONDS)
        self.max_retries = max_retries if max_retries is not None else settings.LLM_MAX_RETRIES

        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,  # We manage retries with tenacity for better telemetry
        )

    async def create_chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Execute non-streaming completion with exponential backoff.
        Returns: (completion_text, usage_dict)
        """
        chosen_model = model or settings.LLM_MODEL
        tokens_limit = max_tokens or settings.LLM_MAX_TOKENS

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError)),
        )
        async def _call():
            return await self._client.chat.completions.create(
                model=chosen_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=tokens_limit,
                stream=False,
            )

        resp = await _call()
        content = resp.choices[0].message.content or ""
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            "total_tokens": resp.usage.total_tokens if resp.usage else 0,
            "model": chosen_model,
        }
        return content, usage

    async def create_chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from OpenAI-compatible endpoint.
        Yields text fragments as they arrive.
        """
        chosen_model = model or settings.LLM_MODEL
        tokens_limit = max_tokens or settings.LLM_MAX_TOKENS

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError)),
        )
        async def _init_stream():
            return await self._client.chat.completions.create(
                model=chosen_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=tokens_limit,
                stream=True,
            )

        response_stream = await _init_stream()
        async for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Singleton getter for the app-wide LLM client."""
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance
