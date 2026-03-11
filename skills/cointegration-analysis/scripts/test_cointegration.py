#!/usr/bin/env python3
"""Cointegration testing pipeline for pairs trading analysis.

Runs Engle-Granger cointegration tests on two price series, estimates hedge
ratios, computes spread statistics (ADF, Hurst exponent, half-life), and
performs rolling stability analysis.

Usage:
    python scripts/test_cointegration.py              # Demo with synthetic data
    python scripts/test_cointegration.py --demo        # Same as above

Dependencies:
    uv pip install pandas numpy scipy

Environment Variables:
    None required — runs entirely on synthetic or provided data.
"""

import argparse
import sys
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


# ── Configuration ───────────────────────────────────────────────────
DEFAULT_ADF_MAX_LAG: int = 20
ROLLING_WINDOW: int = 60
HURST_MAX_LAG: int = 20
ENTRY_ZSCORE: float = 2.0


# ── ADF Test (Manual Implementation) ───────────────────────────────
def adf_test(
    series: np.ndarray,
    max_lag: int = DEFAULT_ADF_MAX_LAG,
) -> dict:
    """Run Augmented Dickey-Fuller test for unit root.

    Uses AIC to select optimal lag length, then tests for unit root
    via the t-statistic on the lagged level coefficient.

    Args:
        series: 1-D array of the time series to test.
        max_lag: Maximum number of lags to consider.

    Returns:
        Dictionary with keys: adf_stat, p_value_approx, used_lags,
        nobs, critical_values.
    """
    series = np.asarray(series, dtype=float)
    n = len(series)
    if n < 20:
        raise ValueError("Series too short for ADF test (need >= 20 observations)")

    max_lag = min(max_lag, n // 3 - 1)
    best_aic = np.inf
    best_result: Optional[dict] = None

    for lag in range(0, max_lag + 1):
        y = np.diff(series)
        y_lag = series[:-1]

        # Build regressor matrix: [y_{t-1}, Δy_{t-1}, ..., Δy_{t-lag}, const]
        start = lag
        y_trimmed = y[start:]
        nobs = len(y_trimmed)
        if nobs < 10:
            continue

        X_cols = [y_lag[start:start + nobs]]
        for j in range(1, lag + 1):
            X_cols.append(y[start - j:start - j + nobs])
        X_cols.append(np.ones(nobs))
        X = np.column_stack(X_cols)

        try:
            coeffs, residuals, rank, _ = np.linalg.lstsq(X, y_trimmed, rcond=None)
        except np.linalg.LinAlgError:
            continue

        if len(residuals) == 0:
            sse = np.sum((y_trimmed - X @ coeffs) ** 2)
        else:
            sse = residuals[0]

        k = X.shape[1]
        aic = nobs * np.log(sse / nobs + 1e-15) + 2 * k

        if aic < best_aic:
            best_aic = aic
            gamma = coeffs[0]
            resid = y_trimmed - X @ coeffs
            sigma2 = np.sum(resid ** 2) / (nobs - k)
            XtX_inv = np.linalg.pinv(X.T @ X)
            se_gamma = np.sqrt(sigma2 * XtX_inv[0, 0])
            adf_stat = gamma / se_gamma if se_gamma > 1e-15 else -999.0

            best_result = {
                "adf_stat": adf_stat,
                "used_lags": lag,
                "nobs": nobs,
            }

    if best_result is None:
        raise ValueError("ADF test failed — could not fit any lag specification")

    # Approximate p-value using MacKinnon-style interpolation (simplified)
    stat = best_result["adf_stat"]
    best_result["p_value_approx"] = _adf_pvalue_approx(stat, n)
    best_result["critical_values"] = {"1%": -3.43, "5%": -2.86, "10%": -2.57}
    return best_result


def _adf_pvalue_approx(stat: float, nobs: int) -> float:
    """Approximate ADF p-value using interpolation of critical values.

    This is a simplified approximation. For production use, prefer
    statsmodels.tsa.stattools.adfuller which uses MacKinnon tables.

    Args:
        stat: ADF test statistic.
        nobs: Number of observations.

    Returns:
        Approximate p-value between 0 and 1.
    """
    # Approximate critical values for constant, no trend
    breakpoints = [
        (-3.43, 0.01),
        (-2.86, 0.05),
        (-2.57, 0.10),
        (-1.94, 0.30),
        (-1.62, 0.50),
        (-0.50, 0.90),
        (0.00, 0.95),
        (1.00, 0.99),
    ]
    if stat <= breakpoints[0][0]:
        return breakpoints[0][1]
    if stat >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for i in range(len(breakpoints) - 1):
        s0, p0 = breakpoints[i]
        s1, p1 = breakpoints[i + 1]
        if s0 <= stat <= s1:
            frac = (stat - s0) / (s1 - s0)
            return p0 + frac * (p1 - p0)
    return 0.99


# ── Cointegration Test ──────────────────────────────────────────────
def engle_granger_test(
    y: np.ndarray,
    x: np.ndarray,
) -> dict:
    """Run Engle-Granger cointegration test (both directions).

    Step 1: OLS regression Y = α + β*X + ε
    Step 2: ADF test on residuals ε

    Tests both Y~X and X~Y, returns the stronger result.

    Args:
        y: Price series of asset Y.
        x: Price series of asset X.

    Returns:
        Dictionary with cointegration test results including hedge ratio,
        p-values for both directions, and overall assessment.

    Raises:
        ValueError: If series have different lengths or are too short.
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    if len(y) != len(x):
        raise ValueError(f"Series must have equal length: {len(y)} != {len(x)}")
    if len(y) < 30:
        raise ValueError("Need at least 30 observations for cointegration test")

    results: dict = {}

    # Direction 1: Y ~ X
    slope_yx, intercept_yx, r_yx, _, stderr_yx = stats.linregress(x, y)
    resid_yx = y - slope_yx * x - intercept_yx
    adf_yx = adf_test(resid_yx)

    # Direction 2: X ~ Y
    slope_xy, intercept_xy, r_xy, _, stderr_xy = stats.linregress(y, x)
    resid_xy = x - slope_xy * y - intercept_xy
    adf_xy = adf_test(resid_xy)

    # Use Engle-Granger critical values (stricter than standard ADF)
    eg_critical = {"1%": -3.90, "5%": -3.34, "10%": -3.04}

    # Pick the direction with stronger rejection (lower p-value / more negative stat)
    if adf_yx["adf_stat"] < adf_xy["adf_stat"]:
        primary_direction = "Y ~ X"
        hedge_ratio = slope_yx
        intercept = intercept_yx
        hedge_stderr = stderr_yx
        residuals = resid_yx
        primary_adf = adf_yx
    else:
        primary_direction = "X ~ Y"
        hedge_ratio = 1.0 / slope_xy if abs(slope_xy) > 1e-10 else float("inf")
        intercept = -intercept_xy / slope_xy if abs(slope_xy) > 1e-10 else 0.0
        hedge_stderr = stderr_xy
        residuals = resid_yx  # Still use Y - β*X spread for trading
        primary_adf = adf_xy

    # Determine cointegration at Engle-Granger critical values
    adf_stat = min(adf_yx["adf_stat"], adf_xy["adf_stat"])
    eg_cointegrated_5pct = adf_stat < eg_critical["5%"]
    eg_cointegrated_10pct = adf_stat < eg_critical["10%"]

    results["direction_yx"] = {
        "hedge_ratio": slope_yx,
        "intercept": intercept_yx,
        "r_squared": r_yx ** 2,
        "adf_stat": adf_yx["adf_stat"],
        "adf_pvalue": adf_yx["p_value_approx"],
    }
    results["direction_xy"] = {
        "hedge_ratio": slope_xy,
        "intercept": intercept_xy,
        "r_squared": r_xy ** 2,
        "adf_stat": adf_xy["adf_stat"],
        "adf_pvalue": adf_xy["p_value_approx"],
    }
    results["primary_direction"] = primary_direction
    results["hedge_ratio"] = slope_yx  # Always use Y~X for spread construction
    results["intercept"] = intercept_yx
    results["hedge_ratio_stderr"] = stderr_yx
    results["residuals"] = resid_yx
    results["eg_critical_values"] = eg_critical
    results["best_adf_stat"] = adf_stat
    results["cointegrated_5pct"] = eg_cointegrated_5pct
    results["cointegrated_10pct"] = eg_cointegrated_10pct
    results["correlation"] = float(np.corrcoef(x, y)[0, 1])

    return results


# ── Spread Statistics ───────────────────────────────────────────────
def hurst_exponent(series: np.ndarray, max_lag: int = HURST_MAX_LAG) -> float:
    """Estimate Hurst exponent using variance of lagged differences.

    H < 0.5: Mean-reverting
    H = 0.5: Random walk
    H > 0.5: Trending

    Args:
        series: 1-D price or spread series.
        max_lag: Maximum lag for estimation.

    Returns:
        Estimated Hurst exponent.
    """
    series = np.asarray(series, dtype=float)
    lags = range(2, min(max_lag + 1, len(series) // 2))
    if len(list(lags)) < 3:
        return 0.5  # Insufficient data

    tau = []
    for lag in lags:
        diffs = series[lag:] - series[:-lag]
        std = np.std(diffs)
        if std > 0:
            tau.append(std)
        else:
            tau.append(1e-10)

    valid_lags = list(lags)[: len(tau)]
    log_lags = np.log(valid_lags)
    log_tau = np.log(tau)
    slope, _, _, _, _ = stats.linregress(log_lags, log_tau)
    return float(slope)


def half_life_of_mean_reversion(spread: np.ndarray) -> float:
    """Estimate half-life of mean reversion from AR(1) model.

    Fits: Δspread_t = φ * spread_{t-1} + ε_t
    Half-life = -ln(2) / ln(1 + φ)

    Args:
        spread: Stationary spread series.

    Returns:
        Half-life in number of periods. Returns inf if not mean-reverting.
    """
    spread = np.asarray(spread, dtype=float)
    spread_lag = spread[:-1]
    spread_diff = np.diff(spread)
    slope, _, _, _, _ = stats.linregress(spread_lag, spread_diff)
    if slope >= 0:
        return float("inf")
    phi = 1 + slope
    if phi <= 0 or phi >= 1:
        return float("inf")
    return float(-np.log(2) / np.log(phi))


def spread_statistics(spread: np.ndarray) -> dict:
    """Compute comprehensive spread statistics.

    Args:
        spread: Spread series (Y - β*X - α).

    Returns:
        Dictionary with mean, std, skew, kurtosis, ADF, Hurst, half-life.
    """
    spread = np.asarray(spread, dtype=float)
    z_score = (spread - np.mean(spread)) / np.std(spread)

    adf_result = adf_test(spread)
    hurst = hurst_exponent(spread)
    hl = half_life_of_mean_reversion(spread)

    return {
        "mean": float(np.mean(spread)),
        "std": float(np.std(spread)),
        "skewness": float(stats.skew(spread)),
        "kurtosis": float(stats.kurtosis(spread)),
        "current_value": float(spread[-1]),
        "current_zscore": float(z_score[-1]),
        "min": float(np.min(spread)),
        "max": float(np.max(spread)),
        "adf_stat": adf_result["adf_stat"],
        "adf_pvalue": adf_result["p_value_approx"],
        "hurst_exponent": hurst,
        "half_life": hl,
        "is_mean_reverting": hurst < 0.5 and adf_result["p_value_approx"] < 0.05,
    }


# ── Rolling Cointegration ──────────────────────────────────────────
def rolling_cointegration(
    y: np.ndarray,
    x: np.ndarray,
    window: int = ROLLING_WINDOW,
) -> dict:
    """Test cointegration stability over rolling windows.

    Args:
        y: Price series Y.
        x: Price series X.
        window: Rolling window size in observations.

    Returns:
        Dictionary with arrays of rolling p-values, hedge ratios,
        and stability assessment.
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = len(y)

    if n < window + 10:
        raise ValueError(
            f"Need at least {window + 10} observations for rolling test "
            f"with window={window}, got {n}"
        )

    rolling_pvalues: list[float] = []
    rolling_hedges: list[float] = []
    rolling_adf_stats: list[float] = []

    for i in range(window, n):
        y_win = y[i - window : i]
        x_win = x[i - window : i]

        slope, intercept, _, _, _ = stats.linregress(x_win, y_win)
        resid = y_win - slope * x_win - intercept

        try:
            adf_result = adf_test(resid)
            rolling_pvalues.append(adf_result["p_value_approx"])
            rolling_adf_stats.append(adf_result["adf_stat"])
        except ValueError:
            rolling_pvalues.append(1.0)
            rolling_adf_stats.append(0.0)

        rolling_hedges.append(slope)

    pvals = np.array(rolling_pvalues)
    hedges = np.array(rolling_hedges)

    pct_significant = float(np.mean(pvals < 0.05)) * 100
    hedge_drift = float(
        (np.max(hedges) - np.min(hedges)) / np.mean(np.abs(hedges)) * 100
    ) if np.mean(np.abs(hedges)) > 1e-10 else 0.0

    # Stability assessment
    if pct_significant > 80 and hedge_drift < 25:
        stability = "STABLE"
    elif pct_significant > 50 and hedge_drift < 50:
        stability = "MODERATE"
    else:
        stability = "UNSTABLE"

    return {
        "rolling_pvalues": pvals,
        "rolling_hedge_ratios": hedges,
        "rolling_adf_stats": np.array(rolling_adf_stats),
        "pct_windows_significant": pct_significant,
        "hedge_ratio_mean": float(np.mean(hedges)),
        "hedge_ratio_std": float(np.std(hedges)),
        "hedge_ratio_drift_pct": hedge_drift,
        "stability": stability,
    }


# ── Synthetic Data Generation ──────────────────────────────────────
def generate_cointegrated_pair(
    n: int = 300,
    hedge_ratio: float = 1.5,
    intercept: float = 10.0,
    spread_vol: float = 1.0,
    mean_reversion_speed: float = 0.05,
    drift: float = 0.01,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic cointegrated pair.

    Creates two price series X and Y where Y = α + β*X + ε, with ε
    following an Ornstein-Uhlenbeck (mean-reverting) process.

    Args:
        n: Number of observations.
        hedge_ratio: True hedge ratio β.
        intercept: True intercept α.
        spread_vol: Volatility of the spread process.
        mean_reversion_speed: Speed of mean reversion (0 to 1).
        drift: Common stochastic trend drift.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (y_prices, x_prices).
    """
    rng = np.random.default_rng(seed)

    # Generate common stochastic trend (random walk)
    x_innovations = drift + rng.normal(0, 1, n)
    x_prices = 100.0 + np.cumsum(x_innovations)

    # Generate mean-reverting spread (Ornstein-Uhlenbeck)
    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = (
            spread[t - 1]
            - mean_reversion_speed * spread[t - 1]
            + spread_vol * rng.normal()
        )

    # Construct Y = α + β*X + spread
    y_prices = intercept + hedge_ratio * x_prices + spread

    return y_prices, x_prices


# ── Report Printing ─────────────────────────────────────────────────
def print_report(
    coint_result: dict,
    spread_stats: dict,
    rolling_result: dict,
    y_name: str = "Y",
    x_name: str = "X",
) -> None:
    """Print a comprehensive cointegration analysis report.

    Args:
        coint_result: Output of engle_granger_test().
        spread_stats: Output of spread_statistics().
        rolling_result: Output of rolling_cointegration().
        y_name: Display name for Y series.
        x_name: Display name for X series.
    """
    sep = "=" * 60
    sub = "-" * 60

    print(f"\n{sep}")
    print("  COINTEGRATION ANALYSIS REPORT")
    print(sep)

    # Cointegration test
    print(f"\n{'COINTEGRATION TEST':^60}")
    print(sub)
    print(f"  Pair: {y_name} vs {x_name}")
    print(f"  Observations: {len(coint_result['residuals'])}")
    print(f"  Correlation: {coint_result['correlation']:.4f}")
    print()
    print(f"  Direction Y~X:")
    d = coint_result["direction_yx"]
    print(f"    ADF stat: {d['adf_stat']:.4f}  (p ≈ {d['adf_pvalue']:.4f})")
    print(f"    Hedge ratio: {d['hedge_ratio']:.4f}")
    print(f"    R²: {d['r_squared']:.4f}")
    print()
    print(f"  Direction X~Y:")
    d = coint_result["direction_xy"]
    print(f"    ADF stat: {d['adf_stat']:.4f}  (p ≈ {d['adf_pvalue']:.4f})")
    print(f"    Hedge ratio: {d['hedge_ratio']:.4f}")
    print(f"    R²: {d['r_squared']:.4f}")
    print()
    print(f"  Best ADF stat: {coint_result['best_adf_stat']:.4f}")
    print(f"  Engle-Granger critical values: {coint_result['eg_critical_values']}")

    coint_status = "YES" if coint_result["cointegrated_5pct"] else "NO"
    coint_marker = "✓" if coint_result["cointegrated_5pct"] else "✗"
    print(f"\n  >>> COINTEGRATED (5%): {coint_status} {coint_marker}")
    if not coint_result["cointegrated_5pct"] and coint_result["cointegrated_10pct"]:
        print("      (Significant at 10% level)")

    # Hedge ratio
    print(f"\n{'HEDGE RATIO':^60}")
    print(sub)
    hr = coint_result["hedge_ratio"]
    se = coint_result["hedge_ratio_stderr"]
    print(f"  Hedge ratio (β): {hr:.4f}")
    print(f"  Standard error: {se:.4f}")
    print(f"  95% CI: [{hr - 1.96 * se:.4f}, {hr + 1.96 * se:.4f}]")
    print(f"  Intercept (α): {coint_result['intercept']:.4f}")
    print(f"  Spread: {y_name} - {hr:.4f} * {x_name} - {coint_result['intercept']:.4f}")

    # Spread statistics
    print(f"\n{'SPREAD STATISTICS':^60}")
    print(sub)
    print(f"  Mean: {spread_stats['mean']:.4f}")
    print(f"  Std: {spread_stats['std']:.4f}")
    print(f"  Skewness: {spread_stats['skewness']:.4f}")
    print(f"  Kurtosis: {spread_stats['kurtosis']:.4f}")
    print(f"  Range: [{spread_stats['min']:.4f}, {spread_stats['max']:.4f}]")
    print(f"  Current value: {spread_stats['current_value']:.4f}")
    print(f"  Current z-score: {spread_stats['current_zscore']:.4f}")

    # Mean reversion tests
    print(f"\n{'MEAN REVERSION TESTS':^60}")
    print(sub)
    print(f"  ADF stat: {spread_stats['adf_stat']:.4f}  (p ≈ {spread_stats['adf_pvalue']:.4f})")
    print(f"  Hurst exponent: {spread_stats['hurst_exponent']:.4f}  ", end="")
    if spread_stats["hurst_exponent"] < 0.4:
        print("(strong mean reversion)")
    elif spread_stats["hurst_exponent"] < 0.5:
        print("(mild mean reversion)")
    elif spread_stats["hurst_exponent"] < 0.6:
        print("(near random walk)")
    else:
        print("(trending)")
    hl = spread_stats["half_life"]
    hl_str = f"{hl:.1f} periods" if hl < 1000 else "∞"
    print(f"  Half-life: {hl_str}")

    mr = "YES" if spread_stats["is_mean_reverting"] else "NO"
    mr_marker = "✓" if spread_stats["is_mean_reverting"] else "✗"
    print(f"\n  >>> MEAN-REVERTING: {mr} {mr_marker}")

    # Trading signal
    print(f"\n{'CURRENT SIGNAL':^60}")
    print(sub)
    z = spread_stats["current_zscore"]
    if z < -ENTRY_ZSCORE:
        signal = f"LONG SPREAD (z = {z:.2f} < -{ENTRY_ZSCORE})"
        action = f"Buy {y_name}, Sell {x_name}"
    elif z > ENTRY_ZSCORE:
        signal = f"SHORT SPREAD (z = {z:.2f} > +{ENTRY_ZSCORE})"
        action = f"Sell {y_name}, Buy {x_name}"
    else:
        signal = f"NO SIGNAL (z = {z:.2f}, threshold = ±{ENTRY_ZSCORE})"
        action = "No action"
    print(f"  Signal: {signal}")
    print(f"  Action: {action}")

    # Rolling stability
    print(f"\n{'ROLLING STABILITY (window={ROLLING_WINDOW})':^60}")
    print(sub)
    print(f"  Windows tested: {len(rolling_result['rolling_pvalues'])}")
    print(f"  % windows significant (p<0.05): {rolling_result['pct_windows_significant']:.1f}%")
    print(f"  Hedge ratio mean: {rolling_result['hedge_ratio_mean']:.4f}")
    print(f"  Hedge ratio std: {rolling_result['hedge_ratio_std']:.4f}")
    print(f"  Hedge ratio drift: {rolling_result['hedge_ratio_drift_pct']:.1f}%")
    print(f"\n  >>> STABILITY: {rolling_result['stability']}")

    # Overall assessment
    print(f"\n{'OVERALL ASSESSMENT':^60}")
    print(sub)
    checks = {
        "Cointegrated (EG 5%)": coint_result["cointegrated_5pct"],
        "Spread is mean-reverting": spread_stats["is_mean_reverting"],
        "Half-life 5-60 days": 5 <= spread_stats["half_life"] <= 60,
        "Rolling stability": rolling_result["stability"] in ("STABLE", "MODERATE"),
        "Hurst < 0.5": spread_stats["hurst_exponent"] < 0.5,
    }
    passed = sum(checks.values())
    total = len(checks)
    for check, ok in checks.items():
        marker = "✓" if ok else "✗"
        print(f"  [{marker}] {check}")

    print(f"\n  Score: {passed}/{total}")
    if passed == total:
        print("  VERDICT: Strong cointegration — viable pairs trade candidate")
    elif passed >= 3:
        print("  VERDICT: Moderate evidence — proceed with caution")
    else:
        print("  VERDICT: Weak/no cointegration — not recommended for pairs trading")

    print(f"\n{sep}")
    print("  This analysis is for informational purposes only.")
    print("  It does not constitute financial advice.")
    print(sep)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run cointegration analysis pipeline."""
    parser = argparse.ArgumentParser(
        description="Cointegration testing for pairs trading analysis"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Run demo with synthetic cointegrated pair (default: True)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=300,
        help="Number of synthetic data points (default: 300)",
    )
    parser.add_argument(
        "--hedge-ratio",
        type=float,
        default=1.5,
        help="True hedge ratio for synthetic data (default: 1.5)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=ROLLING_WINDOW,
        help=f"Rolling window size (default: {ROLLING_WINDOW})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    args = parser.parse_args()

    print("Generating synthetic cointegrated pair...")
    print(f"  N={args.n}, true β={args.hedge_ratio}, seed={args.seed}")

    y, x = generate_cointegrated_pair(
        n=args.n,
        hedge_ratio=args.hedge_ratio,
        seed=args.seed,
    )

    print("Running Engle-Granger cointegration test...")
    coint_result = engle_granger_test(y, x)

    print("Computing spread statistics...")
    spread = coint_result["residuals"]
    spread_stats = spread_statistics(spread)

    print("Running rolling cointegration analysis...")
    rolling_result = rolling_cointegration(y, x, window=args.window)

    print_report(
        coint_result,
        spread_stats,
        rolling_result,
        y_name="Asset_Y",
        x_name="Asset_X",
    )


if __name__ == "__main__":
    main()
