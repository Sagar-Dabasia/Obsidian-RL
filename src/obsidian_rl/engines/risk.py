"""Deterministic Risk Engine.

Pre-execution gating with default-deny semantics, hard caps on exposure, leverage,
concentration, and drawdown. All decisions are deterministic and side-effect free.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from obsidian_rl.data.contracts import MarketBar
from obsidian_rl.engines.portfolio_combination import CombinationResult, CombinedTarget
from obsidian_rl.portfolio.engine import PortfolioState


class RiskDecision(Enum):
    """Risk engine decision outcomes."""

    APPROVE = "APPROVE"  # Proposal passes all checks unchanged
    SCALE = "SCALE"  # Proposal scaled down to meet limits
    REJECT = "REJECT"  # Proposal vetoed entirely


class RiskReasonCode(Enum):
    """Machine-readable reason codes for risk decisions."""

    OK = "OK"
    DEFAULT_DENY_UNINITIALIZED = "DEFAULT_DENY_UNINITIALIZED"
    DEFAULT_DENY_STALE_MARKET = "DEFAULT_DENY_STALE_MARKET"
    DEFAULT_DENY_MISSING_PORTFOLIO_STATE = "DEFAULT_DENY_MISSING_PORTFOLIO_STATE"
    DEFAULT_DENY_NON_FINITE_PROPOSAL = "DEFAULT_DENY_NON_FINITE_PROPOSAL"
    DEFAULT_DENY_MISSING_TARGET_PRICE = "DEFAULT_DENY_MISSING_TARGET_PRICE"
    DEFAULT_DENY_MISSING_TARGET_BAR = "DEFAULT_DENY_MISSING_TARGET_BAR"
    DEFAULT_DENY_STALE_TARGET_BAR = "DEFAULT_DENY_STALE_TARGET_BAR"
    DEFAULT_DENY_MULTI_ASSET_UNSUPPORTED = "DEFAULT_DENY_MULTI_ASSET_UNSUPPORTED"
    PER_ASSET_EXPOSURE_CAP_EXCEEDED = "PER_ASSET_EXPOSURE_CAP_EXCEEDED"
    PORTFOLIO_GROSS_EXPOSURE_CAP_EXCEEDED = "PORTFOLIO_GROSS_EXPOSURE_CAP_EXCEEDED"
    PORTFOLIO_NET_EXPOSURE_CAP_EXCEEDED = "PORTFOLIO_NET_EXPOSURE_CAP_EXCEEDED"
    LEVERAGE_CAP_EXCEEDED = "LEVERAGE_CAP_EXCEEDED"
    CONCENTRATION_CAP_EXCEEDED = "CONCENTRATION_CAP_EXCEEDED"
    MAX_DRAWDOWN_LIMIT_EXCEEDED = "MAX_DRAWDOWN_LIMIT_EXCEEDED"
    DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED = "DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Configuration for the RiskEngine.

    Attributes:
        max_drawdown_limit: Maximum allowed portfolio drawdown as fraction (e.g., 0.15 = 15%).
            If current drawdown >= this limit, new exposure increases are blocked.
        max_leverage: Maximum portfolio leverage (gross exposure / net equity). Must be >= 1.0.
        max_per_asset_exposure: Maximum absolute exposure per single asset in (0, 1.0].
        max_gross_exposure: Maximum portfolio gross exposure (sum of absolute exposures).
        max_net_exposure: Maximum portfolio net exposure (absolute sum of signed exposures).
        max_concentration_pct: Maximum single-asset concentration as fraction of gross exposure.
            Only enforced when portfolio has >1 asset. In (0, 1.0].
        market_freshness_ms: Maximum age of market data (observed_at_utc) before stale
            rejection.
    """

    max_drawdown_limit: float = 0.15
    max_leverage: float = 2.0
    max_per_asset_exposure: float = 1.0
    max_gross_exposure: float = 1.0
    max_net_exposure: float = 1.0
    max_concentration_pct: float = 0.5
    market_freshness_ms: int = 300_000  # 5 minutes

    def __post_init__(self) -> None:
        # Reject booleans explicitly (bool is subclass of int in Python)
        for name in (
            "max_drawdown_limit",
            "max_leverage",
            "max_per_asset_exposure",
            "max_gross_exposure",
            "max_net_exposure",
            "max_concentration_pct",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{name}={value!r} must be int or float, not {type(value).__name__}"
                )
            if not math.isfinite(value):
                raise ValueError(f"{name}={value!r} must be finite")

        if not (0.0 <= self.max_drawdown_limit <= 1.0):
            raise ValueError(
                f"max_drawdown_limit must be finite in [0, 1], got {self.max_drawdown_limit!r}"
            )
        if self.max_leverage < 1.0:
            raise ValueError(f"max_leverage must be finite and >= 1.0, got {self.max_leverage!r}")
        if not (0.0 < self.max_per_asset_exposure <= 1.0):
            raise ValueError(
                f"max_per_asset_exposure must be finite in (0, 1.0], "
                f"got {self.max_per_asset_exposure!r}"
            )
        if self.max_gross_exposure < 0.0:
            raise ValueError(
                f"max_gross_exposure must be finite and >= 0, got {self.max_gross_exposure!r}"
            )
        if self.max_net_exposure < 0.0:
            raise ValueError(
                f"max_net_exposure must be finite and >= 0, got {self.max_net_exposure!r}"
            )
        if not (0.0 < self.max_concentration_pct <= 1.0):
            raise ValueError(
                f"max_concentration_pct must be finite in (0, 1.0], "
                f"got {self.max_concentration_pct!r}"
            )
        if not isinstance(self.market_freshness_ms, int) or self.market_freshness_ms <= 0:
            raise ValueError(
                f"market_freshness_ms must be positive int, got {self.market_freshness_ms!r}"
            )


