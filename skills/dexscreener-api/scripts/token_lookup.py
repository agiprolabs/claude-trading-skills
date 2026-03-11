#!/usr/bin/env python3
"""Look up any token across all chains using DexScreener (no auth required).

Fetches all DEX pairs for a token, sorts by liquidity, and displays a
comprehensive summary including price, volume, liquidity, buy/sell
pressure, and cross-DEX comparison.

Usage:
    python scripts/token_lookup.py
    TOKEN_ADDRESS="So11111111111111111111111111111111111111112" python scripts/token_lookup.py
    TOKEN_SYMBOL="BONK" python scripts/token_lookup.py

Dependencies:
    uv pip install httpx
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS", "")
TOKEN_SYMBOL = os.getenv("TOKEN_SYMBOL", "")
CHAIN_FILTER = os.getenv("CHAIN_FILTER", "")  # e.g., "solana" to limit results

BASE_URL = "https://api.dexscreener.com"

if not TOKEN_ADDRESS and not TOKEN_SYMBOL:
    TOKEN_ADDRESS = "So11111111111111111111111111111111111111112"  # SOL

# ── API Functions ───────────────────────────────────────────────────


def dexscreener_get(url: str, params: Optional[dict] = None, max_retries: int = 3) -> dict:
    """Make a GET request to DexScreener with retry logic.

    Args:
        url: Full URL to request.
        params: Query parameters.
        max_retries: Maximum retry attempts.

    Returns:
        Parsed JSON response.

    Raises:
        RuntimeError: After exhausting retries.
    """
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, params=params, timeout=15.0)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                wait = 10.0 * (attempt + 1)
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


def lookup_by_address(address: str) -> list[dict]:
    """Look up all pairs for a token address.

    Args:
        address: Token mint/contract address.

    Returns:
        List of pair dicts sorted by liquidity.
    """
    data = dexscreener_get(f"{BASE_URL}/latest/dex/tokens/{address}")
    pairs = data.get("pairs") or []
    pairs.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0, reverse=True)
    return pairs


def lookup_by_symbol(symbol: str) -> list[dict]:
    """Search for pairs by token symbol.

    Args:
        symbol: Token symbol (e.g., "BONK").

    Returns:
        List of pair dicts matching the symbol, sorted by liquidity.
    """
    data = dexscreener_get(f"{BASE_URL}/latest/dex/search", params={"q": symbol})
    pairs = data.get("pairs") or []
    # Filter to exact symbol match
    matched = [
        p for p in pairs
        if p.get("baseToken", {}).get("symbol", "").upper() == symbol.upper()
    ]
    matched.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0, reverse=True)
    return matched if matched else pairs


# ── Analysis ────────────────────────────────────────────────────────


def analyze_buy_sell_pressure(pair: dict) -> dict:
    """Analyze buy/sell transaction ratios across timeframes.

    Args:
        pair: Single pair response dict.

    Returns:
        Dict with buy ratios by timeframe.
    """
    txns = pair.get("txns", {})
    result = {}
    for tf in ["m5", "h1", "h6", "h24"]:
        data = txns.get(tf, {})
        buys = data.get("buys", 0)
        sells = data.get("sells", 0)
        total = buys + sells
        result[tf] = {
            "buys": buys,
            "sells": sells,
            "total": total,
            "buy_ratio": round(buys / total, 3) if total > 0 else 0.5,
        }
    return result


def format_usd(value: float) -> str:
    """Format a USD value for display."""
    if value >= 1_000_000_000:
        return f"${value / 1e9:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1e6:.2f}M"
    elif value >= 1_000:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


# ── Display ─────────────────────────────────────────────────────────


def print_pair_summary(pair: dict, rank: int = 1) -> None:
    """Print summary for a single pair.

    Args:
        pair: Pair response dict.
        rank: Display rank number.
    """
    base = pair.get("baseToken", {})
    quote = pair.get("quoteToken", {})
    symbol = base.get("symbol", "?")
    name = base.get("name", "Unknown")

    price_usd = float(pair.get("priceUsd", "0") or "0")
    liq = (pair.get("liquidity") or {}).get("usd", 0) or 0
    vol_24h = (pair.get("volume") or {}).get("h24", 0) or 0
    fdv = pair.get("fdv", 0) or 0
    mcap = pair.get("marketCap", 0) or 0

    chain = pair.get("chainId", "?")
    dex = pair.get("dexId", "?")
    labels = pair.get("labels", [])
    pool_type = f" [{', '.join(labels)}]" if labels else ""

    created_ms = pair.get("pairCreatedAt", 0)
    created_str = ""
    if created_ms:
        created_dt = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
        created_str = created_dt.strftime("%Y-%m-%d")

    print(f"\n{'─'*55}")
    print(f"  #{rank} — {symbol}/{quote.get('symbol', '?')} on {dex} ({chain}){pool_type}")
    print(f"{'─'*55}")
    print(f"  Name:       {name}")
    print(f"  Price:      {'${:.8f}'.format(price_usd) if price_usd < 0.01 else '${:.4f}'.format(price_usd)}")
    print(f"  Liquidity:  {format_usd(liq)}")
    print(f"  Volume 24h: {format_usd(vol_24h)}")
    if mcap:
        print(f"  Market Cap: {format_usd(mcap)}")
    if fdv and fdv != mcap:
        print(f"  FDV:        {format_usd(fdv)}")
    if created_str:
        print(f"  Created:    {created_str}")
    print(f"  Pair:       {pair.get('pairAddress', '?')[:20]}...")

    # Price changes
    changes = pair.get("priceChange", {})
    if changes:
        parts = []
        for tf in ["m5", "h1", "h6", "h24"]:
            pct = changes.get(tf)
            if pct is not None:
                parts.append(f"{tf}: {pct:+.2f}%")
        if parts:
            print(f"  Changes:    {' | '.join(parts)}")

    # Buy/sell pressure
    pressure = analyze_buy_sell_pressure(pair)
    h1 = pressure.get("h1", {})
    h24 = pressure.get("h24", {})
    if h1.get("total", 0) > 0:
        print(f"  Txns 1h:    {h1['buys']}B / {h1['sells']}S (buy ratio: {h1['buy_ratio']:.0%})")
    if h24.get("total", 0) > 0:
        print(f"  Txns 24h:   {h24['buys']}B / {h24['sells']}S (buy ratio: {h24['buy_ratio']:.0%})")


def print_cross_dex_comparison(pairs: list[dict]) -> None:
    """Print a comparison table across DEXes.

    Args:
        pairs: List of pair dicts, already sorted by liquidity.
    """
    if len(pairs) < 2:
        return

    # Filter to same chain for meaningful comparison
    chains = set(p.get("chainId") for p in pairs[:10])
    if len(chains) == 1:
        print(f"\n{'='*55}")
        print(f"  Cross-DEX Comparison ({list(chains)[0]})")
        print(f"{'='*55}")
    else:
        print(f"\n{'='*55}")
        print(f"  Cross-Chain Comparison")
        print(f"{'='*55}")

    print(f"  {'DEX':<15} {'Chain':<10} {'Price':>12} {'Liquidity':>12} {'Vol 24h':>12}")
    print(f"  {'─'*15} {'─'*10} {'─'*12} {'─'*12} {'─'*12}")

    for p in pairs[:10]:
        dex = p.get("dexId", "?")[:14]
        chain = p.get("chainId", "?")[:9]
        price = float(p.get("priceUsd", "0") or "0")
        liq = (p.get("liquidity") or {}).get("usd", 0) or 0
        vol = (p.get("volume") or {}).get("h24", 0) or 0

        price_str = f"${price:.6f}" if price < 0.01 else f"${price:.4f}"
        print(f"  {dex:<15} {chain:<10} {price_str:>12} {format_usd(liq):>12} {format_usd(vol):>12}")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run token lookup and display results."""
    if TOKEN_ADDRESS:
        print(f"Looking up token: {TOKEN_ADDRESS}")
        pairs = lookup_by_address(TOKEN_ADDRESS)
    else:
        print(f"Searching for: {TOKEN_SYMBOL}")
        pairs = lookup_by_symbol(TOKEN_SYMBOL)

    if CHAIN_FILTER:
        pairs = [p for p in pairs if p.get("chainId") == CHAIN_FILTER]

    if not pairs:
        print("No pairs found.")
        sys.exit(1)

    # Primary pair details
    base_symbol = pairs[0].get("baseToken", {}).get("symbol", "?")
    total_liq = sum((p.get("liquidity") or {}).get("usd", 0) or 0 for p in pairs)

    print(f"\nFound {len(pairs)} pairs for {base_symbol}")
    print(f"Total liquidity across all pairs: {format_usd(total_liq)}")

    # Show top 3 pairs
    for i, pair in enumerate(pairs[:3], 1):
        print_pair_summary(pair, rank=i)

    # Cross-DEX comparison
    if len(pairs) >= 2:
        print_cross_dex_comparison(pairs)

    print()


if __name__ == "__main__":
    main()
