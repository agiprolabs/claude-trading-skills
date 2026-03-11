#!/usr/bin/env python3
"""Build empirical slippage curves from Jupiter quotes or synthetic data.

Queries Jupiter V6 API at multiple trade sizes to measure actual executable
slippage, fits a power-law model, and estimates maximum trade sizes for
various slippage thresholds.

Usage:
    python scripts/slippage_curve.py
    python scripts/slippage_curve.py --demo
    TOKEN_MINT=<mint_address> python scripts/slippage_curve.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Solana token mint address to analyze (optional, defaults to
                BONK for demonstration).
"""

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
SOL_DECIMALS = 9

# Default token: BONK (widely available, decent liquidity)
DEFAULT_TOKEN_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

# Trade sizes to test (in SOL)
TRADE_SIZES_SOL = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0]

# Request timeout and delay
REQUEST_TIMEOUT = 15.0
REQUEST_DELAY = 0.5  # seconds between requests to avoid rate limiting


# ── Data Classes ────────────────────────────────────────────────────
@dataclass
class QuoteResult:
    """Result from a single Jupiter quote query."""

    trade_size_sol: float
    input_lamports: int
    output_amount: int
    output_decimals: int
    effective_price: float  # SOL per token
    route_plan: list[dict] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class SlippagePoint:
    """A single point on the slippage curve."""

    trade_size_sol: float
    slippage_bps: float
    effective_price: float
    output_tokens: float


@dataclass
class PowerLawFit:
    """Parameters of the power-law slippage model: bps = a * size^b."""

    a: float
    b: float
    r_squared: float


