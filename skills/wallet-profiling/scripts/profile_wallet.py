#!/usr/bin/env python3
"""Profile a Solana wallet: fetch trade data, compute performance metrics,
classify trading style, and generate a comprehensive report.

Usage:
    python scripts/profile_wallet.py
    python scripts/profile_wallet.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    WALLET_ADDRESS: Solana wallet address to profile
    ST_API_KEY: SolanaTracker API key (optional, enables PnL data)
"""

import os
import sys
import json
import statistics
import math
from datetime import datetime, timezone
from typing import Optional

# ── Configuration ───────────────────────────────────────────────────
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
ST_API_KEY = os.getenv("ST_API_KEY", "")
DEMO_MODE = "--demo" in sys.argv


# ── Demo Data ───────────────────────────────────────────────────────
def generate_demo_data() -> list[dict]:
    """Generate realistic demo trade data for testing.

    Returns:
        List of trade dicts with pnl, timestamps, sizes, and hold times.
    """
    import random
    random.seed(42)

    base_time = 1735689600  # 2025-01-01 00:00:00 UTC
    trades = []

    for i in range(150):
        # Simulate a scalper/day-trader with ~55% win rate
        is_win = random.random() < 0.55
        if is_win:
            pnl_sol = random.uniform(0.1, 8.0)
            roi = random.uniform(0.05, 2.5)
        else:
            pnl_sol = -random.uniform(0.1, 4.0)
            roi = random.uniform(-0.95, -0.05)

        hold_minutes = random.lognormvariate(3.5, 1.2)  # Median ~33 min
        trade_size = random.lognormvariate(1.5, 0.8)     # Median ~4.5 SOL
        entry_time = base_time + i * random.randint(3600, 28800)

        token_types = ["pumpfun"] * 4 + ["raydium"] * 3 + ["orca"] * 2 + ["meteora"]
        token_type = random.choice(token_types)

        trades.append({
            "token_address": f"DemoToken{i:04d}{'A' * 32}"[:44],
            "token_symbol": f"DEMO{i}",
            "pnl_sol": round(pnl_sol, 4),
            "roi": round(roi, 4),
            "entry_value_sol": round(trade_size, 4),
            "exit_value_sol": round(trade_size * (1 + roi), 4),
            "hold_time_minutes": round(hold_minutes, 1),
            "entry_timestamp": entry_time,
            "exit_timestamp": entry_time + int(hold_minutes * 60),
            "num_buys": random.randint(1, 3),
            "num_sells": random.randint(1, 2),
            "token_type": token_type,
        })

    return trades


