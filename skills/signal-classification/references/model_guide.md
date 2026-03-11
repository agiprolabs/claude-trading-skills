# Signal Classification — Model Guide

## XGBoost for Trading

### Installation

```bash
uv pip install xgboost
```

### Key Parameters

| Parameter | Default | Recommended | Purpose |
|-----------|---------|-------------|---------|
| `n_estimators` | 100 | 200 | Number of boosting rounds |
| `max_depth` | 6 | 4 | Maximum tree depth (lower = less overfit) |
| `learning_rate` | 0.3 | 0.05 | Step size shrinkage (lower = needs more rounds) |
| `subsample` | 1.0 | 0.8 | Fraction of samples per tree |
| `colsample_bytree` | 1.0 | 0.8 | Fraction of features per tree |
| `min_child_weight` | 1 | 5 | Minimum sum of instance weight in a child |
| `gamma` | 0 | 0.1 | Minimum loss reduction for a split |
| `reg_alpha` | 0 | 0.01 | L1 regularization |
| `reg_lambda` | 1 | 1.0 | L2 regularization |
| `scale_pos_weight` | 1 | ratio neg/pos | Handles class imbalance |

### Recommended Starting Configuration

```python
from xgboost import XGBClassifier

model = XGBClassifier(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    gamma=0.1,
    reg_alpha=0.01,
    reg_lambda=1.0,
    eval_metric="logloss",
    use_label_encoder=False,
    random_state=42,
    n_jobs=-1,
)
```

### Overfitting Control

- **Early stopping**: stop training when validation metric stops improving

```python
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    verbose=False,
)
```

- **max_depth=3-5**: deeper trees memorize noise
- **min_child_weight=5-10**: prevents splits on tiny groups
- **subsample + colsample_bytree < 1.0**: adds randomness, reduces variance

### Feature Importance

```python
# Gain-based importance (preferred)
importance = model.get_booster().get_score(importance_type="gain")

# Or via sklearn interface
importance = dict(zip(feature_names, model.feature_importances_))
```

## LightGBM for Trading

### Installation

```bash
uv pip install lightgbm
```

### Key Parameters

| Parameter | Default | Recommended | Purpose |
|-----------|---------|-------------|---------|
| `num_leaves` | 31 | 31 | Maximum leaves per tree (primary complexity control) |
| `n_estimators` | 100 | 200 | Number of boosting rounds |
| `learning_rate` | 0.1 | 0.05 | Step size shrinkage |
| `feature_fraction` | 1.0 | 0.8 | Fraction of features per tree (= colsample_bytree) |
| `bagging_fraction` | 1.0 | 0.8 | Fraction of data per tree (= subsample) |
| `bagging_freq` | 0 | 5 | Perform bagging every N iterations |
| `min_child_samples` | 20 | 20 | Minimum samples in a leaf |
| `reg_alpha` | 0 | 0.01 | L1 regularization |
| `reg_lambda` | 0 | 1.0 | L2 regularization |
| `max_depth` | -1 | 6 | Max tree depth (-1 = unlimited) |

### Recommended Starting Configuration

```python
import lightgbm as lgb

model = lgb.LGBMClassifier(
    num_leaves=31,
    n_estimators=200,
    learning_rate=0.05,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=5,
    min_child_samples=20,
    reg_alpha=0.01,
    reg_lambda=1.0,
    max_depth=6,
    random_state=42,
    n_jobs=-1,
    verbose=-1,
)
```

### LightGBM vs XGBoost Key Differences

- LightGBM uses leaf-wise growth (deeper, narrower trees); XGBoost uses level-wise
- `num_leaves` controls complexity in LightGBM; `max_depth` controls it in XGBoost
- LightGBM is typically 2-5x faster on datasets > 10k samples
- Rule of thumb: `num_leaves` should be < `2^max_depth` to avoid overfitting

## Comparison: XGBoost vs LightGBM

| Aspect | XGBoost | LightGBM |
|--------|---------|----------|
| Training speed | Moderate | Fast (2-5x faster) |
| Memory usage | Higher | Lower |
| Accuracy | Very good | Very good (comparable) |
| Small datasets (<5k) | Slightly better | Good |
| Large datasets (>50k) | Good | Better |
| Missing values | Native support | Native support |
| Categorical features | Requires encoding | Native support |
| Community | Very large | Large |
| Interpretability | Good | Good |

**Recommendation**: Use XGBoost for small trading datasets (<10k samples). Use LightGBM for larger datasets or when training speed matters (e.g., hyperparameter search).

## Hyperparameter Tuning with Optuna

Use walk-forward validation as the objective to avoid overfitting the hyperparameters:

```python
import optuna

def objective(trial: optuna.Trial) -> float:
    """Optuna objective using walk-forward profit factor."""
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500),
        "max_depth": trial.suggest_int("max_depth", 3, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
    }
    # Run walk-forward with these params, return avg profit factor
    avg_pf = run_walk_forward(X, y, returns, params)
    return avg_pf

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=50)
best_params = study.best_params
```

**Critical**: the walk-forward validation inside the objective must use the same windows you will use in production. Do not optimize on random CV metrics.

## Ensemble Methods

### Simple Average

Average predictions from XGBoost and LightGBM for more robust signals:

```python
def ensemble_predict(
    xgb_model: "XGBClassifier",
    lgb_model: "LGBMClassifier",
    X: "pd.DataFrame",
    weights: tuple[float, float] = (0.5, 0.5),
) -> "np.ndarray":
    """Weighted average of XGBoost and LightGBM predictions.

    Args:
        xgb_model: Trained XGBoost classifier.
        lgb_model: Trained LightGBM classifier.
        X: Feature matrix.
        weights: Weights for each model (must sum to 1).

    Returns:
        Blended probability predictions.
    """
    xgb_prob = xgb_model.predict_proba(X)[:, 1]
    lgb_prob = lgb_model.predict_proba(X)[:, 1]
    return weights[0] * xgb_prob + weights[1] * lgb_prob
```

### Stacking

Use out-of-sample predictions from walk-forward as features for a meta-model:

1. Run walk-forward with XGBoost — collect OOS predictions
2. Run walk-forward with LightGBM — collect OOS predictions
3. Train a logistic regression on (xgb_pred, lgb_pred) -> label
4. Use the meta-model for final predictions

Stacking adds complexity. Start with simple averaging and only stack if it demonstrably improves out-of-sample metrics.

## Common Mistakes

1. **Using random CV instead of walk-forward**: inflates metrics by 10-30%
2. **Too many estimators without early stopping**: memorizes training data
3. **Ignoring class imbalance**: model predicts majority class for everything
4. **Optimizing hyperparameters on test data**: double-dipping produces overfit params
5. **max_depth > 6**: almost always overfits on trading data
6. **Not setting random_state**: results are not reproducible
7. **Forgetting to set verbose=False/n_jobs**: noisy output and single-threaded training
