---
name: signal-classification
description: ML trading signal classifiers using XGBoost and LightGBM with walk-forward validation, SHAP feature importance, and threshold optimization
---

# Signal Classification

Predict whether an asset's price will move up or down over a forward horizon using supervised machine learning classifiers. This skill covers the full pipeline: label creation, model training, walk-forward validation, feature importance analysis, and threshold optimization for trading applications.

## Why Tree-Based Models Dominate Trading ML

XGBoost and LightGBM are the workhorses of quantitative trading ML for good reason:

- **Non-linear relationships**: Financial features interact in complex, non-linear ways that trees capture naturally
- **Robust to feature scale**: No need to normalize or standardize inputs — trees split on rank order
- **Built-in feature importance**: Understand which features drive predictions without separate analysis
- **Fast training and inference**: Train on thousands of samples in seconds, predict in microseconds
- **Handle missing values**: Native support for NaN without imputation hacks
- **Regularization built in**: max_depth, min_child_weight, subsample all prevent overfitting

Linear models and deep learning have their place, but for tabular trading features with fewer than 100k samples, gradient-boosted trees consistently outperform alternatives.

## Classification Types

### Binary Classification

The simplest and most common setup. Predict whether forward returns exceed a threshold:

- **Up signal**: forward return > +1%
- **Down signal**: forward return < -1%
- **Neutral (excluded)**: -1% to +1% — drop these from training to create cleaner labels

```python
import numpy as np

def create_binary_labels(
    prices: np.ndarray, horizon: int = 24, threshold: float = 0.01
) -> np.ndarray:
    """Create binary labels from forward returns.

    Args:
        prices: Array of prices.
        horizon: Forward return lookback in bars.
        threshold: Minimum return magnitude for a label.

    Returns:
        Array of labels: 1 (up), 0 (down), NaN (neutral).
    """
    fwd_returns = np.roll(prices, -horizon) / prices - 1
    fwd_returns[-horizon:] = np.nan
    labels = np.where(fwd_returns > threshold, 1,
             np.where(fwd_returns < -threshold, 0, np.nan))
    return labels
```

### Multi-Class Classification

Three classes for finer signal granularity:

| Class | Condition | Typical threshold |
|-------|-----------|-------------------|
| Strong Up | fwd_return > +2% | High confidence long |
| Mild Up | +0.5% to +2% | Moderate confidence |
| Down | fwd_return < -0.5% | Avoid / short |

Multi-class reduces per-class sample size. Use only with large datasets (1000+ samples per class).

### Probability Calibration

Raw model probabilities from XGBoost/LightGBM are not well-calibrated. A predicted 0.7 probability does not mean 70% chance of being correct. Use calibration to fix this:

```python
from sklearn.calibration import CalibratedClassifierCV

calibrated = CalibratedClassifierCV(base_model, cv=5, method="isotonic")
calibrated.fit(X_train, y_train)
probs = calibrated.predict_proba(X_test)[:, 1]
```

Isotonic calibration works better than Platt scaling for tree models.

## Walk-Forward Validation

**This is the single most important concept in trading ML.** Standard cross-validation randomly shuffles data, which creates lookahead bias. Walk-forward validation respects time ordering.

### How It Works

```
Window 1: [===TRAIN===][GAP][=TEST=]
Window 2:    [===TRAIN===][GAP][=TEST=]
Window 3:       [===TRAIN===][GAP][=TEST=]
Window 4:          [===TRAIN===][GAP][=TEST=]
```

Each window:
1. Train on past N bars
2. Skip a gap (embargo) equal to the forward return horizon
3. Predict on next M bars
4. Record out-of-sample predictions
5. Slide forward and repeat

### Typical Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Train window | 30 days (720 hourly bars) | Enough data to learn, recent enough to be relevant |
| Test window | 7 days (168 hourly bars) | Enough predictions for statistical significance |
| Step size | 1 day (24 bars) | Overlap test windows for more data points |
| Gap (embargo) | Same as forward horizon | Prevents label leakage |

### Walk-Forward Implementation

```python
from typing import Iterator

def walk_forward_splits(
    n_samples: int,
    train_size: int = 720,
    test_size: int = 168,
    step_size: int = 24,
    gap: int = 24,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test index splits.

    Args:
        n_samples: Total number of samples.
        train_size: Number of training samples per window.
        test_size: Number of test samples per window.
        step_size: Step between successive windows.
        gap: Gap between train end and test start.

    Yields:
        Tuples of (train_indices, test_indices).
    """
    start = 0
    while start + train_size + gap + test_size <= n_samples:
        train_idx = np.arange(start, start + train_size)
        test_start = start + train_size + gap
        test_idx = np.arange(test_start, test_start + test_size)
        yield train_idx, test_idx
        start += step_size
```

See `references/validation_methods.md` for purged CV, CPCV, and evaluation metrics.

## Model Training Pipeline

### Full Pipeline Overview

