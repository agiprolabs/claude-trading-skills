#!/usr/bin/env python3
"""Walk-forward validation engine with rolling and expanding windows.

Provides a configurable walk-forward splitter that respects time series ordering,
supports purging and embargo, and produces per-fold metrics. Includes a --demo
mode that generates synthetic price data and runs a simple moving-average
crossover strategy through the validator.

Usage:
    python scripts/walk_forward.py --demo
    python scripts/walk_forward.py --help

Dependencies:
    uv pip install numpy pandas

Environment Variables:
    None required (--demo mode uses synthetic data).
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import Iterator, Literal, Optional

import numpy as np
import pandas as pd


# ── Configuration ───────────────────────────────────────────────────

@dataclasses.dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation.

    Attributes:
        train_size: Number of bars in the training window.
        test_size: Number of bars in the test window.
        step_size: Number of bars to advance between folds.
        window_type: 'rolling' (fixed train) or 'expanding' (growing train).
        purge_size: Number of bars to purge from end of training set
            to avoid label leakage.
        embargo_size: Number of bars to skip between train and test
            to avoid autocorrelation leakage.
    """

    train_size: int = 90
    test_size: int = 14
    step_size: int = 14
    window_type: Literal["rolling", "expanding"] = "rolling"
    purge_size: int = 0
    embargo_size: int = 0


@dataclasses.dataclass
class Fold:
    """A single train/test fold.

    Attributes:
        fold_idx: Zero-based fold index.
        train_indices: Array indices for the training set.
        test_indices: Array indices for the test set.
        train_start: Datetime of first training bar (if available).
        train_end: Datetime of last training bar (if available).
        test_start: Datetime of first test bar (if available).
        test_end: Datetime of last test bar (if available).
    """

    fold_idx: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_start: Optional[str] = None
    train_end: Optional[str] = None
    test_start: Optional[str] = None
    test_end: Optional[str] = None


@dataclasses.dataclass
class FoldResult:
    """Performance metrics for a single fold."""

    fold_idx: int
    train_sharpe: float
    test_sharpe: float
    train_return: float
    test_return: float
    test_max_drawdown: float
    test_hit_rate: float
    n_train: int
    n_test: int


# ── Walk-Forward Splitter ───────────────────────────────────────────

