---
name: ohlcv-processing
description: Market data preparation including OHLCV resampling, gap handling, anomaly detection, normalization, and multi-source merging
---

# OHLCV Processing — Market Data Preparation

Clean, consistent OHLCV data is the foundation of every trading analysis. Garbage in, garbage out — a single anomalous candle can trigger false signals, corrupt indicator calculations, and produce misleading backtest results. This skill covers the full data preparation pipeline: validation, cleaning, resampling, normalization, and multi-source merging.

**Why this matters**: Crypto OHLCV data is messier than traditional markets. 24/7 trading means no official close, DEX aggregators disagree on prices, low-liquidity tokens produce impossible candles, and API outages create gaps. Every analysis workflow should start with this pipeline.

## Quick Start

### 1. Install Dependencies

```bash
uv pip install pandas numpy httpx
```

### 2. Standard OHLCV DataFrame Format

All processing functions expect this canonical format:

```python
import pandas as pd

# Canonical OHLCV DataFrame
# - DatetimeIndex in UTC
# - Columns: open, high, low, close, volume (lowercase)
# - Sorted ascending by timestamp
# - No duplicate timestamps

df = pd.DataFrame({
    "open": [1.10, 1.12, 1.11],
    "high": [1.15, 1.14, 1.13],
    "low": [1.08, 1.10, 1.09],
    "close": [1.12, 1.11, 1.12],
    "volume": [50000, 48000, 52000],
}, index=pd.to_datetime([
    "2025-01-01 00:00:00",
    "2025-01-01 00:01:00",
    "2025-01-01 00:02:00",
], utc=True))
df.index.name = "timestamp"
```

### 3. Full Processing Pipeline

```python
import pandas as pd
import numpy as np

def process_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Run complete OHLCV processing pipeline."""
    df = standardize_columns(df)
    df = validate_ohlcv(df)
    df = handle_gaps(df, method="ffill")
    df = detect_and_flag_anomalies(df)
    return df
```

## Data Validation

### Column Checks

```python
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lowercase standard."""
    df.columns = df.columns.str.lower().str.strip()
    # Common renames
    rename_map = {"vol": "volume", "v": "volume", "o": "open",
                  "h": "high", "l": "low", "c": "close"}
    df = df.rename(columns=rename_map)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df[["open", "high", "low", "close", "volume"]]
```

### Structural Validation

```python
def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Validate OHLCV structural integrity."""
    # Ensure DatetimeIndex in UTC
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")

    # Sort and deduplicate
    df = df.sort_index()
    dupes = df.index.duplicated(keep="last")
    if dupes.any():
        print(f"Warning: Removed {dupes.sum()} duplicate timestamps")
        df = df[~dupes]

    # Type enforcement
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df
```

### Impossible Candle Detection

```python
def find_impossible_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Find candles that violate OHLC constraints."""
    issues = pd.DataFrame(index=df.index)
    issues["high_lt_low"] = df["high"] < df["low"]
    issues["high_lt_open"] = df["high"] < df["open"]
    issues["high_lt_close"] = df["high"] < df["close"]
    issues["low_gt_open"] = df["low"] > df["open"]
    issues["low_gt_close"] = df["low"] > df["close"]
    issues["negative_price"] = (df[["open", "high", "low", "close"]] < 0).any(axis=1)
    issues["negative_volume"] = df["volume"] < 0
    issues["any_issue"] = issues.any(axis=1)
    return issues[issues["any_issue"]]
```

## Gap Handling

Crypto trades 24/7, but gaps still occur from API outages, low liquidity, or aggregator downtime.

### Detect Gaps

```python
def detect_gaps(df: pd.DataFrame, expected_freq: str = "1min") -> pd.Series:
    """Find missing timestamps based on expected frequency."""
    full_index = pd.date_range(
        start=df.index.min(), end=df.index.max(), freq=expected_freq, tz="UTC"
    )
    missing = full_index.difference(df.index)
    return missing
```

### Fill Gaps

```python
def handle_gaps(
    df: pd.DataFrame,
    freq: str = "1min",
    method: str = "ffill",
    max_gap: int = 5,
) -> pd.DataFrame:
    """Fill gaps in OHLCV data.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.
        freq: Expected bar frequency.
        method: 'ffill' (forward fill) or 'interpolate'.
        max_gap: Maximum consecutive bars to fill. Larger gaps are left as NaN.
    """
    full_index = pd.date_range(
        start=df.index.min(), end=df.index.max(), freq=freq, tz="UTC"
    )
    df = df.reindex(full_index)
    df.index.name = "timestamp"

    # Mark which bars were filled
    df["is_filled"] = df["close"].isna()

    if method == "ffill":
        # Forward fill OHLC (flat candle), zero volume
        df[["open", "high", "low", "close"]] = (
            df[["open", "high", "low", "close"]].ffill(limit=max_gap)
        )
        df["volume"] = df["volume"].fillna(0)
    elif method == "interpolate":
        df[["open", "high", "low", "close"]] = (
            df[["open", "high", "low", "close"]].interpolate(
                method="time", limit=max_gap
            )
        )
        df["volume"] = df["volume"].fillna(0)

    return df
```

## Anomaly Detection

See `references/data_quality.md` for the complete anomaly taxonomy.

### Price Spike Detection

```python
def detect_price_spikes(
    df: pd.DataFrame, window: int = 20, threshold: float = 3.0
) -> pd.Series:
    """Flag bars where return exceeds threshold * rolling std."""
    returns = df["close"].pct_change()
    rolling_std = returns.rolling(window, min_periods=5).std()
    spike = returns.abs() > (threshold * rolling_std)
    return spike.fillna(False)
```

