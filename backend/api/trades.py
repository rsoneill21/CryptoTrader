"""
Order management API routes.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.auth import get_current_user
from core.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    apply_cursor_pagination,
    decode_cursor,
    encode_cursor,
)
from core.indicators import side_color
from db.database import get_async_db
from db.models import Order, Trade, User
from api.market import DecisionRecord, fetch_decisions_for_trade
from agents.market_analyst import market_analyst_agent
from services.market_data import market_data_service
from services.kraken import kraken_service, KrakenAPIError
from core.exceptions import DatabaseException, ServiceUnavailableException
from core.risk import RiskService
from core.paper_trading import PaperTradeSignal, TradeIntent, TradeSide
from services.paper_trading_service import paper_trading_engine
from services.trade_sync import (
    PENDING_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    order_lifecycle_sync_service,
)

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


class TradeSummary(BaseModel):
    id: int
    strategy_id: Optional[int]
    symbol: str
    side: str
    entry_price: Optional[float]
    exit_price: Optional[float]
    quantity: float
    entry_time: Optional[datetime]
    exit_time: Optional[datetime]
    pnl: Optional[float]
    is_paper: bool
    is_manual: bool
    ai_model_used: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class TradeListResponse(BaseModel):
    trades: List[TradeSummary]
    next_cursor: Optional[str] = None
    limit: int
    has_more: bool = False


class CloseTradeRequest(BaseModel):
    """Payload used to mark a trade as closed."""

    quantity: Optional[float] = Field(None, gt=0.0, description="Quantity to close; defaults to full")
    close_reason: Optional[str] = Field(None, max_length=512)


class CloseTradeResponse(BaseModel):
    """Confirmation returned after closing a trade."""

    trade_id: int
    status: str
    reason_code: Optional[str]
    reason_message: Optional[str]
    requested_quantity: float
    filled_quantity: float
    remaining_quantity: float
    executed_price: float
    close_reason: Optional[str]
    exit_time: Optional[datetime]
    pnl: Optional[float]


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


ORDER_STATUSES = {"pending", "partially_filled", "filled", "rejected", "canceled"}


class ManualOrderSubmitRequest(BaseModel):
    """Manual order entry contract for market and limit intents."""

    symbol: str = Field(..., description="Trading pair (e.g., BTC/USD)")
    side: str = Field(..., pattern="^(buy|sell)$", description="Order side")
    order_type: str = Field(..., pattern="^(market|limit)$", description="Order type")
    quantity: Optional[float] = Field(None, gt=0)
    risk_percent: Optional[float] = Field(None, ge=1.0, le=100.0)
    limit_price: Optional[float] = Field(None, gt=0)
    is_paper: bool = True

    @model_validator(mode="after")
    def _validate_order_sizing(self) -> "ManualOrderSubmitRequest":
        has_quantity = self.quantity is not None
        has_risk_percent = self.risk_percent is not None
        if has_quantity == has_risk_percent:
            raise ValueError("Provide exactly one of quantity or risk_percent")

        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")

        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("limit_price is only allowed for limit orders")

        return self


class ManualOrderSubmitResponse(BaseModel):
    """Lifecycle-aware result returned by manual order submission."""

    order_id: int
    trade_id: Optional[int]
    status: str
    reason_code: Optional[str] = None
    reason_message: Optional[str] = None
    requested_quantity: float
    filled_quantity: float
    order_type: str
    side: str
    symbol: str
    execution_price: Optional[float] = None


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
        await db.refresh(trade, attribute_names=["orders"])
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to create manual trade", exc_info=True)
        raise DatabaseException(
            message="Failed to execute trade",
            details={"operation": "create_manual_trade"},
        ) from exc

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
        await db.refresh(trade, attribute_names=["orders"])
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to create system trade", exc_info=True)
        raise DatabaseException(
            message="Failed to record system trade",
            details={"operation": "create_system_trade"},
        ) from exc

    logger.info(
        "System trade created: id=%s, symbol=%s, ai_model=%s, is_manual=False",
        trade.id, trade.symbol, trade.ai_model_used,
    )
    return _serialize_trade(trade)


@router.post(
    "/orders",
    response_model=ManualOrderSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_manual_order(
    request: ManualOrderSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ManualOrderSubmitResponse:
    """Submit a manual market/limit order with server-side risk gating."""

    symbol = request.symbol.strip().upper()
    order_type = request.order_type.lower()
    side = request.side.lower()

    try:
        if order_type == "limit":
            reference_price = float(request.limit_price or 0.0)
        else:
            ticker = await kraken_service.get_ticker(symbol)
            reference_price = float(ticker.last)
    except KrakenAPIError as exc:
        logger.warning("Unable to fetch reference price for %s", symbol, exc_info=True)
        raise ServiceUnavailableException(
            service="kraken",
            details={"symbol": symbol, "operation": "manual_order_submit"},
        ) from exc

    if request.risk_percent is not None:
        quantity = await RiskService.quantity_from_risk_percent(
            db,
            risk_percent=request.risk_percent,
            reference_price=reference_price,
        )
    else:
        quantity = float(request.quantity or 0.0)

    await RiskService.validate_trade(
        db=db,
        symbol=symbol,
        quantity=quantity,
        price=reference_price,
        side=side,
    )

    now = datetime.utcnow()
    trade = Trade(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=reference_price if order_type == "market" else request.limit_price,
        entry_time=now if order_type == "market" else None,
        is_paper=request.is_paper,
        is_manual=True,
    )
    db.add(trade)
    await db.flush()

    order_status = "filled" if order_type == "market" else "pending"
    filled_quantity = quantity if order_type == "market" else 0.0

    order = Order(
        trade_id=trade.id,
        status=order_status,
        order_type=order_type,
        side=side,
        price=reference_price if order_type == "market" else request.limit_price,
        quantity=quantity,
        filled_quantity=filled_quantity,
    )
    db.add(order)

    if order_type == "market":
        signal_side = TradeSide.BUY if side == "buy" else TradeSide.SELL
        try:
            await paper_trading_engine.execute_signal(
                PaperTradeSignal(
                    symbol=symbol,
                    intent=TradeIntent.ENTRY,
                    side=signal_side,
                    quantity=quantity,
                    price=reference_price,
                    timestamp=now,
                    metadata={
                        "source": "manual_order",
                        "order_type": order_type,
                        "created_by": current_user.email,
                    },
                )
            )
        except ValueError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "order_execution_failed",
                    "message": str(exc),
                },
            ) from exc

    try:
        await db.commit()
        await db.refresh(order)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to submit manual order", exc_info=True)
        raise DatabaseException(
            message="Failed to submit manual order",
            details={"operation": "submit_manual_order", "symbol": symbol},
        ) from exc

    return ManualOrderSubmitResponse(
        order_id=order.id,
        trade_id=trade.id,
        status=_normalize_order_status(order.status),
        reason_code=None,
        reason_message=None,
        requested_quantity=quantity,
        filled_quantity=float(order.filled_quantity or 0.0),
        order_type=order.order_type,
        side=order.side,
        symbol=symbol,
        execution_price=float(order.price) if order.price is not None else None,
    )


@router.get(
    "/",
    response_model=TradeListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_trades(
    cursor: Optional[str] = Query(
        None,
        description="Cursor token for pagination",
    ),
    limit: int = Query(
        DEFAULT_PAGE_LIMIT,
        ge=1,
        le=MAX_PAGE_LIMIT,
        description="Number of trades per page",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> TradeListResponse:
    """Return historical trades using cursor-based pagination."""
    cursor_timestamp: Optional[datetime] = None
    cursor_id: Optional[int] = None
    if cursor:
        try:
            cursor_timestamp, cursor_id = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cursor: {exc}",
            )

    try:
        query = select(Trade).where(Trade.entry_time.is_not(None))
        cursor_tuple = (
            (cursor_timestamp, cursor_id)
            if cursor_timestamp is not None and cursor_id is not None
            else None
        )
        query, _, _ = apply_cursor_pagination(
            query,
            cursor_values=cursor_tuple,
            timestamp_column=Trade.entry_time,
            id_column=Trade.id,
        )
        query = query.order_by(desc(Trade.entry_time), desc(Trade.id))
        query = query.limit(limit + 1)
        result = await db.execute(query)
        trades = list(result.scalars().all())
    except HTTPException:
        raise
    except SQLAlchemyError as exc:  # pragma: no cover - defensive guard
        logger.error("Trade list fetch failed", exc_info=True)
        raise DatabaseException(
            message="Unable to retrieve trades",
            details={"operation": "list_trades"},
        ) from exc

    has_more = len(trades) > limit
    if has_more:
        trades = trades[:limit]

    next_cursor = None
    if has_more and trades and trades[-1].entry_time is not None:
        next_cursor = encode_cursor(trades[-1].entry_time, trades[-1].id)

    return TradeListResponse(
        trades=[TradeSummary.model_validate(trade) for trade in trades],
        next_cursor=next_cursor,
        limit=limit,
        has_more=has_more,
    )


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


def _normalize_order_status(status_value: str) -> str:
    normalized = (status_value or "").strip().lower().replace("-", "_")
    alias_map = {
        "open": "pending",
        "new": "pending",
        "closed": "filled",
        "cancelled": "canceled",
        "expired": "canceled",
    }
    mapped = alias_map.get(normalized, normalized)
    return mapped if mapped in ORDER_STATUSES else "rejected"


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
            .where(Trade.exit_time.is_(None), Trade.entry_time.is_not(None))
            .order_by(Trade.entry_time.desc())
        )
        trades = result.scalars().all()
    except SQLAlchemyError as exc:  # pragma: no cover - DB should be reachable
        logger.error("Failed to fetch active trades", exc_info=True)
        raise DatabaseException(
            message="Unable to retrieve active trades",
            details={"operation": "list_active_trades"},
        ) from exc

    # Fetch current prices for all unique symbols in active trades
    symbols = {trade.symbol for trade in trades}
    price_map: Dict[str, float] = {}
    for symbol in symbols:
        try:
            ticker = await kraken_service.get_ticker(symbol)
            price_map[symbol] = float(ticker.last)
        except Exception as exc:
            logger.debug("Unable to fetch price for %s", symbol, exc_info=True)

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
    """Close a trade at market price with optional partial quantity."""
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

    if trade.entry_price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "position_not_open",
                "message": "Trade has not been filled yet",
                "details": {"trade_id": trade_id},
            },
        )

    requested_quantity = float(request.quantity if request.quantity is not None else trade.quantity)
    if requested_quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_close_quantity",
                "message": "Close quantity must be greater than zero",
            },
        )

    if requested_quantity > float(trade.quantity):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "insufficient_position_quantity",
                "message": "Close quantity exceeds open position size",
                "details": {
                    "requested_quantity": requested_quantity,
                    "open_quantity": float(trade.quantity),
                },
            },
        )

    try:
        cached_price = await paper_trading_engine.get_cached_price(trade.symbol)
        if cached_price is not None:
            execution_price = float(cached_price)
        else:
            ticker = await kraken_service.get_ticker(trade.symbol)
            execution_price = float(ticker.last)
    except KrakenAPIError as exc:
        logger.warning("Unable to fetch close price for trade %s", trade_id, exc_info=True)
        raise ServiceUnavailableException(
            service="kraken",
            details={"operation": "close_trade", "trade_id": trade_id, "symbol": trade.symbol},
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error fetching close price for trade %s", trade_id, exc_info=True)
        raise ServiceUnavailableException(
            service="pricing",
            details={"operation": "close_trade", "trade_id": trade_id, "symbol": trade.symbol},
        ) from exc

    close_side = "sell" if trade.side.lower() == "buy" else "buy"
    await RiskService.validate_close(
        db=db,
        symbol=trade.symbol,
        quantity=requested_quantity,
        price=execution_price,
        side=close_side,
    )

    try:
        await paper_trading_engine.execute_signal(
            PaperTradeSignal(
                symbol=trade.symbol,
                intent=TradeIntent.EXIT,
                quantity=requested_quantity,
                price=execution_price,
                timestamp=datetime.utcnow(),
                metadata={
                    "source": "manual_close",
                    "trade_id": trade.id,
                    "close_reason": request.close_reason,
                    "closed_by": current_user.email,
                },
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "close_execution_failed",
                "message": str(exc),
                "details": {"trade_id": trade.id, "symbol": trade.symbol},
            },
        ) from exc

    now = datetime.utcnow()

    if requested_quantity < float(trade.quantity):
        partial_pnl = None
        if trade.entry_price is not None:
            side_multiplier = 1 if trade.side.lower() == "buy" else -1
            partial_pnl = (execution_price - trade.entry_price) * requested_quantity * side_multiplier

        partial_close = Trade(
            strategy_id=trade.strategy_id,
            ai_model_used=trade.ai_model_used,
            is_paper=trade.is_paper,
            is_manual=trade.is_manual,
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            exit_price=execution_price,
            quantity=requested_quantity,
            pnl=partial_pnl,
            fees=trade.fees,
            entry_time=trade.entry_time,
            exit_time=now,
            entry_reasoning_json=trade.entry_reasoning_json,
            exit_reasoning_json={
                "close_reason": request.close_reason,
                "requested_quantity": requested_quantity,
                "executed_price": execution_price,
                "close_type": "partial",
                "updated_by": current_user.email,
                "updated_at": now.isoformat(),
            },
            market_conditions_json=trade.market_conditions_json,
            indicators_json=trade.indicators_json,
            ai_managed=trade.ai_managed,
        )
        db.add(partial_close)

        trade.quantity = float(trade.quantity) - requested_quantity

        exit_reason = trade.exit_reasoning_json if isinstance(trade.exit_reasoning_json, dict) else {}
        partial_events = exit_reason.get("partial_closes")
        if not isinstance(partial_events, list):
            partial_events = []
        partial_events.append(
            {
                "requested_quantity": requested_quantity,
                "executed_price": execution_price,
                "close_reason": request.close_reason,
                "updated_by": current_user.email,
                "updated_at": now.isoformat(),
            }
        )
        exit_reason["partial_closes"] = partial_events
        trade.exit_reasoning_json = exit_reason
        pnl = partial_pnl
    else:
        trade.exit_price = execution_price
        trade.exit_time = now
        pnl = _calculate_pnl(trade, execution_price)
        if pnl is not None:
            trade.pnl = pnl

        trade.exit_reasoning_json = {
            "close_reason": request.close_reason,
            "requested_quantity": requested_quantity,
            "executed_price": execution_price,
            "close_type": "full",
            "updated_by": current_user.email,
            "updated_at": now.isoformat(),
        }

    try:
        await db.commit()
        await db.refresh(trade)
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Unable to close trade %s", trade_id, exc_info=True)
        raise DatabaseException(
            message="Failed to close trade",
            details={"operation": "close_trade", "trade_id": trade_id},
        ) from exc

    logger.info("Trade %s closed by user %s", trade_id, current_user.email)

    return CloseTradeResponse(
        trade_id=trade.id,
        status="filled",
        reason_code=None,
        reason_message=None,
        requested_quantity=requested_quantity,
        filled_quantity=requested_quantity,
        remaining_quantity=float(trade.quantity) if trade.exit_time is None else 0.0,
        executed_price=execution_price,
        close_reason=request.close_reason,
        exit_time=now,
        pnl=pnl,
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
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Unable to record adjustment for trade %s", trade_id, exc_info=True)
        raise DatabaseException(
            message="Failed to persist adjustment",
            details={"operation": "adjust_trade", "trade_id": trade_id},
        ) from exc

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
        logger.warning("Unable to load candles for trade %s", trade_id, exc_info=True)

    analyst_insights: List[Dict[str, Any]] = []
    try:
        analyst_insights = await market_analyst_agent.get_recent_insights(trade.symbol, limit=3)
    except Exception as exc:
        logger.warning("Analyst insights unavailable for %s", trade.symbol, exc_info=True)

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
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to toggle ai_managed for trade %s", trade_id, exc_info=True)
        raise DatabaseException(
            message="Failed to update trade",
            details={"operation": "toggle_ai_managed", "trade_id": trade_id},
        ) from exc

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
    except KrakenAPIError as exc:
        logger.warning("Unable to fetch live price for %s", trade.symbol, exc_info=True)
        raise ServiceUnavailableException(
            service="kraken",
            details={"symbol": trade.symbol, "operation": "get_ticker"},
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error fetching price for %s", trade.symbol, exc_info=True)
        raise ServiceUnavailableException(
            service="kraken",
            details={"symbol": trade.symbol, "operation": "get_ticker"},
        ) from exc

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
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to add to position %s", trade_id, exc_info=True)
        raise DatabaseException(
            message="Failed to update position",
            details={"operation": "add_to_position", "trade_id": trade_id},
        ) from exc

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
    reason_code: Optional[str] = None
    reason_message: Optional[str] = None


class PendingOrderResponse(BaseModel):
    id: int
    trade_id: Optional[int]
    trade_symbol: Optional[str]
    trade_side: Optional[str]
    exchange_order_id: Optional[str]
    status: str
    order_type: str
    side: str
    price: Optional[float]
    quantity: float
    filled_quantity: float
    created_at: datetime
    updated_at: datetime
    reason_code: Optional[str] = None
    reason_message: Optional[str] = None


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
                logger.debug("Could not refresh order %s", order.exchange_order_id, exc_info=True)

    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error(
            "Failed to persist refreshed order statuses for trade %s",
            trade_id,
            exc_info=True,
        )
        raise DatabaseException(
            message="Unable to refresh order statuses",
            details={"operation": "list_trade_orders", "trade_id": trade_id},
        ) from exc

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
            reason_code=_extract_reason_details(o.error_message)[0],
            reason_message=_extract_reason_details(o.error_message)[1],
        )
        for o in orders
    ]


def _extract_reason_details(error_message: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not error_message:
        return None, None

    message = error_message.strip()
    if message.startswith("[") and "]" in message:
        token, _, detail = message.partition("]")
        code = token.strip("[]").strip().lower()
        parsed_message = detail.strip() or None
        return code or None, parsed_message

    return None, message


@router.get(
    "/orders/pending",
    response_model=List[PendingOrderResponse],
    status_code=status.HTTP_200_OK,
)
async def list_pending_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[PendingOrderResponse]:
    """Return pending/partial orders after lifecycle reconciliation."""
    try:
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.trade))
            .where(Order.status.in_(tuple(PENDING_ORDER_STATUSES)))
            .order_by(Order.created_at.desc())
        )
        orders = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error("Failed to fetch pending orders", exc_info=True)
        raise DatabaseException(
            message="Unable to retrieve pending orders",
            details={"operation": "list_pending_orders"},
        ) from exc

    lifecycle_changed = False
    try:
        for order in orders:
            if not order.exchange_order_id:
                continue
            sync_result = await order_lifecycle_sync_service.reconcile_order(db, order)
            lifecycle_changed = lifecycle_changed or sync_result.changed

        if lifecycle_changed:
            await db.commit()
            refreshed_result = await db.execute(
                select(Order)
                .options(selectinload(Order.trade))
                .where(Order.status.in_(tuple(PENDING_ORDER_STATUSES)))
                .order_by(Order.created_at.desc())
            )
            orders = list(refreshed_result.scalars().all())
    except KrakenAPIError as exc:
        await db.rollback()
        logger.warning("Unable to reconcile pending orders", exc_info=True)
        raise ServiceUnavailableException(
            service="kraken",
            details={"operation": "list_pending_orders"},
        ) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to persist pending order reconciliation", exc_info=True)
        raise DatabaseException(
            message="Unable to persist pending order status",
            details={"operation": "list_pending_orders"},
        ) from exc

    visible_orders = [
        order for order in orders if (order.status or "").lower() not in TERMINAL_ORDER_STATUSES
    ]
    payload: List[PendingOrderResponse] = []
    for order in visible_orders:
        reason_code, reason_message = _extract_reason_details(order.error_message)
        payload.append(
            PendingOrderResponse(
                id=order.id,
                trade_id=order.trade_id,
                trade_symbol=order.trade.symbol if order.trade else None,
                trade_side=order.trade.side if order.trade else None,
                exchange_order_id=order.exchange_order_id,
                status=order.status,
                order_type=order.order_type,
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                filled_quantity=order.filled_quantity,
                created_at=order.created_at,
                updated_at=order.updated_at,
                reason_code=reason_code,
                reason_message=reason_message,
            )
        )
    return payload


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
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to update canceled order %s", order_id, exc_info=True)
        raise DatabaseException(
            message="Failed to update canceled order",
            details={"operation": "cancel_order", "order_id": order_id},
        ) from exc

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
            sync_result = await order_lifecycle_sync_service.reconcile_order(db, order)
            if sync_result.changed:
                await db.commit()
            await db.refresh(order)
        except KrakenAPIError as exc:
            logger.warning("Unable to refresh order %s from exchange", order_id, exc_info=True)
            raise ServiceUnavailableException(
                service="kraken",
                details={"operation": "sync_order_status", "order_id": order_id},
            ) from exc
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error("DB error syncing order %s", order_id, exc_info=True)
            raise DatabaseException(
                message="Unable to sync order status",
                details={"operation": "get_order_status", "order_id": order_id},
            ) from exc
        except Exception as exc:
            await db.rollback()
            logger.error("Unexpected error syncing order %s", order_id, exc_info=True)
            raise ServiceUnavailableException(
                service="orders",
                details={"operation": "sync_order_status", "order_id": order_id},
            ) from exc

    reason_code, reason_message = _extract_reason_details(order.error_message)
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
        reason_code=reason_code,
        reason_message=reason_message,
    )
