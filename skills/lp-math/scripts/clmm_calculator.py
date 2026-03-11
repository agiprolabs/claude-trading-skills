#!/usr/bin/env python3
"""Concentrated Liquidity (CLMM) Calculator.

Calculates position values, capital efficiency, liquidity amounts, and fee
earnings for concentrated liquidity AMM positions (Orca Whirlpool, Raydium CLMM,
Uniswap V3-style).

Usage:
    python scripts/clmm_calculator.py
    python scripts/clmm_calculator.py --demo

Dependencies:
    None (pure math, standard library only)

Environment Variables:
    None required
"""

import argparse
import math
from dataclasses import dataclass
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class CLMMPosition:
    """A concentrated liquidity position."""

    liquidity: float
    price_lower: float
    price_upper: float
    entry_price: float

    @property
    def tick_lower(self) -> int:
        """Lower tick boundary."""
        return price_to_tick(self.price_lower)

    @property
    def tick_upper(self) -> int:
        """Upper tick boundary."""
        return price_to_tick(self.price_upper)

    @property
    def range_width_pct(self) -> float:
        """Range width as percentage of midpoint."""
        mid = (self.price_lower + self.price_upper) / 2
        return (self.price_upper - self.price_lower) / mid * 100


@dataclass
class PositionValue:
    """Value of a CLMM position at a given price."""

    price: float
    amount_x: float
    amount_y: float
    total_value_y: float
    in_range: bool
    pct_token_x: float
    pct_token_y: float


@dataclass
class RangeComparison:
    """Comparison of different range strategies."""

    label: str
    price_lower: float
    price_upper: float
    efficiency: float
    liquidity: float
    value_at_entry: float
    value_at_minus10: float
    value_at_plus10: float
    il_at_minus10: float
    il_at_plus10: float
    fee_multiplier: float


# ── Core Math Functions ─────────────────────────────────────────────


def price_to_tick(price: float) -> int:
    """Convert price to tick index.

    Args:
        price: The price to convert.

    Returns:
        Tick index (rounded to nearest integer).

    Raises:
        ValueError: If price is non-positive.
    """
    if price <= 0:
        raise ValueError(f"Price must be positive, got {price}")
    return round(math.log(price) / math.log(1.0001))


def tick_to_price(tick: int) -> float:
    """Convert tick index to price.

    Args:
        tick: The tick index.

    Returns:
        Price at the given tick.
    """
    return 1.0001 ** tick


def capital_efficiency(price_lower: float, price_upper: float) -> float:
    """Calculate capital efficiency ratio vs full-range position.

    A position in range [P_lower, P_upper] provides the same market depth
    as a full-range position with `efficiency` times more capital.

    Args:
        price_lower: Lower bound of the price range.
        price_upper: Upper bound of the price range.

    Returns:
        Capital efficiency multiplier.

    Raises:
        ValueError: If price_lower >= price_upper or either is non-positive.
    """
    if price_lower <= 0 or price_upper <= 0:
        raise ValueError("Prices must be positive")
    if price_lower >= price_upper:
        raise ValueError("price_lower must be less than price_upper")

    ratio = math.sqrt(price_upper / price_lower)
    if ratio <= 1:
        return float("inf")
    return ratio / (ratio - 1)


def liquidity_from_amounts(
    price_current: float,
    price_lower: float,
    price_upper: float,
    amount_x: float,
    amount_y: float,
) -> float:
    """Calculate liquidity L from deposit amounts.

    Args:
        price_current: Current pool price (Y per X).
        price_lower: Lower price bound.
        price_upper: Upper price bound.
        amount_x: Amount of token X to deposit.
        amount_y: Amount of token Y to deposit.

    Returns:
        Liquidity value L. Uses min(L_from_x, L_from_y) for balanced deposit.

    Raises:
        ValueError: If prices are invalid.
    """
    if price_lower >= price_upper:
        raise ValueError("price_lower must be less than price_upper")
    if price_current <= 0:
        raise ValueError("Current price must be positive")

    sqrt_p = math.sqrt(price_current)
    sqrt_pa = math.sqrt(price_lower)
    sqrt_pb = math.sqrt(price_upper)

    if price_current <= price_lower:
        # All token X
        if amount_x <= 0:
            return 0.0
        return amount_x / (1 / sqrt_pa - 1 / sqrt_pb)
    elif price_current >= price_upper:
        # All token Y
        if amount_y <= 0:
            return 0.0
        return amount_y / (sqrt_pb - sqrt_pa)
    else:
        # In range: both tokens
        l_from_x = amount_x / (1 / sqrt_p - 1 / sqrt_pb) if amount_x > 0 else float("inf")
        l_from_y = amount_y / (sqrt_p - sqrt_pa) if amount_y > 0 else float("inf")
        return min(l_from_x, l_from_y)


