#!/usr/bin/env python3
"""Evaluate a Solana wallet's suitability for copy trading.

Fetches trade history from SolanaTracker PnL API, computes a composite
copy-trade suitability score, and prints a comprehensive GO/NO-GO
recommendation. Includes a --demo mode with example data.

Usage:
    python scripts/evaluate_wallet.py                     # uses WALLET_ADDRESS env var
    python scripts/evaluate_wallet.py <wallet_address>    # direct argument
    python scripts/evaluate_wallet.py --demo              # run with example data

Dependencies:
    uv pip install httpx

Environment Variables:
    WALLET_ADDRESS: Wallet to evaluate (optional if passed as argument)
    ST_API_KEY: SolanaTracker API key (optional, improves rate limits)
"""

import json
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────
ST_API_KEY = os.getenv("ST_API_KEY", "")
ST_BASE_URL = "https://data.solanatracker.io"

# Minimum thresholds for copy-trade suitability
MIN_TRADES = 50
MIN_WIN_RATE = 0.55
MIN_PROFIT_FACTOR = 1.5
MAX_DAYS_INACTIVE = 7
MIN_DISTINCT_TOKENS = 10
MAX_SINGLE_TRADE_PNL_PCT = 0.40
MAX_BOT_PROBABILITY = 0.30

# Score weights
WEIGHT_TRADE_COUNT = 0.15
WEIGHT_WIN_RATE = 0.20
WEIGHT_PROFIT_FACTOR = 0.25
WEIGHT_CONSISTENCY = 0.20
WEIGHT_RECENCY = 0.10
WEIGHT_HUMAN_PROB = 0.10


# ── Data Structures ────────────────────────────────────────────────
@dataclass
class TokenTrade:
    """Summarized trade on a single token."""
    token_address: str
    token_symbol: str
    pnl_sol: float
    pnl_usd: float
    bought_sol: float
    sold_sol: float
    num_buys: int
    num_sells: int
    first_trade_ts: int
    last_trade_ts: int

    @property
    def is_win(self) -> bool:
        return self.pnl_sol > 0

    @property
    def hold_time_seconds(self) -> int:
        return max(self.last_trade_ts - self.first_trade_ts, 0)


@dataclass
class WalletEvaluation:
    """Complete copy-trade evaluation for a wallet."""
    wallet: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    total_pnl_sol: float
    total_pnl_usd: float
    distinct_tokens: int
    days_since_last_trade: float
    max_single_trade_pnl_pct: float
    median_hold_time_hours: float
    bot_probability: float
    consistency_score: float
    composite_score: float
    rating: str
    passed_all_minimums: bool
    failures: list[str]


