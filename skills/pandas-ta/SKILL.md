---
name: pandas-ta
description: Technical analysis with 130+ indicators using pandas-ta for crypto market data
---

# pandas-ta — Technical Analysis for Crypto Markets

pandas-ta is a Python library that extends pandas DataFrames with 130+ technical analysis indicators accessible via `df.ta`. It covers trend, momentum, volatility, volume, and overlap indicator categories — all callable with a single method on any OHLCV DataFrame.

## Installation

```bash
uv pip install pandas-ta pandas httpx
```

## Quick Start

```python
import pandas as pd
import pandas_ta as ta

# Assume df is a DataFrame with columns: open, high, low, close, volume
# All lowercase column names required

# Single indicator
df["rsi"] = df.ta.rsi(length=14)
df["atr"] = df.ta.atr(length=14)

# Multiple indicators via strategy
df.ta.strategy(ta.Strategy(
    name="Quick Check",
    ta=[
        {"kind": "rsi", "length": 14},
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "bbands", "length": 20, "std": 2.0},
    ]
))
```

## OHLCV DataFrame Format

pandas-ta expects a DataFrame with lowercase column names:

```python
import pandas as pd

df = pd.DataFrame({
    "open": [...],
    "high": [...],
    "low": [...],
    "close": [...],
    "volume": [...]
}, index=pd.DatetimeIndex([...]))
```

**Important**: Set the index to a `DatetimeIndex` for time-aware indicators like VWAP. Column names must be lowercase (`close`, not `Close`).

### Handling Missing Data

```python
# Drop rows with NaN in OHLCV columns
df = df.dropna(subset=["open", "high", "low", "close", "volume"])

# Forward-fill small gaps (1-2 bars max)
df = df.ffill(limit=2)

# Verify no zero-volume bars for volume indicators
df = df[df["volume"] > 0]
```

## Core Indicator Categories

### Trend Indicators

Identify market direction and trend strength.

| Indicator | Call | Key Signal |
|-----------|------|------------|
| SMA | `df.ta.sma(length=20)` | Price above = bullish |
| EMA | `df.ta.ema(length=20)` | Faster than SMA, less lag |
| SuperTrend | `df.ta.supertrend(length=10, multiplier=3)` | Direction column: 1=bull, -1=bear |
| Ichimoku | `df.ta.ichimoku()` | Returns tuple of (span, lines) DataFrames |
| VWMA | `df.ta.vwma(length=20)` | Volume-weighted price trend |
| HMA | `df.ta.hma(length=20)` | Minimal lag, smooth trend |
| ADX | `df.ta.adx(length=14)` | >25 = trending, <20 = ranging |

### Momentum Indicators

Measure speed and magnitude of price changes.

| Indicator | Call | Key Signal |
|-----------|------|------------|
| RSI | `df.ta.rsi(length=14)` | >70 overbought, <30 oversold |
| MACD | `df.ta.macd(fast=12, slow=26, signal=9)` | Histogram crossover = entry |
| Stochastic | `df.ta.stoch(k=14, d=3, smooth_k=3)` | >80 overbought, <20 oversold |
| CCI | `df.ta.cci(length=20)` | >100 overbought, <-100 oversold |
| Williams %R | `df.ta.willr(length=14)` | >-20 overbought, <-80 oversold |
| ROC | `df.ta.roc(length=10)` | Positive = upward momentum |
| MFI | `df.ta.mfi(length=14)` | Money flow version of RSI |

### Volatility Indicators

Measure price dispersion and expected range.

| Indicator | Call | Key Signal |
|-----------|------|------------|
| Bollinger Bands | `df.ta.bbands(length=20, std=2)` | Squeeze = breakout pending |
| ATR | `df.ta.atr(length=14)` | Position sizing, stop placement |
| Keltner Channels | `df.ta.kc(length=20, scalar=1.5)` | BB inside KC = squeeze |
| Donchian Channels | `df.ta.donchian(lower_length=20, upper_length=20)` | Breakout detection |

### Volume Indicators

Confirm price moves with volume analysis.

| Indicator | Call | Key Signal |
|-----------|------|------------|
| OBV | `df.ta.obv()` | Divergence from price = reversal |
| VWAP | `df.ta.vwap()` | Intraday fair value (needs DatetimeIndex) |
| CMF | `df.ta.cmf(length=20)` | >0 accumulation, <0 distribution |
| AD | `df.ta.ad()` | Accumulation/Distribution line |

## Strategy Class

Run multiple indicators in a single call using `ta.Strategy`:

```python
import pandas_ta as ta

# Built-in "All" strategy runs every indicator
df.ta.strategy(ta.AllStrategy)

# Custom strategy
my_strategy = ta.Strategy(
    name="Crypto Scalp",
    description="Fast indicators for crypto scalping",
    ta=[
        {"kind": "ema", "length": 9},
        {"kind": "ema", "length": 21},
        {"kind": "rsi", "length": 7},
        {"kind": "stoch", "k": 5, "d": 3, "smooth_k": 3},
        {"kind": "atr", "length": 7},
        {"kind": "bbands", "length": 10, "std": 2.0},
        {"kind": "obv"},
    ]
)
df.ta.strategy(my_strategy)
```

### Named Strategy Patterns

