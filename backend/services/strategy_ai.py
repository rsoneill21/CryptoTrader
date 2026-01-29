"""AI strategy proposal helpers driven by OpenAI / Claude."""

import asyncio
import json
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional

import openai
from anthropic import AI_PROMPT, Anthropic, HUMAN_PROMPT
from pydantic import BaseModel, Extra, Field, validator

logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    """Supported AI vendors for strategy generation."""

    OPENAI = "openai"
    CLAUDE = "claude"


def _env_provider() -> AIProvider:
    candidate = os.getenv("STRATEGY_AI_PROVIDER", AIProvider.OPENAI.value).lower()
    try:
        return AIProvider(candidate)
    except ValueError:
        logger.warning("Unknown STRATEGY_AI_PROVIDER=%s; defaulting to openai", candidate)
        return AIProvider.OPENAI


class StrategyProposalInput(BaseModel, extra=Extra.forbid):
    """Validated payload describing the market context for the AI prompt."""

    symbols: List[str] = Field(..., min_items=1)
    timeframe: str = Field("1h", min_length=1)
    market_summary: str = Field(..., min_length=10)
    risk_tolerance: str = Field("balanced", min_length=1)
    preferred_indicators: List[str] = Field(default_factory=list)
    target_return_pct: Optional[float] = Field(None, ge=0)
    max_positions: Optional[int] = Field(3, ge=1)
    notes: Optional[str] = Field(None, description="Optional reasoning to seed the prompt.")

    @validator("symbols", each_item=True)
    def _normalize_symbols(cls, value: str) -> str:
        return value.strip().upper()


class StrategyProposal(BaseModel):
    """Structured response returned after parsing the AI completion."""

    name: str
    description: str
    entry_criteria: Optional[str]
    exit_criteria: Optional[str]
    risk_management: Optional[str]
    indicators: List[str] = Field(default_factory=list)
    rules: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float]
    provider: AIProvider
    raw_response: str


class StrategyAIService:
    """Wraps OpenAI / Claude calls to propose trading strategies."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_provider: Optional[AIProvider] = None,
    ) -> None:
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._default_provider = default_provider or _env_provider()
        self._openai_model = os.getenv("STRATEGY_AI_OPENAI_MODEL", "gpt-4o-mini")
        self._claude_model = os.getenv("STRATEGY_AI_CLAUDE_MODEL", "claude-3.5-sonic")

        if self._openai_api_key:
            openai.api_key = self._openai_api_key

        self._anthropic_client = (
            Anthropic(api_key=self._anthropic_api_key)
            if self._anthropic_api_key
            else None
        )

    async def propose_strategy(
        self,
        request: StrategyProposalInput,
        provider: Optional[AIProvider] = None,
    ) -> StrategyProposal:
        """Produce a structured strategy proposal from the configured AI providers."""

        chosen = self._select_provider(provider)

        if chosen == AIProvider.OPENAI:
            raw_response = await self._call_openai(request)
        else:
            raw_response = await self._call_claude(request)

        parsed = self._parse_response(raw_response)

        return StrategyProposal(
            name=parsed.get("name") or self._fallback_name(chosen),
            description=parsed.get("description") or parsed.get("summary") or "",
            entry_criteria=parsed.get("entry_criteria"),
            exit_criteria=parsed.get("exit_criteria"),
            risk_management=parsed.get("risk_management"),
            indicators=self._normalize_indicators(parsed.get("indicators")),
            rules=parsed.get("rules") or parsed.get("rule_set") or {},
            confidence=self._safe_float(parsed.get("confidence")),
            provider=chosen,
            raw_response=raw_response,
        )

    def _select_provider(self, candidate: Optional[AIProvider]) -> AIProvider:
        """Pick an available provider based on the requested preference."""
        if candidate and self._is_provider_available(candidate):
            return candidate

        if self._is_provider_available(self._default_provider):
            return self._default_provider

        for provider in AIProvider:
            if self._is_provider_available(provider):
                return provider

        raise RuntimeError("No AI provider configured for strategy proposals")

    def _is_provider_available(self, provider: AIProvider) -> bool:
        if provider == AIProvider.OPENAI:
            return bool(self._openai_api_key)
        if provider == AIProvider.CLAUDE:
            return bool(self._anthropic_api_key and self._anthropic_client)
        return False

    async def _call_openai(self, request: StrategyProposalInput) -> str:
        if not self._openai_api_key:
            raise RuntimeError("OpenAI API key is not configured for strategy proposals")

        system_message = (
            "You are CryptoTrader's AI strategist. Analyze the supplied market "
            "context and compose a concise trading playbook."
        )
        user_message = self._build_prompt(request)

        try:
            completion = await openai.ChatCompletion.acreate(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.25,
                max_tokens=900,
            )
            text = completion.choices[0].message.content
            return text.strip()
        except Exception as exc:
            logger.exception("OpenAI strategy call failed: %s", exc)
            raise

    async def _call_claude(self, request: StrategyProposalInput) -> str:
        if not self._anthropic_client:
            raise RuntimeError("Anthropic/Claude API key is not configured")

        prompt = f"{HUMAN_PROMPT}{self._build_prompt(request)}{AI_PROMPT}"

        try:
            response = await asyncio.to_thread(
                self._anthropic_client.completions.create,
                model=self._claude_model,
                prompt=prompt,
                max_tokens_to_sample=900,
                temperature=0.25,
            )
            return response.completion.strip()
        except Exception as exc:
            logger.exception("Claude strategy call failed: %s", exc)
            raise

    def _build_prompt(self, request: StrategyProposalInput) -> str:
        indicators = ", ".join(request.preferred_indicators) or "N/A"
        notes = request.notes or "None"
        lines = [
            "Market context:",
            request.market_summary.strip(),
            "",
            f"Symbols: {', '.join(request.symbols)}",
            f"Timeframe: {request.timeframe}",
            f"Risk tolerance: {request.risk_tolerance}",
            f"Target return: {request.target_return_pct or 'unspecified'}",
            f"Max concurrent positions: {request.max_positions}",
            f"Preferred indicators: {indicators}",
            f"Additional notes: {notes}",
            "",
            "Return a JSON object with the following keys: name, description, entry_criteria, exit_criteria, risk_management, indicators (array), rules (object), confidence (number between 0 and 1).",
            "Do not include markdown fences; reply with raw JSON as the entire text when possible.",
        ]
        return "\n".join(lines)

    def _parse_response(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}

        cleaned = self._strip_code_blocks(text)
        json_payload = self._extract_json(cleaned)
        if not json_payload:
            return {"description": cleaned, "rules": {"raw": cleaned}}
        return json_payload

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        trimmed = text.strip()
        if trimmed.startswith("```"):
            lines = trimmed.splitlines()
            if len(lines) > 2 and lines[0].startswith("```"):
                lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                trimmed = "\n".join(lines).strip()
        return trimmed

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None

        candidate = text[first:last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _normalize_indicators(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None]
        if isinstance(value, str):
            return [value.strip()]
        return []

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fallback_name(provider: AIProvider) -> str:
        return f"{provider.value.upper()} Strategy"


# Singleton instance for easy reuse across the backend.
strategy_ai_service = StrategyAIService()
