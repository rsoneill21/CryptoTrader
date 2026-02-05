"""Market data API routes backed by Kraken public endpoints."""

import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import fetch_ai_decisions_async, get_async_db
from db.models import AIDecision
from core.auth import get_current_session_ws
from services.kraken import KrakenAPIError, KrakenService, kraken_service, OHLC, Ticker
from services.kraken_ws import KrakenWSFeed, kraken_ws
from services.market_data import market_data_service
from services.portfolio import PortfolioSnapshot, portfolio_service
from agents.market_analyst import market_analyst_agent
from agents.sentiment_agent import SentimentSummary, sentiment_agent
from core.exceptions import ServiceUnavailableException

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_INTERVALS = list(KrakenService.INTERVAL_MAP.keys())

PAIR_REGEX = r"^[A-Z0-9]{2,12}/[A-Z0-9]{2,12}$"
PAIR_PATTERN = re.compile(PAIR_REGEX)


def _normalize_trading_pair(value: str, parameter: str = "pair") -> str:
    """Ensure a trading pair is provided in BASE/QUOTE format."""
    sanitized = value.strip().upper()
    if not sanitized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{parameter} cannot be empty",
        )

    if not PAIR_PATTERN.match(sanitized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{parameter} must be in BASE/QUOTE format "
                "using uppercase letters and numbers "
                f"(e.g., BTC/USD). Got: {value}"
            ),
        )

    return sanitized


class TickerResponse(BaseModel):
    symbol: str
    ask: Decimal
    bid: Decimal
    last: Decimal
    volume_24h: Decimal = Field(..., alias="volume24h")
    vwap_24h: Decimal = Field(..., alias="vwap24h")
    high_24h: Decimal = Field(..., alias="high24h")
    low_24h: Decimal = Field(..., alias="low24h")
    open_24h: Decimal = Field(..., alias="open24h")
    trades_24h: int = Field(..., alias="trades24h")
    timestamp: datetime

    model_config = {"populate_by_name": True}


class OHLCEntry(BaseModel):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Decimal
    trades: int


class OHLCSeriesResponse(BaseModel):
    pair: str
    interval: str
    last: int
    candles: List[OHLCEntry]


class PairSummary(BaseModel):
    symbol: str
    kraken_name: str
    base: str
    quote: str
    lot_decimals: int
    pair_decimals: int
    ordermin: Decimal


class PairsResponse(BaseModel):
    pairs: List[PairSummary]


DEFAULT_PRICE_SYMBOLS = sorted(KrakenService.PAIR_MAPPINGS.keys())


class PricesResponse(BaseModel):
    prices: List[TickerResponse]


class OrderbookEntry(BaseModel):
    price: Decimal
    volume: Decimal
    timestamp: int


class OrderbookResponse(BaseModel):
    symbol: str
    bids: List[OrderbookEntry]
    asks: List[OrderbookEntry]


class DecisionRecord(BaseModel):
    id: int
    agent_name: str
    decision_type: str
    reasoning: Optional[Dict[str, Any]]
    confidence_score: Optional[float]
    action_taken: Optional[str]
    timestamp: datetime
    related_strategy_id: Optional[int]
    related_trade_id: Optional[int]
    near_miss: bool
    near_miss_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class DecisionLogResponse(BaseModel):
    decisions: List[DecisionRecord]
    total: int

    model_config = ConfigDict(from_attributes=True)


