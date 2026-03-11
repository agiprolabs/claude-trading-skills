# OHLCV Resampling Guide

## Core Resample Rules

When aggregating fine-grained candles into coarser timeframes, each OHLCV field has a specific aggregation rule:

| Field    | Aggregation | Rationale |
|----------|-------------|-----------|
| `open`   | `first`     | Opening price of the period is the first trade |
| `high`   | `max`       | Highest price across all sub-bars |
| `low`    | `min`       | Lowest price across all sub-bars |
| `close`  | `last`      | Closing price is the last trade |
| `volume` | `sum`       | Total volume traded in the period |

```python
OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}

resampled = df.resample("1h").agg(OHLCV_AGG).dropna(subset=["close"])
```

**Critical**: Always `dropna(subset=["close"])` after resampling. Periods with no data produce all-NaN rows that contaminate downstream calculations.

## Common Timeframes

| Frequency | Pandas Code | Typical Use Case |
|-----------|-------------|-----------------|
| 1 minute  | `1min`      | Scalping, microstructure analysis, raw data |
| 5 minutes | `5min`      | Short-term momentum, intraday patterns |
| 15 minutes| `15min`     | Intraday trading, common chart timeframe |
| 1 hour    | `1h`        | Swing entry/exit, indicator calculation |
| 4 hours   | `4h`        | Swing trading, trend identification |
| 1 day     | `1D`        | Daily analysis, portfolio rebalancing |
| 1 week    | `1W`        | Long-term trend, macro analysis |

### Timeframe Selection Guidelines

- **Indicator calculation**: Use the timeframe the indicator was designed for. RSI-14 on 1-minute bars is very different from RSI-14 on daily bars.
- **Backtesting**: Match the timeframe to your trading frequency. If you trade once per day, use daily bars.
- **Multi-timeframe analysis**: Typically combine 3 timeframes — e.g., 15m (entry timing), 1h (trend direction), 4h (macro context).

## Handling Partial Bars at Boundaries

When resampling, the first and last bars in the dataset may be partial (e.g., resampling to 1h but data starts at 10:23).

### Problem

```python
# Data starts at 10:23, resampling to 1h
# The 10:00-11:00 bar only contains 37 minutes of data
# This partial bar has lower volume and may have misleading OHLC
```

### Solutions

**Drop partial bars** (recommended for backtesting):
```python
def resample_drop_partial(
    df: pd.DataFrame, freq: str
) -> pd.DataFrame:
    """Resample and drop the first/last bar if partial."""
    resampled = df.resample(freq).agg(OHLCV_AGG).dropna(subset=["close"])
    # Count source bars per resampled bar
    bar_counts = df["close"].resample(freq).count()
    expected = bar_counts.median()
    # Drop bars with significantly fewer source bars
    full_bars = bar_counts >= (expected * 0.8)
    return resampled[full_bars]
```

**Keep and flag** (recommended for live data):
```python
bar_counts = df["close"].resample(freq).count()
resampled["bar_count"] = bar_counts
resampled["is_partial"] = bar_counts < bar_counts.median() * 0.8
```

## VWAP-Weighted Resampling

Standard OHLCV resampling treats all sub-bars equally. For a volume-weighted view, compute VWAP alongside standard resampling.

### Session VWAP

```python
def compute_session_vwap(df: pd.DataFrame, session_freq: str = "1D") -> pd.Series:
    """Compute VWAP that resets each session (e.g., daily)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical_price * df["volume"]

    cum_tp_vol = tp_vol.groupby(tp_vol.index.floor(session_freq)).cumsum()
    cum_vol = df["volume"].groupby(df["volume"].index.floor(session_freq)).cumsum()

    return cum_tp_vol / cum_vol
```

### Rolling VWAP

```python
def rolling_vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """Compute rolling VWAP over N bars."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical_price * df["volume"]
    return tp_vol.rolling(window).sum() / df["volume"].rolling(window).sum()
```

## Multi-Timeframe Alignment

When combining indicators from multiple timeframes, alignment is critical. A 4h indicator value must be assigned to the correct 1h or 15m bars.

### Forward-Fill Method (standard)

The higher-timeframe value applies to all lower-timeframe bars within that period, using the *previous* completed higher-timeframe bar (no lookahead).

```python
def align_timeframes(
    base_df: pd.DataFrame,
    higher_tf_series: pd.Series,
) -> pd.Series:
    """Align a higher-timeframe series to a lower-timeframe index.

    Uses forward-fill to avoid lookahead bias: each bar gets the
    most recently completed higher-timeframe value.
    """
    # Shift higher TF by one period to avoid lookahead
    higher_shifted = higher_tf_series.shift(1)
    # Reindex to base timeframe and forward fill
    aligned = higher_shifted.reindex(base_df.index, method="ffill")
    return aligned
```

### Example: 15m Base with 4h Trend

```python
df_15m = resample_ohlcv(df_1m, "15min")
df_4h = resample_ohlcv(df_1m, "4h")

# Compute 4h SMA
sma_4h = df_4h["close"].rolling(20).mean()

# Align to 15m without lookahead
df_15m["sma_4h"] = align_timeframes(df_15m, sma_4h)
```

## Resampling Pitfalls

### 1. Lookahead Bias
Using the current (incomplete) higher-timeframe bar for decisions. Always shift by one period or use only completed bars.

### 2. Volume Inflation
When resampling up (1m → 1h), volume sums correctly. When resampling down (1h → 1m), distributing volume across sub-bars is lossy and unreliable. Only resample from fine to coarse.

### 3. Timezone Mismatch
If your data is in UTC but you resample with `1D`, the daily boundary is UTC midnight. If your strategy uses US market hours, set `offset` in the resample call:
```python
# US Eastern daily bars (market close = 20:00 UTC in winter)
df.resample("1D", offset="20h").agg(OHLCV_AGG)
```

### 4. Missing Sub-Bars
If 30 out of 60 expected 1-minute bars are missing in an hour, the 1h candle is computed from only half the data. The `high` and `low` may understate the true range. Track `bar_count` to assess quality.

### 5. Pandas Frequency Aliases
Common aliases and their meaning:
- `1min` or `T` — 1 minute
- `5min` or `5T` — 5 minutes
- `1h` or `H` — 1 hour
- `4h` or `4H` — 4 hours
- `1D` or `D` — 1 calendar day
- `1W` or `W` — 1 week (ends Sunday by default)
- `1MS` — 1 month start
- `1ME` — 1 month end

**Note**: Pandas 2.x deprecated `H` in favor of `h`, and `T` in favor of `min`. Use the full-word forms for forward compatibility.

## Resampling with Additional Columns

If your DataFrame has extra columns (e.g., `vwap`, `trade_count`, `is_filled`), define aggregation rules for each:

```python
EXTENDED_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "trade_count": "sum",
    "vwap": "last",          # Or recompute from resampled data
    "is_filled": "any",      # True if any sub-bar was filled
}
```