def amounts_from_liquidity(
    liquidity: float,
    price_current: float,
    price_lower: float,
    price_upper: float,
) -> tuple[float, float]:
    """Calculate token amounts for a given liquidity and price.

    Args:
        liquidity: The liquidity value L.
        price_current: Current pool price.
        price_lower: Lower price bound.
        price_upper: Upper price bound.

    Returns:
        Tuple of (amount_x, amount_y).
    """
    sqrt_p = math.sqrt(price_current)
    sqrt_pa = math.sqrt(price_lower)
    sqrt_pb = math.sqrt(price_upper)

    if price_current <= price_lower:
        amount_x = liquidity * (1 / sqrt_pa - 1 / sqrt_pb)
        amount_y = 0.0
    elif price_current >= price_upper:
        amount_x = 0.0
        amount_y = liquidity * (sqrt_pb - sqrt_pa)
    else:
        amount_x = liquidity * (1 / sqrt_p - 1 / sqrt_pb)
        amount_y = liquidity * (sqrt_p - sqrt_pa)

    return amount_x, amount_y


def position_value(
    liquidity: float,
    price_current: float,
    price_lower: float,
    price_upper: float,
) -> PositionValue:
    """Calculate the full value of a CLMM position.

    Args:
        liquidity: The liquidity value L.
        price_current: Current pool price (Y per X).
        price_lower: Lower price bound.
        price_upper: Upper price bound.

    Returns:
        PositionValue with token amounts and total value.
    """
    amount_x, amount_y = amounts_from_liquidity(
        liquidity, price_current, price_lower, price_upper
    )

    total_y = amount_x * price_current + amount_y
    in_range = price_lower < price_current < price_upper

    pct_x = (amount_x * price_current / total_y * 100) if total_y > 0 else 0
    pct_y = (amount_y / total_y * 100) if total_y > 0 else 0

    return PositionValue(
        price=price_current,
        amount_x=amount_x,
        amount_y=amount_y,
        total_value_y=total_y,
        in_range=in_range,
        pct_token_x=pct_x,
        pct_token_y=pct_y,
    )


def impermanent_loss_pct(price_ratio: float) -> float:
    """Calculate impermanent loss for a full-range position.

    Args:
        price_ratio: New price / entry price.

    Returns:
        IL as a positive percentage (e.g., 5.72 for 5.72% loss).
    """
    if price_ratio <= 0:
        return 100.0
    il = 2 * math.sqrt(price_ratio) / (1 + price_ratio) - 1
    return abs(il) * 100


def clmm_impermanent_loss(
    liquidity: float,
    entry_price: float,
    current_price: float,
    price_lower: float,
    price_upper: float,
) -> float:
    """Calculate impermanent loss for a CLMM position.

    Compares position value to holding the initial tokens.

    Args:
        liquidity: Position liquidity L.
        entry_price: Price when position was opened.
        current_price: Current price.
        price_lower: Lower price bound.
        price_upper: Upper price bound.

    Returns:
        IL as a percentage (positive = loss vs holding).
    """
    # Value at entry
    entry_x, entry_y = amounts_from_liquidity(
        liquidity, entry_price, price_lower, price_upper
    )
    hold_value = entry_x * current_price + entry_y

    # Current position value
    current_x, current_y = amounts_from_liquidity(
        liquidity, current_price, price_lower, price_upper
    )
    position_value_now = current_x * current_price + current_y

    if hold_value == 0:
        return 0.0
    return (1 - position_value_now / hold_value) * 100


def estimate_fee_earnings(
    your_liquidity: float,
    total_liquidity_in_range: float,
    daily_volume: float,
    fee_rate: float,
    days: int = 1,
) -> float:
    """Estimate fee earnings for a CLMM position.

    Args:
        your_liquidity: Your L in the active range.
        total_liquidity_in_range: Total L from all LPs in the active range.
        daily_volume: Average daily trading volume (in token Y terms).
        fee_rate: Fee rate as decimal (e.g., 0.003 for 0.3%).
        days: Number of days to estimate.

    Returns:
        Estimated fee earnings in token Y terms.
    """
    if total_liquidity_in_range == 0:
        return 0.0
    your_share = your_liquidity / total_liquidity_in_range
    daily_fees = daily_volume * fee_rate
    return daily_fees * your_share * days


# ── Display Functions ───────────────────────────────────────────────


