#!/usr/bin/env python3
"""Compare multiple Solana wallets side-by-side: fetch data, compute metrics
for each, rank by key performance indicators, and identify best performers.

Usage:
    python scripts/compare_wallets.py
    python scripts/compare_wallets.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    WALLET_ADDRESSES: Comma-separated Solana wallet addresses
    ST_API_KEY: SolanaTracker API key (optional, enables PnL data)
"""

import os
import sys
import statistics
import math
from datetime import datetime, timezone
from typing import Optional

# ── Configuration ───────────────────────────────────────────────────
WALLET_ADDRESSES = os.getenv("WALLET_ADDRESSES", "")
ST_API_KEY = os.getenv("ST_API_KEY", "")
DEMO_MODE = "--demo" in sys.argv


# ── Demo Data ───────────────────────────────────────────────────────
def generate_demo_wallets() -> dict[str, list[dict]]:
    """Generate demo trade data for three wallets with different profiles.

    Returns:
        Dict mapping wallet address to list of trade dicts.
    """
    import random

    wallets = {}

    # Wallet A: Consistent scalper, moderate edge
    random.seed(100)
    base_time = 1735689600
    trades_a = []
    for i in range(200):
        is_win = random.random() < 0.58
        if is_win:
            pnl = random.uniform(0.2, 3.0)
            roi = random.uniform(0.05, 0.8)
        else:
            pnl = -random.uniform(0.1, 2.0)
            roi = random.uniform(-0.6, -0.05)

        trades_a.append({
            "token_address": f"TokenA{i:04d}{'B' * 32}"[:44],
            "token_symbol": f"TKA{i}",
            "pnl_sol": round(pnl, 4),
            "roi": round(roi, 4),
            "entry_value_sol": round(random.uniform(2, 8), 4),
            "hold_time_minutes": round(random.uniform(10, 120), 1),
            "entry_timestamp": base_time + i * random.randint(3600, 14400),
            "num_buys": 1,
            "num_sells": 1,
        })
    wallets["ScalperAlpha111111111111111111111111111111"] = trades_a

    # Wallet B: Aggressive sniper, high win rate but volatile
    random.seed(200)
    trades_b = []
    for i in range(120):
        is_win = random.random() < 0.45
        if is_win:
            pnl = random.uniform(1.0, 25.0)
            roi = random.uniform(0.5, 10.0)
        else:
            pnl = -random.uniform(0.5, 5.0)
            roi = random.uniform(-0.95, -0.2)

        trades_b.append({
            "token_address": f"TokenB{i:04d}{'C' * 32}"[:44],
            "token_symbol": f"TKB{i}",
            "pnl_sol": round(pnl, 4),
            "roi": round(roi, 4),
            "entry_value_sol": round(random.uniform(5, 30), 4),
            "hold_time_minutes": round(random.uniform(0.5, 5), 1),
            "entry_timestamp": base_time + i * random.randint(7200, 28800),
            "num_buys": 1,
            "num_sells": 1,
        })
    wallets["SniperBeta2222222222222222222222222222222222"] = trades_b

    # Wallet C: Swing trader, fewer trades but high conviction
    random.seed(300)
    trades_c = []
    for i in range(60):
        is_win = random.random() < 0.52
        if is_win:
            pnl = random.uniform(2.0, 15.0)
            roi = random.uniform(0.1, 1.5)
        else:
            pnl = -random.uniform(1.0, 8.0)
            roi = random.uniform(-0.5, -0.1)

        trades_c.append({
            "token_address": f"TokenC{i:04d}{'D' * 32}"[:44],
            "token_symbol": f"TKC{i}",
            "pnl_sol": round(pnl, 4),
            "roi": round(roi, 4),
            "entry_value_sol": round(random.uniform(10, 50), 4),
            "hold_time_minutes": round(random.uniform(1440, 14400), 1),
            "entry_timestamp": base_time + i * random.randint(43200, 172800),
            "num_buys": random.randint(1, 4),
            "num_sells": random.randint(1, 3),
        })
    wallets["SwingGamma33333333333333333333333333333333333"] = trades_c

    return wallets


