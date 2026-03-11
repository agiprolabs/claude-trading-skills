---
name: volatility-modeling
description: Volatility estimation, forecasting, and regime classification using GARCH, EWMA, realized volatility, and volatility cones
---

# Volatility Modeling

Volatility — the magnitude of price fluctuations — is arguably the single most
important quantity in trading.  It drives position sizing, stop placement, option
pricing, and regime detection.  This skill covers estimation, forecasting, and
practical application of volatility in crypto markets.

## Why Volatility Matters

| Use Case | How Volatility Is Used |
|---|---|
| **Position sizing** | Scale position inversely with vol so each trade risks a consistent dollar amount |
| **Stop placement** | ATR-based stops widen in high-vol regimes, tighten in low-vol |
| **Strategy selection** | Mean-reversion works in low vol; momentum works in high vol |
| **Risk budgeting** | Vol-target portfolios maintain constant portfolio-level risk |
| **Regime detection** | Vol regime shifts signal changing market dynamics |
| **Option pricing** | Implied vs realized vol gap creates trading opportunities |

## Types of Volatility

### Historical (Realized) Volatility
Computed from observed past returns.  The most common and directly measurable
form.  Multiple estimators exist with different statistical efficiency.

### Implied Volatility
Derived from option prices via Black-Scholes or similar models.  Limited in
crypto DeFi where liquid options markets are sparse, but available on Deribit
for BTC/ETH.

### Forecast Volatility
Predicted future volatility from models like EWMA or GARCH.  Used for
forward-looking position sizing and risk budgets.

---

## Estimation Methods

### 1. Close-to-Close (Standard Deviation of Log Returns)

The simplest estimator.  Compute the standard deviation of log returns and
annualize.

```python
import numpy as np

log_returns = np.log(closes[1:] / closes[:-1])
vol_daily = np.std(log_returns, ddof=1)
vol_annual = vol_daily * np.sqrt(365)  # crypto trades 365 days
```

- **Pros**: Simple, widely understood.
- **Cons**: Uses only close prices — ignores intraday range.

### 2. Parkinson (High-Low Range)

Uses the daily high-low range, which is ~5x more statistically efficient than
close-to-close.

```python
hl_ratio = np.log(highs / lows)
vol_parkinson = np.sqrt(np.mean(hl_ratio**2) / (4 * np.log(2))) * np.sqrt(365)
```

- **Pros**: More efficient, captures intraday moves.
- **Cons**: Downward bias with discrete sampling; ignores close-to-close jumps.

### 3. Garman-Klass (OHLC)

The most efficient single-day OHLC estimator.

```python
hl = np.log(highs / lows)
co = np.log(closes / opens)
gk = np.mean(0.5 * hl**2 - (2 * np.log(2) - 1) * co**2)
vol_gk = np.sqrt(gk) * np.sqrt(365)
```

- **Pros**: Best efficiency among OHLC estimators.
- **Cons**: Assumes no drift; sensitive to opening gaps.

### 4. Yang-Zhang

Combines overnight (close-to-open) and open-to-close components.  Handles
gaps properly.  Less relevant for 24/7 crypto but useful for tokens with
sporadic trading.

### 5. EWMA (Exponentially Weighted Moving Average)

RiskMetrics approach — no parameters to estimate beyond λ.

```python
lam = 0.94  # RiskMetrics default for daily
ewma_var = np.zeros(len(returns))
ewma_var[0] = returns[0] ** 2
for t in range(1, len(returns)):
    ewma_var[t] = lam * ewma_var[t - 1] + (1 - lam) * returns[t - 1] ** 2
vol_ewma = np.sqrt(ewma_var) * np.sqrt(365)
```

- λ = 0.94 for daily data (RiskMetrics).
- λ = 0.97 for weekly data.
- Higher λ → smoother, slower reaction to new information.

### 6. GARCH(1,1)

The workhorse autoregressive volatility model.  Captures volatility clustering.

```
σ²_t = ω + α · r²_{t-1} + β · σ²_{t-1}
```

- **ω**: long-run variance weight.
- **α**: reaction to recent shock (typically 0.05–0.15 for crypto).
- **β**: persistence (typically 0.80–0.90 for crypto).
- **α + β < 1**: stationarity constraint.
- **Long-run variance**: ω / (1 − α − β).

