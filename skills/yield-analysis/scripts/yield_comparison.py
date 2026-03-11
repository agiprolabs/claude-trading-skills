#!/usr/bin/env python3
"""Fetch and compare DeFi yield opportunities on Solana.

Queries the DeFiLlama yields API (free, no authentication) for Solana pools
and lending markets, then ranks them by risk-adjusted yield. Includes a
--demo mode with representative data for offline use.

Usage:
    python scripts/yield_comparison.py
    python scripts/yield_comparison.py --demo
    python scripts/yield_comparison.py --min-tvl 1000000 --top 20

Dependencies:
    uv pip install httpx

Environment Variables:
    None required — DeFiLlama yields API is free and requires no API key.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    print("httpx is required. Install with: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

DEFILLAMA_YIELDS_URL = "https://yields.llama.fi/pools"
REQUEST_TIMEOUT = 30
SOL_STAKING_APR = 7.0  # Baseline SOL staking APR for comparison


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class YieldOpportunity:
    """A single yield opportunity with decomposed metrics."""

    pool_id: str
    project: str
    symbol: str
    chain: str
    tvl_usd: float
    apy_total: float
    apy_base: float  # From fees / real yield
    apy_reward: float  # From emissions
    il_7d: Optional[float]  # 7-day IL percentage
    exposure: str  # "single" or "multi"
    risk_tier: str  # Computed: "low", "medium", "high"
    real_yield_pct: float  # Percentage of yield from fees
    risk_adjusted_yield: float  # yield / risk_score


# ── Risk Assessment ─────────────────────────────────────────────────


def classify_risk(
    apy_total: float,
    apy_base: float,
    apy_reward: float,
    tvl_usd: float,
    exposure: str,
) -> tuple[str, float]:
    """Classify the risk tier and compute a risk score for a yield opportunity.

    Risk score ranges from 1 (lowest risk) to 10 (highest risk).

    Args:
        apy_total: Total APY.
        apy_base: Base APY from fees.
        apy_reward: Reward APY from emissions.
        tvl_usd: Total value locked in USD.
        exposure: "single" for single-asset, "multi" for multi-asset.

    Returns:
        Tuple of (risk_tier, risk_score).
    """
    score = 0.0

    # Emission dependency: high reward APY relative to base = more risk
    if apy_total > 0:
        emission_ratio = apy_reward / apy_total
    else:
        emission_ratio = 0
    score += emission_ratio * 3.0  # Max 3.0

    # Absolute yield level: very high APY is suspicious
    if apy_total > 100:
        score += 2.5
    elif apy_total > 50:
        score += 1.5
    elif apy_total > 20:
        score += 0.5

    # TVL: lower TVL = higher risk (less battle-tested, more slippage)
    if tvl_usd < 100_000:
        score += 2.0
    elif tvl_usd < 1_000_000:
        score += 1.0
    elif tvl_usd < 10_000_000:
        score += 0.5

    # Multi-asset exposure has IL risk
    if exposure == "multi":
        score += 1.0

    # Clamp to 1-10 range
    score = max(1.0, min(10.0, score))

    if score <= 3.0:
        tier = "low"
    elif score <= 6.0:
        tier = "medium"
    else:
        tier = "high"

    return tier, score


def compute_real_yield_pct(apy_base: float, apy_total: float) -> float:
    """Compute what percentage of total yield comes from real sources (fees).

    Args:
        apy_base: Base APY from fees.
        apy_total: Total APY.

    Returns:
        Percentage of yield from fees (0-100).
    """
    if apy_total <= 0:
        return 0.0
    return min(100.0, (apy_base / apy_total) * 100)


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_solana_yields(min_tvl: float = 100_000) -> list[dict]:
    """Fetch Solana yield data from DeFiLlama.

    Args:
        min_tvl: Minimum TVL filter in USD.

    Returns:
        List of pool dictionaries from DeFiLlama.

    Raises:
        httpx.HTTPStatusError: On API error.
        httpx.ConnectError: On network failure.
    """
    try:
        response = httpx.get(DEFILLAMA_YIELDS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except httpx.ConnectError:
        print("Error: Could not connect to DeFiLlama API.")
        print("Check your internet connection or try --demo mode.")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: DeFiLlama API returned {e.response.status_code}")
        sys.exit(1)

    data = response.json()
    pools = data.get("data", [])

    # Filter for Solana pools with minimum TVL
    solana_pools = [
        p for p in pools
        if p.get("chain") == "Solana"
        and (p.get("tvlUsd") or 0) >= min_tvl
        and (p.get("apy") or 0) > 0
    ]

    return solana_pools


def parse_pool(pool: dict) -> YieldOpportunity:
    """Parse a DeFiLlama pool dict into a YieldOpportunity.

    Args:
        pool: Raw pool data from DeFiLlama.

    Returns:
        Parsed YieldOpportunity with risk assessment.
    """
    apy_total = pool.get("apy") or 0.0
    apy_base = pool.get("apyBase") or 0.0
    apy_reward = pool.get("apyReward") or 0.0
    tvl_usd = pool.get("tvlUsd") or 0.0
    exposure = pool.get("exposure") or "multi"
    il_7d = pool.get("il7d")

    risk_tier, risk_score = classify_risk(
        apy_total, apy_base, apy_reward, tvl_usd, exposure
    )

    real_pct = compute_real_yield_pct(apy_base, apy_total)

    # Risk-adjusted yield: higher is better
    risk_adjusted = apy_total / risk_score if risk_score > 0 else 0

    return YieldOpportunity(
        pool_id=pool.get("pool", ""),
        project=pool.get("project", "unknown"),
        symbol=pool.get("symbol", "???"),
        chain="Solana",
        tvl_usd=tvl_usd,
        apy_total=apy_total,
        apy_base=apy_base,
        apy_reward=apy_reward,
        il_7d=il_7d,
        exposure=exposure,
        risk_tier=risk_tier,
        real_yield_pct=real_pct,
        risk_adjusted_yield=risk_adjusted,
    )


# ── Demo Data ───────────────────────────────────────────────────────


def demo_data() -> list[YieldOpportunity]:
    """Generate representative Solana yield data for offline demo.

    Returns:
        List of YieldOpportunity objects with realistic parameters.
    """
    pools = [
        # LP pools
        {"project": "raydium", "symbol": "SOL-USDC", "tvl": 45_000_000,
         "apy": 22.5, "base": 16.8, "reward": 5.7, "exposure": "multi"},
        {"project": "orca", "symbol": "SOL-USDC", "tvl": 38_000_000,
         "apy": 19.2, "base": 15.1, "reward": 4.1, "exposure": "multi"},
        {"project": "raydium", "symbol": "SOL-mSOL", "tvl": 12_000_000,
         "apy": 11.3, "base": 8.2, "reward": 3.1, "exposure": "multi"},
        {"project": "orca", "symbol": "SOL-jitoSOL", "tvl": 8_500_000,
         "apy": 12.8, "base": 9.5, "reward": 3.3, "exposure": "multi"},
        {"project": "raydium", "symbol": "USDC-USDT", "tvl": 55_000_000,
         "apy": 5.2, "base": 4.8, "reward": 0.4, "exposure": "multi"},
        {"project": "meteora", "symbol": "SOL-USDC", "tvl": 15_000_000,
         "apy": 28.4, "base": 22.1, "reward": 6.3, "exposure": "multi"},
        {"project": "raydium", "symbol": "RAY-USDC", "tvl": 6_200_000,
         "apy": 35.6, "base": 12.3, "reward": 23.3, "exposure": "multi"},
        {"project": "orca", "symbol": "BONK-SOL", "tvl": 3_800_000,
         "apy": 68.2, "base": 45.1, "reward": 23.1, "exposure": "multi"},
        # Lending
        {"project": "marginfi", "symbol": "USDC", "tvl": 120_000_000,
         "apy": 8.5, "base": 5.2, "reward": 3.3, "exposure": "single"},
        {"project": "marginfi", "symbol": "SOL", "tvl": 85_000_000,
         "apy": 6.1, "base": 3.8, "reward": 2.3, "exposure": "single"},
        {"project": "kamino", "symbol": "USDC", "tvl": 95_000_000,
         "apy": 9.2, "base": 6.1, "reward": 3.1, "exposure": "single"},
        {"project": "kamino", "symbol": "SOL", "tvl": 60_000_000,
         "apy": 5.8, "base": 3.5, "reward": 2.3, "exposure": "single"},
        {"project": "solend", "symbol": "USDC", "tvl": 45_000_000,
         "apy": 6.8, "base": 5.5, "reward": 1.3, "exposure": "single"},
        # Staking / LST
        {"project": "marinade", "symbol": "mSOL", "tvl": 800_000_000,
         "apy": 7.2, "base": 7.2, "reward": 0.0, "exposure": "single"},
        {"project": "jito", "symbol": "jitoSOL", "tvl": 600_000_000,
         "apy": 7.5, "base": 7.5, "reward": 0.0, "exposure": "single"},
        {"project": "blazestake", "symbol": "bSOL", "tvl": 150_000_000,
         "apy": 7.0, "base": 7.0, "reward": 0.0, "exposure": "single"},
    ]

    results = []
    for p in pools:
        risk_tier, risk_score = classify_risk(
            p["apy"], p["base"], p["reward"], p["tvl"], p["exposure"]
        )
        real_pct = compute_real_yield_pct(p["base"], p["apy"])
        risk_adj = p["apy"] / risk_score if risk_score > 0 else 0

        results.append(YieldOpportunity(
            pool_id=f"demo-{p['project']}-{p['symbol']}",
            project=p["project"],
            symbol=p["symbol"],
            chain="Solana",
            tvl_usd=p["tvl"],
            apy_total=p["apy"],
            apy_base=p["base"],
            apy_reward=p["reward"],
            il_7d=None,
            exposure=p["exposure"],
            risk_tier=risk_tier,
            real_yield_pct=real_pct,
            risk_adjusted_yield=risk_adj,
        ))

    return results


# ── Display ─────────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format USD value with K/M/B suffixes."""
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:.0f}"


