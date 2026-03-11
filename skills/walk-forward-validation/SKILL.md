---
name: walk-forward-validation
description: Walk-forward validation framework for trading strategies and ML models with time-series-aware splits, overfit detection, and regime-aware validation
---

# Walk-Forward Validation

Walk-forward validation framework for trading strategies and ML models. Standard cross-validation (k-fold, random splits) fails catastrophically for financial time series because it introduces lookahead bias and ignores autocorrelation. This skill covers proper time-series validation techniques including rolling and expanding windows, purged cross-validation, combinatorial purged cross-validation (CPCV), and overfit detection metrics.

## Why Standard Cross-Validation Fails

Standard k-fold CV assumes data points are independent and identically distributed (IID). Financial time series violate both assumptions:

1. **Lookahead bias** — Random splits let the model train on future data and predict past data, artificially inflating performance.
2. **Autocorrelation** — Adjacent observations are correlated. A random split that puts Monday in test and Tuesday in train leaks information.
3. **Regime dependence** — Markets shift between regimes. A model trained on a bull market and tested on a bull market tells you nothing about bear market performance.
4. **Label overlap** — If labels are computed over windows (e.g., 24h forward return), adjacent train/test samples share label computation periods, leaking information.

## Walk-Forward Framework

### Rolling Window (Fixed Train Size)

The train window has a fixed size and slides forward in time. This is preferred when you believe older data is less relevant (common in crypto).

```
Window 1: [===TRAIN===][=TEST=]
Window 2:    [===TRAIN===][=TEST=]
Window 3:       [===TRAIN===][=TEST=]
```

**Parameters:**
- `train_size`: Number of bars/days in the training window
- `test_size`: Number of bars/days in the test window
- `step_size`: How far to advance between folds (often equals `test_size`)

### Expanding Window (Growing Train)

The train window starts at the beginning and expands forward. This uses all available historical data, which helps when data is scarce.

```
Window 1: [==TRAIN==][=TEST=]
Window 2: [====TRAIN====][=TEST=]
Window 3: [======TRAIN======][=TEST=]
```

**Parameters:**
- `min_train_size`: Minimum training samples before first fold
- `test_size`: Fixed test window size
- `step_size`: How far to advance between folds

### Choosing Between Them

| Factor | Rolling | Expanding |
|---|---|---|
| Data recency | Prioritizes recent data | Uses all history |
| Regime changes | Better adapts to new regimes | May dilute recent regime |
| Sample size | Fixed, may be small | Grows over time |
| Crypto preference | Preferred for < 6mo horizons | Better for regime-stable models |

## Purging and Embargo

### Purging

Remove training samples whose labels overlap with the test set's time range. If a label is computed as the 24h forward return starting at time `t`, any training sample where `t + 24h` extends into the test period must be purged.

```python
def purge_train_indices(
    train_idx: list[int],
    test_start: int,
    label_horizon: int,
    timestamps: list[int],
) -> list[int]:
    """Remove train samples whose label windows overlap test period."""
    test_start_time = timestamps[test_start]
    return [
        i for i in train_idx
        if timestamps[i] + label_horizon < test_start_time
    ]
```

### Embargo

Add a buffer gap between the end of training and start of testing to account for serial correlation that purging alone does not eliminate.

```
[===TRAIN===][--EMBARGO--][=TEST=]
```

Typical embargo sizes:
- **1-minute bars**: 60–240 bars (1–4 hours)
- **5-minute bars**: 12–48 bars (1–4 hours)
- **Hourly bars**: 6–24 bars (6–24 hours)
- **Daily bars**: 2–5 bars (2–5 days)
- **Crypto rule of thumb**: Embargo >= 2x the label computation horizon

## Combinatorial Purged Cross-Validation (CPCV)

CPCV (Lopez de Prado, 2018) generates all possible train/test combinations from `N` groups while maintaining temporal ordering. This produces far more test paths than standard walk-forward, enabling statistical tests for overfitting.

**Key properties:**
- Splits data into `N` contiguous groups
- For each combination of `k` test groups, the remaining `N-k` groups form the training set
- Applies purging and embargo at each train/test boundary
- Produces `C(N, k)` backtest paths (e.g., N=6, k=2 gives 15 paths)

See `references/methodology.md` for the full CPCV algorithm and formulas.

