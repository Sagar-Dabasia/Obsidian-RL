import math

import pytest

from obsidian_rl.evaluation.statistical_validity import (
    compute_dsr,
    compute_psr,
    expected_maximum_sr,
)


def test_psr_known_reference_normal():
    # sr = 1.0, benchmark = 0.5, obs = 101, skew = 0, kurt = 3 (normal)
    psr = compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=0.0, kurtosis=3.0)
    assert math.isclose(psr, 0.9999778, abs_tol=1e-6)


def test_psr_known_reference_skewed_kurtotic():
    # sr = 1.0, benchmark = 0.5, obs = 101, skew = -1.0, kurt = 7.0
    psr = compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=-1.0, kurtosis=7.0)
    assert math.isclose(psr, 0.996236, abs_tol=1e-5)

    psr_normal = compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=0.0, kurtosis=3.0)
    assert psr < psr_normal


def test_dsr_known_reference():
    # trials_var = 0.01, num_trials = 10
    exp_max = expected_maximum_sr(trials_sr_var=0.01, num_trials=10)
    assert math.isclose(exp_max, 0.1574589, abs_tol=1e-5)

    dsr = compute_dsr(
        sr=1.0,
        trials_sr_var=0.01,
        num_trials=10,
        num_obs=101,
        skewness=0.0,
        kurtosis=3.0,
    )
    assert math.isclose(dsr, 1.0, abs_tol=1e-7)


def test_dsr_increasing_trial_penalty():
    dsr_1 = compute_dsr(
        sr=0.5, trials_sr_var=0.04, num_trials=2, num_obs=101, skewness=0.0, kurtosis=3.0
    )
    dsr_100 = compute_dsr(
        sr=0.5, trials_sr_var=0.04, num_trials=100, num_obs=101, skewness=0.0, kurtosis=3.0
    )
    dsr_1000 = compute_dsr(
        sr=0.5, trials_sr_var=0.04, num_trials=1000, num_obs=101, skewness=0.0, kurtosis=3.0
    )

    assert dsr_1 > dsr_100 > dsr_1000


def test_dsr_one_trial_behavior():
    exp_max = expected_maximum_sr(trials_sr_var=0.04, num_trials=1)
    assert exp_max == 0.0

    dsr_1 = compute_dsr(
        sr=0.5, trials_sr_var=0.04, num_trials=1, num_obs=101, skewness=0.0, kurtosis=3.0
    )
    psr_0 = compute_psr(sr=0.5, sr_benchmark=0.0, num_obs=101, skewness=0.0, kurtosis=3.0)
    assert dsr_1 == psr_0


def test_invalid_num_obs():
    with pytest.raises(ValueError, match="num_obs must be strictly greater than 1"):
        compute_psr(sr=1.0, sr_benchmark=0.0, num_obs=1, skewness=0.0, kurtosis=3.0)

    with pytest.raises(ValueError, match="num_obs must be strictly greater than 1"):
        compute_dsr(
            sr=1.0, trials_sr_var=0.01, num_trials=10, num_obs=0, skewness=0.0, kurtosis=3.0
        )


def test_invalid_trial_count():
    with pytest.raises(ValueError, match="num_trials must be at least 1"):
        compute_dsr(
            sr=1.0, trials_sr_var=0.01, num_trials=0, num_obs=101, skewness=0.0, kurtosis=3.0
        )

    with pytest.raises(ValueError, match="num_trials must be at least 1"):
        compute_dsr(
            sr=1.0, trials_sr_var=0.01, num_trials=-5, num_obs=101, skewness=0.0, kurtosis=3.0
        )

    with pytest.raises(TypeError, match="num_trials must be an integer"):
        compute_dsr(
            sr=1.0,
            trials_sr_var=0.01,
            num_trials=10.5,
            num_obs=101,
            skewness=0.0,
            kurtosis=3.0,
        )  # type: ignore


def test_nan_inf_inputs():
    with pytest.raises(ValueError, match="Inputs cannot be NaN"):
        compute_psr(sr=float("nan"), sr_benchmark=0.0, num_obs=101, skewness=0.0, kurtosis=3.0)

    with pytest.raises(ValueError, match="Inputs cannot be inf"):
        compute_psr(sr=1.0, sr_benchmark=float("inf"), num_obs=101, skewness=0.0, kurtosis=3.0)

    with pytest.raises(ValueError, match="trials_sr_var must be finite"):
        compute_dsr(
            sr=1.0,
            trials_sr_var=float("inf"),
            num_trials=10,
            num_obs=101,
            skewness=0.0,
            kurtosis=3.0,
        )


def test_invalid_variance():
    # Kurtosis too low causing negative variance
    with pytest.raises(ValueError, match="Calculated variance must be strictly positive"):
        compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=0.0, kurtosis=-10.0)

    with pytest.raises(
        ValueError, match="trials_sr_var must be strictly positive for multiple trials"
    ):
        compute_dsr(
            sr=1.0, trials_sr_var=0.0, num_trials=10, num_obs=101, skewness=0.0, kurtosis=3.0
        )

    with pytest.raises(
        ValueError, match="trials_sr_var must be strictly positive for multiple trials"
    ):
        compute_dsr(
            sr=1.0, trials_sr_var=-0.01, num_trials=10, num_obs=101, skewness=0.0, kurtosis=3.0
        )


def test_deterministic_repeatability():
    outputs = [
        compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=-0.5, kurtosis=4.0)
        for _ in range(10)
    ]
    assert len(set(outputs)) == 1


def test_output_probability_bounded():
    prob_high = compute_psr(sr=100.0, sr_benchmark=0.0, num_obs=1000, skewness=0.0, kurtosis=3.0)
    prob_low = compute_psr(sr=-100.0, sr_benchmark=0.0, num_obs=1000, skewness=0.0, kurtosis=3.0)

    assert 0.0 <= prob_high <= 1.0
    assert 0.0 <= prob_low <= 1.0

    dsr_high = compute_dsr(
        sr=100.0,
        trials_sr_var=0.1,
        num_trials=10000,
        num_obs=1000,
        skewness=0.0,
        kurtosis=3.0,
    )
    assert 0.0 <= dsr_high <= 1.0
