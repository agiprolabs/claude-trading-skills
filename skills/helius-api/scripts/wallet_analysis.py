#!/usr/bin/env python3
"""Analyze a Solana wallet using Helius DAS and Enhanced Transactions APIs.

Fetches a wallet's token portfolio via DAS API, retrieves parsed transaction
history, and generates a profile including top holdings, recent swap activity,
preferred DEXes, and trading frequency.

Usage:
    python scripts/wallet_analysis.py
    WALLET_ADDRESS="YourWallet..." python scripts/wallet_analysis.py

Dependencies:
    uv pip install httpx python-dotenv

Environment Variables:
    HELIUS_API_KEY: Your Helius API key (free tier works)
    WALLET_ADDRESS: Solana wallet to analyze (optional, uses example if not set)
"""

import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

API_KEY = os.getenv("HELIUS_API_KEY", "")
if not API_KEY:
    print("Set HELIUS_API_KEY environment variable")
    print("  Get a free key at https://dashboard.helius.dev")
    sys.exit(1)

WALLET = os.getenv("WALLET_ADDRESS", "")
if not WALLET:
    print("Set WALLET_ADDRESS environment variable")
    print("  export WALLET_ADDRESS='YourSolanaWalletAddress'")
    sys.exit(1)

RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
API_URL = f"https://api-mainnet.helius-rpc.com/v0"

# Rate limit delay between API calls (seconds)
RATE_LIMIT_DELAY = 0.5

# ── API Helpers ─────────────────────────────────────────────────────


def das_request(method: str, params: dict) -> dict:
    """Make a DAS API request via JSON-RPC.

    Args:
        method: DAS method name (e.g., 'getAssetsByOwner').
        params: Method parameters.

    Returns:
        The 'result' field from the JSON-RPC response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        KeyError: If response has no 'result'.
    """
    resp = httpx.post(
        RPC_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"DAS error: {data['error']}")
    return data["result"]


