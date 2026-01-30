"""Unified AI model management (OpenAI, Claude, Ollama)."""

from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
import openai
from anthropic import Anthropic
from pydantic import BaseModel, BaseSettings, Field, HttpUrl, validator

logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    """Supported AI vendors."""

    OPENAI = "openai"
    CLAUDE = "claude"
    OLLAMA = "ollama"


PROVIDER_DESCRIPTIONS: Dict[AIProvider, str] = {
    AIProvider.OPENAI: "OpenAI GPT-4 / GPT-4o-chat models",
    AIProvider.CLAUDE: "Anthropic Claude (local or Claude 3.5-sonic)",
    AIProvider.OLLAMA: "Ollama local models (http://localhost:11434)",
}


class AIModelsSettings(BaseSettings):
    """Environment-configured defaults for each provider."""

    openai_model: str = Field("gpt-4o-mini", env="AI_MODELS_OPENAI_MODEL")
    claude_model: str = Field("claude-3.5-sonic", env="AI_MODELS_CLAUDE_MODEL")
    ollama_model: str = Field("gemma3", env="AI_MODELS_OLLAMA_MODEL")
    default_provider: AIProvider = Field(
        AIProvider.OPENAI, env="AI_MODELS_DEFAULT_PROVIDER"
    )
    system_prompt: str = Field(
        "You are CryptoTrader's AI assistant.", env="AI_MODELS_SYSTEM_PROMPT"
    )
    ollama_base_url: HttpUrl = Field("http://localhost:11434/api", env="OLLAMA_BASE_URL")
    ollama_api_key: Optional[str] = Field(None, env="OLLAMA_API_KEY")
    request_timeout_seconds: float = Field(
        20.0, env="AI_MODELS_REQUEST_TIMEOUT_SECONDS", gt=0
    )

    class Config:  # noqa: D106
        env_file = ".env"
        extra = "ignore"

    @validator("default_provider", pre=True)
    def _normalize_provider(cls, value: Any) -> AIProvider:
        if isinstance(value, AIProvider):
            return value
        if isinstance(value, str):
            try:
                return AIProvider(value.strip().lower())
            except ValueError:
                raise ValueError(f"Unknown provider '{value}'")
        raise ValueError("default_provider must be a valid AIProvider")


class AIModelRequest(BaseModel):
    """Normalized request for any provider."""

    prompt: str = Field(..., min_length=1)
    provider: Optional[AIProvider] = Field(
        None, description="Override the selected provider"
    )
    model: Optional[str] = Field(None, description="Override the configured model")
    system_prompt: Optional[str] = Field(
        None, description="Inject a provider-specific system prompt"
    )
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="Sampling temperature (0-2)"
    )
    max_tokens: int = Field(512, gt=0, description="Maximum tokens to generate")
    suffix: Optional[str] = Field(
        None, description="Text appended after the generated response"
    )
    stream: bool = Field(False, description="Whether streaming responses are desired")

    @validator("prompt", pre=True)
    def _strip_prompt(cls, value: str) -> str:
        return value.strip()


class AIModelResponse(BaseModel):
    """Structured output returned after a provider call."""

    provider: AIProvider
    model: str
    text: str
    raw_response: Any


class AIModelDescriptor(BaseModel):
    """Describes the current configuration for a provider."""

    provider: AIProvider
    model: str
    description: str
    available: bool
    active: bool


