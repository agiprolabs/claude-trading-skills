#!/usr/bin/env python3
"""Fetch and display Jupiter swap quotes with route analysis.

Queries the Jupiter v6 API for the best swap route between two tokens,
displays a detailed breakdown of the quote including amounts, price impact,
route path, and compares with direct price to show effective cost.

Usage:
    python scripts/get_quote.py
    python scripts/get_quote.py --demo
    INPUT_MINT=So111... OUTPUT_MINT=EPjF... AMOUNT_LAMPORTS=1000000000 python scripts/get_quote.py

Dependencies:
    uv pip install httpx

Environment Variables:
    INPUT_MINT:      Input token mint address (default: SOL)
    OUTPUT_MINT:     Output token mint address (default: USDC)
    AMOUNT_LAMPORTS: Input amount in smallest units (default: 1000000000 = 1 SOL)
    SLIPPAGE_BPS:    Maximum slippage in basis points (default: 50)
    HELIUS_API_KEY:  Optional — for priority fee estimation
"""

import os
import sys
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────

JUPITER_BASE_URL = "https://quote-api.jup.ag/v6"
JUPITER_PRICE_URL = "https://price.jup.ag/v2/price"

# Well-known token mints
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

# Token decimals for display
KNOWN_DECIMALS: dict[str, int] = {
    SOL_MINT: 9,
    USDC_MINT: 6,
    USDT_MINT: 6,
}

INPUT_MINT = os.getenv("INPUT_MINT", SOL_MINT)
OUTPUT_MINT = os.getenv("OUTPUT_MINT", USDC_MINT)
AMOUNT_LAMPORTS = int(os.getenv("AMOUNT_LAMPORTS", "1000000000"))  # 1 SOL
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "50"))
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")


# ── Token Metadata ──────────────────────────────────────────────────

def get_token_info(client: httpx.Client, mint: str) -> dict:
    """Look up token symbol and decimals from Jupiter token list.

    Args:
        client: HTTP client instance.
        mint: Token mint address.

    Returns:
        Dict with 'symbol' and 'decimals' keys.
    """
    if not hasattr(get_token_info, "_cache"):
        get_token_info._cache = {}

    if mint in get_token_info._cache:
        return get_token_info._cache[mint]

    # Use known decimals if available
    if mint in KNOWN_DECIMALS:
        info = {"symbol": _mint_to_symbol(mint), "decimals": KNOWN_DECIMALS[mint]}
        get_token_info._cache[mint] = info
        return info

    # Fetch from Jupiter token list
    try:
        resp = client.get(f"{JUPITER_BASE_URL}/tokens", timeout=10.0)
        resp.raise_for_status()
        for token in resp.json():
            if token["address"] == mint:
                info = {"symbol": token.get("symbol", "UNKNOWN"),
                        "decimals": token.get("decimals", 9)}
                get_token_info._cache[mint] = info
                return info
    except httpx.HTTPError:
        pass

    info = {"symbol": mint[:8] + "...", "decimals": 9}
    get_token_info._cache[mint] = info
    return info


def _mint_to_symbol(mint: str) -> str:
    """Map well-known mints to symbols."""
    symbols = {SOL_MINT: "SOL", USDC_MINT: "USDC", USDT_MINT: "USDT"}
    return symbols.get(mint, mint[:8] + "...")


# ── Jupiter Quote ───────────────────────────────────────────────────

