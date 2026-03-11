# pandas-ta — Common Pitfalls in Crypto Technical Analysis

Mistakes that cause false signals, incorrect backtests, and real losses when using technical indicators on crypto market data.

## 1. NaN Values at Start of Series

**Problem**: Every indicator produces NaN for its warmup period. RSI(14) has 14+ NaN bars. MACD(12,26,9) has 33+ NaN bars. Treating NaN as 0 or ignoring it generates false signals.

**Fix**:
```python
# Always check for sufficient data
min_bars = 200  # Enough warmup for most indicators
if len(df) < min_bars:
    raise ValueError(f"Need {min_bars} bars, got {len(df)}")

# Drop NaN rows before signal evaluation
signals = signals.dropna()

# Or check explicitly
rsi = df.ta.rsi(length=14)
valid_rsi = rsi.iloc[14:]  # Skip warmup period
```

**Rule of thumb**: Need at least 3x the longest indicator period in your dataset.

## 2. Lookahead Bias

**Problem**: Using future data to make current decisions. Common in backtesting when indicators or signals reference data not yet available at decision time.

**Examples**:
- Using `df["close"]` for the current bar before the bar closes
- Centering a moving average (pandas default for some rolling operations)
- Using `BBP` (Bollinger Band percent) calculated on the full dataset

**Fix**:
```python
# Shift signals by 1 bar — act on NEXT bar after signal
df["signal"] = (df["RSI_14"] < 30).astype(int)
df["entry"] = df["signal"].shift(1)  # Enter on next bar

# In backtesting, always use .shift(1) for signal-to-execution
# You see the signal at bar N close, you act at bar N+1 open
```

## 3. Overfitting with Too Many Indicators

**Problem**: Combining 10+ indicators to find "perfect" entry conditions produces a system that worked historically but fails live. More indicators = more curve fitting.

**Symptoms**:
- Backtest win rate > 80% but live trading loses money
- Strategy only works on one specific token in one specific time period
- Adding or removing one indicator drastically changes results

**Fix**:
- Use 3-5 indicators maximum per strategy
- Each indicator should measure something different (trend + momentum + volatility, not RSI + Stochastic + Williams %R which all measure momentum)
- Validate on out-of-sample data from a different time period
- Use walk-forward analysis, not single backtest optimization

## 4. Parameter Optimization Trap

**Problem**: Optimizing indicator parameters on historical data finds the best past parameters, not the best future parameters. RSI(13) beating RSI(14) on historical data is noise, not signal.

**Fix**:
```python
# Test a small range of standard parameters, not a wide sweep
# Standard RSI: 7, 9, 14, 21 — not RSI(1) through RSI(50)
standard_params = {
    "rsi": [7, 9, 14, 21],
    "ema_fast": [9, 12, 20],
    "ema_slow": [21, 26, 50],
    "bb_std": [2.0, 2.5, 3.0],
}

# If results are very sensitive to parameter choice, the edge is fragile
# Robust strategies work across a range of parameters
```

## 5. Volume Indicator Reliability on Low-Cap Tokens

**Problem**: OBV, CMF, MFI, and VWAP assume volume data is accurate. On Solana memecoins and low-cap tokens, volume is often unreliable due to:
- Wash trading (bots trading with themselves)
- Concentrated liquidity (one market maker = most volume)
- Cross-DEX arbitrage inflating volume
- Different DEX APIs reporting different volume

**Fix**:
- Use price-based indicators (RSI, BBands, SuperTrend, EMAs) as primary
- Use volume indicators only for confirmation, not as primary signals
- Cross-reference volume with on-chain transaction count
- For tokens with < $100K daily volume, ignore volume indicators entirely

## 6. Repainting Indicators

**Problem**: Some indicators change their historical values as new data arrives. The signal that appeared on bar N may look different when viewed from bar N+10.

**Common repainting indicators**:
- Zigzag (by definition)
- Pivot points (require future data to confirm)
- Some implementations of SuperTrend (confirm pandas-ta uses non-repainting version)

**Fix**:
- Test by comparing indicator values computed on data ending at bar N vs. data ending at bar N+100
- If historical values change, the indicator repaints
- pandas-ta's standard indicators (RSI, MACD, BBands, EMA) do NOT repaint

```python
# Verification: compute indicator twice, compare
rsi_full = df.ta.rsi(length=14)
rsi_partial = df.iloc[:100].ta.rsi(length=14)

# These should be identical for overlapping bars
assert rsi_full.iloc[:100].equals(rsi_partial), "Indicator repaints!"
```

## 7. Timeframe Mismatch

**Problem**: Indicator parameters calibrated for daily charts produce garbage on 1-minute charts. RSI(14) on 1d = 14 trading days. RSI(14) on 1m = 14 minutes. They measure completely different things.

