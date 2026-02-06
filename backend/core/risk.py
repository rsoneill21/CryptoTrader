"""Core risk validation service for trade requests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import RiskException
from core.trading_control import trading_control
from db.models import PaperTradingState, RiskSettings, Trade


DEFAULT_ACCOUNT_BALANCE = 100_000.0


class RiskService:
    """Single source of truth for risk checks before trade execution."""

    @staticmethod
    async def get_settings(db: AsyncSession) -> RiskSettings:
        query = select(RiskSettings).order_by(RiskSettings.updated_at.desc()).limit(1)
        result = await db.execute(query)
        settings = result.scalars().first()
        if settings is not None:
            return settings

        settings = RiskSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        return settings

    @staticmethod
    async def _account_balance(db: AsyncSession) -> float:
        query = (
            select(PaperTradingState.state_json)
            .where(PaperTradingState.is_active.is_(True))
            .order_by(PaperTradingState.updated_at.desc())
            .limit(1)
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()
        if not isinstance(state, dict):
            return DEFAULT_ACCOUNT_BALANCE

        cash = float(state.get("cash") or 0.0)
        realized_pnl = float(state.get("realized_pnl") or 0.0)
        unrealized_pnl = float(state.get("unrealized_pnl") or 0.0)
        equity = cash + realized_pnl + unrealized_pnl
        if equity <= 0:
            starting_cash = float(state.get("starting_cash") or DEFAULT_ACCOUNT_BALANCE)
            return max(starting_cash, 0.0)
        return equity

    @classmethod
    async def validate_trade(
        cls,
        db: AsyncSession,
        symbol: str,
        quantity: float,
        price: float,
        side: str,
    ) -> None:
        if trading_control.is_paused():
            pause_status = trading_control.status()
            raise RiskException(
                "Trading is currently paused",
                details={"reason": pause_status.reason, "triggered_by": pause_status.triggered_by},
            )

        settings = await cls.get_settings(db)
        trade_value = abs(float(quantity) * float(price))

        balance = await cls._account_balance(db)
        max_position_value = balance * (float(settings.max_position_size_pct or 0.0) / 100.0)
        if max_position_value > 0 and trade_value > max_position_value:
            raise RiskException(
                "Trade exceeds maximum position size",
                details={
                    "symbol": symbol,
                    "side": side,
                    "trade_value": trade_value,
                    "max_position_value": max_position_value,
                    "account_balance": balance,
                },
            )

        open_positions_query = select(func.count(Trade.id)).where(Trade.exit_time.is_(None))
        open_positions_result = await db.execute(open_positions_query)
        open_positions = int(open_positions_result.scalar_one() or 0)
        max_positions = int(settings.max_concurrent_positions or 0)
        if max_positions > 0 and open_positions >= max_positions:
            raise RiskException(
                "Maximum concurrent positions reached",
                details={
                    "open_positions": open_positions,
                    "max_concurrent_positions": max_positions,
                },
            )

        now = datetime.utcnow()
        hour_start = now - timedelta(hours=1)
        day_start = now - timedelta(days=1)

        trades_hour_query = select(func.count(Trade.id)).where(Trade.entry_time >= hour_start)
        trades_hour_result = await db.execute(trades_hour_query)
        trades_last_hour = int(trades_hour_result.scalar_one() or 0)

        hour_limit = int(settings.max_trades_per_hour or 0)
        if hour_limit > 0 and trades_last_hour >= hour_limit:
            raise RiskException(
                "Hourly trade frequency limit reached",
                details={"trades_last_hour": trades_last_hour, "max_trades_per_hour": hour_limit},
            )

        trades_day_query = select(func.count(Trade.id)).where(Trade.entry_time >= day_start)
        trades_day_result = await db.execute(trades_day_query)
        trades_last_day = int(trades_day_result.scalar_one() or 0)

        day_limit = int(settings.max_trades_per_day or 0)
        if day_limit > 0 and trades_last_day >= day_limit:
            raise RiskException(
                "Daily trade frequency limit reached",
                details={"trades_last_day": trades_last_day, "max_trades_per_day": day_limit},
            )

        current_exposure_query = select(
            func.coalesce(
                func.sum(func.abs(func.coalesce(Trade.quantity, 0.0) * func.coalesce(Trade.entry_price, 0.0))),
                0.0,
            )
        ).where(Trade.symbol == symbol, Trade.exit_time.is_(None))
        current_exposure_result = await db.execute(current_exposure_query)
        current_exposure = float(current_exposure_result.scalar_one() or 0.0)

        projected_exposure = current_exposure + trade_value
        max_asset_exposure = float(settings.max_asset_exposure or 0.0)
        if max_asset_exposure > 0 and projected_exposure > max_asset_exposure:
            raise RiskException(
                "Asset exposure limit exceeded",
                details={
                    "symbol": symbol,
                    "current_exposure": current_exposure,
                    "projected_exposure": projected_exposure,
                    "max_asset_exposure": max_asset_exposure,
                },
            )
