#!/usr/bin/env python3
"""Estimate MEV risk for a planned Solana DEX trade.

Analyzes token liquidity, trade size, and slippage settings to estimate
the probability and cost of sandwich attacks. Provides actionable
protection recommendations.

Usage:
    python scripts/mev_risk_estimator.py                     # demo mode
    python scripts/mev_risk_estimator.py --demo              # explicit demo
    python scripts/mev_risk_estimator.py --mint <TOKEN_MINT> --size 10 --slippage 100

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Token mint address (alternative to --mint flag)
    TRADE_SIZE_SOL: Trade size in SOL (default: 1.0)
    SLIPPAGE_BPS: Slippage tolerance in basis points (default: 100)
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────
TOKEN_MINT = os.getenv("TOKEN_MINT", "")
TRADE_SIZE_SOL = float(os.getenv("TRADE_SIZE_SOL", "1.0"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "100"))

DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT = 15.0

# SOL mint for reference
SOL_MINT = "So11111111111111111111111111111111111111112"


# ── Data Classes ────────────────────────────────────────────────────
@dataclass
class TokenPoolData:
    """Liquidity and volume data for a token's best pool."""

    pair_address: str
    dex_name: str
    base_token_symbol: str
    quote_token_symbol: str
    liquidity_usd: float
    volume_24h_usd: float
    price_usd: float
    price_change_24h_pct: float
    fdv: float
    pool_created_at: Optional[str]


@dataclass
class MevRiskAssessment:
    """Complete MEV risk assessment for a planned trade."""

    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    trade_size_sol: float
    trade_size_usd: float
    slippage_bps: int
    pool_liquidity_usd: float
    volume_24h_usd: float
    trade_pct_of_pool: float
    estimated_price_impact_bps: float
    slippage_headroom_bps: float
    estimated_sandwich_cost_usd: float
    is_profitable_to_sandwich: bool
    recommended_slippage_bps: int
    recommendations: list[str] = field(default_factory=list)
    protection_plan: list[str] = field(default_factory=list)


