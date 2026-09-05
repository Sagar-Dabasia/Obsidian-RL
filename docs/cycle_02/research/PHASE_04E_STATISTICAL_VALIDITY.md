# Phase 4E: Statistical Validity Gate

## Overview

This phase implements the mathematical foundation for evaluating the statistical significance of quantitative strategies discovered during research, specifically focusing on the Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR) as defined by Bailey and López de Prado.

## Probabilistic Sharpe Ratio (PSR)

PSR provides an adjusted estimate of the probability that a strategy's true Sharpe ratio exceeds a benchmark, accounting for:
- Non-normal returns (skewness and kurtosis)
- Finite sample length (number of observations)

It produces a rigorous, probability-bounded output (0 to 1) rather than a simple point estimate.

## Deflated Sharpe Ratio (DSR)

DSR extends PSR to correct for selection bias under multiple testing. Whenever multiple configurations, hyper-parameters, or completely distinct strategies are evaluated, the expected maximum Sharpe ratio of random noise increases.

DSR deflates the observed Sharpe ratio by testing it against the expected maximum Sharpe ratio under the null hypothesis, effectively penalizing backtests for the number of trials attempted.

## Trial Governance

- **Explicit Accounting**: Every genuinely attempted strategy, configuration, or hyper-parameter combination counts toward the relevant multiple-testing history.
- **Fail Closed**: Unknown or unrecorded trial counts must result in failure (fail closed). We never infer or fabricate the number of trials.
- **Failed/Invalid Experiments**: Experiments that fail early or are classified as invalid (e.g., Phase 4D) MUST NOT disappear from trial accounting when statistically applicable. Their evaluation consumed degrees of freedom.
- **Phase 4E and Invalid Evidence**: Phase 4E cannot retroactively convert an invalid experiment (like Phase 4D) into valid strategy evidence. We do not calculate PSR/DSR for Phase 4D as a strategy result.

## PBO / CPCV (Probability of Backtest Overfitting / Combinatorially Purged Cross-Validation)

**Status: NOT YET COMPUTABLE**

Current repository evidence lacks the required honest multi-trial return matrix and combinatorial structure to compute PBO or perform CPCV. 

What is required to compute PBO:
1. A complete, uncorrupted matrix of returns for *every* trial/configuration evaluated during a research phase, spanning the identical time period.
2. A strict combinatorial partitioning mechanism that maintains chronology and holdout isolation across all trials simultaneously.

We do not fabricate matrices, folds, trials, or synthetic examples to fulfill this requirement. Until a research phase organically produces the necessary multi-trial matrix under strict isolation, PBO and CPCV remain deferred.
