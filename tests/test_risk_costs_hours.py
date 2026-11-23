from datetime import date, datetime, time

import pytest

from bot.broker import PaperBroker
from bot.costs import ZERO_COSTS, CostModel
from bot.market_hours import IST, MarketHours
from bot.risk import RiskConfig, RiskManager

D = date(2026, 11, 2)  # a Monday


def test_max_trades_per_day_and_reset():
    r = RiskManager(RiskConfig(max_trades_per_day=2))
    for _ in range(2):
        assert r.can_enter(D, 100)[0]
        r.record_entry(D)
    ok, why = r.can_enter(D, 100)
    assert not ok and "max trades" in why
    assert r.can_enter(date(2026, 11, 3), 100)[0]  # new day resets


def test_max_daily_loss():
    r = RiskManager(RiskConfig(max_loss_per_day=1000))
    r.record_exit(D, -1200)
    ok, why = r.can_enter(D, 100)
    assert not ok and "daily loss" in why


def test_kill_switch_blocks():
    r = RiskManager(RiskConfig(), kill_switch=lambda: True)
    assert r.can_enter(D, 100) == (False, "kill switch is ON")


def test_position_size():
    r = RiskManager(RiskConfig(max_position_value=50_000))
    assert r.position_size(1000) == 50
    assert not r.can_enter(D, 60_000)[0]


def test_costs_and_slippage():
    c = CostModel(brokerage_per_order=20, brokerage_pct=0.0003, other_charges_pct=0.0, slippage_bps=10)
    assert c.fees(1000, 10) == pytest.approx(3.0)        # 0.03% of 10,000 < 20 cap
    assert c.fees(100_000, 10) == pytest.approx(20.0)    # capped
    assert c.fill_price(100, "BUY") == pytest.approx(100.1)
    assert c.fill_price(100, "SELL") == pytest.approx(99.9)


def test_paper_broker_pnl_and_roundtrip():
    b = PaperBroker(CostModel(brokerage_per_order=0, brokerage_pct=0, other_charges_pct=0, slippage_bps=0), 10_000)
    t0 = datetime(2026, 11, 2, 9, 30, tzinfo=IST)
    b.buy("X", 10, 100, t0, 99, 102)
    trade = b.sell("X", 105, t0, "test")
    assert trade.net_pnl == pytest.approx(50)
    assert b.cash == pytest.approx(10_050)
    b.buy("Y", 1, 10, t0, 9, 11)
    clone = PaperBroker.from_dict(b.to_dict(), ZERO_COSTS)
    assert clone.cash == pytest.approx(b.cash)
    assert clone.positions["Y"].entry_time == t0
    assert clone.trades[0].net_pnl == pytest.approx(50)


def test_market_hours():
    h = MarketHours(holidays={date(2026, 11, 3)})
    at = lambda d, hh, mm: datetime.combine(d, time(hh, mm), tzinfo=IST)  # noqa: E731
    assert h.is_open(at(D, 9, 15))
    assert not h.is_open(at(D, 9, 14))
    assert not h.is_open(at(D, 15, 30))
    assert not h.can_enter(at(D, 15, 0))
    assert h.must_square_off(at(D, 15, 15))
    assert not h.is_trading_day(date(2026, 11, 3))   # holiday
    assert not h.is_trading_day(date(2026, 11, 7))   # Saturday
