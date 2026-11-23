"""Risk limits. Checked BEFORE every entry order, never after."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable


@dataclass
class RiskConfig:
    max_trades_per_day: int = 5          # entries per day, across all symbols
    max_loss_per_day: float = 2000.0     # stop entering once realised loss hits this
    max_position_value: float = 50000.0  # capital per position
    stop_loss_pct: float = 0.01          # 1% below entry
    target_pct: float = 0.02             # 2% above entry


class RiskManager:
    def __init__(self, cfg: RiskConfig, kill_switch: Callable[[], bool] = lambda: False) -> None:
        self.cfg = cfg
        self.kill_switch = kill_switch
        self.day: date | None = None
        self.trades_today = 0
        self.realised_pnl_today = 0.0

    def _roll(self, d: date) -> None:
        if d != self.day:
            self.day = d
            self.trades_today = 0
            self.realised_pnl_today = 0.0

    def can_enter(self, d: date, price: float) -> tuple[bool, str]:
        self._roll(d)
        if self.kill_switch():
            return False, "kill switch is ON"
        if self.trades_today >= self.cfg.max_trades_per_day:
            return False, f"max trades per day reached ({self.cfg.max_trades_per_day})"
        if self.realised_pnl_today <= -abs(self.cfg.max_loss_per_day):
            return False, f"max daily loss reached ({self.realised_pnl_today:.2f})"
        if self.position_size(price) < 1:
            return False, "position size < 1 share at this price"
        return True, "ok"

    def position_size(self, price: float) -> int:
        if price <= 0:
            return 0
        return math.floor(self.cfg.max_position_value / price)

    def record_entry(self, d: date) -> None:
        self._roll(d)
        self.trades_today += 1

    def record_exit(self, d: date, pnl: float) -> None:
        self._roll(d)
        self.realised_pnl_today += pnl

    def stop_price(self, entry: float) -> float:
        return entry * (1 - self.cfg.stop_loss_pct)

    def target_price(self, entry: float) -> float:
        return entry * (1 + self.cfg.target_pct)
