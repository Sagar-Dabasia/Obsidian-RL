"""Focused tests for RiskEngine."""

import pytest

from obsidian_rl.data.contracts import AssetClass, MarketBar, QuoteStatus, Timeframe, VolumeType
from obsidian_rl.engines import (
    CombinationResult,
    CombinedTarget,
    EngineProposal,
    EngineType,
    RiskConfig,
    RiskContext,
    RiskDecision,
    RiskEngine,
    RiskReasonCode,
)
from obsidian_rl.portfolio.engine import PortfolioState


def make_market_bar(symbol: str, observed_at_utc: int) -> MarketBar:
    """Create a minimal valid MarketBar for testing."""
    return MarketBar(
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE",
        symbol=symbol,
        timeframe=Timeframe.H4,
        timestamp_utc=observed_at_utc - 3600_000,
        observed_at_utc=observed_at_utc,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        quote_status=QuoteStatus.OBSERVED,
        bid=99.99,
        ask=100.01,
        volume_type=VolumeType.BASE,
        volume=1000.0,
        data_source="TEST",
        schema_version="SCHEMA_V2",
        # row_hash will be auto-computed
    )


def make_proposal(
    engine: EngineType,
    symbol: str,
    target: float,
    confidence: float = 1.0,
    timestamp: int = 1_000_000_000_000,
) -> EngineProposal:
    return EngineProposal(
        engine=engine,
        asset_class=AssetClass.CRYPTO,
        venue="BINANCE",
        symbol=symbol,
        target_exposure=target,
        confidence=confidence,
        timestamp_utc=timestamp,
    )


def make_combination_result(
    targets: list[CombinedTarget],
    timestamp: int = 1_000_000_000_000,
) -> CombinationResult:
    gross = sum(abs(t.target_exposure) for t in targets)
    net = sum(t.target_exposure for t in targets)
    return CombinationResult(
        targets=tuple(targets),
        portfolio_gross_exposure=gross,
        portfolio_net_exposure=net,
        timestamp_utc=timestamp,
        config_fingerprint="test_fp",
    )


def make_risk_context(
    portfolio_state: PortfolioState,
    prices: dict[str, float],
    market_bars: dict[str, MarketBar],
    combination_result: CombinationResult,
    current_time_ms: int = 1_000_000_000_000,
) -> RiskContext:
    return RiskContext(
        portfolio_state=portfolio_state,
        current_prices=prices,
        market_bars=market_bars,
        combination_result=combination_result,
        current_time_ms=current_time_ms,
    )


def _make_nan_target(symbol: str) -> CombinedTarget:
    """Test-only helper: create a CombinedTarget with NaN target_exposure,
    bypassing constructor validation to exercise RiskEngine's own check."""
    t = object.__new__(CombinedTarget)
    object.__setattr__(t, "asset_class", AssetClass.CRYPTO)
    object.__setattr__(t, "venue", "BINANCE")
    object.__setattr__(t, "symbol", symbol)
    object.__setattr__(t, "target_exposure", float("nan"))
    object.__setattr__(t, "contributing_engines", (EngineType.TREND,))
    object.__setattr__(t, "gross_exposure_contribution", 0.5)
    object.__setattr__(t, "net_exposure_contribution", 0.5)
    return t


def _make_inf_target(symbol: str) -> CombinedTarget:
    """Test-only helper: create a CombinedTarget with +inf target_exposure,
    bypassing constructor validation to exercise RiskEngine's own check."""
    t = object.__new__(CombinedTarget)
    object.__setattr__(t, "asset_class", AssetClass.CRYPTO)
    object.__setattr__(t, "venue", "BINANCE")
    object.__setattr__(t, "symbol", symbol)
    object.__setattr__(t, "target_exposure", float("inf"))
    object.__setattr__(t, "contributing_engines", (EngineType.TREND,))
    object.__setattr__(t, "gross_exposure_contribution", 0.5)
    object.__setattr__(t, "net_exposure_contribution", 0.5)
    return t


