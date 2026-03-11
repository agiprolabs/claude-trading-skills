#!/usr/bin/env python3
"""Backtest a regime-adaptive strategy vs a static strategy on synthetic data.

Generates OHLCV data with clear regime transitions, then compares:
- Static strategy: Always uses EMA crossover signals
- Adaptive strategy: Switches between EMA crossover (trending regime)
  and RSI mean-reversion (ranging regime), with position sizing
  adjusted by volatility regime.

Usage:
    python scripts/regime_backtest.py

Dependencies:
    uv pip install pandas numpy

Environment Variables:
    None required (uses synthetic data only).
"""

import sys
from typing import Optional

import numpy as np
import pandas as pd

# ── Configuration ───────────────────────────────────────────────────
N_BARS = 500
INITIAL_CAPITAL = 10000.0
COMMISSION_BPS = 10  # 10 bps per trade (each way)

# Indicator parameters
ATR_PERIOD = 14
ADX_PERIOD = 14
EMA_FAST = 10
EMA_SLOW = 30
RSI_PERIOD = 14
RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
VOL_LOOKBACK = 80


# ── Data Generation ────────────────────────────────────────────────
def generate_regime_data(n_bars: int = 500, seed: int = 123) -> pd.DataFrame:
    """Generate synthetic OHLCV data with multiple regime transitions.

    Regime schedule:
    - 0-79:    Low vol uptrend
    - 80-159:  High vol uptrend
    - 160-249: Low vol range (mean-reverting)
    - 250-329: High vol range (choppy)
    - 330-399: Low vol downtrend
    - 400-499: Low vol uptrend (recovery)

    Args:
        n_bars: Number of bars.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with open, high, low, close, volume columns and a
        'true_regime' column for validation.
    """
    rng = np.random.RandomState(seed)
    prices = [100.0]
    volumes = []
    true_regimes = ["low_vol_uptrend"]  # First bar regime

    regime_schedule = [
        (80, 0.002, 0.007, 1200, "low_vol_uptrend"),
        (160, 0.003, 0.022, 2500, "high_vol_uptrend"),
        (250, 0.0, 0.005, 900, "low_vol_range"),
        (330, 0.0, 0.028, 1800, "high_vol_range"),
        (400, -0.002, 0.008, 1100, "low_vol_downtrend"),
        (500, 0.002, 0.007, 1300, "low_vol_uptrend"),
    ]

    for i in range(1, n_bars):
        # Find current regime
        drift, vol, base_vol, regime_name = 0.0, 0.01, 1000, "unknown"
        for end_bar, d, v, bv, name in regime_schedule:
            if i < end_bar:
                drift, vol, base_vol, regime_name = d, v, bv, name
                break

        # For range regimes, add mean-reversion force
        if "range" in regime_name:
            mean_target = 130.0 if i < 330 else 120.0
            drift = (mean_target - prices[-1]) / mean_target * 0.05

        ret = drift + vol * rng.randn()
        prices.append(prices[-1] * (1 + ret))
        volumes.append(base_vol * (1 + 0.4 * abs(rng.randn())))
        true_regimes.append(regime_name)

    volumes.append(volumes[-1])
    prices_arr = np.array(prices)

    # Generate OHLC
    noise = np.abs(rng.randn(n_bars)) * 0.004 + 0.002
    highs = prices_arr * (1 + noise)
    lows = prices_arr * (1 - noise)
    opens = np.roll(prices_arr, 1)
    opens[0] = prices_arr[0]

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices_arr,
        "volume": volumes,
        "true_regime": true_regimes,
    })


