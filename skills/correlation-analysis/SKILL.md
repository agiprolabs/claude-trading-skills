---
name: correlation-analysis
description: Cross-asset correlation analysis including rolling correlation, hierarchical clustering, tail dependence, and regime-dependent correlation
---

# Correlation Analysis

Cross-asset correlation analysis for diversification assessment, risk management, pairs trading signal generation, and portfolio construction.

## Why Correlation Matters

Correlation measures how assets move together. In crypto markets this is critical for:

- **Diversification**: holding correlated assets provides no diversification benefit — you are effectively holding one concentrated position
- **Risk management**: portfolio risk depends on the correlation structure, not just individual asset volatility
- **Pairs trading**: highly correlated assets that temporarily diverge create mean-reversion opportunities
- **Portfolio construction**: optimal allocation requires accurate correlation estimates
- **Crash protection**: understanding tail dependence reveals whether assets crash together

## Correlation Methods

### Pearson Correlation

Linear correlation assuming normality. Most common but least robust for crypto.

```python
import pandas as pd
import numpy as np

# Always compute on returns, never on prices
returns_a = prices_a.pct_change().dropna()
returns_b = prices_b.pct_change().dropna()

pearson_corr = returns_a.corr(returns_b)  # default is Pearson
```

- **Range**: -1 (perfect inverse) to +1 (perfect co-movement)
- **Assumes**: linear relationship, normally distributed returns, no outliers
- **Limitation**: crypto returns are heavy-tailed — Pearson underestimates extreme co-movement

### Spearman Rank Correlation

Converts values to ranks, then computes Pearson on ranks. Captures monotonic (not just linear) relationships.

```python
spearman_corr = returns_a.corr(returns_b, method='spearman')
```

- More robust to outliers and non-linear relationships
- Better for crypto due to heavy-tailed return distributions
- Slightly lower power than Pearson when normality holds

### Kendall Tau Correlation

Counts concordant vs discordant pairs. Most robust to outliers.

```python
kendall_corr = returns_a.corr(returns_b, method='kendall')
```

- Most robust to outliers of the three methods
- Computationally slower on large datasets
- Best for small samples or heavily skewed data

## Rolling Correlation

Static correlation hides regime changes. Rolling correlation reveals how relationships evolve.

### Window-Based Rolling Correlation

```python
# Rolling Pearson correlation
rolling_corr = returns_a.rolling(window=60).corr(returns_b)

# Multiple windows for different time horizons
windows = {
    'short': 20,    # ~1 month of trading days
    'medium': 60,   # ~3 months
    'long': 120,    # ~6 months
}
for label, w in windows.items():
    df[f'corr_{label}'] = returns_a.rolling(w).corr(returns_b)
```

### EWMA Correlation

Exponentially weighted — more responsive to recent changes.

```python
def ewma_correlation(x: pd.Series, y: pd.Series, span: int = 60) -> pd.Series:
    """Compute EWMA correlation between two return series."""
    cov_xy = x.mul(y).ewm(span=span).mean() - x.ewm(span=span).mean() * y.ewm(span=span).mean()
    std_x = x.ewm(span=span).std()
    std_y = y.ewm(span=span).std()
    return cov_xy / (std_x * std_y)
```

### Typical Windows

| Window | Days | Use Case |
|--------|------|----------|
| Short  | 20   | Tactical trading, pairs entry/exit |
| Medium | 60   | Strategy allocation, regime detection |
| Long   | 120  | Portfolio construction, strategic allocation |

## Correlation Matrix Analysis

### Computing the Full Matrix

```python
# Build return matrix for multiple assets
returns = pd.DataFrame({
    'BTC': btc_returns,
    'ETH': eth_returns,
    'SOL': sol_returns,
    'AVAX': avax_returns,
})

# Correlation matrix (Pearson)
corr_matrix = returns.corr()

# Spearman (better for crypto)
spearman_matrix = returns.corr(method='spearman')
```

### Eigenvalue Decomposition

Decompose the correlation matrix to identify driving factors.

```python
eigenvalues, eigenvectors = np.linalg.eigh(corr_matrix.values)

# Sort descending
idx = eigenvalues.argsort()[::-1]
eigenvalues = eigenvalues[idx]
eigenvectors = eigenvectors[:, idx]

# First eigenvalue = market factor (explains most variance)
# Subsequent eigenvalues = sector/style factors
market_factor_pct = eigenvalues[0] / eigenvalues.sum() * 100
```

- **First eigenvector**: the market factor — when this dominates (>60% variance), everything moves together
- **Subsequent eigenvectors**: sector or style factors
- **Small eigenvalues**: noise / idiosyncratic risk

### Minimum Variance Portfolio

