# pandas-ta — Strategy Patterns for Crypto Trading

Pre-built indicator combinations for common crypto trading styles, with ta.Strategy definitions and signal generation logic.

## Scalping Strategy (1m-5m Timeframes)

Fast indicators tuned for rapid entries and exits on volatile crypto pairs.

### Indicator Set
```python
import pandas_ta as ta

scalp_strategy = ta.Strategy(
    name="Crypto Scalp",
    ta=[
        {"kind": "ema", "length": 9},
        {"kind": "ema", "length": 21},
        {"kind": "rsi", "length": 7},
        {"kind": "stoch", "k": 5, "d": 3, "smooth_k": 3},
        {"kind": "atr", "length": 7},
        {"kind": "obv"},
    ]
)
df.ta.strategy(scalp_strategy)
```

### Signal Logic
```python
# Buy: EMA9 > EMA21, RSI recovering from <30, Stoch %K crossing above %D
buy = (
    (df["EMA_9"] > df["EMA_21"]) &
    (df["RSI_7"] > 30) & (df["RSI_7"].shift(1) <= 30) &
    (df["STOCHk_5_3_3"] > df["STOCHd_5_3_3"])
)

# Stop loss: 1.5x ATR below entry
stop_distance = df["ATRr_7"] * 1.5

# Exit: EMA9 crosses below EMA21 or RSI > 75
exit_signal = (df["EMA_9"] < df["EMA_21"]) | (df["RSI_7"] > 75)
```

### Notes
- Hold time: seconds to minutes
- Best for: high-volume pairs (SOL/USDC, major memecoins with volume)
- Risk: high false signal rate — combine with order flow or L2 data

## Day Trading Strategy (15m-1h Timeframes)

Balanced indicator set for intraday position management.

### Indicator Set
```python
day_strategy = ta.Strategy(
    name="Crypto Day Trade",
    ta=[
        {"kind": "ema", "length": 20},
        {"kind": "ema", "length": 50},
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "rsi", "length": 14},
        {"kind": "bbands", "length": 20, "std": 2.0},
        {"kind": "atr", "length": 14},
        {"kind": "vwap"},
        {"kind": "obv"},
    ]
)
df.ta.strategy(day_strategy)
```

### Signal Logic
```python
# Buy: Price above VWAP, EMA20 > EMA50, MACD histogram positive, RSI 40-65
buy = (
    (df["close"] > df["VWAP_D"]) &
    (df["EMA_20"] > df["EMA_50"]) &
    (df["MACDh_12_26_9"] > 0) &
    (df["RSI_14"].between(40, 65))
)

# Take profit: Price touches upper Bollinger Band or RSI > 70
take_profit = (df["close"] >= df["BBU_20_2.0"]) | (df["RSI_14"] > 70)

# Stop loss: 2x ATR below entry or price below lower BB
stop_loss = (df["close"] < df["BBL_20_2.0"])
```

### Notes
- Hold time: minutes to hours
- Best for: established tokens with consistent volume
- Confirm direction with higher timeframe (4h trend)

## Swing Trading Strategy (4h-1d Timeframes)

Slower indicators for multi-day positions with trend confirmation.

### Indicator Set
```python
swing_strategy = ta.Strategy(
    name="Crypto Swing",
    ta=[
        {"kind": "ema", "length": 50},
        {"kind": "ema", "length": 200},
        {"kind": "supertrend", "length": 10, "multiplier": 3.0},
        {"kind": "rsi", "length": 14},
        {"kind": "adx", "length": 14},
        {"kind": "atr", "length": 14},
        {"kind": "bbands", "length": 20, "std": 2.5},
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
    ]
)
df.ta.strategy(swing_strategy)
```

### Signal Logic
```python
# Buy: EMA50 > EMA200, SuperTrend bullish, ADX > 25, RSI 40-60 (pullback entry)
buy = (
    (df["EMA_50"] > df["EMA_200"]) &
    (df["SUPERTd_10_3.0"] == 1) &
    (df["ADX_14"] > 25) &
    (df["RSI_14"].between(40, 60))
)

# Stop loss: SuperTrend flip or 2.5x ATR
stop_loss = df["SUPERTd_10_3.0"] == -1

# Take profit: RSI > 75 and MACD histogram declining
take_profit = (df["RSI_14"] > 75) & (df["MACDh_12_26_9"] < df["MACDh_12_26_9"].shift(1))
```

### Notes
- Hold time: days to weeks
- Best for: large-cap crypto (SOL, ETH, BTC)
- Use weekly chart for overall trend direction

## PumpFun / Memecoin Scalping (1m-5m)

Ultra-fast indicators for new token launches with extreme volatility.

### Indicator Set
```python
pump_strategy = ta.Strategy(
    name="PumpFun Scalp",
    ta=[
        {"kind": "ema", "length": 5},
        {"kind": "ema", "length": 13},
        {"kind": "rsi", "length": 5},
        {"kind": "atr", "length": 5},
        {"kind": "bbands", "length": 10, "std": 3.0},
    ]
)
df.ta.strategy(pump_strategy)
```

