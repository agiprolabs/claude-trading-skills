#!/usr/bin/env python3
"""Backtest ML signals vs buy-and-hold with walk-forward validation.

Demonstrates end-to-end workflow:
1. Generate synthetic price data with an embedded signal
2. Build features from price data
3. Create forward-return labels
4. Run walk-forward classification
5. Convert ML probabilities to trading signals via threshold
6. Simulate trading based on ML signals
7. Compare: ML strategy vs buy-and-hold vs random signals

Usage:
    python scripts/walk_forward_backtest.py
    python scripts/walk_forward_backtest.py --demo
    python scripts/walk_forward_backtest.py --bars 500 --threshold 0.60

Dependencies:
    uv pip install pandas numpy scikit-learn

Environment Variables:
    None required — uses synthetic data.
"""

import argparse
import sys
import warnings
from typing import Iterator

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Configuration ───────────────────────────────────────────────────
DEFAULT_BARS = 500
FORWARD_HORIZON = 12
RETURN_THRESHOLD = 0.01
TRAIN_SIZE = 100
TEST_SIZE = 30
STEP_SIZE = 15
GAP_SIZE = 12
TRANSACTION_COST = 0.005  # 50 bps round-trip


# ── Data Generation ─────────────────────────────────────────────────
def generate_price_data(
    n_bars: int = DEFAULT_BARS,
    signal_strength: float = 0.15,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with an embedded tradeable pattern.

    Creates a price series with a mean-reverting component that can
    be detected by ML models. The signal_strength controls how
    detectable the pattern is.

    Args:
        n_bars: Number of bars to generate.
        signal_strength: Strength of embedded pattern (0=random, 1=obvious).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)

    # Base price with trend and cycles
    t = np.arange(n_bars, dtype=float)
    trend = 0.0001 * t  # slight uptrend
    cycle = signal_strength * 0.02 * np.sin(2 * np.pi * t / 50)
    noise = rng.normal(0, 0.015, n_bars)

    log_returns = trend + cycle + noise
    close = 100.0 * np.exp(np.cumsum(log_returns))

    # Generate OHLCV from close
    spread = rng.uniform(0.002, 0.01, n_bars)
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_price = close * (1 + rng.normal(0, 0.003, n_bars))

    # Volume with mean-reversion correlation
    base_volume = rng.lognormal(mean=10, sigma=0.5, size=n_bars)
    volume = base_volume * (1 + 2 * np.abs(log_returns) / 0.015)

    df = pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


# ── Feature Engineering ─────────────────────────────────────────────
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build trading features from OHLCV data.

    Computes a set of common technical features without using
    external TA libraries (pure numpy/pandas).

    Args:
        df: DataFrame with open, high, low, close, volume columns.

    Returns:
        DataFrame of features aligned with input index.
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values
    n = len(close)

    features: dict[str, np.ndarray] = {}

    # Returns at various lookbacks
    for lb in [3, 6, 12, 24]:
        ret = np.full(n, np.nan)
        ret[lb:] = close[lb:] / close[:-lb] - 1
        features[f"return_{lb}"] = ret

    # RSI approximation (14-bar)
    period = 14
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)
    avg_gain[period] = np.mean(gain[1:period + 1])
    avg_loss[period] = np.mean(loss[1:period + 1])
    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = avg_gain / (avg_loss + 1e-10)
    features["rsi_14"] = 100 - 100 / (1 + rs)

    # Volatility (rolling std of returns)
    for window in [10, 20]:
        vol = np.full(n, np.nan)
        returns = np.diff(close, prepend=close[0]) / np.maximum(close, 1e-10)
        for i in range(window, n):
            vol[i] = np.std(returns[i - window:i])
        features[f"volatility_{window}"] = vol

    # Volume ratio (current / moving average)
    for window in [10, 20]:
        vol_ma = np.full(n, np.nan)
        for i in range(window, n):
            vol_ma[i] = np.mean(volume[i - window:i])
        features[f"volume_ratio_{window}"] = volume / (vol_ma + 1e-10)

    # Price position in range (0 = at low, 1 = at high)
    for window in [10, 20]:
        pos = np.full(n, np.nan)
        for i in range(window, n):
            h = np.max(high[i - window:i + 1])
            l = np.min(low[i - window:i + 1])
            pos[i] = (close[i] - l) / (h - l + 1e-10)
        features[f"price_position_{window}"] = pos

    # Moving average crossover
    ma_fast = np.full(n, np.nan)
    ma_slow = np.full(n, np.nan)
    for i in range(10, n):
        ma_fast[i] = np.mean(close[i - 10:i])
    for i in range(30, n):
        ma_slow[i] = np.mean(close[i - 30:i])
    features["ma_cross"] = (ma_fast - ma_slow) / (ma_slow + 1e-10)

    # High-low range normalized
    features["hl_range"] = (high - low) / (close + 1e-10)

    return pd.DataFrame(features, index=df.index)


