# Statistical Tests for Mean Reversion

This reference covers four key tests for detecting mean-reverting behavior in financial time series. Run all four to build conviction before trading a mean-reversion strategy.

---

## Augmented Dickey-Fuller (ADF) Test

### Theory

The ADF test checks whether a time series has a unit root (is non-stationary). The regression model:

```
delta_y_t = alpha + beta * y_{t-1} + sum(gamma_i * delta_y_{t-i}) + epsilon_t
```

- **Null hypothesis (H0)**: beta = 0 (unit root exists, non-stationary)
- **Alternative (H1)**: beta < 0 (no unit root, stationary)

If we reject H0 (p < 0.05), the series is stationary and potentially mean-reverting.

### Lag Selection

Choose the number of augmenting lags using one of:
- **AIC/BIC**: Fit models with 1..max_lag lags, pick lowest information criterion
- **Rule of thumb**: `max_lag = int(np.sqrt(len(series)))`
- **Default**: Start with 1 lag, increase if residuals show autocorrelation

### Implementation

```python
import numpy as np

def adf_test_manual(series: np.ndarray, max_lag: int = 1) -> dict:
    """Manual ADF test. Returns dict with test_statistic, p_value_approx, conclusion."""
    n = len(series)
    y = np.diff(series)
    x_lag = series[:-1]
    start = max_lag
    y_trimmed = y[start:]
    regressors = [np.ones(len(y_trimmed)), x_lag[start:]]
    for lag in range(1, max_lag + 1):
        regressors.append(y[start - lag : n - 1 - lag])
    X = np.column_stack(regressors)
    coeffs = np.linalg.lstsq(X, y_trimmed, rcond=None)[0]
    beta = coeffs[1]
    fitted = X @ coeffs
    sigma2 = np.sum((y_trimmed - fitted) ** 2) / (len(y_trimmed) - len(coeffs))
    cov_matrix = sigma2 * np.linalg.inv(X.T @ X)
    t_stat = beta / np.sqrt(cov_matrix[1, 1])
    # MacKinnon critical values (constant, no trend, n > 250)
    crit = {0.01: -3.43, 0.05: -2.86, 0.10: -2.57}
    p = 0.005 if t_stat < crit[0.01] else 0.03 if t_stat < crit[0.05] else 0.07 if t_stat < crit[0.10] else 0.20
    return {"test_statistic": t_stat, "p_value_approx": p, "critical_values": crit}
```

### Interpretation Guide

| ADF Statistic | p-value | Conclusion | Action |
|---------------|---------|------------|--------|
| < -3.43       | < 0.01  | Strongly stationary | High confidence mean reversion |
| -3.43 to -2.86 | 0.01-0.05 | Stationary | Good for mean reversion |
| -2.86 to -2.57 | 0.05-0.10 | Weakly stationary | Proceed with caution |
| > -2.57       | > 0.10  | Non-stationary | Do not trade mean reversion |

### Common Pitfalls

- ADF has low power on short samples (< 100 data points)
- Structural breaks can fool the test (split test around known breaks)
- A stationary series can still trend locally -- use regime detection

---

## Hurst Exponent (R/S Method)

### Theory

The Hurst exponent H measures long-range dependence. For a time series:
- **H < 0.5**: Anti-persistent (mean-reverting). Past up moves predict future down moves.
- **H = 0.5**: Random walk. No predictable pattern.
- **H > 0.5**: Persistent (trending). Past up moves predict future up moves.

### R/S Algorithm

1. For each subseries length `n` in a range of scales:
   a. Divide the series into `m = N/n` non-overlapping blocks
   b. For each block, compute the mean-adjusted cumulative deviation
   c. R = max(cumulative) - min(cumulative) (range)
   d. S = standard deviation of the block
   e. Compute R/S for each block, take the average
2. Plot log(average R/S) vs log(n)
3. Slope of the line = Hurst exponent

### Implementation

```python
import numpy as np

def hurst_rs(series: np.ndarray, min_window: int = 10) -> float:
    """Compute Hurst exponent using rescaled range (R/S) method."""
    n = len(series)
    max_window = n // 2
    window_sizes = []
    w = min_window
    while w <= max_window:
        window_sizes.append(w)
        w = max(w + 1, int(w * 1.5))
    log_n, log_rs = [], []
    for w in window_sizes:
        rs_block = []
        for i in range(n // w):
            block = series[i * w : (i + 1) * w]
            cumulative = np.cumsum(block - np.mean(block))
            R = np.max(cumulative) - np.min(cumulative)
            S = np.std(block, ddof=1)
            if S > 1e-10:
                rs_block.append(R / S)
        if rs_block:
            log_n.append(np.log(w))
            log_rs.append(np.log(np.mean(rs_block)))
    if len(log_n) < 2:
        return 0.5
    return np.polyfit(log_n, log_rs, 1)[0]
```

