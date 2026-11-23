"""Bar-by-bar backtester.

Two modes, so the video can show the difference:
  honest (default): signal on candle i's close -> order fills at candle i+1's open,
                    with fees + slippage, stop/target checked inside each candle.
  naive:            signal AND fill on the same candle's close, zero costs —
                    the way many beginner bots (including my 2021 one) were tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .broker import PaperBroker, Trade
from .costs import ZERO_COSTS, CostModel
from .data import infer_interval
from .market_hours import MarketHours
from .risk import RiskConfig, RiskManager
from .strategy import RsiEmaStrategy, Signal


@dataclass
class BacktestResult:
    symbol: str
    mode: str
    trades: list[Trade]
    equity: pd.Series
    blocked: list[tuple[pd.Timestamp, str]] = field(default_factory=list)
    starting_cash: float = 100_000.0

    def summary(self) -> dict:
        n = len(self.trades)
        wins = sum(1 for t in self.trades if t.net_pnl > 0)
        net = sum(t.net_pnl for t in self.trades)
        peak = self.equity.cummax()
        dd = (self.equity - peak)
        max_dd = float(dd.min()) if len(dd) else 0.0
        max_dd_pct = float((dd / peak).min() * 100) if len(dd) else 0.0
        return {
            "symbol": self.symbol,
            "mode": self.mode,
            "trades": n,
            "win_rate_%": round(100 * wins / n, 1) if n else 0.0,
            "gross_pnl": round(sum(t.gross_pnl for t in self.trades), 2),
            "costs": round(sum(t.costs for t in self.trades), 2),
            "net_pnl": round(net, 2),
            "return_%": round(100 * net / self.starting_cash, 2),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_%": round(max_dd_pct, 2),
            "blocked_by_risk": len(self.blocked),
        }


def _exit_price_for_stop_target(bar: pd.Series, stop: float, target: float) -> tuple[float, str] | None:
    """If the candle touched stop or target, return (fill, reason).
    If it touched both, assume the stop hit first (conservative)."""
    hit_stop = bar["low"] <= stop
    hit_target = bar["high"] >= target
    if hit_stop:
        return (min(stop, bar["open"]), "stop-loss")  # gap below stop fills at open
    if hit_target:
        return (max(target, bar["open"]), "target")
    return None


def run_backtest(df: pd.DataFrame, symbol: str, strategy: RsiEmaStrategy,
                 risk_cfg: RiskConfig, costs: CostModel, hours: MarketHours,
                 naive: bool = False, starting_cash: float = 100_000.0) -> BacktestResult:
    if df.empty:
        raise ValueError("no candles to backtest")
    df = strategy.add_indicators(df)
    interval = infer_interval(df)
    broker = PaperBroker(ZERO_COSTS if naive else costs, starting_cash)
    risk = RiskManager(risk_cfg)
    blocked: list[tuple[pd.Timestamp, str]] = []
    equity: dict[pd.Timestamp, float] = {}

    idx = df.index
    days = [ts.date() for ts in idx]
    pending: Signal | None = None

    def try_enter(price: float, ts: pd.Timestamp) -> None:
        ok, why = risk.can_enter(ts.date(), price)
        if not ok:
            blocked.append((ts, why))
            return
        broker.buy(symbol, risk.position_size(price), price, ts,
                   risk.stop_price(price), risk.target_price(price))
        risk.record_entry(ts.date())

    def exit_(price: float, ts: pd.Timestamp, reason: str) -> None:
        trade = broker.sell(symbol, price, ts, reason)
        risk.record_exit(ts.date(), trade.net_pnl)

    for i in range(len(df)):
        ts, bar, d = idx[i], df.iloc[i], days[i]
        bar_end = ts + interval
        if i > 0 and d != days[i - 1]:
            pending = None  # never carry an order into the next day

        # 1) honest mode: execute yesterday's-candle signal at this candle's open
        if not naive and pending is not None:
            pos = broker.positions.get(symbol)
            if pending == Signal.BUY and pos is None and hours.can_enter(ts):
                try_enter(bar["open"], ts)
            elif pending == Signal.EXIT and pos is not None:
                exit_(bar["open"], ts, "signal")
            pending = None

        # 2) stop-loss / target inside this candle
        pos = broker.positions.get(symbol)
        if pos is not None and not (naive and pos.entry_time == ts):
            hit = _exit_price_for_stop_target(bar, pos.stop, pos.target)
            if hit:
                exit_(hit[0], ts, hit[1])

        # 3) intraday square-off
        pos = broker.positions.get(symbol)
        last_of_day = i == len(df) - 1 or days[i + 1] != d
        if pos is not None and (last_of_day or hours.must_square_off(bar_end)):
            exit_(bar["close"], ts, "square-off")
            pending = None
            equity[ts] = broker.equity({symbol: bar["close"]})
            continue

        # 4) decide on the closed candle
        pos = broker.positions.get(symbol)
        sig = strategy.signal_at(df, i, in_position=pos is not None)
        if naive:
            if sig == Signal.BUY and hours.can_enter(bar_end) and not last_of_day:
                try_enter(bar["close"], ts)
            elif sig == Signal.EXIT and pos is not None:
                exit_(bar["close"], ts, "signal")
        elif sig != Signal.HOLD and not last_of_day:
            if sig == Signal.BUY and not hours.can_enter(bar_end):
                pending = None
            else:
                pending = sig

        equity[ts] = broker.equity({symbol: bar["close"]})

    return BacktestResult(symbol, "naive" if naive else "honest", broker.trades,
                          pd.Series(equity, dtype=float), blocked, starting_cash)