def print_yield_table(
    opportunities: list[YieldOpportunity],
    title: str,
    sort_by: str = "risk_adjusted",
    limit: int = 20,
) -> None:
    """Print a formatted yield comparison table.

    Args:
        opportunities: List of yield opportunities.
        title: Table title.
        sort_by: Sort key — "risk_adjusted", "apy", "real_yield", "tvl".
        limit: Maximum rows to display.
    """
    sort_keys = {
        "risk_adjusted": lambda x: x.risk_adjusted_yield,
        "apy": lambda x: x.apy_total,
        "real_yield": lambda x: x.real_yield_pct,
        "tvl": lambda x: x.tvl_usd,
    }
    key_fn = sort_keys.get(sort_by, sort_keys["risk_adjusted"])
    sorted_opps = sorted(opportunities, key=key_fn, reverse=True)[:limit]

    print(f"\n{'═' * 100}")
    print(f"  {title}")
    print(f"  Sorted by: {sort_by} | SOL staking baseline: {SOL_STAKING_APR:.1f}% APR")
    print(f"{'═' * 100}")

    header = (
        f"  {'Protocol':<12} {'Pool':<16} {'TVL':>9} "
        f"{'APY':>7} {'Fee':>7} {'Reward':>7} "
        f"{'Real%':>6} {'Risk':>6} {'Adj.':>7}"
    )
    print(header)
    print(f"  {'─' * 12} {'─' * 16} {'─' * 9} {'─' * 7} {'─' * 7} {'─' * 7} {'─' * 6} {'─' * 6} {'─' * 7}")

    for opp in sorted_opps:
        risk_marker = {"low": " ", "medium": "*", "high": "!"}
        marker = risk_marker.get(opp.risk_tier, "?")

        print(
            f"  {opp.project:<12} {opp.symbol:<16} {format_usd(opp.tvl_usd):>9} "
            f"{opp.apy_total:>6.1f}% {opp.apy_base:>6.1f}% {opp.apy_reward:>6.1f}% "
            f"{opp.real_yield_pct:>5.0f}% {opp.risk_tier:>5}{marker} "
            f"{opp.risk_adjusted_yield:>6.1f}"
        )

    print(f"{'═' * 100}")
    print(f"  Risk: * = medium, ! = high | Adj. = APY / risk_score (higher is better)")
    print()


