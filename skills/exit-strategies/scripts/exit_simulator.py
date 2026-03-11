#!/usr/bin/env python3
"""Simulate and compare multiple exit strategies on synthetic price data.

Generates synthetic trade scenarios (winning and losing) and applies five
different exit strategies to each. Prints a comparison table showing which
strategy captured the most profit or minimized loss.

This script is for informational analysis only — not financial advice.

Usage:
    python scripts/exit_simulator.py

Dependencies:
    uv pip install pandas numpy
"""

import sys
from typing import Optional

import numpy as np
import pandas as pd

# ── Configuration ───────────────────────────────────────────────────
ENTRY_PRICE = 1.0
NUM_BARS = 200
SEED = 42

# Strategy parameters
FIXED_STOP_PCT = 0.10          # 10% fixed stop loss
ATR_TRAIL_MULT = 2.5           # ATR multiplier for trailing
ATR_PERIOD = 14                # ATR lookback
EMA_PERIOD = 20                # EMA trailing period
EMA_CONSEC = 2                 # Consecutive closes below EMA
TIME_STOP_BARS = 50            # Max bars before time stop
SCALED_TARGETS_RR = [2.0, 3.0, 5.0]  # R:R for scaled exits
SCALED_SELL_PCTS = [0.25, 0.25, 0.25]  # 25% at each target, 25% trails


