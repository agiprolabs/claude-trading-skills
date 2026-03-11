#!/usr/bin/env python3
"""Analyze all DEX pools for a Solana token and rank them by execution quality.

Fetches pool data from DexScreener (free, no API key required), computes
health scores, flags risks, and ranks pools for optimal trade execution.

Usage:
    python scripts/analyze_pools.py <TOKEN_MINT>
    python scripts/analyze_pools.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    None required (DexScreener API is free and keyless).
"""

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

DEXSCREENER_BASE = "https://api.dexscreener.com"
REQUEST_TIMEOUT = 15.0

PROGRAM_IDS = {
    "raydium_v4": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "raydium_clmm": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
    "orca_whirlpool": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "meteora_dlmm": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "meteora_dynamic": "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",
    "pumpswap": "PSwapMdSai8tjrEXcxFeQth87xC4rRsa4VA5mhGhXkP",
}

# Fee rates by DEX (used when DexScreener doesn't report fees)
DEFAULT_FEE_RATES: dict[str, float] = {
    "raydium": 0.0025,
    "raydium_clmm": 0.0025,
    "orca": 0.003,
    "meteora": 0.003,
    "pumpswap": 0.0025,
}


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class PoolInfo:
    """Parsed pool information with computed metrics."""

    pool_address: str
    dex_id: str
    dex_name: str
    pool_type: str
    base_token: str
    quote_token: str
    base_symbol: str
    quote_symbol: str
    price_usd: float
    tvl_usd: float
    volume_24h: float
    volume_6h: float
    volume_1h: float
    price_change_24h: float
    pool_age_hours: float
    fee_rate: float
    txn_count_24h: int
    buys_24h: int
    sells_24h: int
    url: str

    # Computed metrics
    volume_efficiency: float = 0.0
    fee_apr_estimate: float = 0.0
    health_score: float = 0.0
    execution_score: float = 0.0
    red_flags: list[str] = field(default_factory=list)


# ── Pool Classification ────────────────────────────────────────────


def classify_pool_type(dex_id: str) -> str:
    """Classify pool type from DexScreener dex ID.

    Args:
        dex_id: DexScreener DEX identifier string.

    Returns:
        Pool type classification string.
    """
    dex_lower = dex_id.lower()
    if "raydium" in dex_lower and "clmm" in dex_lower:
        return "clmm"
    if "raydium" in dex_lower and "cpmm" in dex_lower:
        return "cpmm"
    if "raydium" in dex_lower:
        return "constant_product"
    if "orca" in dex_lower or "whirlpool" in dex_lower:
        return "whirlpool"
    if "meteora" in dex_lower and "dlmm" in dex_lower:
        return "dlmm"
    if "meteora" in dex_lower:
        return "dynamic"
    if "pump" in dex_lower:
        return "constant_product"
    return "unknown"


def estimate_fee_rate(dex_id: str) -> float:
    """Estimate the swap fee rate based on DEX identifier.

    Args:
        dex_id: DexScreener DEX identifier string.

    Returns:
        Estimated fee rate as a decimal (e.g., 0.0025 for 0.25%).
    """
    dex_lower = dex_id.lower()
    for key, rate in DEFAULT_FEE_RATES.items():
        if key in dex_lower:
            return rate
    return 0.003  # Conservative default


# ── Health Scoring ──────────────────────────────────────────────────