# ── Indicators ──────────────────────────────────────────────────────
def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average True Range."""
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_atr_percentile(
    high: pd.Series, low: pd.Series, close: pd.Series,
    atr_period: int = 14, lookback: int = 80
) -> pd.Series:
    """ATR percentile rank."""
    atr = compute_atr(high, low, close, atr_period)
    return atr.rolling(lookback).rank(pct=True)


def compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average Directional Index."""
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm_copy = plus_dm.copy()
    minus_dm_copy = minus_dm.copy()
    plus_dm_copy[plus_dm < minus_dm] = 0
    minus_dm_copy[minus_dm < plus_dm] = 0

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * plus_dm_copy.ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm_copy.ewm(span=period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    return dx.ewm(span=period, adjust=False).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index.

    Args:
        close: Close prices.
        period: RSI period.

    Returns:
        RSI series (0-100).
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def detect_regime(vol_pct: float, adx_val: float) -> str:
    """Classify regime from volatility percentile and ADX.

    Args:
        vol_pct: ATR percentile (0-1).
        adx_val: Current ADX value.

    Returns:
        Regime string.
    """
    is_trending = adx_val > 22
    is_high_vol = vol_pct > 0.65

    if is_trending and not is_high_vol:
        return "quiet_trend"
    elif is_trending and is_high_vol:
        return "volatile_trend"
    elif not is_trending and not is_high_vol:
        return "quiet_range"
    else:
        return "volatile_range"


# ── Strategy Logic ──────────────────────────────────────────────────
def run_static_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """Run a static EMA crossover strategy (no regime adaptation).

    Always uses EMA crossover signals with fixed position sizing.

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with trade log columns.
    """
    close = df["close"]
    ema_fast = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=EMA_SLOW, adjust=False).mean()

    position = 0  # 0 = flat, 1 = long
    capital = INITIAL_CAPITAL
    shares = 0.0
    trades: list[dict] = []

    for i in range(EMA_SLOW + 1, len(df)):
        signal = 0
        if ema_fast.iloc[i] > ema_slow.iloc[i] and ema_fast.iloc[i - 1] <= ema_slow.iloc[i - 1]:
            signal = 1  # Buy
        elif ema_fast.iloc[i] < ema_slow.iloc[i] and ema_fast.iloc[i - 1] >= ema_slow.iloc[i - 1]:
            signal = -1  # Sell

        price = close.iloc[i]
        commission_rate = COMMISSION_BPS / 10000

        if signal == 1 and position == 0:
            # Buy with full capital
            cost = capital * commission_rate
            shares = (capital - cost) / price
            capital = 0
            position = 1
            trades.append({"bar": i, "action": "BUY", "price": price,
                           "shares": shares, "strategy": "ema_xover"})

        elif signal == -1 and position == 1:
            # Sell all
            proceeds = shares * price
            cost = proceeds * commission_rate
            capital = proceeds - cost
            trades.append({"bar": i, "action": "SELL", "price": price,
                           "shares": shares, "pnl": capital - INITIAL_CAPITAL,
                           "strategy": "ema_xover"})
            shares = 0
            position = 0

    # Close any open position at end
    if position == 1:
        price = close.iloc[-1]
        proceeds = shares * price
        cost = proceeds * (COMMISSION_BPS / 10000)
        capital = proceeds - cost
        trades.append({"bar": len(df) - 1, "action": "SELL (EOD)", "price": price,
                       "shares": shares, "pnl": capital - INITIAL_CAPITAL,
                       "strategy": "ema_xover"})
        shares = 0

    equity = capital if position == 0 else shares * close.iloc[-1]
    return pd.DataFrame(trades) if trades else pd.DataFrame(), equity


