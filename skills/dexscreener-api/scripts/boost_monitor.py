#!/usr/bin/env python3
"""Monitor newly boosted and promoted tokens on DexScreener.

Fetches latest token boosts, top boosts, and community takeovers.
Useful for discovering newly promoted tokens and tracking paid
promotion activity across chains.

Usage:
    python scripts/boost_monitor.py
    CHAIN_FILTER="solana" python scripts/boost_monitor.py

Dependencies:
    uv pip install httpx
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

CHAIN_FILTER = os.getenv("CHAIN_FILTER", "")  # e.g., "solana" to filter
BASE_URL = "https://api.dexscreener.com"

# ── API Functions ───────────────────────────────────────────────────


def dexscreener_get(url: str, max_retries: int = 3) -> list | dict:
    """Make a GET request to DexScreener with retry.

    Args:
        url: Full URL to request.
        max_retries: Maximum retry attempts.

    Returns:
        Parsed JSON response (list or dict).

    Raises:
        RuntimeError: After exhausting retries.
    """
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, timeout=15.0)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                wait = 15.0 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                time.sleep(5.0 * (attempt + 1))
                continue

            resp.raise_for_status()
        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                time.sleep(3.0)
                continue
            raise

    raise RuntimeError(f"Failed after {max_retries} retries: {url}")


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_latest_boosts() -> list[dict]:
    """Fetch recently boosted tokens.

    Returns:
        List of boost entries with chain, address, amounts.
    """
    data = dexscreener_get(f"{BASE_URL}/token-boosts/latest/v1")
    if not isinstance(data, list):
        return []
    return data


def fetch_top_boosts() -> list[dict]:
    """Fetch top boosted tokens sorted by total boost amount.

    Returns:
        List of boost entries sorted by totalAmount descending.
    """
    data = dexscreener_get(f"{BASE_URL}/token-boosts/top/v1")
    if not isinstance(data, list):
        return []
    return data


def fetch_latest_profiles() -> list[dict]:
    """Fetch latest token profiles (claimed/updated).

    Returns:
        List of token profile entries.
    """
    data = dexscreener_get(f"{BASE_URL}/token-profiles/latest/v1")
    if not isinstance(data, list):
        return []
    return data


def fetch_community_takeovers() -> list[dict]:
    """Fetch latest community takeover activity.

    Returns:
        List of CTO entries.
    """
    data = dexscreener_get(f"{BASE_URL}/community-takeovers/latest/v1")
    if not isinstance(data, list):
        return []
    return data


def enrich_with_pair_data(tokens: list[dict], limit: int = 5) -> list[dict]:
    """Enrich boost entries with pair data (price, liquidity).

    Args:
        tokens: List of boost/profile entries.
        limit: Maximum tokens to look up (to stay within rate limits).

    Returns:
        Enriched entries with pair data added.
    """
    enriched = []
    for token in tokens[:limit]:
        chain = token.get("chainId", "")
        address = token.get("tokenAddress", "")
        if not chain or not address:
            enriched.append(token)
            continue

        try:
            data = dexscreener_get(
                f"{BASE_URL}/tokens/v1/{chain}/{address}"
            )
            pairs = data if isinstance(data, list) else data.get("pairs", [])
            if pairs:
                # Sort by liquidity
                pairs.sort(
                    key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0,
                    reverse=True,
                )
                best = pairs[0]
                token["_pair"] = {
                    "price": float(best.get("priceUsd", "0") or "0"),
                    "liquidity": (best.get("liquidity") or {}).get("usd", 0) or 0,
                    "volume_24h": (best.get("volume") or {}).get("h24", 0) or 0,
                    "symbol": best.get("baseToken", {}).get("symbol", "?"),
                    "dex": best.get("dexId", "?"),
                    "pair_count": len(pairs),
                }
            time.sleep(1.0)  # respect profile endpoint rate limit
        except Exception as e:
            print(f"  Warning: couldn't enrich {address[:12]}...: {e}")

        enriched.append(token)

    return enriched


# ── Display ─────────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format a USD value for display."""
    if value >= 1_000_000:
        return f"${value / 1e6:.2f}M"
    elif value >= 1_000:
        return f"${value / 1e3:.1f}K"
    return f"${value:.2f}"


