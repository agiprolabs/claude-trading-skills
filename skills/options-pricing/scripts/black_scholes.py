#!/usr/bin/env python3
"""Black-Scholes option pricing calculator with Greeks and implied volatility solver.

This is a STUB implementation providing core Black-Scholes functionality
using only the Python standard library. No external dependencies required.

Usage:
    python scripts/black_scholes.py --demo

Dependencies:
    None (uses only Python standard library math module)

Environment Variables:
    None required
"""

import argparse
import math
import sys
from typing import NamedTuple


# ── Standard Normal Distribution ────────────────────────────────────
# Pure Python implementations to avoid scipy dependency.


def _norm_cdf(x: float) -> float:
    """Cumulative distribution function for the standard normal distribution.

    Uses the Abramowitz and Stegun approximation (formula 26.2.17)
    with maximum error of 7.5e-8.

    Args:
        x: Value to evaluate.

    Returns:
        P(Z <= x) for Z ~ N(0,1).
    """
    if x < -10.0:
        return 0.0
    if x > 10.0:
        return 1.0

    sign = 1.0
    if x < 0:
        sign = -1.0
        x = -x

    t = 1.0 / (1.0 + 0.2316419 * x)
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    pdf = d * math.exp(-0.5 * x * x)

    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
            + t * (-1.821255978 + t * 1.330274429))))
    cdf = 1.0 - pdf * poly

    if sign < 0:
        cdf = 1.0 - cdf

    return cdf


def _norm_pdf(x: float) -> float:
    """Probability density function for the standard normal distribution.

    Args:
        x: Value to evaluate.

    Returns:
        Density at x for Z ~ N(0,1).
    """
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ── Data Structures ────────────────────────────────────────────────


class OptionPrice(NamedTuple):
    """Result of Black-Scholes pricing."""
    call: float
    put: float


