# Signal Classification — Validation Methods

## Walk-Forward Validation

### Why Time-Series CV, Not Random CV

Random k-fold cross-validation shuffles data, allowing the model to train on future data and predict the past. This creates **lookahead bias** — the most common and devastating mistake in trading ML.

Walk-forward validation enforces temporal ordering: the model only ever predicts data it has never seen, in chronological order.

**Impact**: Random CV typically inflates accuracy by 10-30% compared to walk-forward. A model showing 65% accuracy with random CV may only achieve 52% walk-forward.

### Implementation

```python
import numpy as np
from typing import Iterator

def walk_forward_splits(
    n_samples: int,
    train_size: int = 720,
    test_size: int = 168,
    step_size: int = 24,
    gap: int = 24,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test splits respecting time order.

    Args:
        n_samples: Total number of time-ordered samples.
        train_size: Training window length in bars.
        test_size: Test window length in bars.
        step_size: How far to advance between windows.
        gap: Embargo period between train end and test start.

    Yields:
        Tuples of (train_indices, test_indices).
    """
    start = 0
    while start + train_size + gap + test_size <= n_samples:
        train_end = start + train_size
        test_start = train_end + gap
        test_end = test_start + test_size
        train_idx = np.arange(start, train_end)
        test_idx = np.arange(test_start, test_end)
        yield train_idx, test_idx
        start += step_size
```

### Metrics Aggregation

Aggregate out-of-sample predictions across all walk-forward windows:

1. **Concatenation**: combine all OOS predictions, compute metrics once on the full set
2. **Per-window averaging**: compute metrics per window, report mean and std
3. **Weighted averaging**: weight each window by number of test samples

Method 1 (concatenation) is preferred — it gives a single set of realistic metrics.

### Minimum Requirements

For statistically meaningful results:

- **30+ test periods** across all windows combined
- **100+ trades** (signals that exceed threshold) total
- **5+ walk-forward windows** to assess stability
- **Test window > 2x forward return horizon** to avoid single-event dominance

## Purged Cross-Validation

### The Problem

If the forward return horizon is 24 bars, then bars at the boundary between train and test overlap: the label for bar T-24 depends on the price at bar T, which is in the test set. This creates subtle leakage.

### The Solution: Embargo Period

Insert a gap between train end and test start equal to the forward return horizon:

```
[====TRAIN====][--GAP--][===TEST===]
                ^^^^^^^
           embargo period
```

**Typical gap size**: same as the forward return horizon. If predicting 24-hour returns, use a 24-bar gap.

### Implementation

The `gap` parameter in the walk-forward function above handles this. Always set `gap >= forward_return_horizon`.

## Combinatorial Purged Cross-Validation (CPCV)

### Concept

Standard walk-forward gives one path through the data. CPCV generates multiple train/test paths using combinatorial selection of blocks:

1. Divide data into N contiguous blocks (e.g., N=10)
2. Select k blocks for testing (e.g., k=2)
3. Use remaining blocks for training
4. Apply purging at boundaries
5. Repeat for all C(N, k) combinations

This gives C(10, 2) = 45 different train/test configurations, producing more robust estimates.

### When to Use CPCV

- Sufficient data: need at least 1000+ samples
- High-stakes model selection: choosing between model architectures
- Research: validating that a signal is real, not noise
- Computationally feasible: C(N, k) models to train

### When Walk-Forward Is Sufficient

- Moderate data: 500-2000 samples
- Rapid iteration: testing many feature combinations
- Production: regular retraining on latest data

## Evaluating Trading Classifiers

### Why Accuracy Is Misleading

If 60% of your labels are "up" (bull market bias), a model that always predicts "up" achieves 60% accuracy. Accuracy tells you nothing about trading profitability.

### Precision

**Of all signals the model gives, what fraction are correct?**

```
Precision = True Positives / (True Positives + False Positives)
```

High precision = fewer but more reliable signals. For trading, precision > 0.55 is a reasonable target for crypto.

### Recall

**Of all actual profitable opportunities, what fraction did the model catch?**

```
Recall = True Positives / (True Positives + False Negatives)
```

High recall = catching most moves, but with more false signals. Less important for trading — missing trades is okay, losing money is not.

### F1 Score

Harmonic mean of precision and recall. A balanced metric, but still not trading-specific.

### AUC-ROC

Area under the receiver operating characteristic curve. Measures the model's ability to rank positive samples higher than negative ones. AUC > 0.55 is meaningful for trading; AUC > 0.60 is strong.

### Trading-Specific Metrics

These matter more than generic ML metrics:

**Profit Factor from Signals**

```python
def signal_profit_factor(
    predictions: np.ndarray,
    returns: np.ndarray,
    threshold: float = 0.5,
) -> float:
    """Compute profit factor from ML signals.

    Args:
        predictions: Model predicted probabilities.
        returns: Actual forward returns.
        threshold: Signal threshold.

    Returns:
        Profit factor (gross_profit / gross_loss).
    """
    signals = predictions >= threshold
    if signals.sum() == 0:
        return 0.0
    signal_returns = returns[signals]
    gross_profit = signal_returns[signal_returns > 0].sum()
    gross_loss = abs(signal_returns[signal_returns < 0].sum())
    return gross_profit / gross_loss if gross_loss > 0 else float("inf")
```

Target: profit factor > 1.3 after costs.

**Expected Return per Signal**

```python
def expected_return_per_signal(
    predictions: np.ndarray,
    returns: np.ndarray,
    threshold: float = 0.5,
    cost: float = 0.005,
) -> float:
    """Average return per signal, net of transaction costs.

    Args:
        predictions: Model predicted probabilities.
        returns: Actual forward returns.
        threshold: Signal threshold.
        cost: Round-trip transaction cost (default 50bps).

    Returns:
        Mean return per signal after costs.
    """
    signals = predictions >= threshold
    if signals.sum() == 0:
        return 0.0
    return float(np.mean(returns[signals]) - cost)
```

Target: positive expected return net of 50bps round-trip costs.

## Overfitting Detection

### Train vs Test Metric Gap

Compare metrics on training data vs out-of-sample test data:

| Gap (train - test) | Interpretation |
|---------------------|----------------|
| < 5% | Healthy — model generalizes well |
| 5-15% | Mild overfit — consider more regularization |
| 15-30% | Significant overfit — reduce complexity |
| > 30% | Severe overfit — model is memorizing noise |

### Metric Degradation Over Time

Plot out-of-sample metrics for each walk-forward window chronologically. If metrics decline steadily, the model's features are losing predictive power (feature decay).

### Random Signal Baseline

Compare your model against a random signal generator:

```python
random_accuracy = np.mean(np.random.randint(0, 2, size=len(y_test)) == y_test)
random_pf = signal_profit_factor(np.random.rand(len(y_test)), returns_test)
```

Your model should significantly exceed random baseline across all windows, not just on average.

### Practical Thresholds

A signal classification model is worth deploying if:

- Walk-forward AUC > 0.55 consistently across windows
- Profit factor > 1.3 at optimal threshold, net of costs
- Expected return per signal > 0 net of costs
- Train-test metric gap < 15%
- Performance is stable (not declining) across walk-forward windows
- Model generates at least 2-3 signals per day for sufficient volume
