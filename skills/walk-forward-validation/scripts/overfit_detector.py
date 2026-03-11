#!/usr/bin/env python3
"""Overfit detection: Deflated Sharpe Ratio and Probability of Backtest Overfitting.

Computes the Deflated Sharpe Ratio (DSR) to assess whether an observed Sharpe
ratio is statistically significant after accounting for multiple testing,
non-normality, and backtest length. Also computes the Probability of Backtest
Overfitting (PBO) using combinatorial purged cross-validation.

Usage:
    python scripts/overfit_detector.py --demo
    python scripts/overfit_detector.py --help

Dependencies:
    uv pip install numpy scipy

Environment Variables:
    None required (--demo mode uses synthetic data).
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from itertools import combinations
from typing import Optional

import numpy as np
from scipy.stats import norm


# ── Data Classes ────────────────────────────────────────────────────

@dataclasses.dataclass
class DSRResult:
    """Results from Deflated Sharpe Ratio analysis.

    Attributes:
        observed_sr: The observed annualized Sharpe ratio.
        expected_max_sr: Expected maximum SR under the null.
        sr_std_error: Standard error of the SR estimator.
        dsr_pvalue: Probability that observed SR > 0 after deflation.
        num_trials: Number of strategies tested.
        backtest_length: Number of return observations.
        skewness: Return skewness.
        kurtosis: Return kurtosis (not excess).
        is_significant: Whether DSR > 0.95.
    """

    observed_sr: float
    expected_max_sr: float
    sr_std_error: float
    dsr_pvalue: float
    num_trials: int
    backtest_length: int
    skewness: float
    kurtosis: float
    is_significant: bool


@dataclasses.dataclass
class PBOResult:
    """Results from Probability of Backtest Overfitting analysis.

    Attributes:
        pbo: Probability of backtest overfitting.
        n_paths: Number of CPCV paths evaluated.
        n_overfit_paths: Number of paths where IS-best underperforms OOS median.
        logit_values: Logit-transformed relative ranks for each path.
        mean_oos_rank: Mean relative OOS rank of IS-optimal strategy.
        is_overfit: Whether PBO > 0.50.
    """

    pbo: float
    n_paths: int
    n_overfit_paths: int
    logit_values: list[float]
    mean_oos_rank: float
    is_overfit: bool


@dataclasses.dataclass
class MinBTLResult:
    """Minimum Backtest Length result.

    Attributes:
        min_length: Minimum number of observations needed.
        target_sr: Target Sharpe ratio (non-annualized).
        confidence: Confidence level used.
        skewness: Assumed skewness.
        kurtosis: Assumed kurtosis.
    """

    min_length: int
    target_sr: float
    confidence: float
    skewness: float
    kurtosis: float


# ── Deflated Sharpe Ratio ───────────────────────────────────────────

def deflated_sharpe_ratio(
    observed_sr: float,
    num_trials: int,
    backtest_length: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    annualization: float = 1.0,
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio.

    Adjusts the observed Sharpe ratio for multiple testing, non-normality,
    and backtest length. Returns the probability that the observed SR is
    genuinely greater than zero.

    Args:
        observed_sr: Annualized Sharpe ratio of the selected strategy.
        num_trials: Total number of strategies tested (including discarded).
        backtest_length: Number of return observations.
        skewness: Skewness of strategy returns.
        kurtosis: Kurtosis of strategy returns (not excess; normal = 3.0).
        annualization: Annualization factor (e.g., sqrt(365) for daily crypto).
            The observed_sr is de-annualized internally.

    Returns:
        DSRResult with all computed values.
    """
    if num_trials < 1:
        raise ValueError("num_trials must be >= 1")
    if backtest_length < 10:
        raise ValueError("backtest_length must be >= 10")

    # De-annualize the SR for the formula
    sr = observed_sr / annualization if annualization > 1.0 else observed_sr

    # Standard error of the Sharpe ratio estimator
    sr_std = np.sqrt(
        (1.0 - skewness * sr + (kurtosis - 1.0) / 4.0 * sr**2)
        / (backtest_length - 1)
    )

    # Expected maximum SR under null (all strategies have zero true SR)
    euler_mascheroni = 0.5772156649
    if num_trials == 1:
        expected_max_sr = 0.0
    else:
        z1 = norm.ppf(1.0 - 1.0 / num_trials)
        z2 = norm.ppf(1.0 - 1.0 / (num_trials * np.e))
        expected_max_sr = z1 * (1.0 - euler_mascheroni) + euler_mascheroni * z2

    # Deflated SR p-value
    if sr_std > 0:
        dsr = float(norm.cdf((sr - expected_max_sr) / sr_std))
    else:
        dsr = 1.0 if sr > expected_max_sr else 0.0

    return DSRResult(
        observed_sr=observed_sr,
        expected_max_sr=expected_max_sr * annualization,
        sr_std_error=sr_std * annualization,
        dsr_pvalue=dsr,
        num_trials=num_trials,
        backtest_length=backtest_length,
        skewness=skewness,
        kurtosis=kurtosis,
        is_significant=dsr > 0.95,
    )


