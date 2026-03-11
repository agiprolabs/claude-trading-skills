---
name: regime-detection
description: Market regime identification using volatility clustering, trend detection, and statistical methods for adaptive trading
---

# Regime Detection

Identify the current market regime so you can pick the right strategy, size positions correctly, and avoid deploying trend-following logic in a ranging market (or vice versa).

## Why Regime Detection Matters

Every strategy has a "home regime." A momentum strategy prints money in a clean uptrend but bleeds in a choppy range. A mean-reversion grid thrives in low-volatility consolidation but gets steamrolled by a trending breakout. Regime detection tells you **which playbook to use right now**.

Key benefits:
- **Strategy selection**: Route signals to the right strategy for the current environment
- **Position sizing**: Reduce exposure in hostile regimes, increase in favorable ones
- **Stop adaptation**: Wider stops in high-vol regimes, tighter in low-vol trends
- **Drawdown control**: Sit out "danger zone" regimes (high vol + no trend)

## Core Regime Dimensions

Two orthogonal axes define the four-quadrant regime model:

| | Low Volatility | High Volatility |
|---|---|---|
| **Trending** | Q1: Clean trend — best for trend following | Q2: Volatile trend — momentum with caution |
| **Ranging** | Q3: Quiet range — mean-reversion paradise | Q4: Choppy chaos — reduce or sit out |

A third dimension — **mean-reversion tendency** (Hurst exponent) — refines Q3 by telling you how reliably price reverts.

## Simple Approaches (No ML Required)

### 1. ATR Volatility Percentile

Rank the current ATR against its own recent history to get a 0–100 percentile score.

```python
import pandas as pd
import numpy as np

def atr_percentile(
    high: pd.Series, low: pd.Series, close: pd.Series,
    atr_period: int = 14, lookback: int = 100
) -> pd.Series:
    """ATR percentile rank over a rolling window."""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    return atr.rolling(lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
```

- **< 25th percentile** → Low volatility regime
- **25th–75th** → Normal volatility
- **> 75th percentile** → High volatility regime

### 2. ADX Trend Strength

ADX above 25 signals a trending market; below 20 signals a range.

```python
def compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series,
    period: int = 14
) -> pd.Series:
    """Average Directional Index."""
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    # Zero out when the other is larger
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(span=period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(span=period, adjust=False).mean()
```

### 3. EMA Slope + Price Position

```python
def trend_direction(close: pd.Series, period: int = 20) -> pd.Series:
    """Returns +1 (uptrend), -1 (downtrend), 0 (neutral)."""
    ema = close.ewm(span=period, adjust=False).mean()
    slope = ema.diff(5)  # 5-bar slope
    above = (close > ema).astype(int)
    direction = pd.Series(0, index=close.index)
    direction[(slope > 0) & (above == 1)] = 1
    direction[(slope < 0) & (above == 0)] = -1
    return direction
```

### 4. Bollinger Band Width Percentile

BB width (upper - lower) / middle as a volatility proxy. A "squeeze" (low percentile) often precedes a breakout.

```python
def bb_width_percentile(
    close: pd.Series, period: int = 20,
    std_dev: float = 2.0, lookback: int = 100
) -> pd.Series:
    """Bollinger Band width percentile."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    width = (2 * std_dev * std) / sma
    return width.rolling(lookback).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
```

## Statistical Approaches

### Rolling Hurst Exponent

The Hurst exponent H classifies time series behavior:
- **H < 0.4** → Mean-reverting (anti-persistent)
- **0.4 ≤ H ≤ 0.6** → Random walk (no exploitable structure)
- **H > 0.6** → Trending (persistent)

Computed via the Rescaled Range (R/S) method. See `references/methodology.md` for the full derivation.

```python
def hurst_exponent(series: pd.Series, max_lag: int = 50) -> float:
    """Estimate Hurst exponent using R/S method."""
    lags = range(2, max_lag)
    rs_values = []
    for lag in lags:
        chunks = [series.iloc[i:i+lag] for i in range(0, len(series) - lag, lag)]
        rs_list = []
        for chunk in chunks:
            if len(chunk) < lag:
                continue
            mean_val = chunk.mean()
            devs = chunk - mean_val
            cumdev = devs.cumsum()
            r = cumdev.max() - cumdev.min()
            s = chunk.std(ddof=1)
            if s > 0:
                rs_list.append(r / s)
        if rs_list:
            rs_values.append(np.mean(rs_list))
        else:
            rs_values.append(np.nan)
    valid = [(l, r) for l, r in zip(lags, rs_values) if not np.isnan(r)]
    if len(valid) < 5:
        return 0.5
    log_lags = np.log([v[0] for v in valid])
    log_rs = np.log([v[1] for v in valid])
    coeffs = np.polyfit(log_lags, log_rs, 1)
    return coeffs[0]
```

### Change-Point Detection (CUSUM)

Detects abrupt shifts in mean or variance of a return series.

