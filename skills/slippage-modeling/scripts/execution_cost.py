#!/usr/bin/env python3
"""Estimate total execution cost and break-even for a Solana DEX trade.

Computes all cost components — price impact, DEX fee, priority fee, and
MEV risk — then calculates the minimum price move needed to break even
on a roundtrip trade.

Usage:
    python scripts/execution_cost.py
    python scripts/execution_cost.py --demo
    TOKEN_MINT=<mint> TRADE_SIZE_SOL=5.0 python scripts/execution_cost.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Solana token mint address (optional, defaults to BONK).
    TRADE_SIZE_SOL: Trade size in SOL (optional, defaults to 1.0).
"""

import argparse
import math
import os
import sys
from dataclasses import dataclass
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

DEFAULT_TOKEN_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
DEFAULT_TRADE_SIZE = 1.0

# Priority fee estimates by congestion level
PRIORITY_FEE_LOW = 0.0001      # SOL
PRIORITY_FEE_NORMAL = 0.001    # SOL
PRIORITY_FEE_HIGH = 0.005      # SOL

# MEV risk thresholds (trade size in SOL)
MEV_THRESHOLD_LOW = 1.0
MEV_THRESHOLD_MED = 5.0
MEV_THRESHOLD_HIGH = 20.0

REQUEST_TIMEOUT = 15.0


# ── Data Classes ────────────────────────────────────────────────────
@dataclass
class CostBreakdown:
    """Complete execution cost breakdown for a trade."""

    trade_size_sol: float
    direction: str  # "buy" or "sell"

    # Component costs in basis points
    impact_bps: float
    fee_bps: float
    priority_bps: float
    mev_bps: float

    # Derived
    total_bps: float
    total_sol: float

    # Quote details
    output_amount: float
    effective_price: float
    spot_estimate: float  # estimated spot from small quote

    # Route info
    route_description: str


@dataclass
class BreakEvenAnalysis:
    """Break-even analysis for a roundtrip trade."""

    entry_cost_bps: float
    exit_cost_bps: float
    roundtrip_bps: float
    roundtrip_pct: float
    roundtrip_sol: float
    required_price_move_pct: float