def run_adaptive_strategy(
    df: pd.DataFrame,
    vol_pct: pd.Series,
    adx: pd.Series,
    rsi: pd.Series,
) -> tuple[pd.DataFrame, float]:
    """Run regime-adaptive strategy.

    In trending regimes: use EMA crossover signals.
    In ranging regimes: use RSI mean-reversion signals.
    Position size adjusted by volatility regime.

    Args:
        df: OHLCV DataFrame.
        vol_pct: ATR percentile series.
        adx: ADX series.
        rsi: RSI series.

    Returns:
        Tuple of (trade log DataFrame, final equity).
    """
    close = df["close"]
    ema_fast = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=EMA_SLOW, adjust=False).mean()

    position = 0
    capital = INITIAL_CAPITAL
    shares = 0.0
    trades: list[dict] = []
    warmup = max(EMA_SLOW, VOL_LOOKBACK) + 5

    for i in range(warmup, len(df)):
        vp = vol_pct.iloc[i]
        ax = adx.iloc[i]
        rs = rsi.iloc[i]

        if np.isnan(vp) or np.isnan(ax) or np.isnan(rs):
            continue

        regime = detect_regime(vp, ax)
        price = close.iloc[i]
        commission_rate = COMMISSION_BPS / 10000

        # Position size multiplier based on regime
        if regime == "quiet_trend":
            size_mult = 1.0
        elif regime == "volatile_trend":
            size_mult = 0.50
        elif regime == "quiet_range":
            size_mult = 0.75
        else:  # volatile_range
            size_mult = 0.25

        signal = 0

        if regime in ("quiet_trend", "volatile_trend"):
            # Trend strategy: EMA crossover
            if (ema_fast.iloc[i] > ema_slow.iloc[i]
                    and ema_fast.iloc[i - 1] <= ema_slow.iloc[i - 1]):
                signal = 1
            elif (ema_fast.iloc[i] < ema_slow.iloc[i]
                    and ema_fast.iloc[i - 1] >= ema_slow.iloc[i - 1]):
                signal = -1
        else:
            # Range strategy: RSI mean-reversion
            if rs < RSI_OVERSOLD:
                signal = 1
            elif rs > RSI_OVERBOUGHT:
                signal = -1

        if signal == 1 and position == 0:
            invest = capital * size_mult
            cost = invest * commission_rate
            shares = (invest - cost) / price
            capital -= invest
            position = 1
            trades.append({
                "bar": i, "action": "BUY", "price": price,
                "shares": shares, "regime": regime,
                "size_mult": size_mult,
                "strategy": "ema_xover" if "trend" in regime else "rsi_mr",
            })

        elif signal == -1 and position == 1:
            proceeds = shares * price
            cost = proceeds * commission_rate
            capital += proceeds - cost
            pnl = capital - INITIAL_CAPITAL
            trades.append({
                "bar": i, "action": "SELL", "price": price,
                "shares": shares, "pnl": pnl, "regime": regime,
                "strategy": "ema_xover" if "trend" in regime else "rsi_mr",
            })
            shares = 0
            position = 0

    # Close any open position
    if position == 1:
        price = close.iloc[-1]
        proceeds = shares * price
        cost = proceeds * (COMMISSION_BPS / 10000)
        capital += proceeds - cost
        trades.append({
            "bar": len(df) - 1, "action": "SELL (EOD)", "price": price,
            "shares": shares, "pnl": capital - INITIAL_CAPITAL,
            "regime": "end", "strategy": "close",
        })
        shares = 0

    equity = capital
    trade_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    return trade_df, equity


# ── Performance Metrics ─────────────────────────────────────────────
def compute_metrics(
    trades_df: pd.DataFrame, final_equity: float, label: str
) -> dict:
    """Compute performance metrics from a trade log.

    Args:
        trades_df: DataFrame with trade records.
        final_equity: Final portfolio equity.
        label: Strategy label.

    Returns:
        Dict of performance metrics.
    """
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100
    n_trades = len(trades_df[trades_df["action"].str.startswith("SELL")]) if len(trades_df) > 0 else 0

    wins = 0
    losses = 0
    if len(trades_df) > 0 and "pnl" in trades_df.columns:
        sell_trades = trades_df[trades_df["action"].str.startswith("SELL")].copy()
        # Compute per-trade PnL from sequential buy/sell
        pnls = []
        buy_price = None
        buy_shares = None
        for _, row in trades_df.iterrows():
            if row["action"] == "BUY":
                buy_price = row["price"]
                buy_shares = row["shares"]
            elif row["action"].startswith("SELL") and buy_price is not None:
                trade_pnl = (row["price"] - buy_price) * buy_shares
                pnls.append(trade_pnl)
                if trade_pnl > 0:
                    wins += 1
                else:
                    losses += 1
                buy_price = None

    win_rate = wins / max(1, wins + losses) * 100

    return {
        "label": label,
        "final_equity": final_equity,
        "total_return_pct": total_return,
        "n_trades": n_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
    }


# ── Display ─────────────────────────────────────────────────────────
def print_regime_timeline(df: pd.DataFrame, vol_pct: pd.Series, adx: pd.Series) -> None:
    """Print regime classification across the full history.

    Args:
        df: OHLCV DataFrame.
        vol_pct: ATR percentile series.
        adx: ADX series.
    """
    print("\n" + "=" * 70)
    print("  REGIME TIMELINE")
    print("=" * 70)

    prev_regime = ""
    regime_start = 0

    for i in range(len(df)):
        vp = vol_pct.iloc[i] if not np.isnan(vol_pct.iloc[i]) else 0.5
        ax = adx.iloc[i] if not np.isnan(adx.iloc[i]) else 20.0
        regime = detect_regime(vp, ax)

        if regime != prev_regime:
            if prev_regime:
                true_regime = df["true_regime"].iloc[regime_start]
                print(
                    f"  Bars {regime_start:>4}-{i-1:<4}  "
                    f"Detected: {prev_regime:<18}  "
                    f"Actual: {true_regime:<22}  "
                    f"Close: {df['close'].iloc[i-1]:>8.2f}"
                )
            prev_regime = regime
            regime_start = i

    # Final segment
    if prev_regime:
        true_regime = df["true_regime"].iloc[regime_start]
        print(
            f"  Bars {regime_start:>4}-{len(df)-1:<4}  "
            f"Detected: {prev_regime:<18}  "
            f"Actual: {true_regime:<22}  "
            f"Close: {df['close'].iloc[-1]:>8.2f}"
        )


