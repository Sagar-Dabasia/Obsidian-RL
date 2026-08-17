"""The single authoritative portfolio engine (target-position semantics).

Policies propose a target exposure in [-max_abs_exposure, +max_abs_exposure]; this engine
owns all position state. Sizing is equity-proportional: target_qty = target_exposure *
net_equity / price. A long-to-short reversal is one traded delta covering close + open,
so costs apply to the full |delta| notional.

The engine is execution-timing agnostic: callers must pass the next executable price
after the decision (per ADR-003, the open of the following candle) — never the closing
price that produced the observation.
"""

from dataclasses import dataclass, field, replace
from enum import Enum

from obsidian_rl.portfolio.costs import CostModel, funding_cash_flow


class MarketModel(Enum):
    SPOT = "SPOT"
    PERPETUAL = "PERPETUAL"
    FOREX_MARGIN = "FOREX_MARGIN"


class ExposurePolicy(Enum):
    LONG_FLAT = "LONG_FLAT"
    BIDIRECTIONAL = "BIDIRECTIONAL"


@dataclass(frozen=True)
class PortfolioConfig:
    initial_cash: float = 10_000.0
    max_abs_exposure: float = 1.0
    min_trade_notional: float = 10.0  # skip dust rebalances below this notional
    exposure_tolerance: float = 0.01  # no-trade band vs current exposure (stops cost-decay churn)
    allow_short: bool = True

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if not 0 < self.max_abs_exposure <= 1.0:
            raise ValueError(
                "max_abs_exposure must be in (0, 1]; leverage >1 requires margin modeling"
            )


@dataclass(frozen=True)
class ExecutionResult:
    proposed_target: float
    approved_target: float
    executed_target: float
    delta_qty: float
    exec_price: float
    traded_notional: float
    fee: float
    spread_cost: float
    slippage_cost: float
    realized_pnl_delta: float
    rejection_reason: str | None = None

    @property
    def total_cost(self) -> float:
        return self.fee + self.spread_cost + self.slippage_cost


@dataclass
class PortfolioState:
    cash: float
    qty: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    spread_paid: float = 0.0
    slippage_paid: float = 0.0
    funding_paid: float = 0.0  # net funding cash outflow (negative = received)
    turnover: float = 0.0  # cumulative traded notional
    trade_count: int = 0
    peak_equity: float = field(default=0.0)
    current_drawdown_pct: float = 0.0
    path_maximum_drawdown_pct: float = 0.0

    def unrealized_pnl(self, price: float) -> float:
        return self.qty * (price - self.avg_entry_price)

    def net_equity(self, price: float) -> float:
        return self.cash + self.unrealized_pnl(price)

    def total_costs(self) -> float:
        return self.fees_paid + self.spread_paid + self.slippage_paid + self.funding_paid

    def gross_equity(self, price: float) -> float:
        """Equity as if no costs had ever been charged."""
        return self.net_equity(price) + self.total_costs()

    def exposure(self, price: float) -> float:
        equity = self.net_equity(price)
        if equity <= 0:
            return 0.0
        return self.qty * price / equity

    def drawdown(self, price: float) -> float:
        equity = self.net_equity(price)
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - equity / self.peak_equity)


