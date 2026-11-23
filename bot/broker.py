"""Paper broker: pretends to place orders, applies costs + slippage, keeps a ledger.

There is deliberately no live broker in this project. If you add one later,
implement the same buy()/sell() interface and keep paper mode as the default.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .costs import CostModel


@dataclass
class Position:
    symbol: str
    qty: int
    entry_raw: float      # market price when the order was sent
    entry_fill: float     # price after slippage
    entry_fees: float
    entry_time: datetime
    stop: float
    target: float


@dataclass
class Trade:
    symbol: str
    qty: int
    entry_time: datetime
    entry_fill: float
    exit_time: datetime
    exit_fill: float
    gross_pnl: float      # on raw prices, before any costs
    costs: float          # fees + slippage
    net_pnl: float
    reason: str


class PaperBroker:
    def __init__(self, costs: CostModel, starting_cash: float = 100_000.0) -> None:
        self.costs = costs
        self.cash = starting_cash
        self.starting_cash = starting_cash
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []

    def buy(self, symbol: str, qty: int, price: float, ts: datetime,
            stop: float, target: float) -> Position:
        if symbol in self.positions:
            raise ValueError(f"already holding {symbol}")
        if qty < 1:
            raise ValueError("qty must be >= 1")
        fill = self.costs.fill_price(price, "BUY")
        fees = self.costs.fees(fill, qty)
        self.cash -= fill * qty + fees
        pos = Position(symbol, qty, price, fill, fees, ts, stop, target)
        self.positions[symbol] = pos
        return pos

    def sell(self, symbol: str, price: float, ts: datetime, reason: str) -> Trade:
        pos = self.positions.pop(symbol)
        fill = self.costs.fill_price(price, "SELL")
        fees = self.costs.fees(fill, pos.qty)
        self.cash += fill * pos.qty - fees
        gross = (price - pos.entry_raw) * pos.qty
        net = (fill - pos.entry_fill) * pos.qty - pos.entry_fees - fees
        trade = Trade(symbol, pos.qty, pos.entry_time, pos.entry_fill, ts, fill,
                      gross, gross - net, net, reason)
        self.trades.append(trade)
        return trade

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p.qty * prices.get(s, p.entry_raw) for s, p in self.positions.items())

    # --- persistence (so a restart doesn't forget open paper positions) ---
    def to_dict(self) -> dict:
        def ser(obj: dict) -> dict:
            return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in obj.items()}
        return {
            "cash": self.cash,
            "starting_cash": self.starting_cash,
            "positions": {s: ser(asdict(p)) for s, p in self.positions.items()},
            "trades": [ser(asdict(t)) for t in self.trades],
        }

    @classmethod
    def from_dict(cls, data: dict, costs: CostModel) -> "PaperBroker":
        b = cls(costs, data.get("starting_cash", 100_000.0))
        b.cash = data["cash"]
        for s, p in data.get("positions", {}).items():
            p = dict(p, entry_time=datetime.fromisoformat(p["entry_time"]))
            b.positions[s] = Position(**p)
        for t in data.get("trades", []):
            t = dict(t, entry_time=datetime.fromisoformat(t["entry_time"]),
                     exit_time=datetime.fromisoformat(t["exit_time"]))
            b.trades.append(Trade(**t))
        return b
