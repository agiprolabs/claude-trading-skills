#!/usr/bin/env python3
"""Build and simulate a Jupiter swap transaction without submitting.

Fetches a quote, builds the swap transaction via Jupiter v6 API, then
simulates it against the Solana RPC to verify it would succeed. Reports
compute units, logs, and any errors. NEVER signs or submits a real
transaction.

⚠️  SIMULATION ONLY — This script does NOT execute real swaps.
⚠️  No private keys are required or used.

Usage:
    python scripts/simulate_swap.py
    python scripts/simulate_swap.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    INPUT_MINT:      Input token mint address (default: SOL)
    OUTPUT_MINT:     Output token mint address (default: USDC)
    AMOUNT_LAMPORTS: Input amount in smallest units (default: 1000000000 = 1 SOL)
    SLIPPAGE_BPS:    Maximum slippage in basis points (default: 50)
    USER_PUBKEY:     Your wallet public key (required for non-demo mode)
    SOLANA_RPC_URL:  Solana RPC endpoint (default: public mainnet)
"""

import base64
import os
import sys
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)

# ── Safety Banner ───────────────────────────────────────────────────

SAFETY_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║  ⚠️   SIMULATION MODE — NO REAL TRANSACTIONS WILL EXECUTE   ║
║  This script builds and simulates swap transactions only.    ║
║  No private keys are required, loaded, or used.              ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── Configuration ───────────────────────────────────────────────────

JUPITER_BASE_URL = "https://quote-api.jup.ag/v6"
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Demo public key (a known Solana system account — not a real user wallet)
DEMO_PUBKEY = "11111111111111111111111111111111"

KNOWN_DECIMALS: dict[str, int] = {
    SOL_MINT: 9,
    USDC_MINT: 6,
}

INPUT_MINT = os.getenv("INPUT_MINT", SOL_MINT)
OUTPUT_MINT = os.getenv("OUTPUT_MINT", USDC_MINT)
AMOUNT_LAMPORTS = int(os.getenv("AMOUNT_LAMPORTS", "1000000000"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "50"))
USER_PUBKEY = os.getenv("USER_PUBKEY", "")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", DEFAULT_RPC_URL)


# ── Quote ───────────────────────────────────────────────────────────

def fetch_quote(
    client: httpx.Client,
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = 50,
) -> Optional[dict]:
    """Fetch a swap quote from Jupiter v6 API.

    Args:
        client: HTTP client instance.
        input_mint: Input token mint address.
        output_mint: Output token mint address.
        amount: Input amount in smallest units.
        slippage_bps: Maximum slippage in basis points.

    Returns:
        Quote response dict, or None on failure.
    """
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
        "slippageBps": slippage_bps,
    }
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


# ── Build Swap Transaction ──────────────────────────────────────────