Estimated via maximum likelihood.  See `references/estimators.md` for details.

---

## Volatility Cones

Volatility cones show the percentile distribution of realized volatility at
different lookback windows, revealing whether current vol is historically
high or low.

### Construction
1. Get 1+ years of daily data.
2. For each lookback window (5, 10, 20, 60, 120 days):
   - Compute rolling realized volatility.
   - Extract percentiles: 5th, 25th, 50th, 75th, 95th.
3. Plot percentiles vs window length — the "cone" shape.
4. Overlay current realized vol at each window.

### Interpretation
- **Current vol > 75th percentile**: historically elevated — expect mean reversion.
- **Current vol < 25th percentile**: historically compressed — expect expansion.
- **Cone narrowing at longer windows**: vol mean-reverts over longer horizons.

See `references/volatility_cones.md` for full methodology and worked examples.

---

## Crypto Volatility Characteristics

Crypto vol differs from traditional assets in important ways:

| Characteristic | Detail |
|---|---|
| **Level** | 50–150% annualized is typical; TradFi equities are 15–25% |
| **Clustering** | Strong — high-vol days cluster together |
| **Weekday patterns** | Weekend vol often lower but weekend gaps can be large |
| **Volume correlation** | Vol and volume are positively correlated |
| **Regime dependence** | Bull market vol ≠ bear market vol; ranges are different |
| **Mean reversion** | Vol mean-reverts more reliably than price |
| **Tail risk** | Fat tails — more extreme moves than normal distribution predicts |

### Regime Classification by Volatility

| Regime | Annualized Vol Range | Characteristics |
|---|---|---|
| Low vol | < 40% | Range-bound, mean reversion works |
| Normal vol | 40–80% | Trending possible, balanced strategies |
| High vol | 80–120% | Strong trends or sharp reversals |
| Crisis vol | > 120% | Liquidation cascades, reduced position size |

---

## Volatility Forecasting

### EWMA Forecast
Simple and effective.  The current EWMA variance estimate *is* the 1-step
forecast.  Multi-step forecasts are flat (same as 1-step).

### GARCH Forecast
GARCH produces a term structure of variance forecasts:

```
σ²_{t+h} = V_L + (α + β)^h · (σ²_t − V_L)
```

Where V_L = ω / (1 − α − β) is the long-run variance.

- Short-horizon forecasts reflect current conditions.
- Long-horizon forecasts converge to long-run variance.
- The speed of convergence depends on α + β (persistence).

See `scripts/vol_forecast.py` for a working implementation.

---

## Practical Applications

### Position Sizing with Volatility
```python
# Vol-target position sizing
target_vol = 0.02  # 2% daily portfolio vol target
current_vol = 0.05  # 5% daily asset vol (annualized ~95%)
weight = target_vol / current_vol  # = 0.40 → 40% allocation
```

See the `position-sizing` skill for complete integration.

### ATR-Based Stop Placement
```python
atr_14 = talib.ATR(highs, lows, closes, timeperiod=14)
stop_distance = 2.0 * atr_14[-1]  # 2x ATR stop
stop_price = entry_price - stop_distance  # for longs
```

### Vol-Regime Strategy Selection
```python
vol_percentile = current_vol_percentile(token, window=30)
if vol_percentile < 25:
    strategy = "mean_reversion"
elif vol_percentile > 75:
    strategy = "momentum_breakout"
else:
    strategy = "balanced"
```

---

## Files

### References
| File | Description |
|---|---|
| `references/estimators.md` | Full derivations and details for all volatility estimators |
| `references/volatility_cones.md` | Cone construction methodology and interpretation guide |

### Scripts
| File | Description |
|---|---|
| `scripts/estimate_volatility.py` | Multi-estimator volatility computation with cone analysis |
| `scripts/vol_forecast.py` | EWMA and GARCH forecasting with term structure output |

---

## Related Skills

- **`regime-detection`** — Classify market regimes using volatility as a key input.
- **`position-sizing`** — Scale positions inversely with volatility.
- **`risk-management`** — Portfolio-level vol targeting and risk budgets.
- **`pandas-ta`** — ATR and Bollinger Bands are volatility-based indicators.
- **`custom-indicators`** — Build crypto-specific volatility indicators.

---

## Dependencies

```bash
uv pip install pandas numpy scipy
```

Optional for live data:
```bash
uv pip install httpx
```