class TechnicalSnapshot(BaseModel):
    symbol: str
    data_points: int
    direction: str
    last_price: Optional[Decimal]
    previous_price: Optional[Decimal]
    average: Optional[Decimal]
    high: Optional[Decimal]
    low: Optional[Decimal]
    momentum: Optional[Decimal]
    volatility: Optional[Decimal]
    price_range: Optional[Decimal]
    range_pct: Optional[Decimal]
    last_updated: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AnalystIndicatorSnapshot(BaseModel):
    short_sma: Optional[Decimal]
    long_sma: Optional[Decimal]
    momentum: Optional[Decimal]
    volatility: Optional[Decimal]
    price_count: int
    last_price: Optional[Decimal]
    last_timestamp: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class MarketAnalysisResponse(BaseModel):
    symbol: str
    technical: TechnicalSnapshot
    analyst_indicators: AnalystIndicatorSnapshot
    insights: List[Dict[str, Any]]
    sentiment: Optional[SentimentSummary]
    recommendations: List[str]

    model_config = ConfigDict(from_attributes=True)


def _map_decision(record: Any) -> DecisionRecord:
    return DecisionRecord(
        id=record.id,
        agent_name=record.agent_name,
        decision_type=record.decision_type,
        reasoning=record.reasoning_json,
        confidence_score=record.confidence_score,
        action_taken=record.action_taken,
        timestamp=record.timestamp,
        related_strategy_id=record.related_strategy_id,
        related_trade_id=record.related_trade_id,
        near_miss=bool(record.near_miss),
        near_miss_reason=record.near_miss_reason,
    )


def _build_technical_snapshot(symbol: str, payload: Dict[str, Any]) -> TechnicalSnapshot:
    return TechnicalSnapshot(
        symbol=symbol,
        data_points=int(payload.get("data_points") or 0),
        direction=str(payload.get("direction") or "unknown"),
        last_price=_safe_decimal(payload.get("last_price")),
        previous_price=_safe_decimal(payload.get("previous_price")),
        average=_safe_decimal(payload.get("average")),
        high=_safe_decimal(payload.get("high")),
        low=_safe_decimal(payload.get("low")),
        momentum=_safe_decimal(payload.get("momentum")),
        volatility=_safe_decimal(payload.get("volatility")),
        price_range=_safe_decimal(payload.get("price_range")),
        range_pct=_safe_decimal(payload.get("range_pct")),
        last_updated=payload.get("last_updated"),
    )


def _build_indicator_snapshot(payload: Dict[str, Any]) -> AnalystIndicatorSnapshot:
    return AnalystIndicatorSnapshot(
        short_sma=_safe_decimal(payload.get("short_sma")),
        long_sma=_safe_decimal(payload.get("long_sma")),
        momentum=_safe_decimal(payload.get("momentum")),
        volatility=_safe_decimal(payload.get("volatility")),
        price_count=int(payload.get("price_count") or 0),
        last_price=_safe_decimal(payload.get("last_price")),
        last_timestamp=payload.get("last_timestamp"),
    )


def _build_recommendations(
    symbol: str,
    technical: TechnicalSnapshot,
    indicator: AnalystIndicatorSnapshot,
    insights: List[Dict[str, Any]],
    sentiment: Optional[SentimentSummary],
) -> List[str]:
    recommendations: List[str] = []
    if technical.direction == "rising":
        recommendations.append(f"{symbol}: Price has been trending higher on recent candles.")
    elif technical.direction == "falling":
        recommendations.append(f"{symbol}: Price is slipping lower; monitor for support.")
    elif technical.direction == "flat":
        recommendations.append(f"{symbol}: Price action is range-bound; wait for a breakout.")

    if indicator.momentum is not None:
        threshold = Decimal("0.015")
        if indicator.momentum > threshold:
            recommendations.append("Momentum remains positive; follow-through action is likely.")
        elif indicator.momentum < -threshold:
            recommendations.append("Momentum flipped negative; a retracement may continue.")

    if sentiment:
        if sentiment.average_score >= 0.2:
            recommendations.append("Community sentiment is bullish; buyers dominate the chatter.")
        elif sentiment.average_score <= -0.2:
            recommendations.append("Sentiment tone is bearish; respect resistance levels.")
        else:
            recommendations.append("Sentiment stays neutral; let technicals lead the next move.")

    for insight in insights[:2]:
        summary = insight.get("summary")
        if summary:
            snippet = str(summary).strip()
            if snippet and snippet not in recommendations:
                recommendations.append(f"Insight: {snippet}")

    if not recommendations:
        recommendations.append(f"{symbol}: No strong signals; keep watching price and sentiment.")

    return recommendations


