#!/usr/bin/env python3
"""Analyze a Solana token using SolanaTracker Data API.

Fetches token info, risk assessment, top holders, and recent trades
to produce a comprehensive screening report. Includes risk flags,
holder concentration, and trading activity analysis.

Usage:
    python scripts/token_analysis.py
    TOKEN_ADDRESS="TokenMint..." python scripts/token_analysis.py

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANATRACKER_API_KEY: Your SolanaTracker API key
    TOKEN_ADDRESS: Token mint to analyze (default: SOL)
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────

API_KEY = os.getenv("SOLANATRACKER_API_KEY", "")
if not API_KEY:
    print("Set SOLANATRACKER_API_KEY environment variable")
    print("  Get a key at https://www.solanatracker.io/data-api")
    sys.exit(1)

TOKEN_ADDRESS = os.getenv(
    "TOKEN_ADDRESS", "So11111111111111111111111111111111111111112"
)

BASE_URL = "https://data.solanatracker.io"
HEADERS = {"x-api-key": API_KEY}

# ── API Helper ──────────────────────────────────────────────────────


def st_get(endpoint: str, params: Optional[dict] = None) -> dict | list:
    """Make a GET request to SolanaTracker API with retry.

    Args:
        endpoint: API path (e.g., '/tokens/...').
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        RuntimeError: On persistent API errors.
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
                wait = 5.0 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                print("  Access denied — check API key and subscription tier")
                return {}
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(3.0)
                continue
            raise
    return {}


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_token_info(address: str) -> dict:
    """Fetch full token info including risk, pools, and events.

    Args:
        address: Token mint address.

    Returns:
        Token info dict.
    """
    data = st_get(f"/tokens/{address}")
    return data if isinstance(data, dict) else {}


def fetch_top_holders(address: str) -> list[dict]:
    """Fetch top 20 holders for a token.

    Args:
        address: Token mint address.

    Returns:
        List of holder dicts.
    """
    data = st_get(f"/tokens/{address}/holders/top20")
    return data if isinstance(data, list) else []


def fetch_price_with_changes(address: str) -> dict:
    """Fetch current price with change percentages.

    Args:
        address: Token mint address.

    Returns:
        Price data dict.
    """
    data = st_get("/price", {"token": address, "priceChanges": "true"})
    return data if isinstance(data, dict) else {}


def fetch_top_traders(address: str) -> list[dict]:
    """Fetch top traders for a token.

    Args:
        address: Token mint address.

    Returns:
        List of top trader dicts.
    """
    data = st_get(f"/top-traders/{address}")
    return data if isinstance(data, list) else []


def fetch_bundlers(address: str) -> list[dict]:
    """Fetch bundler wallets for a token.

    Args:
        address: Token mint address.

    Returns:
        List of bundler dicts.
    """
    data = st_get(f"/tokens/{address}/bundlers")
    return data if isinstance(data, list) else []


# ── Analysis ────────────────────────────────────────────────────────


def analyze_risk(token_data: dict) -> list[str]:
    """Analyze risk factors and return formatted flags.

    Args:
        token_data: Full token info response.

    Returns:
        List of risk flag strings.
    """
    risk = token_data.get("risk", {})
    flags = []

    if not risk:
        flags.append("[?] Risk data unavailable")
        return flags

    score = risk.get("score", 0)
    rugged = risk.get("rugged", False)
    verified = risk.get("jupiterVerified", False)

    if rugged:
        flags.append("[!!] TOKEN HAS BEEN RUGGED")
    if verified:
        flags.append("[ok] Jupiter verified")
    else:
        flags.append("[i] Not Jupiter verified")

    flags.append(f"[{'ok' if score >= 7 else '!' if score >= 4 else '!!'}] "
                 f"Risk score: {score}/10")

    for r in risk.get("risks", []):
        level = r.get("level", "info")
        name = r.get("name", "Unknown risk")
        prefix = {"danger": "[!!]", "warn": "[!]", "info": "[i]"}.get(level, "[?]")
        flags.append(f"  {prefix} {name}")

    return flags


def analyze_holders(holders: list[dict]) -> dict:
    """Analyze holder concentration.

    Args:
        holders: List of top holder dicts.

    Returns:
        Concentration analysis dict.
    """
    if not holders:
        return {"count": 0}

    total_pct = sum(h.get("percentage", 0) or h.get("pct", 0) for h in holders)
    top_holder_pct = holders[0].get("percentage", 0) or holders[0].get("pct", 0) if holders else 0

    return {
        "count": len(holders),
        "top_holder_pct": round(top_holder_pct, 2),
        "top_10_pct": round(sum(
            h.get("percentage", 0) or h.get("pct", 0) for h in holders[:10]
        ), 2),
        "top_20_pct": round(total_pct, 2),
    }


