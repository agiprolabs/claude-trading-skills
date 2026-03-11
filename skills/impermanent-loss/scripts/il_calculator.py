#!/usr/bin/env python3
"""Impermanent loss calculator for constant-product and CLMM AMM pools.

Computes IL for any price change scenario, generates comparison tables,
and estimates breakeven fee requirements. Pure math — no external APIs needed.

Usage:
    python scripts/il_calculator.py
    python scripts/il_calculator.py --demo
    python scripts/il_calculator.py --ratio 2.5
    python scripts/il_calculator.py --initial-price 150 --new-price 200 --deposit 10000
    python scripts/il_calculator.py --clmm --range-pct 20 --ratio 1.5

Dependencies:
    None (standard library only)

Environment Variables:
    None required
"""

import argparse
import math
import sys
from typing import Optional


# ── Core IL Formulas ────────────────────────────────────────────────


def il_constant_product(price_ratio: float) -> float:
    """Compute impermanent loss for a constant-product (x*y=k) AMM.

    Args:
        price_ratio: P_new / P_initial. Must be positive.

    Returns:
        IL as a decimal (e.g., -0.0572 for -5.72% IL).

    Raises:
        ValueError: If price_ratio is not positive.
    """
    if price_ratio <= 0:
        raise ValueError(f"Price ratio must be positive, got {price_ratio}")
    r = price_ratio
    return 2.0 * math.sqrt(r) / (1.0 + r) - 1.0


def il_clmm(
    price_ratio: float,
    range_lower: float,
    range_upper: float,
) -> tuple[float, str]:
    """Compute IL for a concentrated liquidity position.

    Args:
        price_ratio: P_new / P_initial. Must be positive.
        range_lower: Lower bound of range as ratio to initial price (e.g., 0.8).
        range_upper: Upper bound of range as ratio to initial price (e.g., 1.2).

    Returns:
        Tuple of (IL as decimal, status string).
        Status is "in_range", "below_range", or "above_range".

    Raises:
        ValueError: If inputs are invalid.
    """
    if price_ratio <= 0:
        raise ValueError(f"Price ratio must be positive, got {price_ratio}")
    if range_lower <= 0 or range_upper <= 0:
        raise ValueError("Range bounds must be positive")
    if range_lower >= range_upper:
        raise ValueError("range_lower must be less than range_upper")

    r = price_ratio
    p_l = range_lower
    p_u = range_upper

    # Initial position value at price ratio = 1.0 (normalized)
    # Using virtual reserves framework
    sqrt_p0 = 1.0  # initial price ratio = 1
    sqrt_pl = math.sqrt(p_l)
    sqrt_pu = math.sqrt(p_u)

    # Liquidity L (normalized so initial deposit = some value)
    # Initial value: L * (sqrt(P0) - sqrt(Pl)) * P0 + L * (1/sqrt(P0) - 1/sqrt(Pu))
    # At P0=1: L * (1 - sqrt_pl) + L * (1 - 1/sqrt_pu)
    initial_x_value = 1.0 - 1.0 / sqrt_pu  # token X amount * price (=1)
    initial_y_value = 1.0 - sqrt_pl          # token Y amount
    v_initial = initial_x_value + initial_y_value

    if v_initial <= 0:
        raise ValueError("Invalid range: initial value is non-positive")

    # Hold value at new price ratio r
    # We held initial_x_value worth of X and initial_y_value of Y
    # X appreciates by factor r, Y stays (Y is numeraire)
    v_hold = initial_x_value * r + initial_y_value

    # LP value at new price ratio r
    sqrt_r = math.sqrt(r)

    if r <= p_l:
        # Price below range: 100% token X
        status = "below_range"
        # All Y converted to X at price sqrt_pl
        v_lp = (1.0 / sqrt_pl - 1.0 / sqrt_pu) * r
    elif r >= p_u:
        # Price above range: 100% token Y
        status = "above_range"
        v_lp = sqrt_pu - sqrt_pl
    else:
        # Price in range
        status = "in_range"
        v_lp = (sqrt_r - sqrt_pl) + (1.0 / sqrt_r - 1.0 / sqrt_pu) * r
        # Simplify: sqrt_r - sqrt_pl + r/sqrt_r - r/sqrt_pu
        #         = sqrt_r - sqrt_pl + sqrt_r - r/sqrt_pu
        #         = 2*sqrt_r - sqrt_pl - r/sqrt_pu
        v_lp = 2.0 * sqrt_r - sqrt_pl - r / sqrt_pu

    il = v_lp / v_hold - 1.0
    return il, status


