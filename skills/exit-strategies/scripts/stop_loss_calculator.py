#!/usr/bin/env python3
"""Calculate stop loss levels, position sizes, and R:R targets for a trade.

Takes entry price, ATR value, and account size as inputs and computes
stop loss levels using multiple methods. For each stop level, shows the
risk amount, position size for a 2% account risk, and R:R target prices.

This script is for informational analysis only — not financial advice.

Usage:
    python scripts/stop_loss_calculator.py

    Or with custom values:
    ENTRY_PRICE=0.05 ATR_VALUE=0.004 ACCOUNT_SIZE=100 python scripts/stop_loss_calculator.py

Dependencies:
    None (pure math, no external packages)

Environment Variables:
    ENTRY_PRICE: Token price at entry (default: 0.001 SOL)
    ATR_VALUE: Current ATR(14) value (default: 0.00008)
    ACCOUNT_SIZE: Account size in SOL (default: 50.0)
    RISK_PCT: Account risk percentage as decimal (default: 0.02 = 2%)
"""

import os
import sys
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────
ENTRY_PRICE = float(os.getenv("ENTRY_PRICE", "0.001"))
ATR_VALUE = float(os.getenv("ATR_VALUE", "0.00008"))
ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "50.0"))
RISK_PCT = float(os.getenv("RISK_PCT", "0.02"))

# Fixed percentage stop levels
FIXED_STOP_PCTS = [0.05, 0.10, 0.15, 0.20]

# ATR multipliers
ATR_MULTIPLIERS = [1.5, 2.0, 2.5, 3.0]

# R:R ratios for target calculation
RR_RATIOS = [2.0, 3.0, 5.0, 10.0]


# ── Core Functions ──────────────────────────────────────────────────
def calculate_fixed_stop(
    entry_price: float,
    stop_pct: float,
) -> dict:
    """Calculate a fixed percentage stop loss.

    Args:
        entry_price: Price at entry.
        stop_pct: Stop percentage as decimal (0.10 = 10%).

    Returns:
        Dict with stop details.
    """
    stop_price = entry_price * (1 - stop_pct)
    risk_per_unit = entry_price - stop_price
    return {
        "method": f"Fixed {stop_pct:.0%}",
        "stop_price": stop_price,
        "risk_per_unit": risk_per_unit,
        "risk_pct": stop_pct * 100,
    }


def calculate_atr_stop(
    entry_price: float,
    atr_value: float,
    multiplier: float,
) -> dict:
    """Calculate an ATR-based stop loss.

    Args:
        entry_price: Price at entry.
        atr_value: Current ATR value.
        multiplier: ATR multiplier.

    Returns:
        Dict with stop details.
    """
    risk_per_unit = atr_value * multiplier
    stop_price = entry_price - risk_per_unit
    risk_pct = (risk_per_unit / entry_price) * 100
    return {
        "method": f"ATR {multiplier:.1f}x",
        "stop_price": max(stop_price, 0),  # Price cannot be negative
        "risk_per_unit": risk_per_unit,
        "risk_pct": risk_pct,
    }


def calculate_position_size(
    account_size: float,
    risk_pct: float,
    risk_per_unit: float,
) -> dict:
    """Calculate position size to risk exactly X% of account.

    Args:
        account_size: Total account value in SOL.
        risk_pct: Fraction of account to risk (0.02 = 2%).
        risk_per_unit: Price difference between entry and stop.

    Returns:
        Dict with sizing details.
    """
    if risk_per_unit <= 0:
        return {
            "risk_amount_sol": 0,
            "position_size_units": 0,
            "position_size_sol": 0,
            "position_pct_of_account": 0,
        }

    risk_amount = account_size * risk_pct
    position_units = risk_amount / risk_per_unit
    position_sol = position_units * ENTRY_PRICE
    position_pct = (position_sol / account_size) * 100

    return {
        "risk_amount_sol": round(risk_amount, 6),
        "position_size_units": round(position_units, 2),
        "position_size_sol": round(position_sol, 6),
        "position_pct_of_account": round(position_pct, 2),
    }


def calculate_rr_targets(
    entry_price: float,
    risk_per_unit: float,
    ratios: list[float],
) -> list[dict]:
    """Calculate take profit prices at given R:R ratios.

    Args:
        entry_price: Price at entry.
        risk_per_unit: Distance from entry to stop.
        ratios: List of R:R ratios.

    Returns:
        List of dicts with target price and gain percentage.
    """
    targets = []
    for ratio in ratios:
        tp_price = entry_price + (risk_per_unit * ratio)
        gain_pct = (tp_price - entry_price) / entry_price * 100
        targets.append({
            "ratio": f"{ratio:.0f}:1",
            "price": tp_price,
            "gain_pct": round(gain_pct, 2),
        })
    return targets


# ── Display Functions ───────────────────────────────────────────────
def print_header() -> None:
    """Print the calculator header with input values."""
    print("\n" + "=" * 80)
    print("  STOP LOSS & POSITION SIZE CALCULATOR")
    print("  For informational analysis only — not financial advice")
    print("=" * 80)
    print(f"\n  Entry Price:    {ENTRY_PRICE:.8f} SOL")
    print(f"  ATR(14) Value:  {ATR_VALUE:.8f}")
    print(f"  Account Size:   {ACCOUNT_SIZE:.2f} SOL")
    print(f"  Risk Per Trade: {RISK_PCT:.0%} ({ACCOUNT_SIZE * RISK_PCT:.4f} SOL)")
    print()


