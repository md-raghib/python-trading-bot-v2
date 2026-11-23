from datetime import datetime

import pandas as pd

from bot.alerts import Alerts
from bot.config import Config
from bot.data import make_sample
from bot.market_hours import IST
from bot.runner import PaperTrader
from bot.strategy import StrategyConfig

DATA = make_sample(days=10, seed=11, start="2026-11-02")  # two trading weeks


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def make_trader(tmp_path, clock, fetcher=None):
    cfg = Config(symbols=["TEST"], state_dir=str(tmp_path), log_dir=str(tmp_path),
                 strategy=StrategyConfig(rsi_buy=45, rsi_sell=60))
    fetch = fetcher or (lambda s, i, p: DATA[DATA.index <= pd.Timestamp(clock())])
    return PaperTrader(cfg, fetcher=fetch, clock=clock, alerts=Alerts(token="", chat_id=""))


def walk_day(trader, clock, day):
    for ts in pd.date_range(f"{day} 09:20", f"{day} 15:35", freq="5min", tz=IST):
        clock.t = ts.to_pydatetime()
        trader.step()


def test_closed_outside_hours(tmp_path):
    clock = Clock(datetime(2026, 11, 2, 8, 0, tzinfo=IST))
    assert make_trader(tmp_path, clock).step() == "closed"
    clock.t = datetime(2026, 11, 7, 11, 0, tzinfo=IST)  # Saturday
    assert make_trader(tmp_path, clock).step() == "closed"


def test_full_day_ends_flat_and_persists(tmp_path):
    clock = Clock(datetime(2026, 11, 2, 9, 20, tzinfo=IST))
    t = make_trader(tmp_path, clock)
    for day in sorted({ts.date() for ts in DATA.index}):
        walk_day(t, clock, day.isoformat())
    assert t.broker.positions == {}
    assert len(t.broker.trades) > 0
    restored = make_trader(tmp_path, clock)
    assert len(restored.broker.trades) == len(t.broker.trades)
    assert restored.broker.cash == t.broker.cash


def test_fetch_errors_do_not_crash(tmp_path, monkeypatch):
    clock = Clock(datetime(2026, 11, 2, 11, 0, tzinfo=IST))
    calls = []

    def boom(s, i, p):
        calls.append(1)
        raise ConnectionError("network down")

    monkeypatch.setattr("bot.runner._time.sleep", lambda s: None)  # skip retry delays
    t = make_trader(tmp_path, clock, fetcher=boom)
    assert t.step() == "open"
    assert len(calls) == 3  # retried before giving up on this poll


def test_kill_switch_squares_off(tmp_path):
    clock = Clock(datetime(2026, 11, 2, 9, 20, tzinfo=IST))
    t = make_trader(tmp_path, clock)
    for ts in pd.date_range("2026-11-02 09:20", "2026-11-02 15:00", freq="5min", tz=IST):
        clock.t = ts.to_pydatetime()
        t.step()
        if t.broker.positions:
            break
    t.cfg.kill_file.write_text("x")
    assert t.step() == "killed"
    assert t.broker.positions == {}