def concentration_factor(range_lower: float, range_upper: float) -> float:
    """Compute the liquidity concentration factor for a CLMM range.

    Args:
        range_lower: Lower price bound as ratio (e.g., 0.8 for -20%).
        range_upper: Upper price bound as ratio (e.g., 1.2 for +20%).

    Returns:
        Concentration factor (multiplier vs full-range).
    """
    if range_lower <= 0 or range_upper <= 0:
        raise ValueError("Range bounds must be positive")
    if range_lower >= range_upper:
        raise ValueError("range_lower must be less than range_upper")
    return 1.0 / (1.0 - math.sqrt(range_lower / range_upper))


def lp_vs_hold_values(
    initial_price: float,
    new_price: float,
    deposit_value: float,
) -> dict[str, float]:
    """Compare LP value vs hold value for a constant-product pool.

    Args:
        initial_price: Price of token X at deposit time.
        new_price: Current price of token X.
        deposit_value: Total deposit value in quote currency.

    Returns:
        Dictionary with lp_value, hold_value, il_pct, il_abs.
    """
    if initial_price <= 0 or new_price <= 0:
        raise ValueError("Prices must be positive")
    if deposit_value <= 0:
        raise ValueError("Deposit value must be positive")

    r = new_price / initial_price
    il = il_constant_product(r)

    # Hold value: half in token X (appreciates by r), half in quote
    hold_value = deposit_value * (r + 1) / 2.0
    lp_value = hold_value * (1.0 + il)
    il_abs = lp_value - hold_value

    return {
        "lp_value": lp_value,
        "hold_value": hold_value,
        "il_pct": il * 100.0,
        "il_abs": il_abs,
        "price_ratio": r,
    }


def breakeven_daily_fee_rate(daily_volatility: float) -> float:
    """Compute the minimum daily fee rate to offset expected IL.

    Uses the small-move approximation: E[IL] ~ sigma^2 / 8.

    Args:
        daily_volatility: Daily volatility as decimal (e.g., 0.05 for 5%).

    Returns:
        Minimum daily fee rate as decimal.
    """
    if daily_volatility < 0:
        raise ValueError("Volatility must be non-negative")
    return daily_volatility ** 2 / 8.0


# ── Display Functions ───────────────────────────────────────────────


def print_il_table() -> None:
    """Print a comprehensive IL table for various price ratios."""
    print("\n" + "=" * 65)
    print("  IMPERMANENT LOSS TABLE — Constant-Product AMM (x * y = k)")
    print("=" * 65)
    print(f"  {'Price Change':>14}  {'Ratio (r)':>10}  {'IL':>10}  {'LP/Hold':>10}")
    print("-" * 65)

    ratios = [
        (0.01, "-99%"),
        (0.05, "-95%"),
        (0.10, "-90%"),
        (0.20, "-80%"),
        (0.25, "-75%"),
        (0.33, "-67%"),
        (0.50, "-50%"),
        (0.67, "-33%"),
        (0.75, "-25%"),
        (0.80, "-20%"),
        (0.90, "-10%"),
        (0.95, "-5%"),
        (1.00, "0%"),
        (1.05, "+5%"),
        (1.10, "+10%"),
        (1.20, "+20%"),
        (1.25, "+25%"),
        (1.50, "+50%"),
        (1.75, "+75%"),
        (2.00, "+100%"),
        (3.00, "+200%"),
        (5.00, "+400%"),
        (10.00, "+900%"),
        (20.00, "+1900%"),
        (50.00, "+4900%"),
        (100.00, "+9900%"),
    ]

    for r, label in ratios:
        il = il_constant_product(r)
        lp_hold = 1.0 + il
        print(f"  {label:>14}  {r:>10.2f}  {il * 100:>9.2f}%  {lp_hold:>9.4f}")

    print("=" * 65)
    print("  IL is always negative. LP/Hold < 1 means LP underperforms.\n")