def compute_health_score(pool: PoolInfo) -> float:
    """Compute a 0-100 health score for a pool.

    Components (each 0-20 points):
    - TVL adequacy: logarithmic scale, peaks at $1M+
    - Volume efficiency: sweet spot 0.5-3.0 V/TVL ratio
    - Pool maturity: older pools score higher (max at 72h)
    - Transaction diversity: buy/sell balance
    - TVL stability: penalize negative price change as proxy

    Args:
        pool: PoolInfo with all metrics populated.

    Returns:
        Health score from 0 to 100.
    """
    # TVL score (0-20): log scale, peaks at $1M+
    if pool.tvl_usd <= 0:
        tvl_score = 0.0
    else:
        tvl_score = min(20.0, max(0.0, 5.0 * math.log10(pool.tvl_usd) - 10.0))

    # Volume score (0-20): V/TVL sweet spot 0.5-3.0
    v_tvl = pool.volume_efficiency
    if v_tvl < 5.0:
        volume_score = min(20.0, max(0.0, v_tvl * 10.0))
    else:
        volume_score = max(0.0, 20.0 - (v_tvl - 5.0) * 4.0)

    # Age score (0-20): max at 72 hours
    age_score = min(20.0, pool.pool_age_hours / 72.0 * 20.0)

    # Transaction diversity score (0-20): balanced buys/sells
    total_txns = pool.buys_24h + pool.sells_24h
    if total_txns > 0:
        buy_ratio = pool.buys_24h / total_txns
        # Perfect balance = 0.5, score drops for imbalance
        balance = 1.0 - abs(buy_ratio - 0.5) * 2.0
        txn_score = min(20.0, balance * 15.0 + min(5.0, total_txns / 200.0 * 5.0))
    else:
        txn_score = 0.0

    # Stability score (0-20): penalize extreme price moves
    abs_change = abs(pool.price_change_24h)
    stability_score = max(0.0, 20.0 - abs_change * 0.4)

    return tvl_score + volume_score + age_score + txn_score + stability_score


def check_red_flags(pool: PoolInfo) -> list[str]:
    """Check pool for warning signs and risk indicators.

    Args:
        pool: PoolInfo with all metrics populated.

    Returns:
        List of red flag description strings.
    """
    flags: list[str] = []

    if pool.tvl_usd < 1_000:
        flags.append("CRITICAL: TVL below $1,000 — extreme slippage risk")
    elif pool.tvl_usd < 10_000:
        flags.append("WARNING: TVL below $10,000 — high slippage on moderate trades")

    if pool.pool_age_hours < 1:
        flags.append("CRITICAL: Pool is less than 1 hour old — sniper risk")
    elif pool.pool_age_hours < 24:
        flags.append("WARNING: Pool is less than 24 hours old — limited history")

    if pool.volume_efficiency > 10:
        flags.append("WARNING: V/TVL > 10 — possible wash trading")
    elif pool.volume_efficiency > 5:
        flags.append("NOTICE: V/TVL > 5 — unusually high turnover")

    if pool.volume_24h == 0 and pool.pool_age_hours > 6:
        flags.append("WARNING: Zero 24h volume — pool may be dead")

    total_txns = pool.buys_24h + pool.sells_24h
    if total_txns > 0:
        buy_ratio = pool.buys_24h / total_txns
        if buy_ratio > 0.9:
            flags.append("WARNING: >90% buys — possible coordinated pump")
        elif buy_ratio < 0.1:
            flags.append("WARNING: >90% sells — possible dump in progress")

    if pool.price_change_24h < -50:
        flags.append("CRITICAL: Price dropped >50% in 24h")
    elif pool.price_change_24h < -20:
        flags.append("WARNING: Price dropped >20% in 24h")

    return flags


# ── Execution Ranking ───────────────────────────────────────────────


def estimate_slippage(pool: PoolInfo, trade_size_usd: float) -> float:
    """Estimate slippage percentage for a trade of the given size.

    Concentrated liquidity pools have better capital efficiency, resulting
    in lower slippage per TVL dollar.

    Args:
        pool: PoolInfo with pool type and TVL.
        trade_size_usd: Size of the trade in USD.

    Returns:
        Estimated slippage as a percentage (e.g., 1.0 = 1%).
    """
    if pool.tvl_usd <= 0:
        return 100.0

    base_slippage = (trade_size_usd / pool.tvl_usd) * 100.0

    # Concentrated liquidity pools have better capital efficiency
    if pool.pool_type in ("clmm", "whirlpool", "dlmm"):
        return base_slippage * 0.3  # ~3x more efficient
    return base_slippage


