# pandas-ta — Top 20 Crypto Indicators Guide

The most useful pandas-ta indicators for crypto trading, organized by category with syntax, recommended parameters, and signal interpretation.

## Trend Indicators

### 1. EMA (Exponential Moving Average)
- **Call**: `df.ta.ema(length=20)`
- **Returns**: `pd.Series` named `EMA_20`
- **Default**: `length=10`
- **Crypto params**: 9/21 for scalping, 20/50 for day trading, 50/200 for swing
- **Signal**: Price above EMA = bullish; EMA crossovers (fast > slow) = buy signal
- **Note**: Responds faster than SMA to recent price changes

### 2. SMA (Simple Moving Average)
- **Call**: `df.ta.sma(length=50)`
- **Returns**: `pd.Series` named `SMA_50`
- **Default**: `length=10`
- **Crypto params**: 20/50/200 are standard levels
- **Signal**: Golden cross (50 > 200) = bullish; death cross (50 < 200) = bearish

### 3. SuperTrend
- **Call**: `df.ta.supertrend(length=10, multiplier=3.0)`
- **Returns**: DataFrame with columns `SUPERT_10_3.0`, `SUPERTd_10_3.0`, `SUPERTl_10_3.0`, `SUPERTs_10_3.0`
- **Default**: `length=7, multiplier=3.0`
- **Crypto params**: `length=10, multiplier=3.0-4.0` (wider for volatile tokens)
- **Signal**: `SUPERTd` = 1 (bullish) or -1 (bearish); direction flip = trend change
- **Note**: Excellent standalone trend filter for crypto

### 4. ADX (Average Directional Index)
- **Call**: `df.ta.adx(length=14)`
- **Returns**: DataFrame with `ADX_14`, `DMP_14`, `DMN_14`
- **Default**: `length=14`
- **Signal**: ADX > 25 = trending, ADX < 20 = ranging; DMP > DMN = uptrend

### 5. HMA (Hull Moving Average)
- **Call**: `df.ta.hma(length=20)`
- **Returns**: `pd.Series` named `HMA_20`
- **Default**: `length=10`
- **Signal**: Minimal lag; direction change = early trend signal
- **Note**: Best low-lag moving average for fast crypto markets

### 6. VWMA (Volume Weighted Moving Average)
- **Call**: `df.ta.vwma(length=20)`
- **Returns**: `pd.Series` named `VWMA_20`
- **Default**: `length=10`
- **Signal**: Price above VWMA = volume-confirmed bullish; divergence = weakening trend
- **Note**: Less reliable on low-cap tokens with thin volume

## Momentum Indicators

### 7. RSI (Relative Strength Index)
- **Call**: `df.ta.rsi(length=14)`
- **Returns**: `pd.Series` named `RSI_14`
- **Default**: `length=14`
- **Crypto params**: 7-10 for scalping, 14 for standard, 21 for swing
- **Signal**: > 70 overbought, < 30 oversold; divergence from price = reversal warning
- **Note**: In strong crypto trends, RSI can stay >70 for extended periods

### 8. MACD (Moving Average Convergence Divergence)
- **Call**: `df.ta.macd(fast=12, slow=26, signal=9)`
- **Returns**: DataFrame with `MACD_12_26_9`, `MACDh_12_26_9`, `MACDs_12_26_9`
- **Default**: `fast=12, slow=26, signal=9`
- **Signal**: Histogram > 0 = bullish momentum; zero-line crossover = trend change
- **Note**: Histogram is the most actionable component for timing

### 9. Stochastic Oscillator
- **Call**: `df.ta.stoch(k=14, d=3, smooth_k=3)`
- **Returns**: DataFrame with `STOCHk_14_3_3`, `STOCHd_14_3_3`
- **Default**: `k=14, d=3, smooth_k=3`
- **Crypto params**: `k=5, d=3, smooth_k=3` for scalping
- **Signal**: > 80 overbought, < 20 oversold; %K crossing above %D = buy

### 10. CCI (Commodity Channel Index)
- **Call**: `df.ta.cci(length=20)`
- **Returns**: `pd.Series` named `CCI_20_0.015`
- **Default**: `length=14`
- **Signal**: > 100 overbought, < -100 oversold; zero-line cross = trend direction

### 11. Williams %R
- **Call**: `df.ta.willr(length=14)`
- **Returns**: `pd.Series` named `WILLR_14`
- **Default**: `length=14`
- **Signal**: > -20 overbought, < -80 oversold; faster than RSI

