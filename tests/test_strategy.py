import pandas as pd

from bot.strategy import RsiEmaStrategy, Signal, StrategyConfig


def frame(close, ema_vals, rsi_vals):
    idx = pd.date_range("2026-11-02 09:15", periods=len(close), freq="5min", tz="Asia/Kolkata")
    return pd.DataFrame({"close": close, "ema": ema_vals, "rsi": rsi_vals}, index=idx)


S = RsiEmaStrategy(StrategyConfig(rsi_buy=30, rsi_sell=70))


def test_buy_on_rsi_cross_above_ema():
    df = frame([100, 101], [99, 99], [28, 31])
    assert S.signal_at(df, 1, in_position=False) == Signal.BUY


def test_no_buy_below_ema():
    df = frame([100, 98], [99, 99], [28, 31])
    assert S.signal_at(df, 1, in_position=False) == Signal.HOLD


def test_no_buy_without_cross():
    df = frame([100, 101], [99, 99], [31, 35])
    assert S.signal_at(df, 1, in_position=False) == Signal.HOLD


def test_exit_rules():
    assert S.signal_at(frame([100, 101], [99, 99], [60, 71]), 1, True) == Signal.EXIT
    assert S.signal_at(frame([100, 98], [99, 99], [60, 50]), 1, True) == Signal.EXIT
    assert S.signal_at(frame([100, 101], [99, 99], [60, 50]), 1, True) == Signal.HOLD


def test_hold_during_warmup():
    df = frame([100, 101], [float("nan"), 99], [28, 31])
    assert S.signal_at(df, 0, in_position=False) == Signal.HOLD
    df = frame([100, 101], [99, float("nan")], [28, 31])
    assert S.signal_at(df, 1, in_position=False) == Signal.HOLD
