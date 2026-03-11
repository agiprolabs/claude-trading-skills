#!/usr/bin/env python3
"""Bond pricing calculator with YTM, duration, and convexity analysis.

This is a STUB implementation providing core fixed income calculations
using only the Python standard library. No external dependencies required.

Usage:
    python scripts/bond_calculator.py --demo

Dependencies:
    None (uses only Python standard library math module)

Environment Variables:
    None required
"""

import argparse
import math
import sys
from typing import NamedTuple


# ── Data Structures ────────────────────────────────────────────────


class BondMetrics(NamedTuple):
    """Complete bond analysis result."""
    dirty_price: float
    current_yield: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float


# ── Bond Pricing ───────────────────────────────────────────────────


def bond_price(
    face: float,
    coupon_rate: float,
    ytm: float,
    periods: int,
    freq: int = 2,
) -> float:
    """Calculate bond price as present value of all cash flows.

    Args:
        face: Face (par) value of the bond.
        coupon_rate: Annual coupon rate (decimal, e.g., 0.05 for 5%).
        ytm: Yield to maturity (annual, decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year (1=annual, 2=semi-annual, 4=quarterly).

    Returns:
        Bond dirty price.

    Raises:
        ValueError: If inputs are invalid.
    """
    if face <= 0:
        raise ValueError(f"Face value must be positive, got {face}")
    if coupon_rate < 0:
        raise ValueError(f"Coupon rate must be non-negative, got {coupon_rate}")
    if periods <= 0:
        raise ValueError(f"Periods must be positive, got {periods}")
    if freq not in (1, 2, 4, 12):
        raise ValueError(f"Frequency must be 1, 2, 4, or 12, got {freq}")

    coupon = face * coupon_rate / freq
    y = ytm / freq

    if abs(y) < 1e-12:
        # Zero yield edge case: simple sum
        return coupon * periods + face

    pv_coupons = sum(coupon / (1 + y) ** t for t in range(1, periods + 1))
    pv_face = face / (1 + y) ** periods
    return pv_coupons + pv_face


def zero_coupon_price(face: float, ytm: float, years: float) -> float:
    """Price a zero-coupon bond.

    Args:
        face: Face value.
        ytm: Yield to maturity (annual, decimal, continuously compounded).
        years: Time to maturity in years.

    Returns:
        Zero-coupon bond price.
    """
    if face <= 0:
        raise ValueError(f"Face value must be positive, got {face}")
    if years <= 0:
        raise ValueError(f"Years must be positive, got {years}")
    return face * math.exp(-ytm * years)


# ── Yield to Maturity Solver ──────────────────────────────────────


def yield_to_maturity(
    price: float,
    face: float,
    coupon_rate: float,
    periods: int,
    freq: int = 2,
    tol: float = 1e-8,
    max_iter: int = 200,
) -> float:
    """Solve for yield to maturity using Newton's method.

    Args:
        price: Current bond price (dirty).
        face: Face (par) value.
        coupon_rate: Annual coupon rate (decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year.
        tol: Convergence tolerance.
        max_iter: Maximum iterations.

    Returns:
        Annual yield to maturity (decimal).

    Raises:
        ValueError: If solver does not converge.
    """
    if price <= 0:
        raise ValueError(f"Price must be positive, got {price}")

    coupon = face * coupon_rate / freq

    # Initial guess based on current yield approximation
    annual_coupon = face * coupon_rate
    ytm_guess = annual_coupon / price
    if ytm_guess <= 0:
        ytm_guess = 0.05  # fallback

    y = ytm_guess / freq  # periodic yield guess

    for iteration in range(max_iter):
        # Price as function of periodic yield
        pv = 0.0
        dpv = 0.0  # derivative of price w.r.t. y

        for t in range(1, periods + 1):
            discount = (1 + y) ** t
            pv += coupon / discount
            dpv -= t * coupon / ((1 + y) ** (t + 1))

        pv += face / (1 + y) ** periods
        dpv -= periods * face / ((1 + y) ** (periods + 1))

        diff = pv - price

        if abs(diff) < tol:
            return y * freq

        if abs(dpv) < 1e-15:
            raise ValueError("Derivative too small — solver stuck")

        y = y - diff / dpv

        # Guard against negative yields going too extreme
        if y < -0.5:
            y = -0.5
        if y > 2.0:
            y = 2.0

    raise ValueError(
        f"YTM solver did not converge after {max_iter} iterations. "
        f"Last estimate: {y * freq:.6f}"
    )


# ── Duration and Convexity ─────────────────────────────────────────


