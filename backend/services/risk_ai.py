"""AI-backed risk adjustment helpers."""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import openai
from anthropic import AI_PROMPT, Anthropic, HUMAN_PROMPT
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.models import RiskSettings, StrategyPerformance, Trade

logger = logging.getLogger(__name__)

RECENT_TRADE_WINDOW = timedelta(days=3)
RECENT_TRADE_LIMIT = 120
HEURISTIC_CONFIDENCE = 0.45


class AIProvider(str, Enum):
    """Supported AI vendors for risk adjustments."""

    OPENAI = "openai"
    CLAUDE = "claude"


def _env_provider() -> "AIProvider":
    candidate = os.getenv("RISK_AI_PROVIDER", "openai").lower()
    try:
        return AIProvider(candidate)
    except ValueError:
        logger.warning("Unknown RISK_AI_PROVIDER=%s; defaulting to openai", candidate)
        return AIProvider.OPENAI


class RiskContext(BaseModel):
    """Snapshot of the current risk posture that feeds into the AI prompt."""

    reference_time: datetime
    max_position_size_pct: float
    max_concurrent_positions: int
    daily_loss_limit: float
    max_drawdown_pct: float
    max_risk_score: float
    current_risk_score: float
    open_positions: int
    recent_trades_analyzed: int
    win_rate: float
    losing_trade_pct: float
    avg_trade_pnl: float
    daily_loss: float
    recent_drawdown_pct: float


class RiskAdjustment(BaseModel):
    """Individual parameter change recommendation."""

    parameter: str
    current_value: float
    recommended_value: float
    rationale: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class RiskRecommendation(BaseModel):
    """Structured recommendation stored on the risk settings record."""

    summary: str
    timestamp: datetime
    adjustments: List[RiskAdjustment]
    confidence: Optional[float]
    provider: str
    raw_response: str
    context: RiskContext


