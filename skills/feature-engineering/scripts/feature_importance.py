#!/usr/bin/env python3
"""Rank features by predictive power and identify redundant features.

Trains a random forest classifier on trading features, computes feature
importance using both MDI (Mean Decrease in Impurity) and permutation
methods, and flags redundant features via inter-correlation analysis.

Usage:
    python scripts/feature_importance.py                    # Demo mode
    python scripts/feature_importance.py --csv features.csv # From CSV file

Dependencies:
    uv pip install pandas numpy scipy scikit-learn

Environment Variables:
    None required (uses synthetic data or CSV input).
"""

import argparse
import sys
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import adfuller


# ── Configuration ───────────────────────────────────────────────────
N_ESTIMATORS: int = 100
MAX_DEPTH: int = 5
RANDOM_STATE: int = 42
CORRELATION_THRESHOLD: float = 0.9
TEST_FRACTION: float = 0.2
N_PERMUTATION_REPEATS: int = 5

# Feature parameters (must match build_features.py)
MOMENTUM_WINDOWS: list[int] = [5, 10, 20]
VOLATILITY_WINDOW: int = 20
VOLUME_WINDOW: int = 20
RSI_PERIOD: int = 14
BB_PERIOD: int = 20
BB_STD: float = 2.0
ATR_PERIOD: int = 14
FORWARD_PERIODS: int = 5
LABEL_THRESHOLD: float = 0.01


