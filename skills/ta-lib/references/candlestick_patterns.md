# TA-Lib Candlestick Patterns — Complete Reference

All 61 candlestick pattern recognition functions. Every function takes `(open, high, low, close)` as float64 NumPy arrays and returns an integer array: `+100` = bullish, `-100` = bearish, `0` = no pattern detected. Some patterns return `+200`/`-200` for strong confirmation.

## Return Value Convention

```python
result = talib.CDLHAMMER(open_, high, low, close)
# result[i] == 100   → bullish hammer on bar i
# result[i] == -100  → bearish variant (if applicable)
# result[i] == 0     → no pattern on bar i
```

## Reversal Bullish (12 patterns)

Patterns that signal a potential bottom/reversal from bearish to bullish trend.

| # | Function | Name | Bars | Reliability | Crypto Notes |
|---|---|---|---|---|---|
| 1 | `CDLHAMMER` | Hammer | 1 | High | Works well on all timeframes |
| 2 | `CDLINVERTEDHAMMER` | Inverted Hammer | 1 | Medium | Needs volume confirmation |
| 3 | `CDLENGULFING` | Bullish Engulfing | 2 | High | Strong on 4h+ timeframes |
| 4 | `CDLPIERCING` | Piercing Line | 2 | High | Less reliable without gaps |
| 5 | `CDLMORNINGSTAR` | Morning Star | 3 | High | Rare on crypto (needs gaps) |
| 6 | `CDLMORNINGDOJISTAR` | Morning Doji Star | 3 | High | Rare on crypto |
| 7 | `CDLHARAMI` | Bullish Harami | 2 | Medium | Common but weak alone |
| 8 | `CDLHARAMICROSS` | Bullish Harami Cross | 2 | Medium | Harami with doji inside |
| 9 | `CDLDRAGONFLYDOJI` | Dragonfly Doji | 1 | Medium | Good at support levels |
| 10 | `CDLABANDONEDBABY` | Abandoned Baby (Bull) | 3 | High | Very rare on crypto |
| 11 | `CDLTHREEWHITESOLDIERS` | Three White Soldiers | 3 | High | Strong trend reversal |
| 12 | `CDLKICKING` | Kicking (Bull) | 2 | High | Needs gaps, rare on crypto |

## Reversal Bearish (12 patterns)

Patterns that signal a potential top/reversal from bullish to bearish trend.

| # | Function | Name | Bars | Reliability | Crypto Notes |
|---|---|---|---|---|---|
| 13 | `CDLSHOOTINGSTAR` | Shooting Star | 1 | High | Works well, confirm with volume |
| 14 | `CDLHANGINGMAN` | Hanging Man | 1 | Medium | Hammer at top, needs confirmation |
| 15 | `CDLENGULFING` | Bearish Engulfing | 2 | High | Returns -100 for bearish |
| 16 | `CDLDARKCLOUDCOVER` | Dark Cloud Cover | 2 | High | Less reliable without gaps |
| 17 | `CDLEVENINGSTAR` | Evening Star | 3 | High | Rare on crypto (needs gaps) |
| 18 | `CDLEVENINGDOJISTAR` | Evening Doji Star | 3 | High | Rare on crypto |
| 19 | `CDLHARAMI` | Bearish Harami | 2 | Medium | Returns -100 for bearish |
| 20 | `CDLHARAMICROSS` | Bearish Harami Cross | 2 | Medium | Harami with doji inside |
| 21 | `CDLGRAVESTONEDOJI` | Gravestone Doji | 1 | Medium | Good at resistance levels |
| 22 | `CDLABANDONEDBABY` | Abandoned Baby (Bear) | 3 | High | Very rare on crypto |
| 23 | `CDLTHREEBLACKCROWS` | Three Black Crows | 3 | High | Strong downtrend signal |
| 24 | `CDLKICKING` | Kicking (Bear) | 2 | High | Needs gaps, rare on crypto |

## Continuation Patterns (8 patterns)

Patterns that suggest the existing trend will continue.

| # | Function | Name | Bars | Reliability | Crypto Notes |
|---|---|---|---|---|---|
| 25 | `CDLRISEFALL3METHODS` | Rising/Falling Three | 5 | High | Needs clear prior trend |
| 26 | `CDLTASUKIGAP` | Tasuki Gap | 3 | Medium | Gap-dependent, rare crypto |
| 27 | `CDLGAPSIDESIDEWHITE` | Side-by-Side White | 3 | Low | Gap-dependent |
| 28 | `CDLSEPARATINGLINES` | Separating Lines | 2 | Medium | Gap-dependent |
| 29 | `CDLMATHOLD` | Mat Hold | 5 | High | Rare but reliable |
| 30 | `CDLINNECK` | In-Neck | 2 | Low | Bearish continuation |
| 31 | `CDLONNECK` | On-Neck | 2 | Low | Bearish continuation |
| 32 | `CDLTHRUSTING` | Thrusting | 2 | Low | Bearish continuation |

## Indecision Patterns (5 patterns)

Patterns indicating market indecision — potential inflection points.

