"""
Order management API routes.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import get_current_user
from core.indicators import side_color
from db.database import get_async_db
from db.models import Order, Trade, User
from backend.api.market import DecisionRecord, fetch_decisions_for_trade
from backend.agents.market_analyst import market_analyst_agent
from services.market_data import market_data_service
from services.kraken import kraken_service, KrakenAPIError

logger = logging.getLogger("cryptotrader.trades")
router = APIRouter()


class OrderSummary(BaseModel):
    """Serialized order metadata returned with active trades."""

    id: int
    order_type: str
    side: str
    status: str
    price: Optional[float]
    quantity: float
    filled_quantity: float
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]
    side_color: str


class ActiveTradeResponse(BaseModel):
    """Minimal view of an active trade for the dashboard."""

    id: int
    strategy_id: Optional[int]
    symbol: str
    side: str
    entry_price: Optional[float]
    quantity: float
    entry_time: Optional[datetime]
    is_paper: bool
    is_manual: bool
    ai_model_used: Optional[str]
    trade_source: str
    current_price: Optional[float]
    unrealized_pnl: Optional[float]
    pnl: Optional[float]
    market_conditions: Optional[Dict[str, Any]]
    ai_managed: bool
    orders: List[OrderSummary]
    side_color: str


class CloseTradeRequest(BaseModel):
    """Payload used to mark a trade as closed."""

    exit_price: float = Field(..., gt=0.0, description="Execution price for the exit leg")
    reason: Optional[str] = Field(None, max_length=512)


class CloseTradeResponse(BaseModel):
    """Confirmation returned after closing a trade."""

    trade_id: int
    exit_time: datetime
    exit_price: float
    pnl: Optional[float]
    message: str


class CreateTradeRequest(BaseModel):
    """Payload for creating a manual trade."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USD)")
    side: str = Field(..., pattern="^(buy|sell)$", description="Order side")
    quantity: float = Field(..., gt=0)
    is_paper: bool = True


