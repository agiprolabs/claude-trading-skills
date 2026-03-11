#!/usr/bin/env python3
"""Multi-source OHLCV merger: align, reconcile, and merge data from two sources.

Demonstrates merging OHLCV data from two different providers (e.g., Birdeye
and DexScreener). Aligns timestamps, resolves price conflicts by preferring
the higher-volume source, and reports discrepancies.

Usage:
    python scripts/merge_sources.py --demo
    python scripts/merge_sources.py --source1 birdeye.csv --source2 dexscreener.csv

Dependencies:
    uv pip install pandas numpy

Environment Variables:
    None required (demo mode uses synthetic data).
"""

import argparse
import sys
from typing import Optional

import numpy as np
import pandas as pd


# ── Configuration ───────────────────────────────────────────────────
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

# Maximum acceptable price discrepancy between sources (percentage)
MAX_PRICE_DISCREPANCY_PCT = 5.0

# Timestamp alignment tolerance
DEFAULT_TOLERANCE = "30s"


# ── Demo Data Generation ───────────────────────────────────────────
def generate_source_pair(
    bars: int = 500,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate two synthetic OHLCV sources with realistic differences.

    Simulates two data providers that mostly agree but differ due to:
    - Different DEX pool weighting (slight price differences)
    - Different volume reporting (can vary 10-30%)
    - Missing bars in each source (different gaps)
    - Slight timestamp offsets

    Args:
        bars: Number of bars per source.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (source1, source2) DataFrames.
    """
    rng = np.random.default_rng(seed)

    # Base price series
    timestamps = pd.date_range(
        start="2025-06-01 00:00:00", periods=bars, freq="1min", tz="UTC"
    )
    returns = rng.normal(0.0001, 0.003, size=bars)
    base_close = 50.0 * np.cumprod(1 + returns)

    # Source 1: "Birdeye-like" — broader coverage, slightly different prices
    spread1 = rng.uniform(0.001, 0.004, size=bars)
    s1_close = base_close * (1 + rng.normal(0, 0.001, size=bars))
    s1_high = s1_close * (1 + spread1)
    s1_low = s1_close * (1 - spread1)
    s1_open = s1_close * (1 + rng.normal(0, 0.0015, size=bars))
    s1_high = np.maximum(s1_high, np.maximum(s1_open, s1_close))
    s1_low = np.minimum(s1_low, np.minimum(s1_open, s1_close))
    s1_volume = rng.exponential(100000, size=bars)

    source1 = pd.DataFrame({
        "open": s1_open, "high": s1_high,
        "low": s1_low, "close": s1_close,
        "volume": s1_volume,
    }, index=timestamps)
    source1.index.name = "timestamp"

    # Source 2: "DexScreener-like" — different pools, volume variation
    price_offset = rng.normal(0, 0.002, size=bars)
    s2_close = base_close * (1 + price_offset)
    spread2 = rng.uniform(0.001, 0.005, size=bars)
    s2_high = s2_close * (1 + spread2)
    s2_low = s2_close * (1 - spread2)
    s2_open = s2_close * (1 + rng.normal(0, 0.002, size=bars))
    s2_high = np.maximum(s2_high, np.maximum(s2_open, s2_close))
    s2_low = np.minimum(s2_low, np.minimum(s2_open, s2_close))
    # Volume differs by 10-30%
    vol_factor = rng.uniform(0.7, 1.3, size=bars)
    s2_volume = s1_volume * vol_factor

    source2 = pd.DataFrame({
        "open": s2_open, "high": s2_high,
        "low": s2_low, "close": s2_close,
        "volume": s2_volume,
    }, index=timestamps)
    source2.index.name = "timestamp"

    # Create different gaps in each source
    # Source 1: missing bars 100-105
    s1_drop = list(range(100, 106))
    source1 = source1.drop(source1.index[s1_drop])

    # Source 2: missing bars 200-210
    s2_drop = list(range(200, 211))
    source2 = source2.drop(source2.index[s2_drop])

    # Add a few large discrepancy bars to source 2 (simulating pool-specific events)
    if len(source2) > 300:
        source2.iloc[300, source2.columns.get_loc("close")] *= 1.08
        source2.iloc[300, source2.columns.get_loc("high")] *= 1.10

    print(f"Generated source 1: {len(source1)} bars")
    print(f"Generated source 2: {len(source2)} bars")

    return source1, source2


# ── Validation ──────────────────────────────────────────────────────
def validate_source(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Validate a single OHLCV source.

    Args:
        df: Raw OHLCV DataFrame.
        name: Source name for logging.

    Returns:
        Validated DataFrame.

    Raises:
        ValueError: If required columns are missing.
    """
    df = df.copy()
    df.columns = df.columns.str.lower().str.strip()

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Source '{name}' missing columns: {missing}")

    # Ensure DatetimeIndex in UTC
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    df = df.sort_index()
    dupes = df.index.duplicated(keep="last")
    if dupes.any():
        print(f"  [{name}] Removed {dupes.sum()} duplicate(s)")
        df = df[~dupes]

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df[["open", "high", "low", "close", "volume"]]


# ── Discrepancy Analysis ──────────────────────────────────────────
def analyze_discrepancies(
    source1: pd.DataFrame,
    source2: pd.DataFrame,
    name1: str = "source1",
    name2: str = "source2",
) -> pd.DataFrame:
    """Analyze price and volume discrepancies between two aligned sources.

    Args:
        source1: First OHLCV source (aligned timestamps).
        source2: Second OHLCV source (aligned timestamps).
        name1: Label for source 1.
        name2: Label for source 2.

    Returns:
        DataFrame with discrepancy metrics per overlapping bar.
    """
    # Find overlapping timestamps
    common_idx = source1.index.intersection(source2.index)
    if len(common_idx) == 0:
        print("  WARNING: No overlapping timestamps between sources")
        return pd.DataFrame()

    s1 = source1.loc[common_idx]
    s2 = source2.loc[common_idx]

    disc = pd.DataFrame(index=common_idx)
    disc.index.name = "timestamp"

    # Price discrepancy (close-to-close, percentage)
    disc["close_pct_diff"] = ((s1["close"] - s2["close"]) / s1["close"] * 100).round(4)
    disc["close_abs_diff"] = (s1["close"] - s2["close"]).abs().round(6)

    # Volume discrepancy (percentage)
    vol_mean = (s1["volume"] + s2["volume"]) / 2
    disc["volume_pct_diff"] = (
        ((s1["volume"] - s2["volume"]) / vol_mean.replace(0, np.nan)) * 100
    ).round(2)

    # High/Low range comparison
    s1_range = (s1["high"] - s1["low"]) / s1["close"] * 100
    s2_range = (s2["high"] - s2["low"]) / s2["close"] * 100
    disc["range_diff_pct"] = (s1_range - s2_range).round(4)

    # Flag large discrepancies
    disc["large_price_disc"] = disc["close_pct_diff"].abs() > MAX_PRICE_DISCREPANCY_PCT
    disc["large_vol_disc"] = disc["volume_pct_diff"].abs() > 50.0

    return disc


def print_discrepancy_report(
    disc: pd.DataFrame,
    name1: str = "source1",
    name2: str = "source2",
) -> None:
    """Print a summary of discrepancies between two sources.

    Args:
        disc: Discrepancy DataFrame from analyze_discrepancies().
        name1: Label for source 1.
        name2: Label for source 2.
    """
    if disc.empty:
        print("  No overlapping data to compare.")
        return

    print("\n" + "=" * 60)
    print(f"  DISCREPANCY REPORT: {name1} vs {name2}")
    print("=" * 60)

    total = len(disc)
    print(f"  Overlapping bars:           {total}")

    # Close price stats
    close_diff = disc["close_pct_diff"]
    print(f"\n  Close Price Discrepancy (%):")
    print(f"    Mean:                     {close_diff.mean():.4f}%")
    print(f"    Std Dev:                  {close_diff.std():.4f}%")
    print(f"    Max Absolute:             {close_diff.abs().max():.4f}%")
    print(f"    Bars > {MAX_PRICE_DISCREPANCY_PCT}%:             "
          f"{disc['large_price_disc'].sum()}")

    # Volume stats
    vol_diff = disc["volume_pct_diff"].dropna()
    print(f"\n  Volume Discrepancy (%):")
    print(f"    Mean:                     {vol_diff.mean():.2f}%")
    print(f"    Std Dev:                  {vol_diff.std():.2f}%")
    print(f"    Bars > 50%:               {disc['large_vol_disc'].sum()}")

    # Show worst discrepancies
    large = disc[disc["large_price_disc"]]
    if not large.empty:
        print(f"\n  Large Price Discrepancies ({len(large)} bars):")
        for ts, row in large.head(5).iterrows():
            print(f"    {ts}: {row['close_pct_diff']:+.4f}% "
                  f"(abs diff: {row['close_abs_diff']:.6f})")
        if len(large) > 5:
            print(f"    ... and {len(large) - 5} more")

    print("=" * 60)


# ── Merging ────────────────────────────────────────────────────────
def merge_ohlcv_sources(
    source1: pd.DataFrame,
    source2: pd.DataFrame,
    tolerance: str = DEFAULT_TOLERANCE,
    prefer: str = "higher_volume",
) -> pd.DataFrame:
    """Merge two OHLCV sources into a single clean dataset.

    Strategy:
    1. Create a union of all timestamps from both sources.
    2. For overlapping timestamps, prefer the source with higher volume.
    3. For non-overlapping timestamps, use whichever source has data.

    Args:
        source1: First OHLCV source (validated).
        source2: Second OHLCV source (validated).
        tolerance: Maximum time difference for timestamp alignment.
        prefer: Conflict resolution — 'higher_volume' or 'source1' or 'source2'.

    Returns:
        Merged OHLCV DataFrame with a 'source' column indicating provenance.
    """
    s1 = source1.copy()
    s2 = source2.copy()

    # Find all unique timestamps
    all_timestamps = s1.index.union(s2.index).sort_values()
    only_in_s1 = s1.index.difference(s2.index)
    only_in_s2 = s2.index.difference(s1.index)
    in_both = s1.index.intersection(s2.index)

    print(f"\n  Timestamps only in source1:  {len(only_in_s1)}")
    print(f"  Timestamps only in source2:  {len(only_in_s2)}")
    print(f"  Timestamps in both:          {len(in_both)}")
    print(f"  Total unique timestamps:     {len(all_timestamps)}")

    # Build merged DataFrame
    ohlcv_cols = ["open", "high", "low", "close", "volume"]
    merged = pd.DataFrame(index=all_timestamps, columns=ohlcv_cols + ["source"])
    merged.index.name = "timestamp"

    # Fill non-overlapping bars
    if len(only_in_s1) > 0:
        for col in ohlcv_cols:
            merged.loc[only_in_s1, col] = s1.loc[only_in_s1, col]
        merged.loc[only_in_s1, "source"] = "source1"

    if len(only_in_s2) > 0:
        for col in ohlcv_cols:
            merged.loc[only_in_s2, col] = s2.loc[only_in_s2, col]
        merged.loc[only_in_s2, "source"] = "source2"

    # Resolve overlapping bars
    if len(in_both) > 0:
        if prefer == "higher_volume":
            use_s2 = s2.loc[in_both, "volume"] > s1.loc[in_both, "volume"]
            use_s1_idx = in_both[~use_s2]
            use_s2_idx = in_both[use_s2]

            for col in ohlcv_cols:
                if len(use_s1_idx) > 0:
                    merged.loc[use_s1_idx, col] = s1.loc[use_s1_idx, col]
                if len(use_s2_idx) > 0:
                    merged.loc[use_s2_idx, col] = s2.loc[use_s2_idx, col]

            merged.loc[use_s1_idx, "source"] = "source1"
            merged.loc[use_s2_idx, "source"] = "source2"

            print(f"  Conflicts resolved: {len(use_s1_idx)} → source1, "
                  f"{len(use_s2_idx)} → source2")

        elif prefer == "source1":
            for col in ohlcv_cols:
                merged.loc[in_both, col] = s1.loc[in_both, col]
            merged.loc[in_both, "source"] = "source1"

        elif prefer == "source2":
            for col in ohlcv_cols:
                merged.loc[in_both, col] = s2.loc[in_both, col]
            merged.loc[in_both, "source"] = "source2"

    # Ensure numeric types
    for col in ohlcv_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    return merged.sort_index()


# ── Quality Report ──────────────────────────────────────────────────
def merged_quality_report(merged: pd.DataFrame) -> None:
    """Print quality summary of the merged dataset.

    Args:
        merged: Merged OHLCV DataFrame with 'source' column.
    """
    print("\n" + "=" * 60)
    print("  MERGED DATASET QUALITY REPORT")
    print("=" * 60)

    total = len(merged)
    print(f"  Total bars:                 {total}")
    print(f"  Date range:                 {merged.index.min()} -> {merged.index.max()}")

    # Source breakdown
    source_counts = merged["source"].value_counts()
    for source, count in source_counts.items():
        pct = count / total * 100
        print(f"  From {source}:              {count} ({pct:.1f}%)")

    # Data quality
    nan_count = merged[["open", "high", "low", "close"]].isna().any(axis=1).sum()
    zero_vol = (merged["volume"] == 0).sum()
    impossible = (merged["high"].astype(float) < merged["low"].astype(float)).sum()

    print(f"\n  Missing prices:             {nan_count}")
    print(f"  Zero volume bars:           {zero_vol}")
    print(f"  Impossible candles:         {impossible}")

    completeness = (1 - merged["close"].isna().mean()) * 100
    print(f"  Completeness:               {completeness:.2f}%")
    print("=" * 60)


# ── File I/O ────────────────────────────────────────────────────────
def load_csv(filepath: str) -> pd.DataFrame:
    """Load OHLCV data from a CSV file.

    Expects columns: timestamp (or as index), open, high, low, close, volume.

    Args:
        filepath: Path to CSV file.

    Returns:
        OHLCV DataFrame with DatetimeIndex.
    """
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.lower().str.strip()

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("date")
        df.index.name = "timestamp"
    else:
        df.index = pd.to_datetime(df.index, utc=True)
        df.index.name = "timestamp"

    return df


# ── CLI ─────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Merge OHLCV data from two sources"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run with synthetic demo data"
    )
    parser.add_argument(
        "--source1", type=str, default=None,
        help="Path to first source CSV file"
    )
    parser.add_argument(
        "--source2", type=str, default=None,
        help="Path to second source CSV file"
    )
    parser.add_argument(
        "--prefer", type=str, default="higher_volume",
        choices=["higher_volume", "source1", "source2"],
        help="Conflict resolution strategy (default: higher_volume)"
    )
    parser.add_argument(
        "--tolerance", type=str, default=DEFAULT_TOLERANCE,
        help=f"Timestamp alignment tolerance (default: {DEFAULT_TOLERANCE})"
    )
    return parser.parse_args()