class Greeks(NamedTuple):
    """Option Greeks for a single option."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class FullResult(NamedTuple):
    """Complete pricing result with price and Greeks."""
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


# ── Black-Scholes Pricing ──────────────────────────────────────────


def _compute_d1_d2(
    S: float, K: float, T: float, r: float, sigma: float
) -> tuple[float, float]:
    """Compute d1 and d2 parameters for Black-Scholes.

    Args:
        S: Current underlying price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        sigma: Volatility (annualized, decimal).

    Returns:
        Tuple of (d1, d2).

    Raises:
        ValueError: If inputs are invalid.
    """
    if S <= 0:
        raise ValueError(f"Underlying price must be positive, got {S}")
    if K <= 0:
        raise ValueError(f"Strike price must be positive, got {K}")
    if T <= 0:
        raise ValueError(f"Time to expiry must be positive, got {T}")
    if sigma <= 0:
        raise ValueError(f"Volatility must be positive, got {sigma}")

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2


def price_option(
    S: float, K: float, T: float, r: float, sigma: float
) -> OptionPrice:
    """Price European call and put options using Black-Scholes.

    Args:
        S: Current underlying price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal form, e.g., 0.05 for 5%).
        sigma: Volatility (annualized, decimal form, e.g., 0.80 for 80%).

    Returns:
        OptionPrice with call and put values.

    Raises:
        ValueError: If inputs are invalid.
    """
    d1, d2 = _compute_d1_d2(S, K, T, r, sigma)
    discount = math.exp(-r * T)

    call = S * _norm_cdf(d1) - K * discount * _norm_cdf(d2)
    put = K * discount * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    return OptionPrice(call=call, put=put)


def compute_greeks(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call"
) -> Greeks:
    """Compute Black-Scholes Greeks for a European option.

    Args:
        S: Current underlying price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        sigma: Volatility (annualized, decimal).
        option_type: "call" or "put".

    Returns:
        Greeks named tuple with delta, gamma, theta, vega, rho.

    Raises:
        ValueError: If option_type is not "call" or "put".
    """
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got '{option_type}'")

    d1, d2 = _compute_d1_d2(S, K, T, r, sigma)
    sqrt_T = math.sqrt(T)
    discount = math.exp(-r * T)
    pdf_d1 = _norm_pdf(d1)

    # Gamma and vega are the same for calls and puts
    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * pdf_d1 * sqrt_T / 100.0  # per 1% vol move

    if option_type == "call":
        delta = _norm_cdf(d1)
        theta = (
            -(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
            - r * K * discount * _norm_cdf(d2)
        ) / 365.0  # per calendar day
        rho = K * T * discount * _norm_cdf(d2) / 100.0  # per 1% rate move
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (
            -(S * pdf_d1 * sigma) / (2.0 * sqrt_T)
            + r * K * discount * _norm_cdf(-d2)
        ) / 365.0  # per calendar day
        rho = -K * T * discount * _norm_cdf(-d2) / 100.0  # per 1% rate move

    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def full_pricing(
    S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call"
) -> FullResult:
    """Compute price and all Greeks in one call.

    Args:
        S: Current underlying price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        sigma: Volatility (annualized, decimal).
        option_type: "call" or "put".

    Returns:
        FullResult with price, delta, gamma, theta, vega, rho.
    """
    prices = price_option(S, K, T, r, sigma)
    greeks = compute_greeks(S, K, T, r, sigma, option_type)

    price = prices.call if option_type == "call" else prices.put

    return FullResult(
        price=price,
        delta=greeks.delta,
        gamma=greeks.gamma,
        theta=greeks.theta,
        vega=greeks.vega,
        rho=greeks.rho,
    )


# ── Implied Volatility Solver ──────────────────────────────────────


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = "call",
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Solve for implied volatility using the bisection method.

    Given a market price for an option, find the volatility that makes
    the Black-Scholes price equal to the market price.

    Args:
        market_price: Observed market price of the option.
        S: Current underlying price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        option_type: "call" or "put".
        tol: Convergence tolerance.
        max_iter: Maximum iterations.

    Returns:
        Implied volatility (annualized, decimal).

    Raises:
        ValueError: If no solution found within bounds or max iterations.
    """
    if market_price <= 0:
        raise ValueError(f"Market price must be positive, got {market_price}")

    # Intrinsic value check
    discount = math.exp(-r * T)
    if option_type == "call":
        intrinsic = max(S - K * discount, 0.0)
    else:
        intrinsic = max(K * discount - S, 0.0)

    if market_price < intrinsic - tol:
        raise ValueError(
            f"Market price {market_price:.4f} is below intrinsic value {intrinsic:.4f}"
        )

    # Bisection bounds: 0.1% to 1000% annualized vol
    vol_low = 0.001
    vol_high = 10.0

    for _ in range(max_iter):
        vol_mid = (vol_low + vol_high) / 2.0
        prices = price_option(S, K, T, r, vol_mid)
        model_price = prices.call if option_type == "call" else prices.put

        diff = model_price - market_price

        if abs(diff) < tol:
            return vol_mid

        if diff > 0:
            vol_high = vol_mid
        else:
            vol_low = vol_mid

    raise ValueError(
        f"Implied volatility did not converge after {max_iter} iterations. "
        f"Last estimate: {vol_mid:.4f}, price diff: {diff:.6f}"
    )


# ── Demo ────────────────────────────────────────────────────────────