def print_clmm_comparison(range_pct: float = 20.0) -> None:
    """Print IL comparison between constant-product and CLMM.

    Args:
        range_pct: CLMM range as +/- percentage (e.g., 20 for ±20%).
    """
    range_lower = 1.0 - range_pct / 100.0
    range_upper = 1.0 + range_pct / 100.0
    cf = concentration_factor(range_lower, range_upper)

    print(f"\n{'=' * 75}")
    print(f"  CLMM vs CONSTANT-PRODUCT IL COMPARISON")
    print(f"  Range: ±{range_pct:.0f}% ({range_lower:.2f}x — {range_upper:.2f}x)")
    print(f"  Concentration Factor: {cf:.1f}x")
    print(f"{'=' * 75}")
    print(
        f"  {'Price Change':>14}  {'Ratio':>6}  {'CP IL':>9}  "
        f"{'CLMM IL':>9}  {'CLMM Status':>14}"
    )
    print("-" * 75)

    ratios = [
        (0.50, "-50%"),
        (0.67, "-33%"),
        (0.75, "-25%"),
        (0.80, "-20%"),
        (0.90, "-10%"),
        (0.95, "-5%"),
        (1.00, "0%"),
        (1.05, "+5%"),
        (1.10, "+10%"),
        (1.20, "+20%"),
        (1.25, "+25%"),
        (1.50, "+50%"),
        (2.00, "+100%"),
        (3.00, "+200%"),
        (5.00, "+400%"),
    ]

    for r, label in ratios:
        cp_il = il_constant_product(r)
        clmm_il_val, status = il_clmm(r, range_lower, range_upper)

        status_display = {
            "in_range": "In Range",
            "below_range": "BELOW (100% X)",
            "above_range": "ABOVE (100% Y)",
        }[status]

        print(
            f"  {label:>14}  {r:>6.2f}  {cp_il * 100:>8.2f}%  "
            f"{clmm_il_val * 100:>8.2f}%  {status_display:>14}"
        )

    print("=" * 75)
    print(
        f"  CLMM amplifies IL by ~{cf:.1f}x within range.\n"
        f"  Outside range: position is 100% one token (max directional IL).\n"
    )


def print_specific_scenario(
    initial_price: float,
    new_price: float,
    deposit: float,
) -> None:
    """Print detailed analysis for a specific price scenario.

    Args:
        initial_price: Price at deposit time.
        new_price: Current or projected price.
        deposit: Deposit amount in quote currency.
    """
    result = lp_vs_hold_values(initial_price, new_price, deposit)

    print(f"\n{'=' * 55}")
    print("  LP vs HOLD — Specific Scenario Analysis")
    print(f"{'=' * 55}")
    print(f"  Initial Price:    ${initial_price:,.2f}")
    print(f"  New Price:        ${new_price:,.2f}")
    print(f"  Price Ratio:      {result['price_ratio']:.4f}x")
    print(f"  Deposit:          ${deposit:,.2f}")
    print(f"{'─' * 55}")
    print(f"  Hold Value:       ${result['hold_value']:,.2f}")
    print(f"  LP Value:         ${result['lp_value']:,.2f}")
    print(f"  Impermanent Loss: {result['il_pct']:.4f}% (${result['il_abs']:,.2f})")
    print(f"{'─' * 55}")

    # Breakeven fee analysis
    daily_vol_estimates = [0.03, 0.05, 0.07, 0.10]
    print("  Breakeven Daily Fee Rates by Volatility:")
    for vol in daily_vol_estimates:
        bfr = breakeven_daily_fee_rate(vol)
        annual = bfr * 365 * 100
        print(
            f"    σ={vol * 100:.0f}%/day → need {bfr * 100:.4f}%/day "
            f"({annual:.1f}% APR)"
        )
    print(f"{'=' * 55}\n")


