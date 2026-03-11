# TA-Lib Function Reference

Most useful functions by category with syntax, parameters, defaults, and return values.

## Overlap Studies

### SMA — Simple Moving Average
```python
sma = talib.SMA(close, timeperiod=30)
```
- **Parameters**: `timeperiod` (default 30)
- **Returns**: Single array. NaN for first `timeperiod - 1` bars.
- **Use**: Trend direction, dynamic support/resistance.

### EMA — Exponential Moving Average
```python
ema = talib.EMA(close, timeperiod=30)
```
- **Parameters**: `timeperiod` (default 30)
- **Returns**: Single array. NaN for first `timeperiod - 1` bars.
- **Use**: Faster-reacting trend filter than SMA. EMA 12/26 used in MACD.

### BBANDS — Bollinger Bands
```python
upper, middle, lower = talib.BBANDS(close, timeperiod=5, nbdevup=2, nbdevdn=2, matype=0)
```
- **Parameters**: `timeperiod` (default 5), `nbdevup` (default 2), `nbdevdn` (default 2), `matype` (0=SMA, 1=EMA, etc.)
- **Returns**: Three arrays (upper, middle, lower). Middle is the moving average.
- **Use**: Volatility bands, mean reversion entries at band touches.

### SAR — Parabolic SAR
```python
sar = talib.SAR(high, low, acceleration=0.02, maximum=0.2)
```
- **Parameters**: `acceleration` (default 0.02), `maximum` (default 0.2)
- **Returns**: Single array of SAR values.
- **Use**: Trailing stop placement, trend direction (price above SAR = bullish).

### MAMA — MESA Adaptive Moving Average
```python
mama, fama = talib.MAMA(close, fastlimit=0.5, slowlimit=0.05)
```
- **Parameters**: `fastlimit` (default 0.5), `slowlimit` (default 0.05)
- **Returns**: Two arrays (MAMA, FAMA). MAMA crosses above FAMA = bullish.
- **Use**: Adaptive trend following with reduced lag.

### DEMA / TEMA — Double/Triple EMA
```python
dema = talib.DEMA(close, timeperiod=30)
tema = talib.TEMA(close, timeperiod=30)
```
- **Use**: Reduced-lag moving averages for faster signal generation.

### WMA — Weighted Moving Average
```python
wma = talib.WMA(close, timeperiod=30)
```

### KAMA — Kaufman Adaptive Moving Average
```python
kama = talib.KAMA(close, timeperiod=30)
```
- **Use**: Adapts speed based on market noise. Slower in choppy markets, faster in trends.

## Momentum Indicators

### RSI — Relative Strength Index
```python
rsi = talib.RSI(close, timeperiod=14)
```
- **Parameters**: `timeperiod` (default 14)
- **Returns**: Single array, values 0-100. NaN for first `timeperiod` bars.
- **Interpretation**: < 30 oversold, > 70 overbought. Crypto often uses 20/80 thresholds.

### MACD — Moving Average Convergence Divergence
```python
macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
```
- **Parameters**: `fastperiod` (12), `slowperiod` (26), `signalperiod` (9)
- **Returns**: Three arrays (MACD line, signal line, histogram).
- **Interpretation**: MACD crosses above signal = bullish. Histogram shows momentum.

### STOCH — Stochastic Oscillator
```python
slowk, slowd = talib.STOCH(high, low, close, fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
```
- **Returns**: Two arrays (SlowK, SlowD), values 0-100.
- **Interpretation**: < 20 oversold, > 80 overbought. K crossing D = signal.

### STOCHRSI — Stochastic RSI
```python
fastk, fastd = talib.STOCHRSI(close, timeperiod=14, fastk_period=5, fastd_period=3, fastd_matype=0)
```
- **Returns**: Two arrays (FastK, FastD), values 0-100.
- **Use**: More sensitive than RSI alone. Popular in crypto analysis.

### CCI — Commodity Channel Index
```python
cci = talib.CCI(high, low, close, timeperiod=14)
```
- **Returns**: Single array, unbounded. Typically oscillates -200 to +200.
- **Interpretation**: > +100 overbought, < -100 oversold.

### WILLR — Williams %R
```python
willr = talib.WILLR(high, low, close, timeperiod=14)
```
- **Returns**: Single array, values -100 to 0.
- **Interpretation**: < -80 oversold, > -20 overbought.

### ADX — Average Directional Index
```python
adx = talib.ADX(high, low, close, timeperiod=14)
```
- **Returns**: Single array, values 0-100.
- **Interpretation**: > 25 trending, < 20 ranging. Does not indicate direction.

