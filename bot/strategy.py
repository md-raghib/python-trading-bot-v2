"""RSI + EMA strategy (long-only, intraday).

Default rules — REPLACE these with the exact rules of your 2021 bot via config.yaml:
  BUY  when RSI crosses up through `rsi_buy` AND close is above the EMA
  EXIT when RSI reaches `rsi_sell` OR close falls below the EMA
Stop-loss / target / square-off are handled by the engine, not here.

Signals are decided on a *closed* candle and must be executed on a later
price (next candle's open in backtests). Never fill on the same candle the
signal was computed from — that is look-ahead bias.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from .indicators import ema, rsi


class Signal(str, Enum):
    BUY = "BUY"
    EXIT = "EXIT"
    HOLD = "HOLD"


@dataclass
class StrategyConfig:
    ema_period: int = 20
    rsi_period: int = 14
    rsi_buy: float = 30.0
    rsi_sell: float = 70.0


class RsiEmaStrategy:
    def __init__(self, cfg: StrategyConfig | None = None) -> None:
        self.cfg = cfg or StrategyConfig()

    @property
    def warmup_bars(self) -> int:
        return max(self.cfg.ema_period, self.cfg.rsi_period + 1) + 1

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema"] = ema(out["close"], self.cfg.ema_period)
        out["rsi"] = rsi(out["close"], self.cfg.rsi_period)
        return out

    def signal_at(self, df: pd.DataFrame, i: int, in_position: bool) -> Signal:
        """Signal for the candle at position i (uses rows <= i only)."""
        if i < 1:
            return Signal.HOLD
        row, prev = df.iloc[i], df.iloc[i - 1]
        needed = (row["ema"], row["rsi"], prev["rsi"])
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in needed):
            return Signal.HOLD  # indicator warm-up: not enough data yet

        c = self.cfg
        if not in_position:
            crossed_up = prev["rsi"] < c.rsi_buy <= row["rsi"]
            if crossed_up and row["close"] > row["ema"]:
                return Signal.BUY
            return Signal.HOLD

        if row["rsi"] >= c.rsi_sell or row["close"] < row["ema"]:
            return Signal.EXIT
        return Signal.HOLD
