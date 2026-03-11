#!/usr/bin/env python3
"""Screen Solana tokens using Birdeye overview, security, and trader data.

Fetches token overview, security info, and top trader data to generate a
screening report. Flags potential risks (mintable, freezeable, high
concentration) and highlights trading activity metrics.

Usage:
    python scripts/token_screener.py
    TOKEN_ADDRESS="TokenMint..." python scripts/token_screener.py

Dependencies:
    uv pip install httpx python-dotenv

Environment Variables:
    BIRDEYE_API_KEY: Your Birdeye API key
    TOKEN_ADDRESS: Token mint to screen (default: SOL)
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

API_KEY = os.getenv("BIRDEYE_API_KEY", "")
if not API_KEY:
    print("Set BIRDEYE_API_KEY environment variable")
    sys.exit(1)

TOKEN_ADDRESS = os.getenv(
    "TOKEN_ADDRESS", "So11111111111111111111111111111111111111112"
)

BASE_URL = "https://public-api.birdeye.so"
HEADERS = {
    "X-API-KEY": API_KEY,
    "x-chain": "solana",
    "accept": "application/json",
}
RATE_LIMIT_DELAY = 1.0  # conservative for free tier

# ── API Helper ──────────────────────────────────────────────────────


def birdeye_get(endpoint: str, params: Optional[dict] = None) -> dict:
    """Make a GET request to Birdeye API with retry.

    Args:
        endpoint: API path (e.g., '/defi/token_overview').
        params: Query parameters.

    Returns:
        The 'data' field from the response.

    Raises:
        RuntimeError: On API error.
    """
    for attempt in range(3):
        try:
            resp = httpx.get(
                f"{BASE_URL}{endpoint}",
                headers=HEADERS,
                params=params or {},
                timeout=30.0,
            )
            if resp.status_code == 429:
                time.sleep(3.0 * (attempt + 1))
                continue
            if resp.status_code == 403:
                return {}  # tier doesn't have access, skip gracefully
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                return {}
            return data.get("data", {})
        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(2.0)
                continue
            raise
    return {}


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_overview(address: str) -> dict:
    """Fetch token overview (30 CU)."""
    return birdeye_get("/defi/token_overview", {"address": address})


def fetch_security(address: str) -> dict:
    """Fetch token security info (50 CU)."""
    return birdeye_get("/defi/token_security", {"address": address})


def fetch_top_traders(address: str, timeframe: str = "24h") -> list[dict]:
    """Fetch top traders for a token (30 CU)."""
    data = birdeye_get("/defi/v2/tokens/top_traders", {
        "address": address,
        "time_frame": timeframe,
        "sort_by": "volume",
        "sort_type": "desc",
        "limit": 10,
    })
    return data.get("items", []) if isinstance(data, dict) else []


# ── Analysis ────────────────────────────────────────────────────────


def analyze_security(security: dict) -> list[str]:
    """Analyze security info and return risk flags.

    Args:
        security: Token security response data.

    Returns:
        List of risk flag strings.
    """
    flags = []

    if not security:
        flags.append("[?] Security data unavailable")
        return flags

    # Mint authority
    owner = security.get("ownerAddress")
    if owner:
        flags.append(f"[!] MINTABLE — owner: {owner[:16]}...")
    else:
        flags.append("[ok] Not mintable (owner renounced)")

    # Freeze authority
    if security.get("freezeable"):
        freeze_auth = security.get("freezeAuthority", "unknown")
        flags.append(f"[!] FREEZEABLE — authority: {freeze_auth[:16]}...")
    else:
        flags.append("[ok] Not freezeable")

    # Metadata mutability
    if security.get("mutableMetadata"):
        flags.append("[!] Metadata is mutable")
    else:
        flags.append("[ok] Metadata immutable")

    # Holder concentration
    top10 = security.get("top10HolderPercent", 0)
    if top10 > 80:
        flags.append(f"[!!] EXTREME CONCENTRATION — top 10 hold {top10:.1f}%")
    elif top10 > 50:
        flags.append(f"[!] High concentration — top 10 hold {top10:.1f}%")
    elif top10 > 0:
        flags.append(f"[ok] Top 10 hold {top10:.1f}%")

    # Creator balance
    creator_pct = security.get("creatorBalance", 0)
    if creator_pct and float(str(creator_pct)) > 10:
        flags.append(f"[!] Creator holds significant balance")

    # Token-2022
    if security.get("isToken2022"):
        flags.append("[i] Token-2022 program")
        if security.get("transferFeeEnable"):
            flags.append("[!] Transfer fees enabled")
        if security.get("nonTransferable"):
            flags.append("[!!] Non-transferable token")

    return flags


def analyze_traders(traders: list[dict]) -> dict:
    """Analyze top trader data.

    Args:
        traders: List of top trader dicts.

    Returns:
        Analysis summary dict.
    """
    if not traders:
        return {"total_traders": 0}

    total_volume = sum(t.get("volume", 0) for t in traders)
    bot_count = sum(1 for t in traders if t.get("tags"))
    bot_volume = sum(t.get("volume", 0) for t in traders if t.get("tags"))

    return {
        "total_traders": len(traders),
        "total_volume_top10": total_volume,
        "bot_count": bot_count,
        "bot_volume_pct": round(bot_volume / total_volume * 100, 1) if total_volume > 0 else 0,
        "top_trader_volume": traders[0].get("volume", 0) if traders else 0,
        "top_trader_address": traders[0].get("owner", "?")[:16] + "..." if traders else "N/A",
        "bot_tags": list(set(
            tag for t in traders for tag in (t.get("tags") or [])
        )),
    }


# ── Display ─────────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format a USD value for display."""
    if value >= 1_000_000_000:
        return f"${value / 1e9:.2f}B"
    elif value >= 1_000_000:
        return f"${value / 1e6:.2f}M"
    elif value >= 1_000:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def print_report(
    address: str,
    overview: dict,
    security_flags: list[str],
    trader_analysis: dict,
) -> None:
    """Print formatted screening report."""
    name = overview.get("name", "Unknown")
    symbol = overview.get("symbol", "?")

    print(f"\n{'='*60}")
    print(f"TOKEN SCREENING: {symbol} ({name})")
    print(f"{'='*60}")
    print(f"  Mint: {address}")

    # Market data
    print(f"\n--- Market Data ---")
    price = overview.get("price", 0)
    print(f"  Price:        ${price:.6f}" if price < 1 else f"  Price:        ${price:.2f}")
    print(f"  Market Cap:   {format_usd(overview.get('mc', 0))}")
    print(f"  Liquidity:    {format_usd(overview.get('liquidity', 0))}")
    print(f"  Markets:      {overview.get('numberMarkets', 0)}")

    # Price changes
    print(f"\n--- Price Changes ---")
    for tf in ["30m", "1h", "4h", "24h"]:
        pct = overview.get(f"priceChange{tf.replace('m', 'm').replace('h', 'h')}Percent", 0)
        key = f"priceChange{tf}Percent"
        # Try various key formats
        for k in [f"priceChange{tf}Percent", f"priceChange{tf.upper()}Percent"]:
            if k in overview:
                pct = overview[k]
                break
        print(f"  {tf:>4}: {pct:+.2f}%")

    # Volume & activity
    print(f"\n--- Activity (24h) ---")
    print(f"  Volume:       {format_usd(overview.get('v24hUSD', 0))}")
    print(f"  Trades:       {overview.get('trade24h', 0):,}")
    print(f"  Buys:         {overview.get('buy24h', 0):,}")
    print(f"  Sells:        {overview.get('sell24h', 0):,}")
    buy_vol = overview.get("vBuy24hUSD", 0)
    sell_vol = overview.get("vSell24hUSD", 0)
    if buy_vol and sell_vol:
        ratio = buy_vol / sell_vol if sell_vol > 0 else float("inf")
        print(f"  Buy/Sell Vol: {ratio:.2f}x")
    print(f"  Unique Wallets: {overview.get('uniqueWallet24h', 0):,}")

    # Security
    print(f"\n--- Security Check ---")
    for flag in security_flags:
        print(f"  {flag}")

    # Top traders
    if trader_analysis.get("total_traders", 0) > 0:
        print(f"\n--- Top Traders (24h) ---")
        print(f"  Top 10 volume:  {format_usd(trader_analysis['total_volume_top10'])}")
        print(f"  #1 trader:      {trader_analysis['top_trader_address']}")
        print(f"  Bots detected:  {trader_analysis['bot_count']}/{trader_analysis['total_traders']}")
        print(f"  Bot volume:     {trader_analysis['bot_volume_pct']}% of top 10")
        if trader_analysis["bot_tags"]:
            print(f"  Bot types:      {', '.join(trader_analysis['bot_tags'])}")

    # Overall assessment
    print(f"\n--- Assessment ---")
    risks = sum(1 for f in security_flags if f.startswith("[!]") or f.startswith("[!!]"))
    liq = overview.get("liquidity", 0)

    if any(f.startswith("[!!]") for f in security_flags):
        print("  RISK: HIGH — critical security flags detected")
    elif risks >= 3:
        print("  RISK: ELEVATED — multiple risk factors")
    elif risks >= 1:
        print("  RISK: MODERATE — some risk factors present")
    else:
        print("  RISK: LOW — no major flags")

    if liq < 10_000:
        print("  LIQUIDITY: DANGEROUSLY LOW (<$10K)")
    elif liq < 50_000:
        print("  LIQUIDITY: LOW (<$50K)")
    elif liq < 250_000:
        print("  LIQUIDITY: MODERATE")
    else:
        print("  LIQUIDITY: ADEQUATE")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run token screening report."""
    print(f"Screening token: {TOKEN_ADDRESS}")

    # Fetch data (total: ~110 CU)
    print("Fetching overview...")
    overview = fetch_overview(TOKEN_ADDRESS)
    time.sleep(RATE_LIMIT_DELAY)

    print("Fetching security...")
    security = fetch_security(TOKEN_ADDRESS)
    time.sleep(RATE_LIMIT_DELAY)

    print("Fetching top traders...")
    traders = fetch_top_traders(TOKEN_ADDRESS)

    if not overview:
        print("Could not fetch token data. Check the address and API key.")
        sys.exit(1)

    # Analyze
    security_flags = analyze_security(security)
    trader_analysis = analyze_traders(traders)

    # Report
    print_report(TOKEN_ADDRESS, overview, security_flags, trader_analysis)


if __name__ == "__main__":
    main()
