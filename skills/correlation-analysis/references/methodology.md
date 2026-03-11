# Correlation Analysis — Methodology Reference

## Pearson Correlation Coefficient

### Formula

```
r = cov(X, Y) / (σ_X * σ_Y)
  = Σ((x_i - x̄)(y_i - ȳ)) / sqrt(Σ(x_i - x̄)² * Σ(y_i - ȳ)²)
```

### Properties

- **Range**: -1 to +1
- **r = +1**: perfect positive linear relationship
- **r = 0**: no linear relationship (may still have non-linear dependence)
- **r = -1**: perfect negative linear relationship

### Assumptions

1. **Linearity**: relationship between X and Y is linear
2. **Normality**: both variables approximately normally distributed
3. **Homoscedasticity**: variance of Y is constant across values of X
4. **No outliers**: extreme values distort Pearson correlation
5. **Stationarity**: compute on returns, not prices (prices are non-stationary)

### When Pearson Fails in Crypto

Crypto returns violate normality (kurtosis of 5–20 vs 3 for normal). Heavy tails mean:
- Pearson underestimates tail co-movement
- Outlier pairs of returns dominate the estimate
- Short samples produce unstable estimates

## Spearman Rank Correlation

### Formula

1. Convert X and Y to ranks: R(X), R(Y)
2. Compute Pearson correlation on the ranks

```
ρ_s = 1 - (6 * Σ d_i²) / (n * (n² - 1))
```

where d_i = rank(x_i) - rank(y_i)

### Advantages Over Pearson

- Captures monotonic relationships (not just linear)
- Robust to outliers — extreme values get large ranks but don't distort
- No normality assumption
- Better for crypto: handles heavy tails naturally

### When to Use

- Default choice for crypto correlation analysis
- When comparing assets with different volatility profiles
- When relationship may be non-linear but monotonic

## Kendall Tau Correlation

### Formula

```
τ = (concordant_pairs - discordant_pairs) / (n * (n-1) / 2)
```

A pair (x_i, y_i), (x_j, y_j) is **concordant** if (x_i - x_j) and (y_i - y_j) have the same sign.

### Properties

- Most robust to outliers
- Better for small samples (<50 observations)
- Computationally O(n²) vs O(n log n) for Pearson/Spearman
- Values tend to be smaller than Pearson/Spearman for the same data

### Conversion Between Measures

Approximate relationship: `ρ_Pearson ≈ sin(π/2 * τ_Kendall)`

## Rolling Correlation

### Window-Based

```python
rolling_corr = returns_a.rolling(window=W).corr(returns_b)
```

**Window selection**:
- Too short (W < 15): noisy, high variance estimates
- Too long (W > 200): sluggish, misses regime changes
- Sweet spot: 30–90 days for most applications

### EWMA Correlation

Exponentially weighted moving average gives more weight to recent observations.

```python
def ewma_correlation(x: pd.Series, y: pd.Series, span: int) -> pd.Series:
    """EWMA correlation with specified span (half-life ≈ span/2.7)."""
    mean_x = x.ewm(span=span).mean()
    mean_y = y.ewm(span=span).mean()
    cov = (x * y).ewm(span=span).mean() - mean_x * mean_y
    var_x = x.pow(2).ewm(span=span).mean() - mean_x.pow(2)
    var_y = y.pow(2).ewm(span=span).mean() - mean_y.pow(2)
    return cov / (var_x.pow(0.5) * var_y.pow(0.5))
```

**EWMA vs Window**:
- EWMA: smoother, no cliff effect when old data drops out
- Window: simpler, easier to interpret as "correlation over last N days"

### Minimum Sample Size

- At least 30 observations for meaningful correlation
- Fewer than 20: correlation estimate has very wide confidence interval
- Rule of thumb: need `n > 50 / (1 - r²)` for stable estimate at correlation r

## Hierarchical Clustering

### Distance Metric

Convert correlation to distance:

```
d(i,j) = sqrt(2 * (1 - ρ_ij))
```

This maps correlation:
- ρ = +1 → d = 0 (identical)
- ρ = 0 → d = √2 ≈ 1.414
- ρ = -1 → d = 2 (maximally different)

### Linkage Methods

| Method | Description | Best For |
|--------|-------------|----------|
| Ward | Minimize within-cluster variance | Compact, equal-size clusters |
| Complete | Maximum distance between cluster members | Well-separated clusters |
| Average | Mean distance between cluster members | General purpose |
| Single | Minimum distance (nearest neighbor) | Chaining — usually avoid |

**Recommendation**: Ward linkage produces the most intuitive clusters for financial assets.

### Cutting the Dendrogram

Choose number of clusters by:
1. **Fixed threshold**: cut at distance t (e.g., t=1.0)
2. **Gap statistic**: compare within-cluster dispersion to random
3. **Elbow method**: plot within-cluster variance vs number of clusters
4. **Domain knowledge**: 3–6 clusters is typical for crypto (BTC-like, ETH-ecosystem, SOL-ecosystem, stablecoins, meme)

## Tail Dependence

### Definition

Lower tail dependence coefficient:

```
λ_L = lim(q→0) P(Y ≤ F_Y⁻¹(q) | X ≤ F_X⁻¹(q))
```

In practice, estimate at finite quantile (typically 5th or 10th percentile):

```
λ̂_L(q) = #{i : x_i < Q_x(q) AND y_i < Q_y(q)} / #{i : x_i < Q_x(q)}
```

### Interpretation

| λ_L Value | Interpretation |
|-----------|---------------|
| 0.0 | Assets never crash together |
| 0.3 | Moderate tail dependence |
| 0.6 | Strong tail dependence — crashes are correlated |
| 1.0 | Always crash together |

### Upper vs Lower Tail

- **Lower tail** (λ_L): co-crashing — most important for risk management
- **Upper tail** (λ_U): co-rallying — relevant for momentum strategies

For crypto: λ_L >> λ_U in most pairs (assets crash together more than they rally together).

## Statistical Significance

### Testing H0: ρ = 0

Test statistic:

```
t = r * sqrt(n - 2) / sqrt(1 - r²)
```

This follows a t-distribution with n-2 degrees of freedom.

### Confidence Interval

Use Fisher z-transform:

```
z = arctanh(r) = 0.5 * ln((1+r)/(1-r))
SE(z) = 1 / sqrt(n - 3)

95% CI for z: z ± 1.96 * SE(z)
Convert back: r = tanh(z)
```

### Minimum Detectable Correlation

For a given sample size n and significance level α:

| n | Min |r| at α=0.05 |
|---|---------------------|
| 20 | 0.444 |
| 30 | 0.361 |
| 50 | 0.279 |
| 100 | 0.197 |
| 252 | 0.124 |

**Implication**: with 30 days of data, correlations below 0.36 are not statistically distinguishable from zero.

## Common Pitfalls

1. **Correlating prices instead of returns**: prices are non-stationary, producing spurious correlation
2. **Ignoring regime changes**: a single correlation number hides regime-dependent behavior
3. **Small sample overconfidence**: 20 data points cannot reliably estimate correlation
4. **Survivorship bias**: only analyzing tokens that still exist inflates average correlation
5. **Frequency mismatch**: daily correlation ≠ hourly correlation (Epps effect: higher frequency → lower correlation)
6. **Confusing correlation with causation**: two assets correlated with BTC will appear correlated with each other
7. **Ignoring tails**: Pearson correlation misses tail dependence that matters most for risk