def rank_pools_for_execution(
    pools: list[PoolInfo], trade_size_usd: float
) -> list[PoolInfo]:
    """Rank pools by execution quality for a given trade size.

    Scoring weights:
    - 50%: Execution cost (fee + estimated slippage) — lower is better
    - 30%: Health score — higher is better
    - 20%: Fee rate — lower is better

    Args:
        pools: List of PoolInfo objects to rank.
        trade_size_usd: Trade size in USD for slippage estimation.

    Returns:
        Pools sorted by execution score, best first.
    """
    for pool in pools:
        slippage_pct = estimate_slippage(pool, trade_size_usd)
        fee_cost = pool.fee_rate * 100.0  # As percentage
        total_cost = slippage_pct + fee_cost

        # Lower cost is better — invert for scoring
        cost_score = 1.0 / max(total_cost, 0.001) * 10.0

        # Normalize health (0-100 → 0-10)
        health_norm = pool.health_score / 10.0

        # Lower fee is better — invert for scoring
        fee_score = 1.0 / max(pool.fee_rate, 0.0001)

        pool.execution_score = cost_score * 0.5 + health_norm * 0.3 + fee_score * 0.0002

    pools.sort(key=lambda p: p.execution_score, reverse=True)
    return pools


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_pools(token_mint: str) -> list[PoolInfo]:
    """Fetch all Solana pools for a token from DexScreener.

    Args:
        token_mint: Solana token mint address.

    Returns:
        List of PoolInfo objects.

    Raises:
        httpx.HTTPStatusError: On non-2xx response from DexScreener.
    """
    url = f"{DEXSCREENER_BASE}/tokens/v1/solana/{token_mint}"
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        resp = client.get(url)
        resp.raise_for_status()
        raw_pools = resp.json()

    if not isinstance(raw_pools, list):
        print(f"Unexpected response format: {type(raw_pools)}")
        return []

    pools: list[PoolInfo] = []
    now_ms = int(time.time() * 1000)

    for p in raw_pools:
        # Skip non-Solana pools
        if p.get("chainId", "") != "solana":
            continue

        created_at = p.get("pairCreatedAt", now_ms)
        age_hours = max(0, (now_ms - created_at) / 3_600_000)

        liquidity = p.get("liquidity") or {}
        volume = p.get("volume") or {}
        price_change = p.get("priceChange") or {}
        txns = p.get("txns") or {}
        txns_24h = txns.get("h24") or {}

        dex_id = p.get("dexId", "unknown")

        pool_info = PoolInfo(
            pool_address=p.get("pairAddress", ""),
            dex_id=dex_id,
            dex_name=p.get("dexId", "unknown"),
            pool_type=classify_pool_type(dex_id),
            base_token=p.get("baseToken", {}).get("address", ""),
            quote_token=p.get("quoteToken", {}).get("address", ""),
            base_symbol=p.get("baseToken", {}).get("symbol", "???"),
            quote_symbol=p.get("quoteToken", {}).get("symbol", "???"),
            price_usd=float(p.get("priceUsd", 0) or 0),
            tvl_usd=float(liquidity.get("usd", 0) or 0),
            volume_24h=float(volume.get("h24", 0) or 0),
            volume_6h=float(volume.get("h6", 0) or 0),
            volume_1h=float(volume.get("h1", 0) or 0),
            price_change_24h=float(price_change.get("h24", 0) or 0),
            pool_age_hours=age_hours,
            fee_rate=estimate_fee_rate(dex_id),
            txn_count_24h=int(txns_24h.get("buys", 0) or 0)
            + int(txns_24h.get("sells", 0) or 0),
            buys_24h=int(txns_24h.get("buys", 0) or 0),
            sells_24h=int(txns_24h.get("sells", 0) or 0),
            url=p.get("url", ""),
        )

        # Compute derived metrics
        pool_info.volume_efficiency = (
            pool_info.volume_24h / pool_info.tvl_usd if pool_info.tvl_usd > 0 else 0.0
        )
        pool_info.fee_apr_estimate = (
            pool_info.volume_efficiency * pool_info.fee_rate * 365 * 100
        )
        pool_info.health_score = compute_health_score(pool_info)
        pool_info.red_flags = check_red_flags(pool_info)

        pools.append(pool_info)

    return pools