def print_boosts(boosts: list[dict], title: str) -> None:
    """Print a formatted table of boosted tokens.

    Args:
        boosts: List of boost entries (optionally enriched).
        title: Section title.
    """
    if not boosts:
        print(f"\n  No {title.lower()} found.")
        return

    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

    for i, b in enumerate(boosts, 1):
        chain = b.get("chainId", "?")
        address = b.get("tokenAddress", "?")
        amount = b.get("amount", 0)
        total = b.get("totalAmount", 0)
        desc = b.get("description", "")[:40]

        pair = b.get("_pair", {})
        symbol = pair.get("symbol", "")
        price = pair.get("price", 0)
        liq = pair.get("liquidity", 0)
        vol = pair.get("volume_24h", 0)

        symbol_str = f" ({symbol})" if symbol else ""
        print(f"\n  #{i} — {chain}{symbol_str}")
        print(f"    Address:  {address}")
        if total:
            print(f"    Boost:    {amount} (total: {total})")
        if desc:
            print(f"    Desc:     {desc}")

        if pair:
            price_str = f"${price:.8f}" if price < 0.01 else f"${price:.4f}"
            print(f"    Price:    {price_str}")
            print(f"    Liq:      {format_usd(liq)}  |  Vol 24h: {format_usd(vol)}")
            print(f"    DEX:      {pair.get('dex', '?')}  |  Pairs: {pair.get('pair_count', 0)}")


def print_profiles(profiles: list[dict]) -> None:
    """Print latest token profiles.

    Args:
        profiles: List of profile entries.
    """
    if not profiles:
        print("\n  No new profiles found.")
        return

    print(f"\n{'='*65}")
    print(f"  Latest Token Profiles")
    print(f"{'='*65}")

    for i, p in enumerate(profiles[:10], 1):
        chain = p.get("chainId", "?")
        address = p.get("tokenAddress", "?")
        desc = p.get("description", "")[:50]
        links = p.get("links", [])
        link_types = [l.get("type", "?") for l in links[:3]]

        print(f"\n  #{i} — {chain}")
        print(f"    Address: {address}")
        if desc:
            print(f"    Desc:    {desc}")
        if link_types:
            print(f"    Links:   {', '.join(link_types)}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run boost monitor and display results."""
    print("DexScreener Boost Monitor")
    print("=" * 65)

    # Fetch all data
    print("\nFetching latest boosts...")
    latest = fetch_latest_boosts()
    time.sleep(1.0)

    print("Fetching top boosts...")
    top = fetch_top_boosts()
    time.sleep(1.0)

    print("Fetching latest profiles...")
    profiles = fetch_latest_profiles()
    time.sleep(1.0)

    print("Fetching community takeovers...")
    ctos = fetch_community_takeovers()

    # Apply chain filter
    if CHAIN_FILTER:
        latest = [b for b in latest if b.get("chainId") == CHAIN_FILTER]
        top = [b for b in top if b.get("chainId") == CHAIN_FILTER]
        profiles = [p for p in profiles if p.get("chainId") == CHAIN_FILTER]
        ctos = [c for c in ctos if c.get("chainId") == CHAIN_FILTER]
        print(f"\nFiltered to chain: {CHAIN_FILTER}")

    # Summary
    print(f"\nFound: {len(latest)} latest boosts, {len(top)} top boosts, "
          f"{len(profiles)} profiles, {len(ctos)} CTOs")

    # Enrich top boosts with pair data
    if top:
        print("\nEnriching top boosts with pair data...")
        top = enrich_with_pair_data(top, limit=5)

    # Display
    print_boosts(top[:10], "Top Boosted Tokens")
    print_boosts(latest[:10], "Latest Boosts")
    print_profiles(profiles)

    if ctos:
        print(f"\n{'='*65}")
        print(f"  Community Takeovers: {len(ctos)} active")
        print(f"{'='*65}")
        for c in ctos[:5]:
            print(f"  - {c.get('chainId', '?')}: {c.get('tokenAddress', '?')[:20]}...")

    # Chain distribution
    all_chains = [b.get("chainId") for b in latest + top if b.get("chainId")]
    if all_chains:
        from collections import Counter
        chain_counts = Counter(all_chains).most_common(10)
        print(f"\n{'='*65}")
        print(f"  Boost Activity by Chain")
        print(f"{'='*65}")
        for chain, count in chain_counts:
            bar = "█" * min(count, 30)
            print(f"  {chain:<15} {count:>4}  {bar}")

    print()


if __name__ == "__main__":
    main()