def print_category_summary(opportunities: list[YieldOpportunity]) -> None:
    """Print yield summary grouped by category.

    Args:
        opportunities: List of yield opportunities.
    """
    # Group by type
    lp_pools = [o for o in opportunities if o.exposure == "multi"]
    lending = [o for o in opportunities if o.exposure == "single" and o.apy_reward > 0]
    staking = [o for o in opportunities if o.exposure == "single" and o.apy_reward == 0]

    print(f"\n{'─' * 60}")
    print(f"  CATEGORY SUMMARY")
    print(f"{'─' * 60}")

    categories = [
        ("LP Pools", lp_pools),
        ("Lending", lending),
        ("Staking / LST", staking),
    ]

    for name, group in categories:
        if not group:
            continue
        avg_apy = sum(o.apy_total for o in group) / len(group)
        avg_real = sum(o.real_yield_pct for o in group) / len(group)
        total_tvl = sum(o.tvl_usd for o in group)
        best = max(group, key=lambda x: x.risk_adjusted_yield)

        print(f"\n  {name} ({len(group)} opportunities)")
        print(f"    Average APY:          {avg_apy:.1f}%")
        print(f"    Average real yield:   {avg_real:.0f}% of total")
        print(f"    Total TVL:            {format_usd(total_tvl)}")
        print(f"    Best risk-adjusted:   {best.symbol} on {best.project} ({best.apy_total:.1f}% APY)")

    print(f"\n{'─' * 60}")

    # Comparison to SOL staking
    above_staking = [o for o in opportunities if o.apy_base > SOL_STAKING_APR]
    print(f"\n  {len(above_staking)} of {len(opportunities)} opportunities have")
    print(f"  fee-based yield above SOL staking ({SOL_STAKING_APR:.1f}% APR).")
    print()