def get_enhanced_transactions(
    address: str,
    limit: int = 50,
    tx_type: Optional[str] = None,
) -> list[dict]:
    """Fetch parsed transaction history for an address.

    Args:
        address: Solana address to query.
        limit: Max transactions to return (max 100 per request).
        tx_type: Optional filter (e.g., 'SWAP', 'TRANSFER').

    Returns:
        List of EnhancedTransaction dicts.
    """
    params: dict = {"api-key": API_KEY, "limit": min(limit, 100)}
    if tx_type:
        params["type"] = tx_type

    resp = httpx.get(
        f"{API_URL}/addresses/{address}/transactions",
        params=params,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


# ── Analysis Functions ──────────────────────────────────────────────


def fetch_portfolio(wallet: str) -> list[dict]:
    """Fetch all fungible token holdings for a wallet.

    Args:
        wallet: Solana wallet address.

    Returns:
        List of asset dicts with token info.
    """
    result = das_request("getAssetsByOwner", {
        "ownerAddress": wallet,
        "page": 1,
        "limit": 1000,
        "displayOptions": {
            "showFungible": True,
            "showNativeBalance": True,
            "showZeroBalance": False,
        },
    })
    return result.get("items", [])


def analyze_portfolio(assets: list[dict]) -> dict:
    """Analyze a wallet's token portfolio.

    Args:
        assets: List of asset dicts from DAS API.

    Returns:
        Analysis dict with holdings summary.
    """
    fungible = []
    nfts = []

    for asset in assets:
        interface = asset.get("interface", "")
        if interface in ("FungibleToken", "FungibleAsset"):
            name = asset.get("content", {}).get("metadata", {}).get("name", "Unknown")
            symbol = asset.get("content", {}).get("metadata", {}).get("symbol", "?")
            token_info = asset.get("token_info", {})
            decimals = token_info.get("decimals", 0)

            fungible.append({
                "name": name,
                "symbol": symbol,
                "mint": asset.get("id", ""),
                "decimals": decimals,
            })
        else:
            nfts.append(asset)

    return {
        "fungible_count": len(fungible),
        "nft_count": len(nfts),
        "top_holdings": fungible[:20],
    }


def analyze_swap_history(swaps: list[dict]) -> dict:
    """Analyze swap transaction history.

    Args:
        swaps: List of enhanced swap transactions.

    Returns:
        Analysis dict with swap patterns.
    """
    if not swaps:
        return {"total_swaps": 0}

    sources = Counter()
    tokens_traded = Counter()
    hourly_activity = Counter()
    total_fee = 0

    for tx in swaps:
        sources[tx.get("source", "UNKNOWN")] += 1
        total_fee += tx.get("fee", 0)

        # Count tokens involved
        for tt in tx.get("tokenTransfers", []):
            mint = tt.get("mint", "unknown")
            tokens_traded[mint] += 1

        # Hourly distribution
        ts = tx.get("timestamp")
        if ts:
            hour = datetime.fromtimestamp(ts, tz=timezone.utc).hour
            hourly_activity[hour] += 1

    # Time span
    timestamps = [tx.get("timestamp", 0) for tx in swaps if tx.get("timestamp")]
    time_span_hours = 0
    if len(timestamps) >= 2:
        time_span_hours = (max(timestamps) - min(timestamps)) / 3600

    swaps_per_hour = len(swaps) / time_span_hours if time_span_hours > 0 else 0

    return {
        "total_swaps": len(swaps),
        "time_span_hours": round(time_span_hours, 1),
        "swaps_per_hour": round(swaps_per_hour, 2),
        "preferred_dexes": sources.most_common(5),
        "unique_tokens_traded": len(tokens_traded),
        "most_traded_mints": tokens_traded.most_common(5),
        "peak_hours_utc": hourly_activity.most_common(3),
        "total_fees_sol": round(total_fee / 1e9, 6),
    }


def analyze_transfers(transfers: list[dict], wallet: str) -> dict:
    """Analyze transfer patterns.

    Args:
        transfers: List of enhanced transfer transactions.
        wallet: The wallet address for determining direction.

    Returns:
        Analysis dict with transfer patterns.
    """
    if not transfers:
        return {"total_transfers": 0}

    inbound = 0
    outbound = 0

    for tx in transfers:
        for nt in tx.get("nativeTransfers", []):
            if nt.get("toUserAccount") == wallet:
                inbound += nt.get("amount", 0)
            elif nt.get("fromUserAccount") == wallet:
                outbound += nt.get("amount", 0)

    return {
        "total_transfers": len(transfers),
        "sol_received": round(inbound / 1e9, 4),
        "sol_sent": round(outbound / 1e9, 4),
        "net_sol_flow": round((inbound - outbound) / 1e9, 4),
    }


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run wallet analysis and print results."""
    print(f"Analyzing wallet: {WALLET}")
    print(f"{'=' * 60}\n")

    # 1. Fetch portfolio
    print("Fetching portfolio...")
    assets = fetch_portfolio(WALLET)
    portfolio = analyze_portfolio(assets)
    time.sleep(RATE_LIMIT_DELAY)

    print(f"\nPortfolio: {portfolio['fungible_count']} tokens, {portfolio['nft_count']} NFTs")
    if portfolio["top_holdings"]:
        print("\nTop Holdings:")
        for h in portfolio["top_holdings"][:10]:
            print(f"  {h['symbol']:>10} | {h['name']}")

    # 2. Fetch recent swaps
    print("\nFetching swap history...")
    swaps = get_enhanced_transactions(WALLET, limit=100, tx_type="SWAP")
    swap_analysis = analyze_swap_history(swaps)
    time.sleep(RATE_LIMIT_DELAY)

    print(f"\nSwap Activity ({swap_analysis['total_swaps']} swaps):")
    if swap_analysis["total_swaps"] > 0:
        print(f"  Time span: {swap_analysis['time_span_hours']}h")
        print(f"  Rate: {swap_analysis['swaps_per_hour']} swaps/hr")
        print(f"  Unique tokens: {swap_analysis['unique_tokens_traded']}")
        print(f"  Total fees: {swap_analysis['total_fees_sol']} SOL")
        print(f"  Preferred DEXes:")
        for dex, count in swap_analysis["preferred_dexes"]:
            print(f"    {dex}: {count}")
        if swap_analysis["peak_hours_utc"]:
            print(f"  Peak hours (UTC):")
            for hour, count in swap_analysis["peak_hours_utc"]:
                print(f"    {hour:02d}:00 — {count} swaps")

    # 3. Fetch recent transfers
    print("\nFetching transfer history...")
    transfers = get_enhanced_transactions(WALLET, limit=100, tx_type="TRANSFER")
    transfer_analysis = analyze_transfers(transfers, WALLET)
    time.sleep(RATE_LIMIT_DELAY)

    print(f"\nTransfer Activity ({transfer_analysis['total_transfers']} transfers):")
    if transfer_analysis["total_transfers"] > 0:
        print(f"  SOL received: {transfer_analysis['sol_received']}")
        print(f"  SOL sent: {transfer_analysis['sol_sent']}")
        print(f"  Net flow: {transfer_analysis['net_sol_flow']} SOL")

    # 4. Summary
    print(f"\n{'=' * 60}")
    print("WALLET PROFILE SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Address:        {WALLET[:20]}...")
    print(f"  Token holdings: {portfolio['fungible_count']}")
    print(f"  NFT holdings:   {portfolio['nft_count']}")
    print(f"  Recent swaps:   {swap_analysis['total_swaps']}")
    if swap_analysis.get("preferred_dexes"):
        print(f"  Primary DEX:    {swap_analysis['preferred_dexes'][0][0]}")
    print(f"  Trade frequency: {swap_analysis.get('swaps_per_hour', 0)} swaps/hr")


if __name__ == "__main__":
    main()
