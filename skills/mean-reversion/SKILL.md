---
name: mean-reversion
description: Mean-reversion strategy tools including Hurst exponent, half-life estimation, z-score signals, ADF testing, and Ornstein-Uhlenbeck modeling
---

# Mean Reversion

Mean reversion is the statistical tendency for prices, spreads, or other financial variables to return toward a long-run average after deviating from it. A mean-reverting series overshoots its mean, then corrects back -- creating predictable oscillations that can be traded.

## When Mean Reversion Works

- **Ranging markets**: Sideways price action with clear support/resistance
- **Pairs spreads**: Spread between cointegrated assets reverts to equilibrium
- **Oversold/overbought extremes**: RSI, Bollinger Band, or z-score extremes in stationary series
- **Funding rate arbitrage**: Perpetual funding rates revert to baseline
- **Stablecoin depegs**: Classic mean-reversion opportunity (peg = known mean)
- **Post-dump recovery**: Brief mean-reversion windows after initial PumpFun dumps

## When Mean Reversion Fails

- Strong trending markets (most crypto most of the time)
- Regime changes: what was stationary becomes non-stationary
- Structural breaks: token migration, protocol upgrade, delistings
- Low liquidity: wide spreads consume mean-reversion profits

---

## Testing for Mean Reversion

Before trading mean reversion, you must statistically confirm the series is mean-reverting. Three complementary tests:

### 1. Augmented Dickey-Fuller (ADF) Test

Tests the null hypothesis that a series has a unit root (non-stationary).

```python
from scipy import stats
import numpy as np

def adf_test(series: np.ndarray, max_lag: int = 0) -> dict:
    """Run ADF test. Reject null (p < 0.05) → stationary → mean-reverting."""
    # See references/statistical_tests.md for full implementation
    # Use statsmodels.tsa.stattools.adfuller for production
    pass
```

- **p < 0.01**: Strong evidence of stationarity
- **p < 0.05**: Evidence of stationarity
- **p > 0.10**: Cannot reject unit root -- likely non-stationary

### 2. Hurst Exponent

Measures the long-range dependence of a time series.

| Hurst Value | Interpretation | Trading Implication |
|-------------|---------------|---------------------|
| H < 0.5     | Mean-reverting | Trade mean reversion |
| H = 0.5     | Random walk    | No edge             |
| H > 0.5     | Trending       | Trade momentum       |

```python
def hurst_exponent(series: np.ndarray) -> float:
    """Compute Hurst exponent via R/S method. H < 0.5 → mean-reverting."""
    # See references/statistical_tests.md for full R/S algorithm
    pass
```

### 3. Variance Ratio Test

Compares variance of multi-period returns to single-period variance.

- **VR < 1**: Negative autocorrelation (mean-reverting)
- **VR = 1**: Random walk
- **VR > 1**: Positive autocorrelation (trending)

```python
def variance_ratio(series: np.ndarray, q: int = 5) -> float:
    """Compute variance ratio at horizon q. VR < 1 → mean-reverting."""
    returns = np.diff(np.log(series))
    var_1 = np.var(returns)
    returns_q = np.diff(np.log(series[::q]))
    var_q = np.var(returns_q)
    return var_q / (q * var_1)
```

See `references/statistical_tests.md` for complete implementations and interpretation guides.

---

## Half-Life Estimation

The half-life tells you how many periods it takes for a deviation to decay to half its size. This is the single most important parameter for mean-reversion trading.

### AR(1) Regression Method

Fit the autoregressive model: `delta_X_t = alpha + beta * X_{t-1} + epsilon`

```python
def half_life(series: np.ndarray) -> float:
    """Estimate mean-reversion half-life from AR(1) regression.

    Returns:
        Half-life in periods. Negative means non-mean-reverting.
    """
    y = np.diff(series)
    x = series[:-1]
    x = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(x, y, rcond=None)[0][1]
    if beta >= 0:
        return -1.0  # Not mean-reverting
    return -np.log(2) / np.log(1 + beta)
```

### Using Half-Life

| Parameter | Rule of Thumb |
|-----------|--------------|
| Lookback window | 2x half-life |
| Holding period | 1x half-life |
| Maximum hold | 3x half-life (stop) |
| Signal recalc | 0.5x half-life |

---

## Z-Score Signal Framework

The z-score normalizes the deviation from the mean, providing standardized entry/exit signals.

```
z = (price - rolling_mean) / rolling_std
```

### Signal Rules

| Condition | Signal | Action |
|-----------|--------|--------|
| z < -2.0  | Buy    | Enter long (price below mean) |
| z > +2.0  | Sell   | Enter short (price above mean) |
| z crosses 0 | Exit | Close position (returned to mean) |
| abs(z) > 3.0 | Stop | Close position (reversion failed) |

### Lookback Window

Set the rolling window to approximately **2x the half-life**:

```python
def z_score_signals(
    prices: np.ndarray,
    lookback: int,
    entry_z: float = 2.0,
    exit_z: float = 0.0,
    stop_z: float = 3.0,
) -> np.ndarray:
    """Generate z-score-based mean-reversion signals.

    Returns:
        Array of signals: 1 (long), -1 (short), 0 (flat).
    """
    rolling_mean = pd.Series(prices).rolling(lookback).mean().values
    rolling_std = pd.Series(prices).rolling(lookback).std().values
    z = (prices - rolling_mean) / rolling_std
    # See scripts/mean_reversion_test.py for full signal generation
    ...
```