```python
# Trend following
trend_strategy = ta.Strategy(
    name="Trend",
    ta=[
        {"kind": "ema", "length": 20},
        {"kind": "ema", "length": 50},
        {"kind": "adx", "length": 14},
        {"kind": "supertrend", "length": 10, "multiplier": 3},
        {"kind": "atr", "length": 14},
    ]
)

# Mean reversion
reversion_strategy = ta.Strategy(
    name="Mean Reversion",
    ta=[
        {"kind": "rsi", "length": 14},
        {"kind": "bbands", "length": 20, "std": 2.0},
        {"kind": "stoch", "k": 14, "d": 3, "smooth_k": 3},
        {"kind": "cci", "length": 20},
    ]
)

# Momentum
momentum_strategy = ta.Strategy(
    name="Momentum",
    ta=[
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "rsi", "length": 14},
        {"kind": "obv"},
        {"kind": "roc", "length": 10},
        {"kind": "mfi", "length": 14},
    ]
)
```

## Crypto-Specific Considerations

### 24/7 Markets
- No session gaps — indicators that rely on open/close of sessions behave differently
- VWAP resets at midnight UTC by default; consider anchored VWAP for custom periods
- Weekend data is continuous — no Monday gap effects

### High Volatility Adjustments
- **Bollinger Bands**: Use 2.5-3x standard deviation instead of the default 2x
- **RSI periods**: Shorter periods (7-10) capture faster crypto cycles
- **ATR**: Use for dynamic stop-losses; crypto ATR is typically 2-5x equity ATR
- **SuperTrend multiplier**: 3-4x for crypto vs 2-3x for equities

### Low-Cap Token Considerations
- Volume indicators (OBV, CMF, MFI) are unreliable with thin order books
- Prefer price-based indicators (RSI, BBands, SuperTrend) for low-liquidity tokens
- ATR-based position sizing is critical — wide spreads amplify losses
- Wash trading inflates volume; cross-reference with on-chain data

### Timeframe Selection
| Timeframe | Use Case | Recommended Indicators |
|-----------|----------|----------------------|
| 1m-5m | Scalping, PumpFun | RSI(5-7), EMA(5,13), ATR(5) |
| 15m-1h | Day trading | MACD, RSI(14), BBands, EMA(20,50) |
| 4h-1d | Swing trading | SuperTrend, ADX, EMA(50,200) |
| 1w | Position trading | SMA(20,50), RSI(14), monthly VWAP |

## Common Indicator Combinations

### Trend Following
```python
# EMA crossover + ADX confirmation + SuperTrend direction
ema_fast = df.ta.ema(length=20)
ema_slow = df.ta.ema(length=50)
adx_df = df.ta.adx(length=14)
st_df = df.ta.supertrend(length=10, multiplier=3)

bullish = (
    (ema_fast > ema_slow) &
    (adx_df["ADX_14"] > 25) &
    (st_df["SUPERTd_10_3.0"] == 1)
)
```

### Mean Reversion
```python
# RSI oversold + price at lower BB + Stochastic oversold
rsi = df.ta.rsi(length=14)
bb = df.ta.bbands(length=20, std=2.5)
stoch = df.ta.stoch(k=14, d=3, smooth_k=3)

buy_signal = (
    (rsi < 30) &
    (df["close"] <= bb["BBL_20_2.5"]) &
    (stoch["STOCHk_14_3_3"] < 20)
)
```

### Momentum Confirmation
```python
# MACD histogram positive + RSI above 50 + OBV rising
macd = df.ta.macd(fast=12, slow=26, signal=9)
rsi = df.ta.rsi(length=14)
obv = df.ta.obv()

momentum_bull = (
    (macd["MACDh_12_26_9"] > 0) &
    (rsi > 50) &
    (obv > obv.shift(1))
)
```

### Volatility Breakout (BB Squeeze)
```python
# Bollinger Band width contracting + volume spike
bb = df.ta.bbands(length=20, std=2.0)
atr = df.ta.atr(length=14)
vol_sma = df["volume"].rolling(20).mean()

bb_width = (bb["BBU_20_2.0"] - bb["BBL_20_2.0"]) / bb["BBM_20_2.0"]
squeeze = bb_width < bb_width.rolling(120).quantile(0.1)
vol_spike = df["volume"] > (vol_sma * 2.0)

breakout_setup = squeeze & vol_spike
```

## Integration with Other Skills

- **birdeye-api**: Fetch OHLCV data → feed into pandas-ta for indicator computation
- **vectorbt**: Use pandas-ta indicators as signal inputs for backtesting
- **trading-visualization**: Plot indicator overlays on price charts
- **slippage-modeling**: Combine ATR with slippage estimates for realistic execution modeling
- **position-sizing**: Use ATR-based sizing from pandas-ta output

## Files

### References
- `references/indicator_guide.md` — Top 20 crypto indicators with syntax, parameters, and interpretation
- `references/strategy_patterns.md` — Pre-built strategy combinations for scalping, day trading, and swing trading
- `references/common_pitfalls.md` — Common mistakes with technical indicators in crypto markets

### Scripts
- `scripts/compute_indicators.py` — Fetch OHLCV data and compute standard indicator set with signal summary
- `scripts/multi_indicator_scan.py` — Run multiple strategy profiles and score current signal alignment
