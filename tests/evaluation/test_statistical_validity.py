import pytest
import numpy as np
import scipy.stats as stats
import math
from obsidian_rl.evaluation.statistical_validity import compute_psr, compute_dsr, expected_maximum_sr

def test_psr_known_reference_normal():
    # sr = 1.0, benchmark = 0.5, obs = 101, skew = 0, kurt = 3 (normal)
    # var = (1 - 0 + (3-1)/4) / 100 = 1.5 / 100 = 0.015
    # sd = sqrt(0.015) ≈ 0.122474487
    # t_stat = 0.5 / sd ≈ 4.0824829
    # expected cdf ≈ 0.9999778
    psr = compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=0.0, kurtosis=3.0)
    assert np.isclose(psr, 0.9999778, atol=1e-6)

def test_psr_known_reference_skewed_kurtotic():
    # sr = 1.0, benchmark = 0.5, obs = 101, skew = -1.0, kurt = 7.0
    # var = (1 - (-1) + (7-1)/4) / 100 = 3.5 / 100 = 0.035
    # sd = sqrt(0.035) ≈ 0.187082869
    # t_stat = 0.5 / sd ≈ 2.6726124
    # expected cdf ≈ 0.996236
    psr = compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=-1.0, kurtosis=7.0)
    assert np.isclose(psr, 0.996236, atol=1e-5)
    
    # Skewed and kurtotic case should yield a lower probability than the normal case
    psr_normal = compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=0.0, kurtosis=3.0)
    assert psr < psr_normal

def test_dsr_known_reference():
    # trials_var = 0.01, num_trials = 10
    # Expected max SR ≈ 0.1574589
    exp_max = expected_maximum_sr(trials_sr_var=0.01, num_trials=10)
    assert np.isclose(exp_max, 0.1574589, atol=1e-5)
    
    # DSR with sr=1.0 against exp_max=0.1574589, obs=101, skew=0, kurt=3
    # t_stat = (1.0 - 0.1574589) / sqrt(0.015) ≈ 6.879
    dsr = compute_dsr(sr=1.0, trials_sr_var=0.01, num_trials=10, num_obs=101, skewness=0.0, kurtosis=3.0)
    # Extremely high t-stat means it should be basically 1.0
    assert np.isclose(dsr, 1.0, atol=1e-7)
    
def test_dsr_increasing_trial_penalty():
    dsr_1 = compute_dsr(sr=0.5, trials_sr_var=0.04, num_trials=2, num_obs=101, skewness=0.0, kurtosis=3.0)
    dsr_100 = compute_dsr(sr=0.5, trials_sr_var=0.04, num_trials=100, num_obs=101, skewness=0.0, kurtosis=3.0)
    dsr_1000 = compute_dsr(sr=0.5, trials_sr_var=0.04, num_trials=1000, num_obs=101, skewness=0.0, kurtosis=3.0)
    
    # As the number of trials increases, the expected max SR increases, 
    # making the fixed SR of 0.5 less impressive, so DSR should decrease.
    assert dsr_1 > dsr_100 > dsr_1000

def test_dsr_one_trial_behavior():
    # 1 trial should have an expected max SR of 0.0 (the base null hypothesis)
    exp_max = expected_maximum_sr(trials_sr_var=0.04, num_trials=1)
    assert exp_max == 0.0
    
    # DSR with 1 trial should be exactly equal to PSR with benchmark = 0.0
    dsr_1 = compute_dsr(sr=0.5, trials_sr_var=0.04, num_trials=1, num_obs=101, skewness=0.0, kurtosis=3.0)
    psr_0 = compute_psr(sr=0.5, sr_benchmark=0.0, num_obs=101, skewness=0.0, kurtosis=3.0)
    assert dsr_1 == psr_0

def test_invalid_num_obs():
    with pytest.raises(ValueError, match="num_obs must be strictly greater than 1"):
        compute_psr(sr=1.0, sr_benchmark=0.0, num_obs=1, skewness=0.0, kurtosis=3.0)
        
    with pytest.raises(ValueError, match="num_obs must be strictly greater than 1"):
        compute_dsr(sr=1.0, trials_sr_var=0.01, num_trials=10, num_obs=0, skewness=0.0, kurtosis=3.0)

def test_invalid_trial_count():
    with pytest.raises(ValueError, match="num_trials must be at least 1"):
        compute_dsr(sr=1.0, trials_sr_var=0.01, num_trials=0, num_obs=101, skewness=0.0, kurtosis=3.0)
        
    with pytest.raises(ValueError, match="num_trials must be at least 1"):
        compute_dsr(sr=1.0, trials_sr_var=0.01, num_trials=-5, num_obs=101, skewness=0.0, kurtosis=3.0)

def test_nan_inf_inputs():
    with pytest.raises(ValueError, match="Inputs cannot be NaN"):
        compute_psr(sr=np.nan, sr_benchmark=0.0, num_obs=101, skewness=0.0, kurtosis=3.0)
        
    with pytest.raises(ValueError, match="Inputs cannot be inf"):
        compute_psr(sr=1.0, sr_benchmark=np.inf, num_obs=101, skewness=0.0, kurtosis=3.0)

def test_deterministic_repeatability():
    # Same inputs must yield exactly the same float every time
    outputs = [compute_psr(sr=1.0, sr_benchmark=0.5, num_obs=101, skewness=-0.5, kurtosis=4.0) for _ in range(10)]
    assert len(set(outputs)) == 1

def test_output_probability_bounded():
    # Extreme values should still yield probabilities in [0, 1]
    prob_high = compute_psr(sr=100.0, sr_benchmark=0.0, num_obs=1000, skewness=0.0, kurtosis=3.0)
    prob_low = compute_psr(sr=-100.0, sr_benchmark=0.0, num_obs=1000, skewness=0.0, kurtosis=3.0)
    
    assert 0.0 <= prob_high <= 1.0
    assert 0.0 <= prob_low <= 1.0
    
    dsr_high = compute_dsr(sr=100.0, trials_sr_var=0.1, num_trials=10000, num_obs=1000, skewness=0.0, kurtosis=3.0)
    assert 0.0 <= dsr_high <= 1.0
