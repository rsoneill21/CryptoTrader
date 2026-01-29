"""Pattern detection helpers for CryptoTrader."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from pydantic import BaseModel, Field


class Candle(BaseModel):
    """Validated representation of a single OHLC candle."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trades: Optional[int] = None

    class Config:
        arbitrary_types_allowed = True


class CandleSeries(BaseModel):
    """Wraps a series of candles and enforces a minimum length."""

    candles: List[Candle] = Field(..., min_items=1)


class LevelType(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


class SupportResistanceLevel(BaseModel):
    """Represents a horizontal support or resistance level."""

    level: Decimal
    level_type: LevelType
    touches: int
    strength: float
    last_touch: datetime

    class Config:
        arbitrary_types_allowed = True


class SupportResistanceConfig(BaseModel):
    lookback: int = Field(60, ge=3)
    tolerance: float = Field(0.0025, gt=0)
    min_touches: int = Field(3, ge=2)


class TrendType(str, Enum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class TrendPoint(BaseModel):
    timestamp: datetime
    price: Decimal


class TrendLine(BaseModel):
    slope: float
    intercept: float
    trend_type: TrendType
    confidence: float
    points: List[TrendPoint]


class TrendLineConfig(BaseModel):
    lookback: int = Field(72, ge=3)
    min_points: int = Field(3, ge=3)
    error_tolerance: float = Field(0.02, gt=0)


class CandlestickPatternType(str, Enum):
    HAMMER = "hammer"
    SHOOTING_STAR = "shooting_star"
    BULLISH_ENGULFING = "bullish_engulfing"
    BEARISH_ENGULFING = "bearish_engulfing"
    DOJI = "doji"
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"


class PatternSentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class CandlestickPattern(BaseModel):
    pattern_type: CandlestickPatternType
    sentiment: PatternSentiment
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class _PivotBucket:
    level: Decimal
    level_type: LevelType
    samples: List[Tuple[Decimal, datetime]] = field(default_factory=list)


def _abs_decimal(value: Decimal) -> Decimal:
    return value.copy_abs()


def _candle_range(candle: Candle) -> Decimal:
    return candle.high - candle.low


def _prepare_series(candles: Sequence[Candle]) -> List[Candle]:
    payload = CandleSeries(candles=list(candles))
    return payload.candles


def _pivot_candidates(candles: List[Candle]) -> List[Tuple[LevelType, Decimal, datetime]]:
    candidates: List[Tuple[LevelType, Decimal, datetime]] = []
    if len(candles) < 3:
        return candidates
    for idx in range(1, len(candles) - 1):
        previous, current, next_ = candles[idx - 1], candles[idx], candles[idx + 1]
        if current.low < previous.low and current.low < next_.low:
            candidates.append((LevelType.SUPPORT, current.low, current.timestamp))
        if current.high > previous.high and current.high > next_.high:
            candidates.append((LevelType.RESISTANCE, current.high, current.timestamp))
    return candidates


def _cluster_levels(
    candidates: Iterable[Tuple[LevelType, Decimal, datetime]], tolerance: Decimal
) -> List[_PivotBucket]:
    buckets: List[_PivotBucket] = []
    for level_type, price, timestamp in candidates:
        inserted = False
        for bucket in buckets:
            if bucket.level_type != level_type:
                continue
            if _abs_decimal(bucket.level - price) <= tolerance:
                bucket.level = (bucket.level + price) / Decimal(2)
                bucket.samples.append((price, timestamp))
                inserted = True
                break
        if not inserted:
            buckets.append(_PivotBucket(level=price, level_type=level_type, samples=[(price, timestamp)]))
    return buckets


def _count_touches(level: Decimal, candles: List[Candle], tolerance: Decimal) -> Tuple[int, Optional[datetime]]:
    touches = 0
    last_touch: Optional[datetime] = None
    for candle in candles:
        if (
            _abs_decimal(candle.low - level) <= tolerance
            or _abs_decimal(candle.high - level) <= tolerance
            or _abs_decimal(candle.close - level) <= tolerance
        ):
            touches += 1
            if last_touch is None or candle.timestamp > last_touch:
                last_touch = candle.timestamp
    return touches, last_touch


def detect_support_resistance(
    candles: Sequence[Candle], *, lookback: int = 60, tolerance: float = 0.0025, min_touches: int = 3
) -> List[SupportResistanceLevel]:
    """Detect recurring horizontal support and resistance levels in an OHLC series."""

    config = SupportResistanceConfig(lookback=lookback, tolerance=tolerance, min_touches=min_touches)
    series = _prepare_series(candles)
    window = series[-config.lookback :]
    if len(window) < 3:
        return []

    max_close = max(c.close for c in window)
    min_close = min(c.close for c in window)
    price_range = max_close - min_close
    reference = price_range if price_range > Decimal(0) else max_close if max_close > Decimal(0) else Decimal(1)
    tolerance_value = reference * Decimal(str(config.tolerance))
    if tolerance_value == Decimal(0):
        tolerance_value = Decimal("0.0001")

    candidates = _pivot_candidates(window)
    clusters = _cluster_levels(candidates, tolerance_value)
    levels: List[SupportResistanceLevel] = []

    for bucket in clusters:
        touches, last_touch = _count_touches(bucket.level, window, tolerance_value)
        if touches < config.min_touches or last_touch is None:
            continue
        strength = touches / len(window)
        levels.append(
            SupportResistanceLevel(
                level=bucket.level,
                level_type=bucket.level_type,
                touches=touches,
                strength=strength,
                last_touch=last_touch,
            )
        )

    return sorted(levels, key=lambda entry: entry.touches, reverse=True)


def _pivot_points(candles: List[Candle], trend_type: TrendType) -> List[Candle]:
    points: List[Candle] = []
    if len(candles) < 3:
        return points
    for idx in range(1, len(candles) - 1):
        previous, current, next_ = candles[idx - 1], candles[idx], candles[idx + 1]
        if trend_type == TrendType.ASCENDING and current.low < previous.low and current.low < next_.low:
            points.append(current)
        if trend_type == TrendType.DESCENDING and current.high > previous.high and current.high > next_.high:
            points.append(current)
    return points


def _build_trend_line(
    pivots: List[Candle], trend_type: TrendType, config: TrendLineConfig
) -> Optional[TrendLine]:
    if len(pivots) < config.min_points:
        return None

    values = [float(point.low if trend_type == TrendType.ASCENDING else point.high) for point in pivots]
    positions = np.arange(len(pivots), dtype=float)
    slope, intercept = np.polyfit(positions, values, 1)
    predicted = slope * positions + intercept
    deviations = np.abs(predicted - values)
    scale = max(float(max(values) - min(values)), 1.0)
    normalized_error = float(np.max(deviations)) / scale
    if normalized_error > config.error_tolerance:
        return None

    confidence = max(0.0, 1.0 - normalized_error)
    points = [TrendPoint(timestamp=point.timestamp, price=point.low if trend_type == TrendType.ASCENDING else point.high) for point in pivots]
    return TrendLine(
        slope=slope,
        intercept=intercept,
        trend_type=trend_type,
        confidence=confidence,
        points=points,
    )


def detect_trend_lines(
    candles: Sequence[Candle], *, lookback: int = 72, min_points: int = 3, error_tolerance: float = 0.02
) -> List[TrendLine]:
    """Identify ascending and descending trend lines from pivot points."""

    config = TrendLineConfig(lookback=lookback, min_points=min_points, error_tolerance=error_tolerance)
    series = _prepare_series(candles)
    window = series[-config.lookback :]
    if len(window) < config.min_points:
        return []

    lines: List[TrendLine] = []
    for trend_type in (TrendType.ASCENDING, TrendType.DESCENDING):
        pivots = _pivot_points(window, trend_type)
        line = _build_trend_line(pivots, trend_type, config)
        if line is not None:
            lines.append(line)

    return lines


def _body_size(candle: Candle) -> Decimal:
    return _abs_decimal(candle.close - candle.open)


def _upper_shadow(candle: Candle) -> Decimal:
    return candle.high - max(candle.open, candle.close)


def _lower_shadow(candle: Candle) -> Decimal:
    return min(candle.open, candle.close) - candle.low


def _body_ratio(candle: Candle) -> float:
    range_ = _candle_range(candle)
    if range_ == Decimal(0):
        return 0.0
    return float(_body_size(candle) / range_)


def _is_bullish(candle: Candle) -> bool:
    return candle.close > candle.open


def _is_bearish(candle: Candle) -> bool:
    return candle.close < candle.open


def _is_indecisive(candle: Candle, threshold: float = 0.15) -> bool:
    return _body_ratio(candle) <= threshold


def _pattern_confidence(base: float) -> float:
    return max(0.0, min(1.0, base))


def _record_pattern(
    pattern_type: CandlestickPatternType,
    sentiment: PatternSentiment,
    candle: Candle,
    confidence: float,
    details: Dict[str, Any],
) -> CandlestickPattern:
    return CandlestickPattern(
        pattern_type=pattern_type,
        sentiment=sentiment,
        timestamp=candle.timestamp,
        confidence=_pattern_confidence(confidence),
        details=details,
    )


def detect_candlestick_patterns(candles: Sequence[Candle]) -> List[CandlestickPattern]:
    """Scan a candle series for common reversal and continuation formations."""

    series = _prepare_series(candles)
    if len(series) < 2:
        return []

    patterns: List[CandlestickPattern] = []
    for idx, candle in enumerate(series):
        body_ratio = _body_ratio(candle)
        lower_shadow = float(_lower_shadow(candle))
        upper_shadow = float(_upper_shadow(candle))
        body_size = float(_body_size(candle))
        candle_range = float(_candle_range(candle)) or 1.0

        # Hammer
        if body_size > 0 and lower_shadow >= 2 * body_size and upper_shadow <= 0.5 * body_size and body_ratio <= 0.35:
            confidence = lower_shadow / (lower_shadow + upper_shadow + 1e-6)
            patterns.append(
                _record_pattern(
                    CandlestickPatternType.HAMMER,
                    PatternSentiment.BULLISH,
                    candle,
                    confidence,
                    {
                        "body_ratio": round(body_ratio, 3),
                        "lower_shadow": round(lower_shadow, 6),
                        "upper_shadow": round(upper_shadow, 6),
                    },
                )
            )

        # Shooting star
        if body_size > 0 and upper_shadow >= 2 * body_size and lower_shadow <= 0.5 * body_size and body_ratio <= 0.35:
            confidence = upper_shadow / (upper_shadow + lower_shadow + 1e-6)
            patterns.append(
                _record_pattern(
                    CandlestickPatternType.SHOOTING_STAR,
                    PatternSentiment.BEARISH,
                    candle,
                    confidence,
                    {
                        "body_ratio": round(body_ratio, 3),
                        "upper_shadow": round(upper_shadow, 6),
                        "lower_shadow": round(lower_shadow, 6),
                    },
                )
            )

        # Engulfing patterns require a prior candle
        if idx >= 1:
            prev = series[idx - 1]
            prev_body = float(_body_size(prev)) or 1e-6
            if _is_bearish(prev) and _is_bullish(candle) and body_size > prev_body:
                details = {
                    "prev_close": float(prev.close),
                    "prev_open": float(prev.open),
                    "curr_close": float(candle.close),
                    "curr_open": float(candle.open),
                }
                patterns.append(
                    _record_pattern(
                        CandlestickPatternType.BULLISH_ENGULFING,
                        PatternSentiment.BULLISH,
                        candle,
                        body_size / (prev_body + 1e-6),
                        details,
                    )
                )
            if _is_bullish(prev) and _is_bearish(candle) and body_size > prev_body:
                details = {
                    "prev_close": float(prev.close),
                    "prev_open": float(prev.open),
                    "curr_close": float(candle.close),
                    "curr_open": float(candle.open),
                }
                patterns.append(
                    _record_pattern(
                        CandlestickPatternType.BEARISH_ENGULFING,
                        PatternSentiment.BEARISH,
                        candle,
                        body_size / (prev_body + 1e-6),
                        details,
                    )
                )

        # Morning/evening star
        if idx >= 2:
            first, second, third = series[idx - 2], series[idx - 1], candle
            if _is_bearish(first) and _is_indecisive(second) and _is_bullish(third):
                midpoint = float((first.open + first.close) / Decimal(2))
                if float(third.close) > midpoint and float(third.close) > float(second.close):
                    details = {
                        "first_body": round(float(_body_size(first)), 6),
                        "third_body": round(body_size, 6),
                    }
                    patterns.append(
                        _record_pattern(
                            CandlestickPatternType.MORNING_STAR,
                            PatternSentiment.BULLISH,
                            third,
                            (body_size + float(_body_size(first))) / (2 * candle_range),
                            details,
                        )
                    )
            if _is_bullish(first) and _is_indecisive(second) and _is_bearish(third):
                midpoint = float((first.open + first.close) / Decimal(2))
                if float(third.close) < midpoint and float(third.close) < float(second.close):
                    details = {
                        "first_body": round(float(_body_size(first)), 6),
                        "third_body": round(body_size, 6),
                    }
                    patterns.append(
                        _record_pattern(
                            CandlestickPatternType.EVENING_STAR,
                            PatternSentiment.BEARISH,
                            third,
                            (body_size + float(_body_size(first))) / (2 * candle_range),
                            details,
                        )
                    )

        # Doji
        if _is_indecisive(candle, threshold=0.1):
            details = {
                "body_ratio": round(body_ratio, 4),
                "range": round(float(candle_range), 6),
            }
            patterns.append(
                _record_pattern(
                    CandlestickPatternType.DOJI,
                    PatternSentiment.NEUTRAL,
                    candle,
                    1.0 - min(body_ratio, 0.99),
                    details,
                )
            )

    return patterns


__all__ = [
    "Candle",
    "CandlestickPattern",
    "CandlestickPatternType",
    "TrendLine",
    "TrendLineConfig",
    "TrendType",
    "SupportResistanceLevel",
    "detect_candlestick_patterns",
    "detect_support_resistance",
    "detect_trend_lines",
]