# ── Demo Data ───────────────────────────────────────────────────────


def generate_demo_pools() -> list[PoolInfo]:
    """Generate synthetic multi-pool data for demo mode.

    Creates a realistic scenario: a token with pools across multiple DEXes
    at different stages of maturity and health.

    Returns:
        List of synthetic PoolInfo objects.
    """
    demo_pools_raw = [
        {
            "name": "Raydium V4 (Main)",
            "pool_address": "DemoPool1111111111111111111111111111111111111",
            "dex_id": "raydium",
            "pool_type": "constant_product",
            "tvl_usd": 250_000,
            "volume_24h": 500_000,
            "volume_6h": 120_000,
            "volume_1h": 18_000,
            "price_change_24h": 5.2,
            "pool_age_hours": 720,
            "fee_rate": 0.0025,
            "buys_24h": 1200,
            "sells_24h": 980,
        },
        {
            "name": "Orca Whirlpool (CL)",
            "pool_address": "DemoPool2222222222222222222222222222222222222",
            "dex_id": "orca",
            "pool_type": "whirlpool",
            "tvl_usd": 180_000,
            "volume_24h": 420_000,
            "volume_6h": 100_000,
            "volume_1h": 15_000,
            "price_change_24h": 5.1,
            "pool_age_hours": 480,
            "fee_rate": 0.003,
            "buys_24h": 800,
            "sells_24h": 750,
        },
        {
            "name": "Meteora DLMM",
            "pool_address": "DemoPool3333333333333333333333333333333333333",
            "dex_id": "meteora_dlmm",
            "pool_type": "dlmm",
            "tvl_usd": 85_000,
            "volume_24h": 200_000,
            "volume_6h": 55_000,
            "volume_1h": 8_000,
            "price_change_24h": 4.8,
            "pool_age_hours": 168,
            "fee_rate": 0.003,
            "buys_24h": 400,
            "sells_24h": 380,
        },
        {
            "name": "Raydium CLMM",
            "pool_address": "DemoPool4444444444444444444444444444444444444",
            "dex_id": "raydium_clmm",
            "pool_type": "clmm",
            "tvl_usd": 60_000,
            "volume_24h": 150_000,
            "volume_6h": 35_000,
            "volume_1h": 5_000,
            "price_change_24h": 5.5,
            "pool_age_hours": 96,
            "fee_rate": 0.0025,
            "buys_24h": 300,
            "sells_24h": 280,
        },
        {
            "name": "PumpSwap (New)",
            "pool_address": "DemoPool5555555555555555555555555555555555555",
            "dex_id": "pumpswap",
            "pool_type": "constant_product",
            "tvl_usd": 12_000,
            "volume_24h": 180_000,
            "volume_6h": 80_000,
            "volume_1h": 25_000,
            "price_change_24h": 45.0,
            "pool_age_hours": 3,
            "fee_rate": 0.0025,
            "buys_24h": 2500,
            "sells_24h": 500,
        },
        {
            "name": "Dead Pool (Raydium V4)",
            "pool_address": "DemoPool6666666666666666666666666666666666666",
            "dex_id": "raydium",
            "pool_type": "constant_product",
            "tvl_usd": 500,
            "volume_24h": 0,
            "volume_6h": 0,
            "volume_1h": 0,
            "price_change_24h": -85.0,
            "pool_age_hours": 2400,
            "fee_rate": 0.0025,
            "buys_24h": 0,
            "sells_24h": 0,
        },
    ]

    pools: list[PoolInfo] = []
    for d in demo_pools_raw:
        pool = PoolInfo(
            pool_address=d["pool_address"],
            dex_id=d["dex_id"],
            dex_name=d["name"],
            pool_type=d["pool_type"],
            base_token="DemoMint1111111111111111111111111111111111111",
            quote_token="So11111111111111111111111111111111111111112",
            base_symbol="DEMO",
            quote_symbol="SOL",
            price_usd=0.00042,
            tvl_usd=d["tvl_usd"],
            volume_24h=d["volume_24h"],
            volume_6h=d["volume_6h"],
            volume_1h=d["volume_1h"],
            price_change_24h=d["price_change_24h"],
            pool_age_hours=d["pool_age_hours"],
            fee_rate=d["fee_rate"],
            txn_count_24h=d["buys_24h"] + d["sells_24h"],
            buys_24h=d["buys_24h"],
            sells_24h=d["sells_24h"],
            url=f"https://dexscreener.com/solana/{d['pool_address']}",
        )

        pool.volume_efficiency = (
            pool.volume_24h / pool.tvl_usd if pool.tvl_usd > 0 else 0.0
        )
        pool.fee_apr_estimate = pool.volume_efficiency * pool.fee_rate * 365 * 100
        pool.health_score = compute_health_score(pool)
        pool.red_flags = check_red_flags(pool)
        pools.append(pool)

    return pools


