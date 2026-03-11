# Walk-Forward Validation — Methodology

## Overview

Walk-forward validation is the gold standard for evaluating trading strategies and financial ML models. It simulates the real-world process of training on historical data and trading on unseen future data.

## Time Series Splitting

### Rolling Window

Fixed-size training window slides forward through data:

```
Time:  t0 ──────────────────────────────────────────── tN

Fold 1: [────TRAIN────][─TEST─]
Fold 2:        [────TRAIN────][─TEST─]
Fold 3:               [────TRAIN────][─TEST─]
```

**Formal definition:**
- Given data `X[0..T]`, train size `W`, test size `H`, step `S`
- Fold `i`: train = `X[i*S .. i*S + W - 1]`, test = `X[i*S + W .. i*S + W + H - 1]`
- Number of folds: `floor((T - W - H + 1) / S) + 1`

### Expanding Window

Training window grows from a fixed start:

```
Time:  t0 ──────────────────────────────────────────── tN

Fold 1: [──TRAIN──][─TEST─]
Fold 2: [──────TRAIN──────][─TEST─]
Fold 3: [──────────TRAIN──────────][─TEST─]
```

**Formal definition:**
- Given data `X[0..T]`, minimum train size `W_min`, test size `H`, step `S`
- Fold `i`: train = `X[0 .. W_min + i*S - 1]`, test = `X[W_min + i*S .. W_min + i*S + H - 1]`
- Number of folds: `floor((T - W_min - H + 1) / S) + 1`

## Purging

### The Problem

When labels are computed over a forward-looking horizon (e.g., "5-day forward return"), a training sample at time `t` uses information up to time `t + horizon`. If the test set begins at time `t_test`, any training sample where `t + horizon >= t_test` has label information that overlaps with the test period.

### The Solution

Remove (purge) training samples whose label computation windows overlap with the test set:

```
purged_train = {i in train : timestamp[i] + label_horizon < test_start_time}
```

### Example

- Label = 24-hour forward return
- Test starts at hour 100
- Training sample at hour 98 uses data from hours 98–122 (overlaps test)
- Training sample at hour 75 uses data from hours 75–99 (overlaps test by 1 hour at boundary)
- Training sample at hour 74 uses data from hours 74–98 (safe, does not reach hour 100)
- Purge samples 75–99 from training

## Embargo

### The Problem

Even after purging, serial correlation in features means that training samples just before the test boundary carry information about the test period through correlated features.

### The Solution

Add a buffer (embargo) between the last training sample and the first test sample:

```
[===TRAIN===][~~EMBARGO~~][===TEST===]
```

The embargo period is excluded from both training and testing. Typical size: 1–5x the autocorrelation decay length of the features.

### Sizing the Embargo

Compute the autocorrelation function (ACF) of your features. The embargo should span enough lags for the ACF to decay below a significance threshold (commonly 2/sqrt(N)):

```python
import numpy as np

def estimate_embargo_size(feature_series: np.ndarray, threshold: float = 0.05) -> int:
    """Estimate embargo size from autocorrelation decay."""
    n = len(feature_series)
    mean = np.mean(feature_series)
    var = np.var(feature_series)
    if var == 0:
        return 1
    acf_values = []
    for lag in range(1, min(n // 4, 100)):
        c = np.mean((feature_series[:-lag] - mean) * (feature_series[lag:] - mean)) / var
        acf_values.append(abs(c))
        if abs(c) < threshold:
            return lag
    return len(acf_values)
```

## Combinatorial Purged Cross-Validation (CPCV)

### Motivation

Standard walk-forward produces a small number of test paths (typically 5–20 folds). This is insufficient for statistical tests like PBO, which need many independent backtest paths. CPCV solves this by generating all valid combinations.

### Algorithm

1. **Partition** the data into `N` contiguous, non-overlapping groups: `G_1, G_2, ..., G_N`
2. **Choose** `k` groups as the test set (typically `k = 2`)
3. **Train** on the remaining `N - k` groups
4. **Purge** training samples at each boundary between a training group and an adjacent test group
5. **Embargo** additional samples after each purge boundary
6. **Repeat** for all `C(N, k)` combinations

### Number of Paths

With `N` groups and `k` test groups:
- Number of combinations: `C(N, k) = N! / (k! * (N-k)!)`
- Each combination produces one backtest path

| N | k | Combinations |
|---|---|---|
| 6 | 2 | 15 |
| 8 | 2 | 28 |
| 10 | 2 | 45 |
| 10 | 3 | 120 |
| 12 | 2 | 66 |

### Purging at Internal Boundaries

Unlike simple walk-forward, CPCV may have train-test boundaries in the middle of the data (not just at the end of training). Every boundary between a training group and a test group requires purging:

```
Groups: [G1:train][G2:test][G3:train][G4:test][G5:train]

Purge zones:
  - End of G1 (train before G2 test)
  - Start of G3 (train after G2 test)
  - End of G3 (train before G4 test)
  - Start of G5 (train after G4 test)
```

### CPCV Implementation Sketch

```python
from itertools import combinations

def cpcv_splits(
    n_samples: int,
    n_groups: int,
    n_test_groups: int,
    purge_window: int = 0,
    embargo_window: int = 0,
) -> list[tuple[list[int], list[int]]]:
    """Generate all CPCV train/test splits."""
    group_size = n_samples // n_groups
    groups = []
    for i in range(n_groups):
        start = i * group_size
        end = (i + 1) * group_size if i < n_groups - 1 else n_samples
        groups.append(list(range(start, end)))

    splits = []
    for test_combo in combinations(range(n_groups), n_test_groups):
        test_set = set()
        for g in test_combo:
            test_set.update(groups[g])

        train_set = set(range(n_samples)) - test_set

        # Purge and embargo at each boundary
        for g in test_combo:
            test_start = groups[g][0]
            test_end = groups[g][-1]
            # Purge before test
            for j in range(max(0, test_start - purge_window), test_start):
                train_set.discard(j)
            # Embargo after test
            for j in range(test_end + 1, min(n_samples, test_end + 1 + embargo_window)):
                train_set.discard(j)

        splits.append((sorted(train_set), sorted(test_set)))
    return splits
```

## Aggregating Results

### Per-Fold Metrics

For each fold, compute:
- **Out-of-sample Sharpe ratio**: `mean(oos_returns) / std(oos_returns) * sqrt(annualization_factor)`
- **Out-of-sample returns**: Total return over the test period
- **Hit rate**: Fraction of correct directional predictions
- **Maximum drawdown**: Worst peak-to-trough decline in test period

### Cross-Fold Aggregation

- **Mean OOS Sharpe**: Average Sharpe across all folds (primary metric)
- **Sharpe ratio of Sharpe ratios**: Stability measure — high variance across folds suggests overfitting
- **Train/Test Sharpe ratio**: If train Sharpe >> test Sharpe, the model is overfitting
- **Rank correlation (IS vs OOS)**: Spearman correlation between in-sample and out-of-sample rankings across parameter sets

A train/test Sharpe ratio above 2.0 is a strong signal of overfitting. Ratios near 1.0 indicate robust generalization.