### Interpretation

| Hurst Range | Behavior | Strength | Crypto Typical |
|-------------|----------|----------|---------------|
| 0.0 - 0.3   | Strongly mean-reverting | High | Rare (spreads only) |
| 0.3 - 0.45  | Mean-reverting | Moderate | Pairs spreads, funding |
| 0.45 - 0.55 | Random walk | None | Some altcoins |
| 0.55 - 0.70 | Trending | Moderate | BTC, ETH, SOL |
| 0.70 - 1.0  | Strongly trending | High | Meme coins, breakouts |

### Data Requirements

- Minimum 100 data points for a rough estimate
- 500+ points for a reliable estimate
- Use returns (not prices) for raw assets; use price levels for spreads
- Recalculate periodically -- Hurst changes with regime

---

## Variance Ratio Test

### Theory

If a series is a random walk, the variance of q-period returns should be q times the variance of 1-period returns. The variance ratio:

```
VR(q) = Var(r_t(q)) / (q * Var(r_t(1)))
```

- **VR < 1**: Negative autocorrelation (mean-reverting)
- **VR = 1**: Random walk
- **VR > 1**: Positive autocorrelation (trending)

### Implementation

```python
import numpy as np
from scipy.stats import norm

def variance_ratio(series: np.ndarray, q: int = 5) -> dict:
    """Compute variance ratio and Lo-MacKinlay z-statistic."""
    log_prices = np.log(series)
    returns = np.diff(log_prices)
    n = len(returns)
    var_1 = np.var(returns, ddof=1)
    returns_q = log_prices[q:] - log_prices[:-q]
    var_q = np.var(returns_q, ddof=1)
    vr = var_q / (q * var_1)
    z_stat = (vr - 1) / np.sqrt(2 * (q - 1) / (3 * n))
    p_value = 2 * (1 - norm.cdf(abs(z_stat)))
    return {"vr": vr, "z_stat": z_stat, "p_value": p_value}
```

### Multi-Horizon Analysis

Test at multiple horizons to see where mean reversion is strongest:

```python
for q in [2, 5, 10, 20, 50]:
    result = variance_ratio(prices, q=q)
    print(f"  q={q:3d}: VR={result['vr']:.3f}  z={result['z_stat']:+.2f}  p={result['p_value']:.4f}")
```

---

## Half-Life from AR(1) Regression

### Theory

For a mean-reverting process, the half-life is the expected time for a deviation to decay to half its original size. From the AR(1) model:

```
delta_X_t = alpha + beta * X_{t-1} + epsilon
```

- beta must be **negative** for mean reversion
- Half-life = `-ln(2) / ln(1 + beta)`
- For small beta: half-life is approximately `-ln(2) / beta`

### Implementation

```python
import numpy as np

def estimate_half_life(series: np.ndarray) -> dict:
    """Estimate half-life from AR(1): delta_X = alpha + beta*X_{t-1} + eps."""
    y = np.diff(series)
    x = series[:-1]
    X = np.column_stack([np.ones(len(x)), x])
    coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha, beta = coeffs[0], coeffs[1]
    if beta >= 0:
        return {"half_life": -1, "beta": beta, "mu": np.mean(series)}
    half_life = -np.log(2) / np.log(1 + beta)
    mu = -alpha / beta
    return {"half_life": half_life, "beta": beta, "mu": mu}
```

### Practical Guidelines

| Half-Life | Timeframe | Suitability |
|-----------|-----------|------------|
| < 1 period | Very fast | Likely noise; high transaction costs |
| 1-5 periods | Fast | Good for HFT with low fees |
| 5-20 periods | Moderate | Sweet spot for most strategies |
| 20-50 periods | Slow | Viable but ties up capital |
| > 50 periods | Very slow | Impractical for most traders |

- Half-life should be **shorter than your patience** and **longer than your transaction costs** can tolerate
- Use the half-life to set your lookback window (2x), holding period (1x), and stop duration (3x)