```python
from numpy.linalg import inv

cov_matrix = returns.cov()
ones = np.ones(len(cov_matrix))
inv_cov = inv(cov_matrix.values)

# Minimum variance weights
weights = inv_cov @ ones / (ones @ inv_cov @ ones)
```

## Hierarchical Clustering

Group assets by correlation similarity to identify natural clusters.

```python
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

# Convert correlation to distance
dist_matrix = np.sqrt(2 * (1 - corr_matrix.values))
np.fill_diagonal(dist_matrix, 0)

# Hierarchical clustering
condensed = squareform(dist_matrix)
linkage_matrix = linkage(condensed, method='ward')

# Cut at threshold to get clusters
clusters = fcluster(linkage_matrix, t=1.0, criterion='distance')
```

**Applications**:
- **Sector detection**: assets in the same cluster behave similarly
- **Diversification**: select one asset per cluster for maximum diversification
- **Risk allocation**: allocate risk budget across clusters, not individual assets

## Tail Dependence

Normal correlation understates co-movement during crashes. Tail dependence measures how often assets experience extreme returns simultaneously.

### Lower Tail Dependence

```python
def tail_dependence(x: pd.Series, y: pd.Series, quantile: float = 0.05) -> float:
    """Estimate lower tail dependence coefficient.

    Measures P(Y < q | X < q) for quantile q.
    Higher values mean assets crash together more often.
    """
    threshold_x = x.quantile(quantile)
    threshold_y = y.quantile(quantile)
    joint_extreme = ((x < threshold_x) & (y < threshold_y)).sum()
    marginal_extreme = (x < threshold_x).sum()
    return joint_extreme / marginal_extreme if marginal_extreme > 0 else 0.0
```

### Crypto-Specific Tail Behavior

In crypto markets, tail dependence typically exceeds normal correlation:
- **Normal correlation** of 0.6 between two altcoins might have **tail dependence** of 0.8
- During market panics, correlations spike toward 1.0 across all risk assets
- This means diversification benefits disappear exactly when needed most

## Regime-Dependent Correlation

Correlation is not constant — it changes with market regime.

| Regime | Typical Correlation | Implication |
|--------|-------------------|-------------|
| Bull (trending up) | 0.4–0.7 | Moderate — some diversification works |
| Range-bound | 0.2–0.5 | Lower — best diversification environment |
| Bear (crash) | 0.8–0.95 | Very high — diversification fails |
| Recovery | 0.5–0.7 | Declining from crash highs |

### Detecting Correlation Regime Shifts

```python
def correlation_zscore(rolling_corr: pd.Series, lookback: int = 252) -> pd.Series:
    """Z-score of rolling correlation vs its own history."""
    mean = rolling_corr.rolling(lookback).mean()
    std = rolling_corr.rolling(lookback).std()
    return (rolling_corr - mean) / std

# Flag regime shift when z-score exceeds threshold
zscore = correlation_zscore(rolling_corr_60d)
regime_shift = zscore.abs() > 2.0
```

## Crypto-Specific Correlation Patterns

### Typical Correlation Ranges

| Pair | Normal Range | Notes |
|------|-------------|-------|
| BTC / ETH | 0.7–0.9 | Highest among majors |
| BTC / SOL | 0.6–0.85 | SOL more volatile, slightly less correlated |
| BTC / Altcoin | 0.5–0.8 | Varies by market cap and sector |
| Meme / BTC | 0.2–0.5 | Lower normal correlation |
| Meme / Meme | 0.1–0.4 | Low normal but high tail dependence |
| Stablecoin / BTC | -0.1–0.1 | Should be near zero |

### Key Observations

- Most altcoins are highly correlated with BTC (0.6–0.9) — the market factor dominates
- Meme and PumpFun tokens show lower normal correlation but higher tail dependence
- SOL ecosystem tokens correlate strongly with SOL price
- Stablecoins should be uncorrelated with risk assets — if correlation appears, investigate (depeg risk)
- Correlation tends to increase during high-volatility regimes
- New token launches may show temporarily low correlation until price discovery stabilizes

## Integration with Other Skills

- **risk-management**: use correlation to compute portfolio-level VaR and stress scenarios
- **portfolio-analytics**: correlation matrix feeds optimal allocation algorithms
- **regime-detection**: correlation regime shifts are an input to regime classification
- **cointegration-analysis**: pairs with high correlation are candidates for cointegration testing
- **position-sizing**: correlation-adjusted sizing prevents correlated concentration

## Files

### References
- `references/methodology.md` — Correlation formulas, statistical tests, estimation methods
- `references/portfolio_applications.md` — Diversification metrics, pairs trading, risk decomposition

### Scripts
- `scripts/correlation_matrix.py` — Multi-asset correlation matrix, clustering, diversification metrics
- `scripts/rolling_correlation.py` — Rolling correlation, regime detection, tail dependence analysis