| # | Function | Name | Bars | Reliability | Crypto Notes |
|---|---|---|---|---|---|
| 33 | `CDLDOJI` | Doji | 1 | Medium | Very common on low TFs |
| 34 | `CDLDRAGONFLYDOJI` | Dragonfly Doji | 1 | Medium | Bullish bias at support |
| 35 | `CDLGRAVESTONEDOJI` | Gravestone Doji | 1 | Medium | Bearish bias at resistance |
| 36 | `CDLLONGLEGGEDDOJI` | Long-Legged Doji | 1 | Medium | High volatility indecision |
| 37 | `CDLSPINNINGTOP` | Spinning Top | 1 | Low | Very common, weak signal |

## Complex Multi-Bar Patterns (14 patterns)

| # | Function | Name | Bars | Reliability |
|---|---|---|---|---|
| 38 | `CDLADVANCEBLOCK` | Advance Block | 3 | Medium |
| 39 | `CDLBELTHOLD` | Belt Hold | 1 | Low |
| 40 | `CDLBREAKAWAY` | Breakaway | 5 | Medium |
| 41 | `CDLCLOSINGMARUBOZU` | Closing Marubozu | 1 | Medium |
| 42 | `CDLCONCEALBABYSWALL` | Concealing Baby Swallow | 4 | High |
| 43 | `CDLCOUNTERATTACK` | Counterattack | 2 | Medium |
| 44 | `CDLDOJISTAR` | Doji Star | 2 | Medium |
| 45 | `CDLHIGHWAVE` | High Wave | 1 | Low |
| 46 | `CDLHIKKAKE` | Hikkake | 3 | Medium |
| 47 | `CDLHIKKAKEMOD` | Modified Hikkake | 3 | Medium |
| 48 | `CDLHOMINGPIGEON` | Homing Pigeon | 2 | Low |
| 49 | `CDLIDENTICAL3CROWS` | Identical Three Crows | 3 | High |
| 50 | `CDLLADDERBOTTOM` | Ladder Bottom | 5 | Medium |
| 51 | `CDLLONGLINE` | Long Line | 1 | Low |

## Remaining Patterns (10 patterns)

| # | Function | Name | Bars | Reliability |
|---|---|---|---|---|
| 52 | `CDLMARUBOZU` | Marubozu | 1 | High |
| 53 | `CDLMATCHINGLOW` | Matching Low | 2 | Medium |
| 54 | `CDLRICKSHAWMAN` | Rickshaw Man | 1 | Low |
| 55 | `CDLSHORTLINE` | Short Line | 1 | Low |
| 56 | `CDLSTALLEDPATTERN` | Stalled Pattern | 3 | Medium |
| 57 | `CDLSTICKSANDWICH` | Stick Sandwich | 3 | Medium |
| 58 | `CDLTAKURI` | Takuri | 1 | Medium |
| 59 | `CDLTRISTAR` | Tri-Star | 3 | Medium |
| 60 | `CDLUNIQUE3RIVER` | Unique Three River | 3 | Medium |
| 61 | `CDLXSIDEGAP3METHODS` | Side Gap Three Methods | 3 | Medium |

## Reliability Tiers for Crypto

### Tier 1 — Most Reliable on 24/7 Markets
These patterns depend on body ratios, not gaps, so they work well on continuous crypto markets:
- `CDLHAMMER`, `CDLSHOOTINGSTAR` — Single-bar reversal, body/wick ratio based
- `CDLENGULFING` — Two-bar reversal, strong on 4h+ timeframes
- `CDLDOJI` variants — Indecision at key levels
- `CDLMARUBOZU` — Strong momentum candle
- `CDLTHREEWHITESOLDIERS`, `CDLTHREEBLACKCROWS` — Three-bar trend

### Tier 2 — Moderately Reliable
Work on crypto but less frequently than traditional markets:
- `CDLHARAMI`, `CDLHARAMICROSS` — Inside bar patterns
- `CDLPIERCING`, `CDLDARKCLOUDCOVER` — Two-bar patterns
- `CDLRISEFALL3METHODS` — Continuation patterns

### Tier 3 — Less Reliable on Crypto
Gap-dependent patterns that rarely form on 24/7 markets:
- `CDLMORNINGSTAR`, `CDLEVENINGSTAR` — Need session gaps
- `CDLABANDONEDBABY` — Requires true gaps
- `CDLKICKING` — Marubozu with gap
- `CDLTASUKIGAP`, `CDLGAPSIDESIDEWHITE` — Gap-dependent

## Scanning All Patterns

```python
import talib
import numpy as np

def scan_all_patterns(open_: np.ndarray, high: np.ndarray,
                      low: np.ndarray, close: np.ndarray) -> dict:
    """Scan OHLC data for all 61 candlestick patterns."""
    candle_funcs = talib.get_function_groups()["Pattern Recognition"]
    results = {}
    for name in candle_funcs:
        func = getattr(talib, name)
        result = func(open_, high, low, close)
        hits = np.nonzero(result)[0]
        if len(hits) > 0:
            results[name] = {
                "count": len(hits),
                "bars": hits.tolist(),
                "values": result[hits].tolist()
            }
    return results
```

## Combining Patterns with Indicators

Candlestick patterns alone generate many false signals. Combine with trend/momentum:

```python
rsi = talib.RSI(close, timeperiod=14)
hammer = talib.CDLHAMMER(open_, high, low, close)

# Only take bullish hammer when RSI is oversold
confirmed = np.where((hammer > 0) & (rsi < 30), hammer, 0)
```
