#!/usr/bin/env python3
"""Analyze DEX liquidity depth for a Solana token.

Fetches pool data from DexScreener and Jupiter quotes to build a complete
liquidity profile: pool inventory, slippage curve, composite score, and
risk flags.

Usage:
    python scripts/analyze_liquidity.py                     # Demo mode (SOL/USDC)
    python scripts/analyze_liquidity.py <token_mint>        # Analyze specific token
    TOKEN_MINT=<address> python scripts/analyze_liquidity.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Token mint address (optional, overridden by CLI arg)
"""

import math
import os
import sys
import time
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────
SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS = 1_000_000_000
SLIPPAGE_TEST_SIZES = [0.1, 0.5, 1.0, 5.0, 10.0, 25.0]
DEXSCREENER_BASE = "https://api.dexscreener.com"
JUPITER_QUOTE_URL = "https://api.jup.ag/quote/v1"

# Demo data for --demo mode or when API calls fail
DEMO_MINT = SOL_MINT  # SOL itself for demo
DEMO_POOLS = [
    {
        "pairAddress": "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
        "dexId": "raydium",
        "baseToken": {"symbol": "SOL"},
        "quoteToken": {"symbol": "USDC"},
        "priceUsd": "145.50",
        "liquidity": {"usd": 12_500_000, "base": 43_000, "quote": 6_250_000},
        "volume": {"h24": 85_000_000},
        "pairCreatedAt": int((time.time() - 365 * 86400) * 1000),
        "labels": [],
    },
    {
        "pairAddress": "7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm",
        "dexId": "orca",
        "baseToken": {"symbol": "SOL"},
        "quoteToken": {"symbol": "USDC"},
        "priceUsd": "145.48",
        "liquidity": {"usd": 8_200_000, "base": 28_200, "quote": 4_100_000},
        "volume": {"h24": 42_000_000},
        "pairCreatedAt": int((time.time() - 300 * 86400) * 1000),
        "labels": ["concentrated"],
    },
    {
        "pairAddress": "FpCMFDFGYotvufJ7HrFHsWEiiQCGbkLCtwHiDnh7o28Q",
        "dexId": "meteora",
        "baseToken": {"symbol": "SOL"},
        "quoteToken": {"symbol": "USDC"},
        "priceUsd": "145.52",
        "liquidity": {"usd": 3_100_000, "base": 10_700, "quote": 1_550_000},
        "volume": {"h24": 15_000_000},
        "pairCreatedAt": int((time.time() - 120 * 86400) * 1000),
        "labels": ["dlmm"],
    },
]