class PortfolioEngine:
    """Owns cash, position, P&L, costs, turnover, drawdown. Nothing else may."""

    def __init__(self, config: PortfolioConfig, costs: CostModel) -> None:
        self.config = config
        self.costs = costs
        self.state = PortfolioState(cash=config.initial_cash, peak_equity=config.initial_cash)

    # ------------------------------------------------------------------ helpers
    def _approve_target(self, proposed: float) -> tuple[float, str | None]:
        if proposed < 0 and not self.config.allow_short:
            raise ValueError(f"short exposure disabled but requested target: {proposed}")
        limit = self.config.max_abs_exposure
        approved = max(-limit, min(limit, proposed))
        reason = None
        if approved != proposed:
            reason = f"target clamped from {proposed} to {approved}"
        return approved, reason

    def mark_to_market(self, price: float) -> PortfolioState:
        """Update peak equity; return a snapshot copy of state."""
        equity = self.state.net_equity(price)
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd = self.state.drawdown(price)
        self.state.current_drawdown_pct = dd
        if dd > self.state.path_maximum_drawdown_pct:
            self.state.path_maximum_drawdown_pct = dd
        return replace_state_copy(self.state)

    # ------------------------------------------------------------------ trading
    def rebalance(self, proposed_target: float, price: float) -> ExecutionResult:
        """Move the position toward a target exposure at the given executable price."""
        if price <= 0:
            raise ValueError(f"non-positive execution price {price}")
        s = self.state
        approved, reason = self._approve_target(proposed_target)

        equity = s.net_equity(price)
        force_flat = equity <= 0
        if force_flat:
            # Bankrupt: force flat, refuse new risk; dust/tolerance skips do not apply.
            approved = 0.0
            reason = "equity non-positive; forcing flat"

        target_qty = approved * equity / price if not force_flat else 0.0
        delta_qty = target_qty - s.qty
        traded_notional = abs(delta_qty) * price

        # The no-trade band exists to stop cost-decay churn on NONZERO targets. A
        # requested full close (approved == 0 with an open position) must always
        # execute — otherwise liquidate() could silently leave a residual position.
        is_close_request = approved == 0.0 and s.qty != 0.0
        current_exposure = s.exposure(price)
        skip = (
            delta_qty != 0.0
            and not is_close_request
            and (
                traded_notional < self.config.min_trade_notional
                or abs(approved - current_exposure) < self.config.exposure_tolerance
            )
        )
        if skip and not force_flat:
            result = ExecutionResult(
                proposed_target=proposed_target,
                approved_target=approved,
                executed_target=s.exposure(price),
                delta_qty=0.0,
                exec_price=price,
                traded_notional=0.0,
                fee=0.0,
                spread_cost=0.0,
                slippage_cost=0.0,
                realized_pnl_delta=0.0,
                rejection_reason=reason or "within no-trade band (tolerance/min notional)",
            )
            self.mark_to_market(price)
            return result

        fee = self.costs.fee_cost(traded_notional)
        spread = self.costs.spread_cost(traded_notional)
        slippage = self.costs.slippage_cost(traded_notional)

        realized = 0.0
        new_qty = s.qty + delta_qty
        if s.qty == 0.0 or (s.qty > 0) == (delta_qty > 0) or delta_qty == 0.0:
            # Opening or increasing (or no-op): weighted average entry.
            new_entry = (
                s.avg_entry_price
                if delta_qty == 0.0
                else (
                    (abs(s.qty) * s.avg_entry_price + abs(delta_qty) * price) / abs(new_qty)
                    if new_qty != 0.0
                    else 0.0
                )
            )
        elif abs(delta_qty) <= abs(s.qty):
            # Reducing or closing: realize P&L on the closed quantity.
            closed = abs(delta_qty)
            realized = closed * (price - s.avg_entry_price) * (1.0 if s.qty > 0 else -1.0)
            new_entry = s.avg_entry_price if new_qty != 0.0 else 0.0
        else:
            # Reversal: close the whole old position, open the remainder at price.
            realized = abs(s.qty) * (price - s.avg_entry_price) * (1.0 if s.qty > 0 else -1.0)
            new_entry = price

        s.cash += realized - fee - spread - slippage
        s.qty = new_qty
        s.avg_entry_price = new_entry if new_qty != 0.0 else 0.0
        s.realized_pnl += realized
        s.fees_paid += fee
        s.spread_paid += spread
        s.slippage_paid += slippage
        s.turnover += traded_notional
        if traded_notional > 0:
            s.trade_count += 1
        self.mark_to_market(price)

        return ExecutionResult(
            proposed_target=proposed_target,
            approved_target=approved,
            executed_target=s.exposure(price),
            delta_qty=delta_qty,
            exec_price=price,
            traded_notional=traded_notional,
            fee=fee,
            spread_cost=spread,
            slippage_cost=slippage,
            realized_pnl_delta=realized,
            rejection_reason=reason,
        )

    def apply_funding(self, price: float, funding_rate: float) -> float:
        """Apply a funding event; returns the cash delta (negative = paid)."""
        flow = funding_cash_flow(self.state.qty, price, funding_rate)
        self.state.cash += flow
        self.state.funding_paid += -flow
        self.mark_to_market(price)
        return flow

    def liquidate(self, price: float) -> ExecutionResult:
        """Terminal close of any open position (episode end / session end)."""
        return self.rebalance(0.0, price)


def replace_state_copy(state: PortfolioState) -> PortfolioState:
    return replace(state)