def print_breakeven_table() -> None:
    """Print breakeven fee rate table for various volatility levels."""
    print(f"\n{'=' * 70}")
    print("  BREAKEVEN FEE RATE TABLE")
    print("  Minimum daily fee rate (as % of deposit) to offset expected IL")
    print(f"{'=' * 70}")
    print(
        f"  {'Daily Vol':>10}  {'E[Daily IL]':>12}  "
        f"{'Breakeven Fee':>14}  {'Annualized':>12}"
    )
    print("-" * 70)

    vols = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50]
    for vol in vols:
        eil = vol ** 2 / 8.0
        annual = eil * 365 * 100
        print(
            f"  {vol * 100:>9.0f}%  {eil * 100:>11.4f}%  "
            f"{eil * 100:>13.4f}%  {annual:>11.1f}%"
        )

    print(f"{'=' * 70}")
    print("  E[Daily IL] ≈ σ²/8 (small-move approximation)")
    print("  Annualized = Daily * 365 (does not compound)\n")


def run_demo() -> None:
    """Run the full demo showing all calculator capabilities."""
    print("\n" + "#" * 70)
    print("#  IMPERMANENT LOSS CALCULATOR — DEMO MODE")
    print("#" * 70)

    # 1. Full IL table
    print_il_table()

    # 2. Specific scenario
    print_specific_scenario(
        initial_price=150.0,
        new_price=225.0,
        deposit=10000.0,
    )

    # 3. CLMM comparison
    print_clmm_comparison(range_pct=20.0)
    print_clmm_comparison(range_pct=10.0)
    print_clmm_comparison(range_pct=50.0)

    # 4. Breakeven table
    print_breakeven_table()

    print("\nDemo complete.")


# ── CLI ─────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Impermanent Loss Calculator for AMM Liquidity Pools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python il_calculator.py --demo\n"
            "  python il_calculator.py --ratio 2.0\n"
            "  python il_calculator.py --initial-price 150 --new-price 200 --deposit 10000\n"
            "  python il_calculator.py --clmm --range-pct 20 --ratio 1.5\n"
            "  python il_calculator.py --table\n"
            "  python il_calculator.py --breakeven\n"
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run full demo with tables and comparisons",
    )
    parser.add_argument(
        "--ratio",
        type=float,
        help="Price ratio (P_new / P_initial) to compute IL for",
    )
    parser.add_argument(
        "--initial-price",
        type=float,
        help="Initial price of the base token",
    )
    parser.add_argument(
        "--new-price",
        type=float,
        help="New price of the base token",
    )
    parser.add_argument(
        "--deposit",
        type=float,
        default=10000.0,
        help="Deposit size in quote currency (default: 10000)",
    )
    parser.add_argument(
        "--clmm",
        action="store_true",
        help="Also compute CLMM IL for the given ratio",
    )
    parser.add_argument(
        "--range-pct",
        type=float,
        default=20.0,
        help="CLMM range as +/- percent (default: 20 for ±20%%)",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="Print the full IL table",
    )
    parser.add_argument(
        "--breakeven",
        action="store_true",
        help="Print the breakeven fee rate table",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the IL calculator."""
    args = parse_args()

    if args.demo:
        run_demo()
        return

    # If no specific action requested, show table + breakeven
    if not any([args.ratio, args.initial_price, args.table, args.breakeven, args.clmm]):
        print("No arguments provided. Use --demo for full demo or --help for options.")
        print_il_table()
        return

    if args.table:
        print_il_table()

    if args.breakeven:
        print_breakeven_table()

    # Compute for specific ratio
    ratio: Optional[float] = args.ratio
    if args.initial_price and args.new_price:
        ratio = args.new_price / args.initial_price

    if ratio is not None:
        try:
            il = il_constant_product(ratio)
            print(f"\n  Price ratio: {ratio:.4f}x")
            print(f"  Constant-product IL: {il * 100:.4f}%")

            if args.initial_price and args.new_price:
                print_specific_scenario(args.initial_price, args.new_price, args.deposit)

            if args.clmm:
                range_lower = 1.0 - args.range_pct / 100.0
                range_upper = 1.0 + args.range_pct / 100.0
                clmm_il_val, status = il_clmm(ratio, range_lower, range_upper)
                cf = concentration_factor(range_lower, range_upper)
                print(
                    f"  CLMM IL (±{args.range_pct:.0f}% range): "
                    f"{clmm_il_val * 100:.4f}% [{status}]"
                )
                print(f"  Concentration factor: {cf:.1f}x")

        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    if args.clmm and ratio is None:
        print_clmm_comparison(args.range_pct)


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