# ── Display ─────────────────────────────────────────────────────────


def print_pool_summary(pool: PoolInfo, rank: int) -> None:
    """Print a formatted summary of a single pool.

    Args:
        pool: PoolInfo to display.
        rank: Display rank number.
    """
    print(f"\n{'='*70}")
    print(f"  #{rank}  {pool.dex_name} — {pool.base_symbol}/{pool.quote_symbol}")
    print(f"{'='*70}")
    print(f"  Pool Type:      {pool.pool_type}")
    print(f"  Pool Address:   {pool.pool_address[:20]}...")
    print(f"  Price (USD):    ${pool.price_usd:.8f}")
    print(f"  TVL:            ${pool.tvl_usd:,.0f}")
    print(f"  Volume (24h):   ${pool.volume_24h:,.0f}")
    print(f"  Volume (1h):    ${pool.volume_1h:,.0f}")
    print(f"  V/TVL Ratio:    {pool.volume_efficiency:.2f}")
    print(f"  Fee Rate:       {pool.fee_rate*100:.2f}%")
    print(f"  Fee APR Est:    {pool.fee_apr_estimate:.1f}%")
    print(f"  Pool Age:       {pool.pool_age_hours:.0f} hours ({pool.pool_age_hours/24:.1f} days)")
    print(f"  Txns (24h):     {pool.txn_count_24h} (buys: {pool.buys_24h}, sells: {pool.sells_24h})")
    print(f"  Price Δ (24h):  {pool.price_change_24h:+.1f}%")
    print(f"  Health Score:   {pool.health_score:.1f}/100")
    print(f"  Exec Score:     {pool.execution_score:.2f}")

    if pool.red_flags:
        print(f"\n  Red Flags:")
        for flag in pool.red_flags:
            print(f"    - {flag}")
    else:
        print(f"\n  Red Flags:      None")


def print_execution_recommendation(
    pools: list[PoolInfo], trade_size_usd: float
) -> None:
    """Print execution recommendation based on ranked pools.

    Args:
        pools: Ranked list of pools (best first).
        trade_size_usd: Trade size used for ranking.
    """
    print(f"\n{'='*70}")
    print(f"  EXECUTION ANALYSIS (trade size: ${trade_size_usd:,.0f})")
    print(f"{'='*70}")

    viable = [p for p in pools if p.tvl_usd >= trade_size_usd * 50]

    if not viable:
        print("\n  No pools have sufficient TVL for this trade size.")
        print(f"  Minimum TVL needed: ${trade_size_usd * 50:,.0f}")
        print("  Consider reducing trade size or splitting across pools.")
        return

    best = viable[0]
    slippage = estimate_slippage(best, trade_size_usd)
    total_cost = slippage + best.fee_rate * 100

    print(f"\n  Recommended Pool: {best.dex_name}")
    print(f"  Pool Type:        {best.pool_type}")
    print(f"  Est. Slippage:    {slippage:.3f}%")
    print(f"  Fee:              {best.fee_rate*100:.2f}%")
    print(f"  Total Est. Cost:  {total_cost:.3f}% (${trade_size_usd * total_cost / 100:,.2f})")

    if best.red_flags:
        print(f"\n  Caution — flags on recommended pool:")
        for flag in best.red_flags:
            print(f"    - {flag}")

    if len(viable) > 1:
        print(f"\n  Alternative pools ({len(viable)-1}):")
        for alt in viable[1:3]:
            alt_slip = estimate_slippage(alt, trade_size_usd)
            alt_cost = alt_slip + alt.fee_rate * 100
            print(f"    - {alt.dex_name}: ~{alt_cost:.3f}% total cost")


