#!/usr/bin/env python3
"""Get and compare swap quotes from Raptor DEX aggregator.

Demonstrates the /quote endpoint with various parameters including
DEX filtering, multi-hop control, and slippage configuration.

Usage:
    python scripts/raptor_quote.py --demo
    python scripts/raptor_quote.py --input So11... --output EPjF... --amount 1000000000

Dependencies:
    uv pip install httpx

Environment Variables:
    RAPTOR_URL: Raptor instance URL (default: http://localhost:8080)
"""

import argparse
import json
import os
import sys
from typing import Optional

RAPTOR_URL = os.getenv("RAPTOR_URL", "http://localhost:8080")

# Well-known Solana token mints
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

# ── Demo Data ───────────────────────────────────────────────────────

DEMO_QUOTE_SOL_USDC = {
    "amountIn": 1_000_000_000,
    "amountOut": 156_234_567,
    "otherAmountThreshold": 155_453_394,
    "priceImpact": 0.03,
    "slippageBps": 50,
    "routePlan": [
        {
            "inputMint": SOL_MINT,
            "outputMint": USDC_MINT,
            "amountIn": 1_000_000_000,
            "amountOut": 156_234_567,
            "dex": "raydium_clmm",
            "pool": "7XawhbbxtsRcQA8KTkHT9f9nc6d69UwqCDh6U5EEbEmX",
        }
    ],
    "contextSlot": 298_765_432,
}

DEMO_QUOTE_SOL_USDC_MULTIHOP = {
    "amountIn": 1_000_000_000,
    "amountOut": 156_189_234,
    "otherAmountThreshold": 155_408_288,
    "priceImpact": 0.05,
    "slippageBps": 50,
    "routePlan": [
        {
            "inputMint": SOL_MINT,
            "outputMint": USDT_MINT,
            "amountIn": 1_000_000_000,
            "amountOut": 156_300_000,
            "dex": "orca_whirlpool",
            "pool": "4GkRbcYg1VKsZropgai4dMf2Nj2PkXNLf43knFpavrSi",
        },
        {
            "inputMint": USDT_MINT,
            "outputMint": USDC_MINT,
            "amountIn": 156_300_000,
            "amountOut": 156_189_234,
            "dex": "meteora_dlmm",
            "pool": "ARwi1S4DaiTG5DX7S4M4ZsrXqpMD1MrTmbu9ue2tpmEq",
        },
    ],
    "contextSlot": 298_765_435,
}

DEMO_QUOTE_FILTERED = {
    "amountIn": 1_000_000_000,
    "amountOut": 156_100_000,
    "otherAmountThreshold": 155_319_500,
    "priceImpact": 0.08,
    "slippageBps": 50,
    "routePlan": [
        {
            "inputMint": SOL_MINT,
            "outputMint": USDC_MINT,
            "amountIn": 1_000_000_000,
            "amountOut": 156_100_000,
            "dex": "orca_whirlpool_v2",
            "pool": "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",
        }
    ],
    "contextSlot": 298_765_438,
}


# ── Core Functions ──────────────────────────────────────────────────


