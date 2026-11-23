"""Trading costs and slippage.

The defaults are rough PLACEHOLDERS. Set them to your broker's real charges
(brokerage, STT, exchange fees, GST, stamp duty) in config.yaml before you
trust any backtest number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    brokerage_per_order: float = 20.0   # flat cap per executed order
    brokerage_pct: float = 0.0003       # brokerage = min(flat cap, pct * turnover)
    other_charges_pct: float = 0.0004   # taxes + exchange fees, as % of turnover
    slippage_bps: float = 5.0           # adverse price move per fill, in basis points

    def fees(self, price: float, qty: int) -> float:
        turnover = abs(price * qty)
        brokerage = min(self.brokerage_per_order, turnover * self.brokerage_pct)
        return brokerage + turnover * self.other_charges_pct

    def fill_price(self, price: float, side: str) -> float:
        """Price after slippage. Buys fill higher, sells fill lower."""
        adj = price * self.slippage_bps / 10_000
        return price + adj if side == "BUY" else price - adj


ZERO_COSTS = CostModel(brokerage_per_order=0, brokerage_pct=0, other_charges_pct=0, slippage_bps=0)