def run_demo() -> None:
    """Run demonstration calculations showing all capabilities."""
    print("=" * 60)
    print("  Black-Scholes Options Pricing Calculator — STUB Demo")
    print("  For informational purposes only. Not financial advice.")
    print("=" * 60)

    # Example: BTC option
    S = 65000.0    # BTC spot price
    K = 70000.0    # Strike price
    T = 30 / 365   # 30 days to expiry
    r = 0.05       # 5% risk-free rate
    sigma = 0.80   # 80% annualized volatility (typical for BTC)

    print(f"\n--- Example: BTC European Options ---")
    print(f"  Spot (S):       ${S:,.0f}")
    print(f"  Strike (K):     ${K:,.0f}")
    print(f"  Expiry (T):     {T*365:.0f} days")
    print(f"  Risk-free (r):  {r:.1%}")
    print(f"  Volatility (σ): {sigma:.0%}")

    # Price both call and put
    prices = price_option(S, K, T, r, sigma)
    print(f"\n  Call Price:  ${prices.call:,.2f}")
    print(f"  Put Price:   ${prices.put:,.2f}")

    # Verify put-call parity: C - P = S - K*e^(-rT)
    parity_lhs = prices.call - prices.put
    parity_rhs = S - K * math.exp(-r * T)
    print(f"\n  Put-Call Parity Check:")
    print(f"    C - P           = ${parity_lhs:,.2f}")
    print(f"    S - K*e^(-rT)   = ${parity_rhs:,.2f}")
    print(f"    Difference:       ${abs(parity_lhs - parity_rhs):.6f} (should be ~0)")

    # Greeks for the call
    print(f"\n--- Call Greeks ---")
    cg = compute_greeks(S, K, T, r, sigma, "call")
    print(f"  Delta:  {cg.delta:+.4f}   (price change per $1 move)")
    print(f"  Gamma:  {cg.gamma:.6f}  (delta change per $1 move)")
    print(f"  Theta:  {cg.theta:+.2f}  (daily time decay in $)")
    print(f"  Vega:   {cg.vega:+.2f}   (price change per 1% vol)")
    print(f"  Rho:    {cg.rho:+.2f}    (price change per 1% rate)")

    # Greeks for the put
    print(f"\n--- Put Greeks ---")
    pg = compute_greeks(S, K, T, r, sigma, "put")
    print(f"  Delta:  {pg.delta:+.4f}")
    print(f"  Gamma:  {pg.gamma:.6f}")
    print(f"  Theta:  {pg.theta:+.2f}")
    print(f"  Vega:   {pg.vega:+.2f}")
    print(f"  Rho:    {pg.rho:+.2f}")

    # Implied volatility
    print(f"\n--- Implied Volatility Solver ---")
    # Use the call price we computed to back out the vol
    iv = implied_volatility(prices.call, S, K, T, r, "call")
    print(f"  Input price:    ${prices.call:,.2f}")
    print(f"  Solved IV:      {iv:.4%}")
    print(f"  Original sigma: {sigma:.4%}")
    print(f"  Error:          {abs(iv - sigma):.8f}")

    # Second example: ATM SOL option
    print(f"\n--- Example: SOL At-The-Money Call ---")
    S2 = 150.0
    K2 = 150.0
    T2 = 7 / 365   # 7 days
    r2 = 0.05
    sigma2 = 1.20   # 120% vol — typical for SOL

    prices2 = price_option(S2, K2, T2, r2, sigma2)
    greeks2 = compute_greeks(S2, K2, T2, r2, sigma2, "call")
    print(f"  Spot = Strike = ${S2:.0f}, 7 days, {sigma2:.0%} vol")
    print(f"  Call Price:  ${prices2.call:.2f}")
    print(f"  Delta:       {greeks2.delta:+.4f}")
    print(f"  Theta:       ${greeks2.theta:+.2f}/day")

    print(f"\n{'=' * 60}")
    print(f"  Demo complete. All calculations are for illustration only.")
    print(f"{'=' * 60}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(
        description="Black-Scholes option pricing calculator (STUB)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demonstration with example calculations",
    )
    parser.add_argument("--spot", type=float, help="Underlying spot price")
    parser.add_argument("--strike", type=float, help="Strike price")
    parser.add_argument("--days", type=float, help="Days to expiration")
    parser.add_argument("--rate", type=float, default=0.05, help="Risk-free rate (default: 0.05)")
    parser.add_argument("--vol", type=float, help="Annualized volatility (decimal, e.g., 0.80)")
    parser.add_argument("--type", choices=["call", "put"], default="call", help="Option type")

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not all([args.spot, args.strike, args.days, args.vol]):
        print("Error: --spot, --strike, --days, and --vol are required (or use --demo)")
        parser.print_help()
        sys.exit(1)

    T = args.days / 365.0
    result = full_pricing(args.spot, args.strike, T, args.rate, args.vol, args.type)

    print(f"\n{args.type.upper()} Option (Black-Scholes)")
    print(f"  Price:  ${result.price:.4f}")
    print(f"  Delta:  {result.delta:+.4f}")
    print(f"  Gamma:  {result.gamma:.6f}")
    print(f"  Theta:  ${result.theta:+.4f}/day")
    print(f"  Vega:   ${result.vega:+.4f}/1%vol")
    print(f"  Rho:    ${result.rho:+.4f}/1%rate")


if __name__ == "__main__":
    main()