def print_position_value(pv: PositionValue, token_x: str, token_y: str) -> None:
    """Print position value details."""
    status = "IN RANGE" if pv.in_range else "OUT OF RANGE"
    print(f"  Price: {pv.price:,.4f} {token_y}/{token_x} [{status}]")
    print(f"    {token_x}: {pv.amount_x:>12,.6f}  ({pv.pct_token_x:>5.1f}%)")
    print(f"    {token_y}: {pv.amount_y:>12,.4f}  ({pv.pct_token_y:>5.1f}%)")
    print(f"    Total ({token_y}): {pv.total_value_y:>12,.4f}")


def print_range_comparison_table(comparisons: list[RangeComparison], token_y: str) -> None:
    """Print a comparison table of range strategies."""
    print(f"\n  {'Strategy':<18} {'Range':>16} {'Efficiency':>11} "
          f"{'Fee Mult':>9} {'IL@-10%':>8} {'IL@+10%':>8}")
    print(f"  {'─' * 18} {'─' * 16} {'─' * 11} {'─' * 9} {'─' * 8} {'─' * 8}")
    for c in comparisons:
        range_str = f"{c.price_lower:.1f}–{c.price_upper:.1f}"
        print(f"  {c.label:<18} {range_str:>16} {c.efficiency:>10.1f}x "
              f"{c.fee_multiplier:>8.1f}x {c.il_at_minus10:>7.2f}% {c.il_at_plus10:>7.2f}%")


# ── Demo Mode ───────────────────────────────────────────────────────


