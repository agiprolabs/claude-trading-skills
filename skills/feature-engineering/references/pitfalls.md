# Feature Engineering Pitfalls

Common mistakes that invalidate trading ML models. Each section describes the
problem, how to detect it, and how to fix it.

## 1. Lookahead Bias

**The single most common and destructive bug in trading ML.**

Lookahead bias occurs when information from the future leaks into features or
labels used for training.

### How It Happens

**Full-sample statistics instead of rolling:**

```python
# WRONG: uses future data to compute mean/std
z_score = (feature - feature.mean()) / feature.std()

# CORRECT: only uses past data
z_score = (feature - feature.rolling(60).mean()) / feature.rolling(60).std()
```

**Target leakage in features:**

```python
# WRONG: forward return accidentally included as a feature
features["next_return"] = close.shift(-1) / close - 1  # This IS the target

# WRONG: feature computed from data that includes the target period
features["volatility"] = close.rolling(20, center=True).std()  # center=True uses future
```

**Incorrect shift direction:**

```python
# WRONG: shifts features backward (uses future features)
features = features.shift(-1)

# CORRECT: shifts target forward (predicts future from past)
target = close.shift(-N) / close - 1
```

### How to Detect

- **Suspiciously high accuracy**: >70% accuracy on crypto classification is almost
  certainly leakage. Real edge is typically 52-58%.
- **Features perfectly correlated with target at lag 0**: Run
  `features.corrwith(target)` — any correlation >0.5 is suspicious.
- **Performance degrades dramatically on truly out-of-sample data**: If backtest
  shows 65% accuracy but live shows 50%, you have leakage.
- **Walk-forward validation**: Split data into 5+ sequential folds. If performance
  is consistent across folds, features are likely clean. If first folds are much
  better, you have leakage from the full-sample normalization.

### How to Fix

1. Use only `.rolling()`, `.expanding()`, or `.ewm()` — never `.mean()`, `.std()`
   on the full series.
2. After computing features, verify that feature at row `t` depends only on data
   from rows `<= t`.
3. Use `sklearn.model_selection.TimeSeriesSplit` for cross-validation.

## 2. Overfitting

Training a model that memorizes the training data instead of learning
generalizable patterns.

### How It Happens

- **Too many features**: 100 features on 500 samples will overfit. Rule of thumb:
  need 10-20 samples per feature. For 50 features, need 500-1000 samples minimum.
- **Complex models on small data**: A 1000-tree random forest on 200 samples will
  memorize every sample.
- **Feature selection on full dataset**: If you select features using the test set,
  you've leaked information about the test set into training.

### How to Detect

- **Train vs. test gap**: If train accuracy is 90% but test accuracy is 52%, the
  model is overfitting.
- **Performance instability**: Small changes in training data cause large changes
  in model predictions.
- **Feature importance instability**: Top features change significantly across
  different training windows.

### How to Fix

- Reduce feature count to < N_samples / 15.
- Use regularized models (L1/L2 regularization, tree depth limits).
- Perform feature selection only within the training fold.
- Use walk-forward validation with multiple windows.

```python
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5)
for train_idx, test_idx in tscv.split(X):
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    # Feature selection HERE, on X_train only
    # Train model HERE, on X_train only
    # Evaluate on X_test
```

## 3. Survivorship Bias

Only analyzing tokens that survived (still tradeable) while ignoring the vast
majority that failed.

### The Problem in Crypto

On Solana PumpFun alone, 98%+ of launched tokens go to zero within days. If
your training data only includes tokens that still have liquidity:

- Your model learns "what tokens that survive look like"
- It never learns "what tokens that fail look like"
- In production, it sees mostly failing tokens and has no useful signal

### How to Fix

- Include dead tokens in your training data.
- Label tokens that went to zero as negative examples.
- Track tokens from launch, not from "tokens that reached $1M market cap."
- When fetching historical data, include delisted/zero-liquidity tokens.

## 4. Data Snooping (Multiple Testing)

