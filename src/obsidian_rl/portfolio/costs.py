"""Configurable transaction-cost model shared by training, replay, evaluation, paper
trading, and dashboard reporting.

Accounting convention: trades execute at the caller-supplied reference price (the next
executable price after the decision), and each cost component is charged explicitly to
cash on the traded notional. This is P&L-equivalent to adjusting the fill price and keeps
every component separately attributable.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """Fractions of traded notional. Defaults are pessimistic for BTCUSDT USD-M perp."""

    taker_fee: float = 0.0005  # 5.0 bps Binance USD-M taker fee (no discounts assumed)
    half_spread: float = 0.00005  # 0.5 bps half bid-ask spread
    slippage: float = 0.0001  # 1.0 bps impact/latency allowance

    def __post_init__(self) -> None:
        for name in ("taker_fee", "half_spread", "slippage"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{name}={value!r} must be int or float, not {type(value).__name__}"
                )
            if not math.isfinite(value):
                raise ValueError(f"{name}={value!r} must be finite")
            if value < 0 or value > 0.05:
                raise ValueError(f"{name}={value} outside sane range [0, 0.05]")

    def fee_cost(self, traded_notional: float) -> float:
        return self.taker_fee * abs(traded_notional)

    def spread_cost(self, traded_notional: float) -> float:
        return self.half_spread * abs(traded_notional)

    def slippage_cost(self, traded_notional: float) -> float:
        return self.slippage * abs(traded_notional)

    def total_cost(self, traded_notional: float) -> float:
        return (
            self.fee_cost(traded_notional)
            + self.spread_cost(traded_notional)
            + self.slippage_cost(traded_notional)
        )

    @property
    def round_trip_rate(self) -> float:
        """Total cost fraction for entering and exiting the same notional."""
        return 2.0 * (self.taker_fee + self.half_spread + self.slippage)


def funding_cash_flow(position_qty: float, price: float, funding_rate: float) -> float:
    """Signed cash flow of a funding event for a perpetual position.

    Longs pay when the rate is positive; shorts receive (and vice versa).
    Returns the cash delta (negative = payment).
    """
    return -funding_rate * position_qty * price
