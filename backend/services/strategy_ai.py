"""AI strategy proposal helpers driven by OpenAI / Claude."""

import asyncio
import json
import logging
import math
import os
from enum import Enum
from typing import Any, Dict, List, Optional

import openai
from anthropic import AI_PROMPT, Anthropic, HUMAN_PROMPT
from pydantic import BaseModel, ConfigDict, Extra, Field, validator

from core.paper_trading import PaperStrategyPerformanceSummary

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


class StrategyPromotionContext(BaseModel):
    """Context describing a paper strategy when seeking a promotion recommendation."""

    strategy_id: int
    strategy_name: str
    performance: PaperStrategyPerformanceSummary
    timeframe: str = Field("recent", min_length=1)
    market_summary: Optional[str] = Field(
        None, description="Optional short summary of the current market context."
    )
    user_notes: Optional[str] = Field(
        None, description="Optional notes or hypotheses that should influence the recommendation."
    )

    model_config = ConfigDict(extra="forbid")


class StrategyPromotionRecommendation(BaseModel):
    """AI or heuristic recommendation whether the strategy should go live."""

    strategy_id: int
    recommended: bool
    confidence: float
    summary: str
    reasoning: str
    suggested_actions: List[str] = Field(default_factory=list)
    provider: Optional[AIProvider] = None
    raw_response: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @validator("confidence", pre=True, always=True)
    def _clamp_confidence(cls, value: Any) -> float:
        try:
            normalized = float(value)
        except (TypeError, ValueError):
            normalized = 0.5
        return max(0.0, min(1.0, normalized))


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

    async def recommend_promotion(
        self,
        context: StrategyPromotionContext,
        provider: Optional[AIProvider] = None,
    ) -> StrategyPromotionRecommendation:
        """Evaluate paper performance and recommend whether the strategy should go live."""

        chosen = None
        raw_response: Optional[str] = None
        parsed: Dict[str, Any] = {}
        try:
            chosen = self._select_provider(provider)
            if chosen == AIProvider.OPENAI:
                raw_response = await self._call_openai_promotion(context)
            else:
                raw_response = await self._call_claude_promotion(context)
            parsed = self._parse_response(raw_response)
        except RuntimeError:
            logger.debug("No AI provider configured for promotion recommendations")
        except Exception as exc:
            logger.exception("Promotion recommendation failed: %s", exc)

        recommendation = self._build_recommendation_from_payload(
            context, parsed, raw_response, chosen
        )
        if recommendation:
            return recommendation

        return self._heuristic_promotion_recommendation(context, raw_response)

    async def analyze_degradation(
        self,
        strategy_id: int,
        strategy_name: str,
        performance_summary: Dict[str, Any],
        provider: Optional[AIProvider] = None,
    ) -> Dict[str, Any]:
        """Analyze a degraded strategy and propose adjustments."""
        chosen = self._select_provider(provider)
        
        prompt = [
            f"Strategy degradation analysis for '{strategy_name}' (ID: {strategy_id})",
            "Performance data:",
            json.dumps(performance_summary, indent=2),
            "",
            "Analyze why the strategy might be failing and propose concrete rule adjustments.",
            "Return a JSON object with: reasoning, suggestions (list), and proposed_rules (object).",
        ]
        
        system_message = "You are a senior quantitative strategist specializing in self-healing trading systems."
        user_message = "\n".join(prompt)

        try:
            if chosen == AIProvider.OPENAI:
                completion = await openai.ChatCompletion.acreate(
                    model=self._openai_model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                )
                text = completion.choices[0].message.content
            else:
                # Claude implementation
                anthropic_prompt = f"{HUMAN_PROMPT}{user_message}{AI_PROMPT}"
                response = await asyncio.to_thread(
                    self._anthropic_client.completions.create,
                    model=self._claude_model,
                    prompt=anthropic_prompt,
                    max_tokens_to_sample=800,
                    temperature=0.3,
                )
                text = response.completion

            return self._parse_response(text)
        except Exception as exc:
            logger.error("Degradation analysis failed for strategy %s", strategy_id, exc_info=True)
            return {
                "reasoning": f"AI analysis failed: {str(exc)}",
                "suggestions": ["Manually review recent trades", "Consider pausing the strategy"],
                "proposed_rules": {}
            }

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

    async def _call_openai_promotion(self, context: StrategyPromotionContext) -> str:
        if not self._openai_api_key:
            raise RuntimeError("OpenAI API key is not configured for strategy promotions")

        system_message = (
            "You are CryptoTrader's promotion analyst. Review the supplied strategy performance summary "
            "and decide whether it is ready for live deployment."
        )
        user_message = self._build_promotion_prompt(context)

        try:
            completion = await openai.ChatCompletion.acreate(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.25,
                max_tokens=700,
            )
            return completion.choices[0].message.content.strip()
        except Exception as exc:
            logger.exception("OpenAI promotion recommendation failed: %s", exc)
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

    async def _call_claude_promotion(self, context: StrategyPromotionContext) -> str:
        if not self._anthropic_client:
            raise RuntimeError("Anthropic/Claude API key is not configured")

        prompt = f"{HUMAN_PROMPT}{self._build_promotion_prompt(context)}{AI_PROMPT}"

        try:
            response = await asyncio.to_thread(
                self._anthropic_client.completions.create,
                model=self._claude_model,
                prompt=prompt,
                max_tokens_to_sample=700,
                temperature=0.25,
            )
            return response.completion.strip()
        except Exception as exc:
            logger.exception("Claude promotion recommendation failed: %s", exc)
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

    def _build_promotion_prompt(self, context: StrategyPromotionContext) -> str:
        metrics = context.performance
        recent_samples = ", ".join(f"{value:.2f}" for value in metrics.recent_pnl_samples)
        recent_samples = recent_samples or "n/a"
        lines: List[str] = [
            "Promotion evaluation request:",
            f"Strategy: {context.strategy_name} (ID {context.strategy_id})",
            f"Timeframe: {context.timeframe}",
            f"Market summary: {context.market_summary or 'N/A'}",
            f"Performance summary:",
            f"- Total trades: {metrics.total_trades}",
            f"- Win rate: {metrics.win_rate:.2%}",
            f"- Total PnL: {metrics.total_pnl:.2f}",
            f"- Max drawdown: {metrics.max_drawdown:.2f}",
            f"- Sharpe ratio: {metrics.sharpe_ratio if metrics.sharpe_ratio is not None else 'N/A'}",
            f"- Recent PnL samples: {recent_samples}",
        ]
        if context.user_notes:
            lines.append(f"Notes: {context.user_notes}")
        lines.extend(
            [
                "Answer with a raw JSON object containing the following keys:",
                "recommended (boolean) - whether this strategy should be promoted to live.",
                "confidence (number 0-1) - your confidence in that recommendation.",
                "summary - concise explanation of the decision.",
                "reasoning - more detailed reasoning or caveats.",
                "suggested_actions - array of concrete next steps.",
                "Do NOT wrap the response in markdown fences."
            ]
        )
        return "\n".join(lines)

    def _parse_response(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}

        cleaned = self._strip_code_blocks(text)
        json_payload = self._extract_json(cleaned)
        if not json_payload:
            return {"description": cleaned, "rules": {"raw": cleaned}}
        return json_payload

    def _build_recommendation_from_payload(
        self,
        context: StrategyPromotionContext,
        payload: Dict[str, Any],
        raw_response: Optional[str],
        provider: Optional[AIProvider],
    ) -> Optional[StrategyPromotionRecommendation]:
        if not payload:
            return None

        if payload.get("strategy_id") and payload["strategy_id"] != context.strategy_id:
            logger.warning(
                "Promotion recommendation payload strategy_id %s does not match context %s",
                payload.get("strategy_id"),
                context.strategy_id,
            )

        if payload.get("recommended") is None:
            return None

        recommended = bool(payload.get("recommended"))
        confidence = self._safe_float(payload.get("confidence"))
        if confidence is None:
            confidence = self._heuristic_confidence_value(context.performance)

        summary = str(
            payload.get("summary")
            or payload.get("reasoning")
            or "Promotion recommendation from AI agent."
        )
        reasoning = str(payload.get("reasoning") or summary)
        actions = self._normalize_actions(
            payload.get("suggested_actions") or payload.get("actions")
        )
        if not actions:
            actions = [
                "Document performance and notify stakeholders",
                "Monitor live risk guards" if recommended else "Collect more paper trades",
            ]

        return StrategyPromotionRecommendation(
            strategy_id=context.strategy_id,
            recommended=recommended,
            confidence=confidence,
            summary=summary,
            reasoning=reasoning,
            suggested_actions=actions,
            provider=provider,
            raw_response=raw_response,
        )

    def _heuristic_promotion_recommendation(
        self, context: StrategyPromotionContext, raw_response: Optional[str]
    ) -> StrategyPromotionRecommendation:
        metrics = context.performance
        promotion_ready = (
            metrics.total_trades >= 10
            and metrics.total_pnl > 0
            and metrics.win_rate >= 0.55
            and metrics.max_drawdown < max(1.0, abs(metrics.total_pnl) * 0.5 + 0.1)
        )
        summary = (
            "Heuristic suggests the strategy is ready for live deployment."
            if promotion_ready
            else "Heuristic suggests continuing paper trading for now."
        )
        reasoning = (
            f"Win rate {metrics.win_rate:.1%}, total PnL {metrics.total_pnl:.2f}, "
            f"max drawdown {metrics.max_drawdown:.2f}."
        )
        actions = [
            "Promote strategy to live" if promotion_ready else "Keep testing via paper trading",
            "Log a review of recent market conditions",
        ]
        return StrategyPromotionRecommendation(
            strategy_id=context.strategy_id,
            recommended=promotion_ready,
            confidence=self._heuristic_confidence_value(metrics),
            summary=summary,
            reasoning=reasoning,
            suggested_actions=actions,
            provider=None,
            raw_response=raw_response,
        )

    def _heuristic_confidence_value(self, metrics: PaperStrategyPerformanceSummary) -> float:
        win_component = metrics.win_rate
        pnl_component = math.tanh(metrics.total_pnl / 1000.0)
        drawdown_penalty = min(0.4, metrics.max_drawdown / (abs(metrics.total_pnl) + 1.0))
        base_confidence = 0.3 + 0.4 * win_component + 0.2 * pnl_component - drawdown_penalty
        return max(0.05, min(0.98, base_confidence))

    @staticmethod
    def _normalize_actions(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if item is not None and str(item).strip()]
        if isinstance(value, str):
            candidate = value.strip()
            return [candidate] if candidate else []
        return []

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