### Signal Logic
```python
# Volume ratio (not a pandas-ta indicator, compute manually)
vol_ratio = df["volume"] / df["volume"].rolling(20).mean()

# Buy: EMA5 > EMA13, RSI recovering (was <25, now >35), volume 3x+ average
buy = (
    (df["EMA_5"] > df["EMA_13"]) &
    (df["RSI_5"] > 35) & (df["RSI_5"].shift(2) < 25) &
    (vol_ratio > 3.0)
)

# Exit: EMA5 < EMA13 or RSI > 85 (take profit) or 2x ATR stop
exit_signal = (df["EMA_5"] < df["EMA_13"]) | (df["RSI_5"] > 85)
```

### Notes
- Hold time: seconds to minutes
- Extremely high risk — most PumpFun tokens go to zero
- Volume data is often unreliable — use as secondary confirmation only
- Always set hard stop-losses; never average down on memecoins

## Multi-Timeframe Analysis Pattern

Combine signals from multiple timeframes for higher confidence entries.

```python
import pandas as pd
import pandas_ta as ta

def analyze_multi_timeframe(
    df_5m: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame,
) -> dict:
    """Score alignment across timeframes.

    Args:
        df_5m: 5-minute OHLCV DataFrame
        df_1h: 1-hour OHLCV DataFrame
        df_4h: 4-hour OHLCV DataFrame

    Returns:
        Dictionary with alignment score and per-timeframe signals.
    """
    signals = {}

    # 4h: overall trend direction
    df_4h.ta.supertrend(length=10, multiplier=3.0, append=True)
    df_4h.ta.adx(length=14, append=True)
    trend_bull = (df_4h["SUPERTd_10_3.0"].iloc[-1] == 1)
    trending = (df_4h["ADX_14"].iloc[-1] > 25)
    signals["4h"] = "bullish" if trend_bull and trending else "bearish" if not trend_bull and trending else "neutral"

    # 1h: momentum confirmation
    df_1h.ta.macd(append=True)
    df_1h.ta.rsi(append=True)
    macd_bull = df_1h["MACDh_12_26_9"].iloc[-1] > 0
    rsi_ok = 40 < df_1h["RSI_14"].iloc[-1] < 70
    signals["1h"] = "bullish" if macd_bull and rsi_ok else "bearish" if not macd_bull else "neutral"

    # 5m: entry timing
    df_5m.ta.ema(length=9, append=True)
    df_5m.ta.ema(length=21, append=True)
    df_5m.ta.rsi(length=7, append=True)
    ema_cross = df_5m["EMA_9"].iloc[-1] > df_5m["EMA_21"].iloc[-1]
    rsi_entry = df_5m["RSI_7"].iloc[-1] < 60
    signals["5m"] = "bullish" if ema_cross and rsi_entry else "neutral"

    # Alignment score
    bull_count = sum(1 for v in signals.values() if v == "bullish")
    signals["alignment"] = bull_count / len(signals)
    signals["recommendation"] = "strong" if bull_count == 3 else "moderate" if bull_count == 2 else "weak"

    return signals
```

## Signal Scoring Framework

Convert raw indicator values into a normalized score for comparison.

```python
def score_indicators(df: pd.DataFrame) -> dict:
    """Score current indicator readings on a -100 to +100 scale.

    Positive = bullish bias, negative = bearish bias.
    """
    scores = {}
    last = df.iloc[-1]

    # RSI: 0-30 = bullish (oversold), 70-100 = bearish (overbought)
    if "RSI_14" in df.columns:
        rsi = last["RSI_14"]
        scores["rsi"] = (50 - rsi) * 2  # 30→+40, 50→0, 70→-40

    # MACD histogram: positive = bullish
    if "MACDh_12_26_9" in df.columns:
        macd_h = last["MACDh_12_26_9"]
        scores["macd"] = min(max(macd_h * 100, -100), 100)

    # BB position: below mid = bullish, above = bearish
    if "BBP_20_2.0" in df.columns:
        bbp = last["BBP_20_2.0"]
        scores["bbands"] = (0.5 - bbp) * 200  # 0→+100, 0.5→0, 1→-100

    # SuperTrend direction
    st_col = [c for c in df.columns if c.startswith("SUPERTd")]
    if st_col:
        scores["supertrend"] = last[st_col[0]] * 50  # +50 or -50

    # Composite
    if scores:
        scores["composite"] = sum(scores.values()) / len(scores)

    return scores
```

## Running Strategies with ta.Strategy

```python
# Run and inspect results
df.ta.strategy(my_strategy)

# All new columns added to df
new_cols = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
print(f"Added {len(new_cols)} indicator columns: {new_cols}")

# Get the last row summary
summary = df[new_cols].iloc[-1].to_dict()
for name, value in summary.items():
    print(f"  {name}: {value:.4f}" if isinstance(value, float) else f"  {name}: {value}")
```
