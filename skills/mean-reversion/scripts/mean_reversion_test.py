#!/usr/bin/env python3
"""Comprehensive mean-reversion analysis for a single asset.

Runs ADF test, Hurst exponent, variance ratio, half-life estimation,
Ornstein-Uhlenbeck parameter estimation, and z-score signal generation.

Usage:
    python scripts/mean_reversion_test.py --demo
    python scripts/mean_reversion_test.py

Dependencies:
    uv pip install pandas numpy scipy httpx

Environment Variables:
    BIRDEYE_API_KEY: Your Birdeye API key (optional; required for live data)
    TOKEN_MINT: Solana token mint address (optional; defaults to SOL)
"""

import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


# ── Configuration ───────────────────────────────────────────────────
BIRDEYE_API_KEY: str = os.getenv("BIRDEYE_API_KEY", "")
TOKEN_MINT: str = os.getenv(
    "TOKEN_MINT", "So11111111111111111111111111111111111111112"
)
DEFAULT_LOOKBACK_BARS: int = 200


# ── ADF Test ────────────────────────────────────────────────────────
def adf_test(series: np.ndarray, max_lag: int = 1) -> dict:
    """Run Augmented Dickey-Fuller test for stationarity.

    Tests the null hypothesis that the series has a unit root (non-stationary).
    Rejecting the null (p < 0.05) indicates stationarity, a prerequisite for
    mean reversion.

    Args:
        series: Price or spread series (levels, not returns).
        max_lag: Number of augmenting lags in the ADF regression.

    Returns:
        Dict with test_statistic, p_value_approx, beta, critical_values,
        and conclusion string.
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
    sigma2 = np.sum(residuals**2) / (len(y_trimmed) - len(coeffs))
    cov_matrix = sigma2 * np.linalg.inv(X.T @ X)
    se_beta = np.sqrt(cov_matrix[1, 1])
    t_stat = beta / se_beta

    # MacKinnon approximate critical values (constant, no trend, n > 250)
    critical_values = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}

    if t_stat < critical_values[0.01]:
        p_approx = 0.005
        conclusion = "Strongly stationary (p < 0.01) -- mean-reverting"
    elif t_stat < critical_values[0.05]:
        p_approx = 0.03
        conclusion = "Stationary (p < 0.05) -- likely mean-reverting"
    elif t_stat < critical_values[0.10]:
        p_approx = 0.07
        conclusion = "Weakly stationary (p < 0.10) -- possibly mean-reverting"
    else:
        p_approx = 0.20
        conclusion = "Non-stationary (p > 0.10) -- NOT mean-reverting"

    return {
        "test_statistic": float(t_stat),
        "p_value_approx": float(p_approx),
        "beta": float(beta),
        "critical_values": critical_values,
        "conclusion": conclusion,
    }


# ── Hurst Exponent ──────────────────────────────────────────────────
def hurst_exponent(series: np.ndarray, min_window: int = 10) -> float:
    """Compute Hurst exponent using the rescaled range (R/S) method.

    H < 0.5: mean-reverting, H = 0.5: random walk, H > 0.5: trending.

    Args:
        series: Price or log-price series.
        min_window: Minimum subseries length for R/S calculation.

    Returns:
        Hurst exponent estimate (float between 0 and 1).

    Raises:
        ValueError: If series is too short for reliable estimation.
    """
    n = len(series)
    if n < 2 * min_window:
        raise ValueError(f"Series too short ({n}). Need >= {2 * min_window} points.")

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
            mean_block = np.mean(block)
            deviations = block - mean_block
            cumulative = np.cumsum(deviations)
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


# ── Variance Ratio ──────────────────────────────────────────────────
def variance_ratio(series: np.ndarray, q: int = 5) -> dict:
    """Compute variance ratio at horizon q.

    VR < 1: mean-reverting, VR = 1: random walk, VR > 1: trending.

    Args:
        series: Price series (levels).
        q: Multi-period return horizon.

    Returns:
        Dict with vr, z_stat, p_value, and conclusion.
    """
    log_prices = np.log(series)
    returns_1 = np.diff(log_prices)
    n = len(returns_1)

    var_1 = np.var(returns_1, ddof=1)
    if var_1 < 1e-15:
        return {"vr": 1.0, "z_stat": 0.0, "p_value": 1.0, "conclusion": "Zero variance"}

    returns_q = log_prices[q:] - log_prices[:-q]
    var_q = np.var(returns_q, ddof=1)

    vr = var_q / (q * var_1)

    # Lo-MacKinlay z-statistic (homoskedastic)
    z_stat = (vr - 1) / np.sqrt(2 * (q - 1) / (3 * n))
    p_value = float(2 * (1 - scipy_stats.norm.cdf(abs(z_stat))))

    if vr < 1 and p_value < 0.05:
        conclusion = f"Mean-reverting at horizon {q} (VR={vr:.3f}, p={p_value:.4f})"
    elif vr > 1 and p_value < 0.05:
        conclusion = f"Trending at horizon {q} (VR={vr:.3f}, p={p_value:.4f})"
    else:
        conclusion = f"Random walk at horizon {q} (VR={vr:.3f}, p={p_value:.4f})"

    return {
        "vr": float(vr),
        "z_stat": float(z_stat),
        "p_value": p_value,
        "conclusion": conclusion,
    }


# ── Half-Life Estimation ───────────────────────────────────────────
def estimate_half_life(series: np.ndarray) -> dict:
    """Estimate mean-reversion half-life from AR(1) regression.

    Fits: delta_X_t = alpha + beta * X_{t-1} + epsilon
    Half-life = -ln(2) / ln(1 + beta) when beta < 0.

    Args:
        series: Price or spread series.

    Returns:
        Dict with half_life, beta, alpha, mu, r_squared, and conclusion.
    """
    y = np.diff(series)
    x = series[:-1]
    X = np.column_stack([np.ones(len(x)), x])

    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha, beta = float(coeffs[0]), float(coeffs[1])

    y_hat = X @ coeffs
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    if beta >= 0:
        return {
            "half_life": -1.0,
            "beta": beta,
            "alpha": alpha,
            "mu": float(np.mean(series)),
            "r_squared": r_squared,
            "conclusion": "Not mean-reverting (beta >= 0)",
        }

    hl = -np.log(2) / np.log(1 + beta)
    mu = -alpha / beta

    return {
        "half_life": float(hl),
        "beta": beta,
        "alpha": alpha,
        "mu": float(mu),
        "r_squared": r_squared,
        "conclusion": f"Mean-reverting with half-life of {hl:.1f} periods",
    }


# ── Ornstein-Uhlenbeck Parameter Estimation ────────────────────────
def estimate_ou_params(series: np.ndarray, dt: float = 1.0) -> dict:
    """Estimate Ornstein-Uhlenbeck process parameters.

    The OU process: dX = theta * (mu - X) * dt + sigma * dW
    Parameters are estimated from AR(1) regression on the series.

    Args:
        series: Price or spread series.
        dt: Time step between observations (1.0 for unit time).

    Returns:
        Dict with theta, mu, sigma, half_life, and interpretation.
    """
    y = np.diff(series)
    x = series[:-1]
    X = np.column_stack([np.ones(len(x)), x])

    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha, beta = float(coeffs[0]), float(coeffs[1])

    if beta >= 0:
        return {
            "theta": 0.0,
            "mu": float(np.mean(series)),
            "sigma": float(np.std(np.diff(series))),
            "half_life": -1.0,
            "interpretation": "Not mean-reverting (beta >= 0); OU model not applicable",
        }

    # OU parameter mapping from discrete AR(1)
    theta = -np.log(1 + beta) / dt
    mu = -alpha / beta
    residuals = y - (alpha + beta * x)
    resid_std = float(np.std(residuals))

    # Convert residual std to OU sigma
    exp_term = 1 - np.exp(-2 * theta * dt)
    if exp_term > 0:
        sigma = resid_std * np.sqrt(2 * theta / exp_term)
    else:
        sigma = resid_std

    hl = np.log(2) / theta if theta > 0 else -1.0

    return {
        "theta": float(theta),
        "mu": float(mu),
        "sigma": float(sigma),
        "half_life": float(hl),
        "interpretation": (
            f"Speed of reversion (theta): {theta:.4f}\n"
            f"  Long-run mean (mu): {mu:.4f}\n"
            f"  Volatility (sigma): {sigma:.4f}\n"
            f"  Half-life: {hl:.1f} periods"
        ),
    }


# ── Z-Score Signal Generation ──────────────────────────────────────
def compute_z_scores(
    prices: np.ndarray,
    lookback: int,
) -> np.ndarray:
    """Compute rolling z-scores for mean-reversion signals.

    z = (price - rolling_mean) / rolling_std

    Args:
        prices: Price series.
        lookback: Rolling window length (recommend 2x half-life).

    Returns:
        Array of z-scores (NaN for first lookback-1 values).
    """
    s = pd.Series(prices)
    rolling_mean = s.rolling(lookback).mean()
    rolling_std = s.rolling(lookback).std()
    z = (s - rolling_mean) / rolling_std
    return z.values


def generate_signals(
    z_scores: np.ndarray,
    entry_z: float = 2.0,
    exit_z: float = 0.0,
    stop_z: float = 3.0,
) -> np.ndarray:
    """Generate mean-reversion trading signals from z-scores.

    Args:
        z_scores: Array of z-score values.
        entry_z: Absolute z-score threshold for entry.
        exit_z: Absolute z-score threshold for exit (return to mean).
        stop_z: Absolute z-score threshold for stop loss.

    Returns:
        Array of positions: 1 (long), -1 (short), 0 (flat).
    """
    n = len(z_scores)
    positions = np.zeros(n)
    current_pos = 0

    for i in range(n):
        z = z_scores[i]
        if np.isnan(z):
            continue

        if current_pos == 0:
            if z < -entry_z:
                current_pos = 1
            elif z > entry_z:
                current_pos = -1
        elif current_pos == 1:
            if z > -exit_z:
                current_pos = 0
            elif z < -stop_z:
                current_pos = 0
        elif current_pos == -1:
            if z < exit_z:
                current_pos = 0
            elif z > stop_z:
                current_pos = 0

        positions[i] = current_pos

    return positions


# ── Demo Data Generation ───────────────────────────────────────────
def generate_demo_data(
    n: int = 500,
    theta: float = 0.1,
    mu: float = 100.0,
    sigma: float = 2.0,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic mean-reverting data using OU process.

    dX = theta * (mu - X) * dt + sigma * dW

    Args:
        n: Number of data points.
        theta: Speed of mean reversion.
        mu: Long-run mean level.
        sigma: Volatility of innovations.
        seed: Random seed for reproducibility.

    Returns:
        Array of simulated prices.
    """
    rng = np.random.default_rng(seed)
    prices = np.zeros(n)
    prices[0] = mu + rng.normal(0, sigma)

    dt = 1.0
    for i in range(1, n):
        dW = rng.normal(0, np.sqrt(dt))
        prices[i] = prices[i - 1] + theta * (mu - prices[i - 1]) * dt + sigma * dW

    return prices