def print_stop_table(stops: list[dict]) -> None:
    """Print formatted stop loss comparison table.

    Args:
        stops: List of stop detail dicts.
    """
    print(f"  {'Method':<14} {'Stop Price':>14} {'Risk/Unit':>14} {'Risk %':>8}")
    print(f"  {'-' * 52}")

    for s in stops:
        print(
            f"  {s['method']:<14} "
            f"{s['stop_price']:>14.8f} "
            f"{s['risk_per_unit']:>14.8f} "
            f"{s['risk_pct']:>7.2f}%"
        )


def print_sizing_table(stops: list[dict]) -> None:
    """Print position sizing for each stop method.

    Args:
        stops: List of stop detail dicts.
    """
    print(f"\n  POSITION SIZING (to risk exactly {RISK_PCT:.0%} of account)")
    print(f"  {'-' * 72}")
    print(
        f"  {'Method':<14} {'Risk (SOL)':>11} {'Units':>14} "
        f"{'Size (SOL)':>12} {'% of Acct':>10}"
    )
    print(f"  {'-' * 72}")

    for s in stops:
        sizing = calculate_position_size(
            ACCOUNT_SIZE, RISK_PCT, s["risk_per_unit"]
        )
        print(
            f"  {s['method']:<14} "
            f"{sizing['risk_amount_sol']:>11.6f} "
            f"{sizing['position_size_units']:>14.2f} "
            f"{sizing['position_size_sol']:>12.6f} "
            f"{sizing['position_pct_of_account']:>9.2f}%"
        )


def print_rr_table(stops: list[dict]) -> None:
    """Print R:R target prices for each stop method.

    Args:
        stops: List of stop detail dicts.
    """
    print(f"\n  R:R TARGET PRICES")
    print(f"  {'-' * 72}")

    header = f"  {'Method':<14}"
    for ratio in RR_RATIOS:
        header += f" {ratio:.0f}:1 Target     "
    print(header)
    print(f"  {'-' * 72}")

    for s in stops:
        targets = calculate_rr_targets(
            ENTRY_PRICE, s["risk_per_unit"], RR_RATIOS
        )
        line = f"  {s['method']:<14}"
        for t in targets:
            line += f" {t['price']:>10.8f}  "
        print(line)

    # Print gain percentages for the first stop method as reference
    print(f"\n  Gain % at each R:R (using {stops[0]['method']}):")
    ref_targets = calculate_rr_targets(
        ENTRY_PRICE, stops[0]["risk_per_unit"], RR_RATIOS
    )
    for t in ref_targets:
        print(f"    {t['ratio']:>5} → {t['price']:.8f} ({t['gain_pct']:>+.2f}%)")


def print_quick_reference() -> None:
    """Print quick reference guide."""
    print(f"\n  QUICK REFERENCE")
    print(f"  {'-' * 60}")
    print(f"  Rule of thumb for stop distance:")
    print(f"    Scalp:     1.0-1.5× ATR = {ATR_VALUE * 1.0:.8f} - {ATR_VALUE * 1.5:.8f}")
    print(f"    Day trade: 1.5-2.0× ATR = {ATR_VALUE * 1.5:.8f} - {ATR_VALUE * 2.0:.8f}")
    print(f"    Swing:     2.0-3.0× ATR = {ATR_VALUE * 2.0:.8f} - {ATR_VALUE * 3.0:.8f}")
    print()
    print(f"  Maximum position size guidelines:")
    print(f"    Conservative: risk 1% = {ACCOUNT_SIZE * 0.01:.4f} SOL")
    print(f"    Standard:     risk 2% = {ACCOUNT_SIZE * 0.02:.4f} SOL")
    print(f"    Aggressive:   risk 5% = {ACCOUNT_SIZE * 0.05:.4f} SOL")
    print()
    print(f"  Note: If position size exceeds 20% of account, consider")
    print(f"  widening the stop or reducing the position.")
    print()


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run the stop loss calculator and print all tables."""
    # Validate inputs
    if ENTRY_PRICE <= 0:
        print("Error: ENTRY_PRICE must be positive.")
        sys.exit(1)
    if ATR_VALUE <= 0:
        print("Error: ATR_VALUE must be positive.")
        sys.exit(1)
    if ACCOUNT_SIZE <= 0:
        print("Error: ACCOUNT_SIZE must be positive.")
        sys.exit(1)
    if not 0 < RISK_PCT < 1:
        print("Error: RISK_PCT must be between 0 and 1.")
        sys.exit(1)

    print_header()

    # Calculate all stops
    fixed_stops = [
        calculate_fixed_stop(ENTRY_PRICE, pct)
        for pct in FIXED_STOP_PCTS
    ]
    atr_stops = [
        calculate_atr_stop(ENTRY_PRICE, ATR_VALUE, mult)
        for mult in ATR_MULTIPLIERS
    ]

    all_stops = fixed_stops + atr_stops

    # Print tables
    print("  FIXED PERCENTAGE STOPS")
    print_stop_table(fixed_stops)

    print(f"\n  ATR-BASED STOPS (ATR = {ATR_VALUE:.8f})")
    print_stop_table(atr_stops)

    print_sizing_table(all_stops)
    print_rr_table(all_stops)
    print_quick_reference()


if __name__ == "__main__":
    main()