# ── Data Fetching ──────────────────────────────────────────────────
def fetch_pools(mint: str) -> list[dict]:
    """Fetch all DEX pools for a token from DexScreener.

    Args:
        mint: Token mint address.

    Returns:
        List of pool/pair objects with liquidity data.
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


def fetch_jupiter_quote(
    token_mint: str, sol_amount: float, client: httpx.Client
) -> Optional[dict]:
    """Fetch a Jupiter quote for a specific trade size.

    Args:
        token_mint: Output token mint address.
        sol_amount: Amount of SOL to swap.
        client: Reusable httpx client.

    Returns:
        Quote response dict, or None on failure.
    """
    try:
        resp = client.get(
            JUPITER_QUOTE_URL,
            params={
                "inputMint": SOL_MINT,
                "outputMint": token_mint,
                "amount": str(int(sol_amount * LAMPORTS)),
                "slippageBps": 5000,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except (httpx.HTTPError, ValueError):
        pass
    return None


def build_slippage_curve(
    token_mint: str, sizes: Optional[list[float]] = None
) -> list[dict]:
    """Build empirical slippage curve via Jupiter quotes.

    Args:
        token_mint: Token to buy with SOL.
        sizes: SOL amounts to test.

    Returns:
        List of dicts with sol, tokens_out, slippage_bps.
    """
    if sizes is None:
        sizes = SLIPPAGE_TEST_SIZES

    results: list[dict] = []
    base_rate: Optional[float] = None

    with httpx.Client() as client:
        for sol in sizes:
            quote = fetch_jupiter_quote(token_mint, sol, client)
            if quote is None:
                continue
            out_amount = int(quote.get("outAmount", 0))
            if out_amount <= 0:
                continue
            rate = out_amount / sol
            if base_rate is None:
                base_rate = rate
            slippage_bps = int((1 - rate / base_rate) * 10000) if base_rate else 0
            results.append({
                "sol": sol,
                "tokens_out": out_amount,
                "slippage_bps": max(0, slippage_bps),
                "price_impact_pct": quote.get("priceImpactPct", "0"),
            })
            time.sleep(0.15)  # Respect rate limits

    return results


# ── Analysis Functions ─────────────────────────────────────────────
def pool_age_hours(pair_created_at_ms: int) -> float:
    """Calculate pool age in hours from creation timestamp.

    Args:
        pair_created_at_ms: Pool creation time in milliseconds.

    Returns:
        Age in hours, or 0 if timestamp is invalid.
    """
    if pair_created_at_ms <= 0:
        return 0.0
    return max(0.0, (time.time() * 1000 - pair_created_at_ms) / 3_600_000)


def compute_liquidity_score(
    total_liquidity_usd: float,
    pool_count: int,
    largest_pool_pct: float,
    oldest_pool_hours: float,
    max_slippage_bps_at_1sol: int,
) -> int:
    """Compute composite liquidity score from 0 (dangerous) to 100 (deep).

    Components:
        Depth (40%): log-scaled TVL from $1K (0) to $1M+ (40)
        Diversity (15%): more pools = more resilient, capped at 5 pools
        Concentration (15%): penalty if one pool dominates
        Age (15%): older pools are more reliable, full marks at 7 days
        Slippage (15%): lower slippage at 1 SOL = better

    Args:
        total_liquidity_usd: Total liquidity across all pools in USD.
        pool_count: Number of active pools.
        largest_pool_pct: Fraction of total liquidity in the largest pool (0-1).
        oldest_pool_hours: Age of the oldest pool in hours.
        max_slippage_bps_at_1sol: Slippage in bps for a 1 SOL trade.

    Returns:
        Score from 0 to 100.
    """
    # Depth: 0-40 points (log scale: $1K=0, $1M=40)
    if total_liquidity_usd <= 0:
        depth = 0
    else:
        depth = min(40, int(40 * math.log10(max(total_liquidity_usd, 1)) / 6))

    # Diversity: 0-15 points (3 pts per pool, max 5 pools)
    diversity = min(15, pool_count * 3)

    # Concentration: 0-15 points (penalize single-pool dominance)
    concentration = int(15 * (1 - largest_pool_pct))

    # Age: 0-15 points (7+ days = full marks)
    age = min(15, int(15 * min(oldest_pool_hours, 168) / 168))

    # Slippage: 0-15 points (0 bps = 15 pts, 150+ bps = 0 pts)
    slippage = max(0, 15 - max_slippage_bps_at_1sol // 10)

    return max(0, min(100, depth + diversity + concentration + age + slippage))


def detect_risk_flags(pools: list[dict]) -> list[str]:
    """Detect liquidity risk flags from pool data.

    Args:
        pools: List of DexScreener pool/pair objects.

    Returns:
        List of human-readable warning strings.
    """
    flags: list[str] = []

    if len(pools) == 0:
        flags.append("NO_POOLS: No active pools found")
        return flags

    if len(pools) == 1:
        flags.append("SINGLE_POOL: Only 1 pool exists — exit may be difficult")

    total_liq = sum(p.get("liquidity", {}).get("usd", 0) for p in pools)
    if total_liq < 10_000:
        flags.append(f"THIN_LIQUIDITY: Total TVL ${total_liq:,.0f} < $10,000")

    for p in pools:
        age_h = pool_age_hours(p.get("pairCreatedAt", 0))
        if 0 < age_h < 2:
            dex = p.get("dexId", "unknown")
            flags.append(f"NEW_POOL: {dex} pool is {age_h:.1f}h old")

    for p in pools:
        vol = p.get("volume", {}).get("h24", 0)
        liq = p.get("liquidity", {}).get("usd", 0)
        if liq > 0 and vol / liq > 10:
            dex = p.get("dexId", "unknown")
            flags.append(f"VOLUME_MISMATCH: {dex} 24h volume/TVL = {vol/liq:.1f}x (possible wash trading)")

    prices = [float(p.get("priceUsd", 0)) for p in pools if float(p.get("priceUsd", 0)) > 0]
    if len(prices) >= 2:
        deviation = (max(prices) - min(prices)) / min(prices)
        if deviation > 0.05:
            flags.append(f"PRICE_DEVIATION: {deviation:.1%} price difference across pools")

    return flags


def max_position_from_liquidity(
    total_liquidity_usd: float,
    max_slippage_pct: float = 1.0,
    trade_type: str = "swing",
) -> float:
    """Estimate maximum position size in USD based on available liquidity.

    Uses rule-of-thumb: for constant-product AMMs, trading X% of pool
    reserves produces approximately X% slippage.

    Args:
        total_liquidity_usd: Total liquidity across all pools.
        max_slippage_pct: Maximum acceptable slippage percentage.
        trade_type: One of "scalp", "swing", "position".

    Returns:
        Maximum position size in USD.
    """
    fractions = {"scalp": 0.01, "swing": 0.03, "position": 0.07}
    base_fraction = fractions.get(trade_type, 0.03)
    adjusted = base_fraction * (max_slippage_pct / 2.0)
    return total_liquidity_usd * adjusted


# ── Reporting ──────────────────────────────────────────────────────
def format_report(
    token_mint: str,
    pools: list[dict],
    slippage_curve: list[dict],
    score: int,
    flags: list[str],
    max_pos: float,
) -> str:
    """Format a complete liquidity analysis report.

    Args:
        token_mint: Token mint address.
        pools: Pool data from DexScreener.
        slippage_curve: Empirical slippage data from Jupiter.
        score: Composite liquidity score (0-100).
        flags: Risk flag strings.
        max_pos: Maximum recommended position size in USD.

    Returns:
        Formatted report string.
    """
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("LIQUIDITY ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append(f"Token: {token_mint}")
    lines.append(f"Pools: {len(pools)}")

    total_liq = sum(p.get("liquidity", {}).get("usd", 0) for p in pools)
    total_vol = sum(p.get("volume", {}).get("h24", 0) for p in pools)
    lines.append(f"Total Liquidity: ${total_liq:,.0f}")
    lines.append(f"Total 24h Volume: ${total_vol:,.0f}")
    lines.append("")

    # Pool breakdown
    lines.append("── Pool Breakdown " + "─" * 52)
    lines.append(f"  {'DEX':<12} {'Liquidity':>14} {'Volume 24h':>14} {'Age':>10} {'Price':>12}")
    lines.append("  " + "-" * 64)
    for p in sorted(pools, key=lambda x: x.get("liquidity", {}).get("usd", 0), reverse=True):
        dex = p.get("dexId", "?")[:11]
        liq = p.get("liquidity", {}).get("usd", 0)
        vol = p.get("volume", {}).get("h24", 0)
        age_h = pool_age_hours(p.get("pairCreatedAt", 0))
        price = p.get("priceUsd", "?")
        if age_h > 24:
            age_str = f"{age_h / 24:.0f}d"
        else:
            age_str = f"{age_h:.1f}h"
        lines.append(f"  {dex:<12} ${liq:>12,.0f} ${vol:>12,.0f} {age_str:>10} ${price:>10}")
    lines.append("")

    # Slippage curve
    if slippage_curve:
        lines.append("── Slippage Curve " + "─" * 52)
        lines.append(f"  {'SOL':>8} {'Tokens Out':>16} {'Slippage':>10} {'Impact':>10}")
        lines.append("  " + "-" * 46)
        for s in slippage_curve:
            sol_str = f"{s['sol']:.1f}"
            tokens = f"{s['tokens_out']:,}"
            slip = f"{s['slippage_bps']} bps"
            impact = f"{s.get('price_impact_pct', '?')}%"
            lines.append(f"  {sol_str:>8} {tokens:>16} {slip:>10} {impact:>10}")
        lines.append("")

    # Score and sizing
    lines.append("── Assessment " + "─" * 56)
    score_label = (
        "CRITICAL" if score < 20 else
        "POOR" if score < 40 else
        "FAIR" if score < 60 else
        "GOOD" if score < 80 else
        "EXCELLENT"
    )
    lines.append(f"  Liquidity Score: {score}/100 ({score_label})")
    lines.append(f"  Max Position (swing, 1% slip): ${max_pos:,.0f}")
    lines.append(f"  Max Position (scalp, 0.5% slip): ${max_position_from_liquidity(total_liq, 0.5, 'scalp'):,.0f}")
    lines.append("")

    # Risk flags
    if flags:
        lines.append("── Risk Flags " + "─" * 56)
        for f in flags:
            lines.append(f"  !! {f}")
        lines.append("")
    else:
        lines.append("── Risk Flags " + "─" * 56)
        lines.append("  No risk flags detected.")
        lines.append("")

    lines.append("=" * 70)
    lines.append("Note: This is informational analysis, not financial advice.")
    lines.append("Liquidity conditions change rapidly. Re-check before trading.")
    lines.append("=" * 70)

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run liquidity analysis for a token."""
    # Determine token mint
    if len(sys.argv) > 1:
        token_mint = sys.argv[1]
    else:
        token_mint = os.getenv("TOKEN_MINT", "")

    use_demo = not token_mint or token_mint == "--demo"

    if use_demo:
        print("[demo mode] Using hardcoded SOL/USDC pool data")
        print("Pass a token mint address as argument for live analysis.\n")
        token_mint = DEMO_MINT
        pools = DEMO_POOLS
        slippage_curve: list[dict] = [
            {"sol": 0.1, "tokens_out": 68_900, "slippage_bps": 0, "price_impact_pct": "0.00"},
            {"sol": 0.5, "tokens_out": 344_400, "slippage_bps": 1, "price_impact_pct": "0.01"},
            {"sol": 1.0, "tokens_out": 688_700, "slippage_bps": 2, "price_impact_pct": "0.02"},
            {"sol": 5.0, "tokens_out": 3_442_000, "slippage_bps": 5, "price_impact_pct": "0.05"},
            {"sol": 10.0, "tokens_out": 6_880_000, "slippage_bps": 8, "price_impact_pct": "0.08"},
            {"sol": 25.0, "tokens_out": 17_190_000, "slippage_bps": 15, "price_impact_pct": "0.15"},
        ]
    else:
        print(f"Fetching pools for {token_mint}...")
        pools = fetch_pools(token_mint)
        if not pools:
            print("No pools found. Token may not be listed or mint address may be incorrect.")
            sys.exit(1)
        print(f"Found {len(pools)} pool(s). Building slippage curve...")
        slippage_curve = build_slippage_curve(token_mint)

    # Compute metrics
    total_liq = sum(p.get("liquidity", {}).get("usd", 0) for p in pools)
    if total_liq > 0:
        largest_pool_liq = max(p.get("liquidity", {}).get("usd", 0) for p in pools)
        largest_pool_pct = largest_pool_liq / total_liq
    else:
        largest_pool_pct = 1.0

    oldest_hours = max(
        (pool_age_hours(p.get("pairCreatedAt", 0)) for p in pools),
        default=0.0,
    )

    slippage_at_1sol = 0
    for s in slippage_curve:
        if s["sol"] == 1.0:
            slippage_at_1sol = s["slippage_bps"]
            break

    score = compute_liquidity_score(
        total_liq, len(pools), largest_pool_pct, oldest_hours, slippage_at_1sol
    )
    flags = detect_risk_flags(pools)
    max_pos = max_position_from_liquidity(total_liq, max_slippage_pct=1.0, trade_type="swing")

    report = format_report(token_mint, pools, slippage_curve, score, flags, max_pos)
    print(report)


if __name__ == "__main__":
    main()
