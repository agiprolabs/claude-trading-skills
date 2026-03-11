#!/usr/bin/env python3
"""Scan multiple assets for mean-reverting pairs.

Tests all pairwise combinations for correlation, cointegration,
Hurst exponent of the spread, and half-life. Ranks pairs by
mean-reversion quality and shows current trading signals.

Usage:
    python scripts/pairs_scanner.py --demo

Dependencies:
    uv pip install pandas numpy scipy

Environment Variables:
    None required (demo mode uses synthetic data).
"""

import argparse
import itertools
import sys
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


# ── Configuration ───────────────────────────────────────────────────
NUM_DEMO_ASSETS: int = 5
DEMO_BARS: int = 500
SEED: int = 42


# ── Statistical Tests (self-contained) ─────────────────────────────
def adf_test(series: np.ndarray, max_lag: int = 1) -> dict:
    """Run Augmented Dickey-Fuller test for stationarity.

    Args:
        series: Price or spread series.
        max_lag: Number of augmenting lags.

    Returns:
        Dict with test_statistic, p_value_approx, and is_stationary.
    """
    y = np.diff(series)
    x_lag = series[:-1]

    start = max_lag
    y_trimmed = y[start:]
    regressors = [np.ones(len(y_trimmed)), x_lag[start:]]
    for lag in range(1, max_lag + 1):
        regressors.append(y[start - lag : len(y) - lag])
    X = np.column_stack(regressors)

    coeffs = np.linalg.lstsq(X, y_trimmed, rcond=None)[0]
    beta = coeffs[1]

    fitted = X @ coeffs
    residuals = y_trimmed - fitted
    n_obs = len(y_trimmed)
    n_params = len(coeffs)
    sigma2 = np.sum(residuals**2) / (n_obs - n_params)

    try:
        cov_matrix = sigma2 * np.linalg.inv(X.T @ X)
        se_beta = np.sqrt(cov_matrix[1, 1])
        t_stat = beta / se_beta
    except np.linalg.LinAlgError:
        return {"test_statistic": 0.0, "p_value_approx": 1.0, "is_stationary": False}

    # MacKinnon critical values (constant, no trend)
    # For cointegration residuals, use stricter values
    critical_values = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}

    if t_stat < critical_values[0.01]:
        p_approx = 0.005
    elif t_stat < critical_values[0.05]:
        p_approx = 0.03
    elif t_stat < critical_values[0.10]:
        p_approx = 0.07
    else:
        p_approx = 0.20

    return {
        "test_statistic": float(t_stat),
        "p_value_approx": float(p_approx),
        "is_stationary": p_approx < 0.05,
    }


def hurst_exponent(series: np.ndarray, min_window: int = 10) -> float:
    """Compute Hurst exponent using R/S method.

    Args:
        series: Time series data.
        min_window: Minimum window size for R/S calculation.

    Returns:
        Hurst exponent (H < 0.5 = mean-reverting).
    """
    n = len(series)
    if n < 2 * min_window:
        return 0.5

    max_window = n // 2
    window_sizes: list[int] = []
    w = min_window
    while w <= max_window:
        window_sizes.append(w)
        w = max(w + 1, int(w * 1.5))

    log_n: list[float] = []
    log_rs: list[float] = []

    for w in window_sizes:
        num_blocks = n // w
        rs_block: list[float] = []
        for i in range(num_blocks):
            block = series[i * w : (i + 1) * w]
            mean_b = np.mean(block)
            cumulative = np.cumsum(block - mean_b)
            R = float(np.max(cumulative) - np.min(cumulative))
            S = float(np.std(block, ddof=1))
            if S > 1e-10:
                rs_block.append(R / S)
        if rs_block:
            log_n.append(np.log(w))
            log_rs.append(np.log(np.mean(rs_block)))

    if len(log_n) < 2:
        return 0.5

    coeffs = np.polyfit(log_n, log_rs, 1)
    return float(coeffs[0])


def estimate_half_life(series: np.ndarray) -> float:
    """Estimate mean-reversion half-life from AR(1) regression.

    Args:
        series: Price or spread series.

    Returns:
        Half-life in periods. Negative means not mean-reverting.
    """
    y = np.diff(series)
    x = series[:-1]
    X = np.column_stack([np.ones(len(x)), x])

    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    beta = float(coeffs[1])

    if beta >= 0:
        return -1.0
    return float(-np.log(2) / np.log(1 + beta))