### Position Sizing with Z-Score

Scale position size with z-score magnitude for better risk-adjusted returns:

```python
size = base_size * min(abs(z) / entry_threshold, max_scale)
```

See `references/strategy_design.md` for complete entry/exit framework and sizing.

---

## Ornstein-Uhlenbeck (OU) Process

The OU process is the continuous-time model of mean reversion:

```
dX = theta * (mu - X) * dt + sigma * dW
```

| Parameter | Meaning | Estimation |
|-----------|---------|------------|
| theta     | Speed of mean reversion | From AR(1) beta: theta = -ln(1+beta)/dt |
| mu        | Long-run mean | From AR(1) intercept: mu = -alpha/beta |
| sigma     | Volatility of innovations | Residual std from AR(1) |

### Parameter Estimation

```python
def estimate_ou_params(series: np.ndarray, dt: float = 1.0) -> dict:
    """Estimate OU process parameters from observed series.

    Returns:
        Dict with keys: theta, mu, sigma, half_life.
    """
    y = np.diff(series)
    x = series[:-1]
    x_with_const = np.column_stack([np.ones(len(x)), x])
    params = np.linalg.lstsq(x_with_const, y, rcond=None)[0]
    alpha, beta = params[0], params[1]

    theta = -np.log(1 + beta) / dt
    mu = -alpha / beta if beta != 0 else np.mean(series)
    residuals = y - (alpha + beta * x)
    sigma = np.std(residuals) * np.sqrt(2 * theta / (1 - np.exp(-2 * theta * dt)))

    return {
        "theta": theta,
        "mu": mu,
        "sigma": sigma,
        "half_life": np.log(2) / theta if theta > 0 else -1,
    }
```

---

## Strategy Types

### Single-Asset Mean Reversion

Apply z-score framework directly to a token's price series. Works best on:
- Stablecoins (USDC/USDT spread)
- Tokens in established ranges
- After confirming stationarity with ADF test

### Pairs Trading

Trade the spread between two cointegrated assets:

1. Confirm cointegration (see `cointegration-analysis` skill)
2. Compute spread: `S = Y - beta * X`
3. Apply z-score framework to the spread
4. Go long spread (buy Y, sell X) when z < -2
5. Go short spread (sell Y, buy X) when z > +2

### Statistical Arbitrage

Multi-asset extension of pairs trading:
- Eigenportfolios from PCA of correlated assets
- Trade the smallest eigenvalue portfolios (most mean-reverting)
- Requires larger universe (10+ assets)

---

## Crypto-Specific Considerations

1. **Most crypto trends**: Hurst exponent for BTC, ETH, SOL is typically 0.55-0.70. Raw price mean reversion is rare.
2. **Where to find mean reversion**:
   - Pairs spreads (SOL/ETH ratio, BTC dominance)
   - Funding rates on perpetuals
   - Basis between spot and futures
   - Stablecoin depegs
   - Fee tier spreads across DEXs
3. **Short lookbacks**: Crypto mean reversion has short half-lives (hours to days, not weeks)
4. **Transaction costs**: DEX swap fees (0.25-1%) can eat mean-reversion profits. Factor in slippage.
5. **Regime awareness**: Use `regime-detection` skill to only trade mean reversion in ranging regimes.

---

## Integration with Other Skills

| Skill | Integration |
|-------|------------|
| `cointegration-analysis` | Find cointegrated pairs for pairs trading |
| `pandas-ta` | RSI, Bollinger Bands as mean-reversion indicators |
| `regime-detection` | Filter: only trade MR in ranging regimes |
| `vectorbt` | Backtest mean-reversion strategies |
| `volatility-modeling` | Estimate sigma for OU model |
| `slippage-modeling` | Factor execution costs into P&L estimates |
| `position-sizing` | Size positions using Kelly + z-score scaling |

---

## Files

### References
- `references/statistical_tests.md` -- ADF, Hurst exponent, variance ratio, and half-life estimation with full implementations and interpretation
- `references/strategy_design.md` -- Z-score framework, position sizing, pairs trading setup, risk management, and backtest considerations

### Scripts
- `scripts/mean_reversion_test.py` -- Comprehensive mean-reversion analysis: ADF, Hurst, variance ratio, half-life, OU estimation, z-score signals
- `scripts/pairs_scanner.py` -- Scan multiple assets for mean-reverting pairs: correlation, cointegration, spread analysis, ranking

---

## Quick Start

```bash
# Run mean-reversion analysis on synthetic data
python scripts/mean_reversion_test.py --demo

# Scan for mean-reverting pairs
python scripts/pairs_scanner.py --demo

# Analyze a specific token (requires BIRDEYE_API_KEY)
BIRDEYE_API_KEY=your_key TOKEN_MINT=So11...1 python scripts/mean_reversion_test.py
```

*This skill provides analytical tools and information only. It does not constitute financial advice or trading recommendations.*
