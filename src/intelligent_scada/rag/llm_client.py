"""Small OpenAI-compatible chat-completions client."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx


class LLMConfigurationError(RuntimeError):
    """Raised when an answer or router model is not configured for use."""


class LLMProviderError(RuntimeError):
    """Safe provider failure suitable for the public API."""

    def __init__(self, message: str, *, status_code: int = 502, code: str = "provider_error") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        model: str,
        timeout: float = 90.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _endpoint(self) -> str:
        if not self.base_url or not self.api_key:
            raise LLMConfigurationError(
                "Answer model is not configured. Set the API base URL and key in .env."
            )
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        response_format: dict[str, str] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = self._endpoint()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMProviderError("The model provider timed out. Try again shortly.",
                                   status_code=504, code="provider_timeout") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise LLMProviderError("The model provider is rate limited. Try again later.",
                                       status_code=503, code="provider_rate_limit") from exc
            raise LLMProviderError("The model provider rejected the request. Check server configuration.") from exc
        except (httpx.RequestError, ValueError) as exc:
            raise LLMProviderError("The model provider is unavailable or returned an invalid response.") from exc
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Expected nonempty text")
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError("The model provider returned an invalid answer. Try again.") from exc
