"""Chat context assembly service for trading-grounded responses."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RiskSettings, Trade
from services.portfolio import PortfolioSnapshot, portfolio_service

PORTFOLIO_TOP_HOLDINGS = 5
POSITION_TOP_COUNT = 3

_PERFORMANCE_KEYWORDS = (
    "performance",
    "p&l",
    "pnl",
    "how am i doing",
    "profit",
    "loss",
    "drawdown",
    "return",
)
_WEEK_KEYWORDS = ("week", "7d", "seven day")


class ChatContextAssembler:
    """Builds normalized trading context for chat policy and rendering."""

    def __init__(
        self,
        portfolio_fetcher: Optional[Callable[[], Awaitable[PortfolioSnapshot]]] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._portfolio_fetcher = portfolio_fetcher or portfolio_service.get_snapshot
        self._now_provider = now_provider or datetime.utcnow

    async def build(
        self,
        *,
        db: AsyncSession,
        prompt: str,
        context_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = self._now_provider()
        timeframe_used = self.classify_timeframe(prompt)
        context_json = context_json or {}

        active_positions = await self._load_active_positions(db)
        portfolio_summary, portfolio_flags = await self._load_portfolio_summary(now)
        risk_summary, risk_flags = await self._load_risk_summary(db)
        baseline = await self._load_baseline_comparison(db, now, timeframe_used)
        why_trade = await self._load_why_trade_context(db, prompt, context_json)

        missing_fields: List[str] = []
        refusal_reasons: List[str] = []
        missing_fields.extend(portfolio_flags["missing_fields"])
        missing_fields.extend(risk_flags["missing_fields"])
        missing_fields.extend(why_trade["missing_fields"])
        refusal_reasons.extend(portfolio_flags["refusal_reasons"])
        refusal_reasons.extend(risk_flags["refusal_reasons"])
        refusal_reasons.extend(why_trade["refusal_reasons"])

        stale_context = any((portfolio_flags["stale_context"], risk_flags["stale_context"]))
        incomplete_context = bool(why_trade["incomplete_context"]) or bool(missing_fields)

        return {
            "timeframe_used": timeframe_used,
            "portfolio_summary": portfolio_summary,
            "top_positions": active_positions[:POSITION_TOP_COUNT],
            "baseline_comparison": baseline,
            "risk_snapshot": risk_summary,
            "trade_context": why_trade["trade_context"],
            "stale_context": stale_context,
            "incomplete_context": incomplete_context,
            "missing_fields": sorted(set(missing_fields)),
            "refusal_reasons": sorted(set(refusal_reasons)),
        }

    def classify_timeframe(self, prompt: str) -> str:
        normalized = prompt.lower()
        if any(token in normalized for token in _WEEK_KEYWORDS):
            return "7d"
        if any(token in normalized for token in _PERFORMANCE_KEYWORDS):
            return "24h"
        return "session"

    async def _load_active_positions(self, db: AsyncSession) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Trade)
            .where(Trade.exit_time.is_(None), Trade.entry_time.is_not(None))
            .order_by(Trade.entry_time.desc())
        )
        active = list(result.scalars().all())

        positions: List[Dict[str, Any]] = []
        for trade in active:
            quantity = float(trade.quantity or 0.0)
            entry_price = float(trade.entry_price or 0.0)
            notional = abs(quantity * entry_price)
            positions.append(
                {
                    "trade_id": trade.id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "quantity": quantity,
                    "entry_price": float(trade.entry_price) if trade.entry_price is not None else None,
                    "notional": notional,
                    "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                }
            )

        return sorted(positions, key=lambda row: row["notional"], reverse=True)

    async def _load_portfolio_summary(self, now: datetime) -> tuple[Dict[str, Any], Dict[str, Any]]:
        summary: Dict[str, Any] = {
            "fetched_at": None,
            "expires_at": None,
            "ttl_seconds": None,
            "source": None,
            "holdings_count": 0,
            "top_holdings": [],
        }
        flags = {
            "stale_context": False,
            "missing_fields": [],
            "refusal_reasons": [],
        }

        snapshot = await self._portfolio_fetcher()
        summary["fetched_at"] = snapshot.fetched_at.isoformat() if snapshot.fetched_at else None
        summary["expires_at"] = snapshot.expires_at.isoformat() if snapshot.expires_at else None
        summary["ttl_seconds"] = snapshot.ttl_seconds
        summary["source"] = snapshot.source
        summary["holdings_count"] = len(snapshot.holdings)
        summary["top_holdings"] = self._top_holdings(snapshot.holdings)

        if snapshot.fetched_at is None:
            flags["stale_context"] = True
            flags["missing_fields"].append("portfolio.fetched_at")
            flags["refusal_reasons"].append("missing_portfolio_snapshot_timestamp")

        if snapshot.expires_at is None:
            flags["stale_context"] = True
            flags["missing_fields"].append("portfolio.expires_at")
            flags["refusal_reasons"].append("missing_portfolio_expiry")
        elif snapshot.expires_at <= now:
            flags["stale_context"] = True
            flags["refusal_reasons"].append("expired_portfolio_snapshot")

        return summary, flags

    async def _load_risk_summary(self, db: AsyncSession) -> tuple[Dict[str, Any], Dict[str, Any]]:
        result = await db.execute(select(RiskSettings).order_by(RiskSettings.updated_at.desc()).limit(1))
        settings = result.scalars().first()
        flags = {
            "stale_context": False,
            "missing_fields": [],
            "refusal_reasons": [],
        }

        if settings is None:
            flags["stale_context"] = True
            flags["missing_fields"].append("risk.updated_at")
            flags["refusal_reasons"].append("missing_risk_reference_timestamp")
            return {
                "current_risk_score": None,
                "max_risk_score": None,
                "risk_ratio": None,
                "status": "unknown",
                "reference_time": None,
            }, flags

        max_score = float(settings.max_risk_score or 0.0)
        current_score = float(settings.current_risk_score or 0.0)
        ratio = (current_score / max_score) if max_score > 0 else 0.0
        status = "alert" if max_score > 0 and current_score >= max_score else "ok"
        if settings.updated_at is None:
            flags["stale_context"] = True
            flags["missing_fields"].append("risk.updated_at")
            flags["refusal_reasons"].append("missing_risk_reference_timestamp")

        return {
            "current_risk_score": current_score,
            "max_risk_score": max_score,
            "risk_ratio": ratio,
            "status": status,
            "reference_time": settings.updated_at.isoformat() if settings.updated_at else None,
        }, flags

    async def _load_baseline_comparison(self, db: AsyncSession, now: datetime, timeframe_used: str) -> Dict[str, Any]:
        if timeframe_used == "7d":
            window = timedelta(days=7)
            baseline_label = "prior_7d"
        elif timeframe_used == "24h":
            window = timedelta(hours=24)
            baseline_label = "prior_day"
        else:
            session_start = datetime(now.year, now.month, now.day)
            window = now - session_start if now > session_start else timedelta(hours=1)
            baseline_label = "prior_session"

        current_start = now - window
        baseline_start = current_start - window

        current_pnl = await self._sum_realized_pnl(db, current_start, now)
        baseline_pnl = await self._sum_realized_pnl(db, baseline_start, current_start)
        delta = current_pnl - baseline_pnl

        return {
            "window": timeframe_used,
            "baseline": baseline_label,
            "current_realized_pnl": current_pnl,
            "baseline_realized_pnl": baseline_pnl,
            "delta_realized_pnl": delta,
        }

    async def _sum_realized_pnl(self, db: AsyncSession, start: datetime, end: datetime) -> float:
        stmt = (
            select(func.coalesce(func.sum(Trade.pnl), 0.0))
            .where(Trade.exit_time.is_not(None), Trade.exit_time >= start, Trade.exit_time < end)
        )
        result = await db.execute(stmt)
        return float(result.scalar_one() or 0.0)

    async def _load_why_trade_context(
        self,
        db: AsyncSession,
        prompt: str,
        context_json: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = prompt.lower()
        result = {
            "trade_context": None,
            "incomplete_context": False,
            "missing_fields": [],
            "refusal_reasons": [],
        }

        if "why" not in normalized or "trade" not in normalized:
            return result

        trade_id = self._extract_trade_id(prompt, context_json)
        if trade_id is None:
            result["incomplete_context"] = True
            result["missing_fields"].append("trade_id")
            result["refusal_reasons"].append("missing_trade_rationale_context")
            return result

        trade = await db.get(Trade, trade_id)
        if trade is None:
            result["incomplete_context"] = True
            result["missing_fields"].append("trade_context")
            result["refusal_reasons"].append("missing_trade_rationale_context")
            return result

        if not any((trade.entry_reasoning_json, trade.exit_reasoning_json, trade.indicators_json)):
            result["incomplete_context"] = True
            result["missing_fields"].append("trade_context.rationale")
            result["refusal_reasons"].append("missing_trade_rationale_context")
            return result

        result["trade_context"] = {
            "trade_id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side,
            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "entry_reasoning": trade.entry_reasoning_json,
            "exit_reasoning": trade.exit_reasoning_json,
            "indicators": trade.indicators_json,
        }
        return result

    def _extract_trade_id(self, prompt: str, context_json: Dict[str, Any]) -> Optional[int]:
        context_trade_id = context_json.get("trade_id")
        if isinstance(context_trade_id, int):
            return context_trade_id

        match = re.search(r"trade\s*#?\s*(\d+)", prompt.lower())
        if match:
            return int(match.group(1))
        return None

    def _top_holdings(self, holdings: List[Any]) -> List[Dict[str, Any]]:
        ranked = sorted(holdings, key=lambda h: Decimal(str(h.total)), reverse=True)
        payload: List[Dict[str, Any]] = []
        for row in ranked[:PORTFOLIO_TOP_HOLDINGS]:
            payload.append(
                {
                    "asset": row.asset,
                    "total": float(row.total),
                    "available": float(row.available),
                    "reserved": float(row.reserved),
                }
            )
        return payload