# ── Jupiter Quote ───────────────────────────────────────────────────
def fetch_quote(
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
) -> Optional[dict]:
    """Fetch a Jupiter V6 quote.

    Args:
        input_mint: Input token mint.
        output_mint: Output token mint.
        amount_lamports: Input amount in smallest units.

    Returns:
        Parsed JSON response or None on error.
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": "5000",
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.get(JUPITER_QUOTE_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"Quote error: {e}")
        return None


def extract_fee_bps(quote_data: dict) -> float:
    """Extract total swap fee from Jupiter route plan.

    Args:
        quote_data: Raw Jupiter quote response.

    Returns:
        Estimated fee in basis points.
    """
    route_plan = quote_data.get("routePlan", [])
    if not route_plan:
        return 25.0  # Default assumption: Raydium 0.25%

    total_fee_pct = 0.0
    for step in route_plan:
        swap_info = step.get("swapInfo", {})
        fee_amount = int(swap_info.get("feeAmount", "0"))
        in_amount = int(swap_info.get("inAmount", "1"))
        if in_amount > 0:
            total_fee_pct += fee_amount / in_amount

    return total_fee_pct * 10_000 if total_fee_pct > 0 else 25.0


def describe_route(quote_data: dict) -> str:
    """Generate human-readable route description.

    Args:
        quote_data: Raw Jupiter quote response.

    Returns:
        String describing the route.
    """
    route_plan = quote_data.get("routePlan", [])
    if not route_plan:
        return "Unknown route"

    labels = []
    for step in route_plan:
        swap_info = step.get("swapInfo", {})
        label = swap_info.get("label", "Unknown")
        pct = step.get("percent", 100)
        labels.append(f"{label} ({pct}%)")

    return " → ".join(labels)


# ── Cost Estimation ─────────────────────────────────────────────────
def estimate_priority_fee_bps(trade_size_sol: float, congestion: str = "normal") -> float:
    """Estimate priority fee in bps relative to trade size.

    Args:
        trade_size_sol: Trade size in SOL.
        congestion: Network congestion level ('low', 'normal', 'high').

    Returns:
        Priority fee cost in basis points.
    """
    fee_sol = {
        "low": PRIORITY_FEE_LOW,
        "normal": PRIORITY_FEE_NORMAL,
        "high": PRIORITY_FEE_HIGH,
    }.get(congestion, PRIORITY_FEE_NORMAL)

    if trade_size_sol <= 0:
        return 0.0
    return (fee_sol / trade_size_sol) * 10_000


def estimate_mev_bps(trade_size_sol: float, pool_tvl_estimate: str = "medium") -> float:
    """Estimate MEV risk cost in basis points.

    Uses trade size and estimated pool liquidity to assess sandwich
    attack risk. Larger trades on thinner pools face higher MEV cost.

    Args:
        trade_size_sol: Trade size in SOL.
        pool_tvl_estimate: Pool liquidity category ('deep', 'medium', 'thin').

    Returns:
        Estimated MEV cost in basis points.
    """
    # Base MEV risk by pool depth
    base_mev = {
        "deep": 2.0,    # >$1M TVL
        "medium": 10.0,  # $100K-$1M TVL
        "thin": 30.0,    # <$100K TVL
    }.get(pool_tvl_estimate, 10.0)

    # Scale with trade size (larger trades attract more MEV)
    if trade_size_sol < MEV_THRESHOLD_LOW:
        size_mult = 0.5
    elif trade_size_sol < MEV_THRESHOLD_MED:
        size_mult = 1.0
    elif trade_size_sol < MEV_THRESHOLD_HIGH:
        size_mult = 2.0
    else:
        size_mult = 4.0

    return base_mev * size_mult


def estimate_execution_cost(
    token_mint: str,
    trade_size_sol: float,
    direction: str = "buy",
    congestion: str = "normal",
    pool_depth: str = "medium",
) -> Optional[CostBreakdown]:
    """Estimate total execution cost for a trade.

    Fetches Jupiter quotes at the target size and a small reference size,
    computes price impact, adds fee/priority/MEV estimates.

    Args:
        token_mint: Token mint address.
        trade_size_sol: Trade size in SOL.
        direction: 'buy' (SOL -> token) or 'sell' (token -> SOL).
        congestion: Network congestion level.
        pool_depth: Estimated pool liquidity depth.

    Returns:
        CostBreakdown or None if quotes fail.
    """
    # Fetch small reference quote (0.001 SOL) for spot price estimate
    ref_lamports = int(0.001 * 10**SOL_DECIMALS)
    ref_quote = fetch_quote(SOL_MINT, token_mint, ref_lamports)
    if not ref_quote:
        print("Failed to fetch reference quote.")
        return None

    ref_out = int(ref_quote.get("outAmount", 0))
    if ref_out <= 0:
        print("Reference quote returned zero output.")
        return None

    spot_estimate = 0.001 / ref_out  # SOL per raw unit

    # Fetch actual trade quote
    trade_lamports = int(trade_size_sol * 10**SOL_DECIMALS)
    trade_quote = fetch_quote(SOL_MINT, token_mint, trade_lamports)
    if not trade_quote:
        print("Failed to fetch trade quote.")
        return None

    trade_out = int(trade_quote.get("outAmount", 0))
    if trade_out <= 0:
        print("Trade quote returned zero output.")
        return None

    effective_price = trade_size_sol / trade_out  # SOL per raw unit

    # Price impact: how much worse than spot
    impact_frac = (effective_price - spot_estimate) / spot_estimate if spot_estimate > 0 else 0
    impact_bps = max(0.0, impact_frac * 10_000)

    # Fee from route
    fee_bps = extract_fee_bps(trade_quote)

    # Priority fee
    priority_bps = estimate_priority_fee_bps(trade_size_sol, congestion)

    # MEV risk
    mev_bps = estimate_mev_bps(trade_size_sol, pool_depth)

    total_bps = impact_bps + fee_bps + priority_bps + mev_bps
    total_sol = trade_size_sol * total_bps / 10_000

    return CostBreakdown(
        trade_size_sol=trade_size_sol,
        direction=direction,
        impact_bps=round(impact_bps, 2),
        fee_bps=round(fee_bps, 2),
        priority_bps=round(priority_bps, 2),
        mev_bps=round(mev_bps, 2),
        total_bps=round(total_bps, 2),
        total_sol=round(total_sol, 6),
        output_amount=trade_out,
        effective_price=effective_price,
        spot_estimate=spot_estimate,
        route_description=describe_route(trade_quote),
    )


def estimate_execution_cost_demo(
    trade_size_sol: float,
    direction: str = "buy",
) -> CostBreakdown:
    """Generate demo execution cost estimate with synthetic data.

    Simulates a mid-cap token with ~$300K TVL.

    Args:
        trade_size_sol: Trade size in SOL.
        direction: Trade direction.

    Returns:
        Synthetic CostBreakdown.
    """
    # Simulated pool: 750 SOL reserves
    pool_sol = 750.0
    impact_frac = trade_size_sol / (pool_sol + trade_size_sol)
    impact_bps = round(impact_frac * 10_000, 2)

    fee_bps = 25.0  # Raydium standard
    priority_bps = round(estimate_priority_fee_bps(trade_size_sol, "normal"), 2)
    mev_bps = round(estimate_mev_bps(trade_size_sol, "medium"), 2)

    total_bps = impact_bps + fee_bps + priority_bps + mev_bps
    total_sol = trade_size_sol * total_bps / 10_000

    spot_price = 0.0001
    eff_price = spot_price * (1 + impact_frac)

    return CostBreakdown(
        trade_size_sol=trade_size_sol,
        direction=direction,
        impact_bps=impact_bps,
        fee_bps=fee_bps,
        priority_bps=priority_bps,
        mev_bps=mev_bps,
        total_bps=round(total_bps, 2),
        total_sol=round(total_sol, 6),
        output_amount=int(trade_size_sol / eff_price),
        effective_price=eff_price,
        spot_estimate=spot_price,
        route_description="Raydium AMM (100%) [demo]",
    )


# ── Break-Even Analysis ────────────────────────────────────────────
def compute_break_even(
    entry_cost: CostBreakdown,
    exit_multiplier: float = 1.2,
) -> BreakEvenAnalysis:
    """Compute break-even price move for a roundtrip trade.

    Exit slippage is typically higher than entry (selling into a pool
    you just bought from). exit_multiplier scales the entry cost.

    Args:
        entry_cost: Cost breakdown for the entry trade.
        exit_multiplier: Factor to scale entry costs for exit estimate.

    Returns:
        BreakEvenAnalysis with roundtrip costs.
    """
    exit_impact = entry_cost.impact_bps * exit_multiplier
    exit_bps = exit_impact + entry_cost.fee_bps + entry_cost.priority_bps + entry_cost.mev_bps * 0.5

    roundtrip_bps = entry_cost.total_bps + exit_bps
    roundtrip_pct = roundtrip_bps / 100.0
    roundtrip_sol = entry_cost.trade_size_sol * roundtrip_bps / 10_000
    required_move = roundtrip_bps / (10_000 - roundtrip_bps) * 100

    return BreakEvenAnalysis(
        entry_cost_bps=round(entry_cost.total_bps, 2),
        exit_cost_bps=round(exit_bps, 2),
        roundtrip_bps=round(roundtrip_bps, 2),
        roundtrip_pct=round(roundtrip_pct, 4),
        roundtrip_sol=round(roundtrip_sol, 6),
        required_price_move_pct=round(required_move, 4),
    )


# ── Display ─────────────────────────────────────────────────────────
def print_cost_report(cost: CostBreakdown, break_even: BreakEvenAnalysis) -> None:
    """Print formatted execution cost report.

    Args:
        cost: Execution cost breakdown.
        break_even: Break-even analysis.
    """
    print("\n" + "=" * 60)
    print("EXECUTION COST REPORT")
    print("=" * 60)
    print(f"Direction:    {cost.direction.upper()}")
    print(f"Trade size:   {cost.trade_size_sol:.4f} SOL")
    print(f"Route:        {cost.route_description}")

    print("\n--- Cost Components ---")
    print(f"  Price impact:    {cost.impact_bps:>8.2f} bps")
    print(f"  DEX fee:         {cost.fee_bps:>8.2f} bps")
    print(f"  Priority fee:    {cost.priority_bps:>8.2f} bps")
    print(f"  MEV risk:        {cost.mev_bps:>8.2f} bps")
    print(f"  ────────────────────────────")
    print(f"  TOTAL:           {cost.total_bps:>8.2f} bps  ({cost.total_bps / 100:.2f}%)")
    print(f"  Cost in SOL:     {cost.total_sol:>8.6f} SOL")

    print("\n--- Break-Even Analysis ---")
    print(f"  Entry cost:        {break_even.entry_cost_bps:>8.2f} bps")
    print(f"  Exit cost (est):   {break_even.exit_cost_bps:>8.2f} bps")
    print(f"  Roundtrip cost:    {break_even.roundtrip_bps:>8.2f} bps  ({break_even.roundtrip_pct:.2f}%)")
    print(f"  Roundtrip in SOL:  {break_even.roundtrip_sol:>8.6f} SOL")
    print(f"  Min price move:    {break_even.required_price_move_pct:>8.4f}%")

    print("\n--- Assessment ---")
    if break_even.roundtrip_bps < 100:
        print("  LOW COST — Favorable execution. Most strategies can absorb this.")
    elif break_even.roundtrip_bps < 300:
        print("  MODERATE COST — Ensure expected move exceeds break-even threshold.")
    elif break_even.roundtrip_bps < 1000:
        print("  HIGH COST — Only viable for high-conviction, large-move trades.")
    else:
        print("  VERY HIGH COST — Consider smaller size or higher-liquidity alternatives.")

    print("\n" + "=" * 60)
    print("NOTE: This is an estimate for informational purposes.")
    print("Actual costs may differ due to market conditions.")
    print("=" * 60)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run execution cost estimation."""
    parser = argparse.ArgumentParser(description="Estimate DEX execution costs")
    parser.add_argument("--demo", action="store_true", help="Use synthetic data")
    parser.add_argument("--token", type=str, default=None, help="Token mint address")
    parser.add_argument("--size", type=float, default=None, help="Trade size in SOL")
    parser.add_argument("--direction", type=str, default="buy", choices=["buy", "sell"])
    parser.add_argument("--congestion", type=str, default="normal", choices=["low", "normal", "high"])
    parser.add_argument("--pool-depth", type=str, default="medium", choices=["deep", "medium", "thin"])
    args = parser.parse_args()

    token_mint = args.token or os.getenv("TOKEN_MINT", DEFAULT_TOKEN_MINT)
    trade_size = args.size or float(os.getenv("TRADE_SIZE_SOL", str(DEFAULT_TRADE_SIZE)))

    if args.demo:
        print("DEMO MODE — using synthetic cost estimates")
        print(f"Simulated mid-cap token, pool TVL ~$300K")
        cost = estimate_execution_cost_demo(trade_size, args.direction)
    else:
        print(f"Estimating costs for {trade_size:.4f} SOL {args.direction}")
        print(f"Token: {token_mint}")
        cost = estimate_execution_cost(
            token_mint, trade_size, args.direction, args.congestion, args.pool_depth
        )

    if cost is None:
        print("Failed to estimate execution cost.")
        sys.exit(1)

    break_even = compute_break_even(cost)
    print_cost_report(cost, break_even)


if __name__ == "__main__":
    main()