# ── Probability of Backtest Overfitting ─────────────────────────────

def probability_of_backtest_overfitting(
    strategy_returns: np.ndarray,
    n_groups: int = 6,
    n_test_groups: int = 2,
) -> PBOResult:
    """Compute Probability of Backtest Overfitting using CPCV.

    Splits the data into groups, generates all C(N,k) train/test combinations,
    and measures how often the in-sample optimal strategy underperforms
    out-of-sample.

    Args:
        strategy_returns: 2D array of shape (n_observations, n_strategies).
            Each column is a strategy's return time series.
        n_groups: Number of contiguous groups to split data into.
        n_test_groups: Number of groups to use as test in each combination.

    Returns:
        PBOResult with PBO estimate and diagnostics.
    """
    n_obs, n_strategies = strategy_returns.shape
    if n_strategies < 2:
        raise ValueError("Need at least 2 strategies for PBO")
    if n_groups < 3:
        raise ValueError("Need at least 3 groups for meaningful CPCV")

    group_size = n_obs // n_groups
    if group_size < 5:
        raise ValueError(
            f"Each group has only {group_size} observations. "
            f"Reduce n_groups or provide more data."
        )

    # Create group boundaries
    group_bounds: list[tuple[int, int]] = []
    for i in range(n_groups):
        start = i * group_size
        end = (i + 1) * group_size if i < n_groups - 1 else n_obs
        group_bounds.append((start, end))

    logit_values: list[float] = []
    n_overfit = 0

    for test_combo in combinations(range(n_groups), n_test_groups):
        test_set = set(test_combo)

        # Build train and test index arrays
        train_indices: list[int] = []
        test_indices: list[int] = []

        for g_idx in range(n_groups):
            start, end = group_bounds[g_idx]
            indices = list(range(start, end))
            if g_idx in test_set:
                test_indices.extend(indices)
            else:
                train_indices.extend(indices)

        if not train_indices or not test_indices:
            continue

        train_arr = np.array(train_indices)
        test_arr = np.array(test_indices)

        # Compute in-sample performance (mean return) for each strategy
        is_performance = np.mean(strategy_returns[train_arr], axis=0)

        # Select IS-best strategy
        is_best_idx = int(np.argmax(is_performance))

        # Compute out-of-sample performance for all strategies
        oos_performance = np.mean(strategy_returns[test_arr], axis=0)

        # Rank the IS-best strategy in OOS performance
        oos_rank = int(np.sum(oos_performance > oos_performance[is_best_idx]))
        relative_rank = (oos_rank + 1) / n_strategies  # 1-based, normalized

        # Logit transform (clamp to avoid log(0))
        clamped = np.clip(relative_rank, 0.01, 0.99)
        logit = float(np.log(clamped / (1.0 - clamped)))
        logit_values.append(logit)

        if relative_rank > 0.5:
            n_overfit += 1

    n_paths = len(logit_values)
    pbo = n_overfit / n_paths if n_paths > 0 else 1.0
    mean_rank = float(np.mean([
        (1.0 / (1.0 + np.exp(-lv))) for lv in logit_values
    ])) if logit_values else 1.0

    return PBOResult(
        pbo=pbo,
        n_paths=n_paths,
        n_overfit_paths=n_overfit,
        logit_values=logit_values,
        mean_oos_rank=mean_rank,
        is_overfit=pbo > 0.50,
    )


