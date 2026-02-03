"""
Order management API routes.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from core.auth import get_current_user
from core.indicators import side_color
from db.database import get_db
from db.models import Order, Trade, User
from backend.api.market import DecisionRecord, fetch_decisions_for_trade
from backend.agents.market_analyst import market_analyst_agent
from services.market_data import market_data_service

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
    pnl: Optional[float]
    market_conditions: Optional[Dict[str, Any]]
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
    db: Session = Depends(get_db),
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
        db.commit()
        db.refresh(trade)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create manual trade: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute trade",
        )

    logger.info("Manual trade created: id=%s, symbol=%s", trade.id, trade.symbol)
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


def _serialize_trade(trade: Trade) -> ActiveTradeResponse:
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
        pnl=trade.pnl,
        market_conditions=trade.market_conditions_json,
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
    db: Session = Depends(get_db),
) -> List[ActiveTradeResponse]:
    """Return all trades that have not been exited yet."""
    try:
        trades = (
            db.query(Trade)
            .options(selectinload(Trade.orders))
            .filter(Trade.exit_time.is_(None))
            .order_by(Trade.entry_time.desc())
            .all()
        )
    except Exception as exc:  # pragma: no cover - DB should be reachable
        logger.error("Failed to fetch active trades: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve active trades",
        )

    return [_serialize_trade(trade) for trade in trades]


@router.post(
    "/{trade_id}/close",
    response_model=CloseTradeResponse,
    status_code=status.HTTP_200_OK,
)
async def close_trade(
    trade_id: int,
    request: CloseTradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CloseTradeResponse:
    """Mark a trade as closed and record exit pricing."""
    trade = db.get(Trade, trade_id)
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
        db.commit()
        db.refresh(trade)
    except Exception as exc:
        db.rollback()
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
    db: Session = Depends(get_db),
) -> AdjustTradeResponse:
    """Persist stop-loss / take-profit adjustments for an active trade."""
    trade = db.get(Trade, trade_id)
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
        db.commit()
        db.refresh(trade)
    except Exception as exc:
        db.rollback()
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
    db: Session = Depends(get_db),
) -> TradeReasoningResponse:
    """Return AI reasoning, context, and analyst insights for a specific trade."""
    trade = db.get(Trade, trade_id)
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

    decisions = fetch_decisions_for_trade(db, trade_id)

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