class CreateSystemTradeRequest(BaseModel):
    """Payload for creating an AI/system-originated trade."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USD)")
    side: str = Field(..., pattern="^(buy|sell)$", description="Order side")
    quantity: float = Field(..., gt=0)
    entry_price: Optional[float] = Field(None, gt=0)
    is_paper: bool = True
    strategy_id: Optional[int] = None
    ai_model_used: Optional[str] = None
    entry_reasoning: Optional[Dict[str, Any]] = None
    indicators: Optional[Dict[str, Any]] = None


class TradeCandle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    timeframe: str

    model_config = ConfigDict(from_attributes=True)


class TradeReasoningResponse(BaseModel):
    """Detailed explanation describing why a trade was placed."""

    trade_id: int
    symbol: str
    side: str
    strategy_id: Optional[int]
    entry_time: Optional[datetime]
    exit_time: Optional[datetime]
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: float
    is_paper: bool
    is_manual: bool
    entry_reasoning: Optional[Dict[str, Any]]
    exit_reasoning: Optional[Dict[str, Any]]
    market_conditions: Optional[Dict[str, Any]]
    indicators: Optional[Dict[str, Any]]
    ai_decisions: List[DecisionRecord] = Field(default_factory=list)
    recent_candles: List[TradeCandle] = Field(default_factory=list)
    analyst_insights: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/",
    response_model=ActiveTradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_trade(
    request: CreateTradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ActiveTradeResponse:
    """Execute a manual trade and record it."""
    now = datetime.utcnow()

    trade = Trade(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        is_paper=request.is_paper,
        is_manual=True,
        entry_time=now,
        # In a real app, we'd fetch the current price from an exchange here
        # For now, we'll assume it's a market order that fills at some price
        # (Placeholder for real execution logic)
    )

    try:
        db.add(trade)
        await db.commit()
        await db.refresh(trade)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to create manual trade: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute trade",
        )

    logger.info("Manual trade created: id=%s, symbol=%s", trade.id, trade.symbol)
    return _serialize_trade(trade)


@router.post(
    "/system",
    response_model=ActiveTradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_system_trade(
    request: CreateSystemTradeRequest,
    db: AsyncSession = Depends(get_async_db),
) -> ActiveTradeResponse:
    """Record a trade originated by an AI agent or internal system process."""
    now = datetime.utcnow()

    trade = Trade(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        entry_price=request.entry_price,
        is_paper=request.is_paper,
        is_manual=False,
        strategy_id=request.strategy_id,
        ai_model_used=request.ai_model_used,
        entry_time=now,
        entry_reasoning_json=request.entry_reasoning,
        indicators_json=request.indicators,
    )

    try:
        db.add(trade)
        await db.commit()
        await db.refresh(trade)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to create system trade: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record system trade",
        )

    logger.info(
        "System trade created: id=%s, symbol=%s, ai_model=%s, is_manual=False",
        trade.id, trade.symbol, trade.ai_model_used,
    )
    return _serialize_trade(trade)


class AdjustTradeRequest(BaseModel):
    """Payload for adjusting stop-loss/take-profit levels."""

    stop_loss: Optional[float] = Field(None, gt=0.0)
    take_profit: Optional[float] = Field(None, gt=0.0)
    note: Optional[str] = Field(None, max_length=512)

    # Pydantic v2 migration: replaced @root_validator with @model_validator(mode='after')
    @model_validator(mode="after")
    def require_price_change(self) -> "AdjustTradeRequest":
        if self.stop_loss is None and self.take_profit is None:
            raise ValueError("At least one of stop_loss or take_profit must be provided")
        return self


def _build_order_summary(order: Order) -> OrderSummary:
    return OrderSummary(
        id=order.id,
        order_type=order.order_type,
        side=order.side,
        status=order.status,
        price=order.price,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        created_at=order.created_at,
        updated_at=order.updated_at,
        error_message=order.error_message,
        side_color=side_color(order.side),
    )


def _serialize_trade(
    trade: Trade, current_price: Optional[float] = None
) -> ActiveTradeResponse:
    if trade.is_manual:
        source = "manual"
    elif trade.ai_model_used:
        source = f"ai:{trade.ai_model_used}"
    else:
        source = "system"

    unrealized_pnl = None
    if current_price is not None and trade.entry_price is not None and trade.exit_time is None:
        side_multiplier = 1 if trade.side.lower() == "buy" else -1
        unrealized_pnl = (current_price - trade.entry_price) * trade.quantity * side_multiplier

    return ActiveTradeResponse(
        id=trade.id,
        strategy_id=trade.strategy_id,
        symbol=trade.symbol,
        side=trade.side,
        entry_price=trade.entry_price,
        quantity=trade.quantity,
        entry_time=trade.entry_time,
        is_paper=trade.is_paper,
        is_manual=trade.is_manual,
        ai_model_used=trade.ai_model_used,
        trade_source=source,
        current_price=current_price,
        unrealized_pnl=unrealized_pnl,
        pnl=trade.pnl,
        market_conditions=trade.market_conditions_json,
        ai_managed=bool(trade.ai_managed),
        orders=[_build_order_summary(order) for order in trade.orders],
        side_color=side_color(trade.side),
    )


def _calculate_pnl(trade: Trade, exit_price: float) -> Optional[float]:
    if trade.entry_price is None or trade.quantity is None:
        return None

    side_multiplier = 1 if trade.side.lower() == "buy" else -1
    return (exit_price - trade.entry_price) * trade.quantity * side_multiplier


@router.get(
    "/active",
    response_model=List[ActiveTradeResponse],
    status_code=status.HTTP_200_OK,
)
async def list_active_trades(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[ActiveTradeResponse]:
    """Return all trades that have not been exited yet, with live prices."""
    try:
        result = await db.execute(
            select(Trade)
            .options(selectinload(Trade.orders))
            .where(Trade.exit_time.is_(None))
            .order_by(Trade.entry_time.desc())
        )
        trades = result.scalars().all()
    except Exception as exc:  # pragma: no cover - DB should be reachable
        logger.error("Failed to fetch active trades: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve active trades",
        )

    # Fetch current prices for all unique symbols in active trades
    symbols = {trade.symbol for trade in trades}
    price_map: Dict[str, float] = {}
    for symbol in symbols:
        try:
            ticker = await kraken_service.get_ticker(symbol)
            price_map[symbol] = float(ticker.last)
        except Exception as exc:
            logger.debug("Unable to fetch price for %s: %s", symbol, exc)

    return [
        _serialize_trade(trade, current_price=price_map.get(trade.symbol))
        for trade in trades
    ]


@router.post(
    "/{trade_id}/close",
    response_model=CloseTradeResponse,
    status_code=status.HTTP_200_OK,
)
async def close_trade(
    trade_id: int,
    request: CloseTradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> CloseTradeResponse:
    """Mark a trade as closed and record exit pricing."""
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    if trade.exit_time is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trade is already closed",
        )

    now = datetime.utcnow()
    trade.exit_price = request.exit_price
    trade.exit_time = now
    pnl = _calculate_pnl(trade, request.exit_price)
    if pnl is not None:
        trade.pnl = pnl

    if request.reason:
        exit_reason = trade.exit_reasoning_json or {}
        if not isinstance(exit_reason, dict):
            exit_reason = {}
        exit_reason.update(
            {
                "note": request.reason,
                "updated_by": current_user.email,
                "updated_at": now.isoformat(),
            }
        )
        trade.exit_reasoning_json = exit_reason

    try:
        await db.commit()
        await db.refresh(trade)
    except Exception as exc:
        await db.rollback()
        logger.error("Unable to close trade %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close trade",
        )

    logger.info("Trade %s closed by user %s", trade_id, current_user.email)

    return CloseTradeResponse(
        trade_id=trade.id,
        exit_time=trade.exit_time,
        exit_price=trade.exit_price,
        pnl=trade.pnl,
        message="Trade closed successfully",
    )


class AdjustTradeResponse(BaseModel):
    """Response payload after recording an adjustment."""

    trade_id: int
    adjustments: Dict[str, Optional[float]]
    updated_at: datetime
    message: str


@router.put(
    "/{trade_id}/adjust",
    response_model=AdjustTradeResponse,
    status_code=status.HTTP_200_OK,
)
async def adjust_trade(
    trade_id: int,
    request: AdjustTradeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> AdjustTradeResponse:
    """Persist stop-loss / take-profit adjustments for an active trade."""
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    conditions = trade.market_conditions_json or {}
    if not isinstance(conditions, dict):
        conditions = {}

    adjustments = conditions.get("adjustments")
    if not isinstance(adjustments, list):
        adjustments = []

    now = datetime.utcnow()
    adjustment_entry: Dict[str, Optional[float]] = {
        "stop_loss": request.stop_loss,
        "take_profit": request.take_profit,
        "note": request.note,
        "updated_by": current_user.email,
        "updated_at": now.isoformat(),
    }
    adjustments.append(adjustment_entry)
    conditions["adjustments"] = adjustments
    trade.market_conditions_json = conditions

    try:
        await db.commit()
        await db.refresh(trade)
    except Exception as exc:
        await db.rollback()
        logger.error("Unable to record adjustment for trade %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist adjustment",
        )

    logger.info(
        "Adjustment recorded for trade %s by %s",
        trade_id,
        current_user.email,
    )

    return AdjustTradeResponse(
        trade_id=trade.id,
        adjustments=adjustment_entry,
        updated_at=now,
        message="Adjustment saved",
    )


@router.get(
    "/{trade_id}/reasoning",
    response_model=TradeReasoningResponse,
    status_code=status.HTTP_200_OK,
)
async def explain_trade_reasoning(
    trade_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> TradeReasoningResponse:
    """Return AI reasoning, context, and analyst insights for a specific trade."""
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    reference_time = trade.entry_time or trade.exit_time or datetime.utcnow()
    candles: List[Dict[str, Any]] = []
    try:
        candles = await market_data_service.fetch_recent_candles(
            trade.symbol,
            reference_time,
            lookback=20,
        )
    except Exception as exc:
        logger.warning("Unable to load candles for trade %s: %s", trade_id, exc)

    analyst_insights: List[Dict[str, Any]] = []
    try:
        analyst_insights = await market_analyst_agent.get_recent_insights(trade.symbol, limit=3)
    except Exception as exc:
        logger.warning("Analyst insights unavailable for %s: %s", trade.symbol, exc)

    decisions = await fetch_decisions_for_trade(db, trade_id)

    return TradeReasoningResponse(
        trade_id=trade.id,
        symbol=trade.symbol,
        side=trade.side,
        strategy_id=trade.strategy_id,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        quantity=trade.quantity,
        is_paper=trade.is_paper,
        is_manual=trade.is_manual,
        entry_reasoning=trade.entry_reasoning_json,
        exit_reasoning=trade.exit_reasoning_json,
        market_conditions=trade.market_conditions_json,
        indicators=trade.indicators_json,
        ai_decisions=decisions,
        recent_candles=[TradeCandle(**candle) for candle in candles],
        analyst_insights=analyst_insights,
    )


# ---------------------------------------------------------------------------
# AI-managed toggle
# ---------------------------------------------------------------------------

class AIToggleResponse(BaseModel):
    trade_id: int
    ai_managed: bool
    message: str


@router.put(
    "/{trade_id}/ai-toggle",
    response_model=AIToggleResponse,
    status_code=status.HTTP_200_OK,
)
async def toggle_ai_managed(
    trade_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> AIToggleResponse:
    """Toggle the ai_managed flag on a trade."""
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.exit_time is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trade is already closed")

    trade.ai_managed = not bool(trade.ai_managed)

    try:
        await db.commit()
        await db.refresh(trade)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to toggle ai_managed for trade %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update trade",
        )

    state = "enabled" if trade.ai_managed else "disabled"
    logger.info("AI management %s for trade %s by %s", state, trade_id, current_user.email)
    return AIToggleResponse(trade_id=trade.id, ai_managed=trade.ai_managed, message=f"AI management {state}")


# ---------------------------------------------------------------------------
# Add to position
# ---------------------------------------------------------------------------

class AddToPositionRequest(BaseModel):
    quantity: float = Field(..., gt=0, description="Additional quantity to add")


class AddToPositionResponse(BaseModel):
    trade_id: int
    new_quantity: float
    new_entry_price: Optional[float]
    message: str


@router.post(
    "/{trade_id}/add",
    response_model=AddToPositionResponse,
    status_code=status.HTTP_200_OK,
)
async def add_to_position(
    trade_id: int,
    request: AddToPositionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> AddToPositionResponse:
    """Add quantity to an existing position, recomputing the weighted-average entry price."""
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.exit_time is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trade is already closed")

    # Fetch current price for the new leg
    try:
        ticker = await kraken_service.get_ticker(trade.symbol)
        add_price = float(ticker.last)
    except Exception as exc:
        logger.warning("Unable to fetch live price for %s: %s", trade.symbol, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not fetch current price from exchange",
        )

    old_qty = trade.quantity or 0.0
    new_qty = old_qty + request.quantity

    # Weighted-average entry price
    if trade.entry_price is not None:
        trade.entry_price = (
            (trade.entry_price * old_qty) + (add_price * request.quantity)
        ) / new_qty
    else:
        trade.entry_price = add_price

    trade.quantity = new_qty

    try:
        await db.commit()
        await db.refresh(trade)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to add to position %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update position",
        )

    logger.info(
        "Added %.4f to trade %s (new qty=%.4f) by %s",
        request.quantity, trade_id, trade.quantity, current_user.email,
    )
    return AddToPositionResponse(
        trade_id=trade.id,
        new_quantity=trade.quantity,
        new_entry_price=trade.entry_price,
        message=f"Added {request.quantity} to position",
    )


# ---------------------------------------------------------------------------
# Order management
# ---------------------------------------------------------------------------

class OrderInfoResponse(BaseModel):
    id: int
    trade_id: Optional[int]
    exchange_order_id: Optional[str]
    status: str
    order_type: str
    side: str
    price: Optional[float]
    quantity: float
    filled_quantity: float
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str]


@router.get(
    "/{trade_id}/orders",
    response_model=List[OrderInfoResponse],
    status_code=status.HTTP_200_OK,
)
async def list_trade_orders(
    trade_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[OrderInfoResponse]:
    """Return orders for a trade, refreshing status from Kraken for open exchange orders."""
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")

    result = await db.execute(
        select(Order)
        .where(Order.trade_id == trade_id)
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    # Sync status from exchange for orders that have an exchange_order_id and aren't terminal
    terminal_statuses = {"closed", "canceled", "expired", "filled", "cancelled"}
    for order in orders:
        if order.exchange_order_id and order.status.lower() not in terminal_statuses:
            try:
                info = await kraken_service.get_order_status(order.exchange_order_id)
                order.status = info.status.value
                order.filled_quantity = float(info.filled_volume)
            except Exception as exc:
                logger.debug("Could not refresh order %s: %s", order.exchange_order_id, exc)

    try:
        await db.commit()
    except Exception:
        await db.rollback()

    return [
        OrderInfoResponse(
            id=o.id,
            trade_id=o.trade_id,
            exchange_order_id=o.exchange_order_id,
            status=o.status,
            order_type=o.order_type,
            side=o.side,
            price=o.price,
            quantity=o.quantity,
            filled_quantity=o.filled_quantity,
            created_at=o.created_at,
            updated_at=o.updated_at,
            error_message=o.error_message,
        )
        for o in orders
    ]


class CancelOrderResponse(BaseModel):
    order_id: int
    status: str
    message: str


@router.post(
    "/orders/{order_id}/cancel",
    response_model=CancelOrderResponse,
    status_code=status.HTTP_200_OK,
)
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> CancelOrderResponse:
    """Cancel an exchange order."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if not order.exchange_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has no exchange order ID — cannot cancel",
        )

    try:
        await kraken_service.cancel_order(order.exchange_order_id)
    except KrakenAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    order.status = "canceled"
    try:
        await db.commit()
        await db.refresh(order)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to update canceled order %s: %s", order_id, exc)

    logger.info("Order %s canceled by %s", order_id, current_user.email)
    return CancelOrderResponse(order_id=order.id, status=order.status, message="Order canceled")


@router.get(
    "/orders/{order_id}/status",
    response_model=OrderInfoResponse,
    status_code=status.HTTP_200_OK,
)
async def get_order_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> OrderInfoResponse:
    """Fetch the latest order status from the exchange and sync to DB."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.exchange_order_id:
        try:
            info = await kraken_service.get_order_status(order.exchange_order_id)
            order.status = info.status.value
            order.filled_quantity = float(info.filled_volume)
            await db.commit()
            await db.refresh(order)
        except KrakenAPIError as exc:
            logger.warning("Unable to refresh order %s from exchange: %s", order_id, exc)
        except Exception as exc:
            await db.rollback()
            logger.error("DB error syncing order %s: %s", order_id, exc)

    return OrderInfoResponse(
        id=order.id,
        trade_id=order.trade_id,
        exchange_order_id=order.exchange_order_id,
        status=order.status,
        order_type=order.order_type,
        side=order.side,
        price=order.price,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        created_at=order.created_at,
        updated_at=order.updated_at,
        error_message=order.error_message,
    )