Running many experiments and only reporting the ones that work.

### How It Happens

- Testing 100 feature combinations, finding 5 that "work" on historical data.
- By chance alone, at p=0.05, you'd expect 5 out of 100 to appear significant.
- These 5 features have no real predictive power — they are statistical flukes.

### How to Detect

- **Bonferroni correction**: Divide significance level by number of tests.
  Testing 100 features at p=0.05 requires p < 0.0005 for each feature.
- **Out-of-sample holdout**: Reserve 20% of data that you never touch until
  final evaluation. If results hold on this set, they're more likely real.

### How to Fix

- Pre-register your feature set before testing. Decide which features to use
  based on domain knowledge, not data mining.
- Use a strict holdout set that is never used for feature selection.
- Report all experiments, not just successful ones.
- Apply Bonferroni or Benjamini-Hochberg correction for multiple comparisons.

## 5. Non-Stationarity

Features whose statistical properties change over time.

### Why It Breaks Models

A model trained on features with mean=0, std=1 will fail when those features
shift to mean=5, std=3 in production. The model's decision boundaries are
calibrated to the training distribution.

### Common Non-Stationary Features

| Feature | Problem | Fix |
|---------|---------|-----|
| Raw price | Trends over time | Use returns |
| Raw volume | Grows with adoption | Use volume ratios |
| OBV | Cumulative, always grows | Use OBV slope |
| Holder count | Grows over time | Use holder count change |
| Dollar volume | Scales with price | Use dollar volume ratio |
| Moving averages | Track price level | Use MA crossover signals |

### Rolling Feature Importance

Features that are important in one market regime may be useless in another.
Monitor feature importance over time:

```python
# Compute feature importance in rolling windows
window_size = 200
importances_over_time = []
for start in range(0, len(X) - window_size, 50):
    end = start + window_size
    model.fit(X.iloc[start:end], y.iloc[start:end])
    importances_over_time.append(model.feature_importances_)
```

If a feature's importance fluctuates wildly, it may be regime-dependent and
should be used cautiously.

## 6. Label Imbalance

When one class dominates the label distribution.

### The Problem

If 80% of your labels are "flat" (no significant move), a model that always
predicts "flat" achieves 80% accuracy while being completely useless.

### How to Detect

```python
print(y_train.value_counts(normalize=True))
# If any class is >70% or <10%, you have imbalance
```

### Solutions

| Method | Description | When to Use |
|--------|-------------|-------------|
| Adjusted thresholds | Widen up/down threshold until classes are ~balanced | First approach |
| Class weights | `class_weight='balanced'` in sklearn | Simple, no data change |
| SMOTE oversampling | Generate synthetic minority samples | Moderate imbalance |
| Undersampling | Reduce majority class | Large datasets only |
| Stratified splits | Maintain class ratios in train/test | Always do this |

```python
from sklearn.ensemble import RandomForestClassifier

# Automatically adjust for class imbalance
model = RandomForestClassifier(class_weight="balanced", random_state=42)
```

### Evaluation Metrics for Imbalanced Data

Do not use accuracy. Use:

- **Precision**: Of predicted positives, how many are correct?
- **Recall**: Of actual positives, how many are detected?
- **F1 score**: Harmonic mean of precision and recall.
- **ROC-AUC**: Discrimination ability regardless of threshold.
- **Profit factor**: Actual financial performance (the true metric).

## Checklist Before Training

Use this checklist before training any model:

- [ ] All features use rolling (not full-sample) statistics
- [ ] Target is forward-shifted, not feature-backward-shifted
- [ ] Train/test split is temporal, not random
- [ ] Feature selection done only on training data
- [ ] No feature has >0.5 correlation with target at lag 0
- [ ] Dead/failed tokens included in training data
- [ ] Class distribution is reasonably balanced (or weights adjusted)
- [ ] Number of features < number of samples / 15
- [ ] Features pass ADF stationarity test (p < 0.05)
- [ ] Walk-forward validation shows consistent (not declining) performance
