"""Focused tests for PortfolioCombinationEngine."""

import pytest

from obsidian_rl.data.contracts import AssetClass
from obsidian_rl.engines import (
    CombinationConfig,
    EngineProposal,
    EngineType,
    PortfolioCombinationEngine,
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


class TestPortfolioCombinationEngine:
    """Tests for deterministic combination logic."""

    def test_deterministic_combination(self) -> None:
        """Same inputs always produce identical outputs."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0, EngineType.CARRY: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 0.8),
            make_proposal(EngineType.CARRY, "BTCUSDT", 0.6),
        ]

        result1 = engine.combine(proposals)
        result2 = engine.combine(proposals)

        assert result1.targets == result2.targets
        assert result1.portfolio_gross_exposure == result2.portfolio_gross_exposure
        assert result1.portfolio_net_exposure == result2.portfolio_net_exposure
        assert result1.config_fingerprint == result2.config_fingerprint

    def test_exact_weight_behavior(self) -> None:
        """Weighted average matches manual calculation."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 3.0, EngineType.CARRY: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        # TREND weight 0.75, CARRY weight 0.25
        # Target = 0.75 * 1.0 + 0.25 * (-0.5) = 0.75 - 0.125 = 0.625
        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 1.0),
            make_proposal(EngineType.CARRY, "BTCUSDT", -0.5),
        ]

        result = engine.combine(proposals)
        target = result.targets[0]
        assert target.target_exposure == pytest.approx(0.625)

    def test_invalid_weights_rejected(self) -> None:
        """Negative or non-finite weights raise ValueError."""
        with pytest.raises(ValueError, match=r"weight.*must be non-negative"):
            CombinationConfig(engine_weights={EngineType.TREND: -1.0})

        with pytest.raises(ValueError, match=r"weight.*must be finite"):
            CombinationConfig(engine_weights={EngineType.TREND: float("inf")})

        with pytest.raises(ValueError, match=r"sum of engine_weights must be positive"):
            CombinationConfig(engine_weights={EngineType.TREND: 0.0})

    def test_non_finite_inputs_rejected(self) -> None:
        """NaN/inf in proposals raises ValueError."""

        # Test NaN
        with pytest.raises(ValueError, match=r"target_exposure must be finite"):
            make_proposal(EngineType.TREND, "BTCUSDT", float("nan"))

        # Test infinity
        with pytest.raises(ValueError, match=r"target_exposure must be finite"):
            make_proposal(EngineType.TREND, "BTCUSDT", float("inf"))

    def test_bounded_outputs(self) -> None:
        """All target_exposure outputs are in [-1.0, +1.0]."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        # Input is clamped to [-1, 1] at proposal level, so test that output respects per-asset cap
        proposals = [make_proposal(EngineType.TREND, "BTCUSDT", 1.0)]
        result = engine.combine(proposals)
        assert -1.0 <= result.targets[0].target_exposure <= 1.0

        proposals = [make_proposal(EngineType.TREND, "BTCUSDT", -1.0)]
        result = engine.combine(proposals)
        assert -1.0 <= result.targets[0].target_exposure <= 1.0

    def test_gross_net_exposure_calculation(self) -> None:
        """Gross = sum|targets|, Net = sum(targets)."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0, EngineType.CARRY: 1.0},
            max_gross_exposure=2.0,  # High caps to not trigger scaling
            max_net_exposure=2.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 0.8),
            make_proposal(EngineType.CARRY, "BTCUSDT", 0.6),
            make_proposal(EngineType.TREND, "ETHUSDT", -0.4),
            make_proposal(EngineType.CARRY, "ETHUSDT", -0.2),
        ]

        result = engine.combine(proposals)
        # BTC: (0.8+0.6)/2 = 0.7, ETH: (-0.4-0.2)/2 = -0.3
        # Gross = 0.7 + 0.3 = 1.0, Net = 0.7 - 0.3 = 0.4
        assert result.portfolio_gross_exposure == pytest.approx(1.0)
        assert result.portfolio_net_exposure == pytest.approx(0.4)

    def test_conflicting_engine_proposals(self) -> None:
        """Opposing proposals produce weighted average, not winner-take-all."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0, EngineType.CARRY: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 1.0),
            make_proposal(EngineType.CARRY, "BTCUSDT", -1.0),
        ]

        result = engine.combine(proposals)
        # Equal weights, equal confidence -> average = 0.0
        assert result.targets[0].target_exposure == 0.0

    def test_no_input_mutation(self) -> None:
        """Input proposals are never mutated."""
        config = CombinationConfig(engine_weights={EngineType.TREND: 1.0})
        engine = PortfolioCombinationEngine(config)

        original_target = 0.8
        proposals = [make_proposal(EngineType.TREND, "BTCUSDT", original_target)]
        original_confidence = proposals[0].confidence

        engine.combine(proposals)

        # Proposals unchanged
        assert proposals[0].target_exposure == original_target
        assert proposals[0].confidence == original_confidence

    def test_different_timestamps_rejected(self) -> None:
        """Proposals with different timestamps raise ValueError."""
        config = CombinationConfig(engine_weights={EngineType.TREND: 1.0})
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 0.5, timestamp=1_000_000_000_000),
            make_proposal(EngineType.CARRY, "BTCUSDT", 0.5, timestamp=1_000_000_001_000),
        ]
        with pytest.raises(ValueError, match="identical timestamp_utc"):
            engine.combine(proposals)

    def test_empty_proposals_rejected(self) -> None:
        """Empty proposal list raises ValueError."""
        config = CombinationConfig(engine_weights={EngineType.TREND: 1.0})
        engine = PortfolioCombinationEngine(config)

        with pytest.raises(ValueError, match="proposals must not be empty"):
            engine.combine([])

    def test_per_asset_cap_enforced(self) -> None:
        """Per-asset exposure cap is enforced."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=0.5,  # Cap at 0.5
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [make_proposal(EngineType.TREND, "BTCUSDT", 1.0)]
        result = engine.combine(proposals)
        assert result.targets[0].target_exposure == 0.5

    def test_portfolio_gross_cap_scaling(self) -> None:
        """Portfolio gross exposure cap triggers proportional scaling."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0},
            max_gross_exposure=0.5,  # Low cap
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 0.8),
            make_proposal(EngineType.TREND, "ETHUSDT", 0.6),
        ]
        # Gross would be 1.4, capped to 0.5 -> scale factor 0.5/1.4
        result = engine.combine(proposals)
        assert result.portfolio_gross_exposure == pytest.approx(0.5)
        scale = 0.5 / 1.4
        assert result.targets[0].target_exposure == pytest.approx(0.8 * scale)
        assert result.targets[1].target_exposure == pytest.approx(0.6 * scale)

    def test_portfolio_net_cap_scaling(self) -> None:
        """Portfolio net exposure cap triggers proportional scaling."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0},
            max_gross_exposure=2.0,
            max_net_exposure=0.3,  # Low net cap
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 0.8),
            make_proposal(EngineType.TREND, "ETHUSDT", 0.4),
        ]
        # Net would be 1.2, capped to 0.3 -> scale factor 0.3/1.2 = 0.25
        result = engine.combine(proposals)
        assert result.portfolio_net_exposure == pytest.approx(0.3)
        assert result.targets[0].target_exposure == pytest.approx(0.2)
        assert result.targets[1].target_exposure == pytest.approx(0.1)

    def test_deterministic_ordering(self) -> None:
        """Output targets are sorted deterministically by (asset_class, venue, symbol)."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0},
            max_gross_exposure=2.0,
            max_net_exposure=2.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        # Add in random order
        proposals = [
            make_proposal(EngineType.TREND, "ETHUSDT", 0.5),
            make_proposal(EngineType.TREND, "BTCUSDT", 0.3),
            make_proposal(EngineType.TREND, "SOLUSDT", 0.7),
        ]

        result = engine.combine(proposals)
        symbols = [t.symbol for t in result.targets]
        assert symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_confidence_weighting(self) -> None:
        """Proposal confidence acts as additional weight multiplier."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0, EngineType.CARRY: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        # TREND: weight=0.5, conf=1.0, target=1.0
        # CARRY: weight=0.5, conf=0.5, target=-1.0
        # Numerator = 0.5*1.0*1.0 + 0.5*0.5*(-1.0) = 0.5 - 0.25 = 0.25
        # Denominator = 0.5*1.0 + 0.5*0.5 = 0.5 + 0.25 = 0.75
        # Result = 0.25/0.75 = 1/3
        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 1.0, confidence=1.0),
            make_proposal(EngineType.CARRY, "BTCUSDT", -1.0, confidence=0.5),
        ]
        result = engine.combine(proposals)
        assert result.targets[0].target_exposure == pytest.approx(1.0 / 3.0)

    def test_zero_confidence_ignored(self) -> None:
        """Zero confidence proposals don't contribute to weighted average."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0, EngineType.CARRY: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 1.0, confidence=1.0),
            make_proposal(EngineType.CARRY, "BTCUSDT", -1.0, confidence=0.0),
        ]
        result = engine.combine(proposals)
        # Only TREND contributes
        assert result.targets[0].target_exposure == 1.0

    def test_contributing_engines_tracked(self) -> None:
        """Contributing engines are correctly tracked in output."""
        config = CombinationConfig(
            engine_weights={EngineType.TREND: 1.0, EngineType.CARRY: 1.0, EngineType.MACRO: 1.0},
            max_gross_exposure=1.0,
            max_net_exposure=1.0,
            per_asset_exposure_cap=1.0,
        )
        engine = PortfolioCombinationEngine(config)

        proposals = [
            make_proposal(EngineType.TREND, "BTCUSDT", 1.0, confidence=1.0),
            make_proposal(EngineType.CARRY, "BTCUSDT", 0.5, confidence=1.0),
            make_proposal(EngineType.MACRO, "BTCUSDT", -0.5, confidence=0.0),  # Zero conf
        ]
        result = engine.combine(proposals)
        contrib = result.targets[0].contributing_engines
        assert EngineType.TREND in contrib
        assert EngineType.CARRY in contrib
        assert EngineType.MACRO not in contrib  # Zero confidence
        assert len(contrib) == 2

    def test_config_fingerprint_deterministic(self) -> None:
        """Config fingerprint is deterministic and matches same config."""
        config1 = CombinationConfig(engine_weights={EngineType.TREND: 1.0})
        config2 = CombinationConfig(engine_weights={EngineType.TREND: 1.0})
        engine1 = PortfolioCombinationEngine(config1)
        engine2 = PortfolioCombinationEngine(config2)

        proposals = [make_proposal(EngineType.TREND, "BTCUSDT", 0.5)]
        r1 = engine1.combine(proposals)
        r2 = engine2.combine(proposals)

        assert r1.config_fingerprint == r2.config_fingerprint
        assert len(r1.config_fingerprint) == 16  # SHA256 truncated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