@dataclass(frozen=True, slots=True)
class RiskContext:
    """Immutable context required for risk evaluation.

    All fields are point-in-time and must be provided by the caller.
    """

    portfolio_state: PortfolioState
    current_prices: Mapping[str, float]  # symbol -> mark price
    market_bars: Mapping[str, MarketBar]  # symbol -> latest bar (for freshness)
    combination_result: CombinationResult
    current_time_ms: int  # Evaluation timestamp (wall clock)

    def __post_init__(self) -> None:
        if not self.portfolio_state:
            raise ValueError("portfolio_state is required")
        if not self.current_prices:
            raise ValueError("current_prices must not be empty")
        if not self.market_bars:
            raise ValueError("market_bars must not be empty")
        if not self.combination_result:
            raise ValueError("combination_result is required")
        if not isinstance(self.current_time_ms, int) or self.current_time_ms <= 0:
            raise ValueError(f"current_time_ms must be positive int, got {self.current_time_ms!r}")

        # Validate all prices are finite and positive
        for sym, price in self.current_prices.items():
            if not math.isfinite(price) or price <= 0:
                raise ValueError(f"price for {sym} must be finite and positive, got {price!r}")

        # Validate all market bars have valid observed_at_utc
        for sym, bar in self.market_bars.items():
            if not isinstance(bar.observed_at_utc, int) or bar.observed_at_utc <= 0:
                raise ValueError(
                    f"market_bar for {sym} has invalid observed_at_utc: {bar.observed_at_utc!r}"
                )


@dataclass(frozen=True, slots=True)
class RiskEvaluation:
    """Result of a risk evaluation."""

    decision: RiskDecision
    reason: RiskReasonCode
    reason_detail: str
    approved_targets: tuple[CombinedTarget, ...]
    portfolio_gross_exposure: float
    portfolio_net_exposure: float
    portfolio_leverage: float
    current_drawdown: float
    max_drawdown_limit: float
    timestamp_utc: int
    config_fingerprint: str

    def is_approved(self) -> bool:
        return self.decision == RiskDecision.APPROVE

    def is_scaled(self) -> bool:
        return self.decision == RiskDecision.SCALE

    def is_rejected(self) -> bool:
        return self.decision == RiskDecision.REJECT


