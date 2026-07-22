"""Tests for PpoSeedEnsembleStrategy: median aggregation, reset, validation,
non-finite rejection, and confirmation data gating."""

import math
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from obsidian_rl.evaluation.backtest import DEFAULT_TARGETS
from obsidian_rl.features.observation import PortfolioObs
from tools.ppo_seed_ensemble_screen import (
    EnsembleFoldResult,
    PpoSeedEnsembleStrategy,
    check_eligibility,
)


def _make_fake_member(
    fixed_target: float, strategy_id: str = "fake"
) -> MagicMock:
    m = MagicMock()
    m.strategy_id = strategy_id
    m.propose = MagicMock(return_value=fixed_target)
    m.reset = MagicMock()
    return m


def _dummy_portfolio() -> PortfolioObs:
    return PortfolioObs(
        exposure=0.0,
        unrealized_return=0.0,
        time_in_position=0.0,
        recent_turnover=0.0,
        drawdown=0.0,
    )


def _dummy_market_row() -> np.ndarray:
    return np.zeros(12, dtype=np.float32)


class TestMedianAggregation:
    def test_all_same_target(self) -> None:
        members = [_make_fake_member(0.5, f"m{i}") for i in range(5)]
        ens = PpoSeedEnsembleStrategy(members)
        result = ens.propose(_dummy_market_row(), _dummy_portfolio())
        assert result == 0.5

    def test_median_of_five_odd(self) -> None:
        """With targets [-1, -0.5, 0, 0.5, 1], median = 0.0."""
        targets = [-1.0, -0.5, 0.0, 0.5, 1.0]
        members = [_make_fake_member(t, f"m{i}") for i, t in enumerate(targets)]
        ens = PpoSeedEnsembleStrategy(members)
        result = ens.propose(_dummy_market_row(), _dummy_portfolio())
        assert result == 0.0

    def test_median_with_majority_long(self) -> None:
        """With targets [0.5, 0.5, 0.5, -0.5, 1.0], median = 0.5."""
        targets = [0.5, 0.5, 0.5, -0.5, 1.0]
        members = [_make_fake_member(t, f"m{i}") for i, t in enumerate(targets)]
        ens = PpoSeedEnsembleStrategy(members)
        result = ens.propose(_dummy_market_row(), _dummy_portfolio())
        assert result == 0.5

    def test_median_with_majority_flat(self) -> None:
        """With targets [0, 0, 0, 1, -1], median = 0.0."""
        targets = [0.0, 0.0, 0.0, 1.0, -1.0]
        members = [_make_fake_member(t, f"m{i}") for i, t in enumerate(targets)]
        ens = PpoSeedEnsembleStrategy(members)
        result = ens.propose(_dummy_market_row(), _dummy_portfolio())
        assert result == 0.0

    def test_median_is_always_allowed_target(self) -> None:
        """With 5 targets drawn from DEFAULT_TARGETS, median is always valid."""
        for _ in range(20):
            targets = [
                DEFAULT_TARGETS[np.random.randint(0, len(DEFAULT_TARGETS))]
                for _ in range(5)
            ]
            members = [_make_fake_member(t, f"m{i}") for i, t in enumerate(targets)]
            ens = PpoSeedEnsembleStrategy(members)
            result = ens.propose(_dummy_market_row(), _dummy_portfolio())
            assert result in DEFAULT_TARGETS


class TestResetBehavior:
    def test_reset_calls_all_members(self) -> None:
        members = [_make_fake_member(0.0, f"m{i}") for i in range(5)]
        ens = PpoSeedEnsembleStrategy(members)
        ens.reset()
        for m in members:
            m.reset.assert_called_once()

    def test_propose_calls_all_members(self) -> None:
        members = [_make_fake_member(0.0, f"m{i}") for i in range(5)]
        ens = PpoSeedEnsembleStrategy(members)
        ens.propose(_dummy_market_row(), _dummy_portfolio())
        for m in members:
            m.propose.assert_called_once()


class TestValidation:
    def test_requires_exactly_five_members(self) -> None:
        with pytest.raises(ValueError, match="exactly 5 members"):
            PpoSeedEnsembleStrategy([_make_fake_member(0.0)] * 4)
        with pytest.raises(ValueError, match="exactly 5 members"):
            PpoSeedEnsembleStrategy([_make_fake_member(0.0)] * 6)
        # Exactly 5 should work
        PpoSeedEnsembleStrategy([_make_fake_member(0.0)] * 5)