def build_swap_transaction(
    client: httpx.Client,
    quote: dict,
    user_pubkey: str,
    priority_fee: str = "auto",
) -> Optional[dict]:
    """Build a swap transaction from a Jupiter quote.

    Args:
        client: HTTP client instance.
        quote: Quote response from Jupiter.
        user_pubkey: User's wallet public key (base58).
        priority_fee: Priority fee setting — "auto" or integer microLamports.

    Returns:
        Swap response dict containing swapTransaction, or None on failure.
    """
    body = {
        "quoteResponse": quote,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": priority_fee,
    }
    try:
        resp = client.post(
            f"{JUPITER_BASE_URL}/swap",
            json=body,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"Swap API error {e.response.status_code}: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"HTTP error building swap: {e}")
        return None


# ── Simulate Transaction ────────────────────────────────────────────

def simulate_transaction(
    client: httpx.Client,
    rpc_url: str,
    swap_transaction_b64: str,
) -> Optional[dict]:
    """Simulate a transaction via Solana RPC without submitting.

    Args:
        client: HTTP client instance.
        rpc_url: Solana RPC endpoint URL.
        swap_transaction_b64: Base64-encoded transaction from Jupiter.

    Returns:
        Simulation result dict, or None on RPC failure.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": [
            swap_transaction_b64,
            {
                "encoding": "base64",
                "commitment": "confirmed",
                "sigVerify": False,
                "replaceRecentBlockhash": True,
            },
        ],
    }
    try:
        resp = client.post(rpc_url, json=payload, timeout=30.0)
        resp.raise_for_status()
        result = resp.json()

        if "error" in result:
            print(f"RPC error: {result['error']}")
            return None

        return result.get("result", {}).get("value")
    except httpx.HTTPStatusError as e:
        print(f"RPC HTTP error {e.response.status_code}: {e.response.text}")
        return None
    except httpx.HTTPError as e:
        print(f"HTTP error during simulation: {e}")
        return None


# ── Display ─────────────────────────────────────────────────────────

def format_amount(raw: str, decimals: int) -> str:
    """Format raw token amount for display.

    Args:
        raw: Amount string in smallest units.
        decimals: Token decimal places.

    Returns:
        Formatted amount string.
    """
    value = int(raw) / (10 ** decimals)
    if value >= 1.0:
        return f"{value:,.4f}"
    return f"{value:,.{decimals}f}"


def display_quote_summary(quote: dict) -> None:
    """Print a concise quote summary.

    Args:
        quote: Jupiter quote response.
    """
    in_dec = KNOWN_DECIMALS.get(quote["inputMint"], 9)
    out_dec = KNOWN_DECIMALS.get(quote["outputMint"], 6)
    in_sym = "SOL" if quote["inputMint"] == SOL_MINT else quote["inputMint"][:8] + "..."
    out_sym = "USDC" if quote["outputMint"] == USDC_MINT else quote["outputMint"][:8] + "..."

    in_amt = format_amount(quote["inAmount"], in_dec)
    out_amt = format_amount(quote["outAmount"], out_dec)
    min_amt = format_amount(quote["otherAmountThreshold"], out_dec)
    impact = float(quote.get("priceImpactPct", "0"))

    route_parts = []
    for step in quote.get("routePlan", []):
        label = step.get("swapInfo", {}).get("label", "?")
        route_parts.append(label)
    route_str = " → ".join(route_parts) if route_parts else "Unknown"

    print("─── Quote Summary ────────────────────────────────────────")
    print(f"  Sell:        {in_amt} {in_sym}")
    print(f"  Buy:         ~{out_amt} {out_sym}")
    print(f"  Min recv:    {min_amt} {out_sym}")
    print(f"  Impact:      {impact:.4f}%")
    print(f"  Slippage:    {quote.get('slippageBps', 0) / 100:.2f}%")
    print(f"  Route:       {route_str}")
    print()


def display_swap_details(swap_data: dict) -> None:
    """Print swap transaction build details.

    Args:
        swap_data: Jupiter swap response.
    """
    tx_b64 = swap_data.get("swapTransaction", "")
    tx_bytes = base64.b64decode(tx_b64) if tx_b64 else b""
    last_block = swap_data.get("lastValidBlockHeight", "N/A")
    priority = swap_data.get("prioritizationFeeLamports", "N/A")
    cu_limit = swap_data.get("computeUnitLimit", "N/A")

    dynamic = swap_data.get("dynamicSlippageReport")

    print("─── Swap Transaction Details ─────────────────────────────")
    print(f"  Transaction size:    {len(tx_bytes)} bytes")
    print(f"  Last valid block:    {last_block}")
    print(f"  Priority fee:        {priority} lamports")
    print(f"  Compute unit limit:  {cu_limit}")

    if dynamic:
        print(f"  Dynamic slippage:    {dynamic.get('slippageBps', 'N/A')} bps")
        sim_slip = dynamic.get("simulatedIncurredSlippageBps", "N/A")
        print(f"  Simulated slippage:  {sim_slip} bps")
    print()


def display_simulation_result(sim_result: dict) -> None:
    """Print simulation results.

    Args:
        sim_result: Simulation value from RPC response.
    """
    err = sim_result.get("err")
    units = sim_result.get("unitsConsumed", 0)
    logs = sim_result.get("logs", [])

    print("─── Simulation Result ────────────────────────────────────")

    if err is None:
        print("  Status:     SUCCESS")
        print(f"  Compute:    {units:,} units consumed")
    else:
        print("  Status:     FAILED")
        print(f"  Error:      {err}")
        print(f"  Compute:    {units:,} units consumed")

    # Show last N log lines (most informative)
    if logs:
        print()
        print("  Logs (last 15 lines):")
        for line in logs[-15:]:
            # Truncate long log lines
            if len(line) > 100:
                line = line[:97] + "..."
            print(f"    {line}")

    print()

    if err is None:
        print("  ✓ Transaction would succeed if signed and submitted.")
    else:
        print("  ✗ Transaction would FAIL. Check error and logs above.")

    print()
    print("─── REMINDER: This was a SIMULATION only. ────────────────")
    print("  No transaction was signed, submitted, or executed.")
    print("─────────────────────────────────────────────────────────")
    print()


# ── Pipeline ────────────────────────────────────────────────────────

def run_simulation(
    client: httpx.Client,
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int,
    user_pubkey: str,
    rpc_url: str,
) -> bool:
    """Run the full quote → build → simulate pipeline.

    Args:
        client: HTTP client instance.
        input_mint: Input token mint.
        output_mint: Output token mint.
        amount: Input amount in smallest units.
        slippage_bps: Slippage tolerance in basis points.
        user_pubkey: Wallet public key.
        rpc_url: Solana RPC URL.

    Returns:
        True if simulation succeeded, False otherwise.
    """
    # Step 1: Get quote
    print("Step 1/3: Fetching Jupiter quote...")
    quote = fetch_quote(client, input_mint, output_mint, amount, slippage_bps)
    if not quote:
        print("Failed to fetch quote. Aborting.")
        return False
    display_quote_summary(quote)

    # Safety check: price impact
    impact = float(quote.get("priceImpactPct", "0"))
    if impact > 10.0:
        print(f"BLOCKED: Price impact {impact:.2f}% exceeds 10% safety limit.")
        print("This trade would likely result in significant loss.")
        return False
    elif impact > 5.0:
        print(f"WARNING: High price impact ({impact:.2f}%). In production,")
        print("this would require explicit user override.")

    # Step 2: Build swap transaction
    print("Step 2/3: Building swap transaction...")
    swap_data = build_swap_transaction(client, quote, user_pubkey)
    if not swap_data:
        print("Failed to build swap transaction. Aborting.")
        return False

    swap_tx_b64 = swap_data.get("swapTransaction", "")
    if not swap_tx_b64:
        print("No transaction returned from Jupiter. Aborting.")
        return False
    display_swap_details(swap_data)

    # Step 3: Simulate
    print("Step 3/3: Simulating transaction via RPC...")
    sim_result = simulate_transaction(client, rpc_url, swap_tx_b64)
    if sim_result is None:
        print("RPC simulation call failed. This may be a network issue.")
        print("The transaction itself may still be valid.")
        return False
    display_simulation_result(sim_result)

    return sim_result.get("err") is None


# ── Main ────────────────────────────────────────────────────────────

def run_demo(client: httpx.Client) -> None:
    """Run demo simulation with SOL → USDC.

    Note: Demo uses a system account as pubkey, so the swap build
    may fail (account doesn't hold SOL). This demonstrates the
    pipeline and error handling.

    Args:
        client: HTTP client instance.
    """
    print("Running demo: Simulate 1 SOL → USDC swap")
    print(f"Using demo pubkey: {DEMO_PUBKEY[:16]}...")
    print("(Demo account may not have balance — build/simulation may fail)")
    print()

    run_simulation(
        client=client,
        input_mint=SOL_MINT,
        output_mint=USDC_MINT,
        amount=1_000_000_000,
        slippage_bps=50,
        user_pubkey=DEMO_PUBKEY,
        rpc_url=SOLANA_RPC_URL,
    )


def main() -> None:
    """Main entry point."""
    print(SAFETY_BANNER)

    demo_mode = "--demo" in sys.argv

    with httpx.Client() as client:
        if demo_mode:
            run_demo(client)
            return

        if not USER_PUBKEY:
            print("ERROR: USER_PUBKEY environment variable is required.")
            print("Set it to your wallet's public key (base58 format).")
            print()
            print("Example:")
            print('  USER_PUBKEY="YourPubkeyHere" python scripts/simulate_swap.py')
            print()
            print("Or run in demo mode:")
            print("  python scripts/simulate_swap.py --demo")
            sys.exit(1)

        print(f"Configuration:")
        print(f"  Input mint:   {INPUT_MINT}")
        print(f"  Output mint:  {OUTPUT_MINT}")
        print(f"  Amount:       {AMOUNT_LAMPORTS} (smallest units)")
        print(f"  Slippage:     {SLIPPAGE_BPS} bps")
        print(f"  Wallet:       {USER_PUBKEY[:16]}...")
        print(f"  RPC:          {SOLANA_RPC_URL[:40]}...")
        print()

        success = run_simulation(
            client=client,
            input_mint=INPUT_MINT,
            output_mint=OUTPUT_MINT,
            amount=AMOUNT_LAMPORTS,
            slippage_bps=SLIPPAGE_BPS,
            user_pubkey=USER_PUBKEY,
            rpc_url=SOLANA_RPC_URL,
        )

        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