# ── Correlation Tests ───────────────────────────────────────────────
def compute_correlations(
    series_a: np.ndarray,
    series_b: np.ndarray,
) -> dict:
    """Compute Pearson and Spearman correlation between two series.

    Args:
        series_a: First price series.
        series_b: Second price series.

    Returns:
        Dict with pearson_r, pearson_p, spearman_r, spearman_p.
    """
    pearson_r, pearson_p = scipy_stats.pearsonr(series_a, series_b)
    spearman_r, spearman_p = scipy_stats.spearmanr(series_a, series_b)

    return {
        "pearson_r": float(pearson_r),
        "pearson_p": float(pearson_p),
        "spearman_r": float(spearman_r),
        "spearman_p": float(spearman_p),
    }


# ── Cointegration Test (Engle-Granger) ─────────────────────────────
def engle_granger_test(
    y: np.ndarray,
    x: np.ndarray,
) -> dict:
    """Test for cointegration using Engle-Granger two-step method.

    Step 1: Regress Y on X to get hedge ratio (beta).
    Step 2: Test residuals (spread) for stationarity with ADF.

    Args:
        y: Dependent price series.
        x: Independent price series.

    Returns:
        Dict with hedge_ratio, intercept, spread, adf_result,
        and is_cointegrated flag.
    """
    X = np.column_stack([np.ones(len(x)), x])
    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    intercept, hedge_ratio = float(coeffs[0]), float(coeffs[1])

    spread = y - (intercept + hedge_ratio * x)
    adf_result = adf_test(spread)

    return {
        "hedge_ratio": hedge_ratio,
        "intercept": intercept,
        "spread": spread,
        "adf_result": adf_result,
        "is_cointegrated": adf_result["is_stationary"],
    }


