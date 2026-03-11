---
name: feature-engineering
description: Feature construction from market data for ML trading models including price, volume, on-chain, and microstructure features
---

# Feature Engineering for Trading ML

Feature engineering is the single highest-leverage activity in building ML trading
models. Model selection (XGBoost vs. neural net vs. logistic regression) matters far
less than the quality and diversity of input features. A simple model on great
features will outperform a complex model on raw prices every time.

This skill covers constructing, validating, and selecting features from market data
for use in classification (signal-classification) and regression models targeting
crypto/Solana token trading.

## Why Features Beat Models

Raw OHLCV data is non-stationary, noisy, and high-dimensional. Models trained
directly on price series will overfit. Feature engineering transforms raw data into
stationary, informative signals that capture distinct aspects of market behavior:

- **Compression**: Reduce thousands of price bars to dozens of descriptive statistics
- **Stationarity**: Convert non-stationary prices into stationary returns and ratios
- **Domain knowledge**: Encode trader intuition (support/resistance, volume climax)
  as computable quantities
- **Regime awareness**: Features that behave differently in trending vs. ranging
  markets help models adapt

## Feature Categories

### 1. Price Features

Derived purely from OHLCV price columns. These capture trend, momentum, and
volatility from the price series itself.

| Feature | Formula | Lookback |
|---------|---------|----------|
| `log_return` | `ln(close_t / close_{t-1})` | 1 bar |
| `abs_return` | `abs(log_return)` | 1 bar |
| `return_volatility` | `std(log_return, N)` | 20 bars |
| `momentum_N` | `close_t / close_{t-N} - 1` | 5, 10, 20 |
| `acceleration` | `momentum_5 - momentum_5[5]` | 10 bars |
| `high_low_range` | `(high - low) / close` | 1 bar |
| `close_position` | `(close - low) / (high - low)` | 1 bar |
| `gap` | `open_t / close_{t-1} - 1` | 1 bar |
| `rolling_skew` | `skew(log_return, N)` | 20 bars |
| `rolling_kurtosis` | `kurtosis(log_return, N)` | 20 bars |

### 2. Volume Features

Volume confirms or contradicts price movements. Divergences between price and
volume are among the most reliable signals in short-term trading.

| Feature | Formula | Lookback |
|---------|---------|----------|
| `volume_ratio` | `volume_t / mean(volume, N)` | 20 bars |
| `volume_ma_ratio` | `sma(volume, 5) / sma(volume, 20)` | 20 bars |
| `obv_slope` | `slope(OBV, N)` | 10 bars |
| `vwap_deviation` | `(close - VWAP) / VWAP` | intraday |
| `volume_acceleration` | `volume_ratio_t - volume_ratio_{t-1}` | 21 bars |
| `buy_volume_ratio` | `buy_volume / total_volume` | 1 bar |
| `dollar_volume` | `close * volume` | 1 bar |
| `volume_cv` | `std(volume, N) / mean(volume, N)` | 20 bars |

### 3. Technical Features

Standard technical indicators computed via `pandas-ta`. Use the `pandas-ta` skill
for full parameter documentation.

| Feature | Source | Lookback |
|---------|--------|----------|
| `rsi` | RSI(14) | 14 bars |
| `macd_histogram` | MACD(12,26,9) histogram | 33 bars |
| `bb_position` | `(close - BB_lower) / (BB_upper - BB_lower)` | 20 bars |
| `bb_width` | `(BB_upper - BB_lower) / BB_mid` | 20 bars |
| `atr_ratio` | `ATR(14) / close` | 14 bars |
| `adx` | ADX(14) | 14 bars |
| `stoch_k` | Stochastic %K(14,3) | 14 bars |
| `cci` | CCI(20) | 20 bars |
| `mfi` | MFI(14) | 14 bars |
| `supertrend_direction` | Supertrend direction (+1/-1) | 10 bars |

### 4. Microstructure Features

Derived from trade-level data (individual swaps/transactions). Require on-chain
or DEX API data.

| Feature | Description |
|---------|-------------|
| `trade_count_ratio` | Trades this bar / avg trades per bar |
| `avg_trade_size` | Mean trade size in USD |
| `large_trade_pct` | % of volume from trades > $10k |
| `unique_traders` | Count of distinct wallet addresses |
| `buy_count_ratio` | Buy trades / total trades |
| `trade_size_entropy` | Shannon entropy of trade size distribution |

### 5. On-Chain Features

Derived from blockchain state changes. Require Helius or Solana RPC data.

| Feature | Description |
|---------|-------------|
| `holder_count_change` | Change in unique holders over N periods |
| `whale_net_flow` | Net tokens moved by top-10 holders |
| `token_velocity` | Transfer volume / circulating supply |
| `liquidity_change` | Change in DEX liquidity pool TVL |

### 6. Cross-Asset Features

Capture relationships between the target token and broader market.

| Feature | Description |
|---------|-------------|
| `sol_correlation` | Rolling correlation with SOL price |
| `btc_beta` | Rolling beta to BTC returns |
| `sector_momentum` | Average return of tokens in same sector |

### 7. Time Features

Cyclical encoding of calendar time. Use sin/cos encoding to preserve cyclical
continuity (hour 23 is close to hour 0).

