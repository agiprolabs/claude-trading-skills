# Correlation Analysis — Portfolio Applications Reference

## Diversification Analysis

### Average Pairwise Correlation

The simplest measure of portfolio diversification:

```python
import numpy as np

def average_pairwise_correlation(corr_matrix: np.ndarray) -> float:
    """Average off-diagonal correlation in the matrix."""
    n = corr_matrix.shape[0]
    mask = ~np.eye(n, dtype=bool)
    return corr_matrix[mask].mean()
```

**Interpretation**:
- avg_corr < 0.3: well diversified
- avg_corr 0.3–0.6: moderate diversification
- avg_corr > 0.6: poorly diversified — assets move together

### Effective Number of Independent Bets

```
N_eff = 1 / (1/N + (1 - 1/N) * avg_corr)
```

Alternatively, from eigenvalues of the correlation matrix:

```python
def effective_n_eigenvalue(corr_matrix: np.ndarray) -> float:
    """Effective N from eigenvalue entropy."""
    eigenvalues = np.linalg.eigvalsh(corr_matrix)
    eigenvalues = eigenvalues[eigenvalues > 0]  # numerical stability
    proportions = eigenvalues / eigenvalues.sum()
    entropy = -np.sum(proportions * np.log(proportions))
    return np.exp(entropy)
```

| Portfolio | N Assets | N_eff | Assessment |
|-----------|----------|-------|------------|
| All altcoins | 10 | 2.1 | Poor — essentially 2 independent bets |
| Mixed crypto | 10 | 4.3 | Moderate |
| Crypto + stables | 10 | 6.8 | Good diversification |

### Diversification Ratio

```
DR = (Σ w_i * σ_i) / σ_portfolio
```

- DR = 1: no diversification benefit (all perfectly correlated)
- DR > 1: diversification is reducing portfolio volatility
- Higher DR = better diversified

```python
def diversification_ratio(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """Ratio of weighted average vol to portfolio vol."""
    vols = np.sqrt(np.diag(cov_matrix))
    weighted_avg_vol = np.dot(weights, vols)
    portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
    return weighted_avg_vol / portfolio_vol
```

## Correlation-Adjusted Position Sizing

### Problem

Adding a new position that is correlated with existing holdings increases portfolio risk more than the individual position's risk suggests.

### Adjustment Formula

```python
def adjusted_position_size(
    base_size: float,
    new_asset_corr_with_portfolio: float
) -> float:
    """Reduce position size based on correlation with existing portfolio.

    Args:
        base_size: Size without correlation adjustment.
        new_asset_corr_with_portfolio: Correlation of new asset with
            the existing portfolio return stream.

    Returns:
        Adjusted position size (smaller when correlation is high).
    """
    adjustment = np.sqrt(max(0, 1 - new_asset_corr_with_portfolio ** 2))
    return base_size * adjustment
```

| Correlation with Portfolio | Adjustment Factor | Effect |
|---------------------------|-------------------|--------|
| 0.0 | 1.00 | No reduction — fully independent |
| 0.3 | 0.95 | 5% reduction |
| 0.5 | 0.87 | 13% reduction |
| 0.7 | 0.71 | 29% reduction |
| 0.9 | 0.44 | 56% reduction |

### Portfolio-Level Correlation

Compute the correlation of a new asset with the existing portfolio return:

```python
def asset_portfolio_correlation(
    asset_returns: np.ndarray,
    portfolio_returns: np.ndarray
) -> float:
    """Correlation between a candidate asset and existing portfolio."""
    return np.corrcoef(asset_returns, portfolio_returns)[0, 1]
```

## Pairs Trading from Correlation

### Candidate Selection

1. Compute correlation matrix for asset universe
2. Filter pairs with correlation > 0.8
3. Verify economic rationale (same sector, similar mechanics)
4. Test for cointegration (see `cointegration-analysis` skill)

### Spread Construction

```python
def compute_spread(
    prices_a: pd.Series,
    prices_b: pd.Series,
    lookback: int = 60
) -> pd.Series:
    """Z-score of the log price ratio."""
    ratio = np.log(prices_a / prices_b)
    mean = ratio.rolling(lookback).mean()
    std = ratio.rolling(lookback).std()
    return (ratio - mean) / std
```

