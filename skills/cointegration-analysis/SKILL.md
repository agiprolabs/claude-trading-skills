---
name: cointegration-analysis
description: Cointegration testing for pairs trading using Engle-Granger, Johansen, and rolling stability analysis
---

# Cointegration Analysis

Cointegration testing identifies pairs of assets that share a long-run equilibrium
relationship, enabling statistical arbitrage and pairs trading strategies.

## What Is Cointegration?

Two price series are **cointegrated** when they are individually non-stationary
(random walks) but a linear combination of them is stationary (mean-reverting).
Intuitively, the prices may wander apart temporarily but are pulled back to an
equilibrium spread over time.

### Cointegration vs Correlation

| Property | Correlation | Cointegration |
|---|---|---|
| Measures | Short-term co-movement | Long-run equilibrium |
| Stationarity | Requires stationary returns | Works with non-stationary prices |
| Time horizon | Can change rapidly | Stable over months/years |
| Trading use | Momentum/trend signals | Mean-reversion pairs trades |
| Failure mode | Breaks in regime changes | Breaks on structural shifts |

Two assets can be highly correlated but not cointegrated (e.g., two unrelated
uptrends). Conversely, cointegrated assets may have low short-term correlation
during temporary divergences — which is exactly when pairs trades are entered.

### Why It Matters

- **Pairs trading**: Long the underperformer, short the outperformer, profit on convergence
- **Statistical arbitrage**: Systematic mean-reversion on spread z-scores
- **Spread trading**: Trade the spread directly as a synthetic instrument
- **Risk hedging**: Cointegrated hedge ratios minimize tracking error over time

## Methods

### 1. Engle-Granger Two-Step

The most common approach for two series.

**Step 1** — Regress Y on X using OLS:

```
Y_t = α + β * X_t + ε_t
```

**Step 2** — Test the residuals ε_t for stationarity using the ADF test.

- If residuals are stationary (p < 0.05) → Y and X are cointegrated
- β is the **hedge ratio** for the pairs trade
- α is the long-run mean of the spread

**Important**: Engle-Granger critical values differ from standard ADF critical
values. For n=2 series: 1% = -3.90, 5% = -3.34, 10% = -3.04.

**Asymmetry warning**: Testing Y~X can give a different result than X~Y. Always
test both directions and use the stronger result.

```python
from scipy import stats
import numpy as np
from statsmodels.tsa.stattools import adfuller

# Step 1: OLS regression
slope, intercept, _, _, _ = stats.linregress(x_prices, y_prices)
hedge_ratio = slope

# Step 2: Test residuals
residuals = y_prices - hedge_ratio * x_prices - intercept
adf_stat, p_value, _, _, crit_values, _ = adfuller(residuals, maxlag=None, autolag="AIC")

cointegrated = p_value < 0.05
```

### 2. Johansen Test

Tests multiple series simultaneously and returns the number of cointegrating
relationships. More powerful than Engle-Granger for >2 series.

- Based on a VAR model: ΔY_t = Π·Y_{t-1} + Σ Γ_i·ΔY_{t-i} + ε_t
- Tests the rank of the Π matrix
- Uses trace test and maximum eigenvalue test
- Returns: number of cointegrating vectors and the vectors themselves

```python
from statsmodels.tsa.vector_ar.vecm import coint_johansen

# data: T×N array of price series
result = coint_johansen(data, det_order=0, k_ar_diff=1)

# Trace statistic vs critical values (90%, 95%, 99%)
trace_stats = result.lr1          # Trace statistics
trace_crit = result.cvt           # Critical values
max_eigen_stats = result.lr2      # Max eigenvalue statistics
max_eigen_crit = result.cvm       # Critical values

# Cointegrating vectors
coint_vectors = result.evec
```

### 3. Phillips-Ouliaris

Similar to Engle-Granger but uses Phillips-Perron style test statistics
instead of ADF. More robust to heteroskedasticity and serial correlation in
the residuals. Available via `statsmodels.tsa.stattools.coint`.

```python
from statsmodels.tsa.stattools import coint

# Returns: test statistic, p-value, critical values
t_stat, p_value, crit_values = coint(y_prices, x_prices)
cointegrated = p_value < 0.05
```

## Practical Workflow

### Step 1: Screen Pairs by Correlation

Pre-filter using Pearson correlation > 0.7 to reduce the number of
cointegration tests (which are more expensive).

### Step 2: Test Cointegration