def macaulay_duration(
    face: float,
    coupon_rate: float,
    ytm: float,
    periods: int,
    freq: int = 2,
) -> float:
    """Calculate Macaulay duration in years.

    Macaulay duration is the weighted average time to receive cash flows,
    where weights are the present values of each cash flow.

    Args:
        face: Face value.
        coupon_rate: Annual coupon rate (decimal).
        ytm: Annual yield to maturity (decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year.

    Returns:
        Macaulay duration in years.
    """
    coupon = face * coupon_rate / freq
    y = ytm / freq
    price = bond_price(face, coupon_rate, ytm, periods, freq)

    weighted_sum = 0.0
    for t in range(1, periods + 1):
        pv_cf = coupon / (1 + y) ** t
        weighted_sum += (t / freq) * pv_cf

    # Add face value at maturity
    pv_face = face / (1 + y) ** periods
    weighted_sum += (periods / freq) * pv_face

    return weighted_sum / price


def modified_duration(
    face: float,
    coupon_rate: float,
    ytm: float,
    periods: int,
    freq: int = 2,
) -> float:
    """Calculate modified duration.

    Modified duration measures the percentage price change for a 1%
    change in yield: ΔP/P ≈ -D_mod * Δy

    Args:
        face: Face value.
        coupon_rate: Annual coupon rate (decimal).
        ytm: Annual yield to maturity (decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year.

    Returns:
        Modified duration in years.
    """
    mac_dur = macaulay_duration(face, coupon_rate, ytm, periods, freq)
    return mac_dur / (1 + ytm / freq)


def convexity(
    face: float,
    coupon_rate: float,
    ytm: float,
    periods: int,
    freq: int = 2,
) -> float:
    """Calculate bond convexity.

    Convexity measures the curvature of the price-yield relationship,
    providing a second-order correction to the duration approximation.

    Args:
        face: Face value.
        coupon_rate: Annual coupon rate (decimal).
        ytm: Annual yield to maturity (decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year.

    Returns:
        Convexity (in years squared, scaled by freq²).
    """
    coupon = face * coupon_rate / freq
    y = ytm / freq
    price = bond_price(face, coupon_rate, ytm, periods, freq)

    conv_sum = 0.0
    for t in range(1, periods + 1):
        cf = coupon
        if t == periods:
            cf += face
        conv_sum += t * (t + 1) * cf / (1 + y) ** (t + 2)

    return conv_sum / (price * freq ** 2)


# ── Full Analysis ──────────────────────────────────────────────────


def analyze_bond(
    face: float,
    coupon_rate: float,
    ytm: float,
    periods: int,
    freq: int = 2,
) -> BondMetrics:
    """Perform complete bond analysis.

    Args:
        face: Face value.
        coupon_rate: Annual coupon rate (decimal).
        ytm: Annual yield to maturity (decimal).
        periods: Number of coupon periods remaining.
        freq: Coupon frequency per year.

    Returns:
        BondMetrics with price, yield, duration, convexity, and DV01.
    """
    price = bond_price(face, coupon_rate, ytm, periods, freq)
    cur_yield = (face * coupon_rate) / price if price > 0 else 0.0
    mac_dur = macaulay_duration(face, coupon_rate, ytm, periods, freq)
    mod_dur = mac_dur / (1 + ytm / freq)
    conv = convexity(face, coupon_rate, ytm, periods, freq)
    dv01 = mod_dur * price * 0.0001  # dollar value of 1 basis point

    return BondMetrics(
        dirty_price=price,
        current_yield=cur_yield,
        macaulay_duration=mac_dur,
        modified_duration=mod_dur,
        convexity=conv,
        dv01=dv01,
    )


def price_change_estimate(
    mod_dur: float, conv: float, price: float, yield_change_bps: float
) -> float:
    """Estimate price change using duration and convexity.

    Args:
        mod_dur: Modified duration.
        conv: Convexity.
        price: Current bond price.
        yield_change_bps: Yield change in basis points (e.g., 50 for +50bp).

    Returns:
        Estimated dollar price change.
    """
    dy = yield_change_bps / 10000.0
    pct_change = -mod_dur * dy + 0.5 * conv * dy ** 2
    return price * pct_change


# ── Demo ────────────────────────────────────────────────────────────