def print_comparison(
    static_metrics: dict, adaptive_metrics: dict
) -> None:
    """Print side-by-side comparison of strategies.

    Args:
        static_metrics: Performance metrics for static strategy.
        adaptive_metrics: Performance metrics for adaptive strategy.
    """
    print("\n" + "=" * 70)
    print("  PERFORMANCE COMPARISON")
    print("=" * 70)
    print(f"\n  {'Metric':<25}  {'Static (EMA only)':<20}  {'Regime-Adaptive':<20}")
    print(f"  {'-'*25}  {'-'*20}  {'-'*20}")

    rows = [
        ("Initial Capital", f"${INITIAL_CAPITAL:,.2f}", f"${INITIAL_CAPITAL:,.2f}"),
        ("Final Equity",
         f"${static_metrics['final_equity']:,.2f}",
         f"${adaptive_metrics['final_equity']:,.2f}"),
        ("Total Return",
         f"{static_metrics['total_return_pct']:+.2f}%",
         f"{adaptive_metrics['total_return_pct']:+.2f}%"),
        ("Num Trades",
         f"{static_metrics['n_trades']}",
         f"{adaptive_metrics['n_trades']}"),
        ("Win Rate",
         f"{static_metrics['win_rate_pct']:.1f}%",
         f"{adaptive_metrics['win_rate_pct']:.1f}%"),
        ("Wins / Losses",
         f"{static_metrics['wins']} / {static_metrics['losses']}",
         f"{adaptive_metrics['wins']} / {adaptive_metrics['losses']}"),
    ]

    for label, static_val, adaptive_val in rows:
        print(f"  {label:<25}  {static_val:<20}  {adaptive_val:<20}")

    diff = adaptive_metrics["total_return_pct"] - static_metrics["total_return_pct"]
    print(f"\n  Regime adaptation edge: {diff:+.2f}% return difference")

    if diff > 0:
        print("  The adaptive strategy outperformed by avoiding wrong-regime trades.")
    else:
        print("  The static strategy outperformed — regime detection may have filtered")
        print("  profitable signals. Review regime thresholds and strategy pairing.")

    print("\n  This is a simulation for analytical purposes only.")
    print("  Past synthetic performance does not predict real market results.")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run the regime-adaptive backtest comparison."""
    print("Generating synthetic data with 6 regime phases (500 bars)...")
    df = generate_regime_data(N_BARS)

    print("Computing indicators...")
    vol_pct = compute_atr_percentile(
        df["high"], df["low"], df["close"], ATR_PERIOD, VOL_LOOKBACK
    )
    adx = compute_adx(df["high"], df["low"], df["close"], ADX_PERIOD)
    rsi = compute_rsi(df["close"], RSI_PERIOD)

    # Show regime timeline
    print_regime_timeline(df, vol_pct, adx)

    # Run both strategies
    print("\nRunning static EMA crossover strategy...")
    static_trades, static_equity = run_static_strategy(df)

    print("Running regime-adaptive strategy...")
    adaptive_trades, adaptive_equity = run_adaptive_strategy(df, vol_pct, adx, rsi)

    # Compute and display metrics
    static_metrics = compute_metrics(static_trades, static_equity, "Static")
    adaptive_metrics = compute_metrics(adaptive_trades, adaptive_equity, "Adaptive")

    print_comparison(static_metrics, adaptive_metrics)

    # Show adaptive strategy trade detail
    if len(adaptive_trades) > 0 and "regime" in adaptive_trades.columns:
        print("\n" + "-" * 70)
        print("  ADAPTIVE STRATEGY — TRADE LOG")
        print("-" * 70)
        for _, row in adaptive_trades.iterrows():
            regime = row.get("regime", "?")
            strat = row.get("strategy", "?")
            size_m = row.get("size_mult", 1.0)
            action = row["action"]
            print(
                f"  Bar {int(row['bar']):>4}  {action:<12}  "
                f"@ {row['price']:>8.2f}  "
                f"Regime: {regime:<18}  "
                f"Strategy: {strat:<10}  "
                f"Size: {size_m:.0%}"
            )
    print()


if __name__ == "__main__":
    main()