# ── Data Fetching ───────────────────────────────────────────────────
def fetch_sol_price(client: httpx.Client) -> float:
    """Fetch current SOL price in USD from CoinGecko.

    Args:
        client: httpx Client instance.

    Returns:
        SOL price in USD. Falls back to 150.0 on error.
    """
    try:
        resp = client.get(
            f"{COINGECKO_BASE}/simple/price",
            params={"ids": "solana", "vs_currencies": "usd"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("solana", {}).get("usd", 150.0))
    except (httpx.HTTPError, KeyError, ValueError):
        return 150.0


def fetch_token_pool_data(
    mint: str, client: httpx.Client
) -> Optional[TokenPoolData]:
    """Fetch pool data for a token from DexScreener.

    Finds the most liquid Solana pool for the given token mint.

    Args:
        mint: Token mint address.
        client: httpx Client instance.

    Returns:
        TokenPoolData for the most liquid pool, or None.
    """
    try:
        resp = client.get(
            f"{DEXSCREENER_BASE}/tokens/{mint}",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        print(f"  Warning: DexScreener API error: {e}")
        return None

    pairs = data.get("pairs", [])
    if not pairs:
        return None

    # Filter to Solana pairs and sort by liquidity
    solana_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not solana_pairs:
        solana_pairs = pairs  # Fall back to all chains

    solana_pairs.sort(
        key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
        reverse=True,
    )

    best = solana_pairs[0]
    liquidity = best.get("liquidity", {})
    volume = best.get("volume", {})
    price_change = best.get("priceChange", {})

    return TokenPoolData(
        pair_address=best.get("pairAddress", ""),
        dex_name=best.get("dexId", "unknown"),
        base_token_symbol=best.get("baseToken", {}).get("symbol", "???"),
        quote_token_symbol=best.get("quoteToken", {}).get("symbol", "???"),
        liquidity_usd=float(liquidity.get("usd", 0) or 0),
        volume_24h_usd=float(volume.get("h24", 0) or 0),
        price_usd=float(best.get("priceUsd", 0) or 0),
        price_change_24h_pct=float(price_change.get("h24", 0) or 0),
        fdv=float(best.get("fdv", 0) or 0),
        pool_created_at=best.get("pairCreatedAt"),
    )


# ── Risk Estimation ────────────────────────────────────────────────
def estimate_mev_risk(
    trade_size_sol: float,
    slippage_bps: int,
    pool: TokenPoolData,
    sol_price: float,
) -> MevRiskAssessment:
    """Estimate MEV risk for a planned trade.

    Uses a simplified constant-product AMM model to estimate price impact
    and sandwich attack profitability.

    Args:
        trade_size_sol: Trade size in SOL.
        slippage_bps: Slippage tolerance in basis points.
        pool: Pool liquidity and volume data.
        sol_price: Current SOL price in USD.

    Returns:
        Complete MevRiskAssessment.
    """
    trade_usd = trade_size_sol * sol_price
    pool_liq = max(pool.liquidity_usd, 1.0)  # Avoid division by zero

    # Trade as percentage of pool
    trade_pct = (trade_usd / pool_liq) * 100

    # Estimated price impact (constant-product model: impact ~ trade/liquidity)
    # For a CPMM pool, price impact ≈ trade_size / (pool_size / 2)
    # Since liquidity_usd represents total pool, one side is ~half
    price_impact_bps = (trade_usd / (pool_liq / 2)) * 10000

    # Slippage headroom: how much room the attacker has to work with
    slippage_headroom = max(0, slippage_bps - price_impact_bps)

    # Sandwich profitability model:
    # The attacker front-runs, pushing price up, then your swap executes
    # at the worse price. Attacker profit ≈ capture_rate * headroom * trade_size.
    # capture_rate depends on pool depth and attacker capital (typically 0.3-0.6)
    capture_rate = 0.4
    sandwich_gross_usd = (slippage_headroom / 10000) * trade_usd * capture_rate

    # Attacker costs
    jito_tip_sol = _estimate_jito_tip(sandwich_gross_usd, sol_price)
    jito_tip_usd = jito_tip_sol * sol_price
    tx_fees_usd = 0.000015 * sol_price * 2  # Two transactions
    attacker_cost = jito_tip_usd + tx_fees_usd

    net_sandwich_profit = sandwich_gross_usd - attacker_cost
    is_profitable = net_sandwich_profit > 0.05  # $0.05 minimum threshold

    # Determine risk level
    risk_level = _classify_risk(
        is_profitable, trade_pct, slippage_headroom, pool.volume_24h_usd
    )

    # Recommended slippage
    recommended_slippage = _recommend_slippage(
        price_impact_bps, pool_liq, pool.volume_24h_usd
    )

    # Build recommendations
    recommendations = _build_recommendations(
        risk_level,
        trade_size_sol,
        slippage_bps,
        recommended_slippage,
        trade_pct,
        is_profitable,
        net_sandwich_profit,
    )

    # Build protection plan
    protection_plan = _build_protection_plan(
        risk_level, trade_size_sol, trade_pct, pool_liq
    )

    return MevRiskAssessment(
        risk_level=risk_level,
        trade_size_sol=trade_size_sol,
        trade_size_usd=round(trade_usd, 2),
        slippage_bps=slippage_bps,
        pool_liquidity_usd=round(pool_liq, 2),
        volume_24h_usd=round(pool.volume_24h_usd, 2),
        trade_pct_of_pool=round(trade_pct, 4),
        estimated_price_impact_bps=round(price_impact_bps, 1),
        slippage_headroom_bps=round(slippage_headroom, 1),
        estimated_sandwich_cost_usd=round(max(net_sandwich_profit, 0), 2),
        is_profitable_to_sandwich=is_profitable,
        recommended_slippage_bps=recommended_slippage,
        recommendations=recommendations,
        protection_plan=protection_plan,
    )


def _estimate_jito_tip(
    sandwich_profit_usd: float, sol_price: float
) -> float:
    """Estimate the Jito tip an attacker would pay.

    Searchers typically tip 30-60% of expected profit. Minimum viable
    tip is ~0.0001 SOL.

    Args:
        sandwich_profit_usd: Gross sandwich profit in USD.
        sol_price: Current SOL price.

    Returns:
        Estimated tip in SOL.
    """
    if sandwich_profit_usd <= 0:
        return 0.0001
    tip_usd = sandwich_profit_usd * 0.5  # 50% of profit to tip
    tip_sol = tip_usd / sol_price
    return max(0.0001, tip_sol)


def _classify_risk(
    is_profitable: bool,
    trade_pct: float,
    headroom_bps: float,
    volume_24h: float,
) -> str:
    """Classify overall MEV risk level.

    Args:
        is_profitable: Whether sandwiching is estimated profitable.
        trade_pct: Trade as percentage of pool liquidity.
        headroom_bps: Slippage headroom in basis points.
        volume_24h: 24h trading volume in USD.

    Returns:
        Risk level string.
    """
    score = 0

    if is_profitable:
        score += 2
    if trade_pct > 5.0:
        score += 3
    elif trade_pct > 1.0:
        score += 2
    elif trade_pct > 0.5:
        score += 1
    if headroom_bps > 200:
        score += 2
    elif headroom_bps > 100:
        score += 1
    # High-volume tokens attract more MEV bots
    if volume_24h > 1_000_000:
        score += 1
    elif volume_24h > 100_000:
        score += 0  # Moderate volume, moderate attention

    if score >= 6:
        return "CRITICAL"
    elif score >= 4:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    return "LOW"


def _recommend_slippage(
    price_impact_bps: float,
    pool_liquidity: float,
    volume_24h: float,
) -> int:
    """Recommend slippage setting based on pool characteristics.

    Args:
        price_impact_bps: Estimated price impact.
        pool_liquidity: Pool liquidity in USD.
        volume_24h: 24h volume in USD.

    Returns:
        Recommended slippage in basis points.
    """
    # Base: 1.5x expected price impact, minimum 30bps
    base = max(30, int(price_impact_bps * 1.5))

    # Adjust for pool characteristics
    if pool_liquidity < 100_000:
        base = max(base, 200)  # Very thin pool needs buffer
    elif pool_liquidity < 500_000:
        base = max(base, 100)

    # Cap at reasonable maximum
    return min(base, 500)


def _build_recommendations(
    risk_level: str,
    trade_size_sol: float,
    current_slippage: int,
    recommended_slippage: int,
    trade_pct: float,
    is_profitable: bool,
    estimated_cost: float,
) -> list[str]:
    """Build list of actionable recommendations.

    Args:
        risk_level: Assessed risk level.
        trade_size_sol: Trade size in SOL.
        current_slippage: Current slippage setting in bps.
        recommended_slippage: Recommended slippage in bps.
        trade_pct: Trade as percentage of pool.
        is_profitable: Whether sandwich is profitable.
        estimated_cost: Estimated sandwich cost in USD.

    Returns:
        List of recommendation strings.
    """
    recs = []

    if current_slippage > recommended_slippage:
        recs.append(
            f"Reduce slippage from {current_slippage}bps to "
            f"{recommended_slippage}bps"
        )

    if risk_level in ("HIGH", "CRITICAL"):
        recs.append("Use Jito bundle submission for MEV protection")
        recs.append("Use a private/staked RPC endpoint (Helius, Triton)")

    if trade_pct > 2.0:
        n_splits = max(2, int(trade_pct / 0.5))
        recs.append(
            f"Split trade into {n_splits} pieces "
            f"({trade_size_sol / n_splits:.2f} SOL each)"
        )

    if is_profitable and estimated_cost > 1.0:
        recs.append(
            f"Estimated sandwich cost: ${estimated_cost:.2f} — "
            f"protection is strongly recommended"
        )

    if risk_level == "CRITICAL":
        recs.append(
            "Consider whether this trade size is appropriate "
            "for the available liquidity"
        )

    if risk_level == "LOW" and not is_profitable:
        recs.append(
            "Standard execution is likely safe. "
            "MEV risk is minimal for this trade."
        )

    recs.append("Enable Jupiter dynamic slippage for auto-adjustment")

    return recs


def _build_protection_plan(
    risk_level: str,
    trade_size_sol: float,
    trade_pct: float,
    pool_liquidity: float,
) -> list[str]:
    """Build step-by-step protection plan.

    Args:
        risk_level: Assessed risk level.
        trade_size_sol: Trade size in SOL.
        trade_pct: Trade as percentage of pool.
        pool_liquidity: Pool liquidity in USD.

    Returns:
        Ordered list of protection steps.
    """
    if risk_level == "LOW":
        return [
            "1. Execute normally with tight slippage",
            "2. Verify execution price matches quote",
        ]

    if risk_level == "MEDIUM":
        return [
            "1. Set slippage to 50-100bps",
            "2. Enable Jupiter dynamic slippage",
            "3. Submit via private RPC if available",
            "4. Verify execution price post-trade",
        ]

    if risk_level == "HIGH":
        steps = [
            "1. Set slippage to minimum viable (30-50bps for liquid tokens)",
            "2. Submit transaction as Jito bundle with 0.001 SOL tip",
            "3. Use private/staked RPC endpoint",
        ]
        if trade_pct > 2.0:
            n = max(2, int(trade_pct))
            steps.append(
                f"4. Split into {n} trades, 30s apart"
            )
            steps.append("5. Monitor each execution for sandwich indicators")
        else:
            steps.append("4. Monitor execution for sandwich indicators")
        return steps

    # CRITICAL
    n = max(3, int(trade_pct))
    return [
        f"1. Split trade into {n}+ pieces",
        "2. Use Jito bundle for each piece (0.001-0.005 SOL tip)",
        "3. Use private/staked RPC endpoint",
        "4. Set 30-60 second delay between trades",
        "5. Monitor pool liquidity between trades for manipulation",
        "6. Consider OTC or limit order alternatives",
        "7. Verify each execution against expected price",
    ]


# ── Output ──────────────────────────────────────────────────────────
def print_assessment(
    assessment: MevRiskAssessment,
    pool: Optional[TokenPoolData] = None,
) -> None:
    """Print formatted MEV risk assessment.

    Args:
        assessment: The risk assessment to display.
        pool: Optional pool data for additional context.
    """
    risk_markers = {
        "LOW": "[OK]",
        "MEDIUM": "[!!]",
        "HIGH": "[!!!]",
        "CRITICAL": "[XXXX]",
    }
    marker = risk_markers.get(assessment.risk_level, "[??]")

    print("=" * 70)
    print(f"MEV RISK ASSESSMENT  {marker} {assessment.risk_level}")
    print("=" * 70)
    print()

    # Trade details
    print("TRADE DETAILS")
    print(f"  Size:              {assessment.trade_size_sol} SOL "
          f"(${assessment.trade_size_usd:.2f})")
    print(f"  Slippage setting:  {assessment.slippage_bps} bps "
          f"({assessment.slippage_bps / 100:.1f}%)")
    print()

    # Pool details
    if pool:
        print("POOL DATA")
        print(f"  DEX:               {pool.dex_name}")
        print(f"  Pair:              {pool.base_token_symbol}/"
              f"{pool.quote_token_symbol}")
        print(f"  Liquidity:         ${pool.liquidity_usd:,.0f}")
        print(f"  24h Volume:        ${pool.volume_24h_usd:,.0f}")
        print(f"  Token Price:       ${pool.price_usd:.6f}")
        print(f"  24h Change:        {pool.price_change_24h_pct:+.1f}%")
        print()

    # Risk metrics
    print("RISK METRICS")
    print(f"  Trade % of pool:   {assessment.trade_pct_of_pool:.4f}%")
    print(f"  Est. price impact: {assessment.estimated_price_impact_bps:.1f} bps")
    print(f"  Slippage headroom: {assessment.slippage_headroom_bps:.1f} bps")
    print(f"  Sandwich viable:   "
          f"{'Yes' if assessment.is_profitable_to_sandwich else 'No'}")
    if assessment.is_profitable_to_sandwich:
        print(f"  Est. sandwich cost: ${assessment.estimated_sandwich_cost_usd:.2f}")
    print(f"  Recommended slip:  {assessment.recommended_slippage_bps} bps")
    print()

    # Recommendations
    print("RECOMMENDATIONS")
    for rec in assessment.recommendations:
        print(f"  - {rec}")
    print()

    # Protection plan
    print("PROTECTION PLAN")
    for step in assessment.protection_plan:
        print(f"  {step}")
    print()
    print("=" * 70)
    print("NOTE: Estimates use simplified AMM models. Actual MEV risk depends")
    print("on real-time searcher activity, pool type (CPMM vs CLMM), and")
    print("current network conditions. This is informational analysis only.")
    print("=" * 70)


# ── Demo Mode ───────────────────────────────────────────────────────
def run_demo() -> None:
    """Run demonstration with synthetic data showing different risk levels."""
    print("=" * 70)
    print("MEV RISK ESTIMATOR — DEMO MODE")
    print("=" * 70)
    print()
    print("Demonstrating risk estimation across different scenarios...")
    print()

    sol_price = 150.0

    scenarios = [
        {
            "name": "Small trade, liquid token",
            "trade_sol": 1.0,
            "slippage": 100,
            "pool": TokenPoolData(
                pair_address="DemoPool1",
                dex_name="raydium",
                base_token_symbol="BONK",
                quote_token_symbol="SOL",
                liquidity_usd=5_000_000,
                volume_24h_usd=10_000_000,
                price_usd=0.00002,
                price_change_24h_pct=5.2,
                fdv=1_200_000_000,
                pool_created_at=None,
            ),
        },
        {
            "name": "Medium trade, moderate liquidity",
            "trade_sol": 10.0,
            "slippage": 200,
            "pool": TokenPoolData(
                pair_address="DemoPool2",
                dex_name="orca",
                base_token_symbol="MEME",
                quote_token_symbol="SOL",
                liquidity_usd=500_000,
                volume_24h_usd=1_000_000,
                price_usd=0.005,
                price_change_24h_pct=-12.3,
                fdv=50_000_000,
                pool_created_at=None,
            ),
        },
        {
            "name": "Large trade, low liquidity (HIGH RISK)",
            "trade_sol": 50.0,
            "slippage": 300,
            "pool": TokenPoolData(
                pair_address="DemoPool3",
                dex_name="raydium",
                base_token_symbol="NEWCOIN",
                quote_token_symbol="SOL",
                liquidity_usd=80_000,
                volume_24h_usd=200_000,
                price_usd=0.0001,
                price_change_24h_pct=45.0,
                fdv=5_000_000,
                pool_created_at=None,
            ),
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 70}")
        print(f"SCENARIO: {scenario['name']}")
        print(f"{'─' * 70}")

        assessment = estimate_mev_risk(
            trade_size_sol=scenario["trade_sol"],
            slippage_bps=scenario["slippage"],
            pool=scenario["pool"],
            sol_price=sol_price,
        )
        print_assessment(assessment, scenario["pool"])
        print()

    print()
    print("Use --mint <TOKEN_MINT> --size <SOL> --slippage <BPS>")
    print("to analyze a real token with live market data.")


# ── Live Analysis ───────────────────────────────────────────────────
def analyze_token(
    mint: str, trade_size_sol: float, slippage_bps: int
) -> None:
    """Analyze MEV risk for a real token using live market data.

    Args:
        mint: Token mint address.
        trade_size_sol: Planned trade size in SOL.
        slippage_bps: Planned slippage setting in basis points.
    """
    print(f"Analyzing MEV risk for token: {mint[:20]}...")
    print(f"Trade size: {trade_size_sol} SOL | Slippage: {slippage_bps} bps")
    print()

    with httpx.Client() as client:
        # Fetch SOL price
        print("Fetching SOL price...")
        sol_price = fetch_sol_price(client)
        print(f"SOL price: ${sol_price:.2f}")

        # Fetch pool data
        print("Fetching pool data from DexScreener...")
        pool = fetch_token_pool_data(mint, client)

        if not pool:
            print()
            print("ERROR: No pool data found for this token.")
            print("The token may not be listed on any Solana DEX,")
            print("or the mint address may be incorrect.")
            sys.exit(1)

        if pool.liquidity_usd <= 0:
            print()
            print("WARNING: Pool has zero reported liquidity.")
            print("MEV risk cannot be accurately assessed.")
            print("Exercise extreme caution with this token.")
            return

        print(f"Found pool: {pool.base_token_symbol}/{pool.quote_token_symbol} "
              f"on {pool.dex_name}")
        print(f"Liquidity: ${pool.liquidity_usd:,.0f}")
        print()

        # Run assessment
        assessment = estimate_mev_risk(
            trade_size_sol=trade_size_sol,
            slippage_bps=slippage_bps,
            pool=pool,
            sol_price=sol_price,
        )

        print_assessment(assessment, pool)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point for MEV risk estimator."""
    parser = argparse.ArgumentParser(
        description="Estimate MEV risk for a planned Solana DEX trade"
    )
    parser.add_argument(
        "--mint",
        type=str,
        default="",
        help="Token mint address to analyze",
    )
    parser.add_argument(
        "--size",
        type=float,
        default=0,
        help="Trade size in SOL",
    )
    parser.add_argument(
        "--slippage",
        type=int,
        default=0,
        help="Slippage tolerance in basis points",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic demo data",
    )
    args = parser.parse_args()

    mint = args.mint or TOKEN_MINT
    trade_size = args.size if args.size > 0 else TRADE_SIZE_SOL
    slippage = args.slippage if args.slippage > 0 else SLIPPAGE_BPS

    if args.demo or not mint:
        run_demo()
    else:
        analyze_token(mint, trade_size, slippage)


if __name__ == "__main__":
    main()