### Zero Volume Detection

```python
def detect_zero_volume(df: pd.DataFrame, min_volume: float = 0) -> pd.Series:
    """Flag bars with zero or below-minimum volume."""
    return df["volume"] <= min_volume
```

### Composite Anomaly Flagging

```python
def flag_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Add anomaly flag columns to DataFrame."""
    df["anomaly_spike"] = detect_price_spikes(df)
    df["anomaly_zero_vol"] = detect_zero_volume(df)
    impossible = find_impossible_candles(df)
    df["anomaly_impossible"] = False
    if not impossible.empty:
        df.loc[impossible.index, "anomaly_impossible"] = True
    df["anomaly_any"] = (
        df["anomaly_spike"] | df["anomaly_zero_vol"] | df["anomaly_impossible"]
    )
    return df
```

## Resampling

See `references/resampling_guide.md` for detailed guidance.

### Standard Resample

```python
OHLCV_RESAMPLE_RULES = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}

def resample_ohlcv(df: pd.DataFrame, target_freq: str) -> pd.DataFrame:
    """Resample OHLCV to a coarser timeframe.

    Args:
        df: OHLCV DataFrame (must be finer than target_freq).
        target_freq: Pandas frequency string ('5min', '15min', '1h', '4h', '1D').

    Returns:
        Resampled OHLCV DataFrame with no NaN rows.
    """
    ohlcv_cols = ["open", "high", "low", "close", "volume"]
    resampled = df[ohlcv_cols].resample(target_freq).agg(OHLCV_RESAMPLE_RULES)
    return resampled.dropna(subset=["close"])
```

### Common Timeframe Ladder

```python
TIMEFRAME_LADDER = ["1min", "5min", "15min", "1h", "4h", "1D"]

def resample_ladder(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Resample 1-minute data to all standard timeframes."""
    results = {"1min": df.copy()}
    for tf in TIMEFRAME_LADDER[1:]:
        results[tf] = resample_ohlcv(df, tf)
    return results
```

### VWAP Calculation

```python
def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute cumulative VWAP over the DataFrame."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    return cum_tp_vol / cum_vol
```

## Normalization

```python
def normalize_prices(
    df: pd.DataFrame, method: str = "returns"
) -> pd.DataFrame:
    """Normalize OHLCV price columns.

    Methods:
        'returns' — Percentage returns (close-to-close).
        'log_returns' — Log returns.
        'minmax' — Min-max scale to [0, 1].
        'zscore' — Z-score normalization.
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
            cmin, cmax = result[col].min(), result[col].max()
            result[f"{col}_norm"] = (result[col] - cmin) / (cmax - cmin)
    elif method == "zscore":
        for col in price_cols:
            result[f"{col}_z"] = (
                (result[col] - result[col].mean()) / result[col].std()
            )
    return result
```

## Multi-Source Merging

When combining data from multiple sources (e.g., Birdeye + DexScreener), timestamps may not align and prices may differ due to different DEX aggregation.

```python
def merge_ohlcv_sources(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    tolerance: str = "30s",
) -> pd.DataFrame:
    """Merge two OHLCV sources, preferring the higher-volume source per bar.

    Args:
        primary: First OHLCV source.
        secondary: Second OHLCV source.
        tolerance: Maximum time difference for alignment.
    """
    merged = pd.merge_asof(
        primary.sort_index(),
        secondary.sort_index(),
        left_index=True, right_index=True,
        tolerance=pd.Timedelta(tolerance),
        suffixes=("_pri", "_sec"),
    )
    # Use higher-volume source per bar
    use_secondary = merged["volume_sec"] > merged["volume_pri"]
    for col in ["open", "high", "low", "close", "volume"]:
        merged[col] = np.where(
            use_secondary, merged[f"{col}_sec"], merged[f"{col}_pri"]
        )
    merged["source"] = np.where(use_secondary, "secondary", "primary")
    return merged[["open", "high", "low", "close", "volume", "source"]]
```

## Timezone Handling

**Standard**: Always store and process in UTC. Convert only for display.

```python
def ensure_utc(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure DatetimeIndex is UTC."""
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    elif str(df.index.tz) != "UTC":
        df.index = df.index.tz_convert("UTC")
    return df
```

## Data Quality Report

```python
def quality_report(df: pd.DataFrame) -> dict:
    """Generate a data quality summary."""
    total = len(df)
    return {
        "total_bars": total,
        "date_range": f"{df.index.min()} → {df.index.max()}",
        "missing_values": int(df[["open", "high", "low", "close"]].isna().sum().sum()),
        "zero_volume_bars": int((df["volume"] == 0).sum()),
        "impossible_candles": int((df["high"] < df["low"]).sum()),
        "duplicate_timestamps": int(df.index.duplicated().sum()),
        "negative_prices": int((df[["open", "high", "low", "close"]] < 0).any(axis=1).sum()),
        "completeness_pct": round((1 - df["close"].isna().mean()) * 100, 2),
    }
```

## Files

### References
- `references/data_quality.md` — Anomaly types, detection methods, correction strategies, crypto-specific data issues
- `references/resampling_guide.md` — Resample rules, timeframe use cases, partial bar handling, VWAP resampling, multi-timeframe alignment

### Scripts
- `scripts/process_ohlcv.py` — Full processing pipeline: validate, clean, resample, normalize with anomaly reporting (run with `--demo` for synthetic data)
- `scripts/merge_sources.py` — Multi-source OHLCV merging with conflict resolution and discrepancy reporting (run with `--demo`)