# ── Birdeye Data Fetching ──────────────────────────────────────────
def fetch_birdeye_ohlcv(
    mint: str,
    api_key: str,
    interval: str = "1H",
    limit: int = 200,
) -> Optional[np.ndarray]:
    """Fetch OHLCV data from Birdeye API and return close prices.

    Args:
        mint: Solana token mint address.
        api_key: Birdeye API key.
        interval: Candle interval (1m, 5m, 15m, 1H, 4H, 1D).
        limit: Number of candles to fetch.

    Returns:
        Array of close prices, or None on failure.
    """
    try:
        import httpx
    except ImportError:
        print("Error: httpx required for live data. Install with: uv pip install httpx")
        return None

    import time

    url = "https://public-api.birdeye.so/defi/ohlcv"
    now = int(time.time())
    # Map interval to seconds for time_from calculation
    interval_seconds = {
        "1m": 60, "5m": 300, "15m": 900,
        "1H": 3600, "4H": 14400, "1D": 86400,
    }
    secs = interval_seconds.get(interval, 3600)
    time_from = now - (limit * secs)

    params = {
        "address": mint,
        "type": interval,
        "time_from": time_from,
        "time_to": now,
    }
    headers = {"X-API-KEY": api_key, "accept": "application/json"}

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"Birdeye API error: {e.response.status_code} - {e.response.text[:200]}")
        return None
    except httpx.RequestError as e:
        print(f"Network error: {e}")
        return None

    items = data.get("data", {}).get("items", [])
    if not items:
        print("No OHLCV data returned from Birdeye.")
        return None

    closes = [float(item["c"]) for item in items if "c" in item]
    if len(closes) < 50:
        print(f"Insufficient data: {len(closes)} bars (need >= 50).")
        return None

    return np.array(closes)


