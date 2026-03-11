#!/usr/bin/env python3
"""Look up token metadata and holder information via Helius DAS API.

Queries the DAS API for comprehensive token information including metadata,
supply, authorities, and top holders. Useful for pre-trade due diligence
on new tokens.

Usage:
    python scripts/token_lookup.py
    TOKEN_MINT="So11111111111111111111111111111111111111112" python scripts/token_lookup.py

Dependencies:
    uv pip install httpx python-dotenv

Environment Variables:
    HELIUS_API_KEY: Your Helius API key (free tier works)
    TOKEN_MINT: Token mint address to look up
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

API_KEY = os.getenv("HELIUS_API_KEY", "")
if not API_KEY:
    print("Set HELIUS_API_KEY environment variable")
    print("  Get a free key at https://dashboard.helius.dev")
    sys.exit(1)

TOKEN_MINT = os.getenv(
    "TOKEN_MINT", "So11111111111111111111111111111111111111112"
)

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
RATE_LIMIT_DELAY = 0.5

# ── API Helper ──────────────────────────────────────────────────────


def das_request(method: str, params: dict, retries: int = 2) -> dict:
    """Make a DAS API request with retry logic.

    Args:
        method: DAS method name.
        params: Method parameters.
        retries: Number of retry attempts.

    Returns:
        The 'result' field from the JSON-RPC response.

    Raises:
        RuntimeError: On DAS error or exhausted retries.
    """
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                RPC_URL,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=30.0,
            )
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"DAS error: {data['error']}")
            return data["result"]
        except httpx.TimeoutException:
            if attempt < retries:
                time.sleep(1.0)
                continue
            raise
    raise RuntimeError("Max retries exceeded")


# ── Token Analysis ──────────────────────────────────────────────────


def get_token_metadata(mint: str) -> dict:
    """Fetch comprehensive token metadata via getAsset.

    Args:
        mint: Token mint address.

    Returns:
        Parsed metadata dict.
    """
    result = das_request("getAsset", {
        "id": mint,
        "options": {
            "showFungible": True,
            "showCollectionMetadata": True,
        }
    })

    metadata = result.get("content", {}).get("metadata", {})
    token_info = result.get("token_info", {})
    authorities = result.get("authorities", [])
    creators = result.get("creators", [])

    return {
        "mint": mint,
        "name": metadata.get("name", "Unknown"),
        "symbol": metadata.get("symbol", "?"),
        "description": metadata.get("description", ""),
        "interface": result.get("interface", "Unknown"),
        "decimals": token_info.get("decimals", 0),
        "supply": token_info.get("supply", 0),
        "token_program": token_info.get("token_program", ""),
        "mint_authority": token_info.get("mint_authority"),
        "freeze_authority": token_info.get("freeze_authority"),
        "mutable": result.get("mutable", False),
        "burnt": result.get("burnt", False),
        "authorities": [
            {"address": a["address"], "scopes": a.get("scopes", [])}
            for a in authorities
        ],
        "creators": [
            {"address": c["address"], "share": c.get("share", 0), "verified": c.get("verified", False)}
            for c in creators
        ],
        "image": result.get("content", {}).get("links", {}).get("image", ""),
    }


def get_top_holders(mint: str, limit: int = 20) -> list[dict]:
    """Fetch top token holders via getTokenAccounts.

    Args:
        mint: Token mint address.
        limit: Max holders to return.

    Returns:
        List of holder dicts sorted by balance (descending).
    """
    result = das_request("getTokenAccounts", {
        "mint": mint,
        "limit": limit,
        "options": {"showZeroBalance": False},
    })

    holders = []
    for account in result.get("token_accounts", []):
        holders.append({
            "owner": account.get("owner", ""),
            "amount": float(account.get("amount", 0)),
            "address": account.get("address", ""),
        })

    # Sort by amount descending
    holders.sort(key=lambda x: x["amount"], reverse=True)
    return holders[:limit]


def compute_concentration(holders: list[dict], total_supply: int, decimals: int) -> dict:
    """Compute holder concentration metrics.

    Args:
        holders: List of holder dicts with 'amount' field (raw amounts).
        total_supply: Total token supply (raw, not decimalized).
        decimals: Token decimals.

    Returns:
        Concentration metrics dict.
    """
    if not holders or total_supply == 0:
        return {"top10_pct": 0, "top20_pct": 0, "largest_holder_pct": 0}

    supply_float = total_supply / (10 ** decimals)
    amounts = [h["amount"] / (10 ** decimals) for h in holders]

    top10_sum = sum(amounts[:10])
    top20_sum = sum(amounts[:20])

    return {
        "top10_pct": round(top10_sum / supply_float * 100, 2) if supply_float > 0 else 0,
        "top20_pct": round(top20_sum / supply_float * 100, 2) if supply_float > 0 else 0,
        "largest_holder_pct": round(amounts[0] / supply_float * 100, 2) if supply_float > 0 and amounts else 0,
        "holder_count_sampled": len(holders),
    }


# ── Display ─────────────────────────────────────────────────────────


def format_supply(raw_supply: int, decimals: int) -> str:
    """Format raw supply into human-readable string."""
    value = raw_supply / (10 ** decimals)
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.4f}"


def print_token_report(
    metadata: dict,
    holders: list[dict],
    concentration: dict,
) -> None:
    """Print a formatted token analysis report.

    Args:
        metadata: Token metadata dict.
        holders: Top holders list.
        concentration: Concentration metrics.
    """
    print(f"{'=' * 60}")
    print(f"TOKEN REPORT: {metadata['symbol']} ({metadata['name']})")
    print(f"{'=' * 60}")
    print()

    # Metadata
    print("Metadata:")
    print(f"  Mint:            {metadata['mint']}")
    print(f"  Interface:       {metadata['interface']}")
    print(f"  Decimals:        {metadata['decimals']}")
    print(f"  Supply:          {format_supply(metadata['supply'], metadata['decimals'])}")
    print(f"  Mutable:         {metadata['mutable']}")
    print(f"  Token Program:   {metadata['token_program'][:20]}...")

    # Authorities
    print()
    print("Authorities:")
    mint_auth = metadata.get("mint_authority")
    freeze_auth = metadata.get("freeze_authority")
    print(f"  Mint authority:   {mint_auth if mint_auth else 'None (supply locked)'}")
    print(f"  Freeze authority: {freeze_auth if freeze_auth else 'None (cannot freeze)'}")

    if metadata["creators"]:
        print()
        print("Creators:")
        for c in metadata["creators"]:
            verified = "verified" if c["verified"] else "unverified"
            print(f"  {c['address'][:20]}... ({c['share']}%, {verified})")

    # Safety flags
    print()
    print("Safety Indicators:")
    if mint_auth:
        print("  [!] Mint authority exists — supply can be increased")
    else:
        print("  [ok] No mint authority — supply is fixed")
    if freeze_auth:
        print("  [!] Freeze authority exists — tokens can be frozen")
    else:
        print("  [ok] No freeze authority")
    if metadata["mutable"]:
        print("  [!] Metadata is mutable — can be changed")
    else:
        print("  [ok] Metadata is immutable")

    # Holders
    if holders:
        print()
        print(f"Top Holders (sampled {concentration['holder_count_sampled']}):")
        print(f"  Top 10 own:       {concentration['top10_pct']}%")
        print(f"  Top 20 own:       {concentration['top20_pct']}%")
        print(f"  Largest holder:   {concentration['largest_holder_pct']}%")
        print()
        print(f"  {'#':>3} {'Owner':>20} {'Amount':>20}")
        print(f"  {'—'*3} {'—'*20} {'—'*20}")
        for i, h in enumerate(holders[:10], 1):
            owner = h["owner"][:20] if h["owner"] else "unknown"
            amt = format_supply(int(h["amount"]), metadata["decimals"])
            print(f"  {i:>3} {owner:>20} {amt:>20}")

    if concentration["top10_pct"] > 80:
        print()
        print("  [!] HIGH CONCENTRATION — top 10 holders own >80% of supply")
    elif concentration["top10_pct"] > 50:
        print()
        print("  [!] MODERATE CONCENTRATION — top 10 holders own >50% of supply")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Look up token and print analysis report."""
    print(f"Looking up token: {TOKEN_MINT}\n")

    # 1. Get metadata
    print("Fetching metadata...")
    metadata = get_token_metadata(TOKEN_MINT)
    time.sleep(RATE_LIMIT_DELAY)

    # 2. Get holders
    print("Fetching top holders...")
    holders = get_top_holders(TOKEN_MINT, limit=20)
    time.sleep(RATE_LIMIT_DELAY)

    # 3. Compute concentration
    concentration = compute_concentration(
        holders, metadata["supply"], metadata["decimals"]
    )

    # 4. Print report
    print()
    print_token_report(metadata, holders, concentration)


if __name__ == "__main__":
    main()
