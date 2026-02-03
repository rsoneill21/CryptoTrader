"""Sentiment/News agent that monitors configured data sources and publishes scored insights."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agents.base import AgentMessage, BaseAgent
from backend.core.message_queue import Channels, message_queue
from backend.core.tasks import log_system_event
from db.database import SessionLocal
from db.models import DataSourceConfig, SentimentData

logger = logging.getLogger(__name__)

DEFAULT_FETCH_INTERVAL = 60
CHECK_INTERVAL = 10.0

POSITIVE_KEYWORDS: List[str] = [
    "bull",
    "bullish",
    "pump",
    "moon",
    "breakout",
    "green",
    "surge",
    "rally",
    "support",
    "long",
]

NEGATIVE_KEYWORDS: List[str] = [
    "bear",
    "bearish",
    "dump",
    "crash",
    "selloff",
    "drop",
    "resistance",
    "short",
    "rejection",
    "liquidation",
]


class SentimentFeedItem(BaseModel):
    """Single piece of text that will be scored and stored."""

    symbol: Optional[str]
    text: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    bias: float = 0.0

    model_config = ConfigDict(extra="ignore")


class SentimentPayload(BaseModel):
    """Validated payload published to the sentiment channel."""

    source: str
    symbol: Optional[str]
    sentiment_score: float
    summary: str
    raw_data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        extra="ignore",
        json_encoders={datetime: lambda value: value.isoformat()},
    )


class SentimentSummary(BaseModel):
    """Aggregated sentiment metrics for a symbol."""

    symbol: str
    average_score: float
    positive_mentions: int
    negative_mentions: int
    neutral_mentions: int
    data_points: int
    latest_summary: Optional[str]
    last_updated: Optional[datetime]
    sources: Dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


DEFAULT_MOCK_FEEDS: Dict[str, List[SentimentFeedItem]] = {
    "twitter": [
        SentimentFeedItem(
            symbol="BTC/USD",
            text="Twitter chatter thinks a BTC break above 50k will trigger another rally",
            metadata={"channel": "twitter", "mood": "optimistic"},
        ),
        SentimentFeedItem(
            symbol="ETH/USD",
            text="Community expects a bullish bounce after the latest ETF inflows",
            metadata={"channel": "twitter", "mood": "positive"},
        ),
    ],
    "reddit": [
        SentimentFeedItem(
            symbol="SOL/USD",
            text="Reddit threads are worried about a dump but also seeing cheap buying opportunities",
            metadata={"channel": "reddit", "thread": "sol"},
        ),
        SentimentFeedItem(
            symbol="ADA/USD",
            text="Users celebrate new roadmap updates even though price is flirting with resistance",
            metadata={"channel": "reddit", "thread": "ada"},
        ),
    ],
    "news": [
        SentimentFeedItem(
            symbol="BTC/USD",
            text="Institutional investors remain bullish on the latest macro data and macro liquidity",
            metadata={"channel": "news", "source": "macro"},
        ),
        SentimentFeedItem(
            symbol="ETH/USD",
            text="Regulatory concerns create bearish pressure but buyers defend the 1.5k level",
            metadata={"channel": "news", "source": "regulation"},
        ),
    ],
    "onchain": [
        SentimentFeedItem(
            symbol="BTC/USD",
            text="Whale accumulation on exchange wallets suggests a steady accumulation phase",
            metadata={"channel": "onchain", "signal": "whale"},
        ),
        SentimentFeedItem(
            symbol="ETH/USD",
            text="Large outflows from staking pools resolve into sideways price action",
            metadata={"channel": "onchain", "signal": "flow"},
        ),
    ],
}


def _clamp_score(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _extract_keywords(raw_value: Any) -> List[str]:
    if not raw_value:
        return []
    if isinstance(raw_value, str):
        return [raw_value.lower()]
    if isinstance(raw_value, Iterable):
        normalized: List[str] = []
        for item in raw_value:
            if isinstance(item, str):
                normalized.append(item.lower())
        return normalized
    return []


class SentimentAgent(BaseAgent):
    """Agent that polls configured data sources, scores sentiment, and publishes it."""

    def __init__(self) -> None:
        super().__init__(
            name="sentiment_agent",
            description="Monitors news, social, and on-chain data to derive sentiment signals",
        )
        self._db_factory = SessionLocal
        self._next_poll: float = 0.0

    async def on_start(self) -> None:
        connected = await message_queue.connect()
        if not connected:
            self._log_system_event(
                "warning",
                "Sentiment agent could not connect to message queue",
                {},
            )

    async def on_stop(self) -> None:
        try:
            await message_queue.disconnect()
        except Exception as exc:
            self._log_system_event(
                "warning",
                "Sentiment agent failed to disconnect",
                {"error": str(exc)},
            )

    async def run(self) -> None:
        now = asyncio.get_running_loop().time()
        if now < self._next_poll:
            await asyncio.sleep(0.1)
            return

        self._next_poll = now + CHECK_INTERVAL
        await self._poll_sources()
        await asyncio.sleep(0.1)

    async def process_message(self, message: AgentMessage) -> None:
        self._log_system_event(
            "debug",
            "Sentiment agent received message",
            {
                "sender": getattr(message, "sender", "internal"),
                "type": getattr(message, "message_type", "unknown"),
            },
        )

    async def summarize_symbol(
        self,
        symbol: Optional[str],
        limit: int = 5,
    ) -> Optional[SentimentSummary]:
        normalized = self._normalize_symbol(symbol)
        if not normalized:
            return None
        sanitized = max(1, min(limit, 50))
        return await asyncio.to_thread(self._build_sentiment_summary, normalized, sanitized)

    async def _poll_sources(self) -> None:
        try:
            source_ids = await asyncio.to_thread(self._load_enabled_source_ids)
        except Exception as exc:
            self._log_system_event(
                "error",
                "Unable to load data source configs",
                {"error": str(exc)},
            )
            return

        if not source_ids:
            return

        tasks = [self._process_source(source_id) for source_id in source_ids]
        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                self._log_system_event(
                    "warning",
                    "Sentiment source task failed",
                    {"error": str(result)},
                )

    async def _process_source(self, source_id: int) -> None:
        try:
            observations = await asyncio.to_thread(self._collect_from_source, source_id)
        except Exception as exc:
            self._log_system_event(
                "error",
                "Failed to collect sentiment",
                {"source_id": source_id, "error": str(exc)},
            )
            return

        if not observations:
            return

        await self._publish_observations(observations)

    def _load_enabled_source_ids(self) -> List[int]:
        db = self._db_factory()
        try:
            configs = (
                db.query(DataSourceConfig.id)
                .filter(DataSourceConfig.enabled.is_(True))
                .all()
            )
            return [row.id for row in configs]
        finally:
            db.close()

    def _collect_from_source(self, source_id: int) -> List[SentimentPayload]:
        db = self._db_factory()
        observations: List[SentimentPayload] = []
        now = datetime.utcnow()
        try:
            config = db.get(DataSourceConfig, source_id)
            if not config or not config.enabled:
                return []

            interval = config.fetch_interval_seconds or DEFAULT_FETCH_INTERVAL
            last_fetch = config.last_fetch
            if last_fetch and (now - last_fetch).total_seconds() < interval:
                return []

            payload_config = (
                config.config_json
                if isinstance(config.config_json, dict)
                else {}
            )

            feed_items = self._build_feed_items(config.source_name or "news", payload_config)
            if not feed_items:
                config.last_fetch = now
                db.add(config)
                db.commit()
                return []

            for item in feed_items:
                payload = self._build_payload(item, config, payload_config)
                observations.append(payload)
                db.add(
                    SentimentData(
                        source=payload.source,
                        symbol=payload.symbol,
                        sentiment_score=float(payload.sentiment_score),
                        summary=payload.summary,
                        raw_data_json=payload.raw_data,
                        timestamp=payload.timestamp,
                    )
                )

            config.last_fetch = now
            db.add(config)
            db.commit()
            return observations
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _build_feed_items(
        self, source_name: str, payload_config: Dict[str, Any]
    ) -> List[SentimentFeedItem]:
        normalized_source = source_name.lower().strip()
        feed_override = payload_config.get("mock_feed")
        items: List[SentimentFeedItem] = []

        if isinstance(feed_override, list):
            for raw_item in feed_override:
                if not isinstance(raw_item, dict):
                    continue
                try:
                    items.append(SentimentFeedItem(**raw_item))
                except ValidationError:
                    continue
            if items:
                return items

        defaults = DEFAULT_MOCK_FEEDS.get(normalized_source) or DEFAULT_MOCK_FEEDS.get("news", [])
        limit_value = payload_config.get("limit")
        if isinstance(limit_value, (int, float)):
            limit = max(1, int(limit_value))
        else:
            limit = len(defaults)

        filtered = self._filter_by_symbols(defaults, payload_config.get("symbols"))
        return filtered[:min(len(filtered), limit)]

    def _build_payload(
        self, item: SentimentFeedItem, config: DataSourceConfig, payload_config: Dict[str, Any]
    ) -> SentimentPayload:
        positive = self._merge_keywords(
            POSITIVE_KEYWORDS, payload_config.get("positive_keywords")
        )
        negative = self._merge_keywords(
            NEGATIVE_KEYWORDS, payload_config.get("negative_keywords")
        )
        bias = self._normalize_bias(item.bias)
        score = self._score_text(item.text, positive, negative, bias)
        symbol = self._normalize_symbol(item.symbol)
        summary = self._summarize_text(item.text)
        raw_data = {
            "text": item.text,
            "metadata": item.metadata,
            "config": payload_config,
        }

        return SentimentPayload(
            source=(config.source_name or "sentiment").strip().lower(),
            symbol=symbol,
            sentiment_score=score,
            summary=summary,
            raw_data=raw_data,
        )

    def _build_sentiment_summary(self, symbol: str, limit: int) -> Optional[SentimentSummary]:
        db = self._db_factory()
        try:
            rows = (
                db.query(SentimentData)
                .filter(SentimentData.symbol == symbol)
                .order_by(SentimentData.timestamp.desc())
                .limit(limit)
                .all()
            )
            if not rows:
                return None

            positive = negative = neutral = 0
            total_score = 0.0
            sources: Dict[str, int] = {}
            latest_summary: Optional[str] = None
            last_updated: Optional[datetime] = None

            for index, row in enumerate(rows):
                score = float(row.sentiment_score or 0.0)
                total_score += score
                if score > 0.05:
                    positive += 1
                elif score < -0.05:
                    negative += 1
                else:
                    neutral += 1
                if row.source:
                    key = row.source.lower()
                else:
                    key = "unknown"
                sources[key] = sources.get(key, 0) + 1
                if index == 0:
                    latest_summary = row.summary
                    last_updated = row.timestamp

            average_score = _clamp_score(total_score / len(rows))
            return SentimentSummary(
                symbol=symbol,
                average_score=average_score,
                positive_mentions=positive,
                negative_mentions=negative,
                neutral_mentions=neutral,
                data_points=len(rows),
                latest_summary=latest_summary,
                last_updated=last_updated,
                sources=sources,
            )
        finally:
            db.close()

    def _filter_by_symbols(
        self,
        items: List[SentimentFeedItem],
        value: Any,
    ) -> List[SentimentFeedItem]:
        if not value:
            return items
        if isinstance(value, str):
            symbols = {value.upper()}
        elif isinstance(value, Iterable):
            symbols = {str(sym).upper() for sym in value if sym}
        else:
            return items

        filtered = [item for item in items if not item.symbol or item.symbol.upper() in symbols]
        return filtered or items

    def _merge_keywords(self, base: List[str], extra: Any) -> List[str]:
        overrides = [kw.lower() for kw in _extract_keywords(extra)]
        merged: List[str] = []
        for keyword in base + overrides:
            normalized = keyword.lower()
            if normalized and normalized not in merged:
                merged.append(normalized)
        return merged

    def _score_text(
        self,
        text: str,
        positives: Sequence[str],
        negatives: Sequence[str],
        bias: float,
    ) -> float:
        normalized = re.findall(r"\b\w+\b", text.lower())
        pos_hits = sum(1 for token in normalized if token in positives)
        neg_hits = sum(1 for token in normalized if token in negatives)
        magnitude = max(1, pos_hits + neg_hits)
        raw_score = (pos_hits - neg_hits) / magnitude
        return _clamp_score(raw_score + bias)

    def _summarize_text(self, text: str) -> str:
        cleaned = text.strip()
        if len(cleaned) <= 180:
            return cleaned
        return cleaned[:177].rsplit(" ", 1)[0] + "..."

    def _normalize_bias(self, value: float) -> float:
        if not isinstance(value, (int, float)):
            return 0.0
        return _clamp_score(float(value))

    def _normalize_symbol(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return value.strip().upper()

    async def _publish_observations(self, observations: List[SentimentPayload]) -> None:
        for payload in observations:
            data = payload.model_dump()
            try:
                published = await message_queue.publish(Channels.SENTIMENT, data)
            except Exception as exc:
                self._log_system_event(
                    "error",
                    "Sentiment publish failed",
                    {"source": payload.source, "error": str(exc)},
                )
                continue

            if published:
                self._log_system_event(
                    "debug",
                    "Sentiment payload published",
                    {"source": payload.source, "symbol": payload.symbol},
                )
            else:
                self._log_system_event(
                    "warning",
                    "Message queue rejected sentiment payload",
                    {"source": payload.source, "symbol": payload.symbol},
                )

    def _log_system_event(
        self, level: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        sanitized = details or {}
        log_method = getattr(logger, level, logger.info)
        log_method("%s | %s", message, sanitized)
        try:
            log_system_event.delay(level, self.name, message, sanitized)
        except Exception as exc:
            logger.warning("Failed to enqueue system log: %s", exc)


sentiment_agent = SentimentAgent()
