#!/usr/bin/env python3
"""Compute common TA-Lib technical indicators on synthetic OHLCV data.

Demonstrates RSI, MACD, Bollinger Bands, ATR, and ADX using TA-Lib when
available, with manual fallback implementations for environments without
the C library installed. Includes a performance comparison between
TA-Lib and manual computation.

Usage:
    python scripts/compute_indicators.py
    python scripts/compute_indicators.py --demo
    python scripts/compute_indicators.py --bars 5000

Dependencies:
    uv pip install numpy pandas
    Optional: uv pip install TA-Lib  (requires C library)
"""

import argparse
import sys
import time
from typing import Optional, Tuple

import numpy as np
import pandas as pd

# ── TA-Lib Import (optional) ───────────────────────────────────────
TALIB_AVAILABLE = False
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    pass


# ── Synthetic Data Generation ──────────────────────────────────────

def generate_ohlcv(
    bars: int = 500,
    start_price: float = 100.0,
    volatility: float = 0.02,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic price dynamics.

    Uses geometric Brownian motion for close prices with random
    high/low/open offsets and volume proportional to price changes.

    Args:
        bars: Number of bars to generate.
        start_price: Starting price.
        volatility: Per-bar return standard deviation.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)

    # Geometric Brownian motion for close prices
    returns = rng.normal(0, volatility, bars)
    close = start_price * np.exp(np.cumsum(returns))

    # Generate OHLV around close
    spread = close * volatility
    high = close + np.abs(rng.normal(0, 1, bars)) * spread
    low = close - np.abs(rng.normal(0, 1, bars)) * spread
    open_ = close + rng.normal(0, 0.5, bars) * spread

    # Ensure high >= max(open, close) and low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    # Volume correlated with absolute returns
    base_volume = 100_000
    volume = base_volume * (1 + 5 * np.abs(returns))
    volume = volume.astype(np.float64)

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


# ── Manual Indicator Implementations (Fallback) ───────────────────