# ── Data Fetching ───────────────────────────────────────────────────
def fetch_wallet_trades(wallet: str, api_key: str) -> Optional[list[dict]]:
    """Fetch PnL data from SolanaTracker API for a single wallet.

    Args:
        wallet: Solana wallet address.
        api_key: SolanaTracker API key.

    Returns:
        List of trade dicts, or None on failure.
    """
    try:
        import httpx
    except ImportError:
        print("httpx not installed. Run: uv pip install httpx")
        return None

    url = f"https://data.solanatracker.io/pnl/{wallet}"
    headers = {"x-api-key": api_key}

    try:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"  API error for {wallet[:8]}...: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        print(f"  Network error for {wallet[:8]}...: {e}")
        return None

    if not isinstance(data, list):
        data = data.get("tokens", data.get("data", []))

    trades = []
    for token_data in data:
        if not isinstance(token_data, dict):
            continue

        realized = token_data.get("realized", 0) or 0
        total_invested = token_data.get("total_invested", 0) or 0
        total_sold = token_data.get("total_sold", 0) or 0
        num_buys = token_data.get("num_buys", 0) or 0
        num_sells = token_data.get("num_sells", 0) or 0

        if num_buys == 0 and num_sells == 0:
            continue

        roi = (total_sold - total_invested) / total_invested if total_invested > 0 else 0
        last_trade = token_data.get("last_trade_time", 0) or 0
        first_trade = token_data.get("first_trade_time", last_trade) or last_trade
        hold_minutes = (last_trade - first_trade) / 60 if last_trade > first_trade else 0

        trades.append({
            "token_address": token_data.get("token", "unknown"),
            "token_symbol": token_data.get("symbol", "???"),
            "pnl_sol": round(realized, 4),
            "roi": round(roi, 4),
            "entry_value_sol": round(total_invested, 4),
            "hold_time_minutes": round(hold_minutes, 1),
            "entry_timestamp": first_trade,
            "num_buys": num_buys,
            "num_sells": num_sells,
        })

    return trades


# ── Metrics ─────────────────────────────────────────────────────────
def compute_metrics(trades: list[dict]) -> dict:
    """Compute all performance metrics for a wallet's trades.

    Args:
        trades: List of trade dicts.

    Returns:
        Dict of metric name to value.
    """
    if not trades:
        return {
            "trade_count": 0, "win_rate": 0, "avg_roi": 0,
            "profit_factor": 0, "total_pnl": 0, "max_drawdown": 0,
            "sharpe": 0, "style": "unknown", "median_hold_min": 0,
            "median_size_sol": 0,
        }

    closed = [t for t in trades if t.get("num_sells", 0) > 0]
    wins = sum(1 for t in closed if t["pnl_sol"] > 0) if closed else 0
    win_rate = wins / len(closed) if closed else 0

    rois = [t["roi"] for t in trades if t.get("roi") is not None]
    avg_roi = statistics.mean(rois) if rois else 0

    gross_win = sum(t["pnl_sol"] for t in trades if t["pnl_sol"] > 0)
    gross_loss = abs(sum(t["pnl_sol"] for t in trades if t["pnl_sol"] < 0))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (99.9 if gross_win > 0 else 0)

    total_pnl = sum(t["pnl_sol"] for t in trades)

    # Max drawdown
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_timestamp", 0))
    cumulative = []
    running = 0.0
    for t in sorted_trades:
        running += t["pnl_sol"]
        cumulative.append(running)

    peak = cumulative[0] if cumulative else 0
    max_dd = 0.0
    for val in cumulative:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            max_dd = max(max_dd, dd)

    # Sharpe
    sharpe = 0.0
    if len(rois) >= 5:
        mean_r = statistics.mean(rois)
        std_r = statistics.stdev(rois)
        if std_r > 0:
            timestamps = sorted(t["entry_timestamp"] for t in trades if t.get("entry_timestamp"))
            if len(timestamps) >= 2:
                span = (timestamps[-1] - timestamps[0]) / 86400
                tpy = len(trades) / max(span, 1) * 365
            else:
                tpy = 365
            sharpe = mean_r / std_r * math.sqrt(tpy)

    # Style
    hold_times = [t["hold_time_minutes"] for t in trades if t.get("hold_time_minutes", 0) > 0]
    median_hold = statistics.median(hold_times) if hold_times else 0
    if median_hold < 5:
        style = "sniper"
    elif median_hold < 60:
        style = "scalper"
    elif median_hold < 1440:
        style = "day_trader"
    elif median_hold < 10080:
        style = "swing"
    else:
        style = "holder"

    sizes = [t["entry_value_sol"] for t in trades if t.get("entry_value_sol", 0) > 0]
    median_size = statistics.median(sizes) if sizes else 0

    # Consistency: rolling win rate std
    consistency = -1.0
    if len(trades) >= 40:
        rolling_wrs = []
        for i in range(20, len(trades) + 1):
            chunk = trades[i - 20:i]
            wr = sum(1 for t in chunk if t["pnl_sol"] > 0) / len(chunk)
            rolling_wrs.append(wr)
        if len(rolling_wrs) >= 2:
            consistency = statistics.stdev(rolling_wrs)

    return {
        "trade_count": len(trades),
        "win_rate": round(win_rate, 3),
        "avg_roi": round(avg_roi, 3),
        "profit_factor": round(profit_factor, 2),
        "total_pnl": round(total_pnl, 2),
        "max_drawdown": round(max_dd, 3),
        "sharpe": round(sharpe, 2),
        "style": style,
        "median_hold_min": round(median_hold, 1),
        "median_size_sol": round(median_size, 2),
        "consistency": round(consistency, 3) if consistency >= 0 else None,
    }