class TestRiskEngine:
    """Tests for deterministic risk gating."""

    def test_default_deny_before_initialization(self) -> None:
        """Uninitialized engine rejects all proposals."""
        config = RiskConfig()
        engine = RiskEngine(config)
        assert not engine.is_initialized()

        # Create minimal context
        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.DEFAULT_DENY_UNINITIALIZED

    def test_default_deny_stale_market_data(self) -> None:
        """Stale market data triggers default-deny rejection."""
        config = RiskConfig(market_freshness_ms=60_000)
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        # Bar observed 2 minutes ago, freshness is 1 minute
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000 - 120_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        # Current time is now
        context = make_risk_context(state, prices, bars, combo, current_time_ms=1_000_000_000_000)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.DEFAULT_DENY_STALE_TARGET_BAR

    def test_default_deny_missing_portfolio_state(self) -> None:
        """Missing portfolio state is rejected at context creation."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        # RiskContext validation should catch this
        with pytest.raises(ValueError, match="portfolio_state is required"):
            RiskContext(
                portfolio_state=None,  # type: ignore
                current_prices={"BTCUSDT": 100.0},
                market_bars={"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)},
                combination_result=make_combination_result([]),
                current_time_ms=1_000_000_000_000,
            )

    def test_non_finite_proposal_rejected(self) -> None:
        """Non-finite target_exposure in proposal is rejected by RiskEngine's own validation."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}

        # Bypass CombinedTarget constructor validation using test-only helper
        # to exercise RiskEngine's independent defensive check (lines 206-213)
        nan_target = _make_nan_target("BTCUSDT")
        combo = make_combination_result([nan_target])
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.DEFAULT_DENY_NON_FINITE_PROPOSAL
        assert "Non-finite target_exposure" in result.reason_detail
        assert "nan" in result.reason_detail.lower()

    def test_non_finite_proposal_rejected_inf(self) -> None:
        """Non-finite (infinity) target_exposure in proposal is rejected by RiskEngine."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}

        # Bypass constructor with +inf
        inf_target = _make_inf_target("BTCUSDT")
        combo = make_combination_result([inf_target])
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.DEFAULT_DENY_NON_FINITE_PROPOSAL
        assert "Non-finite target_exposure" in result.reason_detail

    def test_per_asset_exposure_cap(self) -> None:
        """Per-asset exposure cap is enforced."""
        config = RiskConfig(max_per_asset_exposure=0.3)
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        # Proposal exceeds per-asset cap
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.8,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.8,
                net_exposure_contribution=0.8,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.SCALE
        assert result.approved_targets[0].target_exposure == pytest.approx(0.3)

    def test_portfolio_gross_exposure_cap(self) -> None:
        """Portfolio gross exposure cap triggers scaling for single asset."""
        config = RiskConfig(
            max_gross_exposure=0.5,
            max_per_asset_exposure=1.0,
            max_concentration_pct=1.0,
        )
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        # Single asset with gross > cap
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.9,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.9,
                net_exposure_contribution=0.9,
            ),
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.SCALE
        assert result.portfolio_gross_exposure == pytest.approx(0.5)
        scale = 0.5 / 0.9
        assert result.approved_targets[0].target_exposure == pytest.approx(0.9 * scale)

    def test_portfolio_net_exposure_cap(self) -> None:
        """Portfolio net exposure cap triggers scaling for single asset."""
        config = RiskConfig(
            max_net_exposure=0.3,
            max_gross_exposure=2.0,
            max_per_asset_exposure=1.0,
            max_concentration_pct=1.0,
        )
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        # Single asset with net > cap
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.9,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.9,
                net_exposure_contribution=0.9,
            ),
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.SCALE
        assert result.portfolio_net_exposure == pytest.approx(0.3)
        scale = 0.3 / 0.9
        assert result.approved_targets[0].target_exposure == pytest.approx(0.9 * scale)

    def test_leverage_cap(self) -> None:
        """Leverage (gross exposure) is computed correctly for single asset."""
        config = RiskConfig(
            max_leverage=2.0,
            max_gross_exposure=2.0,
            max_per_asset_exposure=1.0,
            max_concentration_pct=1.0,
        )
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        # Single asset at max per-asset exposure
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=1.0,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=1.0,
                net_exposure_contribution=1.0,
            ),
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        # At target_exposure=1.0, gross=1.0, leverage=1.0 which is < max_leverage=2.0
        assert result.decision == RiskDecision.APPROVE
        assert result.portfolio_leverage == pytest.approx(1.0)
        assert result.approved_targets[0].target_exposure == 1.0

    def test_concentration_cap(self) -> None:
        """Multi-asset proposals rejected with CONCENTRATION_CAP_EXCEEDED."""
        config = RiskConfig(
            max_concentration_pct=0.5,
            max_gross_exposure=2.0,
        )
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {
            "BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000),
            "ETHUSDT": make_market_bar("ETHUSDT", 1_000_000_000_000),
        }
        prices = {"BTCUSDT": 100.0, "ETHUSDT": 2000.0}
        # BTC is 0.9, ETH is 0.1 -> gross=1.0, BTC concentration = 0.9/1.0 = 90% > 50%
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.9,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.9,
                net_exposure_contribution=0.9,
            ),
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="ETHUSDT",
                target_exposure=0.1,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.1,
                net_exposure_contribution=0.1,
            ),
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.CONCENTRATION_CAP_EXCEEDED

    def test_exact_boundary_conditions(self) -> None:
        """Exact boundary values are handled correctly."""
        config = RiskConfig(
            max_per_asset_exposure=0.5,
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            max_leverage=2.0,
        )
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}

        # Exactly at per-asset cap -> APPROVE
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)
        result = engine.evaluate(context)
        assert result.decision == RiskDecision.APPROVE

    def test_max_drawdown_limit_blocks_exposure_increase(self) -> None:
        """Drawdown beyond limit blocks exposure increases."""
        config = RiskConfig(max_drawdown_limit=0.10)
        engine = RiskEngine(config)
        engine.initialize()

        # Portfolio at 15% drawdown (exceeds 10% limit)
        state = PortfolioState(
            cash=8_500.0,
            qty=0.0,
            realized_pnl=-1_500.0,
            peak_equity=10_000.0,
        )
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        # Try to open a new position (increase gross from 0 to 0.5)
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED

    def test_drawdown_gate_allows_reduction(self) -> None:
        """Drawdown gate allows reducing exposure."""
        config = RiskConfig(max_drawdown_limit=0.10)
        engine = RiskEngine(config)
        engine.initialize()

        # Portfolio at 15% drawdown with existing long position
        state = PortfolioState(
            cash=8_500.0,
            qty=50.0,
            avg_entry_price=100.0,
            realized_pnl=-1_500.0,
            peak_equity=10_000.0,
        )
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        # Propose reducing exposure (gross from ~0.5 to 0.2)
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.2,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.2,
                net_exposure_contribution=0.2,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        # Should allow reduction
        assert result.decision in (RiskDecision.APPROVE, RiskDecision.SCALE)

    def test_deterministic_reason_codes(self) -> None:
        """Reason codes are deterministic and machine-readable."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert isinstance(result.reason, RiskReasonCode)
        assert result.reason == RiskReasonCode.OK
        assert isinstance(result.reason_detail, str)
        assert len(result.reason_detail) > 0

    def test_idempotent_repeated_decision(self) -> None:
        """Repeated evaluation with identical inputs produces identical results."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result1 = engine.evaluate(context)
        result2 = engine.evaluate(context)

        assert result1.decision == result2.decision
        assert result1.reason == result2.reason
        assert result1.approved_targets == result2.approved_targets
        assert result1.portfolio_gross_exposure == result2.portfolio_gross_exposure

    def test_no_accounting_ownership(self) -> None:
        """RiskEngine does not own or mutate portfolio state."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        original_cash = 10_000.0
        state = PortfolioState(cash=original_cash, peak_equity=original_cash)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        # Evaluate multiple times
        for _ in range(5):
            engine.evaluate(context)

        # Original state unchanged
        assert state.cash == original_cash
        assert state.qty == 0.0
        assert state.realized_pnl == 0.0

    def test_config_not_mutated(self) -> None:
        """RiskEngine does not mutate its config."""
        config = RiskConfig(max_drawdown_limit=0.15)
        original_limit = config.max_drawdown_limit
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        engine.evaluate(context)
        engine.evaluate(context)

        assert config.max_drawdown_limit == original_limit

    def test_input_context_not_mutated(self) -> None:
        """Input context is not mutated."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        original_combo_targets = list(context.combination_result.targets)
        original_prices = dict(context.current_prices)

        engine.evaluate(context)

        # Context unchanged
        assert list(context.combination_result.targets) == original_combo_targets
        assert dict(context.current_prices) == original_prices

    def test_invalid_config_rejected(self) -> None:
        """Invalid risk config is rejected at construction."""
        with pytest.raises(ValueError, match="max_drawdown_limit"):
            RiskConfig(max_drawdown_limit=1.5)

        with pytest.raises(ValueError, match="max_leverage"):
            RiskConfig(max_leverage=0.5)

        with pytest.raises(ValueError, match="max_per_asset_exposure"):
            RiskConfig(max_per_asset_exposure=1.5)

        with pytest.raises(ValueError, match="max_concentration_pct"):
            RiskConfig(max_concentration_pct=1.5)

    def test_approve_when_all_checks_pass(self) -> None:
        """Clean proposal within all limits is approved."""
        config = RiskConfig()
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.3,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.3,
                net_exposure_contribution=0.3,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.APPROVE
        assert result.reason == RiskReasonCode.OK
        assert result.approved_targets[0].target_exposure == 0.3

    def test_scale_when_some_limits_exceeded(self) -> None:
        """Proposal exceeding some limits is scaled (not rejected)."""
        config = RiskConfig(max_per_asset_exposure=0.5)
        engine = RiskEngine(config)
        engine.initialize()

        state = PortfolioState(cash=10_000.0, peak_equity=10_000.0)
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.8,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.8,
                net_exposure_contribution=0.8,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.SCALE
        assert result.approved_targets[0].target_exposure == 0.5

    def test_reject_when_drawdown_exceeded_and_increasing(self) -> None:
        """Drawdown limit exceeded with exposure increase -> REJECT."""
        config = RiskConfig(max_drawdown_limit=0.10)
        engine = RiskEngine(config)
        engine.initialize()

        # 15% drawdown, trying to increase from 0.2 to 0.5 gross
        state = PortfolioState(
            cash=8_500.0,
            qty=20.0,
            avg_entry_price=100.0,
            realized_pnl=-1_500.0,
            peak_equity=10_000.0,
        )
        bars = {"BTCUSDT": make_market_bar("BTCUSDT", 1_000_000_000_000)}
        prices = {"BTCUSDT": 100.0}
        targets = [
            CombinedTarget(
                asset_class=AssetClass.CRYPTO,
                venue="BINANCE",
                symbol="BTCUSDT",
                target_exposure=0.5,
                contributing_engines=(EngineType.TREND,),
                gross_exposure_contribution=0.5,
                net_exposure_contribution=0.5,
            )
        ]
        combo = make_combination_result(targets)
        context = make_risk_context(state, prices, bars, combo)

        result = engine.evaluate(context)
        assert result.decision == RiskDecision.REJECT
        assert result.reason == RiskReasonCode.DRAWDOWN_GATE_EXPOSURE_INCREASE_BLOCKED

    def test_config_fingerprint_deterministic(self) -> None:
        """Config fingerprint is deterministic."""
        config1 = RiskConfig(max_drawdown_limit=0.15)
        config2 = RiskConfig(max_drawdown_limit=0.15)
        engine1 = RiskEngine(config1)
        engine2 = RiskEngine(config2)

        assert engine1._config_fingerprint == engine2._config_fingerprint
        assert len(engine1._config_fingerprint) == 16


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