async def fetch_decisions_for_trade(
    db: AsyncSession,
    trade_id: int,
    limit: int = 10,
) -> List[DecisionRecord]:
    result = await db.execute(
        select(AIDecision)
        .where(AIDecision.related_trade_id == trade_id)
        .order_by(AIDecision.timestamp.desc())
        .limit(max(1, min(limit, 50)))
    )
    records = result.scalars().all()
    return [_map_decision(record) for record in records]

def _handle_kraken_error(exc: KrakenAPIError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=exc.message or "Failed to reach Kraken",
    )


def _safe_decimal(value: Any, fallback: str = "0") -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(fallback)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _build_orderbook_entries(entries: List[Dict[str, Any]]) -> List[OrderbookEntry]:
    sanitized: List[OrderbookEntry] = []
    for record in entries:
        sanitized.append(OrderbookEntry(
            price=_safe_decimal(record.get("price")),
            volume=_safe_decimal(record.get("volume")),
            timestamp=_safe_int(record.get("timestamp")),
        ))
    return sanitized


async def _build_candles_response(
    symbol: str,
    interval: str,
    since: Optional[int],
    limit: int,
) -> OHLCSeriesResponse:
    if interval not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported interval")

    try:
        candles, last = await kraken_service.get_ohlc(symbol, interval, since)
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)

    entries = _ohlc_entries(candles[:limit])

    return OHLCSeriesResponse(
        pair=symbol,
        interval=interval,
        last=last,
        candles=entries,
    )

def _ticker_response(ticker: Ticker) -> TickerResponse:
    data = {
        "symbol": ticker.symbol,
        "ask": ticker.ask,
        "bid": ticker.bid,
        "last": ticker.last,
        "volume24h": ticker.volume_24h,
        "vwap24h": ticker.vwap_24h,
        "high24h": ticker.high_24h,
        "low24h": ticker.low_24h,
        "open24h": ticker.open_24h,
        "trades24h": ticker.trades_24h,
        "timestamp": ticker.timestamp,
    }
    return TickerResponse(**data)


def _ohlc_entries(candles: List[OHLC]) -> List[OHLCEntry]:
    return [OHLCEntry(**candle.__dict__) for candle in candles]


@router.get("/ticker/{pair}", response_model=TickerResponse)
async def get_ticker(pair: str):
    """Return current ticker data for the requested pair."""
    normalized_pair = _normalize_trading_pair(pair, parameter="pair")
    try:
        ticker = await kraken_service.get_ticker(normalized_pair)
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)

    return _ticker_response(ticker)


@router.get("/prices", response_model=PricesResponse)
async def get_market_prices(
    symbols: Optional[List[str]] = Query(
        None,
        alias="symbol",
        description="Comma-separated or repeated trading symbols to fetch.",
    ),
) -> PricesResponse:
    """Return current ticker data for multiple symbols."""
    seen: set[str] = set()
    selected: List[str] = []

    for raw in symbols or []:
        for part in raw.split(","):
            candidate = part.strip()
            if not candidate:
                continue

            normalized = _normalize_trading_pair(candidate, parameter="symbol")
            if normalized in seen:
                continue

            seen.add(normalized)
            selected.append(normalized)

    if not selected:
        selected = DEFAULT_PRICE_SYMBOLS

    prices: List[TickerResponse] = []

    for symbol in selected:
        try:
            ticker = await kraken_service.get_ticker(symbol)
        except KrakenAPIError as exc:
            raise _handle_kraken_error(exc)
        prices.append(_ticker_response(ticker))

    return PricesResponse(prices=prices)