## Overfit Detection

### Deflated Sharpe Ratio (DSR)

The observed Sharpe ratio must be adjusted for:
- Number of strategies tested (multiple testing)
- Non-normality of returns (skewness, kurtosis)
- Length of the backtest

```python
import numpy as np
from scipy.stats import norm

def deflated_sharpe_ratio(
    observed_sr: float,
    num_trials: int,
    backtest_length: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Compute the probability that observed SR > 0 after deflation.

    Args:
        observed_sr: Annualized Sharpe ratio of the selected strategy.
        num_trials: Number of strategies tested (including discarded ones).
        backtest_length: Number of return observations.
        skewness: Skewness of returns.
        kurtosis: Excess kurtosis of returns.

    Returns:
        p-value (probability SR is genuinely > 0).
    """
    sr_std = np.sqrt(
        (1 - skewness * observed_sr + (kurtosis - 1) / 4 * observed_sr**2)
        / (backtest_length - 1)
    )
    # Expected max SR under null (Euler-Mascheroni approximation)
    euler_mascheroni = 0.5772156649
    expected_max_sr = norm.ppf(1 - 1 / num_trials) * (
        1 - euler_mascheroni
    ) + euler_mascheroni * norm.ppf(1 - 1 / (num_trials * np.e))
    dsr = norm.cdf((observed_sr - expected_max_sr) / sr_std)
    return dsr
```

A DSR below 0.95 suggests the observed performance is likely due to overfitting across the trials tested.

### Probability of Backtest Overfitting (PBO)

PBO uses CPCV to measure the fraction of backtest paths where the in-sample optimal strategy underperforms the median out-of-sample. A PBO above 0.50 indicates more-likely-than-not overfitting.

See `references/overfit_detection.md` for complete derivations and implementation details.

## Crypto-Specific Considerations

1. **Shorter windows**: Crypto regimes change faster than equities. A 90-day rolling window may be more appropriate than 252 days.
2. **24/7 markets**: No weekends or holidays to account for, but funding rate resets (every 8h on perps) create microstructure effects.
3. **Survivorship bias**: Many tokens delist. Validation must include delisted tokens or at minimum acknowledge this limitation.
4. **Liquidity regime shifts**: A token's liquidity profile can change dramatically (new CEX listing, liquidity mining end). Train/test splits should ideally not straddle major liquidity events.
5. **Data availability**: Many tokens have < 1 year of data. Expanding windows with small `min_train_size` may be necessary.

## Practical Window Sizes for Crypto

| Strategy Timeframe | Train Window | Test Window | Embargo |
|---|---|---|---|
| Scalping (1-5min) | 3-7 days | 1 day | 2-4 hours |
| Intraday (15min-1h) | 14-30 days | 3-7 days | 12-24 hours |
| Swing (4h-daily) | 30-90 days | 7-14 days | 2-5 days |
| Position (daily-weekly) | 90-180 days | 30 days | 5-10 days |

## Quick Start

```python
from walk_forward import WalkForwardValidator, WalkForwardConfig

config = WalkForwardConfig(
    train_size=90,
    test_size=14,
    step_size=14,
    window_type="rolling",
    embargo_size=3,
    purge_horizon=1,
)

validator = WalkForwardValidator(config)
for fold in validator.split(price_data):
    model.fit(fold.train_X, fold.train_y)
    predictions = model.predict(fold.test_X)
    fold.record_performance(predictions, fold.test_y)

results = validator.aggregate_results()
print(f"OOS Sharpe: {results.oos_sharpe:.3f}")
print(f"Train/Test Sharpe ratio: {results.sharpe_ratio_ratio:.2f}")
```

## Files

### References
- `references/methodology.md` — Walk-forward theory, window types, purging, embargo, CPCV algorithm with formulas
- `references/overfit_detection.md` — Deflated Sharpe ratio, probability of backtest overfitting, multiple testing corrections
- `references/practical_guide.md` — Window size selection for crypto, regime considerations, common validation mistakes

### Scripts
- `scripts/walk_forward.py` — Walk-forward validation engine with rolling and expanding windows; `--demo` mode with synthetic data
- `scripts/overfit_detector.py` — Deflated Sharpe ratio and PBO computation; `--demo` mode with synthetic backtest results
