"""Market data API routes backed by Kraken public endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from services.kraken import KrakenAPIError, KrakenService, kraken_service, OHLC, Ticker
from services.kraken_ws import KrakenWSFeed, kraken_ws

router = APIRouter()

ALLOWED_INTERVALS = list(KrakenService.INTERVAL_MAP.keys())


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

    class Config:
        allow_population_by_field_name = True


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


def _handle_kraken_error(exc: KrakenAPIError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=exc.message or "Failed to reach Kraken",
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
    try:
        ticker = await kraken_service.get_ticker(pair)
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)

    return _ticker_response(ticker)


@router.get("/ohlc/{pair}", response_model=OHLCSeriesResponse)
async def get_ohlc(
    pair: str,
    interval: str = Query("1h", description="OHLC interval", pattern="^(1m|5m|15m|30m|1h|4h|1d|1w|2w)$"),
    since: Optional[int] = Query(None, ge=0, description="Unix timestamp to start from"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of candles to return"),
):
    """Return OHLC candle data for the requested pair and interval."""
    if interval not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported interval")

    try:
        candles, last = await kraken_service.get_ohlc(pair, interval, since)
    except KrakenAPIError as exc:
        raise _handle_kraken_error(exc)

    entries = _ohlc_entries(candles[:limit])

    return OHLCSeriesResponse(
        pair=pair,
        interval=interval,
        last=last,
        candles=entries,
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


ALLOWED_WS_FEEDS = {
    KrakenWSFeed.TICKER.value,
    KrakenWSFeed.TRADE.value,
    KrakenWSFeed.OHLC.value,
}


@router.websocket("/stream/{feed}")
async def market_stream(websocket: WebSocket, feed: str):
    """
    WebSocket endpoint that streams Kraken updates to connected clients.
    Clients pick a feed (ticker, trade, ohlc) and receive matching events.
    """
    feed = feed.lower()
    if feed not in ALLOWED_WS_FEEDS:
        await websocket.close(code=1003)
        return

    await websocket.accept()
    kraken_ws.add_client(websocket, feeds={feed})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        kraken_ws.remove_client(websocket)
