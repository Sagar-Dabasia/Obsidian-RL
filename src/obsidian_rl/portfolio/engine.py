"""The single authoritative portfolio engine (target-position semantics).

Policies propose a target exposure in [-max_abs_exposure, +max_abs_exposure]; this engine
owns all position state. Sizing is equity-proportional: target_qty = target_exposure *
net_equity / price. A long-to-short reversal is one traded delta covering close + open,
so costs apply to the full |delta| notional.

The engine is execution-timing agnostic: callers must pass the next executable price
after the decision (per ADR-003, the open of the following candle) — never the closing
price that produced the observation.
"""

import math
from collections.abc import Mapping
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
class PositionState:
    """Per-symbol position state for multi-asset portfolio."""

    qty: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    spread_paid: float = 0.0
    slippage_paid: float = 0.0
    funding_paid: float = 0.0
    turnover: float = 0.0
    trade_count: int = 0


@dataclass
class PortfolioState:
    cash: float
    # Single-asset fields (preserved for backwards compatibility)
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

    # Multi-asset extension: per-symbol position state
    positions: dict[str, "PositionState"] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Initialize peak_equity if not set
        if self.peak_equity <= 0:
            self.peak_equity = self.cash

    def get_position(self, symbol: str) -> "PositionState":
        """Get or create position state for a symbol."""
        if symbol not in self.positions:
            self.positions[symbol] = PositionState()
        return self.positions[symbol]

    def unrealized_pnl(self, price: float) -> float:
        """Single-asset unrealized PnL (backwards compatibility)."""
        return self.qty * (price - self.avg_entry_price)

    def net_equity(self, price: float) -> float:
        """Single-asset net equity (backwards compatibility)."""
        return self.cash + self.unrealized_pnl(price)

    def total_costs(self) -> float:
        return self.fees_paid + self.spread_paid + self.slippage_paid + self.funding_paid

    def gross_equity(self, price: float) -> float:
        """Equity as if no costs had ever been charged."""
        return self.net_equity(price) + self.total_costs()

    def exposure(self, price: float) -> float:
        """Single-asset exposure (backwards compatibility)."""
        equity = self.net_equity(price)
        if equity <= 0:
            return 0.0
        return self.qty * price / equity

    def drawdown(self, price: float) -> float:
        """Single-asset drawdown (backwards compatibility)."""
        equity = self.net_equity(price)
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - equity / self.peak_equity)

    # Multi-asset methods
    def _validate_marks_for_held_positions(self, prices: Mapping[str, float]) -> None:
        """Validate all nonzero held positions have finite positive marks.

        Raises ValueError if any held position (qty != 0, excluding DEFAULT)
        is missing a mark or has a non-finite/non-positive mark.
        """
        for symbol, pos in self.positions.items():
            if symbol == "DEFAULT":
                continue
            if pos.qty != 0:
                if symbol not in prices:
                    raise ValueError(f"missing mark for held symbol: {symbol}")
                mark = prices[symbol]
                if not isinstance(mark, (int, float)) or not math.isfinite(mark) or mark <= 0:
                    raise ValueError(
                        f"non-finite or non-positive mark for held symbol {symbol}: {mark!r}"
                    )

    def multi_asset_equity(self, prices: Mapping[str, float]) -> float:
        """Total portfolio equity across all assets using their own mark prices.

        Zero-qty positions are completely skipped — their marks are not accessed,
        so invalid marks for closed positions cannot contaminate equity.
        """
        self._validate_marks_for_held_positions(prices)
        total = self.cash
        for symbol, pos in self.positions.items():
            # Skip zero-qty positions entirely (no mark access = no contamination)
            if pos.qty == 0:
                continue
            # At this point symbol is guaranteed to be in prices with valid mark
            total += pos.qty * (prices[symbol] - pos.avg_entry_price)
        return total

    def multi_asset_gross_exposure(self, prices: Mapping[str, float]) -> float:
        """Gross exposure = sum of absolute position notionals / total equity."""
        self._validate_marks_for_held_positions(prices)
        equity = self.multi_asset_equity(prices)
        if equity <= 0:
            return 0.0
        gross = 0.0
        # Check positions dict first
        if self.positions:
            for symbol, pos in self.positions.items():
                if symbol in prices and pos.qty != 0:
                    gross += abs(pos.qty * prices[symbol]) / equity
        # Fall back to single-asset fields for backwards compatibility
        elif self.qty != 0 and prices:
            # Use the first price as reference
            price = next(iter(prices.values()))
            gross += abs(self.qty * price) / equity
        return gross

    def multi_asset_net_exposure(self, prices: Mapping[str, float]) -> float:
        """Net exposure = sum of signed position notionals / total equity."""
        self._validate_marks_for_held_positions(prices)
        equity = self.multi_asset_equity(prices)
        if equity <= 0:
            return 0.0
        net = 0.0
        # Check positions dict first
        if self.positions:
            for symbol, pos in self.positions.items():
                if symbol in prices and pos.qty != 0:
                    net += pos.qty * prices[symbol] / equity
        # Fall back to single-asset fields for backwards compatibility
        elif self.qty != 0 and prices:
            price = next(iter(prices.values()))
            net += self.qty * price / equity
        return net

    def multi_asset_drawdown(self, prices: Mapping[str, float]) -> float:
        """Drawdown based on total multi-asset equity."""
        self._validate_marks_for_held_positions(prices)
        equity = self.multi_asset_equity(prices)
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - equity / self.peak_equity)

    def update_peak_equity(self, prices: Mapping[str, float]) -> None:
        """Update peak equity based on multi-asset equity."""
        self._validate_marks_for_held_positions(prices)
        equity = self.multi_asset_equity(prices)
        if equity > self.peak_equity:
            self.peak_equity = equity


