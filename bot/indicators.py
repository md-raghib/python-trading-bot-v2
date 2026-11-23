"""Technical indicators.

Every indicator here is *causal*: the value at row i only uses rows 0..i.
That property is what keeps the backtest free of look-ahead bias, and
tests/test_indicators.py checks it.
"""

from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average. NaN until `period` values exist (warm-up)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (0-100). NaN during warm-up."""
    if period < 1:
        raise ValueError("period must be >= 1")
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder smoothing == EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))

    ready = avg_gain.notna() & avg_loss.notna()
    out[ready & (avg_loss == 0) & (avg_gain > 0)] = 100.0
    out[ready & (avg_loss == 0) & (avg_gain == 0)] = 50.0
    out[~ready] = float("nan")
    return out
