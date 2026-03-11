#!/usr/bin/env python3
"""Check Jito bundle status and fetch tip accounts.

In --demo mode, uses mock responses to demonstrate the status-checking
workflow without requiring network access or API keys. In live mode,
queries the Jito block engine for real bundle statuses.

Usage:
    python scripts/check_bundle_status.py --demo
    python scripts/check_bundle_status.py --demo --bundle-id abc123
    python scripts/check_bundle_status.py --bundle-id <real-uuid> --endpoint mainnet
    python scripts/check_bundle_status.py --tip-accounts --endpoint mainnet

Dependencies:
    uv pip install httpx

Environment Variables:
    JITO_BLOCK_ENGINE: Block engine endpoint name (default: mainnet)
"""

import argparse
import json
import os
import sys
import time
from typing import Optional

# ── Configuration ───────────────────────────────────────────────────

BLOCK_ENGINE_URLS = {
    "mainnet": "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
    "amsterdam": "https://amsterdam.block-engine.jito.wtf/api/v1/bundles",
    "frankfurt": "https://frankfurt.block-engine.jito.wtf/api/v1/bundles",
    "tokyo": "https://tokyo.block-engine.jito.wtf/api/v1/bundles",
}

# Mock data for demo mode
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

DEMO_BUNDLE_STATUSES = {
    "landed": {
        "bundle_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "transactions": [
            {
                "signature": "5rGzK8mVpEr2nT9xQwYJk3Fp4BsVH7m1dC6yNqRfW8aL"
                             "p2sXjMv4uDhZ9bK1cA3nE7tG6wF5rHq8iJ0kL",
                "slot": 280000000,
                "confirmation_status": "confirmed",
                "err": None,
            }
        ],
        "slot": 280000000,
        "confirmation_status": "confirmed",
        "err": {"Ok": None},
    },
    "pending": {
        "bundle_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "status": "Pending",
        "landed_slot": None,
    },
    "failed": {
        "bundle_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
        "status": "Failed",
        "landed_slot": None,
    },
}


# ── Core Functions ──────────────────────────────────────────────────

