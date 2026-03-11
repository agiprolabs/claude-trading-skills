#!/usr/bin/env python3
"""EMA crossover parameter sweep with walk-forward validation.

Demonstrates:
  1. Grid search across fast/slow EMA period combinations
  2. Ranking parameter combos by Sharpe, total return, and profit factor
  3. Walk-forward validation (train on first 70%, test on last 30%)
  4. In-sample vs out-of-sample performance comparison

Uses synthetic OHLCV data — no API keys required.

Usage:
    python scripts/parameter_sweep.py

Dependencies:
    uv pip install vectorbt pandas numpy
"""

import sys
from typing import Optional

import numpy as np
import pandas as pd

try:
    import vectorbt as vbt
except ImportError:
    print("vectorbt is required. Install with: uv pip install vectorbt")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────
NUM_BARS: int = 500
INIT_CASH: float = 10_000.0
FEES: float = 0.003
SLIPPAGE: float = 0.005
FREQ: str = "1h"
SEED: int = 99

FAST_PERIODS: list[int] = [5, 8, 12, 15, 20]
SLOW_PERIODS: list[int] = [20, 26, 30, 40, 50]

TRAIN_FRACTION: float = 0.7


# ── Synthetic Data Generation ──────────────────────────────────────

def generate_synthetic_ohlcv(
    num_bars: int = 500,
    start_price: float = 50.0,
    seed: int = 99,
) -> pd.DataFrame:
    """Generate realistic synthetic OHLCV data with multiple market regimes.

    Creates price data with embedded trends, ranges, and reversals to provide
    a challenging but realistic test environment for strategy optimization.

    Args:
        num_bars: Number of OHLCV bars to generate.
        start_price: Starting close price.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume.
        Index is hourly DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    returns = np.zeros(num_bars)

    # Multiple regime phases
    p1 = int(num_bars * 0.15)
    p2 = int(num_bars * 0.35)
    p3 = int(num_bars * 0.50)
    p4 = int(num_bars * 0.70)
    p5 = int(num_bars * 0.85)

    # Uptrend
    returns[:p1] = rng.normal(0.002, 0.012, p1)
    # Range
    returns[p1:p2] = rng.normal(0.0, 0.008, p2 - p1)
    # Strong uptrend
    returns[p2:p3] = rng.normal(0.003, 0.015, p3 - p2)
    # Downtrend
    returns[p3:p4] = rng.normal(-0.002, 0.014, p4 - p3)
    # Range
    returns[p4:p5] = rng.normal(0.0, 0.009, p5 - p4)
    # Mild uptrend
    returns[p5:] = rng.normal(0.001, 0.011, num_bars - p5)

    close = start_price * np.exp(np.cumsum(returns))
    spread = rng.uniform(0.002, 0.010, num_bars)
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_prices = np.clip(
        close * (1 + rng.normal(0, 0.003, num_bars)), low, high
    )
    volume = rng.uniform(100_000, 800_000, num_bars)

    timestamps = pd.date_range(start="2025-01-01", periods=num_bars, freq="1h")

    return pd.DataFrame(
        {
            "open": open_prices,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=timestamps,
    )


# ── Grid Search ─────────────────────────────────────────────────────

def run_grid_search(
    close: pd.Series,
    fast_periods: list[int],
    slow_periods: list[int],
    init_cash: float = INIT_CASH,
    fees: float = FEES,
    slippage: float = SLIPPAGE,
    freq: str = FREQ,
) -> vbt.Portfolio:
    """Run EMA crossover grid search across all fast/slow period combinations.

    Args:
        close: Close price series.
        fast_periods: List of fast EMA periods to test.
        slow_periods: List of slow EMA periods to test.
        init_cash: Starting capital.
        fees: Fee fraction per trade.
        slippage: Slippage fraction.
        freq: Data frequency string.

    Returns:
        Portfolio object containing all parameter combinations.
    """
    fast_ma = vbt.MA.run(close, fast_periods, short_name="fast")
    slow_ma = vbt.MA.run(close, slow_periods, short_name="slow")

    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        size=0.95,
        size_type="percent",
        freq=freq,
    )
    return pf


def extract_metrics(pf: vbt.Portfolio) -> pd.DataFrame:
    """Extract key metrics from a multi-parameter portfolio.

    Args:
        pf: Portfolio object from grid search.

    Returns:
        DataFrame with one row per parameter combination and columns for
        each metric.
    """
    sharpe = pf.sharpe_ratio()
    total_ret = pf.total_return()
    max_dd = pf.max_drawdown()
    trade_count = pf.trades.count()
    win_rate = pf.trades.win_rate()
    profit_factor = pf.trades.profit_factor()

    df = pd.DataFrame({
        "sharpe": sharpe,
        "total_return": total_ret,
        "max_drawdown": max_dd,
        "trade_count": trade_count,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
    })
    return df


# ── Walk-Forward Validation ─────────────────────────────────────────

def walk_forward_validate(
    close: pd.Series,
    fast_periods: list[int],
    slow_periods: list[int],
    train_fraction: float = TRAIN_FRACTION,
    fees: float = FEES,
    slippage: float = SLIPPAGE,
    freq: str = FREQ,
) -> dict:
    """Run walk-forward validation: optimize on train, validate on test.

    Splits data into training (first train_fraction) and testing (remainder).
    Finds optimal parameters on training data, then evaluates those parameters
    on the unseen test data.

    Args:
        close: Full close price series.
        fast_periods: Fast EMA periods to test.
        slow_periods: Slow EMA periods to test.
        train_fraction: Fraction of data for training.
        fees: Fee fraction.
        slippage: Slippage fraction.
        freq: Data frequency.

    Returns:
        Dictionary with training results, test results, and best parameters.
    """
    split_idx = int(len(close) * train_fraction)
    train_close = close.iloc[:split_idx]
    test_close = close.iloc[split_idx:]

    # ── Train phase: optimize ──
    pf_train = run_grid_search(
        train_close, fast_periods, slow_periods,
        fees=fees, slippage=slippage, freq=freq,
    )
    train_metrics = extract_metrics(pf_train)

    # Filter: require at least 5 trades
    valid = train_metrics["trade_count"] >= 5
    if not valid.any():
        print("WARNING: No parameter combo produced >= 5 trades on training data.")
        valid = train_metrics["trade_count"] >= 1

    valid_sharpe = train_metrics.loc[valid, "sharpe"]
    best_params = valid_sharpe.idxmax()

    # Extract fast and slow from the MultiIndex
    if isinstance(best_params, tuple):
        best_fast, best_slow = best_params
    else:
        best_fast, best_slow = best_params, slow_periods[0]

    train_sharpe = float(valid_sharpe[best_params])
    train_return = float(train_metrics.loc[best_params, "total_return"])
    train_trades = int(train_metrics.loc[best_params, "trade_count"])

    # ── Test phase: validate ──
    fast_ma_test = vbt.MA.run(test_close, int(best_fast), short_name="fast")
    slow_ma_test = vbt.MA.run(test_close, int(best_slow), short_name="slow")
    entries_test = fast_ma_test.ma_crossed_above(slow_ma_test)
    exits_test = fast_ma_test.ma_crossed_below(slow_ma_test)

    pf_test = vbt.Portfolio.from_signals(
        close=test_close,
        entries=entries_test,
        exits=exits_test,
        init_cash=INIT_CASH,
        fees=fees,
        slippage=slippage,
        size=0.95,
        size_type="percent",
        freq=freq,
    )

    test_sharpe = float(pf_test.sharpe_ratio())
    test_return = float(pf_test.total_return())
    test_trades = int(pf_test.trades.count())
    test_max_dd = float(pf_test.max_drawdown())

    return {
        "best_fast": int(best_fast),
        "best_slow": int(best_slow),
        "train_sharpe": train_sharpe,
        "train_return": train_return,
        "train_trades": train_trades,
        "test_sharpe": test_sharpe,
        "test_return": test_return,
        "test_trades": test_trades,
        "test_max_dd": test_max_dd,
        "train_bars": split_idx,
        "test_bars": len(close) - split_idx,
    }


# ── Display Functions ───────────────────────────────────────────────

def print_grid_results(
    metrics: pd.DataFrame,
    top_n: int = 5,
) -> None:
    """Print top parameter combinations by different metrics.

    Args:
        metrics: DataFrame from extract_metrics().
        top_n: Number of top results to show.
    """
    # Filter combos with at least 5 trades
    valid = metrics[metrics["trade_count"] >= 5].copy()
    if valid.empty:
        valid = metrics[metrics["trade_count"] >= 1].copy()

    print("\n" + "=" * 80)
    print("GRID SEARCH RESULTS")
    print(f"Total parameter combinations: {len(metrics)}")
    print(f"Valid combinations (>= 5 trades): {len(valid)}")
    print("=" * 80)

    # Best by Sharpe
    print(f"\n--- Top {top_n} by Sharpe Ratio ---")
    top_sharpe = valid.nlargest(top_n, "sharpe")
    _print_metric_table(top_sharpe)

    # Best by Total Return
    print(f"\n--- Top {top_n} by Total Return ---")
    top_return = valid.nlargest(top_n, "total_return")
    _print_metric_table(top_return)

    # Best by Profit Factor
    pf_valid = valid[valid["profit_factor"].notna() & (valid["profit_factor"] < np.inf)]
    if not pf_valid.empty:
        print(f"\n--- Top {top_n} by Profit Factor ---")
        top_pf = pf_valid.nlargest(top_n, "profit_factor")
        _print_metric_table(top_pf)


def _print_metric_table(df: pd.DataFrame) -> None:
    """Print a formatted table of metrics.

    Args:
        df: DataFrame with metric columns.
    """
    print(
        f"  {'Params':<20} {'Sharpe':>8} {'Return':>10} {'MaxDD':>8} "
        f"{'WinRate':>8} {'PF':>8} {'Trades':>7}"
    )
    print("  " + "-" * 70)
    for idx, row in df.iterrows():
        params_str = str(idx)
        sharpe = row["sharpe"]
        ret = row["total_return"]
        mdd = row["max_drawdown"]
        wr = row["win_rate"]
        pf_val = row["profit_factor"]
        tc = row["trade_count"]

        print(
            f"  {params_str:<20} "
            f"{sharpe:>8.3f} "
            f"{ret:>9.2%} "
            f"{mdd:>7.2%} "
            f"{wr if not np.isnan(wr) else 0:>7.2%} "
            f"{pf_val if not np.isnan(pf_val) else 0:>8.2f} "
            f"{int(tc):>7d}"
        )


def print_walk_forward_results(wf: dict) -> None:
    """Print walk-forward validation results.

    Args:
        wf: Dictionary from walk_forward_validate().
    """
    print("\n" + "=" * 80)
    print("WALK-FORWARD VALIDATION")
    print("=" * 80)
    print(f"\nBest parameters (optimized on training data):")
    print(f"  Fast EMA: {wf['best_fast']}")
    print(f"  Slow EMA: {wf['best_slow']}")
    print()

    print(f"{'Metric':<25} {'In-Sample':>15} {'Out-of-Sample':>15}")
    print("-" * 55)
    print(f"{'Bars':<25} {wf['train_bars']:>15d} {wf['test_bars']:>15d}")
    print(f"{'Sharpe Ratio':<25} {wf['train_sharpe']:>15.3f} {wf['test_sharpe']:>15.3f}")
    print(f"{'Total Return':<25} {wf['train_return']:>14.2%} {wf['test_return']:>14.2%}")
    print(f"{'Trade Count':<25} {wf['train_trades']:>15d} {wf['test_trades']:>15d}")

    if wf["test_max_dd"] > 0:
        print(f"{'Max Drawdown (OOS)':<25} {'':>15s} {wf['test_max_dd']:>14.2%}")

    # Sharpe decay analysis
    if wf["train_sharpe"] > 0:
        decay = 1.0 - (wf["test_sharpe"] / wf["train_sharpe"])
        print(f"\nSharpe decay: {decay:.1%}")
        if decay < 0.3:
            assessment = "Low decay — parameters appear robust"
        elif decay < 0.6:
            assessment = "Moderate decay — use with caution"
        else:
            assessment = "High decay — likely overfit, consider simpler strategy"
        print(f"Assessment: {assessment}")
    elif wf["train_sharpe"] <= 0:
        print("\nIn-sample Sharpe <= 0: strategy may not be viable for this data.")

    print()
    print("Note: This analysis uses synthetic data for demonstration only.")
    print("Real-world performance depends on data quality, market conditions,")
    print("and execution factors not captured in backtesting.")


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run parameter sweep and walk-forward validation."""
    print("Generating synthetic OHLCV data...")
    print(f"  Bars: {NUM_BARS}")
    print(f"  Frequency: {FREQ}")
    print(f"  Fees: {FEES:.1%}")
    print(f"  Slippage: {SLIPPAGE:.1%}")

    df = generate_synthetic_ohlcv(num_bars=NUM_BARS, seed=SEED)
    close = df["close"]

    print(f"  Price range: {close.min():.2f} — {close.max():.2f}")
    buy_hold = (close.iloc[-1] / close.iloc[0]) - 1
    print(f"  Buy & hold return: {buy_hold:.2%}")

    # ── Full-sample grid search ──
    print(f"\nRunning grid search...")
    print(f"  Fast periods: {FAST_PERIODS}")
    print(f"  Slow periods: {SLOW_PERIODS}")
    print(f"  Total combinations: {len(FAST_PERIODS) * len(SLOW_PERIODS)}")

    pf = run_grid_search(close, FAST_PERIODS, SLOW_PERIODS)
    metrics = extract_metrics(pf)
    print_grid_results(metrics, top_n=5)

    # ── Walk-forward validation ──
    print(f"\nRunning walk-forward validation...")
    print(f"  Train/test split: {TRAIN_FRACTION:.0%} / {1 - TRAIN_FRACTION:.0%}")

    wf_results = walk_forward_validate(
        close, FAST_PERIODS, SLOW_PERIODS,
        train_fraction=TRAIN_FRACTION,
    )
    print_walk_forward_results(wf_results)


if __name__ == "__main__":
    main()