# ── Price Generation ────────────────────────────────────────────────
def generate_price_series(
    entry: float,
    n_bars: int,
    trend: float = 0.0,
    volatility: float = 0.03,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """Generate synthetic OHLC price data for simulation.

    Args:
        entry: Starting price.
        n_bars: Number of bars to generate.
        trend: Drift per bar (positive = uptrend).
        volatility: Per-bar volatility (std dev of returns).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with open, high, low, close columns.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, volatility, n_bars)
    closes = entry * np.cumprod(1 + returns)

    # Generate OHLC from closes
    highs = closes * (1 + rng.uniform(0, volatility, n_bars))
    lows = closes * (1 - rng.uniform(0, volatility, n_bars))
    opens = np.roll(closes, 1)
    opens[0] = entry

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    })

    # Calculate ATR
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = df["tr"].rolling(ATR_PERIOD).mean()
    df["atr"] = df["atr"].bfill()

    # Calculate EMA
    df["ema"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()

    return df


# ── Exit Strategy Implementations ───────────────────────────────────
def fixed_stop_loss(
    df: pd.DataFrame,
    entry: float,
    stop_pct: float,
) -> dict:
    """Fixed percentage stop loss — exit when price drops X% from entry.

    Args:
        df: OHLC DataFrame.
        entry: Entry price.
        stop_pct: Stop loss percentage as decimal.

    Returns:
        Dict with strategy results.
    """
    stop_price = entry * (1 - stop_pct)

    for i, row in df.iterrows():
        if row["close"] <= stop_price:
            pnl = (row["close"] - entry) / entry * 100
            return {
                "strategy": f"Fixed Stop ({stop_pct:.0%})",
                "exit_bar": i,
                "exit_price": round(row["close"], 6),
                "exit_reason": "stop_loss",
                "pnl_pct": round(pnl, 2),
                "peak_price": round(df["close"].iloc[: i + 1].max(), 6),
            }

    # Never triggered — return final bar
    final = df["close"].iloc[-1]
    pnl = (final - entry) / entry * 100
    return {
        "strategy": f"Fixed Stop ({stop_pct:.0%})",
        "exit_bar": len(df) - 1,
        "exit_price": round(final, 6),
        "exit_reason": "end_of_data",
        "pnl_pct": round(pnl, 2),
        "peak_price": round(df["close"].max(), 6),
    }


def atr_trailing_stop(
    df: pd.DataFrame,
    entry: float,
    multiplier: float,
) -> dict:
    """ATR-based trailing stop.

    Trail = highest_close - ATR * multiplier. Only moves up.

    Args:
        df: OHLC DataFrame with 'atr' column.
        entry: Entry price.
        multiplier: ATR multiplier.

    Returns:
        Dict with strategy results.
    """
    peak = entry
    trail_stop = entry - (df["atr"].iloc[0] * multiplier)

    for i, row in df.iterrows():
        peak = max(peak, row["close"])
        new_stop = peak - (row["atr"] * multiplier)
        trail_stop = max(trail_stop, new_stop)  # Only moves up

        if row["close"] <= trail_stop:
            pnl = (row["close"] - entry) / entry * 100
            return {
                "strategy": f"ATR Trail ({multiplier}x)",
                "exit_bar": i,
                "exit_price": round(row["close"], 6),
                "exit_reason": "trailing_stop",
                "pnl_pct": round(pnl, 2),
                "peak_price": round(peak, 6),
            }

    final = df["close"].iloc[-1]
    pnl = (final - entry) / entry * 100
    return {
        "strategy": f"ATR Trail ({multiplier}x)",
        "exit_bar": len(df) - 1,
        "exit_price": round(final, 6),
        "exit_reason": "end_of_data",
        "pnl_pct": round(pnl, 2),
        "peak_price": round(peak, 6),
    }


def scaled_exits(
    df: pd.DataFrame,
    entry: float,
    stop_loss_price: float,
    targets_rr: list[float],
    sell_pcts: list[float],
    trail_pct: float = 0.15,
) -> dict:
    """Scaled exit strategy — sell tranches at R:R targets, trail remainder.

    Args:
        df: OHLC DataFrame.
        entry: Entry price.
        stop_loss_price: Initial stop loss price.
        targets_rr: R:R ratios for each tranche.
        sell_pcts: Fraction to sell at each target.
        trail_pct: Trail percentage for the final moonbag.

    Returns:
        Dict with strategy results.
    """
    risk = entry - stop_loss_price
    tp_prices = [entry + (risk * rr) for rr in targets_rr]

    remaining = 1.0
    realized_pnl = 0.0
    current_stop = stop_loss_price
    tranche_idx = 0
    peak = entry
    exits_log: list[str] = []

    for i, row in df.iterrows():
        price = row["close"]
        peak = max(peak, price)

        # Check stop loss on remaining position
        if price <= current_stop and remaining > 0:
            exit_pnl = (price - entry) / entry * remaining * 100
            realized_pnl += exit_pnl
            exits_log.append(f"Bar {i}: Stop hit, sold {remaining:.0%} at {price:.4f}")
            remaining = 0.0
            return {
                "strategy": "Scaled Exits",
                "exit_bar": i,
                "exit_price": round(price, 6),
                "exit_reason": "stop_loss" if not exits_log[:-1] else "trailing_stop",
                "pnl_pct": round(realized_pnl, 2),
                "peak_price": round(peak, 6),
                "detail": "; ".join(exits_log),
            }

        # Check take profit tranches
        if tranche_idx < len(tp_prices) and price >= tp_prices[tranche_idx]:
            sell_frac = sell_pcts[tranche_idx]
            tranche_pnl = (price - entry) / entry * sell_frac * 100
            realized_pnl += tranche_pnl
            remaining -= sell_frac
            exits_log.append(
                f"Bar {i}: TP{tranche_idx + 1} hit ({targets_rr[tranche_idx]}R), "
                f"sold {sell_frac:.0%} at {price:.4f}"
            )

            # Move stop up after each tranche
            if tranche_idx == 0:
                current_stop = entry  # Breakeven
            else:
                current_stop = entry + (risk * targets_rr[tranche_idx - 1])

            tranche_idx += 1

        # Trail the moonbag
        if tranche_idx >= len(tp_prices) and remaining > 0:
            trail_stop = peak * (1 - trail_pct)
            current_stop = max(current_stop, trail_stop)

    # End of data — close remaining
    if remaining > 0:
        final = df["close"].iloc[-1]
        exit_pnl = (final - entry) / entry * remaining * 100
        realized_pnl += exit_pnl
        exits_log.append(f"Bar {len(df) - 1}: EOD, sold {remaining:.0%} at {final:.4f}")

    return {
        "strategy": "Scaled Exits",
        "exit_bar": len(df) - 1,
        "exit_price": round(df["close"].iloc[-1], 6),
        "exit_reason": "end_of_data",
        "pnl_pct": round(realized_pnl, 2),
        "peak_price": round(peak, 6),
        "detail": "; ".join(exits_log),
    }


def ema_trailing(
    df: pd.DataFrame,
    entry: float,
    consec_bars: int = 2,
) -> dict:
    """EMA trailing stop — exit on M consecutive closes below EMA.

    Args:
        df: OHLC DataFrame with 'ema' column.
        entry: Entry price.
        consec_bars: Required consecutive closes below EMA.

    Returns:
        Dict with strategy results.
    """
    below_count = 0
    peak = entry

    for i, row in df.iterrows():
        peak = max(peak, row["close"])

        if row["close"] < row["ema"]:
            below_count += 1
            if below_count >= consec_bars:
                pnl = (row["close"] - entry) / entry * 100
                return {
                    "strategy": f"EMA({EMA_PERIOD}) Trail",
                    "exit_bar": i,
                    "exit_price": round(row["close"], 6),
                    "exit_reason": "ema_cross",
                    "pnl_pct": round(pnl, 2),
                    "peak_price": round(peak, 6),
                }
        else:
            below_count = 0

    final = df["close"].iloc[-1]
    pnl = (final - entry) / entry * 100
    return {
        "strategy": f"EMA({EMA_PERIOD}) Trail",
        "exit_bar": len(df) - 1,
        "exit_price": round(final, 6),
        "exit_reason": "end_of_data",
        "pnl_pct": round(pnl, 2),
        "peak_price": round(peak, 6),
    }


def time_stop(
    df: pd.DataFrame,
    entry: float,
    max_bars: int,
) -> dict:
    """Time-based stop — exit after N bars if not profitable.

    Args:
        df: OHLC DataFrame.
        entry: Entry price.
        max_bars: Maximum bars to hold.

    Returns:
        Dict with strategy results.
    """
    for i, row in df.iterrows():
        if i >= max_bars:
            pnl_pct = (row["close"] - entry) / entry * 100
            if pnl_pct <= 0:
                return {
                    "strategy": f"Time Stop ({max_bars} bars)",
                    "exit_bar": i,
                    "exit_price": round(row["close"], 6),
                    "exit_reason": "time_stop",
                    "pnl_pct": round(pnl_pct, 2),
                    "peak_price": round(df["close"].iloc[: i + 1].max(), 6),
                }

    final = df["close"].iloc[-1]
    pnl = (final - entry) / entry * 100
    return {
        "strategy": f"Time Stop ({max_bars} bars)",
        "exit_bar": len(df) - 1,
        "exit_price": round(final, 6),
        "exit_reason": "profitable_hold",
        "pnl_pct": round(pnl, 2),
        "peak_price": round(df["close"].max(), 6),
    }


# ── Scenario Runner ─────────────────────────────────────────────────
def run_scenario(
    name: str,
    trend: float,
    volatility: float,
    seed: int,
) -> list[dict]:
    """Run all exit strategies on a generated price scenario.

    Args:
        name: Scenario name for display.
        trend: Per-bar drift.
        volatility: Per-bar volatility.
        seed: Random seed.

    Returns:
        List of result dicts from each strategy.
    """
    df = generate_price_series(
        entry=ENTRY_PRICE,
        n_bars=NUM_BARS,
        trend=trend,
        volatility=volatility,
        seed=seed,
    )

    stop_for_scaled = ENTRY_PRICE * (1 - FIXED_STOP_PCT)

    results = [
        fixed_stop_loss(df, ENTRY_PRICE, FIXED_STOP_PCT),
        atr_trailing_stop(df, ENTRY_PRICE, ATR_TRAIL_MULT),
        scaled_exits(
            df, ENTRY_PRICE, stop_for_scaled,
            SCALED_TARGETS_RR, SCALED_SELL_PCTS,
        ),
        ema_trailing(df, ENTRY_PRICE, EMA_CONSEC),
        time_stop(df, ENTRY_PRICE, TIME_STOP_BARS),
    ]

    return results


def print_results(scenario_name: str, results: list[dict]) -> None:
    """Print formatted comparison table for a scenario.

    Args:
        scenario_name: Name of the scenario.
        results: List of strategy result dicts.
    """
    print(f"\n{'=' * 80}")
    print(f"  SCENARIO: {scenario_name}")
    print(f"  Entry Price: {ENTRY_PRICE}")
    print(f"{'=' * 80}")
    print(
        f"  {'Strategy':<22} {'Exit Bar':>8} {'Exit Price':>11} "
        f"{'P&L %':>8} {'Peak':>11} {'Reason':<18}"
    )
    print(f"  {'-' * 78}")

    for r in results:
        print(
            f"  {r['strategy']:<22} {r['exit_bar']:>8} "
            f"{r['exit_price']:>11.6f} {r['pnl_pct']:>+8.2f}% "
            f"{r['peak_price']:>11.6f} {r['exit_reason']:<18}"
        )

    # Summary
    best = max(results, key=lambda x: x["pnl_pct"])
    worst = min(results, key=lambda x: x["pnl_pct"])
    print(f"\n  Best:  {best['strategy']} ({best['pnl_pct']:+.2f}%)")
    print(f"  Worst: {worst['strategy']} ({worst['pnl_pct']:+.2f}%)")
    print(f"  Spread: {best['pnl_pct'] - worst['pnl_pct']:.2f} percentage points")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run all scenarios and print comparison tables."""
    scenarios = [
        {
            "name": "Strong Uptrend (easy winner)",
            "trend": 0.003,
            "volatility": 0.025,
            "seed": 42,
        },
        {
            "name": "Choppy Uptrend (noisy winner)",
            "trend": 0.001,
            "volatility": 0.04,
            "seed": 123,
        },
        {
            "name": "Pump and Dump (spike then crash)",
            "trend": 0.008,
            "volatility": 0.05,
            "seed": 77,
        },
        {
            "name": "Slow Bleed (gradual loser)",
            "trend": -0.002,
            "volatility": 0.02,
            "seed": 99,
        },
        {
            "name": "Sideways Chop (no trend)",
            "trend": 0.0,
            "volatility": 0.03,
            "seed": 55,
        },
    ]

    print("\n" + "=" * 80)
    print("  EXIT STRATEGY SIMULATOR")
    print("  Comparing 5 exit strategies across 5 market scenarios")
    print("  For informational analysis only — not financial advice")
    print("=" * 80)

    all_results: dict[str, list[dict]] = {}

    for scenario in scenarios:
        results = run_scenario(
            scenario["name"],
            scenario["trend"],
            scenario["volatility"],
            scenario["seed"],
        )
        print_results(scenario["name"], results)
        all_results[scenario["name"]] = results

    # ── Cross-Scenario Summary ──────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("  CROSS-SCENARIO SUMMARY")
    print(f"{'=' * 80}")

    strategy_names = [r["strategy"] for r in list(all_results.values())[0]]
    print(f"\n  {'Strategy':<22}", end="")
    for s in scenarios:
        short_name = s["name"].split("(")[0].strip()[:12]
        print(f" {short_name:>12}", end="")
    print(f" {'Avg P&L':>10}")
    print(f"  {'-' * (22 + 12 * len(scenarios) + 10)}")

    for idx, strat in enumerate(strategy_names):
        pnls = [all_results[s["name"]][idx]["pnl_pct"] for s in scenarios]
        avg_pnl = sum(pnls) / len(pnls)
        print(f"  {strat:<22}", end="")
        for pnl in pnls:
            print(f" {pnl:>+11.2f}%", end="")
        print(f" {avg_pnl:>+9.2f}%")

    print(f"\n  Note: Results depend on synthetic data parameters and random seeds.")
    print(f"  Real-world performance will vary based on market conditions.\n")


if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: uv pip install pandas numpy")
        sys.exit(1)