Run Engle-Granger in both directions. Use p < 0.05 threshold.

### Step 3: Estimate Hedge Ratio

Use OLS for simplicity. For production, consider Total Least Squares or
Dynamic OLS (see `references/methodology.md`).

### Step 4: Compute Spread

```python
spread = y_prices - hedge_ratio * x_prices - intercept
z_score = (spread - spread.mean()) / spread.std()
```

### Step 5: Test Spread for Mean Reversion

- **ADF test**: p < 0.05 confirms stationarity
- **Hurst exponent**: H < 0.5 indicates mean reversion (H ≈ 0.5 = random walk)
- **Half-life**: λ from AR(1) on spread; half-life = -ln(2)/ln(λ)
  - Viable pairs: half-life between 5 and 60 days

### Step 6: Trade the Spread

If the spread is mean-reverting, it is a viable pairs trade candidate.
See `references/pairs_trading.md` for entry/exit rules and risk management.

## Rolling Cointegration

Cointegration relationships can break down over time due to structural changes,
regime shifts, or evolving market dynamics.

### Rolling Window Approach

Test cointegration on rolling 60–90 day windows:

```python
window = 60
rolling_pvalues = []
rolling_hedges = []

for i in range(window, len(prices)):
    y_win = y_prices[i - window:i]
    x_win = x_prices[i - window:i]
    _, p_val, _ = coint(y_win, x_win)
    slope, intercept, _, _, _ = stats.linregress(x_win, y_win)
    rolling_pvalues.append(p_val)
    rolling_hedges.append(slope)
```

### Monitoring Signals

| Signal | Healthy | Warning | Stop Trading |
|---|---|---|---|
| Rolling p-value | < 0.05 | 0.05–0.10 | > 0.10 |
| Hedge ratio drift | < 10% change | 10–25% change | > 25% change |
| Spread half-life | 5–60 days | 60–120 days | > 120 days or < 5 |

## Crypto Pairs Candidates

### Layer-1 Correlation
- SOL vs ETH — L1 sector beta, often cointegrated during trending markets
- SOL vs AVAX — alternative L1 correlation

### Stablecoins
- USDC vs USDT — should be perfectly cointegrated (peg arbitrage)
- Useful as a sanity check for your cointegration pipeline

### Liquid Staking Derivatives
- mSOL vs jitoSOL — both track SOL staking yield
- stSOL vs mSOL — Lido vs Marinade staking

### Same-Sector Tokens
- DEX tokens: RAY vs ORCA
- Lending tokens: cross-protocol comparison
- Meme tokens: rarely cointegrated, high risk

## Common Pitfalls

1. **Spurious cointegration** — Two trending series (both up in a bull market) may
   appear cointegrated. Always test on sufficient data (>200 observations) and
   check out-of-sample stability.

2. **Structural breaks** — A fundamental change (protocol upgrade, tokenomics
   change) can permanently break cointegration. Monitor rolling p-values.

3. **Look-ahead bias** — Estimating the hedge ratio on the full sample and then
   backtesting on the same sample inflates results. Always use walk-forward
   estimation.

4. **Too-short sample** — Cointegration tests need >100 observations minimum,
   ideally >200, to have reasonable power.

5. **Ignoring transaction costs** — Pairs trades involve 4 transactions per
   round trip. At 0.3% per leg, that is 1.2% in costs that the spread must
   overcome.

6. **Asymmetric cointegration** — The relationship may only hold in one
   direction or one regime. Consider threshold cointegration models for
   production use.

## Integration with Other Skills

- **`correlation-analysis`** — Pre-screening pairs by correlation before cointegration testing
- **`mean-reversion`** — Trading the cointegrated spread using mean-reversion entry/exit rules
- **`vectorbt`** — Backtesting pairs strategies with walk-forward validation
- **`regime-detection`** — Identifying when cointegration regimes shift
- **`volatility-modeling`** — Spread volatility forecasting for dynamic position sizing

## Files

### References
- `references/methodology.md` — Engle-Granger details, Johansen derivation, hedge ratio estimation methods, spread construction
- `references/pairs_trading.md` — Entry/exit rules, risk management, performance metrics, crypto-specific considerations

### Scripts
- `scripts/test_cointegration.py` — Full cointegration test pipeline with ADF, Hurst, half-life, rolling stability, and demo mode
- `scripts/pairs_backtest.py` — Walk-forward pairs trading backtest with synthetic data and performance reporting
