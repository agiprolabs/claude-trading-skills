---
name: ta-lib
description: C-optimized technical analysis with 150+ functions and 61 candlestick pattern recognition functions via TA-Lib
---

# ta-lib — C-Optimized Technical Analysis

TA-Lib (Technical Analysis Library) is a C library with a Python wrapper providing 150+ technical analysis functions and 61 candlestick pattern recognition functions. It is the industry standard for performance-critical indicator computation, used in production trading systems where pandas-ta or pure-Python alternatives are too slow.

## What TA-Lib Is

TA-Lib was originally written in C for financial market data analysis. The Python wrapper (`TA-Lib` on PyPI, imported as `talib`) provides:

- **150+ indicator functions** across overlap, momentum, volume, volatility, cycle, and math categories
- **61 candlestick pattern recognition functions** — the most comprehensive pattern library available
- **C-speed computation** — 10-100x faster than pure-Python equivalents on large datasets
- **Two APIs**: a function API (pass arrays directly) and an abstract API (pass dict of arrays)
- **NumPy native** — all inputs and outputs are NumPy arrays

## Installation

TA-Lib requires the underlying C library to be installed first:

```bash
# macOS
brew install ta-lib
uv pip install TA-Lib numpy pandas

# Ubuntu/Debian
sudo apt-get install -y ta-lib
uv pip install TA-Lib numpy pandas

# From source (any platform)
wget https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz
tar -xzf ta-lib-0.6.4-src.tar.gz
cd ta-lib-0.6.4
./configure --prefix=/usr/local
make && sudo make install
uv pip install TA-Lib numpy pandas
```

If the C library is not installed, `import talib` will fail with an `ImportError`. The scripts in this skill include fallback logic for environments without TA-Lib installed.

## When to Use TA-Lib vs pandas-ta

| Criterion | TA-Lib | pandas-ta |
|---|---|---|
| Speed | C-optimized, 10-100x faster | Pure Python, slower on large data |
| Candlestick patterns | 61 built-in patterns | Limited pattern support |
| Installation | Requires C library | `pip install` only |
| API style | NumPy arrays | DataFrame `.ta` accessor |
| Indicator count | 150+ | 130+ |
| Streaming | Single-value update possible | Recompute entire series |
| Dependencies | C lib + numpy | pandas only |

**Use TA-Lib when:**
- Processing millions of bars or running backtests at scale
- You need candlestick pattern recognition (TA-Lib is unmatched here)
- You are building a production pipeline where latency matters
- You need cycle indicators (Hilbert Transform family)

**Use pandas-ta when:**
- You want DataFrame-native convenience
- Installation simplicity matters (no C dependency)
- You need indicators not in TA-Lib (pandas-ta has some extras)

## Quick Start

```python
import numpy as np
import talib

# Create sample data
close = np.random.randn(100).cumsum() + 50
high = close + np.abs(np.random.randn(100))
low = close - np.abs(np.random.randn(100))
open_ = close + np.random.randn(100) * 0.5
volume = np.random.randint(1000, 10000, 100).astype(float)

# Function API — pass arrays directly
rsi = talib.RSI(close, timeperiod=14)
macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
atr = talib.ATR(high, low, close, timeperiod=14)

# Candlestick patterns — return +100 (bullish), -100 (bearish), or 0
doji = talib.CDLDOJI(open_, high, low, close)
hammer = talib.CDLHAMMER(open_, high, low, close)
engulfing = talib.CDLENGULFING(open_, high, low, close)
```

## Function API vs Abstract API

### Function API (Recommended)

Call functions directly with NumPy arrays:

```python
import talib

rsi = talib.RSI(close, timeperiod=14)
sma = talib.SMA(close, timeperiod=20)
upper, mid, lower = talib.BBANDS(close)
```

### Abstract API

Pass a dictionary of arrays and get results by name:

```python
from talib import abstract

inputs = {"open": open_, "high": high, "low": low, "close": close, "volume": volume}

# Call by function name
rsi = abstract.RSI(inputs, timeperiod=14)
macd = abstract.MACD(inputs)  # returns (macd, signal, hist)
```

The abstract API is useful for dynamic indicator selection (e.g., looping over a list of indicator names).

## Function Groups

TA-Lib organizes functions into these groups:

### Overlap Studies
Moving averages and envelope indicators that overlay price charts.

```python
sma = talib.SMA(close, timeperiod=20)
ema = talib.EMA(close, timeperiod=12)
upper, mid, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
sar = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
mama, fama = talib.MAMA(close, fastlimit=0.5, slowlimit=0.05)
```

### Momentum Indicators
Oscillators and trend-strength measures.

```python
rsi = talib.RSI(close, timeperiod=14)
macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
slowk, slowd = talib.STOCH(high, low, close)
cci = talib.CCI(high, low, close, timeperiod=14)
willr = talib.WILLR(high, low, close, timeperiod=14)
adx = talib.ADX(high, low, close, timeperiod=14)
mfi = talib.MFI(high, low, close, volume, timeperiod=14)
```

