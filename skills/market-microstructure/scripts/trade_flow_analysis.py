#!/usr/bin/env python3
"""Trade flow analysis for Solana tokens.

Fetches recent trades for a token, classifies them by size and direction,
computes buy/sell pressure metrics, and generates a composite momentum score.

Usage:
    python scripts/trade_flow_analysis.py                    # demo mode
    python scripts/trade_flow_analysis.py --demo             # explicit demo
    TOKEN_MINT=EPjF... BIRDEYE_API_KEY=xxx python scripts/trade_flow_analysis.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Solana token mint address to analyze
    BIRDEYE_API_KEY: Birdeye API key (optional — falls back to demo data)
"""

import json
import math
import os
import random
import statistics
import sys
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("Install httpx: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────
TOKEN_MINT = os.getenv("TOKEN_MINT", "")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
DEMO_MODE = "--demo" in sys.argv or (not TOKEN_MINT and not BIRDEYE_API_KEY)

SOL_PRICE_USD = 150.0  # Approximate SOL price for demo bucketing

# Trade size buckets in SOL
SIZE_BUCKETS = {
    "micro": (0, 0.1),
    "small": (0.1, 1.0),
    "medium": (1.0, 10.0),
    "large": (10.0, 50.0),
    "whale": (50.0, 200.0),
    "mega": (200.0, float("inf")),
}


# ── Data Fetching ──────────────────────────────────────────────────

def fetch_trades_birdeye(
    token_mint: str, api_key: str, limit: int = 200
) -> list[dict]:
    """Fetch recent trades from Birdeye API.

    Args:
        token_mint: Token mint address.
        api_key: Birdeye API key.
        limit: Maximum trades to fetch.

    Returns:
        List of normalized trade dicts with keys:
        side, volume_usd, volume_sol, timestamp, wallet, tx_hash.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    url = "https://public-api.birdeye.so/defi/txs/token"
    headers = {"X-API-KEY": api_key, "accept": "application/json"}
    params = {"address": token_mint, "limit": min(limit, 50), "tx_type": "swap"}

    trades: list[dict] = []
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("data", {}).get("items", []):
            sol_amount = item.get("volumeUsd", 0) / SOL_PRICE_USD
            trades.append({
                "side": item.get("side", "unknown"),
                "volume_usd": item.get("volumeUsd", 0),
                "volume_sol": sol_amount,
                "timestamp": item.get("blockUnixTime", 0),
                "wallet": item.get("owner", "unknown"),
                "tx_hash": item.get("txHash", ""),
            })

    return trades


def fetch_trades_dexscreener(token_mint: str) -> list[dict]:
    """Fetch pair data from DexScreener as volume summary fallback.

    DexScreener does not provide individual trade data, but pair-level
    volume stats can be used for aggregate analysis.

    Args:
        token_mint: Token mint address.

    Returns:
        List with a single summary pseudo-trade, or empty list.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return []
            pair = pairs[0]
            volume_24h = pair.get("volume", {}).get("h24", 0)
            buys = pair.get("txns", {}).get("h24", {}).get("buys", 0)
            sells = pair.get("txns", {}).get("h24", {}).get("sells", 0)
            print(f"  DexScreener 24h volume: ${volume_24h:,.0f}")
            print(f"  DexScreener 24h buys: {buys}, sells: {sells}")
            return []  # No individual trades available
    except Exception as e:
        print(f"  DexScreener fallback failed: {e}")
        return []


def generate_demo_trades(count: int = 500) -> list[dict]:
    """Generate synthetic trade data for demonstration.

    Creates realistic trade data with patterns:
    - Mix of buy/sell with slight buy bias
    - Log-normal trade size distribution
    - Some whale trades
    - Some repeat wallets (simulating active traders)
    - Timestamps over the last 24 hours

    Args:
        count: Number of synthetic trades to generate.

    Returns:
        List of normalized trade dicts.
    """
    now = int(time.time())
    wallets = [f"wallet_{i:04d}" for i in range(80)]  # 80 unique wallets
    active_wallets = wallets[:15]  # 15 are very active

    trades: list[dict] = []
    for i in range(count):
        # Time: spread over last 24 hours with some clustering
        hours_ago = random.expovariate(0.15)  # cluster toward recent
        hours_ago = min(hours_ago, 24.0)
        ts = now - int(hours_ago * 3600)

        # Side: 55% buys (slight accumulation bias)
        side = "buy" if random.random() < 0.55 else "sell"

        # Size: log-normal distribution (most small, few large)
        sol_amount = random.lognormvariate(mu=0.5, sigma=1.5)
        sol_amount = max(0.01, min(sol_amount, 500.0))

        # Wallet: active wallets trade more
        if random.random() < 0.4:
            wallet = random.choice(active_wallets)
        else:
            wallet = random.choice(wallets)

        trades.append({
            "side": side,
            "volume_usd": sol_amount * SOL_PRICE_USD,
            "volume_sol": sol_amount,
            "timestamp": ts,
            "wallet": wallet,
            "tx_hash": f"demo_tx_{i:06d}",
        })

    # Add some wash-like trades (same wallet buy+sell similar size)
    for _ in range(20):
        wash_wallet = f"wash_{random.randint(0, 4):02d}"
        wash_size = random.uniform(1.0, 5.0)
        wash_time = now - random.randint(0, 86400)
        trades.append({
            "side": "buy",
            "volume_usd": wash_size * SOL_PRICE_USD,
            "volume_sol": wash_size,
            "timestamp": wash_time,
            "wallet": wash_wallet,
            "tx_hash": f"wash_buy_{_:04d}",
        })
        trades.append({
            "side": "sell",
            "volume_usd": wash_size * SOL_PRICE_USD * random.uniform(0.98, 1.02),
            "volume_sol": wash_size * random.uniform(0.98, 1.02),
            "timestamp": wash_time + random.randint(10, 120),
            "wallet": wash_wallet,
            "tx_hash": f"wash_sell_{_:04d}",
        })

    trades.sort(key=lambda t: t["timestamp"])
    return trades


# ── Analysis Functions ─────────────────────────────────────────────

def classify_trade_size(sol_amount: float) -> str:
    """Classify trade into size bucket.

    Args:
        sol_amount: Trade size in SOL.

    Returns:
        Bucket name: micro, small, medium, large, whale, or mega.
    """
    for bucket, (lo, hi) in SIZE_BUCKETS.items():
        if lo <= sol_amount < hi:
            return bucket
    return "mega"


def compute_pressure_metrics(trades: list[dict]) -> dict:
    """Compute buy/sell pressure metrics from trade list.

    Args:
        trades: List of trade dicts with 'side' and 'volume_usd'.

    Returns:
        Dict with buy_ratio, net_flow, trade_count_ratio, etc.
    """
    buy_vol = sum(t["volume_usd"] for t in trades if t["side"] == "buy")
    sell_vol = sum(t["volume_usd"] for t in trades if t["side"] == "sell")
    total_vol = buy_vol + sell_vol

    buy_count = sum(1 for t in trades if t["side"] == "buy")
    sell_count = sum(1 for t in trades if t["side"] == "sell")
    total_count = buy_count + sell_count

    return {
        "buy_volume_usd": buy_vol,
        "sell_volume_usd": sell_vol,
        "total_volume_usd": total_vol,
        "buy_ratio": buy_vol / total_vol if total_vol > 0 else 0.5,
        "net_flow_usd": buy_vol - sell_vol,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "trade_count_ratio": buy_count / total_count if total_count > 0 else 0.5,
    }


def compute_size_distribution(trades: list[dict]) -> dict[str, dict]:
    """Compute volume and count by trade size bucket.

    Args:
        trades: List of trade dicts.

    Returns:
        Dict mapping bucket name to {count, volume_usd, buy_count, sell_count}.
    """
    dist: dict[str, dict] = {}
    for bucket in SIZE_BUCKETS:
        dist[bucket] = {"count": 0, "volume_usd": 0, "buy_count": 0, "sell_count": 0}

    for t in trades:
        bucket = classify_trade_size(t["volume_sol"])
        dist[bucket]["count"] += 1
        dist[bucket]["volume_usd"] += t["volume_usd"]
        if t["side"] == "buy":
            dist[bucket]["buy_count"] += 1
        else:
            dist[bucket]["sell_count"] += 1

    return dist


def compute_unique_traders(trades: list[dict]) -> dict:
    """Compute unique trader metrics.

    Args:
        trades: List of trade dicts with 'wallet' field.

    Returns:
        Dict with unique_count, total_trades, ratio, top_traders.
    """
    from collections import Counter

    wallet_counts = Counter(t["wallet"] for t in trades)
    unique = len(wallet_counts)
    total = len(trades)

    top_5 = wallet_counts.most_common(5)
    top_volume: dict[str, float] = {}
    for wallet, _ in top_5:
        vol = sum(t["volume_usd"] for t in trades if t["wallet"] == wallet)
        top_volume[wallet] = vol

    return {
        "unique_count": unique,
        "total_trades": total,
        "unique_ratio": unique / total if total > 0 else 0,
        "top_traders": [
            {"wallet": w, "trades": c, "volume_usd": top_volume.get(w, 0)}
            for w, c in top_5
        ],
    }


def detect_self_trades(
    trades: list[dict], window_seconds: int = 300
) -> dict:
    """Detect wallets that buy and sell within a short window.

    Args:
        trades: List of trade dicts.
        window_seconds: Time window for matching buy/sell pairs.

    Returns:
        Dict with self_trade_count, self_trade_volume, self_trade_wallets.
    """
    from collections import defaultdict

    wallet_trades: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        wallet_trades[t["wallet"]].append(t)

    self_trade_wallets: set[str] = set()
    self_trade_volume = 0.0
    self_trade_count = 0

    for wallet, wtrades in wallet_trades.items():
        buys = [t for t in wtrades if t["side"] == "buy"]
        sells = [t for t in wtrades if t["side"] == "sell"]
        for buy in buys:
            for sell in sells:
                if abs(buy["timestamp"] - sell["timestamp"]) < window_seconds:
                    self_trade_wallets.add(wallet)
                    self_trade_volume += buy["volume_usd"] + sell["volume_usd"]
                    self_trade_count += 2
                    break
            else:
                continue
            break

    return {
        "self_trade_wallets": len(self_trade_wallets),
        "self_trade_volume_usd": self_trade_volume,
        "self_trade_count": self_trade_count,
    }


def trade_size_entropy(trades: list[dict], buckets: int = 10) -> float:
    """Compute Shannon entropy of trade size distribution.

    Args:
        trades: List of trade dicts.
        buckets: Number of histogram bins.

    Returns:
        Entropy value (higher = more diverse sizes).
    """
    if len(trades) < 2:
        return 0.0
    sizes = [t["volume_usd"] for t in trades]
    min_s, max_s = min(sizes), max(sizes)
    if min_s == max_s:
        return 0.0
    width = (max_s - min_s) / buckets
    counts = [0] * buckets
    for s in sizes:
        idx = min(int((s - min_s) / width), buckets - 1)
        counts[idx] += 1
    total = len(sizes)
    probs = [c / total for c in counts if c > 0]
    return -sum(p * math.log2(p) for p in probs)


def compute_momentum_score(
    buy_ratio: float,
    volume_accel: float,
    whale_buy_pct: float,
    unique_trader_trend: float,
) -> float:
    """Compute composite momentum score from flow signals.

    Args:
        buy_ratio: Buy volume / total volume (0 to 1).
        volume_accel: Current vol / previous vol.
        whale_buy_pct: Whale buy volume / total whale volume (0 to 1).
        unique_trader_trend: Change rate in unique traders.

    Returns:
        Score from -100 (strong sell pressure) to +100 (strong buy pressure).
    """
    buy_component = (buy_ratio - 0.5) * 80
    vol_component = max(-20, min(20, (volume_accel - 1.0) * 20))
    whale_component = (whale_buy_pct - 0.5) * 50
    trader_component = max(-15, min(15, unique_trader_trend * 15))

    score = buy_component + vol_component + whale_component + trader_component
    return max(-100, min(100, score))


def interpret_score(score: float) -> str:
    """Return human-readable interpretation of momentum score.

    Args:
        score: Momentum score (-100 to +100).

    Returns:
        Interpretation string.
    """
    if score >= 60:
        return "STRONG ACCUMULATION — heavy buy pressure"
    elif score >= 20:
        return "MODERATE BUYING — cautious accumulation"
    elif score >= -20:
        return "NEUTRAL — balanced flow"
    elif score >= -60:
        return "MODERATE SELLING — distribution underway"
    else:
        return "STRONG DISTRIBUTION — heavy sell pressure"


# ── Reporting ──────────────────────────────────────────────────────

def print_report(trades: list[dict], token_label: str) -> None:
    """Print formatted trade flow analysis report.

    Args:
        trades: List of normalized trade dicts.
        token_label: Display label for the token.
    """
    print("=" * 70)
    print(f"  TRADE FLOW ANALYSIS — {token_label}")
    print(f"  Trades analyzed: {len(trades)}")
    if trades:
        oldest = min(t["timestamp"] for t in trades)
        newest = max(t["timestamp"] for t in trades)
        span_hours = (newest - oldest) / 3600
        print(f"  Time span: {span_hours:.1f} hours")
    print("=" * 70)

    # ── Pressure Metrics ───────────────────────────────────────────
    pressure = compute_pressure_metrics(trades)
    print("\n── Buy/Sell Pressure ──────────────────────────────────")
    print(f"  Buy Volume:   ${pressure['buy_volume_usd']:>12,.0f}  "
          f"({pressure['buy_ratio']:.1%})")
    print(f"  Sell Volume:  ${pressure['sell_volume_usd']:>12,.0f}  "
          f"({1 - pressure['buy_ratio']:.1%})")
    print(f"  Net Flow:     ${pressure['net_flow_usd']:>+12,.0f}")
    print(f"  Buy Trades:    {pressure['buy_count']:>6d}  "
          f"({pressure['trade_count_ratio']:.1%})")
    print(f"  Sell Trades:   {pressure['sell_count']:>6d}  "
          f"({1 - pressure['trade_count_ratio']:.1%})")

    # ── Size Distribution ──────────────────────────────────────────
    dist = compute_size_distribution(trades)
    print("\n── Trade Size Distribution ────────────────────────────")
    print(f"  {'Bucket':<8} {'Count':>6} {'Volume':>12} {'Buys':>6} {'Sells':>6}")
    print(f"  {'-'*8} {'-'*6} {'-'*12} {'-'*6} {'-'*6}")
    for bucket, data in dist.items():
        if data["count"] > 0:
            print(f"  {bucket:<8} {data['count']:>6d} "
                  f"${data['volume_usd']:>10,.0f} "
                  f"{data['buy_count']:>6d} {data['sell_count']:>6d}")

    # ── Unique Traders ─────────────────────────────────────────────
    trader_info = compute_unique_traders(trades)
    print("\n── Unique Traders ────────────────────────────────────")
    print(f"  Unique wallets:  {trader_info['unique_count']}")
    print(f"  Total trades:    {trader_info['total_trades']}")
    print(f"  Unique ratio:    {trader_info['unique_ratio']:.3f}")
    print(f"\n  Top 5 traders:")
    for t in trader_info["top_traders"]:
        w = t["wallet"]
        if len(w) > 16:
            w = w[:6] + "..." + w[-4:]
        print(f"    {w:<16} {t['trades']:>4} trades  ${t['volume_usd']:>10,.0f}")

    # ── Wash Trading Signals ───────────────────────────────────────
    self_trades = detect_self_trades(trades)
    entropy = trade_size_entropy(trades)
    print("\n── Wash Trading Indicators ───────────────────────────")
    print(f"  Self-trading wallets:  {self_trades['self_trade_wallets']}")
    print(f"  Self-trade volume:     ${self_trades['self_trade_volume_usd']:,.0f}")
    print(f"  Trade size entropy:    {entropy:.2f} "
          f"({'diverse' if entropy > 2.0 else 'moderate' if entropy > 1.0 else 'low — suspicious'})")
    print(f"  Unique trader ratio:   {trader_info['unique_ratio']:.3f} "
          f"({'healthy' if trader_info['unique_ratio'] > 0.3 else 'suspicious'})")

    # ── Momentum Score ─────────────────────────────────────────────
    # Split trades into two halves for acceleration
    mid = len(trades) // 2
    first_half = trades[:mid]
    second_half = trades[mid:]

    first_vol = sum(t["volume_usd"] for t in first_half)
    second_vol = sum(t["volume_usd"] for t in second_half)
    vol_accel = second_vol / first_vol if first_vol > 0 else 1.0

    # Whale buy percentage
    whale_trades = [t for t in trades if t["volume_sol"] >= 50]
    if whale_trades:
        whale_buy_vol = sum(t["volume_usd"] for t in whale_trades if t["side"] == "buy")
        whale_total = sum(t["volume_usd"] for t in whale_trades)
        whale_buy_pct = whale_buy_vol / whale_total if whale_total > 0 else 0.5
    else:
        whale_buy_pct = 0.5

    # Unique trader trend (first vs second half)
    first_unique = len(set(t["wallet"] for t in first_half))
    second_unique = len(set(t["wallet"] for t in second_half))
    trader_trend = (
        (second_unique - first_unique) / first_unique
        if first_unique > 0
        else 0.0
    )

    score = compute_momentum_score(
        pressure["buy_ratio"], vol_accel, whale_buy_pct, trader_trend
    )

    print("\n── Composite Momentum Score ──────────────────────────")
    print(f"  Buy Ratio:           {pressure['buy_ratio']:.3f}")
    print(f"  Volume Acceleration: {vol_accel:.2f}x")
    print(f"  Whale Buy %:         {whale_buy_pct:.1%}")
    print(f"  Trader Trend:        {trader_trend:+.1%}")
    print(f"  ─────────────────────────────")
    print(f"  MOMENTUM SCORE:      {score:+.1f} / 100")
    print(f"  Signal:              {interpret_score(score)}")
    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for trade flow analysis."""
    if DEMO_MODE:
        print("[DEMO MODE] Using synthetic trade data\n")
        trades = generate_demo_trades(500)
        print_report(trades, "DEMO TOKEN")
        return

    print(f"Fetching trades for {TOKEN_MINT[:8]}...{TOKEN_MINT[-4:]}")

    # Try Birdeye first
    trades: list[dict] = []
    if BIRDEYE_API_KEY:
        try:
            trades = fetch_trades_birdeye(TOKEN_MINT, BIRDEYE_API_KEY)
            print(f"  Birdeye: fetched {len(trades)} trades")
        except Exception as e:
            print(f"  Birdeye fetch failed: {e}")

    # Fallback to DexScreener for aggregate stats
    if not trades:
        print("  Trying DexScreener for aggregate data...")
        fetch_trades_dexscreener(TOKEN_MINT)
        print("\n  No individual trade data available. Use --demo for synthetic data.")
        sys.exit(0)

    label = f"{TOKEN_MINT[:8]}...{TOKEN_MINT[-4:]}"
    print_report(trades, label)


if __name__ == "__main__":
    main()