# ── API Functions ───────────────────────────────────────────────────
def fetch_wallet_pnl(wallet: str) -> dict:
    """Fetch wallet PnL data from SolanaTracker.

    Args:
        wallet: Solana wallet address.

    Returns:
        Parsed JSON response with PnL data.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    url = f"{ST_BASE_URL}/pnl/{wallet}"
    headers = {}
    if ST_API_KEY:
        headers["x-api-key"] = ST_API_KEY

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ── Scoring Functions ───────────────────────────────────────────────
def score_trade_count(count: int) -> float:
    """Score based on number of trades. Maxes out at 200."""
    return min(count / 200.0, 1.0) * 100.0


def score_win_rate(win_rate: float) -> float:
    """Score win rate, scaled from 40% to 70%."""
    return max((win_rate - 0.40) / 0.30, 0.0) * 100.0


def score_profit_factor(pf: float) -> float:
    """Score profit factor, scaled from 1.0 to 4.0."""
    return min(max((pf - 1.0) / 3.0, 0.0), 1.0) * 100.0


def score_consistency(trades: list[TokenTrade], window: int = 10) -> float:
    """Score based on rolling win rate stability.

    Lower standard deviation of rolling win rate = higher score.
    """
    if len(trades) < window:
        return 50.0  # Insufficient data, neutral score

    sorted_trades = sorted(trades, key=lambda t: t.first_trade_ts)
    rolling_win_rates: list[float] = []

    for i in range(len(sorted_trades) - window + 1):
        window_trades = sorted_trades[i : i + window]
        wr = sum(1 for t in window_trades if t.is_win) / len(window_trades)
        rolling_win_rates.append(wr)

    if not rolling_win_rates:
        return 50.0

    mean_wr = sum(rolling_win_rates) / len(rolling_win_rates)
    variance = sum((wr - mean_wr) ** 2 for wr in rolling_win_rates) / len(
        rolling_win_rates
    )
    std_dev = math.sqrt(variance)

    # Clamp std_dev to [0, 1] range, then invert
    return max(0.0, (1.0 - min(std_dev, 1.0)) * 100.0)


def score_recency(days_since_last: float) -> float:
    """Score based on days since last trade. Decays over 14 days."""
    return max(1.0 - days_since_last / 14.0, 0.0) * 100.0


def estimate_bot_probability(trades: list[TokenTrade]) -> float:
    """Estimate probability that the wallet is a bot.

    Heuristics:
    - Very short hold times (< 60s median) suggest bot
    - Very high trade count (> 500 in 30 days) suggests bot
    - Regular timing intervals suggest bot
    """
    if not trades:
        return 0.5

    hold_times = [t.hold_time_seconds for t in trades if t.hold_time_seconds > 0]
    if not hold_times:
        return 0.3

    median_hold = sorted(hold_times)[len(hold_times) // 2]
    bot_score = 0.0

    # Very short hold times
    if median_hold < 30:
        bot_score += 0.4
    elif median_hold < 60:
        bot_score += 0.25
    elif median_hold < 120:
        bot_score += 0.1

    # High trade frequency
    if len(trades) > 500:
        bot_score += 0.3
    elif len(trades) > 200:
        bot_score += 0.15

    # Check timing regularity (intervals between trades)
    timestamps = sorted(t.first_trade_ts for t in trades)
    if len(timestamps) >= 10:
        intervals = [
            timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)
        ]
        if intervals:
            mean_interval = sum(intervals) / len(intervals)
            if mean_interval > 0:
                cv = math.sqrt(
                    sum((i - mean_interval) ** 2 for i in intervals) / len(intervals)
                ) / mean_interval
                # Low coefficient of variation = regular = bot-like
                if cv < 0.2:
                    bot_score += 0.3
                elif cv < 0.5:
                    bot_score += 0.1

    return min(bot_score, 1.0)


def score_human_probability(bot_prob: float) -> float:
    """Score based on probability of being human (not a bot)."""
    return (1.0 - bot_prob) * 100.0


# ── Evaluation Pipeline ────────────────────────────────────────────
def parse_trades(pnl_data: dict) -> list[TokenTrade]:
    """Parse SolanaTracker PnL response into TokenTrade objects."""
    trades: list[TokenTrade] = []
    tokens = pnl_data.get("tokens", [])

    for token_data in tokens:
        token_info = token_data.get("token", {})
        pnl = token_data.get("pnl", 0)
        pnl_usd = token_data.get("pnl_usd", 0)
        bought = token_data.get("total_bought_sol", 0) or token_data.get("bought", 0)
        sold = token_data.get("total_sold_sol", 0) or token_data.get("sold", 0)
        num_buys = token_data.get("num_buys", 1)
        num_sells = token_data.get("num_sells", 0)
        first_ts = token_data.get("first_trade_time", 0)
        last_ts = token_data.get("last_trade_time", 0)

        trades.append(
            TokenTrade(
                token_address=token_info.get("mint", token_data.get("token", "")),
                token_symbol=token_info.get("symbol", "???"),
                pnl_sol=float(pnl),
                pnl_usd=float(pnl_usd) if pnl_usd else 0.0,
                bought_sol=float(bought),
                sold_sol=float(sold),
                num_buys=int(num_buys),
                num_sells=int(num_sells),
                first_trade_ts=int(first_ts),
                last_trade_ts=int(last_ts),
            )
        )

    return trades


def evaluate_wallet(
    wallet: str, trades: list[TokenTrade]
) -> WalletEvaluation:
    """Run full copy-trade suitability evaluation.

    Args:
        wallet: The wallet address being evaluated.
        trades: List of parsed token trades.

    Returns:
        Complete WalletEvaluation with scores and recommendation.
    """
    total_trades = len(trades)
    wins = sum(1 for t in trades if t.is_win)
    losses = total_trades - wins
    win_rate = wins / max(total_trades, 1)

    gross_profit = sum(t.pnl_sol for t in trades if t.pnl_sol > 0)
    gross_loss = abs(sum(t.pnl_sol for t in trades if t.pnl_sol < 0))
    profit_factor = gross_profit / max(gross_loss, 0.001)

    total_pnl_sol = sum(t.pnl_sol for t in trades)
    total_pnl_usd = sum(t.pnl_usd for t in trades)

    distinct_tokens = len(set(t.token_address for t in trades))

    # Days since last trade
    last_trade_ts = max((t.last_trade_ts for t in trades), default=0)
    if last_trade_ts > 0:
        days_since_last = (time.time() - last_trade_ts) / 86400.0
    else:
        days_since_last = 999.0

    # Max single-trade PnL as percentage of total
    if total_pnl_sol > 0:
        max_single_pnl = max(t.pnl_sol for t in trades)
        max_single_pnl_pct = max_single_pnl / total_pnl_sol
    else:
        max_single_pnl_pct = 1.0

    # Median hold time
    hold_times = sorted(
        t.hold_time_seconds / 3600.0 for t in trades if t.hold_time_seconds > 0
    )
    median_hold_hours = hold_times[len(hold_times) // 2] if hold_times else 0.0

    # Bot probability
    bot_prob = estimate_bot_probability(trades)

    # Consistency
    consistency = score_consistency(trades)

    # Composite score
    tc_score = score_trade_count(total_trades)
    wr_score = score_win_rate(win_rate)
    pf_score = score_profit_factor(profit_factor)
    rec_score = score_recency(days_since_last)
    hum_score = score_human_probability(bot_prob)

    composite = (
        tc_score * WEIGHT_TRADE_COUNT
        + wr_score * WEIGHT_WIN_RATE
        + pf_score * WEIGHT_PROFIT_FACTOR
        + consistency * WEIGHT_CONSISTENCY
        + rec_score * WEIGHT_RECENCY
        + hum_score * WEIGHT_HUMAN_PROB
    )

    # Rating
    if composite >= 80:
        rating = "EXCELLENT"
    elif composite >= 60:
        rating = "GOOD"
    elif composite >= 40:
        rating = "MARGINAL"
    else:
        rating = "POOR"

    # Check minimum thresholds
    failures: list[str] = []
    if total_trades < MIN_TRADES:
        failures.append(f"Trade count {total_trades} < {MIN_TRADES}")
    if win_rate < MIN_WIN_RATE:
        failures.append(f"Win rate {win_rate:.1%} < {MIN_WIN_RATE:.0%}")
    if profit_factor < MIN_PROFIT_FACTOR:
        failures.append(f"Profit factor {profit_factor:.2f} < {MIN_PROFIT_FACTOR}")
    if days_since_last > MAX_DAYS_INACTIVE:
        failures.append(
            f"Last trade {days_since_last:.0f} days ago > {MAX_DAYS_INACTIVE} days"
        )
    if distinct_tokens < MIN_DISTINCT_TOKENS:
        failures.append(f"Distinct tokens {distinct_tokens} < {MIN_DISTINCT_TOKENS}")
    if max_single_pnl_pct > MAX_SINGLE_TRADE_PNL_PCT:
        failures.append(
            f"Top trade is {max_single_pnl_pct:.0%} of total PnL > {MAX_SINGLE_TRADE_PNL_PCT:.0%}"
        )
    if bot_prob > MAX_BOT_PROBABILITY:
        failures.append(
            f"Bot probability {bot_prob:.0%} > {MAX_BOT_PROBABILITY:.0%}"
        )

    return WalletEvaluation(
        wallet=wallet,
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_pnl_sol=total_pnl_sol,
        total_pnl_usd=total_pnl_usd,
        distinct_tokens=distinct_tokens,
        days_since_last_trade=days_since_last,
        max_single_trade_pnl_pct=max_single_pnl_pct,
        median_hold_time_hours=median_hold_hours,
        bot_probability=bot_prob,
        consistency_score=consistency,
        composite_score=composite,
        rating=rating,
        passed_all_minimums=len(failures) == 0,
        failures=failures,
    )


# ── Display ─────────────────────────────────────────────────────────
def print_evaluation(ev: WalletEvaluation) -> None:
    """Print formatted evaluation report."""
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  COPY-TRADE WALLET EVALUATION")
    print(f"{sep}")
    print(f"  Wallet:  {ev.wallet}")
    print(f"{sep}\n")

    print("  PERFORMANCE SUMMARY")
    print(f"  {'Total trades:':<30} {ev.total_trades}")
    print(f"  {'Wins / Losses:':<30} {ev.wins} / {ev.losses}")
    print(f"  {'Win rate:':<30} {ev.win_rate:.1%}")
    print(f"  {'Profit factor:':<30} {ev.profit_factor:.2f}")
    print(f"  {'Total PnL (SOL):':<30} {ev.total_pnl_sol:+.4f}")
    print(f"  {'Total PnL (USD):':<30} ${ev.total_pnl_usd:+,.2f}")
    print(f"  {'Distinct tokens:':<30} {ev.distinct_tokens}")
    print(f"  {'Days since last trade:':<30} {ev.days_since_last_trade:.1f}")
    print(f"  {'Median hold time:':<30} {ev.median_hold_time_hours:.1f} hours")
    print(f"  {'Max single-trade PnL %:':<30} {ev.max_single_trade_pnl_pct:.0%}")
    print(f"  {'Bot probability:':<30} {ev.bot_probability:.0%}")
    print()

    print("  SCORING BREAKDOWN")
    tc = score_trade_count(ev.total_trades)
    wr = score_win_rate(ev.win_rate)
    pf = score_profit_factor(ev.profit_factor)
    rec = score_recency(ev.days_since_last_trade)
    hum = score_human_probability(ev.bot_probability)

    print(f"  {'Trade count:':<30} {tc:5.1f} / 100  (weight: {WEIGHT_TRADE_COUNT:.0%})")
    print(f"  {'Win rate:':<30} {wr:5.1f} / 100  (weight: {WEIGHT_WIN_RATE:.0%})")
    print(
        f"  {'Profit factor:':<30} {pf:5.1f} / 100  (weight: {WEIGHT_PROFIT_FACTOR:.0%})"
    )
    print(
        f"  {'Consistency:':<30} {ev.consistency_score:5.1f} / 100  (weight: {WEIGHT_CONSISTENCY:.0%})"
    )
    print(f"  {'Recency:':<30} {rec:5.1f} / 100  (weight: {WEIGHT_RECENCY:.0%})")
    print(
        f"  {'Human probability:':<30} {hum:5.1f} / 100  (weight: {WEIGHT_HUMAN_PROB:.0%})"
    )
    print(f"\n  {'COMPOSITE SCORE:':<30} {ev.composite_score:.1f} / 100")
    print(f"  {'RATING:':<30} {ev.rating}")
    print()

    print("  MINIMUM THRESHOLD CHECK")
    if ev.passed_all_minimums:
        print("  All minimum thresholds PASSED")
    else:
        print("  FAILED minimum thresholds:")
        for f in ev.failures:
            print(f"    - {f}")
    print()

    print(f"  RECOMMENDATION")
    if ev.composite_score >= 80 and ev.passed_all_minimums:
        print("  >>> GO — Strong copy-trade candidate")
        print("  Recommended allocation: standard (full per-wallet budget)")
    elif ev.composite_score >= 60 and len(ev.failures) <= 1:
        print("  >>> CONDITIONAL GO — Suitable with monitoring")
        print("  Recommended allocation: reduced (50-75% of per-wallet budget)")
    elif ev.composite_score >= 40:
        print("  >>> WATCHLIST — Not ready for copy trading")
        print("  Add to watchlist and re-evaluate in 1-2 weeks")
    else:
        print("  >>> NO-GO — Do not copy this wallet")
        print("  Insufficient evidence of replicable edge")
    print(f"\n{sep}\n")


# ── Demo Mode ───────────────────────────────────────────────────────
def generate_demo_trades() -> list[TokenTrade]:
    """Generate realistic example trade data for demonstration."""
    import random

    random.seed(42)
    now = int(time.time())
    trades: list[TokenTrade] = []

    symbols = [
        "BONK", "WIF", "POPCAT", "MEW", "BOME", "MYRO", "WEN", "JUP",
        "PYTH", "JTO", "TNSR", "KMNO", "DRIFT", "RENDER", "HNT",
        "MOBILE", "HONEY", "MNDE", "STEP", "RAY", "ORCA", "SRM",
        "FIDA", "ATLAS", "POLIS", "SAMO", "COPE", "MEDIA", "TULIP",
    ]

    for i, symbol in enumerate(symbols):
        # Simulate a mix of wins and losses (roughly 60% win rate)
        is_win = random.random() < 0.60
        bought = round(random.uniform(0.5, 5.0), 2)
        if is_win:
            pnl = round(random.uniform(0.1, 3.0), 4)
        else:
            pnl = round(-random.uniform(0.1, bought * 0.8), 4)
        sold = bought + pnl

        # Random timestamps within last 30 days
        first_ts = now - random.randint(86400, 30 * 86400)
        hold_seconds = random.randint(300, 3 * 86400)  # 5 min to 3 days
        last_ts = first_ts + hold_seconds

        trades.append(
            TokenTrade(
                token_address=f"TokenMint{i:04d}{'x' * 36}"[:44],
                token_symbol=symbol,
                pnl_sol=pnl,
                pnl_usd=pnl * 150.0,  # Approximate SOL price
                bought_sol=bought,
                sold_sol=max(sold, 0),
                num_buys=random.randint(1, 3),
                num_sells=random.randint(1, 2),
                first_trade_ts=first_ts,
                last_trade_ts=last_ts,
            )
        )

    # Add some extra trades for the same tokens to increase count
    for _ in range(40):
        base = random.choice(trades)
        is_win = random.random() < 0.58
        bought = round(random.uniform(0.3, 3.0), 2)
        pnl = round(random.uniform(0.05, 1.5) if is_win else -random.uniform(0.05, bought * 0.7), 4)
        first_ts = now - random.randint(86400, 25 * 86400)
        hold_seconds = random.randint(600, 2 * 86400)

        trades.append(
            TokenTrade(
                token_address=f"TokenMint{len(trades):04d}{'x' * 36}"[:44],
                token_symbol=f"TKN{len(trades)}",
                pnl_sol=pnl,
                pnl_usd=pnl * 150.0,
                bought_sol=bought,
                sold_sol=max(bought + pnl, 0),
                num_buys=1,
                num_sells=1,
                first_trade_ts=first_ts,
                last_trade_ts=first_ts + hold_seconds,
            )
        )

    return trades


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Main entry point."""
    args = sys.argv[1:]
    demo_mode = "--demo" in args

    if demo_mode:
        print("[DEMO MODE] Using generated example trade data\n")
        wallet = "DemoWa11etXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        trades = generate_demo_trades()
        evaluation = evaluate_wallet(wallet, trades)
        print_evaluation(evaluation)
        return

    # Determine wallet address
    wallet = None
    for arg in args:
        if not arg.startswith("-"):
            wallet = arg
            break
    if not wallet:
        wallet = os.getenv("WALLET_ADDRESS", "")
    if not wallet:
        print("Usage: python scripts/evaluate_wallet.py <wallet_address>")
        print("       python scripts/evaluate_wallet.py --demo")
        print("Or set WALLET_ADDRESS environment variable.")
        sys.exit(1)

    print(f"Evaluating wallet: {wallet}")
    print("Fetching PnL data from SolanaTracker...\n")

    try:
        pnl_data = fetch_wallet_pnl(wallet)
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code} — {e.response.text[:200]}")
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        sys.exit(1)

    trades = parse_trades(pnl_data)
    if not trades:
        print("No trade data found for this wallet.")
        sys.exit(1)

    print(f"Found {len(trades)} token trades. Evaluating...\n")
    evaluation = evaluate_wallet(wallet, trades)
    print_evaluation(evaluation)


if __name__ == "__main__":
    main()
