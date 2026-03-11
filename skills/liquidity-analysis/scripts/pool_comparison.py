#!/usr/bin/env python3
"""Compare DEX pools for a Solana token.

Fetches all pools from DexScreener, compares them by liquidity, volume,
age, and price, identifies the best pool for execution, and flags
suspicious pools.

Usage:
    python scripts/pool_comparison.py <token_mint>
    python scripts/pool_comparison.py                # Demo mode with BONK
    TOKEN_MINT=<address> python scripts/pool_comparison.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Token mint address (optional, overridden by CLI arg)
"""

import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────
DEXSCREENER_BASE = "https://api.dexscreener.com"

# BONK mint for demo mode
DEMO_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

DEMO_POOLS = [
    {
        "pairAddress": "8sLbNZoA1cfnvMJLPfp98ZR1Gm14nAkoTn4YzMNqDZkN",
        "dexId": "raydium",
        "baseToken": {"symbol": "BONK", "address": DEMO_MINT},
        "quoteToken": {"symbol": "SOL", "address": "So11111111111111111111111111111111111111112"},
        "priceUsd": "0.00002341",
        "liquidity": {"usd": 4_500_000, "base": 192_000_000_000, "quote": 15_500},
        "volume": {"h24": 12_000_000, "h6": 3_200_000, "h1": 450_000},
        "txns": {"h24": {"buys": 8500, "sells": 7200}},
        "pairCreatedAt": int((time.time() - 400 * 86400) * 1000),
        "labels": [],
    },
    {
        "pairAddress": "9dMXBpMXA1zMcbdv4PgFhoBLGsXgUEi6YkBhsK6kxPgA",
        "dexId": "orca",
        "baseToken": {"symbol": "BONK", "address": DEMO_MINT},
        "quoteToken": {"symbol": "SOL", "address": "So11111111111111111111111111111111111111112"},
        "priceUsd": "0.00002339",
        "liquidity": {"usd": 2_800_000, "base": 119_000_000_000, "quote": 9_650},
        "volume": {"h24": 7_500_000, "h6": 1_800_000, "h1": 280_000},
        "txns": {"h24": {"buys": 4200, "sells": 3900}},
        "pairCreatedAt": int((time.time() - 350 * 86400) * 1000),
        "labels": ["concentrated"],
    },
    {
        "pairAddress": "2KgMEJkL4XKqbFMjT2mFNc3VGHh7HQXR3HjfNfTS7Nfu",
        "dexId": "meteora",
        "baseToken": {"symbol": "BONK", "address": DEMO_MINT},
        "quoteToken": {"symbol": "SOL", "address": "So11111111111111111111111111111111111111112"},
        "priceUsd": "0.00002345",
        "liquidity": {"usd": 950_000, "base": 40_500_000_000, "quote": 3_270},
        "volume": {"h24": 3_200_000, "h6": 900_000, "h1": 120_000},
        "txns": {"h24": {"buys": 1800, "sells": 1500}},
        "pairCreatedAt": int((time.time() - 90 * 86400) * 1000),
        "labels": ["dlmm"],
    },
    {
        "pairAddress": "FakePoolForDemoSuspiciousActivity1234567890ab",
        "dexId": "raydium",
        "baseToken": {"symbol": "BONK", "address": DEMO_MINT},
        "quoteToken": {"symbol": "USDC", "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
        "priceUsd": "0.00002290",
        "liquidity": {"usd": 5_000, "base": 214_000_000, "quote": 2_500},
        "volume": {"h24": 180_000, "h6": 45_000, "h1": 8_000},
        "txns": {"h24": {"buys": 120, "sells": 95}},
        "pairCreatedAt": int((time.time() - 0.5 * 86400) * 1000),
        "labels": [],
    },
]


# ── Data Fetching ──────────────────────────────────────────────────
def fetch_pools(mint: str) -> list[dict]:
    """Fetch all DEX pools for a token from DexScreener.

    Args:
        mint: Token mint address.

    Returns:
        List of pool/pair objects with liquidity > 0.
    """
    try:
        resp = httpx.get(
            f"{DEXSCREENER_BASE}/tokens/v1/solana/{mint}",
            timeout=15,
        )
        resp.raise_for_status()
        pairs = resp.json()
        if not isinstance(pairs, list):
            pairs = pairs.get("pairs", []) if isinstance(pairs, dict) else []
        return [p for p in pairs if p.get("liquidity", {}).get("usd", 0) > 0]
    except (httpx.HTTPError, ValueError) as e:
        print(f"  [warn] DexScreener fetch failed: {e}")
        return []


# ── Analysis Functions ─────────────────────────────────────────────
def pool_age_hours(pair_created_at_ms: int) -> float:
    """Calculate pool age in hours from creation timestamp.

    Args:
        pair_created_at_ms: Creation time in milliseconds.

    Returns:
        Age in hours.
    """
    if pair_created_at_ms <= 0:
        return 0.0
    return max(0.0, (time.time() * 1000 - pair_created_at_ms) / 3_600_000)


def format_age(hours: float) -> str:
    """Format age in hours to human-readable string.

    Args:
        hours: Age in hours.

    Returns:
        Formatted string like '3.5h', '14d', '6mo'.
    """
    if hours < 1:
        return f"{hours * 60:.0f}m"
    elif hours < 48:
        return f"{hours:.1f}h"
    elif hours < 24 * 90:
        return f"{hours / 24:.0f}d"
    else:
        return f"{hours / 24 / 30:.0f}mo"


def analyze_pool(pool: dict, all_pools: list[dict]) -> dict:
    """Analyze a single pool and compute metrics.

    Args:
        pool: DexScreener pair object.
        all_pools: All pools for context (price comparison).

    Returns:
        Dict with analysis metrics.
    """
    liq = pool.get("liquidity", {}).get("usd", 0)
    vol_24h = pool.get("volume", {}).get("h24", 0)
    age_h = pool_age_hours(pool.get("pairCreatedAt", 0))
    price = float(pool.get("priceUsd", 0))
    txns = pool.get("txns", {}).get("h24", {})
    buys = txns.get("buys", 0)
    sells = txns.get("sells", 0)
    total_txns = buys + sells

    # Volume/liquidity ratio (healthy: 1-5x, suspicious: >10x)
    vol_liq_ratio = vol_24h / liq if liq > 0 else 0

    # Buy/sell ratio (healthy: 0.4-0.6 buys, suspicious if very skewed)
    buy_ratio = buys / total_txns if total_txns > 0 else 0.5

    # Price deviation from median across all pools
    all_prices = [float(p.get("priceUsd", 0)) for p in all_pools if float(p.get("priceUsd", 0)) > 0]
    median_price = sorted(all_prices)[len(all_prices) // 2] if all_prices else price
    price_deviation_pct = abs(price - median_price) / median_price * 100 if median_price > 0 else 0

    return {
        "dex": pool.get("dexId", "unknown"),
        "pair_address": pool.get("pairAddress", ""),
        "base": pool.get("baseToken", {}).get("symbol", "?"),
        "quote": pool.get("quoteToken", {}).get("symbol", "?"),
        "price_usd": price,
        "liquidity_usd": liq,
        "volume_24h": vol_24h,
        "age_hours": age_h,
        "total_txns_24h": total_txns,
        "buy_ratio": buy_ratio,
        "vol_liq_ratio": vol_liq_ratio,
        "price_deviation_pct": price_deviation_pct,
        "labels": pool.get("labels", []),
    }


def flag_suspicious(analysis: dict) -> list[str]:
    """Flag suspicious characteristics for a pool.

    Args:
        analysis: Pool analysis dict from analyze_pool().

    Returns:
        List of warning strings.
    """
    flags: list[str] = []

    if analysis["age_hours"] < 2:
        flags.append("VERY_NEW: Pool less than 2 hours old")
    elif analysis["age_hours"] < 24:
        flags.append("NEW: Pool less than 24 hours old")

    if analysis["liquidity_usd"] < 5_000:
        flags.append(f"MICRO_LIQUIDITY: Only ${analysis['liquidity_usd']:,.0f}")
    elif analysis["liquidity_usd"] < 10_000:
        flags.append(f"LOW_LIQUIDITY: ${analysis['liquidity_usd']:,.0f}")

    if analysis["vol_liq_ratio"] > 10:
        flags.append(f"HIGH_VOL_RATIO: {analysis['vol_liq_ratio']:.1f}x volume/TVL")

    if analysis["price_deviation_pct"] > 5:
        flags.append(f"PRICE_OFF: {analysis['price_deviation_pct']:.1f}% from median")

    if analysis["buy_ratio"] > 0.85:
        flags.append(f"BUY_SKEWED: {analysis['buy_ratio']:.0%} buys (possible bot activity)")
    elif analysis["buy_ratio"] < 0.15:
        flags.append(f"SELL_SKEWED: {1 - analysis['buy_ratio']:.0%} sells (possible dump)")

    if analysis["total_txns_24h"] < 20:
        flags.append(f"LOW_ACTIVITY: Only {analysis['total_txns_24h']} txns in 24h")

    return flags


def rank_pools(analyses: list[dict]) -> list[dict]:
    """Rank pools by execution quality.

    Scoring: 50% liquidity rank + 30% volume rank + 20% age rank.
    Penalties for suspicious flags.

    Args:
        analyses: List of pool analysis dicts.

    Returns:
        Sorted list with added 'rank_score' field.
    """
    if not analyses:
        return []

    n = len(analyses)

    # Rank by each metric (higher = better)
    by_liq = sorted(range(n), key=lambda i: analyses[i]["liquidity_usd"])
    by_vol = sorted(range(n), key=lambda i: analyses[i]["volume_24h"])
    by_age = sorted(range(n), key=lambda i: analyses[i]["age_hours"])

    liq_rank = {idx: pos for pos, idx in enumerate(by_liq)}
    vol_rank = {idx: pos for pos, idx in enumerate(by_vol)}
    age_rank = {idx: pos for pos, idx in enumerate(by_age)}

    for i, a in enumerate(analyses):
        base_score = (
            0.50 * liq_rank[i] / max(n - 1, 1)
            + 0.30 * vol_rank[i] / max(n - 1, 1)
            + 0.20 * age_rank[i] / max(n - 1, 1)
        )
        # Penalty for suspicious flags
        flags = flag_suspicious(a)
        penalty = len(flags) * 0.1
        a["rank_score"] = max(0, base_score - penalty)
        a["flags"] = flags

    return sorted(analyses, key=lambda x: x["rank_score"], reverse=True)


# ── Reporting ──────────────────────────────────────────────────────
def format_comparison(token_mint: str, ranked: list[dict]) -> str:
    """Format pool comparison report.

    Args:
        token_mint: Token mint address.
        ranked: Ranked pool analyses.

    Returns:
        Formatted report string.
    """
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("POOL COMPARISON REPORT")
    lines.append("=" * 78)
    lines.append(f"Token: {token_mint}")
    lines.append(f"Pools Found: {len(ranked)}")

    total_liq = sum(a["liquidity_usd"] for a in ranked)
    total_vol = sum(a["volume_24h"] for a in ranked)
    lines.append(f"Total Liquidity: ${total_liq:,.0f}")
    lines.append(f"Total 24h Volume: ${total_vol:,.0f}")
    lines.append("")

    # Comparison table
    lines.append("── Pool Comparison " + "─" * 58)
    header = (
        f"  {'#':>2} {'DEX':<10} {'Pair':<10} {'Liquidity':>12} "
        f"{'Volume 24h':>12} {'Age':>6} {'Txns':>6} {'Score':>6}"
    )
    lines.append(header)
    lines.append("  " + "-" * 74)

    for i, a in enumerate(ranked, 1):
        pair = f"{a['base']}/{a['quote']}"[:9]
        age_str = format_age(a["age_hours"])
        lines.append(
            f"  {i:>2} {a['dex']:<10} {pair:<10} "
            f"${a['liquidity_usd']:>10,.0f} "
            f"${a['volume_24h']:>10,.0f} "
            f"{age_str:>6} "
            f"{a['total_txns_24h']:>5} "
            f"{a['rank_score']:>5.2f}"
        )
    lines.append("")

    # Best pool recommendation
    if ranked:
        best = ranked[0]
        lines.append("── Best Pool for Execution " + "─" * 50)
        lines.append(f"  DEX: {best['dex']}")
        lines.append(f"  Pair: {best['base']}/{best['quote']}")
        lines.append(f"  Address: {best['pair_address']}")
        lines.append(f"  Liquidity: ${best['liquidity_usd']:,.0f}")
        lines.append(f"  24h Volume: ${best['volume_24h']:,.0f}")
        lines.append(f"  Age: {format_age(best['age_hours'])}")
        pct = best["liquidity_usd"] / total_liq * 100 if total_liq > 0 else 0
        lines.append(f"  Share of Total Liquidity: {pct:.1f}%")
        lines.append("")

    # Suspicious pools
    suspicious = [a for a in ranked if a.get("flags")]
    if suspicious:
        lines.append("── Suspicious Pool Flags " + "─" * 52)
        for a in suspicious:
            lines.append(f"  {a['dex']} ({a['base']}/{a['quote']}):")
            for f in a["flags"]:
                lines.append(f"    !! {f}")
        lines.append("")

    # Price comparison
    prices = [a for a in ranked if a["price_usd"] > 0]
    if len(prices) >= 2:
        lines.append("── Price Comparison " + "─" * 57)
        for a in prices:
            lines.append(f"  {a['dex']:<10} {a['base']}/{a['quote']:<8} ${a['price_usd']:.10f}")
        min_p = min(a["price_usd"] for a in prices)
        max_p = max(a["price_usd"] for a in prices)
        spread = (max_p - min_p) / min_p * 100 if min_p > 0 else 0
        lines.append(f"  Price spread: {spread:.2f}%")
        if spread > 2:
            lines.append("  !! Significant price deviation — possible arbitrage or stale pool")
        lines.append("")

    lines.append("=" * 78)
    lines.append("Note: This is informational analysis, not financial advice.")
    lines.append("Pool conditions change rapidly. Re-check before trading.")
    lines.append("=" * 78)

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run pool comparison for a token."""
    if len(sys.argv) > 1:
        token_mint = sys.argv[1]
    else:
        token_mint = os.getenv("TOKEN_MINT", "")

    use_demo = not token_mint or token_mint == "--demo"

    if use_demo:
        print("[demo mode] Using hardcoded BONK pool data")
        print("Pass a token mint address as argument for live analysis.\n")
        token_mint = DEMO_MINT
        pools = DEMO_POOLS
    else:
        print(f"Fetching pools for {token_mint}...")
        pools = fetch_pools(token_mint)
        if not pools:
            print("No pools found. Token may not be listed or mint address may be incorrect.")
            sys.exit(1)
        print(f"Found {len(pools)} pool(s).\n")

    # Analyze each pool
    analyses = [analyze_pool(p, pools) for p in pools]

    # Rank and report
    ranked = rank_pools(analyses)
    report = format_comparison(token_mint, ranked)
    print(report)


if __name__ == "__main__":
    main()
