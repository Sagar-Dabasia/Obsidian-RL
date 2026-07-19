"""Hand-calculated portfolio accounting tests.

Cost model used throughout: fee 10bp, half-spread 5bp, slippage 5bp => 20bp per notional.
Initial cash 10_000. Prices chosen so expected values are exact by hand.
"""

import pytest

from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig, PortfolioEngine

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)  # 0.2% total


def make_engine(**kwargs: object) -> PortfolioEngine:
    cfg = PortfolioConfig(initial_cash=10_000.0, **kwargs)  # type: ignore[arg-type]
    return PortfolioEngine(cfg, CM)


def test_open_and_close_long() -> None:
    eng = make_engine()
    r = eng.rebalance(1.0, 100.0)
    # equity 10000 => qty 100, notional 10000, costs 20
    assert r.delta_qty == pytest.approx(100.0)
    assert r.total_cost == pytest.approx(20.0)
    s = eng.state
    assert s.cash == pytest.approx(9_980.0)
    assert s.qty == pytest.approx(100.0)
    assert s.avg_entry_price == pytest.approx(100.0)
    assert s.net_equity(100.0) == pytest.approx(9_980.0)

    # price rises to 110: unrealized 1000
    assert s.unrealized_pnl(110.0) == pytest.approx(1_000.0)
    assert s.net_equity(110.0) == pytest.approx(10_980.0)

    r2 = eng.rebalance(0.0, 110.0)
    # close 100 @110: notional 11000, costs 22, realized +1000
    assert r2.realized_pnl_delta == pytest.approx(1_000.0)
    assert r2.total_cost == pytest.approx(22.0)
    assert s.qty == 0.0
    assert s.avg_entry_price == 0.0
    assert s.cash == pytest.approx(9_980.0 + 1_000.0 - 22.0)
    assert s.net_equity(110.0) == pytest.approx(10_958.0)


def test_open_and_close_short() -> None:
    eng = make_engine()
    eng.rebalance(-1.0, 100.0)
    s = eng.state
    assert s.qty == pytest.approx(-100.0)
    assert s.cash == pytest.approx(9_980.0)
    # price falls to 90: short gains 1000
    assert s.unrealized_pnl(90.0) == pytest.approx(1_000.0)
    r = eng.rebalance(0.0, 90.0)
    # close 100 @90: notional 9000, costs 18
    assert r.realized_pnl_delta == pytest.approx(1_000.0)
    assert s.cash == pytest.approx(9_980.0 + 1_000.0 - 18.0)
    assert s.net_equity(90.0) == pytest.approx(10_962.0)


def test_short_loses_when_price_rises() -> None:
    eng = make_engine()
    eng.rebalance(-1.0, 100.0)
    assert eng.state.unrealized_pnl(105.0) == pytest.approx(-500.0)


def test_increase_position_weighted_entry() -> None:
    eng = make_engine(min_trade_notional=0.0)
    eng.rebalance(0.5, 100.0)
    s = eng.state
    # equity 10000 => half long = 50 units, notional 5000, costs 10, cash 9990
    assert s.qty == pytest.approx(50.0)
    assert s.cash == pytest.approx(9_990.0)
    # price 120: equity = 9990 + 50*20 = 10990; increase to full long
    eng.rebalance(1.0, 120.0)
    # target qty = 10990/120 = 91.58333...; delta = 41.58333; notional = 4990
    assert s.qty == pytest.approx(10_990.0 / 120.0)
    expected_entry = (50.0 * 100.0 + (10_990.0 / 120.0 - 50.0) * 120.0) / (10_990.0 / 120.0)
    assert s.avg_entry_price == pytest.approx(expected_entry)
    assert s.cash == pytest.approx(9_990.0 - 4_990.0 * 0.002)


def test_reduce_position_realizes_proportional_pnl() -> None:
    eng = make_engine(min_trade_notional=0.0)
    eng.rebalance(1.0, 100.0)  # 100 units, cash 9980
    # price 110, equity 10980; reduce to half exposure => target qty = 0.5*10980/110 = 49.909090..
    r = eng.rebalance(0.5, 110.0)
    closed = 100.0 - 0.5 * 10_980.0 / 110.0
    assert r.realized_pnl_delta == pytest.approx(closed * 10.0)
    assert eng.state.avg_entry_price == pytest.approx(100.0)  # unchanged when reducing


def test_long_to_short_reversal_costs_full_delta() -> None:
    eng = make_engine()
    eng.rebalance(1.0, 100.0)  # qty 100, cash 9980
    r = eng.rebalance(-1.0, 100.0)  # same price: equity 9980, target qty -99.8
    assert r.delta_qty == pytest.approx(-199.8)
    assert r.traded_notional == pytest.approx(19_980.0)
    assert r.total_cost == pytest.approx(19_980.0 * 0.002)
    s = eng.state
    assert s.qty == pytest.approx(-99.8)
    assert s.avg_entry_price == pytest.approx(100.0)  # new short entry at exec price
    assert r.realized_pnl_delta == pytest.approx(0.0)  # flat price => nothing realized
    assert s.cash == pytest.approx(9_980.0 - 39.96)


def test_short_to_long_reversal_realizes_short_pnl() -> None:
    eng = make_engine()
    eng.rebalance(-1.0, 100.0)  # qty -100, cash 9980
    # price falls to 90: equity = 9980 + 1000 = 10980
    r = eng.rebalance(1.0, 90.0)
    # realized on closing short: +1000; new long qty = 10980/90 = 122.0
    assert r.realized_pnl_delta == pytest.approx(1_000.0)
    s = eng.state
    assert s.qty == pytest.approx(122.0)
    assert s.avg_entry_price == pytest.approx(90.0)
    # traded delta = 100 + 122 = 222 units @90 = 19980 notional, costs 39.96
    assert r.traded_notional == pytest.approx(19_980.0)
    assert s.cash == pytest.approx(9_980.0 + 1_000.0 - 39.96)
    assert s.net_equity(90.0) == pytest.approx(10_940.04)