# ── Report Generation ──────────────────────────────────────────────
def print_report(
    prices: np.ndarray,
    source: str,
    entry_z: float = 2.0,
    exit_z: float = 0.0,
    stop_z: float = 3.0,
) -> None:
    """Run all mean-reversion tests and print a comprehensive report.

    Args:
        prices: Price series to analyze.
        source: Description of data source (for the report header).
        entry_z: Z-score entry threshold.
        exit_z: Z-score exit threshold.
        stop_z: Z-score stop threshold.
    """
    print("=" * 70)
    print("  MEAN-REVERSION ANALYSIS REPORT")
    print(f"  Data source: {source}")
    print(f"  Series length: {len(prices)} bars")
    print(f"  Price range: {np.min(prices):.4f} - {np.max(prices):.4f}")
    print(f"  Current price: {prices[-1]:.4f}")
    print("=" * 70)

    # ── ADF Test ────────────────────────────────────────────────────
    print("\n1. AUGMENTED DICKEY-FULLER TEST")
    print("-" * 40)
    adf = adf_test(prices, max_lag=1)
    print(f"   Test statistic: {adf['test_statistic']:.4f}")
    print(f"   Approx p-value: {adf['p_value_approx']:.4f}")
    print(f"   Critical values: 1%={adf['critical_values'][0.01]:.2f}, "
          f"5%={adf['critical_values'][0.05]:.2f}, "
          f"10%={adf['critical_values'][0.10]:.2f}")
    print(f"   >> {adf['conclusion']}")

    # ── Hurst Exponent ──────────────────────────────────────────────
    print("\n2. HURST EXPONENT (R/S Method)")
    print("-" * 40)
    try:
        H = hurst_exponent(prices)
        if H < 0.4:
            h_label = "Strongly mean-reverting"
        elif H < 0.5:
            h_label = "Mean-reverting"
        elif H < 0.55:
            h_label = "Near random walk"
        elif H < 0.7:
            h_label = "Trending"
        else:
            h_label = "Strongly trending"
        print(f"   Hurst exponent: {H:.4f}")
        print(f"   >> {h_label}")
    except ValueError as e:
        print(f"   Error: {e}")
        H = 0.5

    # ── Variance Ratio ──────────────────────────────────────────────
    print("\n3. VARIANCE RATIO TEST")
    print("-" * 40)
    for q in [2, 5, 10, 20]:
        if q >= len(prices) // 2:
            continue
        vr = variance_ratio(prices, q=q)
        print(f"   q={q:3d}: VR={vr['vr']:.3f}  z={vr['z_stat']:+.2f}  "
              f"p={vr['p_value']:.4f}  ({vr['conclusion'].split('(')[0].strip()})")

    # ── Half-Life ───────────────────────────────────────────────────
    print("\n4. HALF-LIFE ESTIMATION")
    print("-" * 40)
    hl = estimate_half_life(prices)
    print(f"   Beta (AR1): {hl['beta']:.6f}")
    print(f"   Alpha: {hl['alpha']:.6f}")
    print(f"   Long-run mean (mu): {hl['mu']:.4f}")
    print(f"   R-squared: {hl['r_squared']:.4f}")
    print(f"   Half-life: {hl['half_life']:.1f} periods")
    print(f"   >> {hl['conclusion']}")

    # ── OU Parameters ───────────────────────────────────────────────
    print("\n5. ORNSTEIN-UHLENBECK PARAMETERS")
    print("-" * 40)
    ou = estimate_ou_params(prices)
    print(f"   Theta (speed): {ou['theta']:.6f}")
    print(f"   Mu (mean): {ou['mu']:.4f}")
    print(f"   Sigma (vol): {ou['sigma']:.4f}")
    print(f"   Half-life: {ou['half_life']:.1f} periods")

    # ── Z-Score Signals ─────────────────────────────────────────────
    print("\n6. Z-SCORE SIGNAL STATUS")
    print("-" * 40)
    effective_hl = hl["half_life"] if hl["half_life"] > 0 else 20
    lookback = max(10, int(2 * effective_hl))
    lookback = min(lookback, len(prices) // 2)

    z_scores = compute_z_scores(prices, lookback)
    signals = generate_signals(z_scores, entry_z, exit_z, stop_z)

    current_z = z_scores[-1] if not np.isnan(z_scores[-1]) else 0.0
    current_signal = int(signals[-1])

    signal_map = {1: "LONG (buy -- price below mean)", -1: "SHORT (sell -- price above mean)", 0: "FLAT (no signal)"}
    print(f"   Lookback window: {lookback} bars (2x half-life)")
    print(f"   Entry z: +/-{entry_z:.1f}  Exit z: {exit_z:.1f}  Stop z: +/-{stop_z:.1f}")
    print(f"   Current z-score: {current_z:+.4f}")
    print(f"   Current signal: {signal_map.get(current_signal, 'UNKNOWN')}")

    # Recent z-score history
    recent_z = z_scores[-10:]
    valid_z = [z for z in recent_z if not np.isnan(z)]
    if valid_z:
        print(f"   Recent z range: [{min(valid_z):+.2f}, {max(valid_z):+.2f}]")

    # Count signals in the series
    long_count = int(np.sum(signals == 1))
    short_count = int(np.sum(signals == -1))
    flat_count = int(np.sum(signals == 0))
    print(f"   Signal distribution: Long={long_count}, Short={short_count}, Flat={flat_count}")

    # ── Overall Assessment ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  OVERALL ASSESSMENT")
    print("=" * 70)

    score = 0
    reasons: list[str] = []

    if adf["p_value_approx"] < 0.05:
        score += 1
        reasons.append("ADF: stationary (supports mean reversion)")
    else:
        reasons.append("ADF: non-stationary (against mean reversion)")

    if H < 0.5:
        score += 1
        reasons.append(f"Hurst: {H:.3f} < 0.5 (supports mean reversion)")
    else:
        reasons.append(f"Hurst: {H:.3f} >= 0.5 (against mean reversion)")

    vr_result = variance_ratio(prices, q=5)
    if vr_result["vr"] < 1 and vr_result["p_value"] < 0.10:
        score += 1
        reasons.append(f"VR(5): {vr_result['vr']:.3f} < 1 (supports mean reversion)")
    else:
        reasons.append(f"VR(5): {vr_result['vr']:.3f} (neutral or trending)")

    if hl["half_life"] > 0:
        score += 1
        reasons.append(f"Half-life: {hl['half_life']:.1f} periods (mean-reverting)")
    else:
        reasons.append("Half-life: negative (not mean-reverting)")

    for r in reasons:
        print(f"   {r}")

    print(f"\n   Mean-reversion score: {score}/4")
    if score >= 3:
        print("   >> STRONG mean-reversion evidence. Suitable for MR strategies.")
    elif score >= 2:
        print("   >> MODERATE mean-reversion evidence. Proceed with caution.")
    elif score == 1:
        print("   >> WEAK mean-reversion evidence. Consider other strategies.")
    else:
        print("   >> NO mean-reversion evidence. Do NOT trade mean reversion on this series.")

    if hl["half_life"] > 0:
        print(f"\n   Suggested parameters:")
        print(f"     Lookback window: {lookback} bars")
        print(f"     Holding period: ~{effective_hl:.0f} bars")
        print(f"     Max hold (stop): ~{3 * effective_hl:.0f} bars")

    print("\n   Note: This analysis is for informational purposes only.")
    print("   It does not constitute financial advice or a trading recommendation.")
    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point: parse arguments and run mean-reversion analysis."""
    parser = argparse.ArgumentParser(
        description="Mean-reversion analysis for a single asset."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use synthetic mean-reverting data instead of live data.",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=DEFAULT_LOOKBACK_BARS,
        help=f"Number of bars to analyze (default: {DEFAULT_LOOKBACK_BARS}).",
    )
    parser.add_argument(
        "--entry-z",
        type=float,
        default=2.0,
        help="Z-score entry threshold (default: 2.0).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1H",
        help="Candle interval for Birdeye data (default: 1H).",
    )
    args = parser.parse_args()

    if args.demo:
        print("Running in DEMO mode with synthetic OU process data.")
        print("Parameters: theta=0.1, mu=100.0, sigma=2.0, n=500\n")
        prices = generate_demo_data(n=500, theta=0.1, mu=100.0, sigma=2.0)
        print_report(prices, source="Synthetic OU process (demo)", entry_z=args.entry_z)
    else:
        if not BIRDEYE_API_KEY:
            print("BIRDEYE_API_KEY not set. Use --demo for synthetic data.")
            print("  export BIRDEYE_API_KEY=your_key_here")
            sys.exit(1)

        print(f"Fetching {args.bars} bars of {args.interval} data for {TOKEN_MINT[:8]}...")
        prices = fetch_birdeye_ohlcv(
            mint=TOKEN_MINT,
            api_key=BIRDEYE_API_KEY,
            interval=args.interval,
            limit=args.bars,
        )
        if prices is None:
            print("Failed to fetch data. Use --demo for synthetic data.")
            sys.exit(1)

        print_report(
            prices,
            source=f"Birdeye API ({TOKEN_MINT[:8]}..., {args.interval})",
            entry_z=args.entry_z,
        )


if __name__ == "__main__":
    main()
