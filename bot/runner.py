"""Paper-trading loop: polls candles, acts on closed candles, never trades real money.

Designed to survive the things that killed the 2021 bot:
  * a data/network error is retried and logged; it does not stop the bot
  * only fully closed candles are used (no signals from a half-formed candle)
  * outside market hours it sleeps instead of exiting
  * open paper positions are saved to disk and survive a restart
  * kill switch (state/KILL file or KILL_SWITCH=1) squares off and blocks entries
"""

from __future__ import annotations

import json
import logging
import time as _time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from .alerts import Alerts
from .broker import PaperBroker
from .config import Config
from .data import drop_incomplete, fetch_yfinance
from .market_hours import now_ist
from .risk import RiskManager
from .strategy import RsiEmaStrategy, Signal

log = logging.getLogger("bot.paper")

Fetcher = Callable[[str, str, str], pd.DataFrame]


class PaperTrader:
    def __init__(self, cfg: Config, fetcher: Fetcher = fetch_yfinance,
                 clock: Callable[[], datetime] = now_ist, alerts: Alerts | None = None) -> None:
        self.cfg = cfg
        self.fetch = fetcher
        self.clock = clock
        self.alerts = alerts or Alerts()
        self.strategy = RsiEmaStrategy(cfg.strategy)
        self.risk = RiskManager(cfg.risk, kill_switch=cfg.kill_switch_on)
        self.interval = pd.Timedelta(cfg.interval.replace("m", "min") if cfg.interval.endswith("m") else cfg.interval)
        self.state_path = Path(cfg.state_dir) / "paper_state.json"
        self.last_processed: dict[str, str] = {}
        self.last_price: dict[str, float] = {}
        self.summary_sent_for: str | None = None
        self.kill_announced = False
        self.broker = PaperBroker(cfg.costs, cfg.starting_cash)
        self._load_state()

    # ---------- state ----------
    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text())
        self.broker = PaperBroker.from_dict(data["broker"], self.cfg.costs)
        self.last_processed = data.get("last_processed", {})
        self.last_price = data.get("last_price", {})
        self.summary_sent_for = data.get("summary_sent_for")
        r = data.get("risk", {})
        if r.get("day"):
            self.risk.day = date.fromisoformat(r["day"])
            self.risk.trades_today = r.get("trades_today", 0)
            self.risk.realised_pnl_today = r.get("realised_pnl_today", 0.0)
        log.info("restored state: %d open position(s), cash %.2f",
                 len(self.broker.positions), self.broker.cash)

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "broker": self.broker.to_dict(),
            "last_processed": self.last_processed,
            "last_price": self.last_price,
            "summary_sent_for": self.summary_sent_for,
            "risk": {"day": self.risk.day.isoformat() if self.risk.day else None,
                     "trades_today": self.risk.trades_today,
                     "realised_pnl_today": self.risk.realised_pnl_today},
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.state_path)  # atomic: a crash mid-write can't corrupt state

    # ---------- helpers ----------
    def _fetch_with_retry(self, symbol: str, attempts: int = 3) -> pd.DataFrame:
        delay = 2.0
        for n in range(1, attempts + 1):
            try:
                return self.fetch(symbol, self.cfg.interval, self.cfg.history_period)
            except Exception as e:  # noqa: BLE001
                if n == attempts:
                    raise
                log.warning("%s fetch failed (%s), retry %d/%d in %.0fs", symbol, e, n, attempts - 1, delay)
                _time.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    def _exit(self, symbol: str, price: float, ts: datetime, reason: str) -> None:
        trade = self.broker.sell(symbol, price, ts, reason)
        self.risk.record_exit(ts.date(), trade.net_pnl)
        self.alerts.send(f"PAPER SELL {symbol} x{trade.qty} @ {trade.exit_fill:.2f} "
                         f"({reason}) net P&L {trade.net_pnl:+.2f}")

    def _square_off_all(self, ts: datetime, reason: str) -> None:
        for sym in list(self.broker.positions):
            price = self.last_price.get(sym, self.broker.positions[sym].entry_raw)
            self._exit(sym, price, ts, reason)

    # ---------- one loop iteration ----------
    def step(self) -> str:
        now = self.clock()
        today = now.date()
        hours = self.cfg.hours

        if self.cfg.kill_switch_on():
            if self.broker.positions:
                self._square_off_all(now, "kill-switch")
                self._save_state()
            if not self.kill_announced:
                self.alerts.send("Kill switch is ON — all paper positions closed, no new entries.")
                self.kill_announced = True
            return "killed"
        self.kill_announced = False

        if not hours.is_trading_day(today) or now.time() < hours.open:
            return "closed"

        if now.time() >= hours.close:
            if self.broker.positions:
                self._square_off_all(now, "square-off (market closed)")
            if self.summary_sent_for != today.isoformat():
                todays = [t for t in self.broker.trades if t.exit_time.date() == today]
                pnl = sum(t.net_pnl for t in todays)
                self.alerts.send(f"Day summary {today}: {len(todays)} paper trade(s), "
                                 f"net P&L {pnl:+.2f}, cash {self.broker.cash:.2f}")
                self.summary_sent_for = today.isoformat()
            self._save_state()
            return "after-close"

        for symbol in self.cfg.symbols:
            try:
                self._step_symbol(symbol, now)
            except Exception as e:  # noqa: BLE001 — one bad symbol must not stop the others
                log.exception("error on %s", symbol)
                self.alerts.send(f"Error on {symbol}: {e}", dedupe_key=f"err:{symbol}")
        self._save_state()
        return "open"

    def _step_symbol(self, symbol: str, now: datetime) -> None:
        df = drop_incomplete(self._fetch_with_retry(symbol), self.interval, now)
        if len(df) < self.strategy.warmup_bars:
            log.info("%s: only %d closed candles, waiting for warm-up", symbol, len(df))
            return
        last_ts = df.index[-1]
        self.last_price[symbol] = float(df["close"].iloc[-1])
        if self.last_processed.get(symbol) == last_ts.isoformat():
            return  # no new closed candle since last check

        df = self.strategy.add_indicators(df)
        i = len(df) - 1
        bar = df.iloc[i]
        bar_end = (last_ts + self.interval).to_pydatetime()
        hours = self.cfg.hours
        pos = self.broker.positions.get(symbol)
        log.info("%s %s close=%.2f ema=%.2f rsi=%.1f pos=%s", symbol, last_ts.strftime("%H:%M"),
                 bar["close"], bar["ema"], bar["rsi"], "yes" if pos else "no")

        if pos is not None:
            if last_ts >= pd.Timestamp(pos.entry_time):  # candles after the entry only
                if bar["low"] <= pos.stop:
                    self._exit(symbol, min(pos.stop, bar["open"]), bar_end, "stop-loss")
                elif bar["high"] >= pos.target:
                    self._exit(symbol, max(pos.target, bar["open"]), bar_end, "target")
            if symbol in self.broker.positions:
                if hours.must_square_off(bar_end):
                    self._exit(symbol, bar["close"], bar_end, "square-off")
                elif self.strategy.signal_at(df, i, in_position=True) == Signal.EXIT:
                    self._exit(symbol, bar["close"], bar_end, "signal")
        elif self.strategy.signal_at(df, i, in_position=False) == Signal.BUY:
            if not hours.can_enter(bar_end):
                log.info("%s BUY signal ignored: past last entry time", symbol)
            else:
                price = float(bar["close"])
                ok, why = self.risk.can_enter(bar_end.date(), price)  # risk check BEFORE order
                if not ok:
                    self.alerts.send(f"BUY {symbol} blocked by risk: {why}", dedupe_key=f"risk:{why}")
                else:
                    qty = self.risk.position_size(price)
                    p = self.broker.buy(symbol, qty, price, bar_end,
                                        self.risk.stop_price(price), self.risk.target_price(price))
                    self.risk.record_entry(bar_end.date())
                    self.alerts.send(f"PAPER BUY {symbol} x{qty} @ {p.entry_fill:.2f} "
                                     f"SL {p.stop:.2f} TGT {p.target:.2f}")

        self.last_processed[symbol] = last_ts.isoformat()

    # ---------- forever ----------
    def run_forever(self) -> None:
        self.alerts.send(f"Paper bot started: {', '.join(self.cfg.symbols)} "
                         f"({self.cfg.interval}). No real orders will be placed.")
        while True:
            try:
                status = self.step()
            except Exception as e:  # noqa: BLE001
                log.exception("loop error")
                self.alerts.send(f"Loop error: {e}", dedupe_key="loop")
                status = "error"
            sleep_for = self.cfg.poll_seconds if status in ("open", "error") else 60
            log.debug("status=%s, sleeping %ss", status, sleep_for)
            _time.sleep(sleep_for)
