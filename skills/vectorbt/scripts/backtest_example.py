#!/usr/bin/env python3
"""Three-strategy backtest comparison using synthetic OHLCV data.

Implements and compares three classic trading strategies:
  1. EMA Crossover (fast=12, slow=26)
  2. RSI Mean Reversion (buy RSI<30, sell RSI>70)
  3. Bollinger Band Breakout (buy above upper, sell below lower)

All backtests use realistic fees (0.3%) and slippage (0.5%) on synthetic
price data with embedded trends and mean-reverting regimes.

Usage:
    python scripts/backtest_example.py

Dependencies:
    uv pip install vectorbt pandas numpy pandas-ta
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

try:
    import pandas_ta as ta  # noqa: F401
except ImportError:
    print("pandas-ta is required. Install with: uv pip install pandas-ta")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────
NUM_BARS: int = 200
INIT_CASH: float = 10_000.0
FEES: float = 0.003        # 0.3% per trade
SLIPPAGE: float = 0.005    # 0.5% slippage
FREQ: str = "1h"
SEED: int = 42


# ── Synthetic Data Generation ──────────────────────────────────────

def generate_synthetic_ohlcv(
    num_bars: int = 200,
    start_price: float = 100.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate realistic synthetic OHLCV data with trends and ranges.

    Creates price data that includes:
    - An uptrend phase (first 30% of bars)
    - A ranging/consolidation phase (middle 40%)
    - A downtrend phase (last 30%)

    Args:
        num_bars: Number of OHLCV bars to generate.
        start_price: Starting close price.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume.
        Index is hourly DatetimeIndex.
    """
    rng = np.random.default_rng(seed)

    # Build returns with regime-dependent drift
    returns = np.zeros(num_bars)
    phase1 = int(num_bars * 0.3)
    phase2 = int(num_bars * 0.7)

    # Uptrend: positive drift
    returns[:phase1] = rng.normal(0.002, 0.015, phase1)
    # Range: near-zero drift, lower vol
    returns[phase1:phase2] = rng.normal(0.0, 0.010, phase2 - phase1)
    # Downtrend: negative drift
    returns[phase2:] = rng.normal(-0.0015, 0.018, num_bars - phase2)

    # Build close prices from cumulative returns
    close = start_price * np.exp(np.cumsum(returns))

    # Derive OHLV from close
    spread = rng.uniform(0.002, 0.012, num_bars)
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_prices = close * (1 + rng.normal(0, 0.003, num_bars))
    # Ensure open is within high/low
    open_prices = np.clip(open_prices, low, high)
    volume = rng.uniform(50_000, 500_000, num_bars) * (1 + np.abs(returns) * 20)

    timestamps = pd.date_range(
        start="2025-01-01", periods=num_bars, freq="1h"
    )

    df = pd.DataFrame(
        {
            "open": open_prices,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=timestamps,
    )
    return df


# ── Strategy Implementations ───────────────────────────────────────

def ema_crossover_signals(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
) -> tuple[pd.Series, pd.Series]:
    """Generate EMA crossover entry/exit signals.

    Enters when fast EMA crosses above slow EMA.
    Exits when fast EMA crosses below slow EMA.

    Args:
        close: Close price series.
        fast_period: Fast EMA window.
        slow_period: Slow EMA window.

    Returns:
        Tuple of (entries, exits) as boolean Series.
    """
    fast_ema = close.ewm(span=fast_period, adjust=False).mean()
    slow_ema = close.ewm(span=slow_period, adjust=False).mean()

    # Cross-above: fast was below, now above
    fast_above = fast_ema > slow_ema
    entries = fast_above & (~fast_above.shift(1, fill_value=False))

    # Cross-below: fast was above, now below
    fast_below = fast_ema < slow_ema
    exits = fast_below & (~fast_below.shift(1, fill_value=False))

    return entries, exits


def rsi_mean_reversion_signals(
    close: pd.Series,
    rsi_period: int = 14,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> tuple[pd.Series, pd.Series]:
    """Generate RSI mean reversion entry/exit signals.

    Enters when RSI crosses below oversold threshold.
    Exits when RSI crosses above overbought threshold.

    Args:
        close: Close price series.
        rsi_period: RSI calculation period.
        oversold: RSI level to trigger entry.
        overbought: RSI level to trigger exit.

    Returns:
        Tuple of (entries, exits) as boolean Series.
    """
    df = pd.DataFrame({"close": close}, index=close.index)
    df.ta.rsi(length=rsi_period, append=True)
    rsi_col = f"RSI_{rsi_period}"
    rsi = df[rsi_col]

    # Enter when RSI crosses below oversold
    below = rsi < oversold
    entries = below & (~below.shift(1, fill_value=False))

    # Exit when RSI crosses above overbought
    above = rsi > overbought
    exits = above & (~above.shift(1, fill_value=False))

    return entries, exits


def bollinger_breakout_signals(
    close: pd.Series,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> tuple[pd.Series, pd.Series]:
    """Generate Bollinger Band breakout entry/exit signals.

    Enters when close crosses above the upper band.
    Exits when close crosses below the lower band.

    Args:
        close: Close price series.
        bb_period: Bollinger Band period.
        bb_std: Number of standard deviations.

    Returns:
        Tuple of (entries, exits) as boolean Series.
    """
    df = pd.DataFrame({"close": close}, index=close.index)
    df.ta.bbands(length=bb_period, std=bb_std, append=True)

    upper_col = f"BBU_{bb_period}_{bb_std}"
    lower_col = f"BBL_{bb_period}_{bb_std}"

    upper = df[upper_col]
    lower = df[lower_col]

    # Enter when price crosses above upper band
    above_upper = close > upper
    entries = above_upper & (~above_upper.shift(1, fill_value=False))

    # Exit when price crosses below lower band
    below_lower = close < lower
    exits = below_lower & (~below_lower.shift(1, fill_value=False))

    return entries, exits


# ── Backtest Runner ─────────────────────────────────────────────────

def run_backtest(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    strategy_name: str,
    init_cash: float = INIT_CASH,
    fees: float = FEES,
    slippage: float = SLIPPAGE,
    freq: str = FREQ,
) -> dict:
    """Run a single backtest and return key metrics.

    Args:
        close: Close price series.
        entries: Boolean entry signals.
        exits: Boolean exit signals.
        strategy_name: Name for display purposes.
        init_cash: Starting capital.
        fees: Fee fraction per trade.
        slippage: Slippage fraction.
        freq: Data frequency string.

    Returns:
        Dictionary with strategy name and performance metrics.
    """
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

    trade_count = pf.trades.count()

    # Handle edge case of zero trades
    if trade_count == 0:
        return {
            "Strategy": strategy_name,
            "Total Return": 0.0,
            "Sharpe Ratio": 0.0,
            "Sortino Ratio": 0.0,
            "Max Drawdown": 0.0,
            "Win Rate": 0.0,
            "Profit Factor": 0.0,
            "Trade Count": 0,
            "Avg Trade PnL": 0.0,
        }

    win_rate = pf.trades.win_rate()
    profit_factor = pf.trades.profit_factor()

    return {
        "Strategy": strategy_name,
        "Total Return": float(pf.total_return()),
        "Sharpe Ratio": float(pf.sharpe_ratio()),
        "Sortino Ratio": float(pf.sortino_ratio()),
        "Max Drawdown": float(pf.max_drawdown()),
        "Win Rate": float(win_rate) if not np.isnan(win_rate) else 0.0,
        "Profit Factor": float(profit_factor) if not np.isnan(profit_factor) else 0.0,
        "Trade Count": int(trade_count),
        "Avg Trade PnL": float(pf.trades.expectancy()),
    }


# ── Display ─────────────────────────────────────────────────────────

def print_comparison_table(results: list[dict]) -> None:
    """Print a formatted comparison table of backtest results.

    Args:
        results: List of result dictionaries from run_backtest().
    """
    print("\n" + "=" * 80)
    print("STRATEGY COMPARISON")
    print("=" * 80)
    print(
        f"{'Strategy':<25} {'Return':>10} {'Sharpe':>8} {'Sortino':>8} "
        f"{'MaxDD':>8} {'WinRate':>8} {'PF':>8} {'Trades':>7}"
    )
    print("-" * 80)

    for r in results:
        print(
            f"{r['Strategy']:<25} "
            f"{r['Total Return']:>9.2%} "
            f"{r['Sharpe Ratio']:>8.3f} "
            f"{r['Sortino Ratio']:>8.3f} "
            f"{r['Max Drawdown']:>7.2%} "
            f"{r['Win Rate']:>7.2%} "
            f"{r['Profit Factor']:>8.2f} "
            f"{r['Trade Count']:>7d}"
        )

    print("-" * 80)

    # Find best strategy by Sharpe ratio
    best = max(results, key=lambda r: r["Sharpe Ratio"])
    print(f"\nBest strategy by Sharpe Ratio: {best['Strategy']}")
    print(f"  Sharpe: {best['Sharpe Ratio']:.3f}")
    print(f"  Return: {best['Total Return']:.2%}")
    print(f"  Max Drawdown: {best['Max Drawdown']:.2%}")
    print(f"  Win Rate: {best['Win Rate']:.2%}")
    print(f"  Trades: {best['Trade Count']}")


def print_data_summary(df: pd.DataFrame) -> None:
    """Print summary statistics of the synthetic data.

    Args:
        df: OHLCV DataFrame.
    """
    print("SYNTHETIC DATA SUMMARY")
    print(f"  Bars: {len(df)}")
    print(f"  Period: {df.index[0]} to {df.index[-1]}")
    print(f"  Start price: {df['close'].iloc[0]:.2f}")
    print(f"  End price: {df['close'].iloc[-1]:.2f}")
    print(f"  High: {df['high'].max():.2f}")
    print(f"  Low: {df['low'].min():.2f}")
    buy_hold = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
    print(f"  Buy & hold return: {buy_hold:.2%}")
    print()
    print("BACKTEST SETTINGS")
    print(f"  Initial cash: ${INIT_CASH:,.0f}")
    print(f"  Fees: {FEES:.1%} per trade")
    print(f"  Slippage: {SLIPPAGE:.1%}")
    print(f"  Position size: 95% of available cash")
    print(f"  Frequency: {FREQ}")


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run three-strategy backtest comparison."""
    # Generate synthetic data
    print("Generating synthetic OHLCV data...\n")
    df = generate_synthetic_ohlcv(num_bars=NUM_BARS, seed=SEED)
    close = df["close"]

    print_data_summary(df)

    # Strategy 1: EMA Crossover
    print("\nRunning EMA Crossover (12/26)...")
    ema_entries, ema_exits = ema_crossover_signals(close, fast_period=12, slow_period=26)
    ema_result = run_backtest(close, ema_entries, ema_exits, "EMA Crossover (12/26)")

    # Strategy 2: RSI Mean Reversion
    print("Running RSI Mean Reversion (14, 30/70)...")
    rsi_entries, rsi_exits = rsi_mean_reversion_signals(close, rsi_period=14)
    rsi_result = run_backtest(close, rsi_entries, rsi_exits, "RSI MeanRev (14, 30/70)")

    # Strategy 3: Bollinger Breakout
    print("Running Bollinger Breakout (20, 2.0)...")
    bb_entries, bb_exits = bollinger_breakout_signals(close, bb_period=20, bb_std=2.0)
    bb_result = run_backtest(close, bb_entries, bb_exits, "BB Breakout (20, 2.0)")

    # Compare results
    results = [ema_result, rsi_result, bb_result]
    print_comparison_table(results)

    print("\nNote: Results are based on synthetic data for demonstration only.")
    print("Past performance does not indicate future results.")


if __name__ == "__main__":
    main()