def fetch_quote(
    client: httpx.Client,
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = 50,
    only_direct_routes: bool = False,
) -> Optional[dict]:
    """Fetch a swap quote from Jupiter v6 API.

    Args:
        client: HTTP client instance.
        input_mint: Input token mint address.
        output_mint: Output token mint address.
        amount: Input amount in smallest units (e.g., lamports for SOL).
        slippage_bps: Maximum slippage in basis points.
        only_direct_routes: If True, skip multi-hop routes.

    Returns:
        Quote response dict, or None on failure.
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
        "slippageBps": slippage_bps,
    }
    if only_direct_routes:
        params["onlyDirectRoutes"] = "true"

    try:
        resp = client.get(
            f"{JUPITER_BASE_URL}/quote",
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"Quote API error {e.response.status_code}: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"HTTP error fetching quote: {e}")
        return None


# ── Jupiter Price ───────────────────────────────────────────────────

def fetch_direct_price(
    client: httpx.Client,
    input_mint: str,
    output_mint: str,
) -> Optional[float]:
    """Fetch direct price from Jupiter Price API v2.

    Args:
        client: HTTP client instance.
        input_mint: Input token mint.
        output_mint: Output (quote) token mint.

    Returns:
        Price as float, or None on failure.
    """
    try:
        resp = client.get(
            JUPITER_PRICE_URL,
            params={"ids": input_mint, "vsToken": output_mint},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        token_data = data.get(input_mint)
        if token_data:
            return float(token_data["price"])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        print(f"Price lookup failed: {e}")
    return None


# ── Priority Fee Estimation ─────────────────────────────────────────

def estimate_priority_fee(
    client: httpx.Client,
    input_mint: str,
    output_mint: str,
) -> Optional[int]:
    """Estimate priority fee using Helius API.

    Args:
        client: HTTP client instance.
        input_mint: Input token mint.
        output_mint: Output token mint.

    Returns:
        Recommended priority fee in microLamports, or None if unavailable.
    """
    if not HELIUS_API_KEY:
        return None

    helius_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getPriorityFeeEstimate",
        "params": [{
            "accountKeys": [input_mint, output_mint],
            "options": {"recommended": True},
        }],
    }
    try:
        resp = client.post(helius_url, json=payload, timeout=10.0)
        resp.raise_for_status()
        result = resp.json().get("result", {})
        return int(result.get("priorityFeeEstimate", 0))
    except (httpx.HTTPError, KeyError, ValueError):
        return None


# ── Display ─────────────────────────────────────────────────────────

def format_amount(raw_amount: str, decimals: int) -> str:
    """Format a raw token amount with proper decimal places.

    Args:
        raw_amount: Amount as string in smallest units.
        decimals: Token decimal places.

    Returns:
        Formatted amount string.
    """
    value = int(raw_amount) / (10 ** decimals)
    if decimals <= 2:
        return f"{value:,.2f}"
    elif value >= 1.0:
        return f"{value:,.4f}"
    else:
        return f"{value:,.{decimals}f}"


def display_quote(
    quote: dict,
    input_info: dict,
    output_info: dict,
    direct_price: Optional[float],
    priority_fee: Optional[int],
) -> None:
    """Display a formatted quote summary.

    Args:
        quote: Jupiter quote response.
        input_info: Input token info (symbol, decimals).
        output_info: Output token info (symbol, decimals).
        direct_price: Direct market price for comparison, or None.
        priority_fee: Estimated priority fee in microLamports, or None.
    """
    in_amount = format_amount(quote["inAmount"], input_info["decimals"])
    out_amount = format_amount(quote["outAmount"], output_info["decimals"])
    min_received = format_amount(quote["otherAmountThreshold"], output_info["decimals"])
    price_impact = float(quote.get("priceImpactPct", "0"))
    slippage = quote.get("slippageBps", 0)

    # Calculate effective price
    in_value = int(quote["inAmount"]) / (10 ** input_info["decimals"])
    out_value = int(quote["outAmount"]) / (10 ** output_info["decimals"])
    effective_price = out_value / in_value if in_value > 0 else 0

    # Route description
    route_parts = []
    for step in quote.get("routePlan", []):
        swap = step.get("swapInfo", {})
        label = swap.get("label", "Unknown")
        pct = step.get("percent", 100)
        if pct < 100:
            route_parts.append(f"{label} ({pct}%)")
        else:
            route_parts.append(label)
    route_str = " → ".join(route_parts) if route_parts else "Unknown"

    # Print formatted output
    print()
    print("=" * 60)
    print("  JUPITER SWAP QUOTE")
    print("=" * 60)
    print()
    print(f"  Sell:          {in_amount} {input_info['symbol']}")
    print(f"  Buy:           ~{out_amount} {output_info['symbol']}")
    print(f"  Min received:  {min_received} {output_info['symbol']}")
    print(f"  Slippage:      {slippage / 100:.2f}%")
    print(f"  Price impact:  {price_impact:.4f}%")
    print(f"  Eff. price:    1 {input_info['symbol']} = {effective_price:,.6f} {output_info['symbol']}")
    print(f"  Route:         {route_str}")

    # Compare with direct price
    if direct_price is not None and effective_price > 0:
        price_diff_bps = abs(effective_price - direct_price) / direct_price * 10000
        print()
        print(f"  Market price:  1 {input_info['symbol']} = {direct_price:,.6f} {output_info['symbol']}")
        print(f"  Diff vs market: {price_diff_bps:,.1f} bps")

    # Priority fee estimate
    if priority_fee is not None:
        fee_sol = priority_fee * 200_000 / 1_000_000_000_000  # assume 200K CU
        print()
        print(f"  Priority fee:  {priority_fee:,} microLamports/CU (~{fee_sol:.6f} SOL)")
    else:
        print()
        print("  Priority fee:  Use 'auto' or set HELIUS_API_KEY for estimate")

    # Warnings
    if price_impact > 2.0:
        print()
        print(f"  *** HIGH PRICE IMPACT: {price_impact:.2f}% ***")
        print("  *** Consider reducing trade size ***")
    elif price_impact > 5.0:
        print()
        print(f"  *** EXTREME PRICE IMPACT: {price_impact:.2f}% ***")
        print("  *** Trade execution NOT recommended ***")

    print()
    print("=" * 60)
    print("  This is a quote only. No transaction has been executed.")
    print("=" * 60)
    print()


# ── Main ────────────────────────────────────────────────────────────

def run_demo(client: httpx.Client) -> None:
    """Run a demo quote for SOL -> USDC.

    Args:
        client: HTTP client instance.
    """
    print("Running demo: 1 SOL → USDC quote")
    print()

    quote = fetch_quote(
        client,
        input_mint=SOL_MINT,
        output_mint=USDC_MINT,
        amount=1_000_000_000,
        slippage_bps=50,
    )
    if not quote:
        print("Failed to fetch demo quote.")
        return

    input_info = {"symbol": "SOL", "decimals": 9}
    output_info = {"symbol": "USDC", "decimals": 6}
    direct_price = fetch_direct_price(client, SOL_MINT, USDC_MINT)
    priority_fee = estimate_priority_fee(client, SOL_MINT, USDC_MINT)

    display_quote(quote, input_info, output_info, direct_price, priority_fee)

    # Also show a direct-route-only comparison
    print("Comparing with direct-route-only quote...")
    direct_quote = fetch_quote(
        client,
        input_mint=SOL_MINT,
        output_mint=USDC_MINT,
        amount=1_000_000_000,
        slippage_bps=50,
        only_direct_routes=True,
    )
    if direct_quote:
        direct_out = int(direct_quote["outAmount"]) / 1e6
        multi_out = int(quote["outAmount"]) / 1e6
        diff = multi_out - direct_out
        print(f"  Multi-hop output:  {multi_out:,.4f} USDC")
        print(f"  Direct-only output: {direct_out:,.4f} USDC")
        print(f"  Multi-hop advantage: {diff:,.4f} USDC ({diff / multi_out * 100:.3f}%)")
        print()


def main() -> None:
    """Main entry point."""
    demo_mode = "--demo" in sys.argv

    with httpx.Client() as client:
        if demo_mode:
            run_demo(client)
            return

        input_mint = INPUT_MINT
        output_mint = OUTPUT_MINT
        amount = AMOUNT_LAMPORTS
        slippage_bps = SLIPPAGE_BPS

        print(f"Fetching quote: {input_mint[:8]}... → {output_mint[:8]}...")
        print(f"Amount: {amount} (smallest units), Slippage: {slippage_bps} bps")
        print()

        # Fetch token metadata
        input_info = get_token_info(client, input_mint)
        output_info = get_token_info(client, output_mint)

        # Fetch quote
        quote = fetch_quote(client, input_mint, output_mint, amount, slippage_bps)
        if not quote:
            print("Failed to fetch quote. Check token mints and try again.")
            sys.exit(1)

        # Fetch comparison price
        direct_price = fetch_direct_price(client, input_mint, output_mint)

        # Estimate priority fee
        priority_fee = estimate_priority_fee(client, input_mint, output_mint)

        # Display results
        display_quote(quote, input_info, output_info, direct_price, priority_fee)


if __name__ == "__main__":
    main()