### 12. ROC (Rate of Change)
- **Call**: `df.ta.roc(length=10)`
- **Returns**: `pd.Series` named `ROC_10`
- **Default**: `length=10`
- **Signal**: Positive = upward momentum; crossing zero = trend shift

### 13. MFI (Money Flow Index)
- **Call**: `df.ta.mfi(length=14)`
- **Returns**: `pd.Series` named `MFI_14`
- **Default**: `length=14`
- **Signal**: > 80 overbought, < 20 oversold; volume-weighted RSI equivalent
- **Note**: Requires reliable volume data; unreliable on low-cap tokens

## Volatility Indicators

### 14. Bollinger Bands
- **Call**: `df.ta.bbands(length=20, std=2.0)`
- **Returns**: DataFrame with `BBL_20_2.0`, `BBM_20_2.0`, `BBU_20_2.0`, `BBB_20_2.0`, `BBP_20_2.0`
- **Default**: `length=5, std=2.0`
- **Crypto params**: `length=20, std=2.5` (wider for crypto volatility)
- **Signal**: BBP (percent B) < 0 = below lower band; BBB (bandwidth) contracting = squeeze
- **Note**: Use BBB for squeeze detection; narrow BBB = imminent breakout

### 15. ATR (Average True Range)
- **Call**: `df.ta.atr(length=14)`
- **Returns**: `pd.Series` named `ATRr_14`
- **Default**: `length=14`
- **Crypto params**: 7 for scalping, 14 for standard
- **Signal**: Rising ATR = increasing volatility; use for stop-loss distance (1.5-2x ATR)
- **Note**: Essential for position sizing — normalize by price for cross-asset comparison

### 16. Keltner Channels
- **Call**: `df.ta.kc(length=20, scalar=1.5)`
- **Returns**: DataFrame with `KCLe_20_1.5`, `KCBe_20_1.5`, `KCUe_20_1.5`
- **Default**: `length=20, scalar=2`
- **Signal**: BBands inside KC = TTM Squeeze (low volatility, breakout pending)

### 17. Donchian Channels
- **Call**: `df.ta.donchian(lower_length=20, upper_length=20)`
- **Returns**: DataFrame with `DCL_20_20`, `DCM_20_20`, `DCU_20_20`
- **Default**: `lower_length=20, upper_length=20`
- **Signal**: Price at upper channel = breakout; price at lower = breakdown

## Volume Indicators

### 18. OBV (On-Balance Volume)
- **Call**: `df.ta.obv()`
- **Returns**: `pd.Series` named `OBV`
- **Signal**: OBV rising while price flat = accumulation; OBV falling while price rising = distribution
- **Note**: Trend of OBV matters more than absolute value

### 19. VWAP (Volume Weighted Average Price)
- **Call**: `df.ta.vwap()`
- **Returns**: `pd.Series` named `VWAP_D`
- **Signal**: Price above VWAP = bullish intraday bias; price below = bearish
- **Note**: Requires DatetimeIndex; resets daily at midnight UTC for crypto
- **Crypto consideration**: Anchored VWAP from key swing points is more useful than daily reset

### 20. CMF (Chaikin Money Flow)
- **Call**: `df.ta.cmf(length=20)`
- **Returns**: `pd.Series` named `CMF_20`
- **Default**: `length=20`
- **Signal**: > 0 = buying pressure (accumulation); < 0 = selling pressure (distribution)
- **Note**: Combines price and volume; confirm with OBV for stronger signals

## Parameter Adjustment by Timeframe

| Timeframe | RSI | EMA fast/slow | BB length/std | ATR | Stoch k |
|-----------|-----|--------------|---------------|-----|---------|
| 1m-5m | 5-7 | 5/13 | 10/2.0 | 5 | 5 |
| 15m | 9-14 | 9/21 | 15/2.0 | 10 | 9 |
| 1h | 14 | 20/50 | 20/2.0 | 14 | 14 |
| 4h | 14 | 20/50 | 20/2.5 | 14 | 14 |
| 1d | 14-21 | 50/200 | 20/2.5 | 14 | 14 |

**General rule**: Shorter timeframes need shorter indicator periods to remain responsive. Longer timeframes benefit from wider volatility bands (higher BB std, higher SuperTrend multiplier).
