# Portfolio Metrics — Formulas & Interpretation Guide

## Notation

| Symbol | Meaning |
|--------|---------|
| R_t | Return in period t |
| R_f | Risk-free rate per period |
| N | Annualization factor (252 daily, 52 weekly, 12 monthly) |
| T | Total number of periods |
| P_t | Portfolio value at time t |

## Return Metrics

### Total Return

```
Total Return = (P_final / P_initial) - 1
```

### CAGR (Compound Annual Growth Rate)

```
CAGR = (P_final / P_initial) ^ (365.25 / days) - 1
```

Where `days` is the calendar day count between first and last observation. CAGR smooths out volatility and shows the constant annual rate that would produce the same terminal value.

### Annualized Mean Return

```
Annualized Mean = mean(R_t) * N
```

This is the arithmetic annualization. It overstates the geometric growth rate when returns are volatile. Use CAGR for the geometric rate.

### Cumulative Return Series

```
Cumulative_t = product(1 + R_i for i in 1..t) - 1
```

In pandas: `(1 + returns).cumprod() - 1`

## Risk Metrics

### Annualized Volatility

```
Vol_annual = std(R_t) * sqrt(N)
```

Uses sample standard deviation. The sqrt(N) scaling assumes returns are IID — an approximation. For crypto and memecoin markets, volatility clustering makes this a rough estimate.

### Value at Risk (VaR) — Historical Method

```
VaR(alpha) = -percentile(R_t, (1 - alpha) * 100)
```

For 95% confidence: `VaR = -percentile(returns, 5)`. This means "on 95% of days, the loss will not exceed VaR."

**Interpretation**: A daily VaR of 3% at 95% confidence means you expect to lose more than 3% on roughly 1 in 20 trading days.

**Parametric VaR** (assumes normal distribution):

```
VaR(alpha) = -(mean(R_t) + z_alpha * std(R_t))
```

Where z_alpha is the z-score for the confidence level (1.645 for 95%, 2.326 for 99%).

### Conditional VaR (CVaR / Expected Shortfall)

```
CVaR(alpha) = -mean(R_t where R_t <= -VaR(alpha))
```

CVaR answers: "When we do breach VaR, how bad is the average loss?" It is always >= VaR and better captures tail risk.

**Example**: If VaR(95%) = 3% and the average loss on the worst 5% of days is 5.2%, then CVaR = 5.2%.

### Maximum Drawdown

```
Drawdown_t = (P_t - max(P_1..P_t)) / max(P_1..P_t)
Max Drawdown = min(Drawdown_t for all t)
```

Maximum drawdown measures the worst peak-to-trough decline. It is always negative (or zero). Report the absolute value when comparing.

### Time Underwater

The longest consecutive period where the portfolio is below its previous peak. Measured in trading days or calendar days. Long underwater periods indicate difficulty recovering from drawdowns.

## Risk-Adjusted Ratios

### Sharpe Ratio

```
Sharpe = (mean(R_t) - R_f) / std(R_t) * sqrt(N)
```

**Derivation**: The Sharpe ratio is the slope of the Capital Allocation Line — the excess return per unit of total risk. Annualization multiplies by sqrt(N) because mean scales linearly with N while standard deviation scales with sqrt(N).

**Interpretation benchmarks**:
| Sharpe | Rating |
|--------|--------|
| < 0 | Losing money |
| 0 - 0.5 | Poor |
| 0.5 - 1.0 | Acceptable |
| 1.0 - 2.0 | Good |
| 2.0 - 3.0 | Excellent |
| > 3.0 | Exceptional (verify — may indicate overfitting) |

**Limitations**: Assumes symmetric return distribution. Penalizes upside volatility equally with downside. Sensitive to measurement frequency.

### Sortino Ratio

```
Sortino = (mean(R_t) - R_f) / std(R_t where R_t < R_f) * sqrt(N)
```

**Derivation**: Replaces total standard deviation with downside deviation. Only penalizes returns below the threshold (usually the risk-free rate or zero). Better than Sharpe for strategies with positive skew (large winners, small losers).