def test_flat_action_and_noop() -> None:
    eng = make_engine()
    r = eng.rebalance(0.0, 100.0)  # already flat
    assert r.delta_qty == 0.0 and r.total_cost == 0.0
    assert eng.state.trade_count == 0
    eng.rebalance(1.0, 100.0)
    n_trades = eng.state.trade_count
    r2 = eng.rebalance(1.0, 100.0)  # same target, same price => no-op via no-trade band
    assert r2.delta_qty == 0.0 and r2.traded_notional == 0.0
    assert eng.state.trade_count == n_trades


def test_equity_conservation_at_constant_price() -> None:
    eng = make_engine(min_trade_notional=0.0)
    price = 100.0
    for target in (0.5, 1.0, -0.5, -1.0, 0.0, 1.0, 0.0):
        before = eng.state.net_equity(price)
        r = eng.rebalance(target, price)
        after = eng.state.net_equity(price)
        assert after == pytest.approx(before - r.total_cost), f"target={target}"


def test_gross_equity_equals_net_plus_costs() -> None:
    eng = make_engine(min_trade_notional=0.0)
    eng.rebalance(1.0, 100.0)
    eng.rebalance(-1.0, 105.0)
    eng.apply_funding(105.0, 0.0001)
    s = eng.state
    assert s.gross_equity(105.0) == pytest.approx(s.net_equity(105.0) + s.total_costs())


def test_funding_applied_to_position() -> None:
    eng = make_engine()
    eng.rebalance(1.0, 100.0)  # qty 100
    flow = eng.apply_funding(100.0, 0.0001)  # long pays 100*100*1e-4 = 1.0
    assert flow == pytest.approx(-1.0)
    assert eng.state.funding_paid == pytest.approx(1.0)
    assert eng.state.cash == pytest.approx(9_979.0)


def test_exposure_limits_clamp() -> None:
    eng = make_engine(max_abs_exposure=0.5)
    r = eng.rebalance(1.0, 100.0)
    assert r.approved_target == 0.5
    assert r.rejection_reason is not None
    assert eng.state.qty == pytest.approx(0.5 * 10_000.0 / 100.0)


def test_short_disabled() -> None:
    eng = PortfolioEngine(PortfolioConfig(initial_cash=10_000.0, allow_short=False), CM)
    r = eng.rebalance(-1.0, 100.0)
    assert r.approved_target == 0.0
    assert eng.state.qty == 0.0


def test_drawdown_tracking() -> None:
    eng = make_engine()
    eng.rebalance(1.0, 100.0)  # cash 9980, qty 100
    eng.mark_to_market(110.0)  # equity 10980 => peak
    assert eng.state.peak_equity == pytest.approx(10_980.0)
    dd = eng.state.drawdown(99.0)  # equity = 9980 + 100*(-1) = 9880
    assert dd == pytest.approx(1.0 - 9_880.0 / 10_980.0)


def test_terminal_liquidation() -> None:
    eng = make_engine()
    eng.rebalance(1.0, 100.0)
    r = eng.liquidate(105.0)
    assert eng.state.qty == 0.0
    assert r.realized_pnl_delta == pytest.approx(500.0)
    assert eng.state.net_equity(105.0) == pytest.approx(eng.state.cash)


def test_bankrupt_forces_flat() -> None:
    eng = make_engine()
    eng.rebalance(1.0, 100.0)
    # catastrophic move: price to 0.01 => equity ~ 9980 - 9999 < 0
    r = eng.rebalance(1.0, 0.01)
    assert r.approved_target == 0.0
    assert eng.state.qty == 0.0
    assert "equity non-positive" in (r.rejection_reason or "")


def test_min_trade_notional_skips_dust() -> None:
    eng = make_engine(min_trade_notional=50.0)
    eng.rebalance(1.0, 100.0)
    # nudge target by a dust amount: delta notional ~ 9980*0.001 = ~10 < 50 => skipped
    r = eng.rebalance(0.999, 100.0)
    assert r.delta_qty == 0.0
    assert r.rejection_reason is not None


def test_leverage_config_rejected() -> None:
    with pytest.raises(ValueError):
        PortfolioConfig(max_abs_exposure=2.0)


def test_liquidate_executes_even_below_min_notional() -> None:
    """Regression (review finding): a close must bypass the no-trade band."""
    eng = make_engine(min_trade_notional=10.0)
    eng.rebalance(0.5, 100.0)  # qty 50
    # price collapses so position notional (50*0.15=7.5) is below min notional
    r = eng.liquidate(0.15)
    assert eng.state.qty == 0.0
    assert r.delta_qty == pytest.approx(-50.0)


def test_close_executes_even_within_exposure_tolerance() -> None:
    """Regression (review finding): |exposure| < tolerance must not make a position
    unclosable when the target is exactly flat."""
    eng = make_engine()
    eng.rebalance(0.5, 100.0)  # qty 50
    # price 1.0: equity ~ 5046, exposure = 50/5046 ~ 0.0099 < tolerance 0.01
    assert abs(eng.state.exposure(1.0)) < eng.config.exposure_tolerance
    r = eng.rebalance(0.0, 1.0)
    assert eng.state.qty == 0.0
    assert r.delta_qty == pytest.approx(-50.0)