class RiskEngine:
    """Deterministic pre-execution risk gate.

    The engine operates in default-deny mode until explicitly initialized.
    All evaluations are pure functions of inputs with no side effects.
    """

    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self._initialized = False
        self._config_fingerprint = self._compute_fingerprint()

    def _compute_fingerprint(self) -> str:
        import hashlib
        import json

        data = {
            "max_drawdown_limit": self.config.max_drawdown_limit,
            "max_leverage": self.config.max_leverage,
            "max_per_asset_exposure": self.config.max_per_asset_exposure,
            "max_gross_exposure": self.config.max_gross_exposure,
            "max_net_exposure": self.config.max_net_exposure,
            "max_concentration_pct": self.config.max_concentration_pct,
            "market_freshness_ms": self.config.market_freshness_ms,
        }
        encoded = json.dumps(data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def initialize(self) -> None:
        """Transition from default-deny to active evaluation mode."""
        self._initialized = True

    def is_initialized(self) -> bool:
        return self._initialized

    def evaluate(self, context: RiskContext) -> RiskEvaluation:
        """Evaluate a combination result against risk limits.

        Args:
            context: Complete evaluation context with portfolio state, prices,
                market data, and proposed combination.

        Returns:
            RiskEvaluation with decision, reason, and approved targets.

        The engine NEVER mutates inputs or creates financial state.
        """
        # Default-deny: uninitialized engine rejects everything
        if not self._initialized:
            return self._reject(
                context,
                RiskReasonCode.DEFAULT_DENY_UNINITIALIZED,
                "RiskEngine not initialized; default-deny active",
            )

        # Validate proposal targets are all finite
        for target in context.combination_result.targets:
            if not math.isfinite(target.target_exposure):
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_NON_FINITE_PROPOSAL,
                    f"Non-finite target_exposure for {target.symbol}: {target.target_exposure!r}",
                )

        # Check market data freshness (default-deny on stale data)
        # First validate that every target has required market data
        for target in context.combination_result.targets:
            if target.symbol not in context.current_prices:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_PRICE,
                    f"Missing current price for target symbol: {target.symbol}",
                )
            if target.symbol not in context.market_bars:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_BAR,
                    f"Missing market bar for target symbol: {target.symbol}",
                )
            bar = context.market_bars[target.symbol]
            # Validate market bar identity matches target
            if bar.symbol != target.symbol:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_BAR,
                    f"Market bar symbol mismatch: bar={bar.symbol}, target={target.symbol}",
                )
            if bar.venue != target.venue:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_BAR,
                    f"Market bar venue mismatch: bar={bar.venue}, target={target.venue}",
                )
            if bar.asset_class != target.asset_class:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_BAR,
                    f"Market bar asset_class mismatch: bar={bar.asset_class}, "
                    f"target={target.asset_class}",
                )
            age_ms = context.current_time_ms - bar.observed_at_utc
            if age_ms > self.config.market_freshness_ms:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_STALE_TARGET_BAR,
                    f"Stale market bar for target {target.symbol}; age "
                    f"{age_ms}ms > limit {self.config.market_freshness_ms}ms",
                )

        # Open-position market data fail-closed validation:
        # Required symbols = union(proposed target symbols, all nonzero
        # authoritative open-position symbols)
        target_symbols = {
            context.combination_result.targets[i].symbol
            for i in range(len(context.combination_result.targets))
        }
        required_symbols = set(target_symbols)
        # Add all symbols with nonzero positions
        for symbol, pos in context.portfolio_state.positions.items():
            if pos.qty != 0:
                required_symbols.add(symbol)

        # For EVERY required symbol require finite positive price,
        # matching bar, fresh observed_at_utc
        for symbol in required_symbols:
            if symbol not in context.current_prices:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_PRICE,
                    f"Missing current price for open position symbol: {symbol}",
                )
            if symbol not in context.market_bars:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_BAR,
                    f"Missing market bar for open position symbol: {symbol}",
                )
            bar = context.market_bars[symbol]
            # Validate market bar identity
            if bar.symbol != symbol:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_BAR,
                    f"Market bar symbol mismatch for open position: "
                    f"bar={bar.symbol}, required={symbol}",
                )
            price = context.current_prices[symbol]
            if not math.isfinite(price) or price <= 0:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_MISSING_TARGET_PRICE,
                    f"Non-finite or non-positive price for open position {symbol}: {price!r}",
                )
            age_ms = context.current_time_ms - bar.observed_at_utc
            if age_ms > self.config.market_freshness_ms:
                return self._reject(
                    context,
                    RiskReasonCode.DEFAULT_DENY_STALE_TARGET_BAR,
                    f"Stale market bar for open position {symbol}; age "
                    f"{age_ms}ms > limit {self.config.market_freshness_ms}ms",
                )

        # Compute current portfolio metrics using multi-asset methods (read-only)
        prices = context.current_prices
        portfolio_state = context.portfolio_state

        # Use multi-asset equity without mutating portfolio state
        current_equity = portfolio_state.multi_asset_equity(prices)

        # If equity is non-positive, force flat (handled by PortfolioEngine)
        if current_equity <= 0:
            return self._reject(
                context,
                RiskReasonCode.MAX_DRAWDOWN_LIMIT_EXCEEDED,
                f"Portfolio equity non-positive ({current_equity:.2f}); forcing flat",
            )

        current_drawdown = portfolio_state.multi_asset_drawdown(prices)

        # Check drawdown gate FIRST - if already beyond limit, block exposure increases
        if current_drawdown >= self.config.max_drawdown_limit:
            # Check if proposal would increase absolute gross exposure
            proposed_gross = context.combination_result.portfolio_gross_exposure
            current_gross = self._compute_current_gross_exposure(context)
            if proposed_gross > current_gross + 1e-12:  # Allow tiny numerical tolerance
                return self._reject(
                    context,
                    RiskReasonCode.DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED,
                    f"Drawdown {current_drawdown:.4f} >= limit "
                    f"{self.config.max_drawdown_limit:.4f}; "
                    f"proposed gross {proposed_gross:.4f} > current {current_gross:.4f}",
                )
            # Allow reduction or flat - proceed to scale down

        # Evaluate each target against per-asset cap
        approved_targets = []
        for target in context.combination_result.targets:
            if abs(target.target_exposure) > self.config.max_per_asset_exposure + 1e-12:
                # Scale this asset down to cap
                capped = target.target_exposure
                if capped > 0:
                    capped = min(capped, self.config.max_per_asset_exposure)
                else:
                    capped = max(capped, -self.config.max_per_asset_exposure)
                approved_targets.append(
                    CombinedTarget(
                        asset_class=target.asset_class,
                        venue=target.venue,
                        symbol=target.symbol,
                        target_exposure=capped,
                        contributing_engines=target.contributing_engines,
                        gross_exposure_contribution=abs(capped),
                        net_exposure_contribution=capped,
                    )
                )
            else:
                approved_targets.append(target)

        # Recompute portfolio exposures after per-asset capping
        portfolio_gross = sum(abs(t.target_exposure) for t in approved_targets)
        portfolio_net = sum(t.target_exposure for t in approved_targets)

        # Check gross exposure cap
        if portfolio_gross > self.config.max_gross_exposure + 1e-12:
            scale = self.config.max_gross_exposure / portfolio_gross if portfolio_gross > 0 else 0.0
            approved_targets = [
                CombinedTarget(
                    asset_class=t.asset_class,
                    venue=t.venue,
                    symbol=t.symbol,
                    target_exposure=t.target_exposure * scale,
                    contributing_engines=t.contributing_engines,
                    gross_exposure_contribution=abs(t.target_exposure * scale),
                    net_exposure_contribution=t.target_exposure * scale,
                )
                for t in approved_targets
            ]
            portfolio_gross = self.config.max_gross_exposure
            portfolio_net *= scale

        # Check net exposure cap
        net_abs = abs(portfolio_net)
        if net_abs > self.config.max_net_exposure + 1e-12:
            scale = self.config.max_net_exposure / net_abs if net_abs > 0 else 0.0
            approved_targets = [
                CombinedTarget(
                    asset_class=t.asset_class,
                    venue=t.venue,
                    symbol=t.symbol,
                    target_exposure=t.target_exposure * scale,
                    contributing_engines=t.contributing_engines,
                    gross_exposure_contribution=abs(t.target_exposure * scale),
                    net_exposure_contribution=t.target_exposure * scale,
                )
                for t in approved_targets
            ]
            portfolio_net *= scale
            portfolio_gross *= scale

        # Check leverage cap (gross exposure / equity)
        # Gross notional = portfolio_gross * equity
        # Leverage = gross notional / equity = portfolio_gross
        # Actually leverage = sum(|position_notional|) / equity
        # position_notional = target_exposure * equity, so sum(|target_exposure|) = portfolio_gross
        # Therefore leverage = portfolio_gross (since each exposure is already normalized to equity)
        portfolio_leverage = portfolio_gross
        if portfolio_leverage > self.config.max_leverage + 1e-12:
            scale = self.config.max_leverage / portfolio_leverage if portfolio_leverage > 0 else 0.0
            approved_targets = [
                CombinedTarget(
                    asset_class=t.asset_class,
                    venue=t.venue,
                    symbol=t.symbol,
                    target_exposure=t.target_exposure * scale,
                    contributing_engines=t.contributing_engines,
                    gross_exposure_contribution=abs(t.target_exposure * scale),
                    net_exposure_contribution=t.target_exposure * scale,
                )
                for t in approved_targets
            ]
            portfolio_gross *= scale
            portfolio_net *= scale
            portfolio_leverage = self.config.max_leverage

        # Check concentration cap (fail-closed: reject if exceeds limit)
        if len(approved_targets) > 1 and portfolio_gross > 0:
            max_concentration = (
                max(abs(t.target_exposure) for t in approved_targets) / portfolio_gross
            )
            if max_concentration > self.config.max_concentration_pct + 1e-12:
                return self._reject(
                    context,
                    RiskReasonCode.CONCENTRATION_CAP_EXCEEDED,
                    f"Max concentration {max_concentration:.4f} > limit "
                    f"{self.config.max_concentration_pct:.4f}; rejecting multi-asset proposal",
                )

        # Final drawdown check after all scaling
        if current_drawdown >= self.config.max_drawdown_limit:
            proposed_gross = sum(abs(t.target_exposure) for t in approved_targets)
            current_gross = self._compute_current_gross_exposure(context)
            if proposed_gross > current_gross + 1e-12:
                return self._reject(
                    context,
                    RiskReasonCode.DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED,
                    f"Drawdown {current_drawdown:.4f} >= limit "
                    f"{self.config.max_drawdown_limit:.4f}; "
                    f"final proposed gross {proposed_gross:.4f} > current {current_gross:.4f}",
                )

        # Determine final decision
        original_targets = context.combination_result.targets
        if self._targets_equal(original_targets, approved_targets):
            decision = RiskDecision.APPROVE
            reason = RiskReasonCode.OK
            reason_detail = "All risk checks passed"
        else:
            decision = RiskDecision.SCALE
            reason = RiskReasonCode.OK  # Scaled but not rejected
            reason_detail = "Proposal scaled to meet risk limits"

        return RiskEvaluation(
            decision=decision,
            reason=reason,
            reason_detail=reason_detail,
            approved_targets=tuple(approved_targets),
            portfolio_gross_exposure=portfolio_gross,
            portfolio_net_exposure=portfolio_net,
            portfolio_leverage=portfolio_leverage,
            current_drawdown=current_drawdown,
            max_drawdown_limit=self.config.max_drawdown_limit,
            timestamp_utc=context.current_time_ms,
            config_fingerprint=self._config_fingerprint,
        )

    def _compute_current_gross_exposure(self, context: RiskContext) -> float:
        """Compute current portfolio gross exposure from existing positions."""
        if not context.current_prices:
            return 0.0
        prices = context.current_prices
        equity = context.portfolio_state.multi_asset_equity(prices)
        if equity <= 0:
            return 0.0
        return context.portfolio_state.multi_asset_gross_exposure(prices)

    def _targets_equal(
        self, original: Sequence[CombinedTarget], approved: Sequence[CombinedTarget]
    ) -> bool:
        """Check if approved targets match original (within tolerance)."""
        if len(original) != len(approved):
            return False
        for o, a in zip(original, approved, strict=True):
            if o.symbol != a.symbol:
                return False
            if abs(o.target_exposure - a.target_exposure) > 1e-10:
                return False
        return True

    def _reject(self, context: RiskContext, reason: RiskReasonCode, detail: str) -> RiskEvaluation:
        """Create a REJECT evaluation with flat targets."""
        flat_targets = tuple(
            CombinedTarget(
                asset_class=t.asset_class,
                venue=t.venue,
                symbol=t.symbol,
                target_exposure=0.0,
                contributing_engines=t.contributing_engines,
                gross_exposure_contribution=0.0,
                net_exposure_contribution=0.0,
            )
            for t in context.combination_result.targets
        )

        # For drawdown in rejection, compute multi-asset drawdown
        if context.current_prices and context.combination_result.targets:
            current_drawdown = context.portfolio_state.multi_asset_drawdown(context.current_prices)
        else:
            current_drawdown = 0.0

        return RiskEvaluation(
            decision=RiskDecision.REJECT,
            reason=reason,
            reason_detail=detail,
            approved_targets=flat_targets,
            portfolio_gross_exposure=0.0,
            portfolio_net_exposure=0.0,
            portfolio_leverage=0.0,
            current_drawdown=current_drawdown,
            max_drawdown_limit=self.config.max_drawdown_limit,
            timestamp_utc=context.current_time_ms,
            config_fingerprint=self._config_fingerprint,
        )
