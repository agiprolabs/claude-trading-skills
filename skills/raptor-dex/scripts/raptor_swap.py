#!/usr/bin/env python3
"""Full Raptor swap flow: quote → build → sign → submit → confirm.

Demonstrates the complete swap lifecycle using Raptor's HTTP API.
In --demo mode, uses mock data and simulates each step without
connecting to Raptor or signing any transactions.

Usage:
    python scripts/raptor_swap.py --demo
    python scripts/raptor_swap.py --input So11... --output EPjF... --amount 1000000000

Dependencies:
    uv pip install httpx
    uv pip install solders  (for live signing only)

Environment Variables:
    RAPTOR_URL: Raptor instance URL (default: http://localhost:8080)
    PRIVATE_KEY: Base58-encoded private key (live mode only, NEVER hardcode)
"""

import argparse
import base64
import json
import os
import sys
import time
from typing import Optional

RAPTOR_URL = os.getenv("RAPTOR_URL", "http://localhost:8080")

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


# ── Demo Data ───────────────────────────────────────────────────────

DEMO_QUOTE = {
    "amountIn": 100_000_000,
    "amountOut": 15_623_456,
    "otherAmountThreshold": 15_545_339,
    "priceImpact": 0.02,
    "slippageBps": 50,
    "routePlan": [
        {
            "inputMint": SOL_MINT,
            "outputMint": USDC_MINT,
            "amountIn": 100_000_000,
            "amountOut": 15_623_456,
            "dex": "raydium_clmm",
            "pool": "7XawhbbxtsRcQA8KTkHT9f9nc6d69UwqCDh6U5EEbEmX",
        }
    ],
    "contextSlot": 298_765_432,
}

DEMO_SWAP_TX = base64.b64encode(b"DEMO_UNSIGNED_TRANSACTION_BYTES_" * 4).decode()
DEMO_SIGNATURE = "5RzEHTnf5bLFDhWdPz1MzBE5c8K5MZxKiVrt7hL8cmH7aJBrFQ2DGNYw5jNzVQ6gTk3BQkXyL8v9cCXW4HFnmFy"


# ── Core Functions ──────────────────────────────────────────────────