class WalkForwardValidator:
    """Walk-forward validation splitter with purging and embargo."""

    def __init__(self, config: WalkForwardConfig) -> None:
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration parameters."""
        if self.config.train_size < 10:
            raise ValueError("train_size must be >= 10")
        if self.config.test_size < 1:
            raise ValueError("test_size must be >= 1")
        if self.config.step_size < 1:
            raise ValueError("step_size must be >= 1")
        if self.config.purge_size < 0:
            raise ValueError("purge_size must be >= 0")
        if self.config.embargo_size < 0:
            raise ValueError("embargo_size must be >= 0")
        if self.config.window_type not in ("rolling", "expanding"):
            raise ValueError("window_type must be 'rolling' or 'expanding'")

    def split(
        self,
        n_samples: int,
        dates: Optional[pd.DatetimeIndex] = None,
    ) -> Iterator[Fold]:
        """Generate walk-forward train/test splits.

        Args:
            n_samples: Total number of observations.
            dates: Optional datetime index for labelling folds.

        Yields:
            Fold objects with train and test indices.
        """
        cfg = self.config
        min_required = cfg.train_size + cfg.purge_size + cfg.embargo_size + cfg.test_size
        if n_samples < min_required:
            raise ValueError(
                f"Need at least {min_required} samples, got {n_samples}"
            )

        fold_idx = 0
        offset = 0

        while True:
            if cfg.window_type == "rolling":
                train_start = offset
                train_end = offset + cfg.train_size
            else:  # expanding
                train_start = 0
                train_end = cfg.train_size + offset

            # Apply purge: remove purge_size bars from end of training
            effective_train_end = train_end - cfg.purge_size

            # Apply embargo: skip embargo_size bars after effective train end
            test_start = train_end + cfg.embargo_size
            test_end = test_start + cfg.test_size

            if test_end > n_samples:
                break

            train_indices = np.arange(train_start, effective_train_end)
            test_indices = np.arange(test_start, test_end)

            fold = Fold(
                fold_idx=fold_idx,
                train_indices=train_indices,
                test_indices=test_indices,
            )

            if dates is not None:
                fold.train_start = str(dates[train_start])
                fold.train_end = str(dates[effective_train_end - 1])
                fold.test_start = str(dates[test_start])
                fold.test_end = str(dates[test_end - 1])

            yield fold
            fold_idx += 1
            offset += cfg.step_size

    def count_folds(self, n_samples: int) -> int:
        """Return the number of folds without generating them."""
        return sum(1 for _ in self.split(n_samples))


# ── Metrics ─────────────────────────────────────────────────────────

def compute_sharpe(returns: np.ndarray, annualization: float = 365.0) -> float:
    """Compute annualized Sharpe ratio from a returns array.

    Args:
        returns: Array of periodic returns.
        annualization: Periods per year (365 for daily crypto).

    Returns:
        Annualized Sharpe ratio, or 0.0 if std is zero.
    """
    if len(returns) < 2 or np.std(returns) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns) * np.sqrt(annualization))


def compute_max_drawdown(returns: np.ndarray) -> float:
    """Compute maximum drawdown from a returns array.

    Args:
        returns: Array of periodic returns.

    Returns:
        Maximum drawdown as a negative float (e.g., -0.15 = -15%).
    """
    cumulative = np.cumprod(1.0 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = cumulative / running_max - 1.0
    return float(np.min(drawdowns))


def compute_hit_rate(predictions: np.ndarray, actuals: np.ndarray) -> float:
    """Compute directional hit rate.

    Args:
        predictions: Predicted direction signals (positive = long).
        actuals: Actual returns.

    Returns:
        Fraction of correct directional predictions.
    """
    if len(predictions) == 0:
        return 0.0
    correct = np.sign(predictions) == np.sign(actuals)
    return float(np.mean(correct))


# ── Demo Strategy ───────────────────────────────────────────────────

def generate_synthetic_prices(
    n_bars: int = 500,
    seed: int = 42,
    base_price: float = 100.0,
    annual_return: float = 0.10,
    annual_vol: float = 0.80,
) -> pd.DataFrame:
    """Generate synthetic daily price data with realistic crypto volatility.

    Args:
        n_bars: Number of daily bars to generate.
        seed: Random seed for reproducibility.
        base_price: Starting price.
        annual_return: Annualized drift.
        annual_vol: Annualized volatility.

    Returns:
        DataFrame with 'date', 'close', and 'returns' columns.
    """
    rng = np.random.default_rng(seed)
    daily_return = annual_return / 365
    daily_vol = annual_vol / np.sqrt(365)

    # Add regime switching for realism
    regime_length = n_bars // 4
    returns = np.empty(n_bars)
    for i in range(4):
        start = i * regime_length
        end = (i + 1) * regime_length if i < 3 else n_bars
        regime_vol = daily_vol * rng.uniform(0.5, 2.0)
        regime_drift = daily_return * rng.uniform(-2.0, 3.0)
        segment = rng.normal(regime_drift, regime_vol, end - start)
        returns[start:end] = segment

    prices = base_price * np.cumprod(1.0 + returns)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="D")

    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "returns": returns,
    })


def sma_crossover_signals(
    prices: np.ndarray,
    fast_period: int = 10,
    slow_period: int = 30,
) -> np.ndarray:
    """Generate signals from SMA crossover: +1 (long) or -1 (flat/short).

    Args:
        prices: Array of closing prices.
        fast_period: Fast SMA lookback.
        slow_period: Slow SMA lookback.

    Returns:
        Array of signals (+1 or -1), NaN for warmup period.
    """
    signals = np.full(len(prices), np.nan)
    for i in range(slow_period, len(prices)):
        fast_sma = np.mean(prices[i - fast_period : i])
        slow_sma = np.mean(prices[i - slow_period : i])
        signals[i] = 1.0 if fast_sma > slow_sma else -1.0
    return signals


def run_walk_forward(
    config: WalkForwardConfig,
    df: pd.DataFrame,
    fast_period: int = 10,
    slow_period: int = 30,
) -> list[FoldResult]:
    """Run walk-forward validation on a SMA crossover strategy.

    Args:
        config: Walk-forward configuration.
        df: DataFrame with 'close' and 'returns' columns.
        fast_period: Fast SMA period.
        slow_period: Slow SMA period.

    Returns:
        List of FoldResult for each fold.
    """
    validator = WalkForwardValidator(config)
    prices = df["close"].values
    returns = df["returns"].values
    dates = pd.DatetimeIndex(df["date"])
    results: list[FoldResult] = []

    for fold in validator.split(len(prices), dates):
        # Train: compute signals on training data
        train_prices = prices[fold.train_indices]
        train_returns = returns[fold.train_indices]
        train_signals = sma_crossover_signals(train_prices, fast_period, slow_period)

        # Only use valid (non-NaN) signals
        valid_train = ~np.isnan(train_signals)
        train_strat_returns = train_signals[valid_train] * train_returns[valid_train]

        # Test: compute signals and returns on test data
        # We need lookback prices before test period for SMA computation
        lookback_start = max(0, fold.test_indices[0] - slow_period)
        extended_prices = prices[lookback_start : fold.test_indices[-1] + 1]
        extended_signals = sma_crossover_signals(extended_prices, fast_period, slow_period)

        # Extract only the test portion of signals
        test_offset = fold.test_indices[0] - lookback_start
        test_signals = extended_signals[test_offset:]
        test_returns = returns[fold.test_indices]

        valid_test = ~np.isnan(test_signals)
        if not np.any(valid_test):
            continue

        test_strat_returns = test_signals[valid_test] * test_returns[valid_test]

        result = FoldResult(
            fold_idx=fold.fold_idx,
            train_sharpe=compute_sharpe(train_strat_returns),
            test_sharpe=compute_sharpe(test_strat_returns),
            train_return=float(np.sum(train_strat_returns)),
            test_return=float(np.sum(test_strat_returns)),
            test_max_drawdown=compute_max_drawdown(test_strat_returns),
            test_hit_rate=compute_hit_rate(test_signals[valid_test], test_returns[valid_test]),
            n_train=int(np.sum(valid_train)),
            n_test=int(np.sum(valid_test)),
        )
        results.append(result)

    return results


# ── Display ─────────────────────────────────────────────────────────

def print_results(results: list[FoldResult], config: WalkForwardConfig) -> None:
    """Print walk-forward validation results.

    Args:
        results: List of per-fold results.
        config: The walk-forward configuration used.
    """
    print("=" * 72)
    print("Walk-Forward Validation Report")
    print("=" * 72)
    print(f"  Window type:      {config.window_type}")
    print(f"  Train size:       {config.train_size} bars")
    print(f"  Test size:        {config.test_size} bars")
    print(f"  Step size:        {config.step_size} bars")
    print(f"  Purge:            {config.purge_size} bars")
    print(f"  Embargo:          {config.embargo_size} bars")
    print(f"  Folds:            {len(results)}")
    print()

    # Per-fold table
    print(f"{'Fold':>4} {'Train SR':>10} {'Test SR':>10} {'Test Ret':>10} "
          f"{'Test MDD':>10} {'Hit Rate':>10}")
    print("-" * 60)
    for r in results:
        print(
            f"{r.fold_idx:>4} "
            f"{r.train_sharpe:>10.2f} "
            f"{r.test_sharpe:>10.2f} "
            f"{r.test_return:>9.2%} "
            f"{r.test_max_drawdown:>9.2%} "
            f"{r.test_hit_rate:>9.1%}"
        )

    # Aggregate
    print()
    train_sharpes = [r.train_sharpe for r in results]
    test_sharpes = [r.test_sharpe for r in results]
    test_returns = [r.test_return for r in results]

    mean_train_sr = np.mean(train_sharpes)
    mean_test_sr = np.mean(test_sharpes)
    std_test_sr = np.std(test_sharpes)
    sr_ratio = mean_train_sr / mean_test_sr if mean_test_sr != 0 else float("inf")

    print("Aggregate Metrics:")
    print(f"  Mean Train Sharpe:   {mean_train_sr:.3f}")
    print(f"  Mean Test Sharpe:    {mean_test_sr:.3f}")
    print(f"  Test Sharpe StdDev:  {std_test_sr:.3f}")
    print(f"  Train/Test SR Ratio: {sr_ratio:.2f}")
    print(f"  Mean Test Return:    {np.mean(test_returns):.2%}")
    print(f"  Total Test Return:   {np.sum(test_returns):.2%}")
    print()

    # Overfit warning
    if sr_ratio > 2.0:
        print("  WARNING: Train/Test SR ratio > 2.0 suggests overfitting.")
    elif sr_ratio > 1.5:
        print("  CAUTION: Train/Test SR ratio > 1.5, moderate overfit risk.")
    else:
        print("  Train/Test SR ratio looks reasonable.")

    print()


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for walk-forward validation."""
    parser = argparse.ArgumentParser(
        description="Walk-forward validation engine for trading strategies."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo with synthetic price data and SMA crossover strategy.",
    )
    parser.add_argument("--train-size", type=int, default=90, help="Training window size (bars).")
    parser.add_argument("--test-size", type=int, default=14, help="Test window size (bars).")
    parser.add_argument("--step-size", type=int, default=14, help="Step size between folds (bars).")
    parser.add_argument(
        "--window-type",
        choices=["rolling", "expanding"],
        default="rolling",
        help="Window type: rolling or expanding.",
    )
    parser.add_argument("--purge", type=int, default=1, help="Purge size (bars).")
    parser.add_argument("--embargo", type=int, default=3, help="Embargo size (bars).")
    parser.add_argument("--n-bars", type=int, default=500, help="Number of synthetic bars (demo).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (demo).")

    args = parser.parse_args()

    if not args.demo:
        print("Run with --demo to see walk-forward validation on synthetic data.")
        print("Example: python scripts/walk_forward.py --demo")
        print()
        print("Or use WalkForwardValidator programmatically:")
        print("  from walk_forward import WalkForwardValidator, WalkForwardConfig")
        sys.exit(0)

    print("Generating synthetic price data...")
    df = generate_synthetic_prices(n_bars=args.n_bars, seed=args.seed)
    print(f"  {len(df)} daily bars from {df['date'].iloc[0].date()} to {df['date'].iloc[-1].date()}")
    print(f"  Price range: {df['close'].min():.2f} – {df['close'].max():.2f}")
    print()

    # Run with rolling window
    config_rolling = WalkForwardConfig(
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
        window_type="rolling",
        purge_size=args.purge,
        embargo_size=args.embargo,
    )

    print("Running rolling-window walk-forward validation...")
    print()
    results_rolling = run_walk_forward(config_rolling, df)
    print_results(results_rolling, config_rolling)

    # Run with expanding window
    config_expanding = WalkForwardConfig(
        train_size=args.train_size,
        test_size=args.test_size,
        step_size=args.step_size,
        window_type="expanding",
        purge_size=args.purge,
        embargo_size=args.embargo,
    )

    print("Running expanding-window walk-forward validation...")
    print()
    results_expanding = run_walk_forward(config_expanding, df)
    print_results(results_expanding, config_expanding)

    # Compare
    print("=" * 72)
    print("Comparison: Rolling vs Expanding")
    print("=" * 72)
    rolling_sr = np.mean([r.test_sharpe for r in results_rolling])
    expanding_sr = np.mean([r.test_sharpe for r in results_expanding])
    print(f"  Rolling  Mean OOS Sharpe: {rolling_sr:.3f}")
    print(f"  Expanding Mean OOS Sharpe: {expanding_sr:.3f}")
    print()
    if abs(rolling_sr - expanding_sr) < 0.3:
        print("  Results are consistent across window types — good sign.")
    else:
        print("  Divergence between window types — investigate regime sensitivity.")
    print()


if __name__ == "__main__":
    main()
