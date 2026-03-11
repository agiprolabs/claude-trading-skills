# Volatility Estimators — Complete Reference

## Notation

| Symbol | Meaning |
|---|---|
| O_i, H_i, L_i, C_i | Open, High, Low, Close on day i |
| r_i = ln(C_i / C_{i-1}) | Log return |
| n | Number of observations in the estimation window |
| N | Annualization factor (365 for daily crypto, 365×24 for hourly) |

---

## 1. Close-to-Close (Standard Deviation)

The baseline estimator.  Uses only closing prices.

**Formula:**

```
r_i = ln(C_i / C_{i-1})
r̄   = (1/n) Σ r_i
σ_CC = sqrt( (1/(n-1)) Σ (r_i - r̄)² ) × sqrt(N)
```

**Worked example** (5 daily closes: 100, 103, 101, 105, 102):

```
r = [ln(103/100), ln(101/103), ln(105/101), ln(102/105)]
  = [0.02956, -0.01961, 0.03883, -0.02899]
r̄ = 0.00495
var = [(0.02461)² + (-0.02456)² + (0.03388)² + (-0.03394)²] / 3
    = 0.001105
σ_daily = sqrt(0.001105) = 0.03324
σ_annual = 0.03324 × sqrt(365) = 0.635 = 63.5%
```

**Properties:**
- Unbiased with ddof=1.
- Statistical efficiency = 1.0 (reference baseline).
- Ignores all intraday information.

---

## 2. Parkinson (High-Low Range)

Uses the daily high-low range.  More efficient because the range captures
intraday volatility that closes miss.

**Formula:**

```
σ²_P = (1 / (4 n ln2)) Σ (ln(H_i / L_i))²
σ_P  = sqrt(σ²_P) × sqrt(N)
```

**Worked example** (3 days, H/L pairs: 105/98, 103/99, 107/100):

```
ln(H/L) = [ln(105/98), ln(103/99), ln(107/100)]
         = [0.0690, 0.0396, 0.0677]
Σ (ln(H/L))² = 0.004761 + 0.001568 + 0.004583 = 0.010912
σ²_P = 0.010912 / (4 × 3 × 0.6931) = 0.010912 / 8.3178 = 0.001312
σ_daily = sqrt(0.001312) = 0.03622
σ_annual = 0.03622 × sqrt(365) = 0.692 = 69.2%
```

**Properties:**
- Efficiency ≈ 5.2 relative to close-to-close.
- Downward bias with discrete sampling (true range is wider than observed).
- Does not account for close-to-close jumps.

---

## 3. Garman-Klass (OHLC)

Uses all four OHLC prices.  The most efficient single-period estimator
assuming no drift and continuous trading.

**Formula:**

```
σ²_GK = (1/n) Σ [ 0.5 (ln(H_i/L_i))² − (2 ln2 − 1)(ln(C_i/O_i))² ]
σ_GK  = sqrt(σ²_GK) × sqrt(N)
```

Note: `2 ln2 − 1 ≈ 0.3863`.

**Worked example** (2 days, OHLC: [100,105,98,103], [103,107,100,101]):

```
Day 1: 0.5×(ln(105/98))² − 0.3863×(ln(103/100))²
      = 0.5×0.004761 − 0.3863×0.000898 = 0.002381 − 0.000347 = 0.002034
Day 2: 0.5×(ln(107/100))² − 0.3863×(ln(101/103))²
      = 0.5×0.004583 − 0.3863×0.000385 = 0.002292 − 0.000149 = 0.002143
σ²_GK = (0.002034 + 0.002143) / 2 = 0.002089
σ_daily = sqrt(0.002089) = 0.04571
σ_annual = 0.04571 × sqrt(365) = 0.873 = 87.3%
```

**Properties:**
- Efficiency ≈ 7.4 relative to close-to-close.
- Assumes no drift (mean return = 0) — reasonable for short windows.
- Sensitive to opening price accuracy.

---

## 4. Yang-Zhang

Combines overnight (close-to-open), open-to-close, and Rogers-Satchell
components.  Handles overnight gaps correctly.

**Formula:**

```
σ²_YZ = σ²_overnight + k × σ²_open-to-close + (1-k) × σ²_RS
k = 0.34 / (1.34 + (n+1)/(n-1))
```

Where σ²_RS is the Rogers-Satchell estimator:

```
σ²_RS = (1/n) Σ [ ln(H/C)×ln(H/O) + ln(L/C)×ln(L/O) ]
```

**Properties:**
- Handles opening jumps (useful for stocks).
- Less relevant for 24/7 crypto markets without gaps.
- Efficiency ≈ 8.0 relative to close-to-close.

---

## 5. EWMA (Exponentially Weighted Moving Average)

RiskMetrics approach.  Recent observations weighted more heavily.

**Formula:**

```
σ²_t = λ × σ²_{t-1} + (1 − λ) × r²_{t-1}
```

**Parameters:**
- λ = 0.94 for daily data (RiskMetrics standard).
- λ = 0.97 for weekly data.
- Higher λ → more smoothing, slower reaction.

**Half-life:** The number of periods for a shock to decay by half:

```
half_life = -ln(2) / ln(λ)
```

- λ = 0.94 → half_life ≈ 11 days.
- λ = 0.97 → half_life ≈ 23 days.

**Properties:**
- No parameters to estimate (just pick λ).
- Reacts to regime changes faster than rolling windows.
- Forecast is flat: E[σ²_{t+h}] = σ²_t for all h.
- Cannot capture mean reversion of vol to long-run level.

**Initialization:** Set σ²_0 = sample variance of first 20 observations.

---

## 6. GARCH(1,1)

Generalized Autoregressive Conditional Heteroskedasticity.

**Formula:**

```
σ²_t = ω + α × ε²_{t-1} + β × σ²_{t-1}
```

Where ε_t = r_t (return shock, assuming zero mean for simplicity).

**Constraints:**
- ω > 0, α ≥ 0, β ≥ 0.
- α + β < 1 (stationarity / finite unconditional variance).

**Long-run (unconditional) variance:**

```
V_L = ω / (1 − α − β)
```

**Multi-step forecast:**

```
E[σ²_{t+h}] = V_L + (α + β)^h × (σ²_t − V_L)
```

Converges to V_L as h → ∞.

**Estimation:** Maximum likelihood with Gaussian or Student-t innovations.

Log-likelihood (Gaussian):

```
L = −(1/2) Σ [ ln(σ²_t) + r²_t / σ²_t ]
```

Optimize over (ω, α, β) using scipy.optimize.minimize with bounds.

**Typical crypto parameters:**

| Parameter | Typical Range | Interpretation |
|---|---|---|
| α | 0.05 – 0.15 | Shock reaction speed |
| β | 0.80 – 0.90 | Persistence |
| α + β | 0.92 – 0.98 | Total persistence |

**Properties:**
- Captures volatility clustering and mean reversion.
- Produces a vol term structure (unlike EWMA).
- Requires numerical optimization.
- Student-t innovations better capture crypto fat tails.

---

## Choosing an Estimator

| Scenario | Recommended Estimator |
|---|---|
| Only closing prices available | Close-to-close |
| OHLC data available, short window | Garman-Klass |
| Need responsive real-time vol | EWMA (λ=0.94) |
| Need forecasts with term structure | GARCH(1,1) |
| Quick percentile-based regime check | Parkinson with rolling window |
| Assets with trading gaps | Yang-Zhang |