# ── Jupiter Quote Functions ─────────────────────────────────────────
def fetch_jupiter_quote(
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int = 5000,
    timeout: float = REQUEST_TIMEOUT,
) -> QuoteResult:
    """Fetch a single quote from Jupiter V6 API.

    Args:
        input_mint: Input token mint address.
        output_mint: Output token mint address.
        amount_lamports: Input amount in smallest unit (lamports for SOL).
        slippage_bps: Maximum slippage tolerance in basis points.
        timeout: HTTP request timeout in seconds.

    Returns:
        QuoteResult with execution details.
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": str(slippage_bps),
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(JUPITER_QUOTE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return QuoteResult(
            trade_size_sol=amount_lamports / 10**SOL_DECIMALS,
            input_lamports=amount_lamports,
            output_amount=0,
            output_decimals=0,
            effective_price=0.0,
            error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
        )
    except httpx.RequestError as e:
        return QuoteResult(
            trade_size_sol=amount_lamports / 10**SOL_DECIMALS,
            input_lamports=amount_lamports,
            output_amount=0,
            output_decimals=0,
            effective_price=0.0,
            error=f"Request error: {str(e)[:200]}",
        )

    out_amount = int(data.get("outAmount", 0))
    # Infer decimals from the first route or default
    out_decimals = _infer_output_decimals(data)
    trade_sol = amount_lamports / 10**SOL_DECIMALS
    tokens = out_amount / 10**out_decimals if out_decimals > 0 else out_amount
    eff_price = trade_sol / tokens if tokens > 0 else 0.0

    route_plan = data.get("routePlan", [])

    return QuoteResult(
        trade_size_sol=trade_sol,
        input_lamports=amount_lamports,
        output_amount=out_amount,
        output_decimals=out_decimals,
        effective_price=eff_price,
        route_plan=route_plan,
    )


def _infer_output_decimals(quote_data: dict) -> int:
    """Infer output token decimals from quote response data.

    Args:
        quote_data: Raw Jupiter quote response.

    Returns:
        Number of decimal places for the output token.
    """
    # Jupiter V6 doesn't always return decimals directly.
    # Use a heuristic: if outAmount is very large relative to a
    # reasonable token amount, it has many decimals.
    out_amount = int(quote_data.get("outAmount", 0))
    in_amount = int(quote_data.get("inAmount", 1))

    # For well-known tokens we could hardcode, but generically:
    # Most SPL tokens use 6 or 9 decimals.
    # Check if routePlan has decimal info.
    route_plan = quote_data.get("routePlan", [])
    for step in route_plan:
        swap_info = step.get("swapInfo", {})
        out_mint = swap_info.get("outputMint", "")
        # If the last hop outputs SOL, it's 9 decimals
        if out_mint == SOL_MINT:
            return SOL_DECIMALS

    # Default assumption for most SPL tokens
    if out_amount > 10**15:
        return 9
    if out_amount > 10**10:
        return 6
    return 6


# ── Slippage Curve Building ─────────────────────────────────────────
def build_slippage_curve_live(
    token_mint: str,
    trade_sizes: list[float],
    direction: str = "buy",
) -> list[SlippagePoint]:
    """Build slippage curve by querying Jupiter at multiple trade sizes.

    Args:
        token_mint: Token mint address to analyze.
        trade_sizes: List of trade sizes in SOL.
        direction: 'buy' (SOL -> token) or 'sell' (token -> SOL).

    Returns:
        List of SlippagePoint objects sorted by trade size.
    """
    quotes: list[QuoteResult] = []

    for size_sol in sorted(trade_sizes):
        lamports = int(size_sol * 10**SOL_DECIMALS)

        if direction == "buy":
            quote = fetch_jupiter_quote(SOL_MINT, token_mint, lamports)
        else:
            # For sell, we'd need token amount, not SOL amount.
            # Approximate by using the buy direction for curve shape.
            quote = fetch_jupiter_quote(SOL_MINT, token_mint, lamports)

        if quote.error:
            print(f"  WARNING: {size_sol} SOL — {quote.error}")
        else:
            quotes.append(quote)
            print(f"  {size_sol:>8.2f} SOL → {quote.output_amount} raw units")

        time.sleep(REQUEST_DELAY)

    if len(quotes) < 2:
        print("ERROR: Need at least 2 successful quotes to build curve.")
        return []

    # Use smallest trade as reference price (closest to spot)
    ref_price = quotes[0].effective_price
    if ref_price <= 0:
        print("ERROR: Reference price is zero. Cannot compute slippage.")
        return []

    points: list[SlippagePoint] = []
    for q in quotes:
        if q.effective_price <= 0:
            continue
        # Slippage = how much more you pay vs reference
        slippage_frac = (q.effective_price - ref_price) / ref_price
        slippage_bps = slippage_frac * 10_000
        tokens = q.output_amount / 10**q.output_decimals if q.output_decimals > 0 else float(q.output_amount)
        points.append(SlippagePoint(
            trade_size_sol=q.trade_size_sol,
            slippage_bps=max(0.0, slippage_bps),
            effective_price=q.effective_price,
            output_tokens=tokens,
        ))

    return points


def build_slippage_curve_demo(trade_sizes: list[float]) -> list[SlippagePoint]:
    """Generate synthetic slippage curve for demonstration.

    Simulates a mid-cap token with ~$200K TVL pool.
    Model: slippage_bps = 15 * trade_size^1.05

    Args:
        trade_sizes: List of trade sizes in SOL.

    Returns:
        List of SlippagePoint objects.
    """
    # Simulated pool: 500 SOL / 5,000,000 tokens
    pool_sol = 500.0
    pool_tokens = 5_000_000.0
    spot_price = pool_sol / pool_tokens  # 0.0001 SOL/token

    points: list[SlippagePoint] = []
    for size in sorted(trade_sizes):
        # Constant-product with some noise for realism
        tokens_out = pool_tokens * size / (pool_sol + size)
        eff_price = size / tokens_out if tokens_out > 0 else 0
        slippage_frac = (eff_price - spot_price) / spot_price
        slippage_bps = slippage_frac * 10_000

        # Add small random-ish perturbation (deterministic based on size)
        noise = math.sin(size * 7.3) * 0.5 + 1.0  # 0.5x to 1.5x
        slippage_bps = max(0.01, slippage_bps * (0.9 + 0.2 * (noise / 1.5)))

        points.append(SlippagePoint(
            trade_size_sol=size,
            slippage_bps=round(slippage_bps, 2),
            effective_price=eff_price,
            output_tokens=tokens_out,
        ))

    return points


# ── Power-Law Fitting ───────────────────────────────────────────────
def fit_power_law(points: list[SlippagePoint]) -> Optional[PowerLawFit]:
    """Fit slippage_bps = a * trade_size^b using log-linear regression.

    Args:
        points: Slippage data points (must have at least 2 with slippage > 0).

    Returns:
        PowerLawFit with coefficients and R-squared, or None if fitting fails.
    """
    # Filter to points with positive slippage
    valid = [(p.trade_size_sol, p.slippage_bps) for p in points if p.slippage_bps > 0 and p.trade_size_sol > 0]

    if len(valid) < 2:
        return None

    # Log-transform
    log_x = [math.log(s) for s, _ in valid]
    log_y = [math.log(b) for _, b in valid]

    n = len(valid)
    sum_x = sum(log_x)
    sum_y = sum(log_y)
    sum_xy = sum(lx * ly for lx, ly in zip(log_x, log_y))
    sum_x2 = sum(lx * lx for lx in log_x)

    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return None

    b = (n * sum_xy - sum_x * sum_y) / denom
    log_a = (sum_y - b * sum_x) / n
    a = math.exp(log_a)

    # R-squared
    mean_y = sum_y / n
    ss_tot = sum((ly - mean_y) ** 2 for ly in log_y)
    ss_res = sum((ly - (log_a + b * lx)) ** 2 for lx, ly in zip(log_x, log_y))
    r_sq = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return PowerLawFit(a=a, b=b, r_squared=r_sq)


def max_trade_size(fit: PowerLawFit, threshold_bps: float) -> float:
    """Compute maximum trade size for a given slippage threshold.

    Args:
        fit: Power-law fit parameters.
        threshold_bps: Maximum acceptable slippage in basis points.

    Returns:
        Maximum trade size in SOL.
    """
    if fit.a <= 0 or fit.b == 0:
        return 0.0
    return (threshold_bps / fit.a) ** (1.0 / fit.b)


# ── Display Functions ───────────────────────────────────────────────
def print_slippage_table(points: list[SlippagePoint]) -> None:
    """Print formatted slippage curve table.

    Args:
        points: List of slippage data points.
    """
    print("\n" + "=" * 72)
    print("SLIPPAGE CURVE")
    print("=" * 72)
    print(f"{'Trade Size (SOL)':>18} {'Slippage (bps)':>16} {'Slippage (%)':>14} {'Eff. Price':>14}")
    print("-" * 72)
    for p in points:
        pct = p.slippage_bps / 100.0
        print(f"{p.trade_size_sol:>18.4f} {p.slippage_bps:>16.2f} {pct:>13.4f}% {p.effective_price:>14.10f}")
    print("-" * 72)


def print_fit_results(fit: PowerLawFit) -> None:
    """Print power-law fit results and max trade size estimates.

    Args:
        fit: Fitted power-law model parameters.
    """
    print(f"\nPOWER-LAW FIT: slippage_bps = {fit.a:.4f} * trade_size ^ {fit.b:.4f}")
    print(f"R-squared: {fit.r_squared:.4f}")

    thresholds = [25, 50, 100, 200, 500, 1000]
    print(f"\n{'Threshold (bps)':>18} {'Max Trade (SOL)':>18}")
    print("-" * 40)
    for t in thresholds:
        max_sol = max_trade_size(fit, t)
        if max_sol > 10_000:
            print(f"{t:>18} {'> 10,000':>18}")
        else:
            print(f"{t:>18} {max_sol:>18.4f}")
    print("-" * 40)


def print_tranche_recommendation(fit: PowerLawFit, total_size: float, threshold_bps: float = 100.0) -> None:
    """Print multi-tranche execution recommendation.

    Args:
        fit: Power-law fit parameters.
        total_size: Total desired trade size in SOL.
        threshold_bps: Maximum slippage per tranche in bps.
    """
    max_sol = max_trade_size(fit, threshold_bps)
    if max_sol <= 0:
        print("\nCannot determine tranche size — fit parameters invalid.")
        return

    if total_size <= max_sol:
        single_slip = fit.a * total_size**fit.b
        print(f"\nTRANCHE ANALYSIS for {total_size:.2f} SOL:")
        print(f"  Single execution: {single_slip:.1f} bps slippage")
        print(f"  Max size for {threshold_bps:.0f} bps: {max_sol:.4f} SOL")
        print(f"  Recommendation: Execute as single trade")
        return

    n_tranches = math.ceil(total_size / max_sol)
    tranche_size = total_size / n_tranches
    per_tranche_slip = fit.a * tranche_size**fit.b
    single_slip = fit.a * total_size**fit.b

    print(f"\nTRANCHE ANALYSIS for {total_size:.2f} SOL:")
    print(f"  Single execution: {single_slip:.1f} bps slippage")
    print(f"  Max size for {threshold_bps:.0f} bps: {max_sol:.4f} SOL")
    print(f"  Recommended tranches: {n_tranches}")
    print(f"  Tranche size: {tranche_size:.4f} SOL")
    print(f"  Per-tranche slippage: {per_tranche_slip:.1f} bps")
    print(f"  Wait between tranches: 5-10 seconds (allow arb rebalancing)")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run slippage curve analysis."""
    parser = argparse.ArgumentParser(description="Build empirical slippage curves")
    parser.add_argument("--demo", action="store_true", help="Use synthetic data instead of live API")
    parser.add_argument("--token", type=str, default=None, help="Token mint address")
    parser.add_argument("--total-size", type=float, default=10.0, help="Total trade size for tranche analysis (SOL)")
    parser.add_argument("--threshold", type=float, default=100.0, help="Slippage threshold for tranche analysis (bps)")
    args = parser.parse_args()

    token_mint = args.token or os.getenv("TOKEN_MINT", DEFAULT_TOKEN_MINT)

    if args.demo:
        print("DEMO MODE — using synthetic slippage curve")
        print("Simulated pool: 500 SOL / 5,000,000 tokens (~$200K TVL)")
        points = build_slippage_curve_demo(TRADE_SIZES_SOL)
    else:
        print(f"Querying Jupiter for token: {token_mint}")
        print(f"Testing {len(TRADE_SIZES_SOL)} trade sizes...")
        points = build_slippage_curve_live(token_mint, TRADE_SIZES_SOL, direction="buy")

    if not points:
        print("No data points collected. Exiting.")
        sys.exit(1)

    print_slippage_table(points)

    fit = fit_power_law(points)
    if fit:
        print_fit_results(fit)
        print_tranche_recommendation(fit, args.total_size, args.threshold)
    else:
        print("\nCould not fit power-law model (insufficient valid data points).")

    print("\nNOTE: This analysis is for informational purposes only.")
    print("Actual execution slippage may differ from quotes due to")
    print("price movement, MEV, and changing liquidity conditions.")


if __name__ == "__main__":
    main()