# ── Ranking ─────────────────────────────────────────────────────────
def rank_wallets(wallet_metrics: dict[str, dict]) -> dict[str, dict]:
    """Rank wallets across multiple dimensions.

    Args:
        wallet_metrics: Dict mapping wallet address to metrics dict.

    Returns:
        Dict mapping wallet to ranks dict.
    """
    wallets = list(wallet_metrics.keys())
    if not wallets:
        return {}

    categories = ["win_rate", "profit_factor", "total_pnl", "sharpe"]
    ranks: dict[str, dict] = {w: {} for w in wallets}

    for cat in categories:
        sorted_by = sorted(wallets, key=lambda w: wallet_metrics[w].get(cat, 0), reverse=True)
        for rank, w in enumerate(sorted_by, 1):
            ranks[w][cat] = rank

    # Composite rank: average of ranks (lower = better)
    for w in wallets:
        ranks[w]["composite"] = round(
            sum(ranks[w][cat] for cat in categories) / len(categories), 1
        )

    return ranks


# ── Report ──────────────────────────────────────────────────────────
def print_comparison_report(
    wallet_metrics: dict[str, dict],
    wallet_ranks: dict[str, dict],
) -> None:
    """Print formatted comparison table.

    Args:
        wallet_metrics: Dict mapping wallet address to metrics.
        wallet_ranks: Dict mapping wallet address to ranks.
    """
    divider = "=" * 90

    print(f"\n{divider}")
    print("  WALLET COMPARISON REPORT")
    print(f"{divider}")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Wallets:   {len(wallet_metrics)}")
    print(f"{divider}\n")

    # Summary table
    wallets = sorted(
        wallet_metrics.keys(),
        key=lambda w: wallet_ranks.get(w, {}).get("composite", 99),
    )

    # Header
    print(f"  {'Wallet':<14} {'Trades':>6} {'Win%':>6} {'PF':>6} {'PnL(SOL)':>10} "
          f"{'Sharpe':>7} {'MaxDD':>7} {'Style':<12} {'Rank':>5}")
    print(f"  {'-' * 85}")

    for w in wallets:
        m = wallet_metrics[w]
        r = wallet_ranks.get(w, {})
        label = w[:12] + ".."
        print(
            f"  {label:<14} {m['trade_count']:>6} {m['win_rate']:>5.0%} "
            f"{m['profit_factor']:>6.2f} {m['total_pnl']:>10.2f} "
            f"{m['sharpe']:>7.2f} {m['max_drawdown']:>6.0%} "
            f"{m['style']:<12} {r.get('composite', 'N/A'):>5}"
        )

    print()

    # Detailed rankings
    print("  RANKINGS BY CATEGORY")
    print(f"  {'-' * 50}")
    categories = [
        ("win_rate", "Win Rate"),
        ("profit_factor", "Profit Factor"),
        ("total_pnl", "Total PnL"),
        ("sharpe", "Sharpe Ratio"),
    ]

    for key, label in categories:
        ranked = sorted(wallets, key=lambda w: wallet_ranks.get(w, {}).get(key, 99))
        winner = ranked[0] if ranked else "N/A"
        val = wallet_metrics.get(winner, {}).get(key, 0)
        if key == "win_rate":
            val_str = f"{val:.0%}"
        elif key == "total_pnl":
            val_str = f"{val:.2f} SOL"
        else:
            val_str = f"{val:.2f}"
        print(f"  {label:<20} #1: {winner[:12]:<14} ({val_str})")

    print()

    # Overall winner
    best = min(wallets, key=lambda w: wallet_ranks.get(w, {}).get("composite", 99))
    print(f"  OVERALL BEST PERFORMER: {best[:20]}...")
    m = wallet_metrics[best]
    print(f"  Style: {m['style'].replace('_', ' ').title()}, "
          f"Win Rate: {m['win_rate']:.0%}, "
          f"PF: {m['profit_factor']:.2f}, "
          f"PnL: {m['total_pnl']:.2f} SOL")

    # Consistency comparison
    consistent_wallets = {
        w: m for w, m in wallet_metrics.items() if m.get("consistency") is not None
    }
    if consistent_wallets:
        print()
        print("  CONSISTENCY (Rolling Win Rate StdDev — lower is better)")
        print(f"  {'-' * 50}")
        for w in sorted(consistent_wallets, key=lambda w: consistent_wallets[w]["consistency"]):
            c = consistent_wallets[w]["consistency"]
            label = "Very Consistent" if c < 0.05 else "Consistent" if c < 0.10 else "Variable" if c < 0.15 else "Erratic"
            print(f"  {w[:14]:<16} StdDev: {c:.3f}  ({label})")

    print(f"\n{divider}")
    print("  NOTE: This analysis is for informational purposes only.")
    print("  Past performance does not guarantee future results.")
    print(f"{divider}\n")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run wallet comparison pipeline."""
    if DEMO_MODE:
        print("Running in demo mode with synthetic data for 3 wallets...\n")
        wallet_data = generate_demo_wallets()
    elif not WALLET_ADDRESSES:
        print("Set WALLET_ADDRESSES environment variable or use --demo flag.")
        print("Usage:")
        print("  export WALLET_ADDRESSES=Wallet1...,Wallet2...,Wallet3...")
        print("  python scripts/compare_wallets.py")
        print("  python scripts/compare_wallets.py --demo")
        sys.exit(1)
    else:
        addresses = [a.strip() for a in WALLET_ADDRESSES.split(",") if a.strip()]
        if len(addresses) < 2:
            print("Provide at least 2 wallet addresses separated by commas.")
            sys.exit(1)

        if not ST_API_KEY:
            print("ST_API_KEY not set. Cannot fetch wallet data without API key.")
            print("Use --demo to see example output.")
            sys.exit(1)

        wallet_data = {}
        for addr in addresses:
            print(f"Fetching data for {addr[:8]}...")
            trades = fetch_wallet_trades(addr, ST_API_KEY)
            if trades:
                wallet_data[addr] = trades
            else:
                print(f"  Skipping {addr[:8]}... (no data)")

        if len(wallet_data) < 2:
            print("Need at least 2 wallets with data for comparison.")
            sys.exit(1)

    # Compute metrics for each wallet
    wallet_metrics = {}
    for wallet, trades in wallet_data.items():
        trades.sort(key=lambda t: t.get("entry_timestamp", 0))
        wallet_metrics[wallet] = compute_metrics(trades)

    # Rank wallets
    wallet_ranks = rank_wallets(wallet_metrics)

    # Print comparison
    print_comparison_report(wallet_metrics, wallet_ranks)


if __name__ == "__main__":
    main()