# ── Minimum Backtest Length ─────────────────────────────────────────

def minimum_backtest_length(
    target_sr: float,
    confidence: float = 0.95,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> MinBTLResult:
    """Compute minimum backtest length for a target Sharpe ratio.

    Args:
        target_sr: Target non-annualized Sharpe ratio.
        confidence: Desired confidence level (e.g., 0.95).
        skewness: Assumed skewness of returns.
        kurtosis: Assumed kurtosis (normal = 3.0).

    Returns:
        MinBTLResult with the minimum number of observations.
    """
    if target_sr <= 0:
        raise ValueError("target_sr must be > 0")

    z_alpha = norm.ppf(confidence)
    variance_factor = 1.0 - skewness * target_sr + (kurtosis - 1.0) / 4.0 * target_sr**2
    min_length = int(np.ceil(1.0 + variance_factor * (z_alpha / target_sr) ** 2))

    return MinBTLResult(
        min_length=min_length,
        target_sr=target_sr,
        confidence=confidence,
        skewness=skewness,
        kurtosis=kurtosis,
    )


# ── Multiple Testing Corrections ───────────────────────────────────

def bonferroni_correction(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Apply Bonferroni correction to a list of p-values.

    Args:
        p_values: List of p-values from individual strategy tests.
        alpha: Family-wise significance level.

    Returns:
        List of booleans (True = reject null = strategy is significant).
    """
    n = len(p_values)
    adjusted_alpha = alpha / n
    return [p < adjusted_alpha for p in p_values]


def holm_correction(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Apply Holm-Bonferroni step-down correction.

    Args:
        p_values: List of p-values.
        alpha: Family-wise significance level.

    Returns:
        List of booleans (True = reject null).
    """
    n = len(p_values)
    sorted_indices = np.argsort(p_values)
    results = [False] * n

    for rank, idx in enumerate(sorted_indices):
        threshold = alpha / (n - rank)
        if p_values[idx] <= threshold:
            results[idx] = True
        else:
            break  # Stop at first non-rejection

    return results


# ── Demo ────────────────────────────────────────────────────────────

def generate_synthetic_strategies(
    n_obs: int = 500,
    n_strategies: int = 20,
    n_genuine: int = 2,
    seed: int = 42,
) -> tuple[np.ndarray, list[str]]:
    """Generate synthetic strategy return streams.

    Creates a mix of strategies with zero true alpha (noise) and a few
    with small genuine alpha, to test overfitting detection.

    Args:
        n_obs: Number of daily observations per strategy.
        n_strategies: Total number of strategies.
        n_genuine: Number of strategies with genuine (small) alpha.
        seed: Random seed.

    Returns:
        Tuple of (returns array [n_obs x n_strategies], strategy names).
    """
    rng = np.random.default_rng(seed)
    daily_vol = 0.03  # ~57% annualized

    returns = np.empty((n_obs, n_strategies))
    names: list[str] = []

    for i in range(n_strategies):
        if i < n_genuine:
            # Genuine alpha: small positive drift
            drift = 0.0003  # ~11% annualized
            returns[:, i] = rng.normal(drift, daily_vol, n_obs)
            names.append(f"alpha_{i+1}")
        else:
            # Zero alpha: pure noise
            returns[:, i] = rng.normal(0.0, daily_vol, n_obs)
            names.append(f"noise_{i-n_genuine+1}")

    return returns, names


def run_demo() -> None:
    """Run the overfit detection demo."""
    print("=" * 72)
    print("Overfit Detection Demo")
    print("=" * 72)
    print()

    # Generate synthetic strategies
    n_strategies = 20
    n_genuine = 2
    n_obs = 500
    returns, names = generate_synthetic_strategies(
        n_obs=n_obs,
        n_strategies=n_strategies,
        n_genuine=n_genuine,
        seed=42,
    )

    print(f"Generated {n_strategies} strategies ({n_genuine} with genuine alpha, "
          f"{n_strategies - n_genuine} noise)")
    print(f"Each strategy has {n_obs} daily return observations")
    print()

    # ── Part 1: Compute Sharpe ratios ──────────────────────────────
    print("-" * 72)
    print("Part 1: Raw Sharpe Ratios (Annualized)")
    print("-" * 72)
    annualization = np.sqrt(365)
    sharpes = []
    for i in range(n_strategies):
        sr = float(np.mean(returns[:, i]) / np.std(returns[:, i]) * annualization)
        sharpes.append(sr)

    # Sort by SR for display
    sorted_idx = np.argsort(sharpes)[::-1]
    print(f"\n{'Rank':>4} {'Strategy':>12} {'Sharpe':>10} {'Type':>8}")
    print("-" * 40)
    for rank, idx in enumerate(sorted_idx[:10]):
        stype = "ALPHA" if idx < n_genuine else "noise"
        print(f"{rank+1:>4} {names[idx]:>12} {sharpes[idx]:>10.3f} {stype:>8}")
    print("  ...")
    print()

    best_idx = int(sorted_idx[0])
    best_sr = sharpes[best_idx]
    best_name = names[best_idx]

    print(f"Best strategy: {best_name} with SR = {best_sr:.3f}")
    print(f"Is it genuine alpha? {'Yes' if best_idx < n_genuine else 'No — it is noise!'}")
    print()

    # ── Part 2: Deflated Sharpe Ratio ──────────────────────────────
    print("-" * 72)
    print("Part 2: Deflated Sharpe Ratio")
    print("-" * 72)

    best_returns = returns[:, best_idx]
    skew = float(np.mean(((best_returns - np.mean(best_returns)) / np.std(best_returns)) ** 3))
    kurt = float(np.mean(((best_returns - np.mean(best_returns)) / np.std(best_returns)) ** 4))

    dsr_result = deflated_sharpe_ratio(
        observed_sr=best_sr,
        num_trials=n_strategies,
        backtest_length=n_obs,
        skewness=skew,
        kurtosis=kurt,
        annualization=annualization,
    )

    print(f"\n  Observed SR:           {dsr_result.observed_sr:.3f}")
    print(f"  Expected Max SR:       {dsr_result.expected_max_sr:.3f}")
    print(f"  SR Std Error:          {dsr_result.sr_std_error:.3f}")
    print(f"  Strategies tested:     {dsr_result.num_trials}")
    print(f"  Backtest length:       {dsr_result.backtest_length} obs")
    print(f"  Return skewness:       {dsr_result.skewness:.3f}")
    print(f"  Return kurtosis:       {dsr_result.kurtosis:.3f}")
    print(f"  DSR p-value:           {dsr_result.dsr_pvalue:.4f}")
    print(f"  Significant (>0.95)?   {'Yes' if dsr_result.is_significant else 'No'}")
    print()

    if not dsr_result.is_significant:
        print("  The DSR says: this Sharpe ratio is not significant after adjusting")
        print("  for the number of strategies tested. Likely overfitted.")
    else:
        print("  The DSR says: this Sharpe ratio remains significant even after")
        print("  adjusting for multiple testing.")
    print()

    # ── Part 3: Probability of Backtest Overfitting ────────────────
    print("-" * 72)
    print("Part 3: Probability of Backtest Overfitting (PBO)")
    print("-" * 72)

    pbo_result = probability_of_backtest_overfitting(
        strategy_returns=returns,
        n_groups=6,
        n_test_groups=2,
    )

    print(f"\n  CPCV paths evaluated:  {pbo_result.n_paths}")
    print(f"  Overfit paths:         {pbo_result.n_overfit_paths}")
    print(f"  PBO:                   {pbo_result.pbo:.3f}")
    print(f"  Mean OOS rank:         {pbo_result.mean_oos_rank:.3f}")
    print(f"  Is overfit (>0.50)?    {'Yes' if pbo_result.is_overfit else 'No'}")
    print()

    if pbo_result.pbo > 0.50:
        print("  PBO > 0.50: Strategy selection process is more likely than not")
        print("  to produce overfitted results.")
    elif pbo_result.pbo > 0.30:
        print("  PBO 0.30-0.50: Elevated overfitting risk. Use additional")
        print("  out-of-sample validation before deploying.")
    else:
        print("  PBO < 0.30: Low overfitting risk. Strategy selection process")
        print("  appears to have genuine predictive power.")
    print()

    # ── Part 4: Minimum Backtest Length ────────────────────────────
    print("-" * 72)
    print("Part 4: Minimum Backtest Length")
    print("-" * 72)

    for sr_target, label in [(0.05, "Low SR (daily ~0.05, ann ~0.96)"),
                              (0.10, "Med SR (daily ~0.10, ann ~1.91)"),
                              (0.20, "High SR (daily ~0.20, ann ~3.82)")]:
        result = minimum_backtest_length(
            target_sr=sr_target, confidence=0.95, skewness=skew, kurtosis=kurt
        )
        years = result.min_length / 365
        print(f"  {label}: {result.min_length} obs ({years:.1f} years)")

    print()

    # ── Part 5: Multiple Testing Correction ────────────────────────
    print("-" * 72)
    print("Part 5: Multiple Testing Correction")
    print("-" * 72)

    # Compute p-values for each strategy (one-sided test: SR > 0)
    p_values: list[float] = []
    for i in range(n_strategies):
        sr_i = np.mean(returns[:, i]) / np.std(returns[:, i])
        se_i = 1.0 / np.sqrt(n_obs)
        p = 1.0 - float(norm.cdf(sr_i / se_i))
        p_values.append(p)

    bonf = bonferroni_correction(p_values, alpha=0.05)
    holm_results = holm_correction(p_values, alpha=0.05)

    print(f"\n{'Strategy':>12} {'p-value':>10} {'Bonferroni':>12} {'Holm':>8} {'Type':>8}")
    print("-" * 56)
    for i in sorted_idx[:10]:
        stype = "ALPHA" if i < n_genuine else "noise"
        print(
            f"{names[i]:>12} {p_values[i]:>10.4f} "
            f"{'Sig' if bonf[i] else '---':>12} "
            f"{'Sig' if holm_results[i] else '---':>8} "
            f"{stype:>8}"
        )

    n_bonf_sig = sum(bonf)
    n_holm_sig = sum(holm_results)
    print(f"\n  Bonferroni significant: {n_bonf_sig}/{n_strategies}")
    print(f"  Holm significant:       {n_holm_sig}/{n_strategies}")
    print()

    # ── Summary ────────────────────────────────────────────────────
    print("=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"  Best raw Sharpe:    {best_sr:.3f} ({best_name})")
    print(f"  DSR p-value:        {dsr_result.dsr_pvalue:.4f} ({'significant' if dsr_result.is_significant else 'NOT significant'})")
    print(f"  PBO:                {pbo_result.pbo:.3f} ({'overfit' if pbo_result.is_overfit else 'acceptable'})")
    print(f"  Bonferroni pass:    {n_bonf_sig} strategies")
    print(f"  Holm pass:          {n_holm_sig} strategies")
    print()
    print("  Key takeaway: Always adjust for multiple testing. A Sharpe of")
    print(f"  {best_sr:.2f} looks great in isolation, but after testing {n_strategies} strategies,")
    print(f"  the DSR reduces it to a p-value of {dsr_result.dsr_pvalue:.3f}.")
    print()


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for overfit detection."""
    parser = argparse.ArgumentParser(
        description="Overfit detection: Deflated Sharpe Ratio and PBO."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo with synthetic backtest results.",
    )
    args = parser.parse_args()

    if not args.demo:
        print("Run with --demo to see overfit detection on synthetic strategies.")
        print("Example: python scripts/overfit_detector.py --demo")
        print()
        print("Or use the functions programmatically:")
        print("  from overfit_detector import deflated_sharpe_ratio, probability_of_backtest_overfitting")
        sys.exit(0)

    run_demo()


if __name__ == "__main__":
    main()
