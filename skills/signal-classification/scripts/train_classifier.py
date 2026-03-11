#!/usr/bin/env python3
"""Train a signal classifier with walk-forward validation and feature importance.

Demonstrates the full ML signal classification pipeline:
1. Generate synthetic features or load provided data
2. Create binary labels from forward returns
3. Walk-forward train/test splitting
4. Model training (XGBoost or sklearn DecisionTree fallback)
5. Out-of-sample evaluation with multiple metrics
6. Feature importance ranking
7. Probability threshold optimization for profit factor

Usage:
    python scripts/train_classifier.py
    python scripts/train_classifier.py --demo
    python scripts/train_classifier.py --samples 500 --features 20

Dependencies:
    uv pip install pandas numpy scikit-learn
    uv pip install xgboost  # optional, falls back to sklearn
    uv pip install shap     # optional, for SHAP feature importance

Environment Variables:
    None required — uses synthetic data by default.
"""

import argparse
import sys
import warnings
from typing import Iterator, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Configuration ───────────────────────────────────────────────────
DEFAULT_SAMPLES = 200
DEFAULT_FEATURES = 15
FORWARD_HORIZON = 12       # bars to compute forward return
RETURN_THRESHOLD = 0.01    # 1% threshold for up/down label
TRAIN_SIZE = 60            # training window in bars
TEST_SIZE = 20             # test window in bars
STEP_SIZE = 10             # step between walk-forward windows
GAP_SIZE = 12              # embargo equal to forward horizon