@router.get("/ohlc/{pair}", response_model=OHLCSeriesResponse)
async def get_ohlc(
    pair: str,
    interval: str = Query("1h", description="OHLC interval", pattern="^(1m|5m|15m|30m|1h|4h|1d|1w|2w)$"),
    since: Optional[int] = Query(None, ge=0, description="Unix timestamp to start from"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of candles to return"),
) -> OHLCSeriesResponse:
    """Return OHLC candle data for the requested pair and interval."""
    validated_pair = _normalize_trading_pair(pair, parameter="pair")
    return await _build_candles_response(validated_pair, interval, since, limit)


@router.get("/candles/{symbol}", response_model=OHLCSeriesResponse)
async def get_candles(
    symbol: str,
    interval: str = Query("1h", description="OHLC interval", pattern="^(1m|5m|15m|30m|1h|4h|1d|1w|2w)$"),
    since: Optional[int] = Query(None, ge=0, description="Unix timestamp to start from"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of candles to return"),
) -> OHLCSeriesResponse:
    """Return OHLC candle data for the requested symbol and interval."""
    validated_symbol = _normalize_trading_pair(symbol, parameter="symbol")
    return await _build_candles_response(validated_symbol, interval, since, limit)


@router.get("/orderbook/{symbol}", response_model=OrderbookResponse)
async def get_orderbook(
    symbol: str,
    count: int = Query(25, ge=1, le=500, description="Number of bids/asks to return per side"),
) -> OrderbookResponse:
    """Return a simplified order book for the given trading symbol."""
    validated_symbol = _normalize_trading_pair(symbol, parameter="symbol")
    try:
        orderbook = await kraken_service.get_orderbook(validated_symbol, count=count)
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)

    orderbook = orderbook or {}

    bids = _build_orderbook_entries(orderbook.get("bids", []))
    asks = _build_orderbook_entries(orderbook.get("asks", []))

    return OrderbookResponse(
        symbol=symbol,
        bids=bids,
        asks=asks,
    )


@router.get("/analysis/{symbol}", response_model=MarketAnalysisResponse)
async def get_market_analysis(
    symbol: str,
    lookback: int = Query(
        20,
        ge=3,
        le=200,
        description="Number of recent candles used for the technical snapshot",
    ),
    insight_limit: int = Query(
        3,
        ge=1,
        le=6,
        description="Maximum number of market insights to include",
    ),
    sentiment_limit: int = Query(
        5,
        ge=1,
        le=20,
        description="How many sentiment samples to summarize",
    ),
) -> MarketAnalysisResponse:
    """Provide a blended market analysis for a symbol, including technical, insight, and sentiment cues."""
    normalized_symbol = _normalize_trading_pair(symbol, parameter="symbol")
    try:
        technical_payload = await market_data_service.summarize_symbol(
            normalized_symbol,
            lookback=lookback,
        )
    except Exception as exc:  # pragma: no cover - best effort summary
        logger.error("Failed to summarize technical data for %s", normalized_symbol, exc_info=True)
        raise ServiceUnavailableException(
            service="market_data",
            details={"symbol": normalized_symbol, "operation": "summarize_symbol"},
        ) from exc

    indicator_payload: Dict[str, Any] = {
        "short_sma": None,
        "long_sma": None,
        "momentum": None,
        "volatility": None,
        "price_count": 0,
        "last_price": None,
        "last_timestamp": None,
    }
    try:
        indicator_payload = await market_analyst_agent.get_indicator_summary(normalized_symbol)
    except Exception as exc:
        logger.warning("Indicator summary unavailable for %s", normalized_symbol, exc_info=True)

    insights: List[Dict[str, Any]] = []
    try:
        insights = await market_analyst_agent.get_recent_insights(normalized_symbol, limit=insight_limit)
    except Exception as exc:
        logger.warning("Failed to fetch analyst insights for %s", normalized_symbol, exc_info=True)

    sentiment_summary: Optional[SentimentSummary] = None
    try:
        sentiment_summary = await sentiment_agent.summarize_symbol(
            normalized_symbol,
            limit=sentiment_limit,
        )
    except Exception as exc:
        logger.warning("Sentiment summary unavailable for %s", normalized_symbol, exc_info=True)

    technical_snapshot = _build_technical_snapshot(normalized_symbol, technical_payload)
    indicator_snapshot = _build_indicator_snapshot(indicator_payload)
    recommendations = _build_recommendations(
        normalized_symbol,
        technical_snapshot,
        indicator_snapshot,
        insights,
        sentiment_summary,
    )

    return MarketAnalysisResponse(
        symbol=normalized_symbol,
        technical=technical_snapshot,
        analyst_indicators=indicator_snapshot,
        insights=insights,
        sentiment=sentiment_summary,
        recommendations=recommendations,
    )


@router.get("/pairs", response_model=PairsResponse)
async def list_pairs():
    """List available trading pairs from Kraken."""
    try:
        pairs = await kraken_service.get_asset_pairs()
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)

    summaries = [
        PairSummary(
            symbol=symbol,
            kraken_name=info.get("kraken_name"),
            base=info.get("base"),
            quote=info.get("quote"),
            lot_decimals=int(info.get("lot_decimals", 0)),
            pair_decimals=int(info.get("pair_decimals", 0)),
            ordermin=Decimal(str(info.get("ordermin", "0"))),
        )
        for symbol, info in sorted(pairs.items())
    ]

    return PairsResponse(pairs=summaries)


