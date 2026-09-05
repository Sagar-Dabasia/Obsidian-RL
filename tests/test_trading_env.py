"""Gymnasium environment tests: compliance, determinism, hand-calculated trajectories,
reward components, termination vs truncation, no-future-access."""

import math

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from obsidian_rl.env.trading_env import RewardConfig, TradingEnv
from obsidian_rl.features.pipeline import WARMUP_ROWS, compute_market_features
from obsidian_rl.portfolio.costs import CostModel
from obsidian_rl.portfolio.engine import PortfolioConfig
from tests.conftest import make_candles

CM = CostModel(taker_fee=0.001, half_spread=0.0005, slippage=0.0005)  # 0.2% total
FLAT, HALF_SHORT, FULL_LONG = 2, 1, 4  # indices into (-1,-0.5,0,0.5,1)


def make_env(n: int = 300, **kwargs: object) -> TradingEnv:
    defaults: dict[str, object] = {
        "cost_model": CM,
        "episode_length": 50,
        "random_start": False,
    }
    defaults.update(kwargs)
    return TradingEnv(make_candles(n), **defaults)  # type: ignore[arg-type]


def test_gymnasium_check_env_passes() -> None:
    env = make_env()
    check_env(env, skip_render_check=True)


def test_deterministic_seeding() -> None:
    env_a, env_b = make_env(random_start=True), make_env(random_start=True)
    obs_a, info_a = env_a.reset(seed=123)
    obs_b, info_b = env_b.reset(seed=123)
    assert info_a["start_index"] == info_b["start_index"]
    np.testing.assert_array_equal(obs_a, obs_b)
    obs_c, info_c = make_env(random_start=True).reset(seed=999)
    assert info_c["start_index"] != info_a["start_index"] or not np.array_equal(obs_c, obs_a)


def test_hand_calculated_trajectory_flat_then_long() -> None:
    """With flat actions equity never moves; a long action pays exact costs."""
    candles = make_candles(WARMUP_ROWS + 20)
    env = TradingEnv(
        candles,
        cost_model=CM,
        episode_length=10,
        random_start=False,
        reward_config=RewardConfig(turnover_weight=0.0, drawdown_weight=0.0),
        portfolio_config=PortfolioConfig(initial_cash=10_000.0),
    )
    env.reset(seed=0)
    _obs, r, _term, _trunc, info = env.step(FLAT)
    assert r == 0.0 and info["net_equity"] == pytest.approx(10_000.0)

    t = WARMUP_ROWS + 1  # env is now at this row; execution at open[t+1]
    exec_px = float(candles["open"].iloc[t + 1])
    next_close = float(candles["close"].iloc[t + 1])
    qty = 10_000.0 / exec_px
    costs = 10_000.0 * 0.002
    expected_equity = 10_000.0 - costs + qty * (next_close - exec_px)
    _obs, r, _term, _trunc, info = env.step(FULL_LONG)
    assert info["net_equity"] == pytest.approx(expected_equity, rel=1e-9)
    assert r == pytest.approx(math.log(expected_equity / 10_000.0), rel=1e-6)
    assert info["execution"]["total_cost"] == pytest.approx(costs)


def test_reward_components_sum_to_reward() -> None:
    env = make_env(reward_config=RewardConfig(0.05, 0.01, 0.02))
    env.reset(seed=1)
    for action in (FULL_LONG, HALF_SHORT, FLAT, FULL_LONG):
        _obs, r, term, trunc, info = env.step(action)
        assert r == pytest.approx(sum(info["reward_components"].values()), abs=1e-12)
        if term or trunc:
            break


def test_turnover_penalty_active() -> None:
    candles = make_candles(WARMUP_ROWS + 20)
    kwargs: dict[str, object] = {
        "cost_model": CM,
        "episode_length": 5,
        "random_start": False,
        "portfolio_config": PortfolioConfig(initial_cash=10_000.0),
    }
    env_no = TradingEnv(candles, reward_config=RewardConfig(0.0, 0.0, 0.0), **kwargs)  # type: ignore[arg-type]
    env_yes = TradingEnv(candles, reward_config=RewardConfig(0.1, 0.0, 0.0), **kwargs)  # type: ignore[arg-type]
    env_no.reset(seed=0)
    env_yes.reset(seed=0)
    _, r_no, _, _, info_no = env_no.step(FULL_LONG)
    _, r_yes, _, _, _info_yes = env_yes.step(FULL_LONG)
    notional = info_no["execution"]["traded_notional"]
    assert r_yes == pytest.approx(r_no - 0.1 * notional / 10_000.0, rel=1e-9)


def test_truncation_at_episode_budget() -> None:
    env = make_env(episode_length=3)
    env.reset(seed=0)
    results = [env.step(FLAT) for _ in range(3)]
    *_, (_obs, _r, term, trunc, _info) = results
    assert trunc is True and term is False


def test_truncation_at_end_of_data() -> None:
    env = make_env(n=WARMUP_ROWS + 5, episode_length=None)
    env.reset(seed=0)
    steps = 0
    trunc = False
    while not trunc and steps < 100:
        _, _, _term, trunc, _ = env.step(FLAT)
        steps += 1
    assert trunc and steps == 4  # decisions at rows W..W+3, executing into W+1..W+4