def fetch_tip_accounts_live(block_engine_url: str) -> list[str]:
    """Fetch tip accounts from the live Jito block engine.

    Args:
        block_engine_url: Full URL to the block engine bundles API.

    Returns:
        List of tip account public keys.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        RuntimeError: On unexpected response format.
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
    return data.get("result", [])


def get_bundle_statuses_live(
    block_engine_url: str,
    bundle_ids: list[str],
) -> list[Optional[dict]]:
    """Check bundle statuses from the live Jito block engine.

    Args:
        block_engine_url: Full URL to the block engine bundles API.
        bundle_ids: List of bundle UUIDs to check (max 5).

    Returns:
        List of status dicts (or None for unknown bundles).

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        RuntimeError: On unexpected response format.
    """
    import httpx

    if len(bundle_ids) > 5:
        raise ValueError("Maximum 5 bundle IDs per request")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBundleStatuses",
        "params": [bundle_ids],
    }
    resp = httpx.post(block_engine_url, json=payload, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"getBundleStatuses error: {data['error']}")

    result = data.get("result", {})
    return result.get("value", [])


def get_inflight_statuses_live(
    block_engine_url: str,
    bundle_ids: list[str],
) -> list[Optional[dict]]:
    """Check in-flight bundle statuses from the live Jito block engine.

    Args:
        block_engine_url: Full URL to the block engine bundles API.
        bundle_ids: List of bundle UUIDs to check (max 5).

    Returns:
        List of in-flight status dicts.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        RuntimeError: On unexpected response format.
    """
    import httpx

    if len(bundle_ids) > 5:
        raise ValueError("Maximum 5 bundle IDs per request")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getInflightBundleStatuses",
        "params": [bundle_ids],
    }
    resp = httpx.post(block_engine_url, json=payload, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(
            f"getInflightBundleStatuses error: {data['error']}"
        )

    result = data.get("result", {})
    return result.get("value", [])


def format_status(status: Optional[dict]) -> str:
    """Format a bundle status dict into a human-readable string.

    Args:
        status: Bundle status dict from the API, or None.

    Returns:
        Formatted status string.
    """
    if status is None:
        return "  Status: NOT FOUND (expired, invalid ID, or not yet processed)"

    lines = []
    bundle_id = status.get("bundle_id", "unknown")
    lines.append(f"  Bundle ID: {bundle_id}")

    # getBundleStatuses format
    if "confirmation_status" in status:
        lines.append(f"  Confirmation: {status['confirmation_status']}")
        lines.append(f"  Slot: {status.get('slot', 'unknown')}")
        err = status.get("err", {})
        if err and err.get("Ok") is None:
            lines.append("  Error: None (success)")
        elif err:
            lines.append(f"  Error: {err}")
        txs = status.get("transactions", [])
        if txs:
            lines.append(f"  Transactions ({len(txs)}):")
            for tx in txs:
                sig = tx.get("signature", "unknown")
                lines.append(f"    Sig: {sig[:20]}...")
                lines.append(f"    Slot: {tx.get('slot', 'unknown')}")
                lines.append(
                    f"    Status: {tx.get('confirmation_status', 'unknown')}"
                )

    # getInflightBundleStatuses format
    elif "status" in status:
        lines.append(f"  Status: {status['status']}")
        landed = status.get("landed_slot")
        if landed:
            lines.append(f"  Landed Slot: {landed}")

    return "\n".join(lines)


# ── Demo Mode ───────────────────────────────────────────────────────

def run_demo_tip_accounts() -> None:
    """Display mock tip accounts in demo mode."""
    print("TIP ACCOUNTS (demo data):")
    print("-" * 60)
    for i, account in enumerate(DEMO_TIP_ACCOUNTS):
        print(f"  [{i}] {account}")
    print(f"\nTotal: {len(DEMO_TIP_ACCOUNTS)} accounts")
    print("Tip account selection: random rotation recommended")


def run_demo_status(bundle_id: Optional[str]) -> None:
    """Display mock bundle statuses in demo mode.

    Args:
        bundle_id: Optional bundle ID to check. If None, shows all demo statuses.
    """
    print("BUNDLE STATUS CHECK (demo data):")
    print("-" * 60)

    if bundle_id:
        # Show a single mock status
        print(f"\nChecking bundle: {bundle_id}")
        print()
        # Use the "landed" mock for any provided ID
        mock = DEMO_BUNDLE_STATUSES["landed"].copy()
        mock["bundle_id"] = bundle_id
        print(format_status(mock))
    else:
        # Show all demo scenarios
        print("\nScenario 1 — LANDED bundle:")
        print(format_status(DEMO_BUNDLE_STATUSES["landed"]))
        print()
        print("Scenario 2 — PENDING bundle (in-flight):")
        print(format_status(DEMO_BUNDLE_STATUSES["pending"]))
        print()
        print("Scenario 3 — FAILED bundle:")
        print(format_status(DEMO_BUNDLE_STATUSES["failed"]))
        print()
        print("Scenario 4 — NOT FOUND (expired or invalid):")
        print(format_status(None))


def run_demo(bundle_id: Optional[str], show_tip_accounts: bool) -> None:
    """Run the full demo workflow.

    Args:
        bundle_id: Optional bundle ID to check status for.
        show_tip_accounts: Whether to display tip accounts.
    """
    print("=" * 60)
    print("JITO BUNDLE STATUS CHECKER — DEMO MODE")
    print("=" * 60)
    print()

    if show_tip_accounts:
        run_demo_tip_accounts()
        print()

    run_demo_status(bundle_id)

    print()
    print("STATUS INTERPRETATION:")
    print("  Landed    — Bundle successfully included in a block")
    print("  Pending   — Bundle received, waiting for slot inclusion")
    print("  Failed    — Bundle failed simulation or expired")
    print("  Not Found — Bundle expired, ID invalid, or not yet seen")
    print()
    print("RECOMMENDED WORKFLOW:")
    print("  1. Submit bundle via sendBundle → get bundle_id")
    print("  2. Wait 1-2 seconds")
    print("  3. Check getInflightBundleStatuses (for in-flight bundles)")
    print("  4. Check getBundleStatuses (for landed bundles)")
    print("  5. If not found after 3s, rebuild with fresh blockhash and retry")


# ── Live Mode ───────────────────────────────────────────────────────

def run_live(
    bundle_id: Optional[str],
    show_tip_accounts: bool,
    endpoint_name: str,
) -> None:
    """Run against the live Jito block engine.

    Args:
        bundle_id: Bundle UUID to check status for.
        show_tip_accounts: Whether to fetch and display tip accounts.
        endpoint_name: Block engine endpoint name.
    """
    block_engine_url = BLOCK_ENGINE_URLS.get(endpoint_name)
    if not block_engine_url:
        print(f"Unknown endpoint: {endpoint_name}")
        print(f"Available: {', '.join(BLOCK_ENGINE_URLS.keys())}")
        sys.exit(1)

    print("=" * 60)
    print("JITO BUNDLE STATUS CHECKER — LIVE MODE")
    print(f"Endpoint: {block_engine_url}")
    print("=" * 60)
    print()

    try:
        if show_tip_accounts:
            print("Fetching tip accounts...")
            accounts = fetch_tip_accounts_live(block_engine_url)
            print(f"Retrieved {len(accounts)} tip accounts:")
            for i, acct in enumerate(accounts):
                print(f"  [{i}] {acct}")
            print()

        if bundle_id:
            print(f"Checking bundle: {bundle_id}")
            print()

            # Try getBundleStatuses first
            print("[getBundleStatuses]")
            statuses = get_bundle_statuses_live(block_engine_url, [bundle_id])
            if statuses:
                for s in statuses:
                    print(format_status(s))
            else:
                print("  No results returned")
            print()

            # Also check in-flight
            print("[getInflightBundleStatuses]")
            inflight = get_inflight_statuses_live(
                block_engine_url, [bundle_id]
            )
            if inflight:
                for s in inflight:
                    print(format_status(s))
            else:
                print("  No in-flight results (bundle may have landed or expired)")

        elif not show_tip_accounts:
            print("No action specified. Use --bundle-id or --tip-accounts.")
            print("Run with --help for usage information.")

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
        description="Check Jito bundle status and fetch tip accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/check_bundle_status.py --demo\n"
            "  python scripts/check_bundle_status.py --demo --bundle-id abc-123\n"
            "  python scripts/check_bundle_status.py --tip-accounts --endpoint mainnet\n"
            "  python scripts/check_bundle_status.py --bundle-id <uuid> --endpoint mainnet\n"
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with mock responses (no network calls)",
    )
    parser.add_argument(
        "--bundle-id",
        type=str,
        default=None,
        help="Bundle UUID to check status for",
    )
    parser.add_argument(
        "--tip-accounts",
        action="store_true",
        help="Fetch and display current Jito tip accounts",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=os.getenv("JITO_BLOCK_ENGINE", "mainnet"),
        choices=list(BLOCK_ENGINE_URLS.keys()),
        help="Block engine endpoint (default: mainnet or JITO_BLOCK_ENGINE env)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.demo:
        run_demo(
            bundle_id=args.bundle_id,
            show_tip_accounts=args.tip_accounts,
        )
    else:
        run_live(
            bundle_id=args.bundle_id,
            show_tip_accounts=args.tip_accounts,
            endpoint_name=args.endpoint,
        )