@router.get("/portfolio", response_model=PortfolioSnapshot)
async def get_portfolio(force_refresh: bool = Query(False, description="Skip cache and refresh data")):
    """Return cached Kraken balance snapshot."""
    try:
        return await portfolio_service.get_snapshot(force_refresh=force_refresh)
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)


@router.get("/decisions", response_model=DecisionLogResponse)
async def list_ai_decisions(
    strategy_id: Optional[int] = Query(
        None, description="Return decisions tied to a specific strategy ID"
    ),
    since: Optional[datetime] = Query(
        None,
        description="Earliest timestamp (inclusive) to include in the response",
    ),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of decision records to return"
    ),
    db: AsyncSession = Depends(get_async_db),
) -> DecisionLogResponse:
    """Return AI decision log entries for auditing paper trading choices."""
    total, records = await fetch_ai_decisions_async(
        db,
        strategy_id=strategy_id,
        since=since,
        limit=limit,
    )
    return DecisionLogResponse(
        total=total,
        decisions=[_map_decision(record) for record in records],
    )


ALLOWED_WS_FEEDS = {
    KrakenWSFeed.TICKER.value,
    KrakenWSFeed.TRADE.value,
    KrakenWSFeed.OHLC.value,
}


@router.websocket("/stream/{feed}")
async def market_stream(
    websocket: WebSocket,
    feed: str,
    symbol: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    WebSocket endpoint that streams Kraken updates to connected clients.
    Clients pick a feed (ticker, trade, ohlc) and optionally a symbol.
    """
    feed = feed.lower()
    if feed not in ALLOWED_WS_FEEDS:
        await websocket.close(code=1003)
        return

    try:
        await get_current_session_ws(websocket, db)
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Trigger on-demand subscription if symbol is provided
    if symbol:
        try:
            normalized = _normalize_trading_pair(symbol)
            if feed == KrakenWSFeed.TICKER.value:
                await kraken_ws.subscribe_ticker([normalized])
            elif feed == KrakenWSFeed.TRADE.value:
                await kraken_ws.subscribe_trades([normalized])
            elif feed == KrakenWSFeed.OHLC.value:
                await kraken_ws.subscribe_ohlc([normalized])
        except Exception:
            logger.error("Failed to subscribe to %s feed for %s", feed, symbol, exc_info=True)

    kraken_ws.add_client(websocket, feeds={feed})
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        kraken_ws.remove_client(websocket)