# ── Data Fetching ───────────────────────────────────────────────────
def fetch_solanatracker_pnl(wallet: str, api_key: str) -> Optional[list[dict]]:
    """Fetch PnL data from SolanaTracker API.

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
        print(f"SolanaTracker API error: {e.response.status_code} - {e.response.text[:200]}")
        return None
    except httpx.RequestError as e:
        print(f"Network error fetching SolanaTracker data: {e}")
        return None

    if not isinstance(data, list):
        # API may return dict with tokens list
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
            "exit_value_sol": round(total_sold, 4),
            "hold_time_minutes": round(hold_minutes, 1),
            "entry_timestamp": first_trade,
            "exit_timestamp": last_trade,
            "num_buys": num_buys,
            "num_sells": num_sells,
            "token_type": "unknown",
        })

    return trades


# ── Metric Computation ──────────────────────────────────────────────
def compute_win_rate(trades: list[dict]) -> float:
    """Compute win rate from trade list.

    Args:
        trades: List of trade dicts with 'pnl_sol' key.

    Returns:
        Win rate as decimal (0.0 to 1.0).
    """
    closed = [t for t in trades if t.get("num_sells", 0) > 0]
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t["pnl_sol"] > 0)
    return wins / len(closed)


def compute_profit_factor(trades: list[dict]) -> float:
    """Compute profit factor: gross_profit / gross_loss.

    Args:
        trades: List of trade dicts with 'pnl_sol' key.

    Returns:
        Profit factor. Returns 99.9 if no losses.
    """
    wins = sum(t["pnl_sol"] for t in trades if t["pnl_sol"] > 0)
    losses = abs(sum(t["pnl_sol"] for t in trades if t["pnl_sol"] < 0))
    if losses == 0:
        return 99.9 if wins > 0 else 0.0
    return wins / losses


def compute_total_pnl(trades: list[dict]) -> float:
    """Compute total PnL in SOL.

    Args:
        trades: List of trade dicts with 'pnl_sol' key.

    Returns:
        Total PnL in SOL.
    """
    return sum(t["pnl_sol"] for t in trades)


def compute_avg_roi(trades: list[dict]) -> float:
    """Compute average ROI per trade.

    Args:
        trades: List of trade dicts with 'roi' key.

    Returns:
        Mean ROI as decimal.
    """
    rois = [t["roi"] for t in trades if t.get("roi") is not None]
    if not rois:
        return 0.0
    return statistics.mean(rois)


def compute_max_drawdown(trades: list[dict]) -> float:
    """Compute maximum drawdown from cumulative PnL.

    Args:
        trades: List of trade dicts sorted by time with 'pnl_sol' key.

    Returns:
        Max drawdown as decimal (0.0 to 1.0).
    """
    if not trades:
        return 0.0

    cumulative = []
    running = 0.0
    for t in trades:
        running += t["pnl_sol"]
        cumulative.append(running)

    peak = cumulative[0]
    max_dd = 0.0
    for val in cumulative:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            max_dd = max(max_dd, dd)

    return max_dd


def compute_sharpe_like(trades: list[dict]) -> float:
    """Compute Sharpe-like ratio from trade returns.

    Args:
        trades: List of trade dicts with 'roi' key.

    Returns:
        Annualized Sharpe-like ratio.
    """
    rois = [t["roi"] for t in trades if t.get("roi") is not None]
    if len(rois) < 5:
        return 0.0

    mean_ret = statistics.mean(rois)
    std_ret = statistics.stdev(rois)
    if std_ret == 0:
        return 0.0

    # Estimate trades per year from timestamps
    timestamps = sorted(t["entry_timestamp"] for t in trades if t.get("entry_timestamp"))
    if len(timestamps) >= 2:
        span_days = (timestamps[-1] - timestamps[0]) / 86400
        if span_days > 0:
            trades_per_year = len(trades) / span_days * 365
        else:
            trades_per_year = 365
    else:
        trades_per_year = 365

    return mean_ret / std_ret * math.sqrt(trades_per_year)


# ── Classification ──────────────────────────────────────────────────
def classify_style(trades: list[dict]) -> str:
    """Classify trading style from hold time distribution.

    Args:
        trades: List of trade dicts with 'hold_time_minutes' key.

    Returns:
        Style label.
    """
    hold_times = [t["hold_time_minutes"] for t in trades if t.get("hold_time_minutes", 0) > 0]
    if not hold_times:
        return "unknown"

    median = statistics.median(hold_times)
    if median < 5:
        return "sniper"
    elif median < 60:
        return "scalper"
    elif median < 1440:
        return "day_trader"
    elif median < 10080:
        return "swing"
    else:
        return "holder"


def classify_size(trades: list[dict]) -> str:
    """Classify wallet by typical trade size.

    Args:
        trades: List of trade dicts with 'entry_value_sol' key.

    Returns:
        Size tier label.
    """
    sizes = [t["entry_value_sol"] for t in trades if t.get("entry_value_sol", 0) > 0]
    if not sizes:
        return "unknown"

    median = statistics.median(sizes)
    if median > 100:
        return "whale"
    elif median > 10:
        return "large"
    elif median > 1:
        return "medium"
    else:
        return "small"


def estimate_bot_probability(trades: list[dict]) -> float:
    """Estimate probability wallet is a bot from timing patterns.

    Args:
        trades: List of trade dicts with 'entry_timestamp' key.

    Returns:
        Probability from 0.0 to 1.0.
    """
    timestamps = sorted(t["entry_timestamp"] for t in trades if t.get("entry_timestamp"))
    if len(timestamps) < 10:
        return 0.0

    intervals = [
        timestamps[i + 1] - timestamps[i]
        for i in range(len(timestamps) - 1)
    ]
    intervals = [iv for iv in intervals if iv > 0]
    if len(intervals) < 5:
        return 0.0

    mean_iv = statistics.mean(intervals)
    std_iv = statistics.stdev(intervals)
    cv = std_iv / mean_iv if mean_iv > 0 else 999

    timing_score = max(0, 1.0 - cv / 0.5)

    # Round-number interval check
    round_count = sum(1 for iv in intervals if iv % 10 < 1 or iv % 10 > 9)
    round_score = round_count / len(intervals)

    # Hour coverage (bots trade 24/7)
    hours = set()
    for ts in timestamps:
        hours.add(datetime.fromtimestamp(ts, tz=timezone.utc).hour)
    hour_score = len(hours) / 24

    probability = timing_score * 0.5 + round_score * 0.25 + hour_score * 0.25
    return round(min(1.0, max(0.0, probability)), 2)


def classify_focus(trades: list[dict]) -> str:
    """Classify wallet focus area.

    Args:
        trades: List of trade dicts with 'token_type' key.

    Returns:
        Focus area label.
    """
    types = [t.get("token_type", "unknown") for t in trades]
    if not types:
        return "unknown"

    from collections import Counter
    counts = Counter(types)
    total = len(types)

    pumpfun_pct = counts.get("pumpfun", 0) / total
    if pumpfun_pct > 0.7:
        return "pumpfun_specialist"
    elif pumpfun_pct > 0.3:
        return "mixed_memecoin"
    else:
        return "dex_trader"


# ── Activity Analysis ───────────────────────────────────────────────
def analyze_activity(trades: list[dict]) -> dict:
    """Analyze trading activity patterns.

    Args:
        trades: List of trade dicts with timestamps.

    Returns:
        Activity metrics dict.
    """
    if not trades:
        return {}

    timestamps = sorted(t["entry_timestamp"] for t in trades if t.get("entry_timestamp"))
    if len(timestamps) < 2:
        return {"total_trades": len(trades)}

    span_days = max((timestamps[-1] - timestamps[0]) / 86400, 1)
    trades_per_day = len(trades) / span_days

    hold_times = [t["hold_time_minutes"] for t in trades if t.get("hold_time_minutes", 0) > 0]
    avg_hold = statistics.mean(hold_times) if hold_times else 0
    median_hold = statistics.median(hold_times) if hold_times else 0

    # Unique tokens
    unique_tokens = len(set(t.get("token_address", "") for t in trades))
    token_diversity = unique_tokens / len(trades) if trades else 0

    # Peak hours
    hours = [datetime.fromtimestamp(ts, tz=timezone.utc).hour for ts in timestamps]
    from collections import Counter
    hour_counts = Counter(hours)
    peak_hours = [h for h, _ in hour_counts.most_common(3)]

    return {
        "total_trades": len(trades),
        "active_days": round(span_days, 1),
        "trades_per_day": round(trades_per_day, 1),
        "avg_hold_minutes": round(avg_hold, 1),
        "median_hold_minutes": round(median_hold, 1),
        "unique_tokens": unique_tokens,
        "token_diversity": round(token_diversity, 2),
        "peak_hours_utc": peak_hours,
    }


# ── Risk Assessment ─────────────────────────────────────────────────
def compute_risk_score(
    trades: list[dict],
    win_rate: float,
    profit_factor: float,
    bot_prob: float,
) -> tuple[int, list[str]]:
    """Compute copy-trade risk score (0=low risk, 100=high risk).

    Args:
        trades: Trade list.
        win_rate: Computed win rate.
        profit_factor: Computed profit factor.
        bot_prob: Bot probability estimate.

    Returns:
        (risk_score, list_of_risk_flags)
    """
    score = 0
    flags = []

    # Wallet age
    timestamps = sorted(t["entry_timestamp"] for t in trades if t.get("entry_timestamp"))
    if len(timestamps) >= 2:
        age_days = (timestamps[-1] - timestamps[0]) / 86400
        if age_days < 14:
            score += 25
            flags.append(f"New wallet ({age_days:.0f} days old)")

    # Single big win concentration
    total_pnl = sum(t["pnl_sol"] for t in trades)
    if total_pnl > 0:
        max_single = max(t["pnl_sol"] for t in trades)
        if max_single / total_pnl > 0.5:
            score += 20
            flags.append(f"Top trade = {max_single / total_pnl:.0%} of total PnL")

    # Performance decay (compare last 30 trades to rest)
    if len(trades) >= 60:
        recent = trades[-30:]
        historical = trades[:-30]
        recent_pf = compute_profit_factor(recent)
        hist_pf = compute_profit_factor(historical)
        if recent_pf < hist_pf * 0.7:
            score += 15
            flags.append(f"Performance decay: recent PF {recent_pf:.2f} vs historical {hist_pf:.2f}")

    # Bot probability
    if bot_prob > 0.7:
        score += 15
        flags.append(f"High bot probability ({bot_prob:.0%})")

    # Suspicious win rate
    if win_rate > 0.8:
        score += 10
        flags.append(f"Suspiciously high win rate ({win_rate:.0%})")

    # Low token diversity
    unique_tokens = len(set(t.get("token_address", "") for t in trades))
    if unique_tokens < 5:
        score += 15
        flags.append(f"Low diversity ({unique_tokens} unique tokens)")

    # Low sample size
    if len(trades) < 30:
        score += 10
        flags.append(f"Small sample ({len(trades)} trades)")

    return min(100, score), flags


# ── Report Generation ──────────────────────────────────────────────
def print_report(
    wallet: str,
    trades: list[dict],
    metrics: dict,
    classification: dict,
    activity: dict,
    risk_score: int,
    risk_flags: list[str],
) -> None:
    """Print formatted wallet profile report.

    Args:
        wallet: Wallet address.
        trades: Trade list.
        metrics: Performance metrics dict.
        classification: Classification dict.
        activity: Activity metrics dict.
        risk_score: Risk score 0-100.
        risk_flags: List of risk flag descriptions.
    """
    divider = "=" * 70

    print(f"\n{divider}")
    print(f"  WALLET PROFILE REPORT")
    print(f"{divider}")
    print(f"  Wallet:  {wallet}")
    print(f"  Trades:  {len(trades)}")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{divider}\n")

    # Performance Metrics
    print("  PERFORMANCE METRICS")
    print(f"  {'-' * 40}")
    print(f"  Win Rate:        {metrics['win_rate']:.1%}")
    print(f"  Avg ROI:         {metrics['avg_roi']:.1%}")
    print(f"  Profit Factor:   {metrics['profit_factor']:.2f}")
    print(f"  Total PnL:       {metrics['total_pnl']:.2f} SOL")
    print(f"  Max Drawdown:    {metrics['max_drawdown']:.1%}")
    print(f"  Sharpe-Like:     {metrics['sharpe']:.2f}")
    print()

    # Classification
    print("  CLASSIFICATION")
    print(f"  {'-' * 40}")
    print(f"  Style:           {classification['style'].replace('_', ' ').title()}")
    print(f"  Size Tier:       {classification['size_tier'].title()}")
    print(f"  Focus:           {classification['focus'].replace('_', ' ').title()}")
    print(f"  Bot Probability: {classification['bot_probability']:.0%}")
    print()

    # Activity
    print("  ACTIVITY")
    print(f"  {'-' * 40}")
    print(f"  Active Days:     {activity.get('active_days', 'N/A')}")
    print(f"  Trades/Day:      {activity.get('trades_per_day', 'N/A')}")
    print(f"  Avg Hold:        {activity.get('avg_hold_minutes', 0):.0f} min")
    print(f"  Median Hold:     {activity.get('median_hold_minutes', 0):.0f} min")
    print(f"  Unique Tokens:   {activity.get('unique_tokens', 'N/A')}")
    print(f"  Token Diversity: {activity.get('token_diversity', 0):.0%}")
    peak = activity.get("peak_hours_utc", [])
    print(f"  Peak Hours (UTC):{' ' + ', '.join(f'{h:02d}:00' for h in peak) if peak else ' N/A'}")
    print()

    # Risk Assessment
    risk_label = (
        "LOW" if risk_score < 25
        else "MODERATE" if risk_score < 50
        else "HIGH" if risk_score < 75
        else "VERY HIGH"
    )
    print("  COPY-TRADE RISK ASSESSMENT")
    print(f"  {'-' * 40}")
    print(f"  Risk Score:      {risk_score}/100 ({risk_label})")
    if risk_flags:
        print(f"  Flags:")
        for flag in risk_flags:
            print(f"    - {flag}")
    else:
        print(f"  Flags:           None detected")
    print()

    # Top Trades
    sorted_trades = sorted(trades, key=lambda t: t["pnl_sol"], reverse=True)
    print("  TOP 5 WINNING TRADES")
    print(f"  {'-' * 40}")
    for t in sorted_trades[:5]:
        symbol = t.get("token_symbol", "???")[:8]
        print(f"  {symbol:<10} PnL: {t['pnl_sol']:>8.2f} SOL  ROI: {t['roi']:>7.0%}")
    print()

    print("  BOTTOM 5 LOSING TRADES")
    print(f"  {'-' * 40}")
    for t in sorted_trades[-5:]:
        symbol = t.get("token_symbol", "???")[:8]
        print(f"  {symbol:<10} PnL: {t['pnl_sol']:>8.2f} SOL  ROI: {t['roi']:>7.0%}")

    print(f"\n{divider}")
    print("  NOTE: This analysis is for informational purposes only.")
    print("  Past performance does not guarantee future results.")
    print(f"{divider}\n")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run wallet profiling pipeline."""
    if DEMO_MODE:
        wallet = "DemoWallet1111111111111111111111111111111111"
        print("Running in demo mode with synthetic data...")
        trades = generate_demo_data()
    elif not WALLET_ADDRESS:
        print("Set WALLET_ADDRESS environment variable or use --demo flag.")
        print("Usage:")
        print("  export WALLET_ADDRESS=YourWallet...")
        print("  python scripts/profile_wallet.py")
        print("  python scripts/profile_wallet.py --demo")
        sys.exit(1)
    else:
        wallet = WALLET_ADDRESS
        trades = None

        if ST_API_KEY:
            print(f"Fetching PnL data from SolanaTracker for {wallet[:8]}...")
            trades = fetch_solanatracker_pnl(wallet, ST_API_KEY)

        if trades is None:
            print("No data available. Set ST_API_KEY for SolanaTracker access or use --demo.")
            sys.exit(1)

        if not trades:
            print(f"No trades found for wallet {wallet[:8]}...")
            sys.exit(0)

    # Sort by entry timestamp
    trades.sort(key=lambda t: t.get("entry_timestamp", 0))

    # Compute metrics
    win_rate = compute_win_rate(trades)
    avg_roi = compute_avg_roi(trades)
    profit_factor = compute_profit_factor(trades)
    total_pnl = compute_total_pnl(trades)
    max_dd = compute_max_drawdown(trades)
    sharpe = compute_sharpe_like(trades)

    metrics = {
        "win_rate": win_rate,
        "avg_roi": avg_roi,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
    }

    # Classify
    bot_prob = estimate_bot_probability(trades)
    classification = {
        "style": classify_style(trades),
        "size_tier": classify_size(trades),
        "focus": classify_focus(trades),
        "bot_probability": bot_prob,
    }

    # Activity analysis
    activity = analyze_activity(trades)

    # Risk assessment
    risk_score, risk_flags = compute_risk_score(trades, win_rate, profit_factor, bot_prob)

    # Print report
    print_report(wallet, trades, metrics, classification, activity, risk_score, risk_flags)


if __name__ == "__main__":
    main()
