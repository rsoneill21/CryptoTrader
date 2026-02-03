"""Utility helpers for computing standard technical indicators."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from pydantic import BaseModel, Field, validator


class _SeriesPayload(BaseModel):
    """Validates a sequence of prices before converting to a :class:`pd.Series`."""

    values: Sequence[float] = Field(..., min_length=1)

    @validator("values", pre=True)
    def _ensure_list(cls, value: Sequence[float]) -> list[float]:
        return list(value)


class _WindowModel(BaseModel):
    """Common window configuration for rolling indicators."""

    window: int = Field(gt=0)


class _MacdModel(BaseModel):
    """Configuration validation for MACD-specific parameters."""

    fast_window: int = Field(gt=0)
    slow_window: int = Field(gt=0)
    signal_window: int = Field(gt=0)

    @validator("slow_window")
    def _slow_gt_fast(cls, value: int, values: dict[str, int]) -> int:
        fast_value = values.get("fast_window")
        if fast_value is not None and value <= fast_value:
            raise ValueError("slow_window must be greater than fast_window")
        return value


class _BollingerModel(BaseModel):
    """Validates Bollinger Band window and multiplier settings."""

    window: int = Field(gt=0)
    std_dev_multiplier: float = Field(gt=0)


def _prepare_series(values: Sequence[float]) -> Series:
    """Convert the input into a float-backed pandas Series after validation."""

    payload = _SeriesPayload(values=values)
    return pd.Series(payload.values, dtype=float)


GREEN_SIDE = "#00d26a"
RED_SIDE = "#ff4757"
NEUTRAL_SIDE = "#9ca3af"
SIDE_COLOR_MAP = {
    "buy": GREEN_SIDE,
    "long": GREEN_SIDE,
    "sell": RED_SIDE,
    "short": RED_SIDE,
}


def side_color(side: Optional[str]) -> str:
    """Return a neutral color unless a known buy/long or sell/short side is provided."""

    if not side:
        return NEUTRAL_SIDE

    return SIDE_COLOR_MAP.get(side.lower(), NEUTRAL_SIDE)


def simple_moving_average(values: Sequence[float], window: int = 20) -> Series:
    """Return the simple moving average (SMA) over the requested window."""

    series = _prepare_series(values)
    validated_window = _WindowModel(window=window)
    return series.rolling(window=validated_window.window, min_periods=validated_window.window).mean()


def exponential_moving_average(values: Sequence[float], window: int = 20) -> Series:
    """Return the exponential moving average (EMA) over the requested window."""

    series = _prepare_series(values)
    validated_window = _WindowModel(window=window)
    return series.ewm(span=validated_window.window, adjust=False).mean()


def relative_strength_index(values: Sequence[float], window: int = 14) -> Series:
    """Return the Relative Strength Index (RSI) computed over the requested window."""

    series = _prepare_series(values)
    validated_window = _WindowModel(window=window)
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.rolling(window=validated_window.window, min_periods=validated_window.window).mean()
    avg_loss = loss.rolling(window=validated_window.window, min_periods=validated_window.window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    zero_loss_mask = avg_loss == 0
    rsi = rsi.where(~zero_loss_mask, 100.0)

    zero_gain_loss_mask = zero_loss_mask & (avg_gain == 0)
    return rsi.where(~zero_gain_loss_mask, 50.0)


def moving_average_convergence_divergence(
    values: Sequence[float], fast_window: int = 12, slow_window: int = 26, signal_window: int = 9
) -> DataFrame:
    """Return MACD line, signal line, and histogram as columns in a DataFrame."""

    series = _prepare_series(values)
    validated = _MacdModel(
        fast_window=fast_window,
        slow_window=slow_window,
        signal_window=signal_window,
    )

    fast_ema = series.ewm(span=validated.fast_window, adjust=False).mean()
    slow_ema = series.ewm(span=validated.slow_window, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=validated.signal_window, adjust=False).mean()
    histogram = macd_line - signal_line

    return DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }
    )


def bollinger_bands(
    values: Sequence[float], window: int = 20, std_dev_multiplier: float = 2.0
) -> DataFrame:
    """Return Bollinger Bands (upper, middle, lower) using the given window and multiplier."""

    series = _prepare_series(values)
    validated = _BollingerModel(window=window, std_dev_multiplier=std_dev_multiplier)
    middle_band = series.rolling(window=validated.window, min_periods=validated.window).mean()
    std_dev = series.rolling(window=validated.window, min_periods=validated.window).std()

    upper_band = middle_band + (validated.std_dev_multiplier * std_dev)
    lower_band = middle_band - (validated.std_dev_multiplier * std_dev)

    return DataFrame(
        {
            "upper": upper_band,
            "middle": middle_band,
            "lower": lower_band,
        }
    )


__all__ = [
    "simple_moving_average",
    "exponential_moving_average",
    "relative_strength_index",
    "moving_average_convergence_divergence",
    "bollinger_bands",
    "side_color",
]
