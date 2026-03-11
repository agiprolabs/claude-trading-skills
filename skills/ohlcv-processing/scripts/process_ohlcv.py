#!/usr/bin/env python3
"""Full OHLCV processing pipeline: validate, clean, resample, normalize.

Runs a complete data preparation workflow on OHLCV candle data. Supports
fetching from the Birdeye API or running in --demo mode with synthetic data
that includes intentional anomalies for testing.

Usage:
    python scripts/process_ohlcv.py --demo
    python scripts/process_ohlcv.py --token So11111111111111111111111111111111111111112

Dependencies:
    uv pip install pandas numpy httpx

Environment Variables:
    BIRDEYE_API_KEY: Your Birdeye API key (only needed for live data mode)
"""

import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

# ── Configuration ───────────────────────────────────────────────────
BIRDEYE_BASE = "https://public-api.birdeye.so"
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

OHLCV_RESAMPLE_RULES: dict[str, str] = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}

TIMEFRAME_LADDER = ["1min", "5min", "15min", "1h", "4h", "1D"]


# ── Demo Data Generation ───────────────────────────────────────────
def generate_demo_data(bars: int = 1440, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic 1-minute OHLCV data with intentional anomalies.

    Creates ~24 hours of data with realistic price action and injects:
    - Price spikes (3 bars)
    - Zero volume bars (5 bars)
    - Impossible candles where high < low (2 bars)
    - Negative prices (1 bar)
    - Duplicate timestamps (2 bars)
    - Gaps (10 missing bars)

    Args:
        bars: Number of bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        Raw OHLCV DataFrame with anomalies (before cleaning).
    """
    rng = np.random.default_rng(seed)

    timestamps = pd.date_range(
        start="2025-06-01 00:00:00", periods=bars, freq="1min", tz="UTC"
    )

    # Generate a random walk for close prices starting at $100
    returns = rng.normal(0.0001, 0.003, size=bars)
    close = 100.0 * np.cumprod(1 + returns)

    # Derive OHLC from close
    spread = rng.uniform(0.001, 0.005, size=bars)
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_price = close * (1 + rng.normal(0, 0.002, size=bars))

    # Ensure OHLC consistency before injecting anomalies
    high = np.maximum(high, np.maximum(open_price, close))
    low = np.minimum(low, np.minimum(open_price, close))

    volume = rng.exponential(50000, size=bars).astype(float)

    df = pd.DataFrame(
        {
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=timestamps,
    )
    df.index.name = "timestamp"

    # ── Inject anomalies ────────────────────────────────────────────

    # 1. Price spikes: 3 bars with 20x normal return
    spike_indices = [200, 600, 1000]
    for idx in spike_indices:
        if idx < len(df):
            df.iloc[idx, df.columns.get_loc("close")] *= 1.5
            df.iloc[idx, df.columns.get_loc("high")] *= 1.8

    # 2. Zero volume bars
    zero_vol_indices = [100, 300, 500, 700, 900]
    for idx in zero_vol_indices:
        if idx < len(df):
            df.iloc[idx, df.columns.get_loc("volume")] = 0.0

    # 3. Impossible candles (high < low)
    impossible_indices = [150, 850]
    for idx in impossible_indices:
        if idx < len(df):
            h = df.iloc[idx]["high"]
            l = df.iloc[idx]["low"]
            df.iloc[idx, df.columns.get_loc("high")] = l * 0.99
            df.iloc[idx, df.columns.get_loc("low")] = h * 1.01

    # 4. Negative price
    if len(df) > 400:
        df.iloc[400, df.columns.get_loc("close")] = -1.0

    # 5. Gaps: remove 10 bars (will be detected during processing)
    gap_indices = list(range(250, 260))
    df = df.drop(df.index[gap_indices])

    # 6. Duplicate timestamps: copy bar 50 to create a duplicate
    if len(df) > 50:
        dupe_row = df.iloc[50:51].copy()
        dupe_row["volume"] = dupe_row["volume"] * 0.5  # Different volume
        df = pd.concat([df, dupe_row]).sort_index()

    print(f"Generated {len(df)} bars of demo data with injected anomalies")
    return df


# ── Data Fetching ───────────────────────────────────────────────────
def fetch_birdeye_ohlcv(
    token_address: str,
    interval: str = "1m",
    limit: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV data from Birdeye API.

    Args:
        token_address: Solana token mint address.
        interval: Candle interval (1m, 5m, 15m, 1H, 4H, 1D).
        limit: Maximum number of candles to fetch.

    Returns:
        OHLCV DataFrame with DatetimeIndex in UTC.

    Raises:
        SystemExit: If API key is not set.
        httpx.HTTPStatusError: On API error.
    """
    import httpx

    api_key = os.getenv("BIRDEYE_API_KEY", "")
    if not api_key:
        print("Error: Set BIRDEYE_API_KEY environment variable")
        sys.exit(1)

    headers = {
        "X-API-KEY": api_key,
        "x-chain": "solana",
        "accept": "application/json",
    }

    import time

    time_to = int(time.time())
    # Estimate time_from based on interval and limit
    interval_seconds = {
        "1m": 60, "5m": 300, "15m": 900,
        "1H": 3600, "4H": 14400, "1D": 86400,
    }
    seconds_per_bar = interval_seconds.get(interval, 60)
    time_from = time_to - (limit * seconds_per_bar)

    resp = httpx.get(
        f"{BIRDEYE_BASE}/defi/ohlcv",
        headers=headers,
        params={
            "address": token_address,
            "type": interval,
            "time_from": time_from,
            "time_to": time_to,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    items = data.get("data", {}).get("items", [])
    if not items:
        print("Warning: No OHLCV data returned from Birdeye")
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(items)
    df["timestamp"] = pd.to_datetime(df["unixTime"], unit="s", utc=True)
    df = df.set_index("timestamp")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["open", "high", "low", "close", "volume"]]

    print(f"Fetched {len(df)} bars from Birdeye API")
    return df


# ── Validation ──────────────────────────────────────────────────────
def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase standard format.

    Args:
        df: Raw OHLCV DataFrame.

    Returns:
        DataFrame with standardized column names.

    Raises:
        ValueError: If required columns are missing after normalization.
    """
    df = df.copy()
    df.columns = df.columns.str.lower().str.strip()
    rename_map = {"vol": "volume", "v": "volume", "o": "open",
                  "h": "high", "l": "low", "c": "close"}
    df = df.rename(columns=rename_map)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df[["open", "high", "low", "close", "volume"]]


def validate_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and fix OHLCV structural integrity.

    - Ensures DatetimeIndex in UTC
    - Sorts by timestamp ascending
    - Removes duplicate timestamps (keeps last)
    - Enforces numeric types

    Args:
        df: OHLCV DataFrame.

    Returns:
        Structurally valid DataFrame.
    """
    df = df.copy()

    # Ensure DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    elif str(df.index.tz) != "UTC":
        df.index = df.index.tz_convert("UTC")

    # Sort ascending
    df = df.sort_index()

    # Remove duplicates
    dupes = df.index.duplicated(keep="last")
    if dupes.any():
        n_dupes = dupes.sum()
        print(f"  Removed {n_dupes} duplicate timestamp(s)")
        df = df[~dupes]

    # Enforce numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ── Anomaly Detection ──────────────────────────────────────────────
def detect_anomalies(
    df: pd.DataFrame,
    spike_window: int = 20,
    spike_threshold: float = 3.0,
) -> pd.DataFrame:
    """Detect and flag all anomaly types in OHLCV data.

    Checks for:
    - Price spikes (return > threshold * rolling std)
    - Zero volume bars
    - Impossible candles (high < low, etc.)
    - Negative prices
    - NaN values

    Args:
        df: Validated OHLCV DataFrame.
        spike_window: Rolling window for spike detection.
        spike_threshold: Number of standard deviations for spike threshold.

    Returns:
        DataFrame with anomaly flag columns added.
    """
    df = df.copy()

    # Price spikes
    returns = df["close"].pct_change()
    rolling_std = returns.rolling(spike_window, min_periods=5).std()
    df["anomaly_spike"] = (returns.abs() > (spike_threshold * rolling_std)).fillna(False)

    # Zero volume
    df["anomaly_zero_vol"] = df["volume"] <= 0

    # Impossible candles
    df["anomaly_impossible"] = (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )

    # Negative prices
    df["anomaly_negative"] = (
        (df["open"] < 0) | (df["high"] < 0) |
        (df["low"] < 0) | (df["close"] < 0)
    )

    # NaN values
    df["anomaly_nan"] = df[["open", "high", "low", "close"]].isna().any(axis=1)

    # Composite flag
    df["anomaly_any"] = (
        df["anomaly_spike"] | df["anomaly_zero_vol"] |
        df["anomaly_impossible"] | df["anomaly_negative"] |
        df["anomaly_nan"]
    )

    return df


# ── Cleaning ────────────────────────────────────────────────────────
def clean_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Fix detected anomalies in OHLCV data.

    - Removes bars with negative prices
    - Fixes impossible candles by recalculating high/low
    - Interpolates price spikes
    - Leaves zero-volume bars flagged but intact

    Args:
        df: DataFrame with anomaly flags from detect_anomalies().

    Returns:
        Cleaned DataFrame.
    """
    df = df.copy()
    initial_len = len(df)

    # Remove negative prices
    neg_mask = df.get("anomaly_negative", pd.Series(False, index=df.index))
    if neg_mask.any():
        n_neg = neg_mask.sum()
        df = df[~neg_mask]
        print(f"  Removed {n_neg} bar(s) with negative prices")

    # Fix impossible candles
    impossible = (
        (df["high"] < df["low"]) |
        (df["high"] < df["open"]) |
        (df["high"] < df["close"]) |
        (df["low"] > df["open"]) |
        (df["low"] > df["close"])
    )
    if impossible.any():
        n_imp = impossible.sum()
        # Recalculate high and low from all four price fields
        price_cols = df.loc[impossible, ["open", "high", "low", "close"]]
        df.loc[impossible, "high"] = price_cols.max(axis=1)
        df.loc[impossible, "low"] = price_cols.min(axis=1)
        print(f"  Fixed {n_imp} impossible candle(s)")

    # Interpolate price spikes
    spike_mask = df.get("anomaly_spike", pd.Series(False, index=df.index))
    if spike_mask.any():
        n_spikes = spike_mask.sum()
        for col in ["open", "high", "low", "close"]:
            df.loc[spike_mask, col] = np.nan
            df[col] = df[col].interpolate(method="time")
        print(f"  Interpolated {n_spikes} price spike(s)")

    removed = initial_len - len(df)
    if removed > 0:
        print(f"  Total bars removed: {removed}")

    return df


# ── Gap Handling ────────────────────────────────────────────────────
def handle_gaps(
    df: pd.DataFrame,
    freq: str = "1min",
    method: str = "ffill",
    max_gap: int = 5,
) -> pd.DataFrame:
    """Detect and fill gaps in OHLCV data.

    Args:
        df: OHLCV DataFrame.
        freq: Expected bar frequency.
        method: Fill method ('ffill' or 'interpolate').
        max_gap: Maximum consecutive bars to fill.

    Returns:
        DataFrame with gaps filled and is_filled column added.
    """
    df = df.copy()
    full_index = pd.date_range(
        start=df.index.min(), end=df.index.max(), freq=freq, tz="UTC"
    )
    n_missing = len(full_index) - len(df)

    df = df.reindex(full_index)
    df.index.name = "timestamp"
    df["is_filled"] = df["close"].isna()

    if n_missing > 0:
        print(f"  Found {n_missing} gap(s) in data")

    if method == "ffill":
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].ffill(limit=max_gap)
        df["volume"] = df["volume"].fillna(0)
    elif method == "interpolate":
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].interpolate(method="time", limit=max_gap)
        df["volume"] = df["volume"].fillna(0)

    filled_count = df["is_filled"].sum()
    still_nan = df["close"].isna().sum()
    if filled_count > 0:
        print(f"  Filled {int(filled_count - still_nan)} bar(s), "
              f"{int(still_nan)} unfillable (gap > {max_gap})")

    return df


# ── Resampling ──────────────────────────────────────────────────────
def resample_ohlcv(df: pd.DataFrame, target_freq: str) -> pd.DataFrame:
    """Resample OHLCV data to a coarser timeframe.

    Args:
        df: OHLCV DataFrame (must be finer than target_freq).
        target_freq: Pandas frequency string (e.g., '5min', '1h', '1D').

    Returns:
        Resampled OHLCV DataFrame.
    """
    ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    resampled = df[ohlcv_cols].resample(target_freq).agg(OHLCV_RESAMPLE_RULES)
    return resampled.dropna(subset=["close"])


def resample_ladder(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Resample 1-minute data to all standard timeframes.

    Args:
        df: 1-minute OHLCV DataFrame.

    Returns:
        Dictionary mapping timeframe labels to resampled DataFrames.
    """
    results: dict[str, pd.DataFrame] = {"1min": df.copy()}
    for tf in TIMEFRAME_LADDER[1:]:
        results[tf] = resample_ohlcv(df, tf)
    return results


# ── Normalization ───────────────────────────────────────────────────
def normalize_prices(
    df: pd.DataFrame, method: str = "returns"
) -> pd.DataFrame:
    """Normalize OHLCV price columns.

    Args:
        df: OHLCV DataFrame.
        method: Normalization method — 'returns', 'log_returns', 'minmax', 'zscore'.

    Returns:
        DataFrame with normalized columns added (original columns preserved).
    """
    price_cols = ["open", "high", "low", "close"]
    result = df.copy()

    if method == "returns":
        for col in price_cols:
            result[f"{col}_ret"] = result[col].pct_change()
    elif method == "log_returns":
        for col in price_cols:
            result[f"{col}_logret"] = np.log(result[col] / result[col].shift(1))
    elif method == "minmax":
        for col in price_cols:
            cmin = result[col].min()
            cmax = result[col].max()
            denom = cmax - cmin
            if denom == 0:
                result[f"{col}_norm"] = 0.0
            else:
                result[f"{col}_norm"] = (result[col] - cmin) / denom
    elif method == "zscore":
        for col in price_cols:
            std = result[col].std()
            if std == 0:
                result[f"{col}_z"] = 0.0
            else:
                result[f"{col}_z"] = (result[col] - result[col].mean()) / std
    else:
        raise ValueError(f"Unknown normalization method: {method}")

    return result


# ── Quality Report ──────────────────────────────────────────────────
def quality_report(df: pd.DataFrame) -> dict[str, object]:
    """Generate a comprehensive data quality summary.

    Args:
        df: OHLCV DataFrame (may include anomaly flag columns).

    Returns:
        Dictionary with quality metrics.
    """
    total = len(df)
    report: dict[str, object] = {
        "total_bars": total,
        "date_range": f"{df.index.min()} -> {df.index.max()}",
        "missing_close": int(df["close"].isna().sum()),
        "missing_any_price": int(df[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
        "zero_volume_bars": int((df["volume"] == 0).sum()),
        "impossible_candles": int((df["high"] < df["low"]).sum()),
        "negative_prices": int((df[["open", "high", "low", "close"]] < 0).any(axis=1).sum()),
        "duplicate_timestamps": int(df.index.duplicated().sum()),
    }

    if "anomaly_spike" in df.columns:
        report["flagged_spikes"] = int(df["anomaly_spike"].sum())
    if "anomaly_any" in df.columns:
        report["total_anomalies"] = int(df["anomaly_any"].sum())
    if "is_filled" in df.columns:
        report["filled_bars"] = int(df["is_filled"].sum())

    # Completeness
    completeness = (1 - df["close"].isna().mean()) * 100
    report["completeness_pct"] = round(completeness, 2)

    return report


def print_report(report: dict[str, object]) -> None:
    """Pretty-print a quality report.

    Args:
        report: Dictionary from quality_report().
    """
    print("\n" + "=" * 60)
    print("  OHLCV DATA QUALITY REPORT")
    print("=" * 60)
    for key, value in report.items():
        label = key.replace("_", " ").title()
        print(f"  {label:.<40} {value}")
    print("=" * 60 + "\n")


# ── Full Pipeline ───────────────────────────────────────────────────
def run_pipeline(
    df: pd.DataFrame,
    freq: str = "1min",
    gap_method: str = "ffill",
    max_gap: int = 5,
    normalize: str = "returns",
    resample_to: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """Run the complete OHLCV processing pipeline.

    Steps: standardize -> validate -> detect anomalies -> report (pre-clean)
    -> clean -> fill gaps -> normalize -> resample -> report (post-clean)

    Args:
        df: Raw OHLCV DataFrame.
        freq: Expected bar frequency for gap detection.
        gap_method: Gap fill method ('ffill' or 'interpolate').
        max_gap: Maximum consecutive gap bars to fill.
        normalize: Normalization method.
        resample_to: List of target timeframes (e.g., ['5min', '1h']).

    Returns:
        Dictionary with 'clean' DataFrame and any resampled DataFrames.
    """
    print("\n[1/6] Standardizing columns...")
    df = standardize_columns(df)

    print("[2/6] Validating structure...")
    df = validate_structure(df)

    print("[3/6] Detecting anomalies...")
    df = detect_anomalies(df)

    pre_report = quality_report(df)
    print_report(pre_report)

    print("[4/6] Cleaning anomalies...")
    df = clean_anomalies(df)

    print("[5/6] Handling gaps...")
    df = handle_gaps(df, freq=freq, method=gap_method, max_gap=max_gap)

    print("[6/6] Normalizing prices...")
    df = normalize_prices(df, method=normalize)

    # Re-run anomaly detection on cleaned data for final report
    df = detect_anomalies(df)
    post_report = quality_report(df)
    print("\n--- Post-Processing Report ---")
    print_report(post_report)

    results: dict[str, pd.DataFrame] = {"clean": df}

    # Resample if requested
    if resample_to:
        print("Resampling to additional timeframes...")
        ohlcv_cols = ["open", "high", "low", "close", "volume"]
        base = df[ohlcv_cols].dropna(subset=["close"])
        for tf in resample_to:
            resampled = resample_ohlcv(base, tf)
            results[tf] = resampled
            print(f"  {tf}: {len(resampled)} bars")

    return results


# ── CLI ─────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="OHLCV data processing pipeline"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with synthetic demo data (no API key needed)"
    )
    parser.add_argument(
        "--token", type=str, default=None,
        help="Solana token mint address to fetch from Birdeye"
    )
    parser.add_argument(
        "--freq", type=str, default="1min",
        help="Expected bar frequency (default: 1min)"
    )
    parser.add_argument(
        "--gap-method", type=str, default="ffill",
        choices=["ffill", "interpolate"],
        help="Gap fill method (default: ffill)"
    )
    parser.add_argument(
        "--max-gap", type=int, default=5,
        help="Maximum consecutive gap bars to fill (default: 5)"
    )
    parser.add_argument(
        "--normalize", type=str, default="returns",
        choices=["returns", "log_returns", "minmax", "zscore"],
        help="Normalization method (default: returns)"
    )
    parser.add_argument(
        "--resample", type=str, nargs="*", default=["5min", "15min", "1h"],
        help="Target timeframes for resampling (default: 5min 15min 1h)"
    )
    return parser.parse_args()


# ── Main ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = parse_args()

    if args.demo:
        print("Running in DEMO mode with synthetic data...\n")
        raw_df = generate_demo_data()
    elif args.token:
        raw_df = fetch_birdeye_ohlcv(args.token)
    else:
        print("Error: Provide --demo or --token <address>")
        print("Run with --help for usage information.")
        sys.exit(1)

    results = run_pipeline(
        raw_df,
        freq=args.freq,
        gap_method=args.gap_method,
        max_gap=args.max_gap,
        normalize=args.normalize,
        resample_to=args.resample,
    )

    clean_df = results["clean"]
    print(f"\nFinal clean dataset: {len(clean_df)} bars")
    print(f"Columns: {list(clean_df.columns)}")
    print(f"\nFirst 3 bars:")
    print(clean_df[["open", "high", "low", "close", "volume"]].head(3).to_string())
    print(f"\nLast 3 bars:")
    print(clean_df[["open", "high", "low", "close", "volume"]].tail(3).to_string())