# ── Synthetic Data Generation ───────────────────────────────────────
def generate_synthetic_data(
    n_samples: int = DEFAULT_SAMPLES,
    n_features: int = DEFAULT_FEATURES,
    signal_strength: float = 0.3,
    seed: int = 42,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Generate synthetic feature matrix with embedded predictive signal.

    Creates features where the first few have genuine (noisy) predictive
    power for forward returns, and the rest are pure noise. This simulates
    a realistic feature matrix where only some features matter.

    Args:
        n_samples: Number of time-ordered samples to generate.
        n_features: Number of features to create.
        signal_strength: How strong the embedded signal is (0=none, 1=perfect).
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (feature_dataframe, forward_returns, prices).
    """
    rng = np.random.default_rng(seed)

    # Generate a price series with trend and mean-reversion
    noise = rng.normal(0, 0.02, n_samples)
    trend = np.sin(np.linspace(0, 4 * np.pi, n_samples)) * 0.01
    log_returns = trend + noise
    prices = 100.0 * np.exp(np.cumsum(log_returns))

    # Forward returns
    fwd_returns = np.full(n_samples, np.nan)
    for i in range(n_samples - FORWARD_HORIZON):
        fwd_returns[i] = prices[i + FORWARD_HORIZON] / prices[i] - 1.0

    # Feature names
    feature_names = [
        "momentum_12", "momentum_24", "rsi_14", "vol_ratio",
        "price_zscore", "volume_trend", "high_low_range", "close_open_ratio",
        "ma_cross_signal", "bb_width", "atr_norm", "obv_slope",
        "vwap_deviation", "skewness_20", "kurtosis_20",
    ]
    # Pad or truncate to match n_features
    while len(feature_names) < n_features:
        feature_names.append(f"noise_feat_{len(feature_names)}")
    feature_names = feature_names[:n_features]

    # Generate features — first 5 have predictive power
    features = {}
    n_signal_features = min(5, n_features)

    for i in range(n_signal_features):
        # Correlated with future returns (with noise)
        signal = fwd_returns.copy()
        signal[np.isnan(signal)] = 0.0
        noise_component = rng.normal(0, 1, n_samples)
        features[feature_names[i]] = (
            signal_strength * signal / (np.std(signal) + 1e-8)
            + (1 - signal_strength) * noise_component
        )

    for i in range(n_signal_features, n_features):
        # Pure noise features
        features[feature_names[i]] = rng.normal(0, 1, n_samples)

    df = pd.DataFrame(features)
    return df, fwd_returns, prices


# ── Label Creation ──────────────────────────────────────────────────
def create_binary_labels(
    fwd_returns: np.ndarray,
    threshold: float = RETURN_THRESHOLD,
) -> np.ndarray:
    """Create binary labels from forward returns.

    Labels: 1 = up (return > threshold), 0 = down (return < -threshold),
    NaN = neutral (within threshold, excluded from training).

    Args:
        fwd_returns: Array of forward returns.
        threshold: Minimum absolute return for a valid label.

    Returns:
        Array with 1 (up), 0 (down), or NaN (neutral/invalid).
    """
    labels = np.full(len(fwd_returns), np.nan)
    labels[fwd_returns > threshold] = 1.0
    labels[fwd_returns < -threshold] = 0.0
    return labels


# ── Walk-Forward Splitting ──────────────────────────────────────────
def walk_forward_splits(
    n_samples: int,
    train_size: int = TRAIN_SIZE,
    test_size: int = TEST_SIZE,
    step_size: int = STEP_SIZE,
    gap: int = GAP_SIZE,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test index splits.

    Respects temporal ordering and includes an embargo gap between
    train and test to prevent label leakage.

    Args:
        n_samples: Total number of time-ordered samples.
        train_size: Number of training samples per window.
        test_size: Number of test samples per window.
        step_size: Step between successive windows.
        gap: Gap between train end and test start (embargo).

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


# ── Model Factory ───────────────────────────────────────────────────
def create_model(model_type: str = "auto") -> object:
    """Create a classifier model.

    Tries XGBoost first, falls back to sklearn GradientBoostingClassifier.

    Args:
        model_type: One of 'auto', 'xgboost', 'sklearn'.

    Returns:
        An sklearn-compatible classifier instance.
    """
    if model_type in ("auto", "xgboost"):
        try:
            from xgboost import XGBClassifier

            return XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=0.1,
                eval_metric="logloss",
                use_label_encoder=False,
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            )
        except ImportError:
            if model_type == "xgboost":
                print("XGBoost not installed. Install with: uv pip install xgboost")
                sys.exit(1)

    # Fallback to sklearn
    from sklearn.ensemble import GradientBoostingClassifier

    return GradientBoostingClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        random_state=42,
    )


# ── Walk-Forward Training ──────────────────────────────────────────
def run_walk_forward(
    X: pd.DataFrame,
    y: np.ndarray,
    fwd_returns: np.ndarray,
    model_type: str = "auto",
) -> dict:
    """Run walk-forward training and collect out-of-sample predictions.

    Args:
        X: Feature matrix (n_samples x n_features).
        y: Binary labels (1=up, 0=down, NaN=excluded).
        fwd_returns: Forward returns for profit factor computation.
        model_type: Model type to use.

    Returns:
        Dictionary with per-fold metrics and aggregated results.
    """
    # Identify valid (non-NaN) label indices
    valid_mask = ~np.isnan(y)

    all_test_indices: list[int] = []
    all_predictions: list[float] = []
    all_true_labels: list[float] = []
    all_returns: list[float] = []
    fold_metrics: list[dict] = []
    feature_importances: list[np.ndarray] = []

    fold_num = 0
    for train_idx, test_idx in walk_forward_splits(len(X)):
        # Filter to valid labels
        train_valid = train_idx[valid_mask[train_idx]]
        test_valid = test_idx[valid_mask[test_idx]]

        if len(train_valid) < 20 or len(test_valid) < 5:
            continue

        fold_num += 1
        X_train = X.iloc[train_valid]
        y_train = y[train_valid]
        X_test = X.iloc[test_valid]
        y_test = y[test_valid]
        test_returns = fwd_returns[test_valid]

        # Train model
        model = create_model(model_type)
        model.fit(X_train, y_train)

        # Predict probabilities
        probs = model.predict_proba(X_test)[:, 1]

        # Compute fold metrics
        preds_binary = (probs >= 0.5).astype(int)
        acc = accuracy_score(y_test, preds_binary)
        prec = precision_score(y_test, preds_binary, zero_division=0)
        rec = recall_score(y_test, preds_binary, zero_division=0)
        f1 = f1_score(y_test, preds_binary, zero_division=0)

        try:
            auc = roc_auc_score(y_test, probs)
        except ValueError:
            auc = 0.5  # Only one class in test set

        fold_metrics.append({
            "fold": fold_num,
            "n_train": len(train_valid),
            "n_test": len(test_valid),
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "auc": auc,
        })

        # Collect feature importance
        if hasattr(model, "feature_importances_"):
            feature_importances.append(model.feature_importances_)

        # Aggregate predictions
        all_test_indices.extend(test_valid.tolist())
        all_predictions.extend(probs.tolist())
        all_true_labels.extend(y_test.tolist())
        all_returns.extend(test_returns.tolist())

    if not fold_metrics:
        print("ERROR: No valid walk-forward folds. Increase data or adjust windows.")
        sys.exit(1)

    # Aggregate feature importance
    avg_importance = None
    if feature_importances:
        avg_importance = np.mean(feature_importances, axis=0)

    return {
        "fold_metrics": fold_metrics,
        "all_predictions": np.array(all_predictions),
        "all_true_labels": np.array(all_true_labels),
        "all_returns": np.array(all_returns),
        "avg_feature_importance": avg_importance,
        "feature_names": list(X.columns),
        "n_folds": fold_num,
    }


# ── Threshold Optimization ─────────────────────────────────────────
def optimize_threshold(
    probabilities: np.ndarray,
    returns: np.ndarray,
    cost: float = 0.005,
    min_signals: int = 10,
) -> tuple[float, float, int]:
    """Find the probability threshold that maximizes profit factor.

    Args:
        probabilities: Model predicted probabilities for the positive class.
        returns: Actual forward returns corresponding to predictions.
        cost: Round-trip transaction cost to subtract from each trade.
        min_signals: Minimum number of signals required at a threshold.

    Returns:
        Tuple of (best_threshold, best_profit_factor, n_signals).
    """
    thresholds = np.arange(0.45, 0.85, 0.01)
    best_threshold = 0.5
    best_pf = 0.0
    best_n = 0

    for t in thresholds:
        signals = probabilities >= t
        n_signals = int(signals.sum())
        if n_signals < min_signals:
            continue

        signal_returns = returns[signals] - cost
        gross_profit = float(signal_returns[signal_returns > 0].sum())
        gross_loss = float(abs(signal_returns[signal_returns < 0].sum()))

        pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
        if pf > best_pf:
            best_pf = pf
            best_threshold = float(t)
            best_n = n_signals

    return best_threshold, best_pf, best_n


# ── SHAP Analysis ───────────────────────────────────────────────────
def compute_shap_importance(
    model: object,
    X_sample: pd.DataFrame,
    max_samples: int = 100,
) -> Optional[pd.DataFrame]:
    """Compute SHAP feature importance if shap is available.

    Args:
        model: Trained tree-based model.
        X_sample: Feature matrix to explain.
        max_samples: Maximum samples for SHAP computation.

    Returns:
        DataFrame with feature names and mean absolute SHAP values,
        or None if shap is not installed.
    """
    try:
        import shap
    except ImportError:
        return None

    sample = X_sample.iloc[:max_samples]

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(sample)

        # Handle binary classification (may return list of arrays)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]  # positive class

        mean_abs_shap = np.mean(np.abs(shap_values), axis=0)
        importance_df = pd.DataFrame({
            "feature": sample.columns,
            "mean_abs_shap": mean_abs_shap,
        }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

        return importance_df
    except Exception:
        return None


# ── Reporting ───────────────────────────────────────────────────────
def print_report(results: dict, threshold_info: tuple) -> None:
    """Print a comprehensive classification report.

    Args:
        results: Output from run_walk_forward.
        threshold_info: Output from optimize_threshold.
    """
    print("\n" + "=" * 70)
    print("SIGNAL CLASSIFICATION — WALK-FORWARD RESULTS")
    print("=" * 70)

    # Per-fold metrics
    print(f"\n{'Fold':>4}  {'Train':>6}  {'Test':>5}  {'Acc':>6}  "
          f"{'Prec':>6}  {'Rec':>6}  {'F1':>6}  {'AUC':>6}")
    print("-" * 55)

    for fm in results["fold_metrics"]:
        print(f"{fm['fold']:>4}  {fm['n_train']:>6}  {fm['n_test']:>5}  "
              f"{fm['accuracy']:>6.3f}  {fm['precision']:>6.3f}  "
              f"{fm['recall']:>6.3f}  {fm['f1']:>6.3f}  {fm['auc']:>6.3f}")

    # Aggregate metrics
    all_preds = results["all_predictions"]
    all_labels = results["all_true_labels"]

    preds_binary = (all_preds >= 0.5).astype(int)
    agg_acc = accuracy_score(all_labels, preds_binary)
    agg_prec = precision_score(all_labels, preds_binary, zero_division=0)
    agg_rec = recall_score(all_labels, preds_binary, zero_division=0)
    agg_f1 = f1_score(all_labels, preds_binary, zero_division=0)

    try:
        agg_auc = roc_auc_score(all_labels, all_preds)
    except ValueError:
        agg_auc = 0.5

    print("-" * 55)
    print(f"{'AGG':>4}  {'':>6}  {len(all_labels):>5}  "
          f"{agg_acc:>6.3f}  {agg_prec:>6.3f}  "
          f"{agg_rec:>6.3f}  {agg_f1:>6.3f}  {agg_auc:>6.3f}")

    # Threshold optimization
    best_t, best_pf, n_signals = threshold_info
    print(f"\n{'THRESHOLD OPTIMIZATION':>40}")
    print("-" * 40)
    print(f"  Optimal threshold:  {best_t:.2f}")
    print(f"  Profit factor:      {best_pf:.3f}")
    print(f"  Signals at threshold: {n_signals}")
    print(f"  Signal rate:        {n_signals / len(all_preds) * 100:.1f}%")

    # Feature importance
    if results["avg_feature_importance"] is not None:
        imp = results["avg_feature_importance"]
        names = results["feature_names"]
        sorted_idx = np.argsort(imp)[::-1]

        print(f"\n{'FEATURE IMPORTANCE (top 10)':>40}")
        print("-" * 40)
        for rank, idx in enumerate(sorted_idx[:10], 1):
            bar = "#" * int(imp[idx] / imp[sorted_idx[0]] * 20)
            print(f"  {rank:>2}. {names[idx]:<20} {imp[idx]:.4f}  {bar}")

    # Assessment
    print(f"\n{'MODEL ASSESSMENT':>40}")
    print("-" * 40)

    if agg_auc > 0.55:
        print("  AUC > 0.55: Model shows predictive power")
    else:
        print("  AUC <= 0.55: Model may not have predictive power")

    if best_pf > 1.3:
        print(f"  Profit factor {best_pf:.2f} > 1.3: Potentially tradeable")
    elif best_pf > 1.0:
        print(f"  Profit factor {best_pf:.2f}: Marginal after costs")
    else:
        print(f"  Profit factor {best_pf:.2f} < 1.0: Not profitable")

    avg_fold_auc = np.mean([fm["auc"] for fm in results["fold_metrics"]])
    std_fold_auc = np.std([fm["auc"] for fm in results["fold_metrics"]])
    print(f"  AUC stability: {avg_fold_auc:.3f} +/- {std_fold_auc:.3f}")

    if std_fold_auc > 0.10:
        print("  WARNING: High AUC variance across folds — unstable model")

    print("\nNote: This analysis is for informational purposes only.")
    print("Past model performance does not guarantee future results.")
    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run the signal classification pipeline."""
    parser = argparse.ArgumentParser(
        description="Train a signal classifier with walk-forward validation."
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run in demo mode with default synthetic data.",
    )
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES,
        help=f"Number of samples to generate (default: {DEFAULT_SAMPLES}).",
    )
    parser.add_argument(
        "--features", type=int, default=DEFAULT_FEATURES,
        help=f"Number of features to generate (default: {DEFAULT_FEATURES}).",
    )
    parser.add_argument(
        "--model", type=str, default="auto",
        choices=["auto", "xgboost", "sklearn"],
        help="Model type to use (default: auto).",
    )
    parser.add_argument(
        "--signal-strength", type=float, default=0.3,
        help="Strength of embedded signal in synthetic data (0-1, default: 0.3).",
    )
    args = parser.parse_args()

    print("Signal Classification — Train Classifier")
    print(f"  Samples: {args.samples}, Features: {args.features}")
    print(f"  Model: {args.model}, Signal strength: {args.signal_strength}")
    print(f"  Walk-forward: train={TRAIN_SIZE}, test={TEST_SIZE}, "
          f"step={STEP_SIZE}, gap={GAP_SIZE}")

    # Step 1: Generate data
    print("\n[1/5] Generating synthetic data...")
    X, fwd_returns, prices = generate_synthetic_data(
        n_samples=args.samples,
        n_features=args.features,
        signal_strength=args.signal_strength,
    )
    print(f"  Feature matrix: {X.shape[0]} samples x {X.shape[1]} features")

    # Step 2: Create labels
    print("[2/5] Creating binary labels...")
    y = create_binary_labels(fwd_returns, threshold=RETURN_THRESHOLD)
    n_up = int(np.nansum(y == 1))
    n_down = int(np.nansum(y == 0))
    n_neutral = int(np.isnan(y).sum())
    print(f"  Up: {n_up}, Down: {n_down}, Neutral (dropped): {n_neutral}")

    # Step 3: Walk-forward training
    print("[3/5] Running walk-forward validation...")
    results = run_walk_forward(X, y, fwd_returns, model_type=args.model)
    print(f"  Completed {results['n_folds']} folds, "
          f"{len(results['all_predictions'])} out-of-sample predictions")

    # Step 4: Threshold optimization
    print("[4/5] Optimizing probability threshold...")
    threshold_info = optimize_threshold(
        results["all_predictions"],
        results["all_returns"],
    )
    print(f"  Best threshold: {threshold_info[0]:.2f}, "
          f"Profit factor: {threshold_info[1]:.3f}")

    # Step 5: SHAP (optional)
    print("[5/5] Computing feature importance...")
    shap_df = None
    try:
        model = create_model(args.model)
        valid = ~np.isnan(y)
        model.fit(X[valid], y[valid])
        shap_df = compute_shap_importance(model, X[valid])
        if shap_df is not None:
            print("  SHAP importance computed successfully")
        else:
            print("  SHAP not available (install: uv pip install shap)")
            print("  Using built-in feature importance instead")
    except Exception as e:
        print(f"  SHAP computation skipped: {e}")

    # Report
    print_report(results, threshold_info)

    if shap_df is not None:
        print(f"\n{'SHAP FEATURE IMPORTANCE':>40}")
        print("-" * 40)
        for _, row in shap_df.head(10).iterrows():
            bar = "#" * int(
                row["mean_abs_shap"] / shap_df["mean_abs_shap"].max() * 20
            )
            print(f"  {row['feature']:<20} {row['mean_abs_shap']:.4f}  {bar}")


if __name__ == "__main__":
    main()