1. **Feature engineering** — compute technical indicators, on-chain metrics, volume features (see `feature-engineering` skill)
2. **Label creation** — forward returns with threshold, drop neutral zone
3. **Walk-forward split** — time-ordered train/test windows with gap
4. **Train model** — XGBoost or LightGBM on each training window
5. **Predict on test** — generate out-of-sample probability predictions
6. **Aggregate predictions** — concatenate all out-of-sample results
7. **Evaluate** — accuracy, precision, recall, F1, AUC, profit factor

### Quick Training Example

```python
from xgboost import XGBClassifier

model = XGBClassifier(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric="logloss",
    use_label_encoder=False,
    random_state=42,
)

model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    verbose=False,
)

probabilities = model.predict_proba(X_test)[:, 1]
```

See `references/model_guide.md` for parameter recommendations and tuning.

## SHAP Feature Importance

SHAP (SHapley Additive exPlanations) provides the gold standard for understanding model predictions.

### Global Feature Importance

Which features matter most across all predictions:

```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# Summary plot (top 15 features)
shap.summary_plot(shap_values, X_test, max_display=15)
```

### Local Explanations

Why a specific prediction was made:

```python
# Explain a single prediction
shap.force_plot(explainer.expected_value, shap_values[0], X_test.iloc[0])
```

### Temporal Feature Importance

Track how feature importance drifts over walk-forward windows. If a feature's importance drops significantly, the market regime may have shifted.

## Threshold Optimization

The default 0.5 probability threshold is almost never optimal for trading.

### Why Not 0.5?

- Class imbalance: if 60% of labels are "up", a 0.5 threshold is too aggressive
- Trading costs: marginal signals (0.51 probability) rarely cover transaction costs
- Asymmetric payoffs: precision matters more than recall for trading

### Optimize for Profit Factor

```python
def optimize_threshold(
    probabilities: np.ndarray,
    returns: np.ndarray,
    thresholds: np.ndarray | None = None,
) -> tuple[float, float]:
    """Find threshold that maximizes profit factor.

    Args:
        probabilities: Model predicted probabilities.
        returns: Actual forward returns.
        thresholds: Thresholds to search over.

    Returns:
        Tuple of (best_threshold, best_profit_factor).
    """
    if thresholds is None:
        thresholds = np.arange(0.50, 0.85, 0.01)
    best_threshold, best_pf = 0.5, 0.0
    for t in thresholds:
        signals = probabilities >= t
        if signals.sum() < 10:
            continue
        signal_returns = returns[signals]
        wins = signal_returns[signal_returns > 0].sum()
        losses = abs(signal_returns[signal_returns < 0].sum())
        pf = wins / losses if losses > 0 else 0.0
        if pf > best_pf:
            best_pf = pf
            best_threshold = t
    return best_threshold, best_pf
```

Typical finding: optimal threshold is 0.60-0.75 for crypto trading signals.

## Crypto-Specific Considerations

### Short Training Windows

Crypto market regimes change fast. A model trained on 6 months of data may perform worse than one trained on 30 days. Use shorter training windows and retrain frequently.

### Class Imbalance

Most time periods are "flat" (returns within the neutral zone). Strategies to handle this:

- **Drop neutral zone**: only train on clear up/down labels
- **Undersample majority class**: `scale_pos_weight` in XGBoost
- **SMOTE**: synthetic minority oversampling (use cautiously — can introduce lookahead)
- **Adjust threshold**: raise the probability threshold to compensate

### Transaction Costs

A model with 55% accuracy sounds good, but after 0.5% round-trip costs (slippage + fees), many signals become unprofitable. Always evaluate signals net of costs:

```python
net_return = gross_return - 0.005  # 50 bps round-trip
```

### Feature Decay

Features lose predictive power over time as more participants discover and trade on them. Monitor rolling performance and retrain when metrics degrade.

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `feature-engineering` | Compute input features for the classifier |
| `vectorbt` | Backtest trading strategies from ML signals |
| `regime-detection` | Train separate models per regime, or use regime as a feature |
| `position-sizing` | Size positions based on classifier confidence |
| `risk-management` | Apply portfolio-level risk limits to ML-generated signals |

## Files

### References
- `references/model_guide.md` — XGBoost and LightGBM parameter guide, tuning, and ensembling
- `references/validation_methods.md` — Walk-forward, purged CV, CPCV, and evaluation metrics

### Scripts
- `scripts/train_classifier.py` — Train a signal classifier with walk-forward validation and feature importance
- `scripts/walk_forward_backtest.py` — Backtest ML signals vs buy-and-hold with walk-forward validation

## Dependencies

```bash
# Core (required)
uv pip install pandas numpy scikit-learn

# Optional (recommended)
uv pip install xgboost lightgbm shap
```

## Key Takeaways

1. **Walk-forward validation is non-negotiable** — random CV will give you wildly inflated results
2. **Optimize threshold for profit factor**, not accuracy — a high-precision, low-recall model beats a high-accuracy one
3. **Short training windows** for crypto — 30 days beats 6 months in most regimes
4. **Monitor feature decay** — retrain when rolling metrics drop below baseline
5. **Always evaluate net of costs** — a 55% accurate model may be unprofitable after fees
6. **SHAP over raw feature importance** — SHAP gives consistent, theoretically grounded explanations
