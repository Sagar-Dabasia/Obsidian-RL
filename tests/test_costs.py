"""Cost model tests with hand-calculated values."""

import pytest

from obsidian_rl.portfolio.costs import CostModel, funding_cash_flow


def test_component_costs_on_notional() -> None:
    cm = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)
    assert cm.fee_cost(10_000) == pytest.approx(10.0)
    assert cm.spread_cost(10_000) == pytest.approx(5.0)
    assert cm.slippage_cost(10_000) == pytest.approx(5.0)
    assert cm.total_cost(10_000) == pytest.approx(20.0)
    assert cm.total_cost(-10_000) == pytest.approx(20.0)  # sign-agnostic


def test_round_trip_rate() -> None:
    cm = CostModel(taker_fee=0.0005, half_spread=0.00005, slippage=0.0001)
    assert cm.round_trip_rate == pytest.approx(0.0013)


def test_insane_parameters_rejected() -> None:
    with pytest.raises(ValueError):
        CostModel(taker_fee=-0.001)
    with pytest.raises(ValueError):
        CostModel(slippage=0.5)


def test_nonfinite_and_bool_parameters_rejected() -> None:
    import math
    for name in ("taker_fee", "half_spread", "slippage"):
        with pytest.raises(ValueError):
            CostModel(**{name: True})
        with pytest.raises(ValueError):
            CostModel(**{name: False})
        with pytest.raises(ValueError):
            CostModel(**{name: float("nan")})
        with pytest.raises(ValueError):
            CostModel(**{name: float("inf")})
        with pytest.raises(ValueError):
            CostModel(**{name: float("-inf")})


def test_funding_long_pays_positive_rate() -> None:
    # long 100 units at price 100, rate +1bp => pays 1.0
    assert funding_cash_flow(100.0, 100.0, 0.0001) == pytest.approx(-1.0)


def test_funding_short_receives_positive_rate() -> None:
    assert funding_cash_flow(-100.0, 100.0, 0.0001) == pytest.approx(1.0)


def test_funding_negative_rate_reverses() -> None:
    assert funding_cash_flow(100.0, 100.0, -0.0001) == pytest.approx(1.0)
