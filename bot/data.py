"""Candle data: CSV files, Yahoo Finance (optional), and synthetic demo data.

All functions return a DataFrame indexed by tz-aware IST candle *start* time
with columns: open, high, low, close, volume.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd

from .market_hours import IST

COLUMNS = ["open", "high", "low", "close", "volume"]


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):  # newer yfinance returns (field, ticker)
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "adj close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"adj close": "close"})
    missing = [c for c in ["open", "high", "low", "close"] if c not in df.columns]
    if missing:
        raise ValueError(f"candle data is missing columns: {missing}")
    if "volume" not in df.columns:
        df["volume"] = 0

    idx = pd.DatetimeIndex(pd.to_datetime(df.index))
    idx = idx.tz_localize(IST) if idx.tz is None else idx.tz_convert(IST)
    df.index = idx
    df.index.name = "timestamp"
    df = df[COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["open", "high", "low", "close"])


def load_csv(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path)
    for col in ("timestamp", "datetime", "date", "Datetime", "Date"):
        if col in raw.columns:
            raw = raw.set_index(col)
            break
    else:
        raise ValueError("CSV needs a timestamp/datetime/date column")
    return normalise(raw)


def fetch_yfinance(symbol: str, interval: str = "5m", period: str = "30d") -> pd.DataFrame:
    """Free, delayed data — fine for backtests and demos, NOT for real trading.
    Yahoo limits intraday history (5m candles: about the last 60 days).
    NSE symbols need the .NS suffix, e.g. RELIANCE.NS."""
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pip install yfinance to download data") from e
    df = yf.download(symbol, interval=interval, period=period, progress=False,
                     auto_adjust=False, threads=False)
    if df is None or df.empty:
        raise RuntimeError(f"no data returned for {symbol}")
    return normalise(df)


def infer_interval(df: pd.DataFrame) -> pd.Timedelta:
    diffs = df.index.to_series().diff().dropna()
    diffs = diffs[diffs < pd.Timedelta(hours=6)]  # ignore overnight gaps
    if diffs.empty:
        return pd.Timedelta(minutes=5)
    return diffs.mode().iloc[0]


def drop_incomplete(df: pd.DataFrame, interval: pd.Timedelta, now: datetime) -> pd.DataFrame:
    """Keep only candles that have fully closed. Acting on a still-forming candle
    is a classic live-trading bug: the signal can disappear before the candle ends."""
    return df[df.index + interval <= pd.Timestamp(now)]


def make_sample(days: int = 20, interval_minutes: int = 5, seed: int = 7,
                start_price: float = 1000.0, start: str = "2026-10-01") -> pd.DataFrame:
    """SYNTHETIC random-walk candles inside NSE hours. For demos and tests only."""
    rng = np.random.default_rng(seed)
    rows, price = [], start_price
    d = pd.Timestamp(start).date()
    made = 0
    while made < days:
        if d.weekday() < 5:
            t = datetime.combine(d, time(9, 15), tzinfo=IST)
            end = datetime.combine(d, time(15, 30), tzinfo=IST)
            price *= 1 + rng.normal(0, 0.004)  # overnight gap
            drift = rng.normal(0, 0.0004)
            while t < end:
                o = price
                c = o * (1 + drift + rng.normal(0, 0.0025))
                h = max(o, c) * (1 + abs(rng.normal(0, 0.001)))
                l = min(o, c) * (1 - abs(rng.normal(0, 0.001)))
                rows.append((t, o, h, l, c, int(rng.integers(1_000, 50_000))))
                price = c
                t += timedelta(minutes=interval_minutes)
            made += 1
        d += timedelta(days=1)
    df = pd.DataFrame(rows, columns=["timestamp", *COLUMNS]).set_index("timestamp")
    return normalise(df)