### Trading Rules

| Signal | Z-Score | Action |
|--------|---------|--------|
| Entry long spread | z < -2.0 | Buy A, sell B |
| Entry short spread | z > +2.0 | Sell A, buy B |
| Exit | abs(z) < 0.5 | Close both legs |
| Stop loss | abs(z) > 3.5 | Close — relationship may be breaking |

### Risk of Pairs Trading

- **Correlation breakdown**: previously correlated assets diverge permanently
- **Regime change**: new market regime invalidates historical relationship
- **Execution**: crypto pairs have different liquidity; slippage on one leg
- **Always test cointegration**, not just correlation — see `cointegration-analysis`

## Risk Decomposition

### Portfolio Variance Formula

```
σ²_p = Σ_i Σ_j w_i * w_j * σ_i * σ_j * ρ_ij
     = w^T * Σ * w
```

where Σ is the covariance matrix.

### Marginal Contribution to Risk (MCTR)

```python
def marginal_contribution_to_risk(
    weights: np.ndarray,
    cov_matrix: np.ndarray
) -> np.ndarray:
    """Each asset's marginal contribution to portfolio volatility."""
    portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
    return (cov_matrix @ weights) / portfolio_vol
```

### Component Risk

```
CR_i = w_i * MCTR_i
% contribution = CR_i / σ_portfolio
```

If one asset contributes >50% of portfolio risk, the portfolio is concentrated regardless of the number of holdings.

### Risk Parity

Equalize risk contribution across assets:

```python
from scipy.optimize import minimize

def risk_parity_weights(cov_matrix: np.ndarray) -> np.ndarray:
    """Find weights where each asset contributes equal risk."""
    n = cov_matrix.shape[0]
    target_risk = 1.0 / n

    def objective(w: np.ndarray) -> float:
        port_vol = np.sqrt(w @ cov_matrix @ w)
        mctr = (cov_matrix @ w) / port_vol
        cr = w * mctr
        cr_pct = cr / port_vol
        return np.sum((cr_pct - target_risk) ** 2)

    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
    bounds = [(0.01, 1.0)] * n
    x0 = np.ones(n) / n
    result = minimize(objective, x0, bounds=bounds, constraints=constraints)
    return result.x
```

## Correlation Breakdown Detection

### Z-Score Monitoring

```python
def correlation_regime_monitor(
    rolling_corr: pd.Series,
    lookback: int = 252
) -> pd.DataFrame:
    """Monitor rolling correlation for regime shifts."""
    mean = rolling_corr.rolling(lookback).mean()
    std = rolling_corr.rolling(lookback).std()
    zscore = (rolling_corr - mean) / std

    df = pd.DataFrame({
        'correlation': rolling_corr,
        'mean': mean,
        'zscore': zscore,
        'regime': 'normal'
    })
    df.loc[zscore > 2.0, 'regime'] = 'high_correlation'
    df.loc[zscore < -2.0, 'regime'] = 'low_correlation'
    return df
```

### Alerts

| Condition | Meaning | Action |
|-----------|---------|--------|
| z > 2.0 | Correlation spike | Reduce correlated positions, increase hedges |
| z < -2.0 | Correlation breakdown | Re-evaluate pairs trades, check for structural change |
| Sustained z > 1.5 | Regime shift | Update correlation estimates, rebalance |

### Correlation Spike During Drawdown

The most dangerous scenario: correlation spikes while portfolio is declining.

```python
def crisis_correlation(
    returns: pd.DataFrame,
    threshold: float = -0.02
) -> pd.DataFrame:
    """Correlation computed only on days when the market is down."""
    market_return = returns.mean(axis=1)
    crisis_mask = market_return < threshold
    crisis_returns = returns[crisis_mask]
    return crisis_returns.corr()
```

Compare crisis correlation vs full-sample correlation. If crisis correlation is materially higher (common in crypto), standard diversification metrics overstate the true benefit.