class RiskAIService:
    """Service that computes risk context, consults AI, and persists suggested adjustments."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_provider: Optional[AIProvider] = None,
    ) -> None:
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._default_provider = default_provider or _env_provider()
        self._openai_model = os.getenv("RISK_AI_OPENAI_MODEL", "gpt-4o-mini")
        self._claude_model = os.getenv("RISK_AI_CLAUDE_MODEL", "claude-3.5-sonic")

        if self._openai_api_key:
            openai.api_key = self._openai_api_key

        self._anthropic_client = (
            Anthropic(api_key=self._anthropic_api_key)
            if self._anthropic_api_key
            else None
        )

    async def recommend_adjustments(self, db: Session) -> RiskRecommendation:
        """Generate a new recommendation and save it to the risk_settings record."""

        context = self._build_context(db)
        try:
            provider = self._select_provider()
            raw_response = await self._call_provider(provider, context)
            recommendation = self._build_recommendation_from_response(
                raw_response, provider, context
            )
        except RuntimeError as exc:
            logger.info("Risk AI provider unavailable (%s); falling back to heuristics", exc)
            recommendation = self._build_heuristic_recommendation(context)
        except Exception as exc:
            logger.exception("Risk AI recommendation failed, using heuristics: %s", exc)
            recommendation = self._build_heuristic_recommendation(context)

        self._persist_recommendation(db, recommendation)
        return recommendation

    def _select_provider(self, candidate: Optional[AIProvider] = None) -> AIProvider:
        """Choose an available AI provider."""

        preferred = candidate or self._default_provider
        if preferred and self._is_provider_available(preferred):
            return preferred

        for provider in AIProvider:
            if self._is_provider_available(provider):
                return provider

        raise RuntimeError("No AI provider configured for risk recommendations")

    def _is_provider_available(self, provider: AIProvider) -> bool:
        if provider == AIProvider.OPENAI:
            return bool(self._openai_api_key)
        if provider == AIProvider.CLAUDE:
            return bool(self._anthropic_api_key and self._anthropic_client)
        return False

    async def _call_provider(self, provider: AIProvider, context: RiskContext) -> str:
        if provider == AIProvider.OPENAI:
            return await self._call_openai(context)
        return await self._call_claude(context)

    async def _call_openai(self, context: RiskContext) -> str:
        if not self._openai_api_key:
            raise RuntimeError("OpenAI API key is not configured for risk recommendations")

        system_prompt = (
            "You are CryptoTrader's risk intelligence agent. "
            "Analyze the provided risk context and suggest actionable adjustments."
        )
        user_prompt = self._build_prompt(context)

        try:
            completion = await openai.ChatCompletion.acreate(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.25,
                max_tokens=600,
            )
            return completion.choices[0].message.content.strip()
        except Exception as exc:
            logger.exception("OpenAI risk call failed: %s", exc)
            raise

    async def _call_claude(self, context: RiskContext) -> str:
        if not self._anthropic_client:
            raise RuntimeError("Anthropic/Claude client is not configured")

        prompt = f"{HUMAN_PROMPT}{self._build_prompt(context)}{AI_PROMPT}"
        try:
            response = await asyncio.to_thread(
                self._anthropic_client.completions.create,
                model=self._claude_model,
                prompt=prompt,
                max_tokens_to_sample=600,
                temperature=0.25,
            )
            return response.completion.strip()
        except Exception as exc:
            logger.exception("Claude risk call failed: %s", exc)
            raise

    def _build_prompt(self, context: RiskContext) -> str:
        context_json = json.dumps(context.model_dump(), default=str, indent=2)
        lines = [
            "Context:\n",
            context_json,
            "\nReturn a JSON object with the following keys:",
            "summary (string),",
            "confidence (number between 0 and 1),",
            "adjustments (array) where each entry includes parameter, current_value, recommended_value, rationale (optional), confidence (optional).",
            "Only include the JSON payload; do not wrap it in markdown fences.",
        ]
        return "\n".join(lines)

    def _build_recommendation_from_response(
        self, raw_response: str, provider: AIProvider, context: RiskContext
    ) -> RiskRecommendation:
        payload = self._extract_json(raw_response)
        if not payload:
            raise ValueError("AI response did not contain valid JSON payload")

        adjustments = []
        current_values = self._current_value_lookup(context)
        for candidate in payload.get("adjustments", []):
            parameter = candidate.get("parameter") or candidate.get("field")
            if not parameter:
                continue
            current = self._safe_float(candidate.get("current_value"))
            if current is None:
                current = current_values.get(parameter)
            recommended = self._safe_float(candidate.get("recommended_value"))
            if recommended is None:
                continue
            rationale = candidate.get("rationale") or candidate.get("reason")
            confidence = self._safe_float(candidate.get("confidence"))
            adjustments.append(
                RiskAdjustment(
                    parameter=parameter,
                    current_value=current,
                    recommended_value=recommended,
                    rationale=rationale,
                    confidence=confidence,
                )
            )

        if not adjustments:
            raise ValueError("AI response did not include valid adjustments")

        summary = payload.get("summary") or payload.get("description") or "AI-generated risk adjustments"
        confidence = self._safe_float(payload.get("confidence"))

        return RiskRecommendation(
            summary=summary,
            timestamp=datetime.utcnow(),
            adjustments=adjustments,
            confidence=confidence,
            provider=provider.value,
            raw_response=raw_response,
            context=context,
        )

    def _extract_json(self, raw_response: str) -> Optional[Dict[str, Any]]:
        trimmed = raw_response.strip()
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            pass

        for match in re.finditer(r"\{.*\}", raw_response, flags=re.DOTALL):
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    def _current_value_lookup(self, context: RiskContext) -> Dict[str, float]:
        return {
            "max_position_size_pct": context.max_position_size_pct,
            "max_concurrent_positions": float(context.max_concurrent_positions),
            "daily_loss_limit": context.daily_loss_limit,
            "max_drawdown_pct": context.max_drawdown_pct,
            "max_risk_score": context.max_risk_score,
        }

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_heuristic_recommendation(self, context: RiskContext) -> RiskRecommendation:
        adjustments: List[RiskAdjustment] = []
        suggestions: Dict[str, float] = {}

        if context.daily_loss >= context.daily_loss_limit * 0.6:
            suggestions["max_position_size_pct"] = max(0.5, context.max_position_size_pct * 0.85)
            suggestions["max_concurrent_positions"] = max(1, context.max_concurrent_positions - 1)
        elif context.win_rate >= 0.6 and context.current_risk_score <= context.max_risk_score * 0.5:
            suggestions["max_position_size_pct"] = min(context.max_position_size_pct * 1.1, 20.0)
            suggestions["max_concurrent_positions"] = context.max_concurrent_positions + 1

        if context.current_risk_score >= context.max_risk_score * 0.9:
            suggestions["max_position_size_pct"] = min(
                suggestions.get("max_position_size_pct", context.max_position_size_pct) * 0.9,
                context.max_position_size_pct,
            )

        if not suggestions:
            suggestions["max_position_size_pct"] = min(context.max_position_size_pct * 1.05, 20.0)

        for parameter, suggested in suggestions.items():
            current = self._current_value_lookup(context).get(parameter)
            if current is None:
                continue
            if abs(suggested - current) < 0.01:
                continue
            rationale = "Heuristic adjustment based on recent risk posture."
            adjustments.append(
                RiskAdjustment(
                    parameter=parameter,
                    current_value=current,
                    recommended_value=suggested,
                    rationale=rationale,
                    confidence=HEURISTIC_CONFIDENCE,
                )
            )

        if not adjustments:
            adjustments.append(
                RiskAdjustment(
                    parameter="max_position_size_pct",
                    current_value=context.max_position_size_pct,
                    recommended_value=context.max_position_size_pct,
                    rationale="No change needed at this time.",
                    confidence=HEURISTIC_CONFIDENCE,
                )
            )

        return RiskRecommendation(
            summary="Fallback heuristic risk recommendation",
            timestamp=datetime.utcnow(),
            adjustments=adjustments,
            confidence=HEURISTIC_CONFIDENCE,
            provider="heuristic",
            raw_response="",
            context=context,
        )

    def _persist_recommendation(self, db: Session, recommendation: RiskRecommendation) -> None:
        settings = self._ensure_risk_settings(db)
        settings.last_ai_recommendation_json = recommendation.model_dump()
        settings.pending_ai_adjustment = True
        db.add(settings)
        db.commit()
        db.refresh(settings)

    def _build_context(self, db: Session) -> RiskContext:
        settings = self._ensure_risk_settings(db)
        now = datetime.utcnow()
        recent_window = now - RECENT_TRADE_WINDOW

        open_positions = db.query(Trade).filter(Trade.exit_time.is_(None)).count()
        recent_trades = (
            db.query(Trade)
            .filter(Trade.entry_time.is_not(None))
            .filter(Trade.entry_time >= recent_window)
            .order_by(Trade.entry_time.desc())
            .limit(RECENT_TRADE_LIMIT)
            .all()
        )

        total_trades = len(recent_trades)
        wins = sum(1 for trade in recent_trades if trade.pnl and trade.pnl > 0)
        losses = sum(1 for trade in recent_trades if trade.pnl and trade.pnl < 0)
        win_rate = wins / total_trades if total_trades else 0.0
        losing_pct = losses / total_trades if total_trades else 0.0
        trade_pnls = [float(trade.pnl) for trade in recent_trades if trade.pnl is not None]
        avg_pnl = sum(trade_pnls) / len(trade_pnls) if trade_pnls else 0.0
        daily_loss = sum(-float(trade.pnl) for trade in recent_trades if trade.pnl and trade.pnl < 0)

        recent_drawdown_entry = (
            db.query(StrategyPerformance)
            .filter(StrategyPerformance.period_end >= recent_window)
            .order_by(StrategyPerformance.max_drawdown.desc())
            .first()
        )
        recent_drawdown_pct = (
            float(recent_drawdown_entry.max_drawdown)
            if recent_drawdown_entry and recent_drawdown_entry.max_drawdown
            else 0.0
        )

        return RiskContext(
            reference_time=now,
            max_position_size_pct=float(settings.max_position_size_pct or 0.0),
            max_concurrent_positions=int(settings.max_concurrent_positions or 0),
            daily_loss_limit=float(settings.daily_loss_limit or 0.0),
            max_drawdown_pct=float(settings.max_drawdown_pct or 0.0),
            max_risk_score=float(settings.max_risk_score or 0.0),
            current_risk_score=float(settings.current_risk_score or 0.0),
            open_positions=open_positions,
            recent_trades_analyzed=total_trades,
            win_rate=win_rate,
            losing_trade_pct=losing_pct,
            avg_trade_pnl=avg_pnl,
            daily_loss=daily_loss,
            recent_drawdown_pct=recent_drawdown_pct,
        )

    def _ensure_risk_settings(self, db: Session) -> RiskSettings:
        settings = db.query(RiskSettings).order_by(RiskSettings.updated_at.desc()).first()
        if settings:
            return settings

        settings = RiskSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings
