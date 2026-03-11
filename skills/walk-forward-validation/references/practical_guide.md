# Walk-Forward Validation — Practical Guide for Crypto

## Window Size Selection

### Principles

1. **Train window must span at least one full market cycle** — or else the model only learns one regime. In crypto, a "cycle" can be as short as 2–4 weeks for altcoins.
2. **Train window should not be so long that stale data dilutes signal** — crypto market structure changes rapidly. Data from 2 years ago may be from a fundamentally different market.
3. **Test window must be long enough for statistical significance** — a 1-day test window produces noisy estimates. Aim for at least 30 independent observations.
4. **Step size determines compute cost** — smaller steps = more folds = better estimates but longer runtime.

### Recommended Window Sizes

| Strategy Type | Train | Test | Step | Embargo | Rationale |
|---|---|---|---|---|---|
| HFT / Scalping (1-5min bars) | 3-7 days | 1 day | 1 day | 2-4 hours | Microstructure changes fast |
| Intraday (15min-1h bars) | 14-30 days | 3-7 days | 3 days | 12-24 hours | Need multiple day/night cycles |
| Swing (4h-daily bars) | 30-90 days | 7-14 days | 7 days | 2-5 days | Must span regime transitions |
| Position (daily-weekly) | 90-180 days | 14-30 days | 14 days | 5-10 days | Longer horizon, need full cycles |
| ML Features (daily) | 60-120 days | 14-21 days | 7 days | 3-5 days | Balance data volume vs recency |

### Crypto vs Equities

| Aspect | Equities | Crypto |
|---|---|---|
| Typical train window | 1-3 years (252-756 bars) | 1-6 months (30-180 bars) |
| Market hours | 6.5h/day, 252 days/year | 24/7/365 |
| Regime change frequency | Quarterly to yearly | Weekly to monthly |
| Data availability | Decades | 2-8 years for most tokens |
| Survivorship bias severity | Moderate | Severe (tokens delist constantly) |
| Recommended approach | Expanding window | Rolling window |

## Regime-Aware Validation

### Why Regimes Matter

A strategy that works in high-volatility trending markets may lose money in low-volatility mean-reverting markets. If your train and test windows both fall within the same regime, validation results are misleading.

### Simple Regime Detection for Splits

Use volatility and trend to classify market regime before splitting:

```python
import numpy as np

def classify_regime(
    returns: np.ndarray,
    lookback: int = 20,
) -> np.ndarray:
    """Classify each bar as trending-volatile, trending-quiet, etc."""
    n = len(returns)
    regimes = np.empty(n, dtype="U20")
    for i in range(lookback, n):
        window = returns[i - lookback : i]
        vol = np.std(window) * np.sqrt(365)  # Annualized
        trend = np.sum(window)  # Cumulative return
        if vol > 0.8:  # High vol threshold (crypto)
            regimes[i] = "trending-up" if trend > 0 else "trending-down"
        else:
            regimes[i] = "quiet-up" if trend > 0 else "quiet-down"
    regimes[:lookback] = "unknown"
    return regimes
```

### Regime-Aware Split Strategy

1. **Classify** each bar into a regime
2. **Verify** that each train window spans at least 2 different regimes
3. **Track** the regime composition of each test window
4. **Report** performance broken down by regime
5. **Flag** folds where train and test are the same regime

If most folds have matching train/test regimes, the validation is unreliable for out-of-regime performance.

## Common Validation Mistakes

### 1. Not Purging Labels

**Mistake:** Using 5-day forward returns as labels without purging the 5-day overlap between train and test.

**Result:** Information leakage inflates accuracy by 10–30%.

**Fix:** Always purge `label_horizon` bars from the end of training data.

### 2. Using Future Information in Features

**Mistake:** Normalizing features using the full dataset's mean/std before splitting.

**Result:** Test set statistics leak into training features.

**Fix:** Fit scalers/normalizers on training data only. Transform test data using training statistics.

```python
# WRONG
scaler.fit(all_data)
train_scaled = scaler.transform(train_data)
test_scaled = scaler.transform(test_data)

# RIGHT
scaler.fit(train_data)
train_scaled = scaler.transform(train_data)
test_scaled = scaler.transform(test_data)
```

### 3. Optimizing Hyperparameters on Test Data

**Mistake:** Using the test fold to tune hyperparameters (learning rate, lookback periods, thresholds).

**Result:** Hyperparameters are fit to the test set, destroying its validity.

**Fix:** Use a three-way split: train / validation / test. Tune on validation, evaluate on test. Or use nested cross-validation.

### 4. Ignoring Transaction Costs

**Mistake:** Computing walk-forward returns without accounting for spreads, slippage, and fees.

**Result:** A strategy with 200 trades/day and 0.5 bps edge appears profitable, but 5 bps per round-trip cost makes it a loser.

**Fix:** Always include realistic transaction costs. For Solana DEX trades, minimum 0.3% (swap fee + slippage).

### 5. Too Few Folds

**Mistake:** Using 3 walk-forward folds and reporting the average.

**Result:** High variance in the estimate. One good or bad fold dominates.

**Fix:** Use at least 8–10 folds, or CPCV to generate 15+ paths.

### 6. Reporting In-Sample Metrics

**Mistake:** Reporting training set performance alongside (or instead of) test set performance.

**Result:** Misleading impression of strategy quality.

**Fix:** Only report out-of-sample metrics. Track the train/test ratio as an overfitting diagnostic.

### 7. Not Accounting for Multiple Testing

**Mistake:** Testing 50 parameter combinations, selecting the best, and reporting its backtest result.

**Result:** The best of 50 random strategies will look profitable by chance alone.

**Fix:** Use the Deflated Sharpe Ratio to adjust for the number of trials.

### 8. Survivorship Bias in Token Universe

**Mistake:** Backtesting on tokens that exist today, ignoring delisted tokens.

**Result:** Returns are inflated because you only test tokens that survived.

**Fix:** Include delisted tokens in your universe, or at minimum report that survivorship bias is present and estimate its magnitude.

## Validation Checklist

Before trusting any backtest result, verify:

- [ ] Time series ordering is respected (no future data in training)
- [ ] Labels are purged at train/test boundaries
- [ ] Embargo period is applied after purging
- [ ] Features are normalized using training data only
- [ ] Transaction costs are included (realistic for the venue)
- [ ] At least 8 walk-forward folds or 15 CPCV paths
- [ ] Deflated Sharpe Ratio > 0.95 (accounting for all trials)
- [ ] PBO < 0.30 (if using strategy selection)
- [ ] Train/test Sharpe ratio < 2.0
- [ ] Results reported per-regime if possible
- [ ] Hyperparameters tuned on validation set, not test set
- [ ] Survivorship bias acknowledged or addressed

## Reporting Template

When presenting walk-forward results, include:

```
Walk-Forward Validation Report
==============================
Window type:        Rolling (90-day train, 14-day test)
Number of folds:    12
Embargo:            3 days
Purge horizon:      1 day
Date range:         2025-01-01 to 2025-12-31
Strategies tested:  25

Out-of-Sample Results:
  Mean Sharpe:        1.42
  Sharpe Std Dev:     0.38
  Mean Return:        +3.2% per fold
  Win Rate:           58.3%
  Max Drawdown:       -8.7%

Overfitting Metrics:
  Train/Test SR:      1.65
  Deflated SR:        0.87
  PBO:                0.22

Regime Breakdown:
  Trending-Up:    SR 2.1 (4 folds)
  Trending-Down:  SR 0.8 (3 folds)
  Quiet:          SR 1.1 (5 folds)
```
