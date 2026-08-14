import numpy as np
import scipy.stats as stats
import warnings

def compute_psr(sr: float, sr_benchmark: float, num_obs: int, skewness: float, kurtosis: float) -> float:
    """
    Computes the Probabilistic Sharpe Ratio (PSR).
    
    Formula from Bailey & López de Prado (2012) 'The Sharpe Ratio Efficient Frontier'.
    
    Args:
        sr: The observed Sharpe Ratio.
        sr_benchmark: The benchmark Sharpe Ratio to test against.
        num_obs: Number of observations (sample length).
        skewness: Sample skewness of the returns.
        kurtosis: Sample Pearson kurtosis of the returns (Normal = 3).
        
    Returns:
        PSR (float) representing the probability that the true SR > sr_benchmark.
    """
    if num_obs <= 1:
        raise ValueError("num_obs must be strictly greater than 1.")
    if np.isnan(sr) or np.isnan(sr_benchmark) or np.isnan(skewness) or np.isnan(kurtosis):
        raise ValueError("Inputs cannot be NaN.")
    if np.isinf(sr) or np.isinf(sr_benchmark) or np.isinf(skewness) or np.isinf(kurtosis):
        raise ValueError("Inputs cannot be inf.")
        
    # Standard deviation of the estimated Sharpe ratio
    # The asymptotic variance of SR is (1 - skew*SR + (kurt - 1)/4 * SR^2) / (num_obs - 1)
    sr_var = (1.0 - skewness * sr + ((kurtosis - 1.0) / 4.0) * (sr ** 2)) / (num_obs - 1.0)
    
    if sr_var <= 0:
        return 1.0 if sr > sr_benchmark else 0.0
        
    # Calculate the test statistic (Z-score)
    t_stat = (sr - sr_benchmark) / np.sqrt(sr_var)
    
    # Return the CDF of the standard normal distribution
    return float(stats.norm.cdf(t_stat))


def expected_maximum_sr(trials_sr_var: float, num_trials: int, euler_gamma: float = 0.5772156649) -> float:
    """
    Calculates the expected maximum Sharpe ratio over multiple independent trials.
    
    Formula from Bailey & López de Prado (2014) 'The Deflated Sharpe Ratio'.
    """
    if num_trials < 1:
        raise ValueError("num_trials must be at least 1.")
    if num_trials == 1:
        return 0.0
    if trials_sr_var < 0:
        raise ValueError("trials_sr_var cannot be negative.")
        
    # Z-scores for approximation
    z_inv_1 = stats.norm.ppf(1.0 - 1.0 / num_trials)
    z_inv_2 = stats.norm.ppf(1.0 - 1.0 / (num_trials * np.e))
    
    expected_max = np.sqrt(trials_sr_var) * ((1.0 - euler_gamma) * z_inv_1 + euler_gamma * z_inv_2)
    return float(expected_max)


def compute_dsr(sr: float, trials_sr_var: float, num_trials: int, num_obs: int, skewness: float, kurtosis: float) -> float:
    """
    Computes the Deflated Sharpe Ratio (DSR).
    
    Formula from Bailey & López de Prado (2014) 'The Deflated Sharpe Ratio'.
    
    Args:
        sr: The observed Sharpe Ratio of the selected strategy.
        trials_sr_var: The variance of the Sharpe Ratios across all trials.
        num_trials: Explicit number of independent trials (configurations/strategies tested).
        num_obs: Number of observations in the backtest sample.
        skewness: Sample skewness of the selected strategy's returns.
        kurtosis: Sample Pearson kurtosis of the selected strategy's returns (Normal = 3).
        
    Returns:
        DSR (float) representing the probability that the true SR > 0, after adjusting for selection bias.
    """
    if num_trials < 1:
        raise ValueError("num_trials must be at least 1. Unknown trial counts must fail closed.")
        
    # For DSR, the benchmark is the expected maximum SR under the null hypothesis of zero true SR
    # across the multiple trials.
    benchmark_sr = expected_maximum_sr(trials_sr_var, num_trials)
    
    # Calculate PSR against the adjusted benchmark
    return compute_psr(sr, benchmark_sr, num_obs, skewness, kurtosis)