```python
def cusum_test(
    returns: pd.Series, threshold: float = 2.0
) -> list[int]:
    """CUSUM change-point detection on returns.

    Returns indices where regime changes are detected.
    """
    mean_r = returns.mean()
    std_r = returns.std()
    if std_r == 0:
        return []
    s_pos, s_neg = 0.0, 0.0
    changes = []
    for i, r in enumerate(returns):
        z = (r - mean_r) / std_r
        s_pos = max(0, s_pos + z - 0.5)
        s_neg = max(0, s_neg - z - 0.5)
        if s_pos > threshold or s_neg > threshold:
            changes.append(i)
            s_pos, s_neg = 0.0, 0.0
    return changes
```

### Hidden Markov Models

For 2–3 state regime models using `hmmlearn`. This is optional — all core functionality works with numpy/pandas only.

```python
# Optional: requires `uv pip install hmmlearn`
from hmmlearn import hmm

def fit_hmm_regimes(
    returns: np.ndarray, n_states: int = 2, n_iter: int = 100
) -> tuple[np.ndarray, object]:
    """Fit a Gaussian HMM to return series."""
    X = returns.reshape(-1, 1)
    model = hmm.GaussianHMM(
        n_components=n_states, covariance_type="full", n_iter=n_iter
    )
    model.fit(X)
    states = model.predict(X)
    return states, model
```

See `references/methodology.md` for details on feature selection and state interpretation.

## Crypto-Specific Considerations

### Regime Speed

Crypto regimes change **much faster** than equities:

| Parameter | Equities | Crypto (large cap) | Crypto (micro cap / PumpFun) |
|---|---|---|---|
| ATR lookback | 100–200 bars | 50–100 bars | 20–50 bars |
| ADX period | 14–28 | 10–14 | 7–10 |
| Regime persistence | Weeks–months | Days–weeks | Hours–days |
| Hurst window | 200+ bars | 100 bars | 50 bars |

### Volume as a Regime Signal

In crypto, volume confirms regime quality:
- **High volume + trend** → Strong conviction, ride it
- **Low volume + trend** → Drift, unreliable, reduce size
- **High volume + range** → Distribution or accumulation, watch for breakout
- **Low volume + range** → Dead market, skip

### PumpFun Micro-Regimes

New token launches follow a stereotyped sequence:
1. **Launch pump** (minutes): Vertical move, extreme vol, no mean-reversion
2. **First dump** (minutes–hours): Profit-taking, high vol, trending down
3. **Consolidation** (hours–days): Low vol range, potential mean-reversion
4. **Second wave or death**: Either breaks out again (new trend) or fades to zero

Each micro-regime lasts minutes to hours. Use 1-minute bars with 20–50 bar windows.

## Combined Regime Classification

```python
def classify_regime(
    vol_percentile: float, adx: float, hurst: float,
    trend_dir: int
) -> dict[str, str]:
    """Classify into the 4-quadrant model."""
    vol_regime = (
        "low" if vol_percentile < 0.30
        else "high" if vol_percentile > 0.70
        else "normal"
    )
    trend_regime = (
        "trending" if adx > 25
        else "ranging" if adx < 20
        else "transitional"
    )
    direction = (
        "up" if trend_dir > 0
        else "down" if trend_dir < 0
        else "neutral"
    )
    mr_regime = (
        "mean_reverting" if hurst < 0.4
        else "trending" if hurst > 0.6
        else "random"
    )
    return {
        "volatility": vol_regime,
        "trend": trend_regime,
        "direction": direction,
        "mean_reversion": mr_regime,
        "quadrant": f"{vol_regime}_vol_{trend_regime}",
    }
```

## Strategy Adaptation

See `references/strategy_adaptation.md` for the full regime-strategy matrix.

Quick reference:

| Current Regime | Action |
|---|---|
| Low vol + trending up | Full size trend-following, tight stops |
| High vol + trending | Half size momentum, wide stops |
| Low vol + ranging | Mean-reversion / grid strategies |
| High vol + ranging | Reduce to 25% size or sit out |
| Regime transition | Flatten or reduce to minimum size |

## Integration with Other Skills

- **`pandas-ta`**: Compute ATR, ADX, Bollinger Bands, EMAs
- **`volatility-modeling`**: Advanced vol forecasting (GARCH, realized vol)
- **`strategy-framework`**: Route signals through regime filter before execution
- **`position-sizing`**: Scale position size by regime volatility
- **`risk-management`**: Adjust portfolio risk limits per regime

## Files

### References
- `references/methodology.md` — Detailed math for Hurst exponent, HMM, change-point detection, and volatility estimation methods
- `references/strategy_adaptation.md` — Full regime-strategy matrix with position sizing, stop adaptation, and PumpFun micro-regime playbook

### Scripts
- `scripts/detect_regime.py` — Compute regime indicators on live or demo data, classify into 4-quadrant model
- `scripts/regime_backtest.py` — Compare regime-adaptive vs static strategy on synthetic data with clear regime transitions