def manual_sma(data: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average using cumulative sum trick.

    Args:
        data: Input price array.
        period: Lookback window.

    Returns:
        Array with SMA values (NaN for first period-1 bars).
    """
    result = np.full_like(data, np.nan)
    if len(data) < period:
        return result
    cumsum = np.cumsum(data)
    cumsum[period:] = cumsum[period:] - cumsum[:-period]
    result[period - 1:] = cumsum[period - 1:] / period
    return result


def manual_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average.

    Args:
        data: Input price array.
        period: Lookback period (determines alpha = 2/(period+1)).

    Returns:
        Array with EMA values (NaN for first period-1 bars).
    """
    result = np.full_like(data, np.nan, dtype=np.float64)
    if len(data) < period:
        return result
    alpha = 2.0 / (period + 1)
    # Seed with SMA of first `period` values
    result[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def manual_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index using Wilder's smoothing.

    Args:
        close: Close price array.
        period: RSI lookback period.

    Returns:
        Array with RSI values 0-100 (NaN for first period bars).
    """
    result = np.full_like(close, np.nan, dtype=np.float64)
    if len(close) < period + 1:
        return result

    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Initial average gain/loss
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder's smoothing
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return result


def manual_macd(
    close: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD: difference of two EMAs plus signal line.

    Args:
        close: Close price array.
        fast: Fast EMA period.
        slow: Slow EMA period.
        signal_period: Signal line EMA period.

    Returns:
        Tuple of (macd_line, signal_line, histogram).
    """
    ema_fast = manual_ema(close, fast)
    ema_slow = manual_ema(close, slow)
    macd_line = ema_fast - ema_slow

    # Signal line: EMA of MACD line (only where MACD is valid)
    valid_start = slow - 1
    signal_line = np.full_like(close, np.nan, dtype=np.float64)
    macd_valid = macd_line[valid_start:]
    if len(macd_valid) >= signal_period:
        sig = manual_ema(macd_valid, signal_period)
        signal_line[valid_start:] = sig

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def manual_bbands(
    close: np.ndarray,
    period: int = 20,
    nbdev: float = 2.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: SMA +/- N standard deviations.

    Args:
        close: Close price array.
        period: Moving average period.
        nbdev: Number of standard deviations.

    Returns:
        Tuple of (upper, middle, lower) band arrays.
    """
    middle = manual_sma(close, period)
    upper = np.full_like(close, np.nan, dtype=np.float64)
    lower = np.full_like(close, np.nan, dtype=np.float64)

    for i in range(period - 1, len(close)):
        std = np.std(close[i - period + 1: i + 1], ddof=0)
        upper[i] = middle[i] + nbdev * std
        lower[i] = middle[i] - nbdev * std

    return upper, middle, lower


def manual_true_range(
    high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> np.ndarray:
    """True Range: max(H-L, |H-prevC|, |L-prevC|).

    Args:
        high: High price array.
        low: Low price array.
        close: Close price array.

    Returns:
        True range array (NaN for first bar).
    """
    tr = np.full_like(close, np.nan, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)
    return tr


def manual_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Average True Range using Wilder's smoothing.

    Args:
        high: High price array.
        low: Low price array.
        close: Close price array.
        period: ATR lookback period.

    Returns:
        ATR array (NaN for first period bars).
    """
    tr = manual_true_range(high, low, close)
    atr = np.full_like(close, np.nan, dtype=np.float64)
    if len(close) < period + 1:
        return atr

    atr[period] = np.mean(tr[1: period + 1])
    for i in range(period + 1, len(close)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def manual_adx(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Average Directional Index.

    Computes +DM, -DM, smoothed +DI, -DI, DX, then ADX.

    Args:
        high: High price array.
        low: Low price array.
        close: Close price array.
        period: ADX lookback period.

    Returns:
        ADX array (NaN for initial lookback bars).
    """
    n = len(close)
    adx_out = np.full(n, np.nan, dtype=np.float64)
    if n < 2 * period + 1:
        return adx_out

    # Directional movement
    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)
    tr = manual_true_range(high, low, close)

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    # Wilder's smoothing for TR, +DM, -DM
    smooth_tr = np.sum(tr[1: period + 1])
    smooth_plus = np.sum(plus_dm[1: period + 1])
    smooth_minus = np.sum(minus_dm[1: period + 1])

    dx_values = []
    for i in range(period, n):
        if i > period:
            smooth_tr = smooth_tr - smooth_tr / period + tr[i]
            smooth_plus = smooth_plus - smooth_plus / period + plus_dm[i]
            smooth_minus = smooth_minus - smooth_minus / period + minus_dm[i]

        if smooth_tr == 0:
            dx_values.append(0.0)
            continue

        plus_di = 100.0 * smooth_plus / smooth_tr
        minus_di = 100.0 * smooth_minus / smooth_tr
        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_values.append(0.0)
        else:
            dx = 100.0 * abs(plus_di - minus_di) / di_sum
            dx_values.append(dx)

    # ADX is smoothed DX
    if len(dx_values) >= period:
        adx_val = np.mean(dx_values[:period])
        adx_out[2 * period - 1] = adx_val
        for i in range(period, len(dx_values)):
            adx_val = (adx_val * (period - 1) + dx_values[i]) / period
            adx_out[period + i] = adx_val

    return adx_out


# ── Computation Engine ─────────────────────────────────────────────

def compute_with_talib(df: pd.DataFrame) -> pd.DataFrame:
    """Compute indicators using TA-Lib.

    Args:
        df: OHLCV DataFrame with float64 columns.

    Returns:
        DataFrame with indicator columns added.
    """
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    volume = df["volume"].values.astype(np.float64)

    result = df.copy()
    result["RSI_14"] = talib.RSI(close, timeperiod=14)
    macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    result["MACD"] = macd
    result["MACD_signal"] = signal
    result["MACD_hist"] = hist
    upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
    result["BB_upper"] = upper
    result["BB_middle"] = middle
    result["BB_lower"] = lower
    result["ATR_14"] = talib.ATR(high, low, close, timeperiod=14)
    result["ADX_14"] = talib.ADX(high, low, close, timeperiod=14)
    return result


def compute_manual(df: pd.DataFrame) -> pd.DataFrame:
    """Compute indicators using manual fallback implementations.

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with indicator columns added.
    """
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)

    result = df.copy()
    result["RSI_14"] = manual_rsi(close, 14)
    macd, signal, hist = manual_macd(close, 12, 26, 9)
    result["MACD"] = macd
    result["MACD_signal"] = signal
    result["MACD_hist"] = hist
    upper, middle, lower = manual_bbands(close, 20, 2.0)
    result["BB_upper"] = upper
    result["BB_middle"] = middle
    result["BB_lower"] = lower
    result["ATR_14"] = manual_atr(high, low, close, 14)
    result["ADX_14"] = manual_adx(high, low, close, 14)
    return result


# ── Performance Benchmark ─────────────────────────────────────────

def benchmark(df: pd.DataFrame, iterations: int = 50) -> None:
    """Compare TA-Lib vs manual computation speed.

    Args:
        df: OHLCV DataFrame for benchmarking.
        iterations: Number of iterations for timing.
    """
    print(f"\n{'='*60}")
    print(f"Performance Benchmark ({len(df)} bars, {iterations} iterations)")
    print(f"{'='*60}")

    # Manual timing
    start = time.perf_counter()
    for _ in range(iterations):
        compute_manual(df)
    manual_time = time.perf_counter() - start
    print(f"Manual fallback: {manual_time:.3f}s total, "
          f"{manual_time/iterations*1000:.1f}ms per call")

    if TALIB_AVAILABLE:
        start = time.perf_counter()
        for _ in range(iterations):
            compute_with_talib(df)
        talib_time = time.perf_counter() - start
        print(f"TA-Lib (C):      {talib_time:.3f}s total, "
              f"{talib_time/iterations*1000:.1f}ms per call")
        speedup = manual_time / talib_time if talib_time > 0 else float("inf")
        print(f"Speedup:         {speedup:.1f}x faster with TA-Lib")
    else:
        print("TA-Lib not installed — skipping C library benchmark.")


# ── Display Functions ──────────────────────────────────────────────

def display_results(df: pd.DataFrame, label: str, tail_n: int = 10) -> None:
    """Print the last N rows of computed indicators.

    Args:
        df: DataFrame with indicator columns.
        label: Label for the output section.
        tail_n: Number of recent bars to display.
    """
    cols = ["close", "RSI_14", "MACD", "MACD_signal", "MACD_hist",
            "BB_upper", "BB_middle", "BB_lower", "ATR_14", "ADX_14"]
    available = [c for c in cols if c in df.columns]

    print(f"\n{'='*60}")
    print(f"Indicator Values — {label} (last {tail_n} bars)")
    print(f"{'='*60}")
    print(df[available].tail(tail_n).to_string(float_format="{:.4f}".format))

    # Summary statistics
    print(f"\n--- Summary ---")
    last = df.iloc[-1]
    if "RSI_14" in df.columns and not np.isnan(last["RSI_14"]):
        rsi_val = last["RSI_14"]
        zone = "OVERSOLD" if rsi_val < 30 else ("OVERBOUGHT" if rsi_val > 70 else "NEUTRAL")
        print(f"RSI(14):  {rsi_val:.2f} [{zone}]")
    if "MACD_hist" in df.columns and not np.isnan(last["MACD_hist"]):
        hist_val = last["MACD_hist"]
        trend = "BULLISH" if hist_val > 0 else "BEARISH"
        print(f"MACD Hist: {hist_val:.4f} [{trend}]")
    if "ATR_14" in df.columns and not np.isnan(last["ATR_14"]):
        atr_pct = last["ATR_14"] / last["close"] * 100
        print(f"ATR(14):  {last['ATR_14']:.4f} ({atr_pct:.2f}% of price)")
    if "ADX_14" in df.columns and not np.isnan(last["ADX_14"]):
        adx_val = last["ADX_14"]
        strength = "STRONG TREND" if adx_val > 25 else "RANGING/WEAK"
        print(f"ADX(14):  {adx_val:.2f} [{strength}]")
    if "BB_upper" in df.columns and not np.isnan(last["BB_upper"]):
        bb_pos = (last["close"] - last["BB_lower"]) / (last["BB_upper"] - last["BB_lower"])
        print(f"BB %B:    {bb_pos:.2f} (0=lower band, 1=upper band)")


def compare_results(talib_df: pd.DataFrame, manual_df: pd.DataFrame) -> None:
    """Compare TA-Lib and manual results to validate accuracy.

    Args:
        talib_df: DataFrame computed with TA-Lib.
        manual_df: DataFrame computed with manual fallback.
    """
    print(f"\n{'='*60}")
    print("Accuracy Comparison: TA-Lib vs Manual")
    print(f"{'='*60}")

    indicators = ["RSI_14", "MACD", "MACD_signal", "ATR_14", "ADX_14",
                   "BB_upper", "BB_middle", "BB_lower"]

    for ind in indicators:
        if ind not in talib_df.columns or ind not in manual_df.columns:
            continue
        t = talib_df[ind].values
        m = manual_df[ind].values
        # Compare only where both are valid
        mask = ~(np.isnan(t) | np.isnan(m))
        if mask.sum() == 0:
            print(f"  {ind:15s}: no overlapping valid values")
            continue
        diff = np.abs(t[mask] - m[mask])
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)
        print(f"  {ind:15s}: max_diff={max_diff:.6f}, mean_diff={mean_diff:.6f}")


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    """Entry point: generate data, compute indicators, display results."""
    parser = argparse.ArgumentParser(
        description="Compute TA-Lib indicators on synthetic OHLCV data."
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Run in demo mode with default settings."
    )
    parser.add_argument(
        "--bars", type=int, default=500,
        help="Number of OHLCV bars to generate (default: 500)."
    )
    parser.add_argument(
        "--benchmark", action="store_true",
        help="Run performance benchmark comparing TA-Lib vs manual."
    )
    args = parser.parse_args()

    bars = args.bars
    print(f"TA-Lib available: {TALIB_AVAILABLE}")
    print(f"Generating {bars} bars of synthetic OHLCV data...")

    df = generate_ohlcv(bars=bars)
    print(f"Price range: {df['close'].min():.2f} - {df['close'].max():.2f}")

    if TALIB_AVAILABLE:
        talib_df = compute_with_talib(df)
        display_results(talib_df, "TA-Lib (C Library)")

        manual_df = compute_manual(df)
        display_results(manual_df, "Manual Fallback")

        compare_results(talib_df, manual_df)
    else:
        print("\nTA-Lib not installed. Using manual fallback implementations.")
        print("Install TA-Lib for C-optimized performance:")
        print("  brew install ta-lib && uv pip install TA-Lib")
        manual_df = compute_manual(df)
        display_results(manual_df, "Manual Fallback")

    if args.benchmark or args.demo:
        benchmark(df)

    print("\nNote: This is synthetic data for demonstration purposes only.")
    print("Not financial advice. Use with real market data for actual analysis.")


if __name__ == "__main__":
    main()