### PLUS_DI / MINUS_DI — Directional Indicators
```python
plus_di = talib.PLUS_DI(high, low, close, timeperiod=14)
minus_di = talib.MINUS_DI(high, low, close, timeperiod=14)
```
- **Use**: Combined with ADX. +DI > -DI = bullish trend, -DI > +DI = bearish.

### MFI — Money Flow Index
```python
mfi = talib.MFI(high, low, close, volume, timeperiod=14)
```
- **Returns**: Single array, values 0-100.
- **Interpretation**: Volume-weighted RSI. < 20 oversold, > 80 overbought.

### ROC — Rate of Change
```python
roc = talib.ROC(close, timeperiod=10)
```
- **Returns**: Percentage change over `timeperiod` bars.

### MOM — Momentum
```python
mom = talib.MOM(close, timeperiod=10)
```
- **Returns**: Price difference over `timeperiod` bars (close - close[n]).

## Volume Indicators

### OBV — On Balance Volume
```python
obv = talib.OBV(close, volume)
```
- **Returns**: Cumulative volume series. Rising OBV = buying pressure.

### AD — Chaikin A/D Line
```python
ad = talib.AD(high, low, close, volume)
```
- **Returns**: Accumulation/Distribution line. Divergence from price signals reversals.

### ADOSC — Chaikin A/D Oscillator
```python
adosc = talib.ADOSC(high, low, close, volume, fastperiod=3, slowperiod=10)
```
- **Returns**: Difference between fast and slow A/D EMAs.

## Volatility Indicators

### ATR — Average True Range
```python
atr = talib.ATR(high, low, close, timeperiod=14)
```
- **Returns**: Single array in price units. Higher = more volatile.
- **Use**: Stop-loss placement, position sizing. Common: 2x ATR stop.

### NATR — Normalized ATR
```python
natr = talib.NATR(high, low, close, timeperiod=14)
```
- **Returns**: ATR as percentage of close. Comparable across different price levels.

### TRANGE — True Range
```python
trange = talib.TRANGE(high, low, close)
```
- **Returns**: Single-bar true range (max of high-low, |high-prevclose|, |low-prevclose|).

## Pattern Recognition (Top 20)

All candlestick functions take `(open, high, low, close)` and return integer arrays:
`+100` = bullish, `-100` = bearish, `0` = no pattern. Some return `+200`/`-200` for strong signals.

| Function | Pattern | Bars | Reliability |
|---|---|---|---|
| `CDLDOJI` | Doji | 1 | Medium |
| `CDLHAMMER` | Hammer | 1 | High |
| `CDLINVERTEDHAMMER` | Inverted Hammer | 1 | Medium |
| `CDLSHOOTINGSTAR` | Shooting Star | 1 | High |
| `CDLHANGINGMAN` | Hanging Man | 1 | Medium |
| `CDLENGULFING` | Engulfing | 2 | High |
| `CDLHARAMI` | Harami | 2 | Medium |
| `CDLPIERCING` | Piercing Line | 2 | High |
| `CDLDARKCLOUDCOVER` | Dark Cloud Cover | 2 | High |
| `CDLMORNINGSTAR` | Morning Star | 3 | High |
| `CDLEVENINGSTAR` | Evening Star | 3 | High |
| `CDLMORNINGDOJISTAR` | Morning Doji Star | 3 | High |
| `CDLEVENINGDOJISTAR` | Evening Doji Star | 3 | High |
| `CDLTHREEWHITESOLDIERS` | Three White Soldiers | 3 | High |
| `CDLTHREEBLACKCROWS` | Three Black Crows | 3 | High |
| `CDLMARUBOZU` | Marubozu | 1 | High |
| `CDLSPINNINGTOP` | Spinning Top | 1 | Low |
| `CDLDRAGONFLYDOJI` | Dragonfly Doji | 1 | Medium |
| `CDLGRAVESTONEDOJI` | Gravestone Doji | 1 | Medium |
| `CDLABANDONEDBABY` | Abandoned Baby | 3 | High |

See `candlestick_patterns.md` for the complete list of all 61 patterns.

## Discovering Functions

```python
# List all groups and their functions
groups = talib.get_function_groups()
for group, funcs in groups.items():
    print(f"\n{group} ({len(funcs)}):")
    for f in funcs:
        print(f"  {f}")

# Get info about any function
info = talib.abstract.Function("RSI").info
print(info["display_name"])       # "Relative Strength Index"
print(info["group"])              # "Momentum Indicators"
print(info["parameters"])         # {"timeperiod": 14}
print(info["output_names"])       # ["real"]
```
