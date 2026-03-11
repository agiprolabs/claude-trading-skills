#!/usr/bin/env python3
"""Rolling correlation analysis with regime detection and tail dependence.

Computes rolling correlation between two assets at multiple windows, detects
correlation regime changes using z-score methodology, and estimates tail
dependence to assess crash co-movement.

Usage:
    python scripts/rolling_correlation.py --demo
    python scripts/rolling_correlation.py --coins bitcoin,ethereum --days 365

Dependencies:
    uv pip install pandas numpy httpx

Environment Variables:
    None required for demo mode.
"""

import argparse
import sys
import time
from typing import Optional

import httpx
import numpy as np
import pandas as pd


# ── Configuration ───────────────────────────────────────────────────
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
WINDOWS = {"short": 20, "medium": 60, "long": 120}
TAIL_QUANTILE = 0.05
REQUEST_DELAY = 1.5


# ── Data Fetching ───────────────────────────────────────────────────
def fetch_prices(
    coin_id: str,
    days: int = 365,
    client: Optional[httpx.Client] = None,
) -> Optional[pd.Series]:
    """Fetch daily closing prices from CoinGecko.

    Args:
        coin_id: CoinGecko coin identifier.
        days: Number of days of history.
        client: Optional reusable httpx client.

    Returns:
        Series of daily prices indexed by date, or None on failure.
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    try:
        if client:
            resp = client.get(url, params=params, timeout=15)
        else:
            resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        prices = data.get("prices", [])
        if not prices:
            return None
        return pd.Series(
            {pd.Timestamp(ts, unit="ms").normalize(): price for ts, price in prices},
            name=coin_id,
        )
    except Exception as e:
        print(f"  Error fetching {coin_id}: {e}")
        return None


def generate_demo_data(n_days: int = 365) -> tuple[pd.Series, pd.Series, str, str]:
    """Generate synthetic data showing correlation breakdown.

    Creates two assets that are normally correlated (~0.7) but experience
    a correlation spike mid-sample (simulating a market stress event)
    followed by a correlation breakdown (simulating structural change).

    Args:
        n_days: Number of days to generate.

    Returns:
        Tuple of (returns_a, returns_b, name_a, name_b).
    """
    rng = np.random.default_rng(123)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)

    # Shared market factor
    market = rng.normal(0.0005, 0.02, n_days)

    # Asset A: consistent market exposure
    idio_a = rng.normal(0, 0.015, n_days)
    returns_a = 0.8 * market + idio_a

    # Asset B: changing correlation regime
    idio_b = rng.normal(0, 0.018, n_days)
    returns_b = np.zeros(n_days)

    # Phase 1 (days 0-120): normal correlation ~0.7
    phase1 = slice(0, 120)
    returns_b[phase1] = 0.7 * market[phase1] + idio_b[phase1]

    # Phase 2 (days 120-180): stress event — correlation spikes to ~0.95
    phase2 = slice(120, 180)
    stress = rng.normal(-0.02, 0.03, 60)  # negative drift during stress
    returns_b[phase2] = 0.95 * market[phase2] + 0.3 * stress + 0.5 * idio_b[phase2]

    # Phase 3 (days 180-280): recovery — correlation normalizes
    phase3 = slice(180, 280)
    returns_b[phase3] = 0.65 * market[phase3] + idio_b[phase3]

    # Phase 4 (days 280+): structural change — correlation breaks down
    phase4 = slice(280, n_days)
    sector_factor = rng.normal(0, 0.025, n_days)
    returns_b[phase4] = 0.3 * market[phase4] + 0.6 * sector_factor[phase4] + idio_b[phase4]

    series_a = pd.Series(returns_a, index=dates, name="Asset_A")
    series_b = pd.Series(returns_b, index=dates, name="Asset_B")
    return series_a, series_b, "Asset_A", "Asset_B"


# ── Rolling Correlation ────────────────────────────────────────────
def compute_rolling_correlations(
    returns_a: pd.Series,
    returns_b: pd.Series,
    windows: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Compute rolling correlation at multiple window sizes.

    Args:
        returns_a: First asset return series.
        returns_b: Second asset return series.
        windows: Dict of {label: window_size}. Defaults to WINDOWS.

    Returns:
        DataFrame with rolling correlation columns.
    """
    if windows is None:
        windows = WINDOWS

    result = pd.DataFrame(index=returns_a.index)
    for label, w in windows.items():
        result[f"corr_{label}"] = returns_a.rolling(w).corr(returns_b)
    return result