def run_demo() -> None:
    """Run demonstration calculations showing all capabilities."""
    print("=" * 60)
    print("  Fixed Income Bond Calculator — STUB Demo")
    print("  For informational purposes only. Not financial advice.")
    print("=" * 60)

    # Example 1: Standard coupon bond
    face = 1000.0
    coupon_rate = 0.05   # 5% annual coupon
    ytm = 0.06           # 6% yield (bond trades at a discount)
    years = 10
    freq = 2             # semi-annual
    periods = years * freq

    print(f"\n--- Example 1: {coupon_rate:.0%} Coupon Bond, {years}-Year ---")
    print(f"  Face Value:     ${face:,.0f}")
    print(f"  Coupon Rate:    {coupon_rate:.2%} (semi-annual)")
    print(f"  YTM:            {ytm:.2%}")
    print(f"  Maturity:       {years} years ({periods} periods)")

    metrics = analyze_bond(face, coupon_rate, ytm, periods, freq)

    print(f"\n  Results:")
    print(f"  Price:              ${metrics.dirty_price:,.4f}")
    print(f"  Current Yield:      {metrics.current_yield:.4%}")
    print(f"  Macaulay Duration:  {metrics.macaulay_duration:.4f} years")
    print(f"  Modified Duration:  {metrics.modified_duration:.4f}")
    print(f"  Convexity:          {metrics.convexity:.4f}")
    print(f"  DV01:               ${metrics.dv01:.4f}")

    # Price change scenarios
    print(f"\n  Price Change Estimates:")
    for bps in [-100, -50, 50, 100]:
        delta_p = price_change_estimate(
            metrics.modified_duration, metrics.convexity,
            metrics.dirty_price, bps
        )
        new_price = metrics.dirty_price + delta_p
        print(f"    {bps:+d} bps: ${delta_p:+,.2f} → ${new_price:,.2f}")

    # Example 2: Premium bond
    print(f"\n--- Example 2: Premium Bond (coupon > yield) ---")
    ytm2 = 0.03
    metrics2 = analyze_bond(face, coupon_rate, ytm2, periods, freq)
    print(f"  {coupon_rate:.0%} coupon, {ytm2:.0%} yield")
    print(f"  Price:              ${metrics2.dirty_price:,.4f} (premium)")
    print(f"  Modified Duration:  {metrics2.modified_duration:.4f}")

    # Example 3: Zero coupon bond
    print(f"\n--- Example 3: Zero-Coupon Bond ---")
    zc_face = 1000.0
    zc_ytm = 0.04
    zc_years = 5.0
    zc_price = zero_coupon_price(zc_face, zc_ytm, zc_years)
    print(f"  Face: ${zc_face:,.0f}, Yield: {zc_ytm:.0%}, Maturity: {zc_years:.0f} years")
    print(f"  Price: ${zc_price:,.4f}")
    print(f"  Duration: {zc_years:.1f} years (always equals maturity for zeros)")

    # Example 4: YTM solver
    print(f"\n--- Example 4: YTM Solver ---")
    known_price = 925.0
    solved_ytm = yield_to_maturity(known_price, face, coupon_rate, periods, freq)
    verify_price = bond_price(face, coupon_rate, solved_ytm, periods, freq)
    print(f"  Given price: ${known_price:,.2f}")
    print(f"  Solved YTM:  {solved_ytm:.6%}")
    print(f"  Verify price: ${verify_price:,.4f}")
    print(f"  Error:        ${abs(verify_price - known_price):.6f}")

    # Example 5: DeFi rate comparison context
    print(f"\n--- DeFi Lending Rate Context ---")
    print(f"  (Planned feature — stub placeholder)")
    print(f"  Traditional 10Y bond yield:  ~{ytm:.1%}")
    print(f"  Solana lending rates:        ~5-15% variable APY")
    print(f"  Key difference: DeFi rates are variable and")
    print(f"  change with pool utilization, while bonds pay")
    print(f"  fixed coupons. Duration analysis helps compare")
    print(f"  the interest rate risk of each approach.")

    print(f"\n{'=' * 60}")
    print(f"  Demo complete. All calculations are for illustration only.")
    print(f"{'=' * 60}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(
        description="Bond pricing calculator (STUB)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demonstration with example calculations",
    )
    parser.add_argument("--face", type=float, default=1000.0, help="Face value (default: 1000)")
    parser.add_argument("--coupon", type=float, help="Annual coupon rate (decimal, e.g., 0.05)")
    parser.add_argument("--ytm", type=float, help="Yield to maturity (decimal, e.g., 0.06)")
    parser.add_argument("--years", type=float, help="Years to maturity")
    parser.add_argument("--freq", type=int, default=2, help="Coupon frequency (default: 2)")
    parser.add_argument(
        "--solve-ytm", type=float, metavar="PRICE",
        help="Solve for YTM given this bond price"
    )

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if args.solve_ytm is not None:
        if not all([args.coupon is not None, args.years]):
            print("Error: --coupon and --years required for --solve-ytm")
            sys.exit(1)
        periods = int(args.years * args.freq)
        solved = yield_to_maturity(args.solve_ytm, args.face, args.coupon, periods, args.freq)
        print(f"Solved YTM: {solved:.6%}")
        return

    if not all([args.coupon is not None, args.ytm is not None, args.years]):
        print("Error: --coupon, --ytm, and --years are required (or use --demo)")
        parser.print_help()
        sys.exit(1)

    periods = int(args.years * args.freq)
    metrics = analyze_bond(args.face, args.coupon, args.ytm, periods, args.freq)

    print(f"\nBond Analysis")
    print(f"  Price:              ${metrics.dirty_price:,.4f}")
    print(f"  Current Yield:      {metrics.current_yield:.4%}")
    print(f"  Macaulay Duration:  {metrics.macaulay_duration:.4f} years")
    print(f"  Modified Duration:  {metrics.modified_duration:.4f}")
    print(f"  Convexity:          {metrics.convexity:.4f}")
    print(f"  DV01:               ${metrics.dv01:.4f}")


if __name__ == "__main__":
    main()