# ── Main ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = parse_args()

    if args.demo:
        print("Running in DEMO mode with synthetic data...\n")
        s1, s2 = generate_source_pair()
    elif args.source1 and args.source2:
        print(f"Loading source 1: {args.source1}")
        s1 = load_csv(args.source1)
        print(f"Loading source 2: {args.source2}")
        s2 = load_csv(args.source2)
    else:
        print("Error: Provide --demo or --source1 and --source2 CSV paths")
        print("Run with --help for usage information.")
        sys.exit(1)

    # Validate both sources
    print("\nValidating sources...")
    s1 = validate_source(s1, "source1")
    s2 = validate_source(s2, "source2")

    # Analyze discrepancies
    print("\nAnalyzing discrepancies...")
    disc = analyze_discrepancies(s1, s2, "source1", "source2")
    print_discrepancy_report(disc, "source1", "source2")

    # Merge
    print("\nMerging sources...")
    merged = merge_ohlcv_sources(s1, s2, tolerance=args.tolerance, prefer=args.prefer)

    # Report
    merged_quality_report(merged)

    # Preview
    print(f"\nFirst 3 bars of merged data:")
    print(merged[["open", "high", "low", "close", "volume", "source"]].head(3).to_string())
    print(f"\nLast 3 bars of merged data:")
    print(merged[["open", "high", "low", "close", "volume", "source"]].tail(3).to_string())
