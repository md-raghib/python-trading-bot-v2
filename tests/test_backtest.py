import pandas as pd
import pytest

from bot.backtest import run_backtest
from bot.costs import CostModel
from bot.data import make_sample
from bot.market_hours import MarketHours
from bot.risk import RiskConfig
from bot.strategy import RsiEmaStrategy, Signal, StrategyConfig


def run(df, naive=False, risk=None, costs=None, strategy=None):
    return run_backtest(df, "TEST", strategy or RsiEmaStrategy(StrategyConfig(rsi_buy=45, rsi_sell=60)),
                        risk or RiskConfig(), costs or CostModel(), MarketHours(), naive=naive)


@pytest.fixture(scope="module")
def sample():
    return make_sample(days=30, seed=11)


def test_trades_happen_and_are_flat_each_day(sample):
    res = run(sample)
    assert len(res.trades) > 0
    for t in res.trades:
        assert t.entry_time.date() == t.exit_time.date()          # intraday only
        assert t.exit_time.time() <= pd.Timestamp("15:30").time()
        assert t.entry_time.time() < pd.Timestamp("15:00").time()  # no late entries


def test_honest_fills_on_next_candle_open(sample):
    """Every honest entry must happen at a candle open AFTER the signal candle."""
    strat = RsiEmaStrategy(StrategyConfig(rsi_buy=45, rsi_sell=60))
    res = run(sample, strategy=strat)
    ind = strat.add_indicators(sample)
    for t in res.trades:
        i = ind.index.get_loc(t.entry_time)
        assert strat.signal_at(ind, i - 1, in_position=False) == Signal.BUY


def test_costs_reduce_pnl(sample):
    free = run(sample, costs=CostModel(0, 0, 0, 0))
    paid = run(sample)
    assert len(free.trades) == len(paid.trades)
    assert paid.summary()["net_pnl"] < free.summary()["net_pnl"]
    assert paid.summary()["costs"] > 0


def test_risk_limit_respected(sample):
    res = run(sample, risk=RiskConfig(max_trades_per_day=1))
    per_day = pd.Series([t.entry_time.date() for t in res.trades]).value_counts()
    assert per_day.max() == 1
    assert res.summary()["blocked_by_risk"] >= 0


def test_naive_mode_runs_and_differs(sample):
    honest = run(sample).summary()
    naive = run(sample, naive=True).summary()
    assert naive["mode"] == "naive" and naive["costs"] == 0
    assert naive != honest


def test_summary_fields(sample):
    s = run(sample).summary()
    for k in ("trades", "win_rate_%", "net_pnl", "max_drawdown", "costs"):
        assert k in s
    assert s["max_drawdown"] <= 0
