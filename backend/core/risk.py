"""Core risk validation service for trade requests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import RiskException
from core.trading_control import trading_control
from db.models import MarketData, PaperTradingState, RiskSettings, Trade
from services.kraken import KrakenAPIError, kraken_service


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
    async def account_equity(cls, db: AsyncSession) -> float:
        """Return the current account equity used for risk sizing decisions."""

        return await cls._account_balance(db)

    @classmethod
    async def quantity_from_risk_percent(
        cls,
        db: AsyncSession,
        *,
        risk_percent: float,
        reference_price: float,
    ) -> float:
        """Derive order quantity from account equity and a percent risk budget."""

        percent = float(risk_percent)
        price = float(reference_price)

        if percent <= 0 or percent > 100:
            raise RiskException(
                "risk_percent must be between 1 and 100",
                details={"risk_percent": percent},
            )

        if price <= 0:
            raise RiskException(
                "reference_price must be greater than zero",
                details={"reference_price": price},
            )

        equity = await cls.account_equity(db)
        risk_notional = equity * (percent / 100.0)
        quantity = risk_notional / price

        if quantity <= 0:
            raise RiskException(
                "Calculated order quantity must be greater than zero",
                details={
                    "account_equity": equity,
                    "risk_percent": percent,
                    "reference_price": price,
                },
            )

        return quantity

    @classmethod
    async def check_daily_halt(cls, db: AsyncSession) -> bool:
        """Pause trading when total daily P&L breaches the configured loss limit."""

        settings = await cls.get_settings(db)
        daily_loss_limit = float(settings.daily_loss_limit or 0.0)
        if daily_loss_limit <= 0:
            return False

        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = day_start + timedelta(days=1)

        realized_result = await db.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                Trade.exit_time.is_not(None),
                Trade.exit_time >= day_start,
                Trade.exit_time < next_day,
            )
        )
        realized_pnl = float(realized_result.scalar_one() or 0.0)

        open_positions_result = await db.execute(
            select(Trade.symbol, Trade.side, Trade.quantity, Trade.entry_price).where(
                Trade.exit_time.is_(None)
            )
        )
        open_positions = list(open_positions_result.all())

        latest_prices: dict[str, float] = {}
        for symbol, _, _, _ in open_positions:
            normalized_symbol = (symbol or "").strip().upper()
            if not normalized_symbol or normalized_symbol in latest_prices:
                continue

            market_result = await db.execute(
                select(MarketData.close)
                .where(MarketData.symbol == normalized_symbol)
                .order_by(MarketData.timestamp.desc())
                .limit(1)
            )
            latest_close = market_result.scalar_one_or_none()
            if latest_close is not None:
                latest_prices[normalized_symbol] = float(latest_close)

        unrealized_pnl = 0.0
        for symbol, side, quantity, entry_price in open_positions:
            if entry_price is None or quantity is None:
                continue

            normalized_symbol = (symbol or "").strip().upper()
            market_price = latest_prices.get(normalized_symbol, float(entry_price))
            side_multiplier = 1.0 if str(side).lower() == "buy" else -1.0
            unrealized_pnl += (market_price - float(entry_price)) * float(quantity) * side_multiplier

        total_daily_pnl = realized_pnl + unrealized_pnl
        if total_daily_pnl <= -daily_loss_limit:
            reason = "Daily loss limit reached (including unrealized)"
            trading_control.pause_trading(
                reason=reason,
                triggered_by="risk_service",
                lock_until_next_day=True,
            )
            return True

        return False

    @classmethod
    async def validate_trade(
        cls,
        db: AsyncSession,
        symbol: str,
        quantity: float,
        price: float,
        side: str,
    ) -> None:
        await cls.check_daily_halt(db)

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

        await cls.check_liquidity(
            db=db,
            symbol=symbol,
            quantity=quantity,
            side=side,
            settings=settings,
        )

    @classmethod
    async def validate_close(
        cls,
        db: AsyncSession,
        *,
        symbol: str,
        quantity: float,
        price: float,
        side: str,
    ) -> None:
        """Validate close intent through centralized risk controls."""

        await cls.check_daily_halt(db)

        if trading_control.is_paused():
            pause_status = trading_control.status()
            raise RiskException(
                "Trading is currently paused",
                details={"reason": pause_status.reason, "triggered_by": pause_status.triggered_by},
            )

        await cls.check_liquidity(
            db=db,
            symbol=symbol,
            quantity=quantity,
            side=side,
        )

    @classmethod
    async def check_liquidity(
        cls,
        db: AsyncSession,
        symbol: str,
        quantity: float,
        side: str,
        settings: Optional[RiskSettings] = None,
    ) -> None:
        requested_quantity = abs(float(quantity))
        if requested_quantity <= 0:
            return

        risk_settings = settings or await cls.get_settings(db)
        max_slippage_pct = max(float(risk_settings.min_liquidity_threshold or 0.0), 0.0)

        try:
            orderbook = await kraken_service.get_orderbook(symbol, count=100)
        except KrakenAPIError as exc:
            raise RiskException(
                "Unable to validate market liquidity",
                details={"symbol": symbol, "side": side, "reason": str(exc)},
            ) from exc

        side_normalized = str(side).lower()
        levels = orderbook.get("asks", []) if side_normalized == "buy" else orderbook.get("bids", [])
        if not levels:
            raise RiskException(
                "No order book liquidity available",
                details={"symbol": symbol, "side": side, "requested_quantity": requested_quantity},
            )

        remaining = requested_quantity
        notional = 0.0
        filled_quantity = 0.0

        for level in levels:
            level_volume = float(level.get("volume", 0.0) or 0.0)
            level_price = float(level.get("price", 0.0) or 0.0)
            if level_volume <= 0 or level_price <= 0:
                continue

            fill = min(level_volume, remaining)
            remaining -= fill
            filled_quantity += fill
            notional += fill * level_price
            if remaining <= 0:
                break

        if filled_quantity < requested_quantity:
            raise RiskException(
                "Insufficient order book depth",
                details={
                    "symbol": symbol,
                    "side": side,
                    "requested_quantity": requested_quantity,
                    "available_quantity": filled_quantity,
                },
            )

        best_price = float(levels[0].get("price", 0.0) or 0.0)
        if best_price <= 0:
            raise RiskException(
                "Invalid top-of-book price",
                details={"symbol": symbol, "side": side},
            )

        average_fill_price = notional / filled_quantity
        slippage_pct = abs((average_fill_price - best_price) / best_price) * 100.0

        if max_slippage_pct > 0 and slippage_pct > max_slippage_pct:
            raise RiskException(
                "Liquidity slippage exceeds threshold",
                details={
                    "symbol": symbol,
                    "side": side,
                    "requested_quantity": requested_quantity,
                    "average_fill_price": average_fill_price,
                    "best_price": best_price,
                    "slippage_pct": slippage_pct,
                    "max_slippage_pct": max_slippage_pct,
                },
            )