def run_demo() -> None:
    """Run a demonstration of CLMM calculations."""
    print("=" * 65)
    print("  Concentrated Liquidity (CLMM) Calculator — Demo")
    print("=" * 65)

    token_x = "SOL"
    token_y = "USDC"
    current_price = 100.0  # 100 USDC per SOL
    deposit_value = 10_000.0  # $10,000 total deposit

    # Step 1: Capital efficiency comparison
    print("\n\n--- STEP 1: Capital Efficiency by Range Width ---")
    print(f"\n  Base price: {current_price} {token_y}/{token_x}")
    print(f"  Deposit value: {deposit_value:,.0f} {token_y}\n")

    ranges = [
        ("Ultra-tight ±2%", 0.02),
        ("Tight ±5%", 0.05),
        ("Medium ±10%", 0.10),
        ("Wide ±25%", 0.25),
        ("Very wide ±50%", 0.50),
        ("Extra wide ±90%", 0.90),
    ]

    print(f"  {'Range':<22} {'Lower':>8} {'Upper':>8} {'Efficiency':>11}")
    print(f"  {'─' * 22} {'─' * 8} {'─' * 8} {'─' * 11}")

    for label, pct in ranges:
        p_low = current_price * (1 - pct)
        p_high = current_price * (1 + pct)
        eff = capital_efficiency(p_low, p_high)
        print(f"  {label:<22} {p_low:>8.2f} {p_high:>8.2f} {eff:>10.1f}x")

    # Step 2: Position value at different prices
    print("\n\n--- STEP 2: Position Value Across Prices ---")

    # Create a position with ±25% range
    p_lower = 75.0
    p_upper = 125.0

    # Determine liquidity from a $10,000 deposit at current price
    # Half in each token at current price
    deposit_x = deposit_value / 2 / current_price  # 50 SOL
    deposit_y = deposit_value / 2  # 5,000 USDC

    liq = liquidity_from_amounts(current_price, p_lower, p_upper, deposit_x, deposit_y)
    print(f"\n  Position: L = {liq:,.2f}")
    print(f"  Range: [{p_lower:.2f}, {p_upper:.2f}] {token_y}/{token_x}")
    print(f"  Deposit: {deposit_x:,.4f} {token_x} + {deposit_y:,.2f} {token_y}")

    prices_to_check = [50, 60, 70, 75, 80, 90, 100, 110, 120, 125, 130, 140, 150]
    print(f"\n  {'Price':>8} {'Status':>12} {token_x + ' Amount':>14} "
          f"{token_y + ' Amount':>14} {'Total (' + token_y + ')':>14} {'IL':>8}")
    print(f"  {'─' * 8} {'─' * 12} {'─' * 14} {'─' * 14} {'─' * 14} {'─' * 8}")

    for p in prices_to_check:
        pv = position_value(liq, p, p_lower, p_upper)
        il = clmm_impermanent_loss(liq, current_price, p, p_lower, p_upper)
        status = "IN RANGE" if pv.in_range else "out"
        print(f"  {p:>8.2f} {status:>12} {pv.amount_x:>14.4f} "
              f"{pv.amount_y:>14.2f} {pv.total_value_y:>14.2f} {il:>7.2f}%")

    # Step 3: Range strategy comparison
    print("\n\n--- STEP 3: Range Strategy Comparison ---")
    print(f"  All positions: {deposit_value:,.0f} {token_y} deposit at "
          f"price {current_price} {token_y}/{token_x}")

    comparisons: list[RangeComparison] = []
    strategies = [
        ("Tight ±5%", 0.05),
        ("Medium ±10%", 0.10),
        ("Wide ±25%", 0.25),
        ("Very Wide ±50%", 0.50),
        ("Full Range ±99%", 0.99),
    ]

    for label, pct in strategies:
        pl = current_price * (1 - pct)
        pu = current_price * (1 + pct)
        eff = capital_efficiency(pl, pu)

        dep_x = deposit_value / 2 / current_price
        dep_y = deposit_value / 2
        l = liquidity_from_amounts(current_price, pl, pu, dep_x, dep_y)

        val_entry = position_value(l, current_price, pl, pu).total_value_y
        val_m10 = position_value(l, current_price * 0.9, pl, pu).total_value_y
        val_p10 = position_value(l, current_price * 1.1, pl, pu).total_value_y

        il_m10 = clmm_impermanent_loss(l, current_price, current_price * 0.9, pl, pu)
        il_p10 = clmm_impermanent_loss(l, current_price, current_price * 1.1, pl, pu)

        comparisons.append(RangeComparison(
            label=label,
            price_lower=pl,
            price_upper=pu,
            efficiency=eff,
            liquidity=l,
            value_at_entry=val_entry,
            value_at_minus10=val_m10,
            value_at_plus10=val_p10,
            il_at_minus10=il_m10,
            il_at_plus10=il_p10,
            fee_multiplier=eff,  # Fee multiplier equals efficiency
        ))

    print_range_comparison_table(comparisons, token_y)

    # Step 4: Fee earnings estimation
    print("\n\n--- STEP 4: Fee Earnings Estimation ---")
    print(f"  Assumptions:")
    print(f"    Daily volume: $500,000")
    print(f"    Fee tier: 0.30%")
    print(f"    Your deposit: ${deposit_value:,.0f}")

    daily_volume = 500_000
    fee_rate = 0.003

    print(f"\n  {'Strategy':<18} {'Your L':>12} {'Daily Fees':>12} "
          f"{'Monthly':>12} {'Ann. APR':>10}")
    print(f"  {'─' * 18} {'─' * 12} {'─' * 12} {'─' * 12} {'─' * 10}")

    for c in comparisons:
        # Assume total liquidity in range = 10x yours
        total_l = c.liquidity * 10
        daily_fees = estimate_fee_earnings(
            c.liquidity, total_l, daily_volume, fee_rate
        )
        monthly = daily_fees * 30
        apr = (daily_fees * 365 / deposit_value) * 100
        print(f"  {c.label:<18} {c.liquidity:>12,.0f} ${daily_fees:>10,.2f} "
              f"${monthly:>10,.2f} {apr:>9.1f}%")

    print("\n  Note: Tighter ranges earn more fees per $ when in range,")
    print("  but earn zero fees when price moves outside the range.")

    # Step 5: Tick math demonstration
    print("\n\n--- STEP 5: Tick Math ---")
    print(f"\n  Price → Tick → Back to Price:")
    test_prices = [50.0, 75.0, 100.0, 125.0, 150.0, 200.0]
    print(f"  {'Price':>10} {'Tick':>10} {'Reconstructed':>14} {'Error':>10}")
    print(f"  {'─' * 10} {'─' * 10} {'─' * 14} {'─' * 10}")
    for p in test_prices:
        t = price_to_tick(p)
        p_back = tick_to_price(t)
        error = abs(p - p_back) / p * 100
        print(f"  {p:>10.4f} {t:>10d} {p_back:>14.4f} {error:>9.4f}%")

    # Step 6: Deposit amount calculation
    print("\n\n--- STEP 6: Required Deposit Amounts ---")
    print(f"  Target: $10,000 total position value")
    print(f"  Current price: {current_price} {token_y}/{token_x}\n")

    for label, pct in [("±5%", 0.05), ("±10%", 0.10), ("±25%", 0.25), ("±50%", 0.50)]:
        pl = current_price * (1 - pct)
        pu = current_price * (1 + pct)

        # Calculate amounts for a balanced deposit
        # Start with equal-value split and compute L
        dx = deposit_value / 2 / current_price
        dy = deposit_value / 2
        l = liquidity_from_amounts(current_price, pl, pu, dx, dy)

        # Get the actual balanced amounts from L
        actual_x, actual_y = amounts_from_liquidity(l, current_price, pl, pu)
        actual_value = actual_x * current_price + actual_y

        print(f"  Range {label} [{pl:.2f}–{pu:.2f}]:")
        print(f"    Deposit: {actual_x:,.4f} {token_x} ({actual_x * current_price:,.2f} {token_y}) "
              f"+ {actual_y:,.2f} {token_y}")
        print(f"    Total value: {actual_value:,.2f} {token_y}")
        print(f"    Split: {actual_x * current_price / actual_value * 100:.1f}% "
              f"{token_x} / {actual_y / actual_value * 100:.1f}% {token_y}")
        print()

    print("=" * 65)
    print("  Demo Complete")
    print("=" * 65)