**Interpretation**: Same scale as Sharpe but typically higher because downside deviation <= total deviation.

### Calmar Ratio

```
Calmar = CAGR / |Max Drawdown|
```

**Interpretation**: Return earned per unit of worst-case drawdown. A Calmar of 2.0 means the strategy earns twice its maximum historical drawdown per year.

| Calmar | Rating |
|--------|--------|
| < 0.5 | Poor |
| 0.5 - 1.0 | Acceptable |
| 1.0 - 3.0 | Good |
| > 3.0 | Excellent |

### Omega Ratio

```
Omega(threshold) = integral[threshold to +inf] (1 - F(x)) dx
                   ────────────────────────────────────────────
                   integral[-inf to threshold] F(x) dx
```

In practice (discrete):

```
Omega = sum(max(R_t - threshold, 0)) / sum(max(threshold - R_t, 0))
```

**Interpretation**: The ratio of probability-weighted gains above a threshold to probability-weighted losses below it. Unlike Sharpe, Omega uses the entire return distribution, not just mean and variance. Omega > 1 means the strategy outperforms the threshold on a probability-weighted basis.

### Information Ratio

```
IR = mean(R_strategy - R_benchmark) / std(R_strategy - R_benchmark) * sqrt(N)
```

**Derivation**: The Sharpe ratio of the active (excess over benchmark) returns. Measures how consistently a strategy outperforms its benchmark.

| IR | Rating |
|----|--------|
| < 0 | Underperforming benchmark |
| 0 - 0.5 | Moderate skill |
| 0.5 - 1.0 | Good skill |
| > 1.0 | Exceptional |

## Annualization Factors

| Frequency | Periods per Year (N) | sqrt(N) |
|-----------|---------------------|---------|
| Daily (trading) | 252 | 15.875 |
| Daily (calendar) | 365 | 19.105 |
| Weekly | 52 | 7.211 |
| Monthly | 12 | 3.464 |
| Hourly (24/7 crypto) | 8760 | 93.59 |
| 5-minute (24/7 crypto) | 105120 | 324.22 |

**Important for crypto**: Traditional equities use 252 trading days. Crypto markets trade 24/7/365, so use 365 for daily or 8760 for hourly when analyzing crypto-native strategies. Solana memecoin strategies typically use 365-day annualization.

## Trade-Level Metrics

### Win Rate

```
Win Rate = count(trades where PnL > 0) / count(all trades)
```

Win rate alone is uninformative. A 30% win rate with 5:1 reward-to-risk is excellent.

### Profit Factor

```
Profit Factor = sum(winning trade PnL) / |sum(losing trade PnL)|
```

| PF | Rating |
|----|--------|
| < 1.0 | Losing |
| 1.0 - 1.5 | Marginal |
| 1.5 - 2.0 | Good |
| 2.0 - 3.0 | Excellent |
| > 3.0 | Exceptional (small sample?) |

### Expectancy

```
Expectancy = (Win Rate * Avg Win) + ((1 - Win Rate) * Avg Loss)
```

Where Avg Loss is negative. Expectancy is the expected PnL per trade. Positive expectancy is necessary (but not sufficient) for a viable strategy.

### Payoff Ratio

```
Payoff Ratio = |Avg Win| / |Avg Loss|
```

Combined with win rate, determines whether a strategy is viable:
- High win rate + low payoff = scalping
- Low win rate + high payoff = trend following
- Both high = very rare, verify with out-of-sample data

## Common Pitfalls

1. **Annualization errors**: Using sqrt(252) on monthly data (should be sqrt(12)).
2. **Survivorship bias**: Only analyzing strategies that survived; ignoring blown-up variants.
3. **Overfitting Sharpe**: Optimizing for Sharpe on in-sample data inflates the metric.
4. **Ignoring drawdown duration**: A 20% drawdown lasting 2 days is very different from one lasting 6 months.
5. **Comparing different frequencies**: A daily Sharpe of 2.0 is not comparable to a monthly Sharpe of 2.0 unless both are annualized identically.
6. **Small sample sizes**: 30 trades is not enough to draw conclusions about win rate or profit factor. Aim for 100+ trades minimum.