class AIModelsService:
    """Centralizes provider selection, model metadata, and generation calls."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        settings: Optional[AIModelsSettings] = None,
    ) -> None:
        self._settings = settings or AIModelsSettings()
        self._active_provider = self._settings.default_provider
        self._model_map: Dict[AIProvider, str] = {
            AIProvider.OPENAI: self._settings.openai_model,
            AIProvider.CLAUDE: self._settings.claude_model,
            AIProvider.OLLAMA: self._settings.ollama_model,
        }
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._openai_model = self._model_map[AIProvider.OPENAI]
        self._claude_model = self._model_map[AIProvider.CLAUDE]
        self._ollama_model = self._model_map[AIProvider.OLLAMA]

        if self._openai_api_key:
            openai.api_key = self._openai_api_key

        self._anthropic_client = (
            Anthropic(api_key=self._anthropic_api_key)
            if self._anthropic_api_key
            else None
        )

        headers: Dict[str, str] = {}
        if self._settings.ollama_api_key:
            headers["Authorization"] = f"Bearer {self._settings.ollama_api_key}"

        self._ollama_client = httpx.AsyncClient(
            base_url=str(self._settings.ollama_base_url).rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(
                self._settings.request_timeout_seconds, connect=5.0, read=5.0
            ),
        )

    async def close(self) -> None:
        """Release the HTTP client used for Ollama."""
        await self._ollama_client.aclose()

    @property
    def active_provider(self) -> AIProvider:
        return self._active_provider

    def set_active_provider(self, provider: AIProvider) -> None:
        """Switch the active provider, ensuring it is configured."""
        if not self._is_provider_available(provider):
            raise RuntimeError(f"{provider.value} is not currently available")
        self._active_provider = provider

    def set_model_for_provider(self, provider: AIProvider, model: str) -> None:
        """Override the configured model name for a provider."""
        normalized = model.strip()
        if not normalized:
            raise ValueError("Model name cannot be empty")
        self._model_map[provider] = normalized

    def get_model_for_provider(self, provider: AIProvider) -> str:
        return self._model_map[provider]

    def list_model_inventory(self) -> List[AIModelDescriptor]:
        """Return the configured model for each provider and whether it can run."""
        inventory: List[AIModelDescriptor] = []
        for provider in AIProvider:
            inventory.append(
                AIModelDescriptor(
                    provider=provider,
                    model=self._model_map[provider],
                    description=PROVIDER_DESCRIPTIONS.get(
                        provider, "Unknown provider"
                    ),
                    available=self._is_provider_available(provider),
                    active=provider == self._active_provider,
                )
            )
        return inventory

    async def generate(self, request: AIModelRequest) -> AIModelResponse:
        """Run a single prompt through the selected provider."""
        provider = self._select_provider(request.provider)
        model = request.model or self._model_map[provider]
        if provider == AIProvider.OPENAI:
            text, raw = await self._call_openai(model, request)
        elif provider == AIProvider.CLAUDE:
            text, raw = await self._call_claude(model, request)
        else:
            text, raw = await self._call_ollama(model, request)

        return AIModelResponse(
            provider=provider, model=model, text=text, raw_response=raw
        )

    def _select_provider(self, candidate: Optional[AIProvider]) -> AIProvider:
        preferred = candidate or self._active_provider
        if preferred and self._is_provider_available(preferred):
            return preferred

        for provider in AIProvider:
            if self._is_provider_available(provider):
                return provider

        raise RuntimeError("No AI provider is currently configured")

    def _is_provider_available(self, provider: AIProvider) -> bool:
        if provider == AIProvider.OPENAI:
            return bool(self._openai_api_key)
        if provider == AIProvider.CLAUDE:
            return bool(self._anthropic_api_key and self._anthropic_client)
        if provider == AIProvider.OLLAMA:
            return bool(self._settings.ollama_base_url)
        return False

    async def _call_openai(
        self, model: str, request: AIModelRequest
    ) -> Tuple[str, Dict[str, Any]]:
        if not self._openai_api_key:
            raise RuntimeError("OpenAI API key is not configured")

        messages = self._build_openai_messages(request)
        temperature = (
            request.temperature if request.temperature is not None else 0.25
        )
        try:
            completion = await openai.ChatCompletion.acreate(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=request.max_tokens,
            )
            text = completion.choices[0].message.content
            raw = {
                "provider": AIProvider.OPENAI.value,
                "model": model,
                "message": text,
            }
            return text.strip(), raw
        except Exception as exc:
            logger.exception("OpenAI model call failed: %s", exc)
            raise

    async def _call_claude(
        self, model: str, request: AIModelRequest
    ) -> Tuple[str, Dict[str, Any]]:
        if not self._anthropic_client:
            raise RuntimeError("Anthropic API key is not configured")

        messages = self._build_claude_messages(request)
        temperature = (
            request.temperature if request.temperature is not None else 0.25
        )
        max_tokens = request.max_tokens
        try:
            response = await asyncio.to_thread(
                self._anthropic_client.messages.create,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = (response.content or "").strip()
            serialized_response = self._serialize_claude_response(response)
            raw = {
                "provider": AIProvider.CLAUDE.value,
                "model": model,
                "message": text,
                "response": serialized_response,
            }
            return text, raw
        except Exception as exc:
            logger.exception("Claude model call failed: %s", exc)
            raise

    async def _call_ollama(
        self, model: str, request: AIModelRequest
    ) -> Tuple[str, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            "stream": False,
        }
        if request.suffix:
            payload["suffix"] = request.suffix
        if request.system_prompt:
            payload["system"] = request.system_prompt

        options: Dict[str, Any] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options

        try:
            response = await self._ollama_client.post(
                "/generate", json=payload
            )
            response.raise_for_status()
            parsed = response.json()
            text = (parsed.get("response") or "").strip()
            raw = {
                "provider": AIProvider.OLLAMA.value,
                "model": model,
                "data": parsed,
            }
            return text, raw
        except Exception as exc:
            logger.exception("Ollama model call failed: %s", exc)
            raise

    def _build_openai_messages(
        self, request: AIModelRequest
    ) -> List[Dict[str, str]]:
        system = request.system_prompt or self._settings.system_prompt
        return [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": request.prompt},
        ]

    def _build_claude_messages(
        self, request: AIModelRequest
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        system = request.system_prompt or self._settings.system_prompt
        if system:
            messages.append({"role": "system", "content": system.strip()})

        user_content = request.prompt
        if request.suffix:
            user_content = f"{user_content}\n{request.suffix}"

        messages.append({"role": "user", "content": user_content})
        return messages

    def _serialize_claude_response(self, response: Any) -> Any:
        for attr in ("dict", "to_dict"):
            serializer = getattr(response, attr, None)
            if callable(serializer):
                try:
                    return serializer()
                except Exception:
                    continue
        return response
