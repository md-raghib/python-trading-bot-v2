import numpy as np
import pandas as pd
import pytest

from bot.data import make_sample
from bot.indicators import ema, rsi


def test_warmup_is_nan():
    s = pd.Series(np.arange(1, 30, dtype=float))
    assert ema(s, 10).iloc[:9].isna().all()
    assert not np.isnan(ema(s, 10).iloc[9])
    assert rsi(s, 14).iloc[:14].isna().all()


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 40, dtype=float))
    assert rsi(up, 14).dropna().eq(100).all()
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert rsi(down, 14).dropna().eq(0).all()
    flat = pd.Series([5.0] * 30)
    assert rsi(flat, 14).dropna().eq(50).all()
    close = make_sample(days=5)["close"]
    r = rsi(close, 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


@pytest.mark.parametrize("fn", [lambda s: ema(s, 20), lambda s: rsi(s, 14)])
def test_no_lookahead(fn):
    """Value at row i must not change when future rows are added."""
    close = make_sample(days=3)["close"]
    full = fn(close)
    for i in (30, 60, 100):
        partial = fn(close.iloc[: i + 1])
        assert partial.iloc[-1] == pytest.approx(full.iloc[i])