# ── Demo Data Generation ───────────────────────────────────────────
def generate_demo_features(n_bars: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data and compute features for demo mode.

    Replicates the feature computation from build_features.py so this
    script is fully self-contained.

    Args:
        n_bars: Number of bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with computed features and labels.
    """
    rng = np.random.default_rng(seed)

    # Generate price series with regime switching
    returns = np.zeros(n_bars)
    regime = 0
    for i in range(n_bars):
        if rng.random() < 0.05:
            regime = rng.choice([-1, 0, 1])
        returns[i] = regime * 0.002 + rng.normal(0, 0.03)

    price = 100.0 * np.exp(np.cumsum(returns))
    high_pct = np.abs(rng.normal(0.01, 0.005, n_bars))
    low_pct = np.abs(rng.normal(0.01, 0.005, n_bars))
    close = price
    high = close * (1 + high_pct)
    low = close * (1 - low_pct)
    open_price = close * (1 + rng.normal(0, 0.005, n_bars))
    high = np.maximum(high, np.maximum(open_price, close))
    low = np.minimum(low, np.minimum(open_price, close))
    base_volume = 1_000_000 * np.exp(rng.normal(0, 0.3, n_bars))
    volume = base_volume * rng.choice([1.0, 1.0, 1.0, 2.5, 4.0], size=n_bars)
    timestamps = pd.date_range("2025-01-01", periods=n_bars, freq="1h", tz="UTC")

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })

    # Compute features (inline to keep script self-contained)
    c, h_col, l_col, o_col, v = df["close"], df["high"], df["low"], df["open"], df["volume"]

    # Price features
    df["log_return"] = np.log(c / c.shift(1))
    df["abs_return"] = df["log_return"].abs()
    df["return_volatility"] = df["log_return"].rolling(VOLATILITY_WINDOW).std()
    for w in MOMENTUM_WINDOWS:
        df[f"momentum_{w}"] = c / c.shift(w) - 1
    df["acceleration"] = df["momentum_5"] - df["momentum_5"].shift(5)
    hl_range = h_col - l_col
    df["high_low_range"] = hl_range / c
    df["close_position"] = np.where(hl_range > 0, (c - l_col) / hl_range, 0.5)
    df["gap"] = o_col / c.shift(1) - 1
    df["rolling_skew"] = df["log_return"].rolling(VOLATILITY_WINDOW).skew()
    df["rolling_kurtosis"] = df["log_return"].rolling(VOLATILITY_WINDOW).kurt()

    # Volume features
    vol_ma = v.rolling(VOLUME_WINDOW).mean()
    df["volume_ratio"] = v / vol_ma
    df["volume_ma_ratio"] = v.rolling(5).mean() / vol_ma
    sign = np.sign(df["log_return"]).fillna(0)
    obv = (sign * v).cumsum()
    df["obv_slope"] = _rolling_slope(obv, 10)
    tp = (h_col + l_col + c) / 3
    cum_tp_vol = (tp * v).rolling(VOLUME_WINDOW).sum()
    cum_vol = v.rolling(VOLUME_WINDOW).sum()
    vwap = cum_tp_vol / cum_vol
    df["vwap_deviation"] = (c - vwap) / vwap
    df["volume_acceleration"] = df["volume_ratio"] - df["volume_ratio"].shift(1)
    dv = c * v
    df["dollar_volume_ratio"] = dv / dv.rolling(VOLUME_WINDOW).mean()
    df["volume_cv"] = v.rolling(VOLUME_WINDOW).std() / vol_ma

    # Technical features
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=RSI_PERIOD, min_periods=RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(span=RSI_PERIOD, min_periods=RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    df["macd_histogram"] = macd_line - signal_line
    bb_mid = c.rolling(BB_PERIOD).mean()
    bb_std = c.rolling(BB_PERIOD).std()
    bb_upper = bb_mid + BB_STD * bb_std
    bb_lower = bb_mid - BB_STD * bb_std
    bb_rng = bb_upper - bb_lower
    df["bb_position"] = np.where(bb_rng > 0, (c - bb_lower) / bb_rng, 0.5)
    df["bb_width"] = bb_rng / bb_mid
    tr = pd.concat([h_col - l_col, (h_col - c.shift(1)).abs(), (l_col - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()
    df["atr_ratio"] = atr / c

    # Time features
    ts = pd.to_datetime(df["timestamp"])
    hour = ts.dt.hour + ts.dt.minute / 60.0
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["day_of_week_sin"] = np.sin(2 * np.pi * ts.dt.dayofweek / 7)

    # Labels
    df["forward_return"] = c.shift(-FORWARD_PERIODS) / c - 1
    df["label"] = (df["forward_return"] > LABEL_THRESHOLD).astype(int)

    return df


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """Compute rolling linear regression slope.

    Args:
        series: Input time series.
        window: Rolling window size.

    Returns:
        Series of slope values.
    """
    slopes = np.full(len(series), np.nan)
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    values = series.values
    for i in range(window - 1, len(values)):
        y = values[i - window + 1: i + 1]
        if np.any(np.isnan(y)):
            continue
        y_mean = y.mean()
        slopes[i] = ((x - x_mean) * (y - y_mean)).sum() / x_var
    return pd.Series(slopes, index=series.index)


# ── Feature Column Detection ───────────────────────────────────────
def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Identify feature columns (excluding OHLCV, timestamp, target).

    Args:
        df: DataFrame with all columns.

    Returns:
        List of feature column names.
    """
    exclude = {
        "timestamp", "open", "high", "low", "close", "volume",
        "forward_return", "label",
    }
    return [c for c in df.columns if c not in exclude]


# ── Importance Computation ──────────────────────────────────────────
def compute_mdi_importance(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    n_estimators: int = N_ESTIMATORS,
    max_depth: int = MAX_DEPTH,
) -> pd.Series:
    """Compute Mean Decrease in Impurity feature importance.

    Args:
        X_train: Training features.
        y_train: Training labels.
        n_estimators: Number of trees in the forest.
        max_depth: Maximum tree depth.

    Returns:
        Series of importance values indexed by feature name, sorted descending.
    """
    from sklearn.ensemble import RandomForestClassifier

    rf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    importances = pd.Series(
        rf.feature_importances_, index=X_train.columns
    ).sort_values(ascending=False)
    return importances


def compute_permutation_importance(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    n_estimators: int = N_ESTIMATORS,
    max_depth: int = MAX_DEPTH,
) -> pd.DataFrame:
    """Compute permutation importance on test set.

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_test: Test features.
        y_test: Test labels.
        n_estimators: Number of trees.
        max_depth: Maximum tree depth.

    Returns:
        DataFrame with columns: feature, perm_importance_mean, perm_importance_std.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.inspection import permutation_importance

    rf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)

    result = permutation_importance(
        rf, X_test, y_test,
        n_repeats=N_PERMUTATION_REPEATS,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    perm_df = pd.DataFrame({
        "feature": X_test.columns,
        "perm_importance_mean": result.importances_mean,
        "perm_importance_std": result.importances_std,
    }).sort_values("perm_importance_mean", ascending=False)

    return perm_df


# ── Redundancy Analysis ────────────────────────────────────────────
def find_redundant_features(
    X: pd.DataFrame, threshold: float = CORRELATION_THRESHOLD
) -> list[dict[str, object]]:
    """Identify pairs of features with correlation above threshold.

    Args:
        X: Feature DataFrame.
        threshold: Correlation threshold for redundancy.

    Returns:
        List of dicts with keys: feature_1, feature_2, correlation.
    """
    corr = X.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    redundant = []
    for col in upper.columns:
        for idx in upper.index:
            val = upper.loc[idx, col]
            if pd.notna(val) and val > threshold:
                redundant.append({
                    "feature_1": idx,
                    "feature_2": col,
                    "correlation": round(val, 4),
                })
    return sorted(redundant, key=lambda x: x["correlation"], reverse=True)


def get_features_to_drop(
    redundant_pairs: list[dict[str, object]],
    importances: pd.Series,
) -> list[str]:
    """Determine which feature to drop from each redundant pair.

    Keeps the feature with higher importance and drops the other.

    Args:
        redundant_pairs: Output of find_redundant_features.
        importances: Feature importance series.

    Returns:
        List of feature names to drop.
    """
    to_drop: set[str] = set()
    for pair in redundant_pairs:
        f1, f2 = pair["feature_1"], pair["feature_2"]
        imp1 = importances.get(f1, 0)
        imp2 = importances.get(f2, 0)
        drop = f2 if imp1 >= imp2 else f1
        to_drop.add(drop)
    return sorted(to_drop)


# ── Reporting ───────────────────────────────────────────────────────
def print_importance_report(
    mdi: pd.Series,
    perm_df: pd.DataFrame,
    redundant_pairs: list[dict[str, object]],
    features_to_drop: list[str],
    train_accuracy: float,
    test_accuracy: float,
) -> None:
    """Print comprehensive feature importance report.

    Args:
        mdi: MDI importance series.
        perm_df: Permutation importance DataFrame.
        redundant_pairs: Redundant feature pairs.
        features_to_drop: Features recommended for removal.
        train_accuracy: Training set accuracy.
        test_accuracy: Test set accuracy.
    """
    print("=" * 72)
    print("FEATURE IMPORTANCE REPORT")
    print("=" * 72)

    # Model performance
    print(f"\nRandom Forest (n={N_ESTIMATORS}, depth={MAX_DEPTH})")
    print(f"  Train accuracy: {train_accuracy:.3f}")
    print(f"  Test accuracy:  {test_accuracy:.3f}")
    gap = train_accuracy - test_accuracy
    if gap > 0.15:
        print(f"  WARNING: Large train/test gap ({gap:.3f}) suggests overfitting.")
    print()

    # MDI importance
    print("-" * 72)
    print("MDI IMPORTANCE (Mean Decrease in Impurity)")
    print("-" * 72)
    print(f"{'Rank':<5} {'Feature':<25} {'Importance':>12} {'Redundant':>10}")
    print("-" * 55)
    for rank, (feat, imp) in enumerate(mdi.items(), 1):
        flag = "DROP" if feat in features_to_drop else ""
        print(f"{rank:<5} {feat:<25} {imp:>12.4f} {flag:>10}")
    print()

    # Permutation importance
    print("-" * 72)
    print("PERMUTATION IMPORTANCE (on test set)")
    print("-" * 72)
    print(f"{'Rank':<5} {'Feature':<25} {'Mean':>10} {'Std':>10}")
    print("-" * 55)
    for rank, (_, row) in enumerate(perm_df.iterrows(), 1):
        print(
            f"{rank:<5} {row['feature']:<25} "
            f"{row['perm_importance_mean']:>10.4f} "
            f"{row['perm_importance_std']:>10.4f}"
        )
    print()

    # Redundancy
    print("-" * 72)
    print(f"REDUNDANT FEATURE PAIRS (correlation > {CORRELATION_THRESHOLD})")
    print("-" * 72)
    if redundant_pairs:
        for pair in redundant_pairs:
            print(
                f"  {pair['feature_1']} <-> {pair['feature_2']} "
                f"(r={pair['correlation']})"
            )
        print(f"\nRecommended drops (lower importance in pair): {features_to_drop}")
    else:
        print("  No redundant pairs found.")
    print()

    # Summary
    n_keep = len(mdi) - len(features_to_drop)
    print("-" * 72)
    print("SUMMARY")
    print("-" * 72)
    print(f"  Total features: {len(mdi)}")
    print(f"  Redundant (drop): {len(features_to_drop)}")
    print(f"  Recommended keep: {n_keep}")
    top5 = list(mdi.head(5).index)
    print(f"  Top 5 features: {', '.join(top5)}")
    print()
    print("=" * 72)
    print("This analysis is for informational purposes only, not financial advice.")
    print("=" * 72)


# ── Main ────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Rank features by predictive power and identify redundancy."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="",
        help="Path to CSV with pre-computed features (from build_features.py).",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=300,
        help="Number of bars for demo data (default: 300).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: compute feature importance and print report."""
    args = parse_args()

    # Load or generate data
    if args.csv:
        print(f"Loading features from {args.csv}...")
        try:
            df = pd.read_csv(args.csv)
        except FileNotFoundError:
            print(f"ERROR: File not found: {args.csv}")
            sys.exit(1)
        if "label" not in df.columns:
            print("ERROR: CSV must contain a 'label' column.")
            sys.exit(1)
    else:
        print(f"Generating {args.bars} bars of demo data...")
        df = generate_demo_features(n_bars=args.bars)

    feature_cols = get_feature_columns(df)
    print(f"Found {len(feature_cols)} features.\n")

    # Prepare clean data
    clean = df[feature_cols + ["label"]].dropna()
    if len(clean) < 50:
        print(f"ERROR: Only {len(clean)} clean rows. Need at least 50.")
        sys.exit(1)

    X = clean[feature_cols]
    y = clean["label"]

    # Temporal train/test split
    split_idx = int(len(X) * (1 - TEST_FRACTION))
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    print(f"Train: {len(X_train)} rows | Test: {len(X_test)} rows")
    print(f"Train label balance: {y_train.mean():.1%} positive")
    print(f"Test label balance:  {y_test.mean():.1%} positive")
    print()

    # Import sklearn here (after data is ready)
    from sklearn.ensemble import RandomForestClassifier

    # Train model for accuracy
    print("Training random forest...")
    rf = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=MAX_DEPTH,
        random_state=RANDOM_STATE,
        class_weight="balanced",
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    train_acc = rf.score(X_train, y_train)
    test_acc = rf.score(X_test, y_test)

    # MDI importance
    print("Computing MDI importance...")
    mdi = compute_mdi_importance(X_train, y_train)

    # Permutation importance
    print("Computing permutation importance...")
    perm_df = compute_permutation_importance(X_train, y_train, X_test, y_test)

    # Redundancy analysis
    print("Analyzing feature redundancy...")
    redundant_pairs = find_redundant_features(X)
    features_to_drop = get_features_to_drop(redundant_pairs, mdi)

    print()
    print_importance_report(
        mdi, perm_df, redundant_pairs, features_to_drop,
        train_acc, test_acc,
    )


if __name__ == "__main__":
    main()
