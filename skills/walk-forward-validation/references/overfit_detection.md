# Overfit Detection Methods

## The Overfitting Problem in Finance

Every backtest is a hypothesis test. When you test many strategies and select the best performer, you are conducting multiple comparisons. The probability that at least one strategy appears profitable by chance increases rapidly with the number of trials.

If you test `N` strategies at a 5% significance level, the probability that at least one falsely appears significant is `1 - (1 - 0.05)^N`. With 20 strategies, this exceeds 64%.

## Deflated Sharpe Ratio (DSR)

### Concept

The Deflated Sharpe Ratio (Bailey and Lopez de Prado, 2014) adjusts the observed Sharpe ratio for:

1. **Number of trials** — How many strategies/parameter sets were tested
2. **Non-normality** — Skewness and kurtosis of returns
3. **Backtest length** — More data points increase statistical reliability

### Formula

The DSR computes the probability that the observed Sharpe ratio exceeds the expected maximum Sharpe ratio under the null hypothesis (all strategies have zero true Sharpe):

```
DSR = Phi((SR_observed - SR_expected_max) / sigma_SR)
```

Where:
- `Phi` = standard normal CDF
- `SR_observed` = Sharpe ratio of the selected strategy
- `SR_expected_max` = expected maximum SR from `N` IID trials
- `sigma_SR` = standard error of the Sharpe ratio estimator

### Standard Error of the Sharpe Ratio

```
sigma_SR = sqrt((1 - gamma_3 * SR + (gamma_4 - 1)/4 * SR^2) / (T - 1))
```

Where:
- `gamma_3` = skewness of returns
- `gamma_4` = kurtosis of returns (not excess kurtosis)
- `T` = number of return observations
- `SR` = observed Sharpe ratio (non-annualized)

### Expected Maximum Sharpe Ratio

Under the null hypothesis that all `N` strategies have zero true Sharpe ratio, the expected maximum observed SR is approximately:

```
E[max(SR)] ≈ Z_inv(1 - 1/N) * (1 - gamma) + gamma * Z_inv(1 - 1/(N*e))
```

Where:
- `Z_inv` = inverse standard normal CDF (quantile function)
- `gamma ≈ 0.5772` = Euler-Mascheroni constant
- `N` = number of independent trials
- `e ≈ 2.7183` = Euler's number

### Interpretation

| DSR Value | Interpretation |
|---|---|
| > 0.95 | Strong evidence of genuine skill |
| 0.80 – 0.95 | Moderate evidence, proceed with caution |
| 0.50 – 0.80 | Weak evidence, likely partially overfitted |
| < 0.50 | Likely overfitted, performance is noise |

### Practical Notes

- `N` must include ALL strategies tested, including those discarded. This is the hardest part — researchers forget or undercount.
- Non-annualized SR should be used in the formula; annualize the result afterward.
- For crypto with 24/7 trading, annualization factor is 365 (daily) or 8760 (hourly).

## Probability of Backtest Overfitting (PBO)

### Concept

PBO (Bailey et al., 2017) uses combinatorial splits to measure the probability that in-sample optimization selects a strategy that underperforms out-of-sample.

### Algorithm

1. Generate multiple train/test splits using CPCV (N groups, k=2 test groups)
2. For each split:
   a. Rank all `S` strategies by in-sample performance
   b. Identify the IS-optimal strategy (best in-sample rank)
   c. Record its out-of-sample rank
3. Compute the relative OOS rank: `w_bar = OOS_rank / S`
4. PBO = fraction of splits where `w_bar > 0.5` (IS-best is worse than OOS median)

### Logit Transformation

For better statistical properties, apply the logit transform before aggregating:

```
lambda = ln(w_bar / (1 - w_bar))
```

PBO is then estimated as the fraction of splits where `lambda > 0` (i.e., OOS rank is worse than median).

### Interpretation

| PBO Value | Interpretation |
|---|---|
| < 0.10 | Low overfitting risk |
| 0.10 – 0.30 | Moderate risk, additional validation recommended |
| 0.30 – 0.50 | High risk, results are unreliable |
| > 0.50 | More likely than not overfitted |

### Stochastic Dominance

PBO can be extended by checking if the IS-optimal strategy's OOS performance distribution stochastically dominates a uniform distribution. If it does not, the strategy selection process has no predictive power.

## Multiple Testing Corrections

When testing multiple hypotheses simultaneously, use corrections to control the family-wise error rate (FWER) or false discovery rate (FDR).

### Bonferroni Correction

The simplest approach — divide the significance level by the number of tests:

```
alpha_adjusted = alpha / N
```

Conservative but guarantees FWER control. With 100 strategies at alpha=0.05, each strategy must achieve p < 0.0005.

### Holm-Bonferroni (Step-Down)

Less conservative than Bonferroni while still controlling FWER:

1. Sort p-values: `p_(1) <= p_(2) <= ... <= p_(N)`
2. For each `i`, reject H_i if `p_(i) <= alpha / (N - i + 1)`
3. Stop at the first non-rejection

### Benjamini-Hochberg (FDR Control)

Controls the expected proportion of false discoveries rather than FWER:

1. Sort p-values: `p_(1) <= p_(2) <= ... <= p_(N)`
2. Find largest `k` where `p_(k) <= k/N * alpha`
3. Reject hypotheses 1 through k

### Which to Use

- **Bonferroni**: When false positives are catastrophic (capital at risk)
- **Holm**: When you want more power than Bonferroni with same FWER guarantee
- **BH**: When testing many strategies and some false positives are acceptable (screening stage)

For trading: Use Bonferroni or Holm when selecting a single strategy to deploy. Use BH when screening a large universe of strategies for further investigation.

## Minimum Backtest Length (MinBTL)

The minimum number of observations needed for a Sharpe ratio to be statistically significant:

```
MinBTL = 1 + (1 - gamma_3 * SR + (gamma_4 - 1)/4 * SR^2) * (Z_alpha / SR)^2
```

Where:
- `Z_alpha` = critical value for desired significance level
- `SR` = target non-annualized Sharpe ratio
- `gamma_3`, `gamma_4` = skewness, kurtosis of returns

### Practical Implications

For a strategy with daily SR = 0.1 (annualized ~1.6) and normal returns:
- At 95% confidence: MinBTL ≈ 385 daily observations (1.05 years)
- At 99% confidence: MinBTL ≈ 664 daily observations (1.82 years)

For crypto with hourly SR = 0.01:
- At 95% confidence: MinBTL ≈ 38,416 hourly observations (4.4 years)

This underscores why high-frequency strategies need very long backtests or very high Sharpe ratios to be statistically validated.

## Combining DSR and PBO

Use both metrics together for robust overfit detection:

1. **DSR** answers: "Is this Sharpe ratio likely real given how many things I tried?"
2. **PBO** answers: "Does my strategy selection process have any predictive power?"

If DSR > 0.95 AND PBO < 0.20, the strategy has strong evidence of genuine edge. If either metric fails, additional out-of-sample testing (preferably paper trading) is essential before deploying capital.
