#!/usr/bin/env python3
"""Build a Jito bundle with tip instruction for MEV-protected execution.

Demonstrates bundle construction with a SOL transfer + tip. In --demo mode,
builds the bundle payload locally using mock data without submitting to the
block engine or requiring any API keys.

SAFETY WARNING: Without --demo, this script submits real bundles that spend
real SOL on tips. Always test with --demo first.

Usage:
    python scripts/build_bundle.py --demo
    python scripts/build_bundle.py --tip 25000 --endpoint mainnet

Dependencies:
    uv pip install httpx

Environment Variables:
    JITO_BLOCK_ENGINE: Block engine endpoint (default: mainnet)
    SOLANA_RPC_URL: Solana RPC endpoint for blockhash fetching
"""

import argparse
import json
import os
import sys
import time
import random
import base64
import hashlib
from typing import Optional

# ── Configuration ───────────────────────────────────────────────────

BLOCK_ENGINE_URLS = {
    "mainnet": "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
    "amsterdam": "https://amsterdam.block-engine.jito.wtf/api/v1/bundles",
    "frankfurt": "https://frankfurt.block-engine.jito.wtf/api/v1/bundles",
    "tokyo": "https://tokyo.block-engine.jito.wtf/api/v1/bundles",
}

DEFAULT_TIP_LAMPORTS = 25_000  # 0.000025 SOL
MAX_TIP_LAMPORTS = 10_000_000  # 0.01 SOL safety cap

# Known Jito tip accounts (fetched dynamically in production)
DEMO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4bVqkfRtQ7NmXwkiAMXBiap",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2o2J3mF9Cp4vFsMhBBe6Vy",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]


# ── Helper Functions ────────────────────────────────────────────────

def select_tip_account(tip_accounts: list[str]) -> str:
    """Select a random tip account for load distribution.

    Args:
        tip_accounts: List of Jito tip account public keys.

    Returns:
        A randomly selected tip account public key.
    """
    return random.choice(tip_accounts)


def safe_tip(tip_lamports: int) -> int:
    """Apply safety cap to tip amount.

    Args:
        tip_lamports: Requested tip in lamports.

    Returns:
        Tip capped at MAX_TIP_LAMPORTS.
    """
    if tip_lamports > MAX_TIP_LAMPORTS:
        print(
            f"WARNING: Tip {tip_lamports} lamports exceeds safety cap "
            f"{MAX_TIP_LAMPORTS}. Capping to {MAX_TIP_LAMPORTS}."
        )
        return MAX_TIP_LAMPORTS
    if tip_lamports < 0:
        print("WARNING: Negative tip not allowed. Using 0.")
        return 0
    return tip_lamports


def lamports_to_sol(lamports: int) -> float:
    """Convert lamports to SOL.

    Args:
        lamports: Amount in lamports.

    Returns:
        Amount in SOL.
    """
    return lamports / 1_000_000_000


def build_demo_bundle_payload(
    tip_lamports: int,
    tip_account: str,
    num_transactions: int = 1,
) -> dict:
    """Build a mock bundle payload for demonstration.

    This constructs the JSON-RPC payload structure that would be sent
    to the Jito block engine. In demo mode, the transactions are
    placeholder strings (not real signed transactions).

    Args:
        tip_lamports: Tip amount in lamports.
        tip_account: Selected Jito tip account.
        num_transactions: Number of transactions in the bundle (1-5).

    Returns:
        JSON-RPC request payload dict.
    """
    if num_transactions < 1 or num_transactions > 5:
        raise ValueError("Bundle must contain 1-5 transactions")

    # Generate mock base58-encoded "transactions"
    mock_txs = []
    for i in range(num_transactions):
        # Create a deterministic mock transaction for reproducibility
        mock_data = f"demo_tx_{i}_{tip_lamports}_{tip_account[:8]}"
        mock_hash = hashlib.sha256(mock_data.encode()).hexdigest()
        mock_txs.append(f"DEMO_{mock_hash[:44]}")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [mock_txs],
    }
    return payload


def fetch_tip_accounts(block_engine_url: str) -> list[str]:
    """Fetch current Jito tip accounts from the block engine.

    Args:
        block_engine_url: Jito block engine API URL.

    Returns:
        List of tip account public keys.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        RuntimeError: If the response format is unexpected.
    """
    import httpx

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTipAccounts",
        "params": [],
    }
    resp = httpx.post(block_engine_url, json=payload, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"getTipAccounts error: {data['error']}")
    if "result" not in data or not isinstance(data["result"], list):
        raise RuntimeError(f"Unexpected response format: {data}")

    return data["result"]


