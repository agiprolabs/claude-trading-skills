#!/usr/bin/env python3
"""Solana DeFi overview using DeFiLlama (free, no auth).

Fetches TVL, DEX volumes, fees, and top protocols for Solana.
Produces a comprehensive DeFi macro snapshot.

Usage:
    python scripts/defi_snapshot.py
    CHAIN="Ethereum" python scripts/defi_snapshot.py

Dependencies:
    uv pip install httpx
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

CHAIN = os.getenv("CHAIN", "Solana")
BASE = "https://api.llama.fi"
COINS = "https://coins.llama.fi"

# ── API Helper ──────────────────────────────────────────────────────


def llama_get(url: str, params: Optional[dict] = None) -> dict | list:
    """GET request to DeFiLlama with retry.

    Args:
        url: Full URL.
        params: Query parameters.

    Returns:
        Parsed JSON response.
    """
    for attempt in range(3):
        try:
            resp = httpx.get(url, params=params or {}, timeout=30.0)
            if resp.status_code == 429:
                time.sleep(30.0)
                continue
            if resp.status_code >= 500:
                time.sleep(5.0)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(5.0)
                continue
            raise
    return {}


# ── Data Fetching ───────────────────────────────────────────────────


def get_chain_tvl(chain: str) -> float:
    """Get current TVL for a chain.

    Args:
        chain: Chain name (e.g., 'Solana').

    Returns:
        TVL in USD.
    """
    chains = llama_get(f"{BASE}/v2/chains")
    if not isinstance(chains, list):
        return 0
    for c in chains:
        if c.get("name", "").lower() == chain.lower():
            return c.get("tvl", 0)
    return 0


def get_top_protocols(chain: str, limit: int = 15) -> list[dict]:
    """Get top protocols by TVL for a chain.

    Args:
        chain: Chain name.
        limit: Number of protocols to return.

    Returns:
        Sorted list of protocol dicts.
    """
    protocols = llama_get(f"{BASE}/protocols")
    if not isinstance(protocols, list):
        return []

    chain_protocols = []
    for p in protocols:
        chains = p.get("chains", [])
        if chain in chains:
            chain_tvl = p.get("chainTvls", {}).get(chain, 0)
            if chain_tvl > 0:
                chain_protocols.append({
                    "name": p.get("name", "?"),
                    "category": p.get("category", "?"),
                    "tvl": chain_tvl,
                    "change_1d": p.get("change_1d", 0),
                    "change_7d": p.get("change_7d", 0),
                })

    chain_protocols.sort(key=lambda x: x["tvl"], reverse=True)
    return chain_protocols[:limit]


def get_dex_volumes(chain: str) -> dict:
    """Get DEX volume overview for a chain.

    Args:
        chain: Chain name.

    Returns:
        Volume summary dict.
    """
    data = llama_get(f"{BASE}/overview/dexs/{chain}", {
        "excludeTotalDataChart": "true",
        "excludeTotalDataChartBreakdown": "true",
    })
    if not isinstance(data, dict):
        return {}
    return data


def get_fees(chain: str) -> dict:
    """Get fee overview for a chain.

    Args:
        chain: Chain name.

    Returns:
        Fee summary dict.
    """
    data = llama_get(f"{BASE}/overview/fees/{chain}", {
        "excludeTotalDataChart": "true",
        "excludeTotalDataChartBreakdown": "true",
    })
    if not isinstance(data, dict):
        return {}
    return data


def get_stablecoin_supply(chain: str) -> dict:
    """Get stablecoin supply for a chain.

    Args:
        chain: Chain name.

    Returns:
        Stablecoin summary dict.
    """
    stables = llama_get("https://stablecoins.llama.fi/stablecoins")
    if not isinstance(stables, list):
        return {}

    total = 0
    breakdown = {}
    for s in stables:
        chain_data = s.get("chainCirculating", {}).get(chain, {})
        current = chain_data.get("current", {}).get("peggedUSD", 0)
        if current > 0:
            total += current
            breakdown[s["symbol"]] = current

    return {"total": total, "breakdown": breakdown}


# ── Display ─────────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format USD value for display."""
    if not value:
        return "$0"
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    elif abs(value) >= 1e6:
        return f"${value / 1e6:.2f}M"
    elif abs(value) >= 1e3:
        return f"${value / 1e3:.1f}K"
    return f"${value:.2f}"