**Fix**:
- Scale parameters to match the timeframe's noise level
- 1m charts: shorter periods (5-9), wider bands (3x std)
- 1d charts: standard periods (14-21), standard bands (2-2.5x std)
- See the parameter table in `indicator_guide.md` for recommended values

## 8. Missing Data and Gaps

**Problem**: Gaps in OHLCV data (missing bars) cause indicator distortion. A 1h chart missing 3 bars has a gap that makes EMAs jump.

**Common causes in crypto**:
- API rate limits causing missed fetches
- DEX downtime or low liquidity periods with no trades
- Data provider outages

**Fix**:
```python
# Detect gaps
expected_freq = pd.Timedelta("1h")  # Adjust for your timeframe
time_diffs = df.index.to_series().diff()
gaps = time_diffs[time_diffs > expected_freq * 1.5]
if len(gaps) > 0:
    print(f"Warning: {len(gaps)} gaps detected")
    print(gaps)

# Option 1: Forward-fill small gaps (1-2 bars)
df = df.asfreq(expected_freq, method="ffill")

# Option 2: Split into continuous segments
segments = []
gap_indices = gaps.index.tolist()
# Process each segment separately

# Option 3: Recompute indicators after gap
# Drop all indicator columns, recompute from scratch
```

## 9. VWAP Misuse in 24/7 Markets

**Problem**: VWAP is designed to reset at market open. Crypto has no market open. pandas-ta resets VWAP at midnight UTC, which is arbitrary for most traders.

**Fix**:
- Use VWAP for intraday reference only, not as a multi-day indicator
- Consider anchored VWAP from significant swing highs/lows instead
- VWMA (volume-weighted moving average) is often more useful than VWAP for crypto

```python
# VWAP requires DatetimeIndex
df.index = pd.DatetimeIndex(df.index)
vwap = df.ta.vwap()  # Resets daily at midnight UTC

# For multi-day analysis, use VWMA instead
vwma = df.ta.vwma(length=20)
```

## 10. Treating Indicators as Absolute Truth

**Problem**: RSI < 30 does not mean "buy". It means price has dropped significantly relative to recent history. In a crash, RSI can stay below 30 for weeks while price drops another 80%.

**Key principles**:
- Indicators are probability modifiers, not binary signals
- Combine indicator signals with market context (regime, trend, volume)
- No single indicator works in all market conditions
- Mean reversion indicators fail in trending markets; trend indicators fail in ranges
- Always have a stop-loss independent of indicator readings

## 11. Column Name Confusion

**Problem**: pandas-ta uses specific column naming conventions. Getting the name wrong returns KeyError or operates on the wrong column.

**Fix**:
```python
# After computing, inspect column names
df.ta.macd(append=True)
print([c for c in df.columns if "MACD" in c])
# Output: ['MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9']

# Common pattern: {INDICATOR}_{param1}_{param2}
# BBands: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0, BBB_20_2.0, BBP_20_2.0
# Stoch: STOCHk_14_3_3, STOCHd_14_3_3
# SuperTrend: SUPERT_10_3.0, SUPERTd_10_3.0, SUPERTl_10_3.0, SUPERTs_10_3.0
```

## 12. Ignoring Indicator Divergence

**Problem**: Price making new highs while RSI makes lower highs (bearish divergence) is one of the strongest signals in TA — but many traders ignore it because the trend "looks strong."

**Fix**:
```python
# Simple divergence detection
def detect_divergence(price: pd.Series, indicator: pd.Series, lookback: int = 20) -> str:
    """Detect bullish or bearish divergence."""
    price_higher = price.iloc[-1] > price.iloc[-lookback:].max() * 0.98
    ind_lower = indicator.iloc[-1] < indicator.iloc[-lookback:].max() * 0.95

    if price_higher and ind_lower:
        return "bearish_divergence"

    price_lower = price.iloc[-1] < price.iloc[-lookback:].min() * 1.02
    ind_higher = indicator.iloc[-1] > indicator.iloc[-lookback:].min() * 1.05

    if price_lower and ind_higher:
        return "bullish_divergence"

    return "none"
```

## Summary Checklist

Before using any indicator-based strategy:

- [ ] Dataset has 3x the longest indicator period in bars
- [ ] NaN values from warmup are excluded from signals
- [ ] Signals are shifted by 1 bar (no lookahead)
- [ ] Using 3-5 indicators max, each measuring different things
- [ ] Parameters are standard values, not over-optimized
- [ ] Volume indicators only used on tokens with reliable volume
- [ ] Tested on out-of-sample data from a different time period
- [ ] Gap detection and handling is implemented
- [ ] Stop-losses are defined independently of indicators
- [ ] Column names are verified after computation