def get_quote(
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = 50,
    dexes: Optional[str] = None,
    max_hops: Optional[int] = None,
    direct_only: bool = False,
) -> dict:
    """Get a swap quote from Raptor.

    Args:
        input_mint: Input token mint address.
        output_mint: Output token mint address.
        amount: Amount in smallest unit (lamports for SOL).
        slippage_bps: Slippage tolerance in basis points.
        dexes: Comma-separated DEX filter.
        max_hops: Maximum routing hops (1-4).
        direct_only: Only return single-hop routes.

    Returns:
        Quote response dict.
    """
    import httpx

    params: dict = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
        "slippageBps": slippage_bps,
    }
    if dexes:
        params["dexes"] = dexes
    if max_hops is not None:
        params["maxHops"] = max_hops
    if direct_only:
        params["directRouteOnly"] = "true"

    resp = httpx.get(f"{RAPTOR_URL}/quote", params=params, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def display_quote(quote: dict, label: str = "Quote") -> None:
    """Display a quote in human-readable format.

    Args:
        quote: Quote response dict.
        label: Display label.
    """
    amount_in = quote["amountIn"]
    amount_out = quote["amountOut"]
    impact = quote.get("priceImpact", 0)
    slippage = quote.get("slippageBps", 0)
    route = quote.get("routePlan", [])
    slot = quote.get("contextSlot", 0)

    # Assume SOL input (9 decimals) and USDC output (6 decimals)
    sol_in = amount_in / 1e9
    usdc_out = amount_out / 1e6
    price = usdc_out / sol_in if sol_in > 0 else 0

    print(f"\n{'=' * 50}")
    print(f"  {label}")
    print(f"{'=' * 50}")
    print(f"  Input:        {sol_in:.4f} SOL ({amount_in:,} lamports)")
    print(f"  Output:       {usdc_out:.4f} USDC ({amount_out:,} units)")
    print(f"  Eff. Price:   ${price:.4f} per SOL")
    print(f"  Price Impact: {impact:.4f}%")
    print(f"  Slippage:     {slippage} bps")
    print(f"  Hops:         {len(route)}")
    print(f"  Slot:         {slot:,}")

    if route:
        print(f"\n  Route:")
        for i, hop in enumerate(route):
            dex = hop.get("dex", "unknown")
            pool = hop.get("pool", "")[:12] + "..."
            print(f"    Hop {i + 1}: {dex} via {pool}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Get and compare Raptor swap quotes."""
    parser = argparse.ArgumentParser(description="Raptor quote comparison")
    parser.add_argument("--demo", action="store_true", help="Use mock data")
    parser.add_argument("--input", type=str, default=SOL_MINT, help="Input mint")
    parser.add_argument("--output", type=str, default=USDC_MINT, help="Output mint")
    parser.add_argument("--amount", type=int, default=1_000_000_000, help="Amount in lamports")
    args = parser.parse_args()

    if args.demo:
        print("=== RAPTOR QUOTE COMPARISON (Demo Mode) ===")
        print(f"Raptor URL: {RAPTOR_URL} (not connected in demo)\n")

        display_quote(DEMO_QUOTE_SOL_USDC, "Default Quote (all DEXes, up to 4 hops)")
        display_quote(DEMO_QUOTE_SOL_USDC_MULTIHOP, "Multi-hop Route (SOL → USDT → USDC)")
        display_quote(DEMO_QUOTE_FILTERED, "Filtered Quote (Orca only, direct route)")

        # Compare
        best_out = DEMO_QUOTE_SOL_USDC["amountOut"]
        worst_out = DEMO_QUOTE_FILTERED["amountOut"]
        diff_bps = (best_out - worst_out) / best_out * 10_000

        print(f"\n{'=' * 50}")
        print(f"  COMPARISON")
        print(f"{'=' * 50}")
        print(f"  Best output:  {best_out / 1e6:.4f} USDC (all DEXes)")
        print(f"  Worst output: {worst_out / 1e6:.4f} USDC (Orca only)")
        print(f"  Difference:   {diff_bps:.1f} bps ({(best_out - worst_out) / 1e6:.4f} USDC)")
        print()
        return

    # Live mode
    try:
        import httpx  # noqa: F811
    except ImportError:
        print("httpx is required. Install with: uv pip install httpx")
        sys.exit(1)

    print(f"Fetching quotes from {RAPTOR_URL}...")

    try:
        q_default = get_quote(args.input, args.output, args.amount)
        display_quote(q_default, "Default Quote")

        q_direct = get_quote(args.input, args.output, args.amount, direct_only=True)
        display_quote(q_direct, "Direct Route Only")
    except Exception as e:
        print(f"Error: {e}")
        print("Is Raptor running? Check RAPTOR_URL environment variable.")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