# ── Pair Analysis ──────────────────────────────────────────────────
def analyze_pair(
    name_a: str,
    name_b: str,
    prices_a: np.ndarray,
    prices_b: np.ndarray,
) -> Optional[dict]:
    """Run full mean-reversion analysis on a pair of assets.

    Computes correlation, cointegration, spread Hurst exponent,
    spread half-life, and current z-score of the spread.

    Args:
        name_a: Name/label of first asset.
        name_b: Name/label of second asset.
        prices_a: Price series of first asset.
        prices_b: Price series of second asset.

    Returns:
        Dict with pair analysis results, or None on error.
    """
    try:
        # Correlation
        corr = compute_correlations(prices_a, prices_b)

        # Cointegration (try both directions, pick lower p-value)
        coint_ab = engle_granger_test(prices_a, prices_b)
        coint_ba = engle_granger_test(prices_b, prices_a)

        if coint_ab["adf_result"]["p_value_approx"] <= coint_ba["adf_result"]["p_value_approx"]:
            coint = coint_ab
            dependent, independent = name_a, name_b
        else:
            coint = coint_ba
            dependent, independent = name_b, name_a

        spread = coint["spread"]

        # Hurst of spread
        H = hurst_exponent(spread)

        # Half-life of spread
        hl = estimate_half_life(spread)

        # Current z-score
        lookback = max(10, int(2 * hl)) if hl > 0 else 20
        lookback = min(lookback, len(spread) // 2)
        s = pd.Series(spread)
        rolling_mean = s.rolling(lookback).mean()
        rolling_std = s.rolling(lookback).std()
        z = (s - rolling_mean) / rolling_std
        current_z = float(z.iloc[-1]) if not np.isnan(z.iloc[-1]) else 0.0

        # Signal
        if abs(current_z) >= 2.0:
            if current_z < -2.0:
                signal = "BUY SPREAD"
            else:
                signal = "SELL SPREAD"
        elif abs(current_z) < 0.5:
            signal = "AT MEAN"
        else:
            signal = "NO SIGNAL"

        # Quality score (0-100)
        quality = 0.0
        if coint["is_cointegrated"]:
            quality += 40
        elif coint["adf_result"]["p_value_approx"] < 0.10:
            quality += 20
        if H < 0.5:
            quality += 20 * (0.5 - H) / 0.5  # More MR = more points
        if 1 < hl < 50:
            quality += 20  # Practical half-life
        if abs(corr["pearson_r"]) > 0.5:
            quality += 10
        if abs(corr["spearman_r"]) > 0.5:
            quality += 10

        return {
            "pair": f"{name_a}/{name_b}",
            "dependent": dependent,
            "independent": independent,
            "pearson_r": corr["pearson_r"],
            "spearman_r": corr["spearman_r"],
            "is_cointegrated": coint["is_cointegrated"],
            "coint_p": coint["adf_result"]["p_value_approx"],
            "coint_t": coint["adf_result"]["test_statistic"],
            "hedge_ratio": coint["hedge_ratio"],
            "hurst": H,
            "half_life": hl,
            "current_z": current_z,
            "signal": signal,
            "quality_score": quality,
            "lookback": lookback,
        }

    except Exception as e:
        print(f"  Warning: Error analyzing {name_a}/{name_b}: {e}")
        return None


# ── Demo Data Generation ───────────────────────────────────────────
def generate_demo_assets(
    n_assets: int = 5,
    n_bars: int = 500,
    seed: int = 42,
) -> dict[str, np.ndarray]:
    """Generate synthetic asset prices with known cointegration structure.

    Creates:
    - Asset A, B: cointegrated pair (strong mean-reverting spread)
    - Asset C: partially correlated with A (weaker cointegration)
    - Asset D: trending (random walk with drift)
    - Asset E: independent random walk

    Args:
        n_assets: Number of assets (uses first 5 names).
        n_bars: Number of data points per asset.
        seed: Random seed for reproducibility.

    Returns:
        Dict mapping asset name to price array.
    """
    rng = np.random.default_rng(seed)
    names = ["SOL", "ETH", "BTC", "BONK", "JUP"][:n_assets]
    assets: dict[str, np.ndarray] = {}

    # Common factor (market)
    market = np.cumsum(rng.normal(0.001, 0.02, n_bars))

    # Asset A (SOL): market + own noise
    sol_noise = np.cumsum(rng.normal(0, 0.01, n_bars))
    assets["SOL"] = 100 * np.exp(0.5 * market + 0.5 * sol_noise)

    # Asset B (ETH): cointegrated with SOL (similar market exposure + mean-reverting spread)
    spread_noise = np.zeros(n_bars)
    spread_noise[0] = rng.normal(0, 0.01)
    for i in range(1, n_bars):
        spread_noise[i] = 0.9 * spread_noise[i - 1] + rng.normal(0, 0.01)
    assets["ETH"] = 2000 * np.exp(0.5 * market + 0.5 * sol_noise + spread_noise)

    # Asset C (BTC): partially correlated with market
    btc_noise = np.cumsum(rng.normal(0, 0.015, n_bars))
    assets["BTC"] = 50000 * np.exp(0.3 * market + 0.7 * btc_noise)

    # Asset D (BONK): trending / momentum
    drift = np.cumsum(rng.normal(0.002, 0.03, n_bars))
    assets["BONK"] = 0.00001 * np.exp(drift)

    # Asset E (JUP): independent random walk
    jup_walk = np.cumsum(rng.normal(0, 0.02, n_bars))
    assets["JUP"] = 1.0 * np.exp(jup_walk)

    return assets


# ── Report Printing ────────────────────────────────────────────────
def print_pairs_report(
    results: list[dict],
    top_n: int = 3,
) -> None:
    """Print formatted pairs scanning report.

    Args:
        results: List of pair analysis results from analyze_pair().
        top_n: Number of top pairs to show in detail.
    """
    # Sort by quality score descending
    results.sort(key=lambda x: x["quality_score"], reverse=True)

    print("=" * 80)
    print("  PAIRS SCANNER — MEAN-REVERSION RANKING")
    print("=" * 80)

    # Summary table
    print(f"\n{'Rank':<5} {'Pair':<12} {'Quality':<9} {'Coint?':<8} "
          f"{'Hurst':<7} {'Half-Life':<11} {'Z-Score':<9} {'Signal'}")
    print("-" * 80)

    for i, r in enumerate(results, 1):
        coint_flag = "YES" if r["is_cointegrated"] else "no"
        hl_str = f"{r['half_life']:.1f}" if r["half_life"] > 0 else "N/A"
        print(f"{i:<5} {r['pair']:<12} {r['quality_score']:<9.1f} {coint_flag:<8} "
              f"{r['hurst']:<7.3f} {hl_str:<11} {r['current_z']:+.3f}   {r['signal']}")

    # Detailed view of top pairs
    print(f"\n{'=' * 80}")
    print(f"  TOP {top_n} PAIRS — DETAILED ANALYSIS")
    print(f"{'=' * 80}")

    for i, r in enumerate(results[:top_n], 1):
        print(f"\n--- #{i}: {r['pair']} (Quality: {r['quality_score']:.1f}/100) ---")
        print(f"  Correlation:")
        print(f"    Pearson:  {r['pearson_r']:+.4f}")
        print(f"    Spearman: {r['spearman_r']:+.4f}")
        print(f"  Cointegration (Engle-Granger):")
        print(f"    Direction: {r['dependent']} = f({r['independent']})")
        print(f"    Hedge ratio: {r['hedge_ratio']:.6f}")
        print(f"    ADF t-stat: {r['coint_t']:.4f}")
        print(f"    ADF p-value: {r['coint_p']:.4f}")
        print(f"    Cointegrated: {'YES' if r['is_cointegrated'] else 'NO'}")
        print(f"  Spread Properties:")
        print(f"    Hurst exponent: {r['hurst']:.4f} "
              f"({'mean-reverting' if r['hurst'] < 0.5 else 'trending'})")
        hl_str = f"{r['half_life']:.1f} bars" if r["half_life"] > 0 else "N/A"
        print(f"    Half-life: {hl_str}")
        print(f"    Lookback window: {r['lookback']} bars")
        print(f"  Current Status:")
        print(f"    Z-score: {r['current_z']:+.4f}")
        print(f"    Signal: {r['signal']}")

        if r["half_life"] > 0 and r["is_cointegrated"]:
            print(f"  Suggested Parameters:")
            print(f"    Lookback: {r['lookback']} bars")
            print(f"    Entry z: +/-2.0")
            print(f"    Exit z: 0.0")
            print(f"    Max hold: {int(3 * r['half_life'])} bars")

    # Overall summary
    cointegrated_count = sum(1 for r in results if r["is_cointegrated"])
    mr_count = sum(1 for r in results if r["hurst"] < 0.5)

    print(f"\n{'=' * 80}")
    print("  SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total pairs scanned: {len(results)}")
    print(f"  Cointegrated pairs: {cointegrated_count}")
    print(f"  Mean-reverting spreads (H < 0.5): {mr_count}")
    if results:
        best = results[0]
        print(f"  Best pair: {best['pair']} (quality {best['quality_score']:.1f}/100)")

    print("\n  Note: This analysis is for informational purposes only.")
    print("  It does not constitute financial advice or a trading recommendation.")
    print(f"{'=' * 80}")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point: parse arguments and run pairs scanner."""
    parser = argparse.ArgumentParser(
        description="Scan multiple assets for mean-reverting pairs."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use synthetic data with known cointegration structure.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Number of top pairs to show in detail (default: 3).",
    )
    args = parser.parse_args()

    if not args.demo:
        print("Currently only --demo mode is supported.")
        print("Usage: python scripts/pairs_scanner.py --demo")
        print("\nTo extend with live data, integrate with Birdeye or DexScreener API.")
        sys.exit(1)

    print("Running in DEMO mode with synthetic data.")
    print(f"Generating {NUM_DEMO_ASSETS} assets with known cointegration structure.\n")
    print("  SOL, ETH: Cointegrated pair (shared market factor + MR spread)")
    print("  BTC: Partially correlated with SOL")
    print("  BONK: Trending (momentum, not mean-reverting)")
    print("  JUP: Independent random walk\n")

    assets = generate_demo_assets(
        n_assets=NUM_DEMO_ASSETS,
        n_bars=DEMO_BARS,
        seed=SEED,
    )

    # Test all pairs
    names = list(assets.keys())
    pairs = list(itertools.combinations(names, 2))
    print(f"Testing {len(pairs)} pairs...\n")

    results: list[dict] = []
    for name_a, name_b in pairs:
        result = analyze_pair(name_a, name_b, assets[name_a], assets[name_b])
        if result is not None:
            results.append(result)
            print(f"  {name_a}/{name_b}: quality={result['quality_score']:.1f}, "
                  f"H={result['hurst']:.3f}, "
                  f"coint={'Y' if result['is_cointegrated'] else 'N'}")

    print()
    print_pairs_report(results, top_n=args.top)


if __name__ == "__main__":
    main()