# ── Display ─────────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format a USD value for display."""
    if not value:
        return "$0"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1e9:.2f}B"
    elif abs(value) >= 1_000_000:
        return f"${value / 1e6:.2f}M"
    elif abs(value) >= 1_000:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def print_report(
    address: str,
    token_data: dict,
    price_data: dict,
    risk_flags: list[str],
    holder_analysis: dict,
    bundlers: list[dict],
) -> None:
    """Print formatted token analysis report.

    Args:
        address: Token mint address.
        token_data: Full token info.
        price_data: Price with changes.
        risk_flags: Analyzed risk flags.
        holder_analysis: Holder concentration data.
        bundlers: Bundler wallet list.
    """
    # Extract token metadata
    token = token_data.get("token", token_data)
    name = token.get("name", "Unknown")
    symbol = token.get("symbol", "?")

    print(f"\n{'='*60}")
    print(f"TOKEN ANALYSIS: {symbol} ({name})")
    print(f"{'='*60}")
    print(f"  Mint: {address}")

    # Price data
    print(f"\n--- Price & Market ---")
    price = price_data.get("price", 0)
    if price:
        print(f"  Price:      {'${:.8f}'.format(price) if price < 0.01 else '${:.4f}'.format(price)}")
    liq = price_data.get("liquidity", 0)
    mcap = price_data.get("marketCap", 0)
    if liq:
        print(f"  Liquidity:  {format_usd(liq)}")
    if mcap:
        print(f"  Market Cap: {format_usd(mcap)}")

    # Price changes
    changes = {
        "5m": price_data.get("priceChange5m"),
        "1h": price_data.get("priceChange1h"),
        "6h": price_data.get("priceChange6h"),
        "24h": price_data.get("priceChange24h"),
    }
    change_parts = [f"{tf}: {v:+.2f}%" for tf, v in changes.items() if v is not None]
    if change_parts:
        print(f"  Changes:    {' | '.join(change_parts)}")

    # Pools
    pools = token_data.get("pools", [])
    if pools:
        print(f"\n--- Pools ({len(pools)}) ---")
        for p in pools[:5]:
            pool_liq = p.get("liquidity", {})
            pool_usd = pool_liq.get("usd", 0) if isinstance(pool_liq, dict) else 0
            dex = p.get("market", p.get("dexId", "?"))
            print(f"  {dex:<15} Liq: {format_usd(pool_usd)}")

    # Risk assessment
    print(f"\n--- Risk Assessment ---")
    for flag in risk_flags:
        print(f"  {flag}")

    # Holder concentration
    if holder_analysis.get("count", 0) > 0:
        print(f"\n--- Holder Concentration ---")
        print(f"  Top holder:   {holder_analysis['top_holder_pct']:.1f}%")
        print(f"  Top 10:       {holder_analysis['top_10_pct']:.1f}%")
        print(f"  Top 20:       {holder_analysis['top_20_pct']:.1f}%")

        if holder_analysis["top_10_pct"] > 80:
            print(f"  [!!] EXTREME CONCENTRATION — top 10 hold >80%")
        elif holder_analysis["top_10_pct"] > 50:
            print(f"  [!] High concentration — top 10 hold >50%")

    # Bundlers
    if bundlers:
        total_bundler_pct = sum(b.get("holdingPercentage", 0) for b in bundlers)
        print(f"\n--- Bundler Activity ---")
        print(f"  Bundlers detected: {len(bundlers)}")
        print(f"  Total holding:     {total_bundler_pct:.1f}%")
        if total_bundler_pct > 10:
            print(f"  [!] Significant bundler concentration")

    # Overall
    print(f"\n--- Assessment ---")
    risk_score = token_data.get("risk", {}).get("score", 0)
    if token_data.get("risk", {}).get("rugged"):
        print("  STATUS: RUGGED — do not trade")
    elif risk_score >= 7:
        print(f"  STATUS: LOW RISK (score {risk_score}/10)")
    elif risk_score >= 4:
        print(f"  STATUS: MODERATE RISK (score {risk_score}/10)")
    else:
        print(f"  STATUS: HIGH RISK (score {risk_score}/10)")

    if liq and liq < 10_000:
        print("  LIQUIDITY: DANGEROUSLY LOW (<$10K)")
    elif liq and liq < 50_000:
        print("  LIQUIDITY: LOW (<$50K)")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Run token analysis report."""
    print(f"Analyzing token: {TOKEN_ADDRESS}")

    print("Fetching token info...")
    token_data = fetch_token_info(TOKEN_ADDRESS)

    if not token_data:
        print("Could not fetch token data. Check the address and API key.")
        sys.exit(1)

    print("Fetching price...")
    price_data = fetch_price_with_changes(TOKEN_ADDRESS)
    time.sleep(0.5)

    print("Fetching holders...")
    holders = fetch_top_holders(TOKEN_ADDRESS)
    time.sleep(0.5)

    print("Fetching bundlers...")
    bundlers = fetch_bundlers(TOKEN_ADDRESS)

    # Analyze
    risk_flags = analyze_risk(token_data)
    holder_analysis = analyze_holders(holders)

    # Report
    print_report(
        TOKEN_ADDRESS, token_data, price_data,
        risk_flags, holder_analysis, bundlers,
    )


if __name__ == "__main__":
    main()