def submit_bundle(
    block_engine_url: str,
    bundle_txs: list[str],
) -> str:
    """Submit a bundle to the Jito block engine.

    Args:
        block_engine_url: Jito block engine API URL.
        bundle_txs: List of base58-encoded signed transactions.

    Returns:
        Bundle UUID string.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        RuntimeError: If the bundle submission returns an error.
    """
    import httpx

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [bundle_txs],
    }
    resp = httpx.post(block_engine_url, json=payload, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(
            f"sendBundle error: {data['error'].get('message', data['error'])}"
        )
    if "result" not in data:
        raise RuntimeError(f"Unexpected response: {data}")

    return data["result"]


# ── Demo Mode ───────────────────────────────────────────────────────

def run_demo(tip_lamports: int, num_transactions: int = 1) -> None:
    """Run bundle construction in demo mode with mock data.

    Args:
        tip_lamports: Tip amount in lamports.
        num_transactions: Number of transactions in the bundle.
    """
    print("=" * 60)
    print("JITO BUNDLE BUILDER — DEMO MODE")
    print("=" * 60)
    print()

    # Step 1: Select tip account
    tip_account = select_tip_account(DEMO_TIP_ACCOUNTS)
    print(f"[1/4] Selected tip account: {tip_account}")
    print(f"       (randomly chosen from {len(DEMO_TIP_ACCOUNTS)} accounts)")
    print()

    # Step 2: Calculate tip
    final_tip = safe_tip(tip_lamports)
    print(f"[2/4] Tip amount: {final_tip:,} lamports ({lamports_to_sol(final_tip):.9f} SOL)")
    print(f"       Safety cap: {MAX_TIP_LAMPORTS:,} lamports ({lamports_to_sol(MAX_TIP_LAMPORTS):.6f} SOL)")
    print()

    # Step 3: Build bundle payload
    payload = build_demo_bundle_payload(
        tip_lamports=final_tip,
        tip_account=tip_account,
        num_transactions=num_transactions,
    )
    print(f"[3/4] Built bundle with {num_transactions} transaction(s)")
    print(f"       Method: {payload['method']}")
    print(f"       Transactions in bundle: {len(payload['params'][0])}")
    print()

    # Step 4: Show what would be sent
    print("[4/4] Bundle payload (would be sent to block engine):")
    print("-" * 60)
    print(json.dumps(payload, indent=2))
    print("-" * 60)
    print()

    # Summary
    print("BUNDLE CONSTRUCTION SUMMARY")
    print(f"  Transactions:  {num_transactions}")
    print(f"  Tip account:   {tip_account}")
    print(f"  Tip amount:    {final_tip:,} lamports")
    print(f"  Tip (SOL):     {lamports_to_sol(final_tip):.9f} SOL")
    print(f"  Tip position:  Last instruction of transaction {num_transactions}")
    print(f"  Status:        NOT SUBMITTED (demo mode)")
    print()
    print("To submit for real, run without --demo (requires signed transactions).")


# ── Live Mode ───────────────────────────────────────────────────────

def run_live(
    tip_lamports: int,
    endpoint_name: str,
) -> None:
    """Run bundle submission against the live block engine.

    This function demonstrates the submission flow but requires real
    signed transactions to actually work. It fetches tip accounts
    from the block engine and shows the submission process.

    Args:
        tip_lamports: Tip amount in lamports.
        endpoint_name: Block engine endpoint name.
    """
    block_engine_url = BLOCK_ENGINE_URLS.get(endpoint_name)
    if not block_engine_url:
        print(f"Unknown endpoint: {endpoint_name}")
        print(f"Available: {', '.join(BLOCK_ENGINE_URLS.keys())}")
        sys.exit(1)

    print("=" * 60)
    print("JITO BUNDLE BUILDER — LIVE MODE")
    print(f"Endpoint: {block_engine_url}")
    print("=" * 60)
    print()

    print("WARNING: Live mode requires real signed transactions.")
    print("This demonstration fetches tip accounts but does not submit")
    print("because building real transactions requires wallet keys.")
    print()

    try:
        print("[1/3] Fetching tip accounts from block engine...")
        tip_accounts = fetch_tip_accounts(block_engine_url)
        print(f"       Retrieved {len(tip_accounts)} tip accounts:")
        for i, acct in enumerate(tip_accounts):
            print(f"         [{i}] {acct}")
        print()

        tip_account = select_tip_account(tip_accounts)
        final_tip = safe_tip(tip_lamports)
        print(f"[2/3] Selected tip account: {tip_account}")
        print(f"       Tip: {final_tip:,} lamports ({lamports_to_sol(final_tip):.9f} SOL)")
        print()

        print("[3/3] To submit a real bundle, you would need to:")
        print("  1. Build transaction(s) with solders or solana-py")
        print("  2. Add tip transfer as last instruction of last tx")
        print("  3. Sign all transactions with your wallet keypair")
        print("  4. Base58-encode the signed transactions")
        print("  5. Call sendBundle with the encoded transactions")
        print()
        print("See SKILL.md for complete bundle construction examples.")

    except Exception as e:
        print(f"Error: {e}")
        print("Check your network connection and endpoint availability.")
        sys.exit(1)


# ── Main ────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Build a Jito bundle with tip instruction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/build_bundle.py --demo\n"
            "  python scripts/build_bundle.py --demo --tip 50000 --txs 3\n"
            "  python scripts/build_bundle.py --endpoint mainnet --tip 25000\n"
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with mock data (no API calls, no keys needed)",
    )
    parser.add_argument(
        "--tip",
        type=int,
        default=DEFAULT_TIP_LAMPORTS,
        help=f"Tip amount in lamports (default: {DEFAULT_TIP_LAMPORTS})",
    )
    parser.add_argument(
        "--txs",
        type=int,
        default=1,
        choices=range(1, 6),
        help="Number of transactions in the bundle (1-5, default: 1)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="mainnet",
        choices=list(BLOCK_ENGINE_URLS.keys()),
        help="Block engine endpoint (default: mainnet)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.demo:
        run_demo(tip_lamports=args.tip, num_transactions=args.txs)
    else:
        run_live(tip_lamports=args.tip, endpoint_name=args.endpoint)