def print_top_picks(opportunities: list[YieldOpportunity], count: int = 5) -> None:
    """Print top risk-adjusted yield picks with rationale.

    Args:
        opportunities: All yield opportunities.
        count: Number of top picks to display.
    """
    # Filter to medium or low risk only
    viable = [o for o in opportunities if o.risk_tier in ("low", "medium")]
    top = sorted(viable, key=lambda x: x.risk_adjusted_yield, reverse=True)[:count]

    print(f"\n{'═' * 60}")
    print(f"  TOP {count} RISK-ADJUSTED OPPORTUNITIES")
    print(f"  (filtered to low/medium risk only)")
    print(f"{'═' * 60}")

    for i, opp in enumerate(top, 1):
        real_label = "real yield" if opp.real_yield_pct > 50 else "emission-heavy"
        print(f"\n  {i}. {opp.symbol} on {opp.project}")
        print(f"     APY: {opp.apy_total:.1f}% ({opp.apy_base:.1f}% fees + {opp.apy_reward:.1f}% rewards)")
        print(f"     TVL: {format_usd(opp.tvl_usd)} | Risk: {opp.risk_tier} | Type: {real_label}")
        print(f"     Risk-adjusted score: {opp.risk_adjusted_yield:.1f}")

    print(f"\n{'═' * 60}")
    print(f"  Note: This is analysis output, not financial advice.")
    print(f"  Always verify data on-chain before making decisions.")
    print()


# ── CLI ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Compare Solana DeFi yield opportunities using DeFiLlama data"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use representative demo data instead of live API",
    )
    parser.add_argument(
        "--min-tvl",
        type=float,
        default=1_000_000,
        help="Minimum TVL filter in USD (default: 1000000)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of results to display (default: 20)",
    )
    parser.add_argument(
        "--sort",
        choices=["risk_adjusted", "apy", "real_yield", "tvl"],
        default="risk_adjusted",
        help="Sort order (default: risk_adjusted)",
    )
    return parser


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for yield comparison tool."""
    parser = build_parser()
    args = parser.parse_args()

    if args.demo:
        print("\n  Solana Yield Comparison — Demo Mode")
        print("  Using representative data (not live)\n")
        opportunities = demo_data()
    else:
        print("\n  Solana Yield Comparison — Live Data")
        print(f"  Fetching from DeFiLlama (min TVL: {format_usd(args.min_tvl)})...\n")
        raw_pools = fetch_solana_yields(min_tvl=args.min_tvl)
        if not raw_pools:
            print("  No Solana pools found matching criteria.")
            print("  Try lowering --min-tvl or use --demo mode.")
            sys.exit(0)
        opportunities = [parse_pool(p) for p in raw_pools]
        print(f"  Found {len(opportunities)} Solana yield opportunities.\n")

    # Display results
    print_yield_table(opportunities, "SOLANA YIELD OPPORTUNITIES", sort_by=args.sort, limit=args.top)
    print_category_summary(opportunities)
    print_top_picks(opportunities)


if __name__ == "__main__":
    main()