def print_report(
    chain: str,
    tvl: float,
    protocols: list[dict],
    volumes: dict,
    fees: dict,
    stables: dict,
) -> None:
    """Print DeFi snapshot report."""
    print(f"\n{'='*60}")
    print(f"DeFi SNAPSHOT — {chain}")
    print(f"{'='*60}")

    # Overview
    print(f"\n--- Overview ---")
    print(f"  Total TVL:        {format_usd(tvl)}")
    vol_24h = volumes.get("total24h", 0)
    print(f"  DEX Volume 24h:   {format_usd(vol_24h)}")
    fees_24h = fees.get("total24h", 0)
    print(f"  Fees 24h:         {format_usd(fees_24h)}")
    print(f"  Stablecoin Supply:{format_usd(stables.get('total', 0))}")

    # Top protocols
    if protocols:
        print(f"\n--- Top Protocols by TVL ---")
        print(f"  {'Protocol':<25} {'Category':<15} {'TVL':>12} {'1d%':>7} {'7d%':>7}")
        print(f"  {'─'*25} {'─'*15} {'─'*12} {'─'*7} {'─'*7}")
        for p in protocols:
            d1 = p.get("change_1d", 0) or 0
            d7 = p.get("change_7d", 0) or 0
            print(f"  {p['name']:<25} {p['category']:<15} "
                  f"{format_usd(p['tvl']):>12} {d1:>+6.1f}% {d7:>+6.1f}%")

    # Top DEXes by volume
    dex_protocols = volumes.get("protocols", [])
    if dex_protocols:
        top_dexes = sorted(dex_protocols, key=lambda x: x.get("total24h", 0) or 0, reverse=True)[:10]
        print(f"\n--- Top DEXes by Volume ---")
        print(f"  {'DEX':<20} {'Vol 24h':>14} {'Vol 7d':>14}")
        print(f"  {'─'*20} {'─'*14} {'─'*14}")
        for d in top_dexes:
            v24 = d.get("total24h", 0) or 0
            v7d = d.get("total7d", 0) or 0
            if v24 > 0:
                print(f"  {d.get('name', '?'):<20} {format_usd(v24):>14} {format_usd(v7d):>14}")

    # Stablecoin breakdown
    breakdown = stables.get("breakdown", {})
    if breakdown:
        print(f"\n--- Stablecoin Supply ---")
        sorted_stables = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
        for symbol, supply in sorted_stables[:5]:
            pct = supply / stables["total"] * 100 if stables["total"] > 0 else 0
            print(f"  {symbol:<8} {format_usd(supply):>14} ({pct:.1f}%)")

    print()


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run DeFi snapshot."""
    print(f"Generating DeFi snapshot for {CHAIN}...")

    print("Fetching TVL...")
    tvl = get_chain_tvl(CHAIN)
    time.sleep(0.5)

    print("Fetching top protocols...")
    protocols = get_top_protocols(CHAIN)
    time.sleep(0.5)

    print("Fetching DEX volumes...")
    volumes = get_dex_volumes(CHAIN)
    time.sleep(0.5)

    print("Fetching fees...")
    fees = get_fees(CHAIN)
    time.sleep(0.5)

    print("Fetching stablecoin data...")
    stables = get_stablecoin_supply(CHAIN)

    print_report(CHAIN, tvl, protocols, volumes, fees, stables)


if __name__ == "__main__":
    main()