class PortfolioEngine:
    """Owns cash, position, P&L, costs, turnover, drawdown. Nothing else may."""

    def __init__(self, config: PortfolioConfig, costs: CostModel) -> None:
        self.config = config
        self.costs = costs
        self.state = PortfolioState(cash=config.initial_cash, peak_equity=config.initial_cash)

    # ------------------------------------------------------------------ helpers
    def _validate_target(self, proposed: float) -> None:
        """Validate target is numeric and finite before any clamping."""
        if not isinstance(proposed, (int, float)) or not math.isfinite(proposed):
            raise ValueError(f"non-finite or non-numeric target {proposed!r}")

    def _approve_target(self, proposed: float) -> tuple[float, str | None]:
        self._validate_target(proposed)
        if proposed < 0 and not self.config.allow_short:
            raise ValueError(f"short exposure disabled but requested target: {proposed}")
        limit = self.config.max_abs_exposure
        approved = max(-limit, min(limit, proposed))
        reason = None
        if approved != proposed:
            reason = f"target clamped from {proposed} to {approved}"
        return approved, reason

    def _validate_execution_price(self, price: float) -> None:
        """Validate execution price is finite and positive."""
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError(f"non-finite or non-positive execution price {price!r}")

    def _validate_funding_params(self, price: float, funding_rate: float) -> None:
        """Validate funding price and rate are numeric and finite."""
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError(f"non-finite or non-positive funding price {price!r}")
        if not isinstance(funding_rate, (int, float)) or not math.isfinite(funding_rate):
            raise ValueError(f"non-finite funding rate {funding_rate!r}")

    def mark_to_market(self, price: float) -> PortfolioState:
        """Update peak equity; return a snapshot copy of state."""
        self._validate_execution_price(price)
        equity = self.state.net_equity(price)
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd = self.state.drawdown(price)
        self.state.current_drawdown_pct = dd
        if dd > self.state.path_maximum_drawdown_pct:
            self.state.path_maximum_drawdown_pct = dd
        return replace_state_copy(self.state)

    def mark_to_market_multi(self, prices: Mapping[str, float]) -> PortfolioState:
        """Update peak equity using multi-asset equity; return a snapshot copy of state."""
        equity = self.state.multi_asset_equity(prices)
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd = self.state.multi_asset_drawdown(prices)
        self.state.current_drawdown_pct = dd
        if dd > self.state.path_maximum_drawdown_pct:
            self.state.path_maximum_drawdown_pct = dd
        return replace_state_copy(self.state)

    # ------------------------------------------------------------------ trading
    def rebalance(
        self,
        proposed_target: float,
        price: float,
        symbol: str | None = None,
        marks: Mapping[str, float] | None = None,
    ) -> ExecutionResult:
        """Move the position toward a target exposure at the given executable price.

        Legacy single-asset usage: rebalance(target, price)
        Multi-asset usage:
            rebalance(target, price, symbol="BTCUSDT",
                      marks={"BTCUSDT": 100, "ETHUSDT": 2000})
        """
        self._validate_execution_price(price)

        # Determine if this is a multi-asset call
        is_multi_asset = symbol is not None

        if is_multi_asset:
            # Multi-asset path: require marks for all held symbols
            if marks is None:
                raise ValueError("multi-asset rebalance requires marks mapping")

            # NEW SYMBOL ATOMICITY: target symbol must have a valid mark BEFORE any mutation
            # symbol is guaranteed to be str here due to is_multi_asset check
            assert symbol is not None
            if symbol not in marks:
                raise ValueError(f"missing mark for target symbol: {symbol}")
            target_mark = marks[symbol]
            if (
                not isinstance(target_mark, (int, float))
                or not math.isfinite(target_mark)
                or target_mark <= 0
            ):
                raise ValueError(
                    f"non-finite or non-positive mark for target symbol {symbol}: {target_mark!r}"
                )

            # Validate all held nonzero positions have marks (skip DEFAULT which is legacy)
            for sym, pos in self.state.positions.items():
                if sym == "DEFAULT":
                    continue
                if pos.qty != 0 and sym not in marks:
                    raise ValueError(f"missing mark for held symbol: {sym}")
                if sym in marks:
                    mark = marks[sym]
                    if not isinstance(mark, (int, float)) or not math.isfinite(mark) or mark <= 0:
                        raise ValueError(
                            f"non-finite or non-positive mark for symbol {sym}: {mark!r}"
                        )
            # Use multi-asset equity for sizing
            equity = self.state.multi_asset_equity(marks)
        else:
            # Legacy single-asset path
            equity = self.state.net_equity(price)

        s = self.state
        approved, reason = self._approve_target(proposed_target)

        force_flat = equity <= 0
        if force_flat:
            approved = 0.0
            reason = "equity non-positive; forcing flat"

        target_qty = approved * equity / price if not force_flat else 0.0

        if is_multi_asset:
            # Get or create the specific symbol's position
            # We know symbol is not None here due to is_multi_asset check
            assert symbol is not None
            pos = s.get_position(symbol)
            current_qty = pos.qty
            delta_qty = target_qty - current_qty
            traded_notional = abs(delta_qty) * price

            is_close_request = approved == 0.0 and current_qty != 0.0
            # Use SIGNED current exposure (preserves short sign)
            current_exposure = current_qty * price / equity if equity > 0 else 0.0
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
                    executed_target=current_exposure,
                    delta_qty=0.0,
                    exec_price=price,
                    traded_notional=0.0,
                    fee=0.0,
                    spread_cost=0.0,
                    slippage_cost=0.0,
                    realized_pnl_delta=0.0,
                    rejection_reason=reason or "within no-trade band (tolerance/min notional)",
                )
                # We know marks is not None here due to is_multi_asset check
                assert marks is not None
                self.mark_to_market_multi(marks)
                return result

            fee = self.costs.fee_cost(traded_notional)
            spread = self.costs.spread_cost(traded_notional)
            slippage = self.costs.slippage_cost(traded_notional)

            realized = 0.0
            new_qty = current_qty + delta_qty
            if current_qty == 0.0 or (current_qty > 0) == (delta_qty > 0) or delta_qty == 0.0:
                new_entry = (
                    pos.avg_entry_price
                    if delta_qty == 0.0
                    else (
                        (abs(current_qty) * pos.avg_entry_price + abs(delta_qty) * price)
                        / abs(new_qty)
                        if new_qty != 0.0
                        else 0.0
                    )
                )
            elif abs(delta_qty) <= abs(current_qty):
                closed = abs(delta_qty)
                realized = (
                    closed * (price - pos.avg_entry_price) * (1.0 if current_qty > 0 else -1.0)
                )
                new_entry = pos.avg_entry_price if new_qty != 0.0 else 0.0
            else:
                realized = (
                    abs(current_qty)
                    * (price - pos.avg_entry_price)
                    * (1.0 if current_qty > 0 else -1.0)
                )
                new_entry = price

            # Central accounting updates
            s.cash += realized - fee - spread - slippage
            s.realized_pnl += realized
            s.fees_paid += fee
            s.spread_paid += spread
            s.slippage_paid += slippage
            s.turnover += traded_notional
            if traded_notional > 0:
                s.trade_count += 1

            # Per-symbol position update
            pos.qty = new_qty
            pos.avg_entry_price = new_entry if new_qty != 0.0 else 0.0
            pos.realized_pnl += realized
            pos.fees_paid += fee
            pos.spread_paid += spread
            pos.slippage_paid += slippage
            pos.turnover += traded_notional
            if traded_notional > 0:
                pos.trade_count += 1

            # In multi-asset mode, we don't mirror to legacy qty/avg_entry/DEFAULT
            # because that would overwrite other symbols' accounting
            # Global portfolio fields (realized_pnl, fees_paid, etc.) are already
            # correctly maintained as cumulative sums by the central accounting above
            # Legacy single-asset path handles its own mirroring to DEFAULT

            # We know marks is not None here due to is_multi_asset check
            assert marks is not None
            self.mark_to_market_multi(marks)

            # Calculate executed_target using post-trade multi-asset equity
            post_equity = self.state.multi_asset_equity(marks)
            executed_exposure = pos.qty * price / post_equity if post_equity > 0 else 0.0
            return ExecutionResult(
                proposed_target=proposed_target,
                approved_target=approved,
                executed_target=executed_exposure,
                delta_qty=delta_qty,
                exec_price=price,
                traded_notional=traded_notional,
                fee=fee,
                spread_cost=spread,
                slippage_cost=slippage,
                realized_pnl_delta=realized,
                rejection_reason=reason,
            )

        # Legacy single-asset path (unchanged behavior)
        delta_qty = target_qty - s.qty
        traded_notional = abs(delta_qty) * price

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
            closed = abs(delta_qty)
            realized = closed * (price - s.avg_entry_price) * (1.0 if s.qty > 0 else -1.0)
            new_entry = s.avg_entry_price if new_qty != 0.0 else 0.0
        else:
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

        default_symbol = "DEFAULT"
        pos = s.get_position(default_symbol)
        pos.qty = s.qty
        pos.avg_entry_price = s.avg_entry_price
        pos.realized_pnl = s.realized_pnl
        pos.fees_paid = s.fees_paid
        pos.spread_paid = s.spread_paid
        pos.slippage_paid = s.slippage_paid
        pos.funding_paid = s.funding_paid
        pos.turnover = s.turnover
        pos.trade_count = s.trade_count

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

    def apply_funding(self, price: float, funding_rate: float, symbol: str | None = None) -> float:
        """Apply a funding event; returns the cash delta (negative = paid).

        Args:
            price: Mark price for the position.
            funding_rate: Funding rate (positive = longs pay, negative = longs receive).
            symbol: Optional symbol for multi-asset funding. If None, uses legacy
                single-asset behavior (DEFAULT symbol and legacy state.qty).

        Returns:
            Cash flow delta (negative = paid out of cash).

        Raises:
            ValueError: If symbol is specified but not present in authoritative positions.
            ValueError: If price or funding_rate are non-numeric or non-finite.
        """
        self._validate_funding_params(price, funding_rate)

        if symbol is None:
            # Legacy single-asset behavior
            flow = funding_cash_flow(self.state.qty, price, funding_rate)
            self.state.cash += flow
            self.state.funding_paid += -flow
            # Also update per-symbol PositionState
            default_symbol = "DEFAULT"
            pos = self.state.get_position(default_symbol)
            pos.funding_paid = self.state.funding_paid
            # Legacy marking updates peak/drawdown based on single-asset equity
            self.mark_to_market(price)
        else:
            # Symbol-aware multi-asset funding: fail-closed on unknown symbol
            if symbol not in self.state.positions:
                raise ValueError(f"funding symbol '{symbol}' not in authoritative positions")
            pos = self.state.positions[symbol]
            flow = funding_cash_flow(pos.qty, price, funding_rate)
            if flow != 0.0:
                self.state.cash += flow
                self.state.funding_paid += -flow
                pos.funding_paid += -flow
            # Do NOT call mark_to_market with single price for multi-asset;
            # caller must mark with full price mapping via
            # update_peak_equity / multi_asset_drawdown
        return flow

    def liquidate(self, price: float) -> ExecutionResult:
        """Terminal close of any open position (episode end / session end)."""
        return self.rebalance(0.0, price)


def replace_state_copy(state: PortfolioState) -> PortfolioState:
    # Deep copy positions dict and each PositionState for true snapshot isolation
    copied_positions = {sym: replace(pos) for sym, pos in state.positions.items()}
    return replace(state, positions=copied_positions)