def step_1_get_quote(
    input_mint: str, output_mint: str, amount: int, slippage_bps: int = 50
) -> dict:
    """Step 1: Get swap quote from Raptor.

    Args:
        input_mint: Input token mint.
        output_mint: Output token mint.
        amount: Amount in smallest unit.
        slippage_bps: Slippage tolerance.

    Returns:
        Quote response.
    """
    import httpx

    resp = httpx.get(
        f"{RAPTOR_URL}/quote",
        params={
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "slippageBps": slippage_bps,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def step_2_build_swap(
    quote: dict,
    user_pubkey: str,
    priority_fee: str = "auto",
    max_priority_fee: int = 100_000,
) -> str:
    """Step 2: Build unsigned swap transaction.

    Args:
        quote: Quote response from step 1.
        user_pubkey: Wallet public key.
        priority_fee: Fee level (min/low/auto/medium/high/veryHigh/turbo/unsafeMax).
        max_priority_fee: Maximum priority fee in lamports.

    Returns:
        Base64-encoded unsigned transaction.
    """
    import httpx

    resp = httpx.post(
        f"{RAPTOR_URL}/swap",
        json={
            "quoteResponse": quote,
            "userPublicKey": user_pubkey,
            "wrapUnwrapSol": True,
            "txVersion": "v0",
            "priorityFee": priority_fee,
            "maxPriorityFee": max_priority_fee,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()["swapTransaction"]


def step_3_sign_transaction(tx_b64: str, private_key_b58: str) -> str:
    """Step 3: Sign the transaction locally.

    Args:
        tx_b64: Base64-encoded unsigned transaction.
        private_key_b58: Base58-encoded private key.

    Returns:
        Base64-encoded signed transaction.
    """
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction

    tx_bytes = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    keypair = Keypair.from_base58_string(private_key_b58)
    signed = VersionedTransaction(tx.message, [keypair])
    return base64.b64encode(bytes(signed)).decode()


def step_4_send_transaction(signed_tx_b64: str) -> str:
    """Step 4: Submit signed transaction via Yellowstone Jet TPU.

    Args:
        signed_tx_b64: Base64-encoded signed transaction.

    Returns:
        Transaction signature.
    """
    import httpx

    resp = httpx.post(
        f"{RAPTOR_URL}/send-transaction",
        json={"transaction": signed_tx_b64},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["signature"]


def step_5_confirm_transaction(signature: str, timeout_s: int = 30) -> dict:
    """Step 5: Wait for transaction confirmation.

    Args:
        signature: Transaction signature.
        timeout_s: Maximum wait time in seconds.

    Returns:
        Transaction status response.
    """
    import httpx

    start = time.time()
    while time.time() - start < timeout_s:
        resp = httpx.get(f"{RAPTOR_URL}/transaction/{signature}", timeout=10.0)
        if resp.status_code == 404:
            time.sleep(1)
            continue
        resp.raise_for_status()
        status = resp.json()
        if status.get("status") in ("confirmed", "failed", "expired"):
            return status
        time.sleep(1)
    return {"status": "timeout", "signature": signature}


def display_step(step_num: int, title: str, details: dict) -> None:
    """Display a step result.

    Args:
        step_num: Step number.
        title: Step title.
        details: Key-value pairs to display.
    """
    print(f"\n  Step {step_num}: {title}")
    print(f"  {'─' * 40}")
    for k, v in details.items():
        print(f"    {k}: {v}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Execute full Raptor swap flow."""
    parser = argparse.ArgumentParser(description="Raptor swap flow")
    parser.add_argument("--demo", action="store_true", help="Simulate with mock data")
    parser.add_argument("--input", default=SOL_MINT, help="Input mint")
    parser.add_argument("--output", default=USDC_MINT, help="Output mint")
    parser.add_argument("--amount", type=int, default=100_000_000, help="Amount (lamports)")
    parser.add_argument("--slippage", type=int, default=50, help="Slippage (bps)")
    parser.add_argument("--priority-fee", default="auto", help="Priority fee level")
    args = parser.parse_args()

    if args.demo:
        print("=" * 50)
        print("  RAPTOR SWAP FLOW (Demo / Simulation)")
        print("=" * 50)
        print(f"  Raptor URL: {RAPTOR_URL} (not connected)")
        print(f"  Swap: 0.1 SOL → USDC")

        # Step 1
        quote = DEMO_QUOTE
        sol_in = quote["amountIn"] / 1e9
        usdc_out = quote["amountOut"] / 1e6
        display_step(1, "GET /quote", {
            "Input": f"{sol_in} SOL",
            "Output": f"{usdc_out:.6f} USDC",
            "Price": f"${usdc_out / sol_in:.4f}/SOL",
            "Impact": f"{quote['priceImpact']}%",
            "Route": f"{len(quote['routePlan'])} hop(s) via {quote['routePlan'][0]['dex']}",
            "Slot": f"{quote['contextSlot']:,}",
        })

        # Step 2
        display_step(2, "POST /swap (build transaction)", {
            "Transaction": f"{DEMO_SWAP_TX[:40]}...",
            "Priority fee": "auto",
            "Wrap/Unwrap SOL": "true",
            "Version": "v0",
        })

        # Step 3
        display_step(3, "Sign locally", {
            "Signer": "DemoWa11et... (private key never sent to Raptor)",
            "Signed tx": f"{DEMO_SWAP_TX[:40]}... (simulated)",
        })

        # Step 4
        display_step(4, "POST /send-transaction (Yellowstone Jet TPU)", {
            "Signature": DEMO_SIGNATURE[:40] + "...",
            "Submission": "Auto-retry for ~30 seconds",
        })

        # Step 5
        display_step(5, "GET /transaction/{sig} (confirm)", {
            "Status": "confirmed",
            "Latency": "~450ms",
            "Slot": "298,765,433",
        })

        print(f"\n{'=' * 50}")
        print("  SWAP COMPLETE (simulated)")
        print(f"{'=' * 50}")
        print(f"  Swapped: {sol_in} SOL → {usdc_out:.6f} USDC")
        print(f"  Signature: {DEMO_SIGNATURE[:40]}...")
        print()

        print("  ⚠️  This was a simulation. No real transaction was sent.")
        print("  ⚠️  For live swaps, run without --demo and set PRIVATE_KEY.")
        print()
        return

    # Live mode
    try:
        import httpx  # noqa: F811
    except ImportError:
        print("httpx is required. Install with: uv pip install httpx")
        sys.exit(1)

    private_key = os.getenv("PRIVATE_KEY", "")
    if not private_key:
        print("⚠️  PRIVATE_KEY not set. Cannot sign transactions.")
        print("Set PRIVATE_KEY environment variable with your base58 private key.")
        print("For quote-only mode, use raptor_quote.py instead.")
        sys.exit(1)

    # Derive public key
    try:
        from solders.keypair import Keypair

        keypair = Keypair.from_base58_string(private_key)
        user_pubkey = str(keypair.pubkey())
    except ImportError:
        print("solders is required for live mode. Install with: uv pip install solders")
        sys.exit(1)

    print(f"Raptor URL: {RAPTOR_URL}")
    print(f"Wallet: {user_pubkey}")
    print(f"Swap: {args.amount} lamports of {args.input[:8]}... → {args.output[:8]}...")

    # Confirmation gate
    print("\n⚠️  THIS WILL EXECUTE A REAL SWAP WITH REAL FUNDS ⚠️")
    confirm = input("Type 'yes' to proceed: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        sys.exit(0)

    quote = step_1_get_quote(args.input, args.output, args.amount, args.slippage)
    print(f"Quote: {quote['amountOut']} output, {quote['priceImpact']}% impact")

    tx_b64 = step_2_build_swap(quote, user_pubkey, args.priority_fee)
    print(f"Transaction built: {len(tx_b64)} chars")

    signed_b64 = step_3_sign_transaction(tx_b64, private_key)
    print("Transaction signed locally")

    signature = step_4_send_transaction(signed_b64)
    print(f"Submitted: {signature}")

    status = step_5_confirm_transaction(signature)
    print(f"Result: {status.get('status')} (latency: {status.get('latency_ms', '?')}ms)")
    print()


if __name__ == "__main__":
    main()