def test_terminal_liquidation_flattens_position() -> None:
    env = make_env(episode_length=2)
    env.reset(seed=0)
    env.step(FULL_LONG)
    _, _, _term, trunc, _info = env.step(FULL_LONG)
    assert trunc
    assert env._engine is not None
    assert env._engine.state.qty == 0.0  # liquidated


def test_invalid_action_raises() -> None:
    env = make_env()
    env.reset(seed=0)
    with pytest.raises(ValueError, match="invalid action"):
        env.step(7)


def test_no_future_information_in_observation() -> None:
    """Env obs at internal row t must equal features computed without any later candle."""
    candles = make_candles(300)
    env = TradingEnv(candles, cost_model=CM, episode_length=20, random_start=False)
    obs, info = env.reset(seed=0)
    t = info["start_index"]
    truncated_feats = compute_market_features(candles.iloc[: t + 1].copy())
    expected_market = truncated_feats.iloc[-1].to_numpy(dtype=np.float32)
    np.testing.assert_array_equal(obs[: len(expected_market)], expected_market)


def test_executed_action_reported_in_info() -> None:
    env = make_env()
    env.reset(seed=0)
    _, _, _, _, info = env.step(FULL_LONG)
    assert info["proposed_target"] == 1.0
    assert info["executed_target"] == pytest.approx(1.0, abs=0.05)


def test_reward_config_validation_rejects_invalid_turnover_penalty_bps() -> None:
    # bool rejected
    with pytest.raises(ValueError, match="must be int or float"):
        RewardConfig(turnover_penalty_bps=True)  # type: ignore[arg-type]
    # negative rejected
    with pytest.raises(ValueError, match="must be non-negative"):
        RewardConfig(turnover_penalty_bps=-1.0)
    # NaN rejected
    with pytest.raises(ValueError, match="must be finite"):
        RewardConfig(turnover_penalty_bps=float("nan"))
    # Infinity rejected
    with pytest.raises(ValueError, match="must be finite"):
        RewardConfig(turnover_penalty_bps=float("inf"))
    # valid values pass
    assert RewardConfig(turnover_penalty_bps=0.0).turnover_penalty_bps == 0.0
    assert RewardConfig(turnover_penalty_bps=5.5).turnover_penalty_bps == 5.5


def test_turnover_regularization_zero_penalty_behavior_identical() -> None:
    candles = make_candles(WARMUP_ROWS + 30)
    env_zero = TradingEnv(
        candles,
        reward_config=RewardConfig(turnover_penalty_bps=0.0),
        episode_length=15,
        random_start=False,
    )
    env_default = TradingEnv(
        candles, reward_config=RewardConfig(), episode_length=15, random_start=False
    )
    obs_z, info_z = env_zero.reset(seed=42)
    obs_d, info_d = env_default.reset(seed=42)
    np.testing.assert_array_equal(obs_z, obs_d)
    assert info_z == info_d

    for action in (FULL_LONG, FLAT, HALF_SHORT, 0, FULL_LONG):
        obs_z, r_z, term_z, trunc_z, info_z = env_zero.step(action)
        obs_d, r_d, term_d, trunc_d, info_d = env_default.step(action)
        np.testing.assert_array_equal(obs_z, obs_d)
        assert r_z == r_d
        assert term_z == term_d and trunc_z == trunc_d
        assert info_z["penalty"] == 0.0
        assert info_z["reward_components"]["turnover_regularization_penalty"] == -0.0
        assert info_z["raw_reward"] == r_z


def test_turnover_regularization_hand_calculated_target_changes() -> None:
    candles = make_candles(WARMUP_ROWS + 30)
    tp_bps = 10.0  # 10 bps -> 0.001 per unit target change
    env = TradingEnv(
        candles,
        reward_config=RewardConfig(turnover_penalty_bps=tp_bps),
        episode_length=15,
        random_start=False,
    )
    env.reset(seed=0)

    # Step 1: flat (0.0) -> FULL_LONG (1.0). Target change = |1.0 - 0.0| = 1.0.
    # Penalty = 0.001 * 1.0 = 0.001.
    _, r1, _, _, info1 = env.step(FULL_LONG)
    expected_pen1 = (tp_bps / 10000.0) * 1.0
    assert info1["penalty"] == pytest.approx(expected_pen1)
    assert info1["raw_reward"] - info1["penalty"] == pytest.approx(r1)
    assert info1["final_reward"] == pytest.approx(r1)
    assert info1["reward_components"]["turnover_regularization_penalty"] == pytest.approx(
        -expected_pen1
    )

    # Step 2: no target change (FULL_LONG -> FULL_LONG). Target change = |1.0 - 1.0| = 0.0.
    # Penalty = 0.0.
    _, r2, _, _, info2 = env.step(FULL_LONG)
    assert info2["penalty"] == pytest.approx(0.0)
    assert info2["reward_components"]["turnover_regularization_penalty"] == pytest.approx(0.0)
    assert r2 == pytest.approx(info2["raw_reward"])

    # Step 3: long-to-short (FULL_LONG 1.0 -> FULL_SHORT -1.0, index 0). Target change =
    # |-1.0 - 1.0| = 2.0.
    _, r3, _, _, info3 = env.step(0)
    expected_pen3 = (tp_bps / 10000.0) * 2.0
    assert info3["penalty"] == pytest.approx(expected_pen3)
    assert info3["raw_reward"] - info3["penalty"] == pytest.approx(r3)
    assert info3["reward_components"]["turnover_regularization_penalty"] == pytest.approx(
        -expected_pen3
    )