def ewma_correlation(
    x: pd.Series, y: pd.Series, span: int = 60
) -> pd.Series:
    """Compute EWMA correlation between two return series.

    Args:
        x: First return series.
        y: Second return series.
        span: EWMA span parameter.

    Returns:
        Series of EWMA correlation values.
    """
    mean_x = x.ewm(span=span).mean()
    mean_y = y.ewm(span=span).mean()
    cov = (x * y).ewm(span=span).mean() - mean_x * mean_y
    var_x = x.pow(2).ewm(span=span).mean() - mean_x.pow(2)
    var_y = y.pow(2).ewm(span=span).mean() - mean_y.pow(2)
    denom = var_x.pow(0.5) * var_y.pow(0.5)
    return cov / denom.replace(0, np.nan)


# ── Regime Detection ───────────────────────────────────────────────
def detect_correlation_regimes(
    rolling_corr: pd.Series,
    lookback: int = 120,
    z_threshold: float = 2.0,
) -> pd.DataFrame:
    """Detect correlation regime changes using z-score method.

    Args:
        rolling_corr: Series of rolling correlation values.
        lookback: Window for computing mean/std of correlation.
        z_threshold: Z-score threshold for regime flag.

    Returns:
        DataFrame with correlation, z-score, and regime columns.
    """
    clean = rolling_corr.dropna()
    mean = clean.rolling(lookback, min_periods=30).mean()
    std = clean.rolling(lookback, min_periods=30).std()
    zscore = (clean - mean) / std.replace(0, np.nan)

    regime = pd.Series("normal", index=clean.index)
    regime[zscore > z_threshold] = "HIGH_CORR"
    regime[zscore < -z_threshold] = "LOW_CORR"

    return pd.DataFrame({
        "correlation": clean,
        "rolling_mean": mean,
        "zscore": zscore,
        "regime": regime,
    })


