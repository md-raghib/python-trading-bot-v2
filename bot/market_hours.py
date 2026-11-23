"""NSE cash-market session times (IST). Holidays come from config.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class MarketHours:
    open: time = time(9, 15)
    close: time = time(15, 30)
    last_entry: time = time(15, 0)    # no new positions after this
    square_off: time = time(15, 15)   # close everything at/after this
    holidays: set[date] = field(default_factory=set)

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def _t(self, dt: datetime) -> time:
        return dt.astimezone(IST).time() if dt.tzinfo else dt.time()

    def is_open(self, dt: datetime) -> bool:
        d = dt.astimezone(IST).date() if dt.tzinfo else dt.date()
        return self.is_trading_day(d) and self.open <= self._t(dt) < self.close

    def can_enter(self, dt: datetime) -> bool:
        return self.is_open(dt) and self._t(dt) < self.last_entry

    def must_square_off(self, dt: datetime) -> bool:
        return self._t(dt) >= self.square_off


def now_ist() -> datetime:
    return datetime.now(IST)