# ── Interactive Mode ────────────────────────────────────────────────


def run_interactive() -> None:
    """Run interactive CLMM calculator."""
    print("=" * 65)
    print("  Concentrated Liquidity Calculator — Interactive Mode")
    print("=" * 65)

    print("\nConfigure your position:")
    try:
        token_x = input("  Token X name [SOL]: ").strip() or "SOL"
        token_y = input("  Token Y name [USDC]: ").strip() or "USDC"
        price = float(input(f"  Current price ({token_y}/{token_x}) [100]: ").strip() or "100")
        p_lower = float(input(f"  Range lower ({token_y}) [75]: ").strip() or "75")
        p_upper = float(input(f"  Range upper ({token_y}) [125]: ").strip() or "125")
        amount_x = float(input(f"  Deposit {token_x} [50]: ").strip() or "50")
        amount_y = float(input(f"  Deposit {token_y} [5000]: ").strip() or "5000")
    except (ValueError, EOFError):
        print("Invalid input, using defaults.")
        token_x, token_y = "SOL", "USDC"
        price, p_lower, p_upper = 100, 75, 125
        amount_x, amount_y = 50, 5000

    liq = liquidity_from_amounts(price, p_lower, p_upper, amount_x, amount_y)
    eff = capital_efficiency(p_lower, p_upper)

    print(f"\n  Liquidity: {liq:,.2f}")
    print(f"  Capital efficiency: {eff:.1f}x")

    pv = position_value(liq, price, p_lower, p_upper)
    print_position_value(pv, token_x, token_y)

    print("\nCommands:")
    print("  price <p>     — Show position value at price p")
    print("  sweep         — Show values across price range")
    print("  fees <vol>    — Estimate daily fees for given volume")
    print("  efficiency    — Show capital efficiency")
    print("  quit          — Exit")

    while True:
        try:
            cmd = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd:
            continue

        parts = cmd.split()
        action = parts[0]

        try:
            if action in ("quit", "q"):
                break
            elif action == "price" and len(parts) == 2:
                p = float(parts[1])
                pv = position_value(liq, p, p_lower, p_upper)
                il = clmm_impermanent_loss(liq, price, p, p_lower, p_upper)
                print_position_value(pv, token_x, token_y)
                print(f"    IL vs holding: {il:.2f}%")
            elif action == "sweep":
                step = (p_upper - p_lower) / 10
                for i in range(15):
                    p = p_lower - 2 * step + i * step
                    if p <= 0:
                        continue
                    pv = position_value(liq, p, p_lower, p_upper)
                    status = "*" if pv.in_range else " "
                    print(f"  {status} {p:>8.2f}: {pv.amount_x:>10.4f} {token_x} + "
                          f"{pv.amount_y:>10.2f} {token_y} = "
                          f"{pv.total_value_y:>10.2f} total")
            elif action == "fees" and len(parts) == 2:
                vol = float(parts[1])
                total_l = liq * 10  # Assume 10x
                daily = estimate_fee_earnings(liq, total_l, vol, 0.003)
                print(f"  Daily fees: ${daily:,.2f} (assuming 10% of range liquidity)")
                print(f"  Monthly:    ${daily * 30:,.2f}")
                print(f"  Annual APR: {daily * 365 / pv.total_value_y * 100:.1f}%")
            elif action == "efficiency":
                print(f"  Efficiency: {eff:.1f}x vs full range")
                print(f"  Range: [{p_lower:.2f}, {p_upper:.2f}]")
                print(f"  Width: {(p_upper - p_lower) / ((p_upper + p_lower) / 2) * 100:.1f}%")
            else:
                print("  Unknown command. Type 'quit' to exit.")
        except (ValueError, ZeroDivisionError) as e:
            print(f"  Error: {e}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Concentrated Liquidity (CLMM) Calculator"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode with pre-configured examples",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        run_interactive()


if __name__ == "__main__":
    main()
