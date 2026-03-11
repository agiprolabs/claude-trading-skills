# OHLCV Data Quality — Anomalies, Detection & Correction

## Why Data Quality Matters

A single bad candle can corrupt rolling indicators for dozens of bars downstream. A 100x price spike that lasts one bar will blow out Bollinger Bands, RSI, and any volatility estimate for the entire lookback window. In backtesting, bad data produces phantom signals and unrealistic P&L. Always validate before analysis.

## Anomaly Taxonomy

### 1. Price Spikes

**What**: A single bar shows a return exceeding 3+ standard deviations from the rolling mean, then immediately reverts.

**Causes**: DEX aggregator picking up a thin-liquidity pool, API returning a stale/wrong price, flash loan manipulation.

**Detection**:
```python
returns = df["close"].pct_change()
rolling_std = returns.rolling(20, min_periods=5).std()
spikes = returns.abs() > (3.0 * rolling_std)
```

**Correction strategies**:
- **Flag only**: Add `anomaly_spike=True` column, let downstream code decide
- **Interpolate**: Replace OHLC with linear interpolation from neighbors
- **Clip**: Cap returns at ±N standard deviations
- **Remove**: Drop the bar entirely (shifts timestamps — use with caution)

**Recommendation**: Flag and interpolate for analysis. Remove for backtesting only if the spike is confirmed as data error (not a real market event).

### 2. Zero Volume Bars

**What**: Bars where `volume == 0` despite having price data.

**Causes**: Low-liquidity token with no trades in that interval, API returning placeholder candles, data source gap-filling with zero volume.

**Detection**:
```python
zero_vol = df["volume"] == 0
```

**Correction strategies**:
- **Keep**: Zero volume is informative — it means no trading happened
- **Forward fill volume**: Misleading, avoid
- **Mark**: Add `is_zero_volume=True` flag for filters

**Recommendation**: Keep zero-volume bars but flag them. Exclude from volume-dependent indicators (VWAP, OBV, volume profile).

### 3. Impossible Candles (high < low)

**What**: A bar where `high < low`, `high < open`, `high < close`, `low > open`, or `low > close`.

**Causes**: Data source bug, incorrect aggregation, API returning fields in wrong order.

**Detection**:
```python
impossible = (
    (df["high"] < df["low"]) |
    (df["high"] < df["open"]) |
    (df["high"] < df["close"]) |
    (df["low"] > df["open"]) |
    (df["low"] > df["close"])
)
```

**Correction strategies**:
- **Recalculate**: Set `high = max(open, high, low, close)` and `low = min(open, high, low, close)`
- **Remove**: Drop the bar if correction is unreliable

**Recommendation**: Recalculate high/low from the four price fields. This fixes most cases caused by field ordering bugs.

### 4. Negative Prices

**What**: Any price field is negative.

**Causes**: Data corruption, integer overflow in source data, bad type conversion.

**Detection**:
```python
negative = (df[["open", "high", "low", "close"]] < 0).any(axis=1)
```

**Correction**: Remove these bars. Negative prices are never valid for spot crypto.

### 5. Duplicate Timestamps

**What**: Two or more bars share the same timestamp.

**Causes**: API pagination overlap, multiple data source concatenation without dedup, timezone conversion errors creating apparent duplicates.

**Detection**:
```python
dupes = df.index.duplicated(keep=False)  # Marks all duplicates
```

**Correction strategies**:
- **Keep last**: Most recent data is usually more accurate (`keep="last"`)
- **Keep highest volume**: The bar with more volume likely represents more trades
- **Average**: Mean of duplicate bars (only for close-valued duplicates)

**Recommendation**: Keep the bar with highest volume if values differ significantly. Keep last if values are similar.

### 6. Stale Data (Flat Lines)

**What**: Multiple consecutive bars with identical OHLC values (open == high == low == close).

**Causes**: No trades occurred, data source repeating last known price, API caching.

**Detection**:
```python
flat = (
    (df["open"] == df["high"]) &
    (df["high"] == df["low"]) &
    (df["low"] == df["close"])
)
consecutive_flat = flat.rolling(5).sum() >= 5
```

**Correction**: Flag but keep. Consecutive flat bars in low-liquidity tokens are real — they indicate no trading activity.

### 7. Extreme Spread Candles

**What**: `(high - low) / close` exceeds a threshold (e.g., > 50% for a single bar).

**Causes**: Real flash crash/pump, aggregation across pools with very different prices, data error.

**Detection**:
```python
spread = (df["high"] - df["low"]) / df["close"]
extreme = spread > 0.5  # 50% spread in one bar
```

**Correction**: Verify against on-chain data. If confirmed as real, keep. If data error, interpolate.

## Validation Pipeline

Run these checks in order before any analysis:

```python
def validate_pipeline(df: pd.DataFrame) -> dict:
    """Run all validation checks and return a report."""
    report = {}
    report["total_bars"] = len(df)
    report["duplicate_timestamps"] = int(df.index.duplicated().sum())
    report["negative_prices"] = int(
        (df[["open", "high", "low", "close"]] < 0).any(axis=1).sum()
    )
    report["impossible_candles"] = int((df["high"] < df["low"]).sum())
    report["zero_volume_bars"] = int((df["volume"] == 0).sum())

    returns = df["close"].pct_change()
    rolling_std = returns.rolling(20, min_periods=5).std()
    report["price_spikes_3sigma"] = int(
        (returns.abs() > 3 * rolling_std).sum()
    )

    flat = (df["open"] == df["high"]) & (df["high"] == df["low"]) & (df["low"] == df["close"])
    report["flat_candles"] = int(flat.sum())

    report["nan_values"] = int(
        df[["open", "high", "low", "close", "volume"]].isna().sum().sum()
    )
    return report
```

## Crypto-Specific Considerations

### 24/7 Trading
- There is no official daily close. "Daily" candles use UTC midnight by convention.
- No weekends or holidays — gaps are always data issues, never market closures.
- Expect higher volume during US/EU trading hours even for crypto.

### No Single Source of Truth
- Unlike equities with a consolidated tape, crypto prices vary by DEX, aggregator, and pool.
- Two sources can legitimately disagree by 0.1–2% on the same timestamp.
- Volume figures are especially unreliable — wash trading inflates DEX volumes.

### Exchange/Aggregator Differences
- Birdeye aggregates across all Solana DEXes — broadest coverage.
- DexScreener may weight pools differently.
- On-chain data (Helius/Solana RPC) is ground truth but requires reconstruction.

### Token Lifecycle Issues
- New tokens may have minutes of data, then nothing.
- Rug pulls create a final catastrophic candle that is real data, not an anomaly.
- Token migrations (v1 → v2) create apparent price discontinuities.

### Precision
- Solana tokens can have 0–9 decimals. A token with 0 decimals has integer-only prices.
- Very low-priced tokens (< $0.000001) need float64 precision at minimum.
- Always use `float64` for price columns, never `float32`.