```python
import numpy as np

hour_sin = np.sin(2 * np.pi * hour / 24)
hour_cos = np.cos(2 * np.pi * hour / 24)
day_of_week = np.sin(2 * np.pi * day / 7)
```

## Stationarity

**Non-stationary features will cause your model to fail on new data.** A feature
is stationary if its statistical properties (mean, variance) don't change over time.

### Testing for Stationarity

Use the Augmented Dickey-Fuller (ADF) test:

```python
from scipy.stats import adfuller

result = adfuller(feature_series.dropna())
p_value = result[1]
is_stationary = p_value < 0.05
```

### Making Features Stationary

| Non-Stationary | Stationary Transform |
|----------------|---------------------|
| Price | Log return |
| Volume | Volume ratio (vol / avg vol) |
| OBV | OBV slope (regression coefficient) |
| Holder count | Holder count change |
| RSI | Already stationary (bounded 0-100) |
| Dollar volume | Dollar volume / rolling mean |

**Rule**: If a feature trends upward or downward over time, it is non-stationary.
Transform it into a ratio, difference, or rate of change.

## Normalization

After computing features, normalize them so that all features have comparable
scales. This is critical for distance-based models (KNN, SVM) and helpful for
tree models.

| Method | Formula | When to Use |
|--------|---------|-------------|
| Z-score | `(x - mean) / std` | Gaussian-like distributions |
| Min-max | `(x - min) / (max - min)` | Bounded features (RSI, BB position) |
| Rank | `rank(x) / len(x)` | Heavy-tailed distributions |

**Critical**: Use **rolling** statistics for normalization. Never use full-sample
mean/std — that introduces lookahead bias.

```python
# CORRECT: rolling z-score
z = (feature - feature.rolling(60).mean()) / feature.rolling(60).std()

# WRONG: full-sample z-score (lookahead bias!)
z = (feature - feature.mean()) / feature.std()
```

## No-Lookahead Guarantee

The most dangerous bug in trading ML is lookahead bias — using future information
to compute features or targets. Follow these rules absolutely:

1. **Rolling calculations only**: Never use `.mean()` or `.std()` on the full
   series. Always use `.rolling(N).mean()`.
2. **Shift targets forward, not features backward**: The target is
   `close.shift(-N) / close - 1` (future return), not `close / close.shift(N) - 1`
   (past return used as target).
3. **No future index alignment**: When joining feature and target DataFrames,
   verify that feature row `t` is paired with target row `t` (where target already
   contains the forward shift).
4. **Train/test split by time**: Never random split. Always
   `train = data[:split_idx]`, `test = data[split_idx:]`.

## Feature Selection

After computing many features, select the most predictive and least redundant:

### Step 1: Remove Low-Variance Features

```python
from sklearn.feature_selection import VarianceThreshold
selector = VarianceThreshold(threshold=0.01)
X_filtered = selector.fit_transform(X)
```

### Step 2: Correlation Filter

Remove features with > 0.9 correlation to another feature (keep the one with
higher target correlation):

```python
corr_matrix = X.corr().abs()
upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
to_drop = [col for col in upper.columns if any(upper[col] > 0.9)]
```

### Step 3: Feature Importance

Train a random forest and rank by importance:

```python
from sklearn.ensemble import RandomForestClassifier
rf = RandomForestClassifier(n_estimators=100, random_state=42)
rf.fit(X_train, y_train)
importances = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)
```

### Step 4: Mutual Information

Non-linear alternative to correlation:

```python
from sklearn.feature_selection import mutual_info_classif
mi = mutual_info_classif(X_train, y_train, random_state=42)
mi_scores = pd.Series(mi, index=X.columns).sort_values(ascending=False)
```

## Label Creation

Labels (targets) define what the model learns to predict.

### Binary Classification

```python
forward_return = close.shift(-N) / close - 1
label = (forward_return > threshold).astype(int)  # 1 = up, 0 = not up
```

Typical thresholds: 1% for 1h bars, 3% for 4h bars, 5% for daily bars.

### Multi-Class Classification

```python
label = pd.cut(forward_return,
               bins=[-np.inf, -threshold, threshold, np.inf],
               labels=[0, 1, 2])  # 0=down, 1=flat, 2=up
```

### Regression

```python
target = forward_return  # Predict exact return magnitude
```

Binary classification is recommended for initial models — it's simpler and
more robust to noise.

## Integration with Other Skills

- **`pandas-ta`**: Compute technical indicators that become features
- **`birdeye-api`**: Fetch OHLCV and trade data for feature computation
- **`helius-api`**: Fetch on-chain data for holder/whale features
- **`signal-classification`**: Use engineered features as model inputs
- **`regime-detection`**: Regime labels as features or for regime-conditional models
- **`ohlcv-processing`**: Clean and resample raw data before feature computation

## Files

### References
- `references/feature_catalog.md` — Complete catalog of ~40 features with formulas,
  lookbacks, stationarity status, and interpretation notes
- `references/pitfalls.md` — Common mistakes in trading feature engineering:
  lookahead bias, overfitting, survivorship bias, data snooping, non-stationarity

### Scripts
- `scripts/build_features.py` — Compute 25+ features from OHLCV data with
  stationarity testing and quality reporting. Supports demo mode with synthetic data
  or live data via Birdeye API.
- `scripts/feature_importance.py` — Rank features by predictive power using
  tree-based importance and permutation importance. Identifies redundant features
  via correlation analysis.