def find_regime_changes(regime_df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Find dates where correlation regime changes.

    Args:
        regime_df: DataFrame from detect_correlation_regimes.

    Returns:
        List of (date_str, from_regime, to_regime) tuples.
    """
    changes: list[tuple[str, str, str]] = []
    prev_regime = "normal"
    for date, row in regime_df.iterrows():
        current = row["regime"]
        if current != prev_regime:
            changes.append((
                date.strftime("%Y-%m-%d"),  # type: ignore[union-attr]
                prev_regime,
                current,
            ))
        prev_regime = current
    return changes


# ── Tail Dependence ─────────────────────────────────────────────────
def compute_tail_dependence(
    returns_a: pd.Series,
    returns_b: pd.Series,
    quantile: float = TAIL_QUANTILE,
) -> dict[str, float]:
    """Estimate tail dependence coefficients.

    Args:
        returns_a: First asset returns.
        returns_b: Second asset returns.
        quantile: Quantile threshold for extreme events (default 5%).

    Returns:
        Dict with lower_tail, upper_tail, and joint_extreme_count.
    """
    n = len(returns_a)

    # Lower tail: crash together
    thresh_a_low = returns_a.quantile(quantile)
    thresh_b_low = returns_b.quantile(quantile)
    a_extreme_low = returns_a < thresh_a_low
    b_extreme_low = returns_b < thresh_b_low
    joint_low = (a_extreme_low & b_extreme_low).sum()
    marginal_low = a_extreme_low.sum()
    lower_tail = joint_low / marginal_low if marginal_low > 0 else 0.0

    # Upper tail: rally together
    thresh_a_high = returns_a.quantile(1 - quantile)
    thresh_b_high = returns_b.quantile(1 - quantile)
    a_extreme_high = returns_a > thresh_a_high
    b_extreme_high = returns_b > thresh_b_high
    joint_high = (a_extreme_high & b_extreme_high).sum()
    marginal_high = a_extreme_high.sum()
    upper_tail = joint_high / marginal_high if marginal_high > 0 else 0.0

    return {
        "lower_tail_dependence": lower_tail,
        "upper_tail_dependence": upper_tail,
        "joint_crash_events": int(joint_low),
        "joint_rally_events": int(joint_high),
        "total_observations": n,
        "extreme_threshold_pct": quantile * 100,
    }


# ── Summary Statistics ──────────────────────────────────────────────
def correlation_summary(
    returns_a: pd.Series,
    returns_b: pd.Series,
    name_a: str,
    name_b: str,
) -> dict[str, float]:
    """Compute full-sample correlation statistics.

    Args:
        returns_a: First asset returns.
        returns_b: Second asset returns.
        name_a: Name of first asset.
        name_b: Name of second asset.

    Returns:
        Dict of correlation statistics.
    """
    n = len(returns_a)
    pearson = returns_a.corr(returns_b, method="pearson")
    spearman = returns_a.corr(returns_b, method="spearman")
    kendall = returns_a.corr(returns_b, method="kendall")

    # Statistical significance (Pearson)
    if abs(pearson) < 1.0 and n > 2:
        t_stat = pearson * np.sqrt(n - 2) / np.sqrt(1 - pearson ** 2)
    else:
        t_stat = np.inf

    # Fisher z-transform confidence interval
    if abs(pearson) < 1.0 and n > 3:
        z = np.arctanh(pearson)
        se = 1.0 / np.sqrt(n - 3)
        ci_low = np.tanh(z - 1.96 * se)
        ci_high = np.tanh(z + 1.96 * se)
    else:
        ci_low, ci_high = pearson, pearson

    return {
        "pair": f"{name_a} / {name_b}",
        "n_obs": n,
        "pearson": pearson,
        "spearman": spearman,
        "kendall": kendall,
        "t_statistic": t_stat,
        "ci_95_low": ci_low,
        "ci_95_high": ci_high,
    }


# ── Display ─────────────────────────────────────────────────────────
def print_rolling_summary(
    rolling_df: pd.DataFrame, ewma_corr: pd.Series
) -> None:
    """Print summary of rolling correlation values.

    Args:
        rolling_df: DataFrame from compute_rolling_correlations.
        ewma_corr: Series of EWMA correlation values.
    """
    print("\n  Rolling Correlation Summary:")
    print("  " + "-" * 55)
    print(f"  {'Window':<12} {'Current':>8} {'Mean':>8} {'Min':>8} {'Max':>8} {'Std':>8}")
    print("  " + "-" * 55)

    for col in rolling_df.columns:
        s = rolling_df[col].dropna()
        if len(s) == 0:
            continue
        label = col.replace("corr_", "").capitalize()
        print(f"  {label:<12} {s.iloc[-1]:>8.3f} {s.mean():>8.3f} "
              f"{s.min():>8.3f} {s.max():>8.3f} {s.std():>8.3f}")

    ewma_clean = ewma_corr.dropna()
    if len(ewma_clean) > 0:
        print(f"  {'EWMA(60)':<12} {ewma_clean.iloc[-1]:>8.3f} "
              f"{ewma_clean.mean():>8.3f} {ewma_clean.min():>8.3f} "
              f"{ewma_clean.max():>8.3f} {ewma_clean.std():>8.3f}")
    print()


def print_regime_timeline(
    regime_df: pd.DataFrame, last_n: int = 20
) -> None:
    """Print recent correlation regime timeline.

    Args:
        regime_df: DataFrame from detect_correlation_regimes.
        last_n: Number of recent observations to show.
    """
    recent = regime_df.tail(last_n)
    print(f"\n  Recent Correlation Regime (last {last_n} observations):")
    print("  " + "-" * 55)
    print(f"  {'Date':<12} {'Corr':>7} {'Z-Score':>8} {'Regime':<12}")
    print("  " + "-" * 55)
    for date, row in recent.iterrows():
        date_str = date.strftime("%Y-%m-%d")  # type: ignore[union-attr]
        corr_val = row["correlation"]
        z_val = row["zscore"]
        regime = row["regime"]
        z_str = f"{z_val:>8.2f}" if not np.isnan(z_val) else "     N/A"
        marker = " !" if regime != "normal" else "  "
        print(f"  {date_str:<12} {corr_val:>7.3f} {z_str} {regime:<12}{marker}")
    print()


def print_correlation_assessment(
    summary: dict[str, float],
    tail_dep: dict[str, float],
    regime_df: pd.DataFrame,
) -> None:
    """Print overall assessment of the correlation relationship.

    Args:
        summary: From correlation_summary.
        tail_dep: From compute_tail_dependence.
        regime_df: From detect_correlation_regimes.
    """
    print("\n  Overall Assessment:")
    print("  " + "-" * 55)

    pearson = summary["pearson"]
    if abs(pearson) > 0.8:
        strength = "STRONG"
    elif abs(pearson) > 0.5:
        strength = "MODERATE"
    elif abs(pearson) > 0.3:
        strength = "WEAK"
    else:
        strength = "NEGLIGIBLE"

    direction = "positive" if pearson > 0 else "negative"
    print(f"  Correlation strength: {strength} {direction} (r={pearson:.3f})")
    print(f"  95% CI: [{summary['ci_95_low']:.3f}, {summary['ci_95_high']:.3f}]")

    # Spearman vs Pearson divergence
    diff = abs(summary["spearman"] - summary["pearson"])
    if diff > 0.1:
        print(f"  Spearman-Pearson gap: {diff:.3f} — suggests non-linear relationship")

    # Tail dependence assessment
    lower = tail_dep["lower_tail_dependence"]
    if lower > pearson and pearson > 0:
        print(f"  WARNING: Tail dependence ({lower:.2f}) > normal correlation ({pearson:.2f})")
        print(f"  Assets crash together MORE than normal correlation suggests.")
    elif lower > 0.5:
        print(f"  High tail dependence ({lower:.2f}) — significant crash co-movement.")

    # Regime stability
    regime_counts = regime_df["regime"].value_counts()
    pct_abnormal = 1.0 - regime_counts.get("normal", 0) / len(regime_df)
    if pct_abnormal > 0.2:
        print(f"  Unstable correlation: {pct_abnormal:.0%} of time in abnormal regime.")
    else:
        print(f"  Correlation regime is relatively stable ({pct_abnormal:.0%} abnormal).")

    # Current regime
    current_regime = regime_df["regime"].iloc[-1]
    current_z = regime_df["zscore"].iloc[-1]
    if current_regime != "normal":
        print(f"  ALERT: Currently in {current_regime} regime (z={current_z:.2f}).")

    print("\n  Note: This is analysis output, not financial advice.")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run rolling correlation analysis."""
    parser = argparse.ArgumentParser(
        description="Rolling correlation with regime detection and tail dependence"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Use synthetic demo data with correlation regime changes"
    )
    parser.add_argument(
        "--coins", type=str, default="bitcoin,ethereum",
        help="Two comma-separated CoinGecko IDs (default: bitcoin,ethereum)"
    )
    parser.add_argument(
        "--days", type=int, default=365,
        help="Days of history (default: 365)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  ROLLING CORRELATION ANALYSIS")
    print("=" * 60)

    if args.demo:
        print("\n  Mode: DEMO (synthetic data with regime changes)")
        returns_a, returns_b, name_a, name_b = generate_demo_data()
    else:
        coins = args.coins.split(",")
        if len(coins) != 2:
            print("  Error: provide exactly 2 coin IDs (e.g., --coins bitcoin,ethereum)")
            sys.exit(1)

        name_a, name_b = coins[0], coins[1]
        print(f"\n  Fetching {args.days}d data for {name_a} and {name_b}...")

        with httpx.Client() as client:
            prices_a = fetch_prices(name_a, days=args.days, client=client)
            time.sleep(REQUEST_DELAY)
            prices_b = fetch_prices(name_b, days=args.days, client=client)

        if prices_a is None or prices_b is None:
            print("  Error: could not fetch price data. Try --demo mode.")
            sys.exit(1)

        prices = pd.DataFrame({"a": prices_a, "b": prices_b}).dropna()
        if len(prices) < 30:
            print(f"  Error: only {len(prices)} data points — need at least 30.")
            sys.exit(1)

        returns_a = prices["a"].pct_change().dropna()
        returns_b = prices["b"].pct_change().dropna()
        # Align
        common_idx = returns_a.index.intersection(returns_b.index)
        returns_a = returns_a.loc[common_idx]
        returns_b = returns_b.loc[common_idx]

    print(f"\n  Pair: {name_a} / {name_b}")
    print(f"  Observations: {len(returns_a)}")
    print(f"  Date range: {returns_a.index[0].strftime('%Y-%m-%d')} to "
          f"{returns_a.index[-1].strftime('%Y-%m-%d')}")

    # Full-sample correlation
    summary = correlation_summary(returns_a, returns_b, name_a, name_b)
    print("\n  Full-Sample Correlation:")
    print("  " + "-" * 45)
    print(f"  Pearson:    {summary['pearson']:>+.4f}")
    print(f"  Spearman:   {summary['spearman']:>+.4f}")
    print(f"  Kendall:    {summary['kendall']:>+.4f}")
    print(f"  t-statistic: {summary['t_statistic']:.2f}")
    print(f"  95% CI:     [{summary['ci_95_low']:.3f}, {summary['ci_95_high']:.3f}]")

    # Rolling correlation
    rolling_df = compute_rolling_correlations(returns_a, returns_b)
    ewma_corr = ewma_correlation(returns_a, returns_b, span=60)
    print_rolling_summary(rolling_df, ewma_corr)

    # Regime detection (using medium window correlation)
    medium_corr = rolling_df["corr_medium"].dropna()
    if len(medium_corr) > 30:
        regime_df = detect_correlation_regimes(medium_corr)
        print_regime_timeline(regime_df)

        # Regime changes
        changes = find_regime_changes(regime_df)
        if changes:
            print("  Regime Change Events:")
            print("  " + "-" * 45)
            for date_str, from_r, to_r in changes:
                print(f"  {date_str}: {from_r} -> {to_r}")
            print()
    else:
        regime_df = pd.DataFrame({"regime": ["normal"], "zscore": [0.0]})
        print("  Insufficient data for regime detection (need >90 observations).\n")

    # Tail dependence
    tail_dep = compute_tail_dependence(returns_a, returns_b)
    print("\n  Tail Dependence Analysis:")
    print("  " + "-" * 50)
    print(f"  Lower tail (crash together):  {tail_dep['lower_tail_dependence']:.3f}")
    print(f"  Upper tail (rally together):  {tail_dep['upper_tail_dependence']:.3f}")
    print(f"  Joint crash events:           {tail_dep['joint_crash_events']}")
    print(f"  Joint rally events:           {tail_dep['joint_rally_events']}")
    print(f"  Extreme threshold:            {tail_dep['extreme_threshold_pct']:.1f}th percentile")

    # Comparison: tail dependence vs normal correlation
    if tail_dep["lower_tail_dependence"] > abs(summary["pearson"]):
        print("  >> Tail dependence EXCEEDS normal correlation — crashes are more correlated")
        print("     than average co-movement suggests. Diversification benefit overstated.")
    else:
        print("  >> Tail dependence within expected range given normal correlation.")

    # Overall assessment
    print_correlation_assessment(summary, tail_dep, regime_df)
    print("=" * 60)


if __name__ == "__main__":
    main()