def print_report(pools: list[PoolInfo], trade_size_usd: float) -> None:
    """Print full analysis report for all pools.

    Args:
        pools: List of PoolInfo objects (will be ranked internally).
        trade_size_usd: Trade size for execution analysis.
    """
    if not pools:
        print("No pools found.")
        return

    print(f"\n{'#'*70}")
    print(f"  DEX POOL ANALYSIS REPORT")
    print(f"  Token: {pools[0].base_symbol}/{pools[0].quote_symbol}")
    print(f"  Pools found: {len(pools)}")
    print(f"{'#'*70}")

    # Rank pools for execution
    ranked = rank_pools_for_execution(pools, trade_size_usd)

    # Print each pool
    for i, pool in enumerate(ranked, 1):
        print_pool_summary(pool, i)

    # Execution recommendation
    print_execution_recommendation(ranked, trade_size_usd)

    # Summary statistics
    total_tvl = sum(p.tvl_usd for p in pools)
    total_vol = sum(p.volume_24h for p in pools)
    critical_flags = sum(
        1 for p in pools for f in p.red_flags if f.startswith("CRITICAL")
    )

    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Total TVL across pools:    ${total_tvl:,.0f}")
    print(f"  Total Volume (24h):        ${total_vol:,.0f}")
    print(f"  Aggregate V/TVL:           {total_vol / max(total_tvl, 1):.2f}")
    print(f"  Pools with critical flags: {critical_flags}/{len(pools)}")
    print(f"  Pool types: {', '.join(sorted(set(p.pool_type for p in pools)))}")

    print(f"\n  Note: This analysis provides information only, not financial advice.")
    print(f"  Always verify pool data on-chain before executing trades.\n")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: parse arguments and run pool analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze DEX pools for a Solana token"
    )
    parser.add_argument(
        "token_mint",
        nargs="?",
        default=None,
        help="Solana token mint address to analyze",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic demo data (no API calls)",
    )
    parser.add_argument(
        "--trade-size",
        type=float,
        default=500.0,
        help="Trade size in USD for execution analysis (default: 500)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    if args.demo:
        print("Running in demo mode with synthetic pool data...\n")
        pools = generate_demo_pools()
    elif args.token_mint:
        print(f"Fetching pools for {args.token_mint}...")
        try:
            pools = fetch_pools(args.token_mint)
        except httpx.HTTPStatusError as e:
            print(f"API error: {e.response.status_code} — {e.response.text[:200]}")
            sys.exit(1)
        except httpx.RequestError as e:
            print(f"Network error: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/analyze_pools.py --demo")
        print("  python scripts/analyze_pools.py <TOKEN_MINT_ADDRESS>")
        sys.exit(1)

    if args.json:
        output = []
        for p in pools:
            output.append({
                "pool_address": p.pool_address,
                "dex": p.dex_name,
                "pool_type": p.pool_type,
                "tvl_usd": p.tvl_usd,
                "volume_24h": p.volume_24h,
                "volume_efficiency": round(p.volume_efficiency, 4),
                "fee_apr_estimate": round(p.fee_apr_estimate, 2),
                "health_score": round(p.health_score, 2),
                "red_flags": p.red_flags,
            })
        print(json.dumps(output, indent=2))
    else:
        print_report(pools, args.trade_size)


if __name__ == "__main__":
    main()
