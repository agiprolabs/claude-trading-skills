# Regime Detection — Methodology Reference

Detailed mathematical methods for identifying market regimes.

## Volatility Regime Detection

### Rolling Standard Deviation of Returns

The simplest volatility estimator. Compute log returns, then rolling standard deviation:

```
r_t = ln(close_t / close_{t-1})
σ_rolling = std(r_{t-N+1}, ..., r_t)
```

- **Window**: 20 bars for crypto, 50–100 for equities
- **Percentile rank**: Rank current σ against the last 100 values → 0–100 score
- **Annualization**: Multiply by √(bars_per_year) if needed, but percentile rank doesn't require it

### ATR Normalization

Raw ATR depends on price level. Normalize for cross-asset comparison:

```
NATR = (ATR / close) × 100
```

NATR of 5% means average true range is 5% of price. Useful for comparing BTC (NATR ~3%) vs a micro-cap (NATR ~15%).

### Parkinson Volatility

Uses high-low range instead of close-to-close. More efficient estimator:

```
σ_park = sqrt( (1 / (4N ln2)) × Σ (ln(H_i / L_i))² )
```

Advantages:
- Uses intrabar information (high/low)
- ~5x more efficient than close-to-close estimator
- Less affected by overnight gaps (less relevant for 24/7 crypto)

Disadvantage:
- Does not capture gap risk (opening jumps)

### Garman-Klass Volatility

Extends Parkinson by incorporating open and close:

```
σ_gk = sqrt( (1/N) × Σ [ 0.5 × (ln(H/L))² - (2ln2 - 1) × (ln(C/O))² ] )
```

Most efficient estimator using OHLC data. Recommended for crypto where you have reliable OHLC.

## Trend Detection

### ADX Calculation

The Average Directional Index measures trend strength regardless of direction.

**Step 1**: Directional Movement
```
+DM = max(high_t - high_{t-1}, 0)  if > |low_{t-1} - low_t|, else 0
-DM = max(low_{t-1} - low_t, 0)    if > (high_t - high_{t-1}), else 0
```

**Step 2**: Directional Indicators (smoothed over N periods)
```
+DI = 100 × smooth(+DM, N) / smooth(TR, N)
-DI = 100 × smooth(-DM, N) / smooth(TR, N)
```

**Step 3**: ADX
```
DX = 100 × |+DI - -DI| / (+DI + -DI)
ADX = smooth(DX, N)
```

Interpretation:
- **ADX < 20**: No trend (ranging)
- **20–25**: Weak trend or emerging trend
- **25–40**: Strong trend
- **> 40**: Very strong trend (often near exhaustion in crypto)

ADX does not indicate direction — only strength. Use +DI vs -DI or price vs EMA for direction.

### Linear Regression Slope + R²

Fit a linear regression to the last N closing prices:

```
slope = Σ((i - ī)(p_i - p̄)) / Σ((i - ī)²)
R² = 1 - Σ(p_i - ŷ_i)² / Σ(p_i - p̄)²
```

- **slope > 0 + R² > 0.6**: Clean uptrend
- **slope < 0 + R² > 0.6**: Clean downtrend
- **R² < 0.3**: No linear trend (ranging or chaotic)

R² is the key signal — high R² means price is "well-behaved" along the regression line, ideal for trend-following.

### EMA Spread as Trend Strength

```
trend_strength = (EMA_fast - EMA_slow) / ATR
```

Normalizing by ATR makes the spread comparable across assets and timeframes. Values > 1.5 indicate strong trend, < 0.5 indicates weak/no trend.

## Hurst Exponent

### Rescaled Range (R/S) Method

The Hurst exponent H characterizes time series persistence.

**Algorithm**:
1. For each lag τ from 2 to max_lag:
   a. Divide series into chunks of length τ
   b. For each chunk:
      - Compute mean m
      - Compute cumulative deviations: Y_t = Σ(x_i - m) for i=1..t
      - R = max(Y) - min(Y) (range of cumulative deviations)
      - S = std(chunk) (standard deviation)
      - RS = R / S
   c. Average RS across all chunks for this lag
2. Plot log(RS) vs log(τ)
3. H = slope of the best-fit line

**Interpretation**:
- **H < 0.4**: Anti-persistent (mean-reverting). Past up-moves predict future down-moves.
- **0.4 ≤ H ≤ 0.6**: No significant memory. Approximately random walk.
- **H > 0.6**: Persistent (trending). Past up-moves predict future up-moves.

**Practical notes**:
- Need at least 100 data points for reliable estimation
- Rolling Hurst: compute H over a sliding window of 100 bars, step by 1
- Crypto assets frequently oscillate between H=0.3 and H=0.7 over days
- Hurst near 0.5 is uninformative — don't trade on it

### Detrended Fluctuation Analysis (DFA)

An alternative to R/S that handles non-stationary trends better:

1. Compute cumulative sum of mean-centered returns
2. Divide into windows of size n
3. Fit a polynomial trend to each window
4. Compute RMS of residuals F(n)
5. H = slope of log(F(n)) vs log(n)

DFA is more robust than R/S for short series but computationally heavier.

## Change-Point Detection

### CUSUM (Cumulative Sum)

Detects shifts in the mean of a standardized series.

**Algorithm**:
```
S⁺_0 = S⁻_0 = 0
S⁺_t = max(0, S⁺_{t-1} + z_t - k)
S⁻_t = max(0, S⁻_{t-1} - z_t - k)
```

Where z_t = (r_t - μ) / σ and k = 0.5 (slack parameter).

A change point is detected when S⁺ or S⁻ exceeds threshold h (typically 2–5). Higher h = fewer false alarms but slower detection.

**Tuning for crypto**:
- k = 0.5, h = 2.0 for fast detection (more false positives)
- k = 0.5, h = 4.0 for conservative detection
- Recompute μ and σ using the last 50–100 bars, not the full history

### Pettitt Test

Non-parametric test for a single change point in the series. Tests whether the distribution before and after a candidate point differs significantly.

Good for confirming CUSUM-detected change points with a p-value.

## Hidden Markov Models

### Model Setup

A Gaussian HMM with N states models regime-switching:
- **States**: Unobserved regimes (e.g., bull, bear, neutral)
- **Observations**: Return features (returns, volatility, volume change)
- **Transition matrix**: Probability of switching between states
- **Emission**: Each state has a Gaussian distribution over observations

### Feature Selection

Recommended feature vector for crypto:
1. Log returns (captures direction + magnitude)
2. Rolling volatility (captures vol regime)
3. Volume ratio: volume / rolling_mean_volume (captures participation)

### Practical Limitations

- **Labels are arbitrary**: HMM assigns state 0, 1, 2 — you must interpret them by examining each state's mean return and volatility
- **Non-stationary**: Retrain periodically (every 200–500 bars)
- **Sensitive to initialization**: Run multiple times, pick best log-likelihood
- **Overfitting with >3 states**: Stick to 2–3 states for crypto
- **Look-ahead risk**: Use only past data for training when backtesting

### State Interpretation

After fitting, examine each state:
```python
for i in range(n_states):
    mask = (states == i)
    print(f"State {i}: mean_return={returns[mask].mean():.4f}, "
          f"vol={returns[mask].std():.4f}, "
          f"pct_time={mask.mean():.1%}")
```

Label states by their characteristics:
- Highest mean return + moderate vol → "Bull"
- Lowest mean return + high vol → "Bear"
- Near-zero return + low vol → "Neutral/Range"