# ── Label Creation ──────────────────────────────────────────────────
def create_labels(
    prices: np.ndarray,
    horizon: int = FORWARD_HORIZON,
    threshold: float = RETURN_THRESHOLD,
) -> tuple[np.ndarray, np.ndarray]:
    """Create binary labels and forward returns from price series.

    Args:
        prices: Array of close prices.
        horizon: Forward return horizon in bars.
        threshold: Minimum return magnitude for a label.

    Returns:
        Tuple of (labels, forward_returns). Labels are 1/0/NaN.
    """
    n = len(prices)
    fwd_returns = np.full(n, np.nan)
    for i in range(n - horizon):
        fwd_returns[i] = prices[i + horizon] / prices[i] - 1.0

    labels = np.full(n, np.nan)
    labels[fwd_returns > threshold] = 1.0
    labels[fwd_returns < -threshold] = 0.0

    return labels, fwd_returns


# ── Walk-Forward Splits ─────────────────────────────────────────────
def walk_forward_splits(
    n_samples: int,
    train_size: int = TRAIN_SIZE,
    test_size: int = TEST_SIZE,
    step_size: int = STEP_SIZE,
    gap: int = GAP_SIZE,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test index splits.

    Args:
        n_samples: Total number of time-ordered samples.
        train_size: Training window length.
        test_size: Test window length.
        step_size: Step between windows.
        gap: Embargo gap between train and test.

    Yields:
        Tuples of (train_indices, test_indices).
    """
    start = 0
    while start + train_size + gap + test_size <= n_samples:
        train_end = start + train_size
        test_start = train_end + gap
        test_end = test_start + test_size
        yield np.arange(start, train_end), np.arange(test_start, test_end)
        start += step_size


# ── ML Signal Generation ───────────────────────────────────────────
def generate_ml_signals(
    X: pd.DataFrame,
    y: np.ndarray,
    threshold: float = 0.55,
) -> np.ndarray:
    """Generate out-of-sample ML signals via walk-forward.

    Args:
        X: Feature matrix.
        y: Binary labels (1/0/NaN).
        threshold: Probability threshold for generating a signal.

    Returns:
        Array of signals: 1 (long), 0 (no position), for each bar.
        Only out-of-sample bars get signals; others are 0.
    """
    n = len(X)
    signals = np.zeros(n)
    valid_mask = ~np.isnan(y)

    fold_count = 0
    oos_count = 0
    total_auc = 0.0

    for train_idx, test_idx in walk_forward_splits(n):
        train_valid = train_idx[valid_mask[train_idx]]
        test_valid = test_idx[valid_mask[test_idx]]

        if len(train_valid) < 20 or len(test_valid) < 3:
            continue

        fold_count += 1

        X_train = X.iloc[train_valid].values
        y_train = y[train_valid]
        X_test = X.iloc[test_valid].values
        y_test = y[test_valid]

        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)

        probs = model.predict_proba(X_test)[:, 1]

        try:
            auc = roc_auc_score(y_test, probs)
            total_auc += auc
        except ValueError:
            pass

        # Generate signals for test bars where probability > threshold
        for i, idx in enumerate(test_valid):
            if probs[i] >= threshold:
                signals[idx] = 1.0

        oos_count += len(test_valid)

    avg_auc = total_auc / fold_count if fold_count > 0 else 0.5
    print(f"  Walk-forward: {fold_count} folds, {oos_count} OOS samples, "
          f"avg AUC: {avg_auc:.3f}")

    return signals


# ── Trading Simulation ──────────────────────────────────────────────
def simulate_strategy(
    prices: np.ndarray,
    signals: np.ndarray,
    cost: float = TRANSACTION_COST,
) -> dict:
    """Simulate a long-only strategy based on signals.

    When signal=1, enter long at next bar's open and hold for
    FORWARD_HORIZON bars. Track returns net of transaction costs.

    Args:
        prices: Array of close prices.
        signals: Array of 0/1 signals.
        cost: Round-trip transaction cost.

    Returns:
        Dictionary with performance metrics.
    """
    n = len(prices)
    trade_returns: list[float] = []
    equity_curve = np.ones(n)
    in_position = False
    entry_price = 0.0
    entry_bar = 0
    n_trades = 0

    for i in range(1, n):
        if in_position:
            # Check if holding period expired
            if i - entry_bar >= FORWARD_HORIZON:
                exit_return = prices[i] / entry_price - 1.0 - cost
                trade_returns.append(exit_return)
                in_position = False
                n_trades += 1
                equity_curve[i] = equity_curve[i - 1] * (1 + exit_return)
            else:
                equity_curve[i] = equity_curve[i - 1]
        else:
            # Check for entry signal (use previous bar's signal)
            if i > 0 and signals[i - 1] == 1:
                entry_price = prices[i]
                entry_bar = i
                in_position = True
            equity_curve[i] = equity_curve[i - 1]

    trade_returns_arr = np.array(trade_returns) if trade_returns else np.array([0.0])

    # Metrics
    total_return = float(equity_curve[-1] / equity_curve[0] - 1)
    n_winning = int(np.sum(trade_returns_arr > 0))
    n_losing = int(np.sum(trade_returns_arr <= 0))
    win_rate = n_winning / max(len(trade_returns_arr), 1)

    gross_profit = float(trade_returns_arr[trade_returns_arr > 0].sum())
    gross_loss = float(abs(trade_returns_arr[trade_returns_arr <= 0].sum()))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_return = float(np.mean(trade_returns_arr))
    avg_win = float(np.mean(trade_returns_arr[trade_returns_arr > 0])) if n_winning > 0 else 0.0
    avg_loss = float(np.mean(trade_returns_arr[trade_returns_arr <= 0])) if n_losing > 0 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peak) / peak
    max_drawdown = float(np.min(drawdowns))

    # Sharpe ratio (annualized, assume hourly bars)
    if len(trade_returns_arr) > 1 and np.std(trade_returns_arr) > 0:
        sharpe = float(np.mean(trade_returns_arr) / np.std(trade_returns_arr)
                       * np.sqrt(252 * 24 / FORWARD_HORIZON))
    else:
        sharpe = 0.0

    return {
        "total_return": total_return,
        "n_trades": len(trade_returns_arr),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "avg_return": avg_return,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "equity_curve": equity_curve,
    }


def simulate_buy_and_hold(prices: np.ndarray) -> dict:
    """Simulate buy-and-hold for comparison.

    Args:
        prices: Array of close prices.

    Returns:
        Dictionary with performance metrics.
    """
    total_return = float(prices[-1] / prices[0] - 1)
    equity_curve = prices / prices[0]

    # Daily returns for Sharpe
    returns = np.diff(prices) / prices[:-1]
    sharpe = 0.0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252 * 24))

    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peak) / peak
    max_drawdown = float(np.min(drawdowns))

    return {
        "total_return": total_return,
        "n_trades": 1,
        "win_rate": 1.0 if total_return > 0 else 0.0,
        "profit_factor": float("inf") if total_return > 0 else 0.0,
        "avg_return": total_return,
        "avg_win": total_return if total_return > 0 else 0.0,
        "avg_loss": total_return if total_return <= 0 else 0.0,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "equity_curve": equity_curve,
    }


def generate_random_signals(
    n: int, signal_rate: float = 0.1, seed: int = 99,
) -> np.ndarray:
    """Generate random signals for baseline comparison.

    Args:
        n: Number of bars.
        signal_rate: Fraction of bars with a signal.
        seed: Random seed.

    Returns:
        Array of 0/1 random signals.
    """
    rng = np.random.default_rng(seed)
    return (rng.random(n) < signal_rate).astype(float)


# ── Reporting ───────────────────────────────────────────────────────
def print_comparison(
    ml_result: dict,
    bh_result: dict,
    random_result: dict,
    ml_threshold: float,
) -> None:
    """Print performance comparison table.

    Args:
        ml_result: ML strategy performance.
        bh_result: Buy-and-hold performance.
        random_result: Random signal performance.
        ml_threshold: ML probability threshold used.
    """
    print("\n" + "=" * 75)
    print("WALK-FORWARD BACKTEST — STRATEGY COMPARISON")
    print("=" * 75)

    header = (f"{'Metric':<22} {'ML (t='}{ml_threshold:.2f}{')':<15} "
              f"{'Buy & Hold':<15} {'Random':<15}")
    print(f"\n{header}")
    print("-" * 70)

    metrics = [
        ("Total Return", "total_return", "{:.2%}"),
        ("Trades", "n_trades", "{:d}"),
        ("Win Rate", "win_rate", "{:.1%}"),
        ("Profit Factor", "profit_factor", "{:.2f}"),
        ("Avg Return/Trade", "avg_return", "{:.3%}"),
        ("Avg Win", "avg_win", "{:.3%}"),
        ("Avg Loss", "avg_loss", "{:.3%}"),
        ("Max Drawdown", "max_drawdown", "{:.2%}"),
        ("Sharpe Ratio", "sharpe_ratio", "{:.2f}"),
    ]

    for label, key, fmt in metrics:
        ml_val = ml_result[key]
        bh_val = bh_result[key]
        rd_val = random_result[key]

        # Format values
        if key == "n_trades":
            ml_str = fmt.format(int(ml_val))
            bh_str = fmt.format(int(bh_val))
            rd_str = fmt.format(int(rd_val))
        elif key == "profit_factor" and ml_val == float("inf"):
            ml_str = "inf"
            bh_str = "inf" if bh_val == float("inf") else fmt.format(bh_val)
            rd_str = "inf" if rd_val == float("inf") else fmt.format(rd_val)
        else:
            ml_str = fmt.format(ml_val)
            bh_str = fmt.format(bh_val)
            rd_str = fmt.format(rd_val)

        print(f"  {label:<20} {ml_str:<15} {bh_str:<15} {rd_str:<15}")

    # Summary
    print(f"\n{'ASSESSMENT':>40}")
    print("-" * 50)

    if ml_result["total_return"] > bh_result["total_return"]:
        print("  ML strategy outperformed buy-and-hold on total return.")
    else:
        print("  Buy-and-hold outperformed ML strategy on total return.")

    if ml_result["total_return"] > random_result["total_return"]:
        print("  ML strategy outperformed random signals.")
    else:
        print("  WARNING: ML strategy did not beat random signals.")

    if ml_result["max_drawdown"] > bh_result["max_drawdown"]:
        print("  ML strategy had smaller drawdown than buy-and-hold.")
    else:
        print("  Buy-and-hold had smaller drawdown.")

    if ml_result["profit_factor"] > 1.3:
        print(f"  Profit factor {ml_result['profit_factor']:.2f} > 1.3: "
              f"Potentially viable signal.")
    elif ml_result["profit_factor"] > 1.0:
        print(f"  Profit factor {ml_result['profit_factor']:.2f}: "
              f"Marginal — may not survive additional costs.")
    else:
        print(f"  Profit factor {ml_result['profit_factor']:.2f}: "
              f"Not profitable at this threshold.")

    print("\nNote: This analysis uses synthetic data for demonstration.")
    print("Past model performance does not guarantee future results.")
    print("This is for informational and educational purposes only.")
    print("=" * 75)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run the walk-forward backtest pipeline."""
    parser = argparse.ArgumentParser(
        description="Backtest ML signals with walk-forward validation."
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run in demo mode with default settings.",
    )
    parser.add_argument(
        "--bars", type=int, default=DEFAULT_BARS,
        help=f"Number of price bars to generate (default: {DEFAULT_BARS}).",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.55,
        help="ML probability threshold for signals (default: 0.55).",
    )
    parser.add_argument(
        "--signal-strength", type=float, default=0.15,
        help="Embedded signal strength in synthetic data (default: 0.15).",
    )
    args = parser.parse_args()

    print("Walk-Forward Backtest — ML Signals vs Baselines")
    print(f"  Bars: {args.bars}, Threshold: {args.threshold:.2f}")
    print(f"  Signal strength: {args.signal_strength}")
    print(f"  Transaction cost: {TRANSACTION_COST:.1%} round-trip")

    # Step 1: Generate price data
    print("\n[1/6] Generating synthetic price data...")
    ohlcv = generate_price_data(
        n_bars=args.bars,
        signal_strength=args.signal_strength,
    )
    prices = ohlcv["close"].values
    print(f"  {len(prices)} bars, price range: "
          f"${prices.min():.2f} - ${prices.max():.2f}")

    # Step 2: Build features
    print("[2/6] Building features from OHLCV...")
    features = build_features(ohlcv)
    print(f"  {features.shape[1]} features computed")

    # Step 3: Create labels
    print("[3/6] Creating forward-return labels...")
    labels, fwd_returns = create_labels(prices)
    n_valid = int(~np.isnan(labels)).sum()
    n_up = int(np.nansum(labels == 1))
    n_down = int(np.nansum(labels == 0))
    print(f"  Valid labels: {n_valid} (up: {n_up}, down: {n_down})")

    # Drop rows where features or labels are NaN
    valid_mask = ~(features.isna().any(axis=1) | np.isnan(labels))
    valid_indices = np.where(valid_mask)[0]
    print(f"  Usable samples (no NaN): {len(valid_indices)}")

    if len(valid_indices) < TRAIN_SIZE + GAP_SIZE + TEST_SIZE + 50:
        print("ERROR: Not enough valid samples. Increase --bars.")
        sys.exit(1)

    # Step 4: Generate ML signals
    print("[4/6] Running walk-forward ML signal generation...")
    ml_signals = generate_ml_signals(features, labels, threshold=args.threshold)
    n_signals = int(ml_signals.sum())
    print(f"  ML signals generated: {n_signals} "
          f"({n_signals / len(ml_signals) * 100:.1f}% of bars)")

    # Step 5: Simulate strategies
    print("[5/6] Simulating trading strategies...")

    print("  a) ML strategy...")
    ml_result = simulate_strategy(prices, ml_signals)
    print(f"     {ml_result['n_trades']} trades, "
          f"return: {ml_result['total_return']:.2%}")

    print("  b) Buy and hold...")
    bh_result = simulate_buy_and_hold(prices)
    print(f"     return: {bh_result['total_return']:.2%}")

    print("  c) Random signals...")
    random_signals = generate_random_signals(
        len(prices),
        signal_rate=n_signals / len(prices) if n_signals > 0 else 0.1,
    )
    random_result = simulate_strategy(prices, random_signals)
    print(f"     {random_result['n_trades']} trades, "
          f"return: {random_result['total_return']:.2%}")

    # Step 6: Report
    print("[6/6] Generating comparison report...")
    print_comparison(ml_result, bh_result, random_result, args.threshold)


if __name__ == "__main__":
    main()