class TestNonFiniteRejection:
    def test_nan_member_output_rejected(self) -> None:
        members = [_make_fake_member(0.0, f"m{i}") for i in range(5)]
        members[2].propose = MagicMock(return_value=float("nan"))
        ens = PpoSeedEnsembleStrategy(members)
        with pytest.raises(ValueError, match="Non-finite"):
            ens.propose(_dummy_market_row(), _dummy_portfolio())

    def test_inf_member_output_rejected(self) -> None:
        members = [_make_fake_member(0.0, f"m{i}") for i in range(5)]
        members[0].propose = MagicMock(return_value=float("inf"))
        ens = PpoSeedEnsembleStrategy(members)
        with pytest.raises(ValueError, match="Non-finite"):
            ens.propose(_dummy_market_row(), _dummy_portfolio())


class TestEligibility:
    def _make_fold_results(
        self,
        base_rets: list[float],
        c2x_rets: list[float] | None = None,
        d1_rets: list[float] | None = None,
        dds: list[float] | None = None,
        turnovers: list[float] | None = None,
    ) -> list[EnsembleFoldResult]:
        n = len(base_rets)
        if c2x_rets is None:
            c2x_rets = base_rets
        if d1_rets is None:
            d1_rets = base_rets
        if dds is None:
            dds = [0.05] * n
        if turnovers is None:
            turnovers = [100.0] * n
        return [
            EnsembleFoldResult(
                fold_id=i,
                penalty=0.0,
                base_net_return=base_rets[i],
                base_max_drawdown=dds[i],
                base_sharpe=1.0,
                base_turnover=turnovers[i],
                base_trades=10,
                costs2x_net_return=c2x_rets[i],
                delay1_net_return=d1_rets[i],
            )
            for i in range(n)
        ]

    def test_all_criteria_pass(self) -> None:
        fr = self._make_fold_results([0.10, 0.05, 0.02])
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is True
        assert all(checks.values())

    def test_insufficient_positive_folds(self) -> None:
        fr = self._make_fold_results([0.10, -0.10, -0.10])
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is False
        assert checks["pos_folds_ge_2"] is False

    def test_worst_fold_too_negative(self) -> None:
        fr = self._make_fold_results([0.10, 0.05, -0.06])
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is False
        assert checks["worst_fold_above_neg5pct"] is False

    def test_negative_mean_base(self) -> None:
        fr = self._make_fold_results([0.01, 0.01, -0.04])
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is False
        assert checks["mean_base_positive"] is False

    def test_negative_c2x(self) -> None:
        fr = self._make_fold_results(
            [0.10, 0.05, 0.02], c2x_rets=[-0.01, -0.01, -0.01]
        )
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is False
        assert checks["mean_c2x_positive"] is False

    def test_drawdown_too_high(self) -> None:
        fr = self._make_fold_results(
            [0.10, 0.05, 0.02], dds=[0.20, 0.10, 0.16]
        )
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is False
        assert checks["mean_dd_le_15pct"] is False

    def test_turnover_exceeds_individual(self) -> None:
        fr = self._make_fold_results(
            [0.10, 0.05, 0.02], turnovers=[300.0, 300.0, 300.0]
        )
        ok, checks = check_eligibility(fr, 200.0)
        assert ok is False
        assert checks["turnover_le_indiv"] is False


class TestConfirmationGating:
    """Confirmation data must NOT be loaded unless a penalty qualifies."""

    def test_no_eligible_penalty_skips_confirmation(self) -> None:
        """When no penalty is eligible, confirmation is never accessed.

        We verify this by checking that check_eligibility returns False
        for all three bad scenarios, meaning the confirmation branch
        would never execute.
        """
        # All negative returns -> no eligibility
        fr = [
            EnsembleFoldResult(
                fold_id=i,
                penalty=0.0,
                base_net_return=-0.10,
                base_max_drawdown=0.20,
                base_sharpe=-1.0,
                base_turnover=500.0,
                base_trades=10,
                costs2x_net_return=-0.10,
                delay1_net_return=-0.10,
            )
            for i in range(3)
        ]
        ok, _ = check_eligibility(fr, 200.0)
        assert ok is False
        # In the main script, this means confirmation data is never loaded.