### Volume Indicators
Volume-based analysis functions.

```python
obv = talib.OBV(close, volume)
ad = talib.AD(high, low, close, volume)
adosc = talib.ADOSC(high, low, close, volume, fastperiod=3, slowperiod=10)
```

### Volatility Indicators
Measures of price variability.

```python
atr = talib.ATR(high, low, close, timeperiod=14)
natr = talib.NATR(high, low, close, timeperiod=14)
trange = talib.TRANGE(high, low, close)
```

### Pattern Recognition (Candlestick)
61 functions that detect candlestick patterns. All return integer arrays:
- `+100` = bullish pattern detected
- `-100` = bearish pattern detected
- `0` = no pattern

```python
# Single patterns
doji = talib.CDLDOJI(open_, high, low, close)
hammer = talib.CDLHAMMER(open_, high, low, close)
engulfing = talib.CDLENGULFING(open_, high, low, close)

# Scan all 61 patterns at once
candle_names = talib.get_function_groups()["Pattern Recognition"]
for name in candle_names:
    func = getattr(talib, name)
    result = func(open_, high, low, close)
    hits = np.nonzero(result)[0]
    if len(hits) > 0:
        print(f"{name}: {len(hits)} detections")
```

See `references/candlestick_patterns.md` for the full list of 61 patterns with reliability ratings and crypto relevance.

### Math Transform & Math Operators
Mathematical functions (sin, cos, ln, etc.) and operators (add, sub, mult, div) on arrays. Rarely used directly but available.

## Crypto Considerations

### 24/7 Markets
- Candlestick patterns designed for traditional markets with opening/closing gaps may behave differently on crypto's continuous markets
- Gap-based patterns (morning star, evening star) are less reliable without session gaps
- Body-ratio patterns (doji, hammer, engulfing) still work well on any timeframe

### Timeframe Selection
- **1m-5m**: Patterns are noisy; combine with volume confirmation
- **15m-1h**: Good for intraday signals on high-cap tokens
- **4h-1d**: Most reliable for pattern recognition
- **Tip**: Higher timeframes produce fewer but more reliable pattern signals

### NaN Handling
TA-Lib returns `NaN` for the initial lookback period of each indicator. Always account for this:

```python
rsi = talib.RSI(close, timeperiod=14)
# First 14 values will be NaN
valid_rsi = rsi[~np.isnan(rsi)]
```

### Solana Token Data
When using TA-Lib with Solana token OHLCV data:
- Ensure arrays are `float64` dtype — TA-Lib requires this
- Sort by timestamp ascending before passing to TA-Lib
- Handle gaps in low-liquidity token data before computing indicators

```python
# Convert to float64 for TA-Lib compatibility
close = df["close"].values.astype(np.float64)
high = df["high"].values.astype(np.float64)
low = df["low"].values.astype(np.float64)
```

## Integration with Other Skills

### With pandas-ta
pandas-ta can use TA-Lib as a backend when installed, getting C-speed through the pandas-ta API:

```python
import pandas_ta as ta
# pandas-ta auto-detects TA-Lib and uses it for supported indicators
# Set explicitly:
ta.Imports["talib"] = True  # Force TA-Lib backend
df.ta.rsi(length=14)  # Uses TA-Lib under the hood if available
```

### With vectorbt
vectorbt integrates with TA-Lib for fast backtesting:

```python
import vectorbt as vbt

# Use TA-Lib indicators in vectorbt
rsi = vbt.talib("RSI").run(close, timeperiod=14)
entries = rsi.real_crossed_below(30)
exits = rsi.real_crossed_above(70)
```

### With Birdeye/DexScreener Data
Fetch OHLCV data from API skills, then process with TA-Lib:

```python
# After fetching OHLCV from birdeye-api or dexscreener-api
close = np.array(ohlcv_data["close"], dtype=np.float64)
rsi = talib.RSI(close, timeperiod=14)
```

## Listing Available Functions

```python
import talib

# All function groups
groups = talib.get_function_groups()
for group, funcs in groups.items():
    print(f"{group}: {len(funcs)} functions")

# All function names
all_funcs = talib.get_functions()
print(f"Total: {len(all_funcs)} functions")

# Info about a specific function
info = talib.abstract.Function("RSI").info
print(info["display_name"], info["group"])
```

## Files

| File | Description |
|---|---|
| `references/function_reference.md` | Most useful functions by category with syntax and parameters |
| `references/candlestick_patterns.md` | All 61 candlestick patterns grouped by type with reliability ratings |
| `scripts/compute_indicators.py` | Computes common indicators with TA-Lib/fallback comparison |
| `scripts/pattern_scanner.py` | Scans OHLCV data for all 61 candlestick patterns |
