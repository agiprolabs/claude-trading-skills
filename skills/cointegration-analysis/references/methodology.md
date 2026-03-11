# Cointegration — Methodology Reference

## Engle-Granger Two-Step Procedure

### Step 1: OLS Cointegrating Regression

Regress the dependent series Y on the independent series X:

```
Y_t = α + β * X_t + ε_t
```

- α = intercept (long-run mean of spread)
- β = hedge ratio (units of X per unit of Y)
- ε_t = residuals (the spread)

OLS estimates are **super-consistent** for cointegrated series — they converge
faster than the usual √T rate. However, standard errors and t-statistics are
invalid due to non-stationarity.

### Step 2: ADF Test on Residuals

Test the null hypothesis that ε_t has a unit root (not cointegrated):

```
Δε_t = γ * ε_{t-1} + Σ δ_i * Δε_{t-i} + u_t
```

- If γ < 0 and statistically significant → residuals are stationary → cointegrated
- Use AIC or BIC to select lag length

### Critical Values (Engle-Granger)

These differ from standard ADF because the residuals are estimated, not observed.

| Significance | n=2 series | n=3 series | n=4 series |
|---|---|---|---|
| 1% | -3.90 | -4.29 | -4.64 |
| 5% | -3.34 | -3.74 | -4.10 |
| 10% | -3.04 | -3.45 | -3.81 |

For sample sizes < 100, use MacKinnon (1991) surface regression for exact values.
The `statsmodels.tsa.stattools.coint` function handles this automatically.

### Asymmetry Issue

Engle-Granger is not symmetric: regressing Y on X may reject cointegration while
X on Y does not (or vice versa). This occurs because OLS minimizes vertical
residuals, which differ by regression direction.

**Best practice**: Test both directions and use the result with the lower p-value.

```python
from statsmodels.tsa.stattools import coint

t1, p1, _ = coint(y, x)  # Y ~ X
t2, p2, _ = coint(x, y)  # X ~ Y
best_p = min(p1, p2)
```

## Johansen Test

### VAR Representation

Start with a VAR(p) model for an N-dimensional price vector Y_t:

```
Y_t = A_1 * Y_{t-1} + A_2 * Y_{t-2} + ... + A_p * Y_{t-p} + ε_t
```

Rewrite in error correction form:

```
ΔY_t = Π * Y_{t-1} + Σ_{i=1}^{p-1} Γ_i * ΔY_{t-i} + ε_t
```

where Π = (Σ A_i) - I and Γ_i = -(Σ_{j=i+1}^{p} A_j).

### Rank of Π

The rank r of Π determines the number of cointegrating relationships:

- r = 0: No cointegration (all series are independent random walks)
- 0 < r < N: r cointegrating relationships exist
- r = N: All series are stationary (no unit roots)

### Trace Test

Tests H_0: rank ≤ r against H_1: rank > r.

```
λ_trace(r) = -T * Σ_{i=r+1}^{N} ln(1 - λ̂_i)
```

where λ̂_i are ordered eigenvalues of Π.

### Maximum Eigenvalue Test

Tests H_0: rank = r against H_1: rank = r + 1.

```
λ_max(r) = -T * ln(1 - λ̂_{r+1})
```

### Implementation

```python
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import numpy as np

# data: T x N array (each column is a price series)
result = coint_johansen(data, det_order=0, k_ar_diff=1)

# det_order: 0 = no deterministic terms, 1 = constant, 2 = trend
# k_ar_diff: number of lagged differences in VAR

for i in range(data.shape[1]):
    trace = result.lr1[i]
    crit_95 = result.cvt[i, 1]  # 95% critical value
    print(f"r <= {i}: trace={trace:.2f}, crit_95={crit_95:.2f}, "
          f"reject={trace > crit_95}")
```

## Hedge Ratio Estimation

### OLS (Ordinary Least Squares)

```python
from scipy import stats
slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
hedge_ratio = slope
```

- Simple and fast
- Super-consistent for cointegrated series
- Biased in finite samples (errors-in-variables problem)

### TLS (Total Least Squares / Orthogonal Regression)

Minimizes perpendicular distance to the regression line rather than vertical
distance. Better when both X and Y contain measurement error (both are random
walks).

```python
from scipy.linalg import svd
import numpy as np

def total_least_squares(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Estimate hedge ratio using Total Least Squares."""
    X = np.column_stack([x, y])
    X_centered = X - X.mean(axis=0)
    _, _, Vt = svd(X_centered)
    slope = -Vt[-1, 0] / Vt[-1, 1]
    intercept = y.mean() - slope * x.mean()
    return slope, intercept
```

### Dynamic OLS (DOLS)

Adds leads and lags of ΔX to the regression to correct for endogeneity:

```
Y_t = α + β * X_t + Σ_{j=-k}^{k} γ_j * ΔX_{t+j} + ε_t
```

- More efficient than OLS in finite samples
- Standard errors are valid for inference
- Typical choice: k = 1 or k = 2

### Rolling OLS

Captures time-varying hedge ratio:

```python
def rolling_hedge_ratio(x: np.ndarray, y: np.ndarray, window: int = 60) -> np.ndarray:
    """Compute rolling OLS hedge ratio."""
    ratios = np.full(len(x), np.nan)
    for i in range(window, len(x)):
        slope, _, _, _, _ = stats.linregress(x[i-window:i], y[i-window:i])
        ratios[i] = slope
    return ratios
```

## Spread Construction and Testing

### Constructing the Spread

```python
spread = y - hedge_ratio * x - intercept
z_score = (spread - spread.mean()) / spread.std()
```

For rolling applications, use expanding or rolling mean/std:

```python
rolling_mean = spread.rolling(window=60).mean()
rolling_std = spread.rolling(window=60).std()
z_score = (spread - rolling_mean) / rolling_std
```

### Testing Mean Reversion

**ADF Test**: Confirms stationarity of the spread (p < 0.05).

**Hurst Exponent**: Measures long-range dependence.
- H < 0.5: Mean-reverting (lower = stronger reversion)
- H = 0.5: Random walk
- H > 0.5: Trending

```python
def hurst_exponent(series: np.ndarray, max_lag: int = 20) -> float:
    """Estimate Hurst exponent using R/S analysis."""
    lags = range(2, max_lag + 1)
    tau = [np.std(np.subtract(series[lag:], series[:-lag])) for lag in lags]
    log_lags = np.log(lags)
    log_tau = np.log(tau)
    slope, _, _, _, _ = stats.linregress(log_lags, log_tau)
    return slope
```

**Half-Life of Mean Reversion**: From AR(1) model on spread.

```python
def half_life(spread: np.ndarray) -> float:
    """Estimate half-life of mean reversion from AR(1) model."""
    spread_lag = spread[:-1]
    spread_diff = np.diff(spread)
    slope, _, _, _, _ = stats.linregress(spread_lag, spread_diff)
    if slope >= 0:
        return float("inf")  # Not mean-reverting
    return -np.log(2) / np.log(1 + slope)
```

A viable pairs trade typically has a half-life between 5 and 60 days. Shorter
means faster reversion but potentially noisy; longer means capital is tied up.

## References

- Engle, R. F. & Granger, C. W. J. (1987). "Co-Integration and Error Correction"
- Johansen, S. (1991). "Estimation and Hypothesis Testing of Cointegration Vectors"
- MacKinnon, J. G. (1991). "Critical Values for Cointegration Tests"
- Hamilton, J. D. (1994). "Time Series Analysis" — Chapters 19–20
- Vidyamurthy, G. (2004). "Pairs Trading: Quantitative Methods and Analysis"
