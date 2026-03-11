#!/usr/bin/env python3
"""Trade journal analyzer — behavioral pattern detection and performance analysis.

Reads a trade journal (JSON) and produces a comprehensive analysis report
including strategy performance, time-based patterns, behavioral red flags,
and actionable recommendations.

Usage:
    python scripts/journal_analyzer.py --demo
    python scripts/journal_analyzer.py --journal trade_journal.json
    python scripts/journal_analyzer.py --journal trade_journal.json --strategy momentum-breakout

Dependencies:
    None — uses Python standard library only (json, datetime, collections)

Environment Variables:
    TRADE_JOURNAL_PATH: Path to journal JSON file (default: trade_journal.json)
"""

import argparse
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────

JOURNAL_PATH = os.getenv("TRADE_JOURNAL_PATH", "trade_journal.json")

REVENGE_MAX_GAP_MINUTES = 15
TILT_SIZE_THRESHOLD = 1.5
MIN_SAMPLE_SIZE = 5
DECAY_WINDOW = 20


# ── Data Loading ────────────────────────────────────────────────────

def load_journal(path: str) -> dict:
    """Load journal from JSON file.

    Args:
        path: Path to the journal JSON file.

    Returns:
        Parsed journal dictionary.

    Raises:
        FileNotFoundError: If journal file does not exist.
        json.JSONDecodeError: If file contains invalid JSON.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Journal not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_closed_trades(journal: dict) -> list[dict]:
    """Extract closed trades (those with an outcome) sorted by entry date.

    Args:
        journal: Journal dictionary.

    Returns:
        List of closed trade records sorted chronologically.
    """
    closed = [t for t in journal.get("trades", []) if t.get("outcome") is not None]
    return sorted(closed, key=lambda t: t.get("entry_date", ""))


# ── Performance Analysis ───────────────────────────────────────────

def performance_by_strategy(trades: list[dict]) -> dict[str, dict]:
    """Compute performance metrics grouped by strategy.

    Args:
        trades: List of closed trade records.

    Returns:
        Dictionary mapping strategy name to performance metrics.
    """
    by_strat: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_strat[t.get("strategy", "unknown")].append(t)

    results: dict[str, dict] = {}
    for strat, strat_trades in sorted(by_strat.items()):
        total = len(strat_trades)
        wins = sum(1 for t in strat_trades if t["outcome"] == "win")
        pnl_values = [t.get("pnl_sol", 0) for t in strat_trades if t.get("pnl_sol") is not None]
        gross_wins = sum(v for v in pnl_values if v > 0)
        gross_losses = sum(abs(v) for v in pnl_values if v < 0)
        pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")

        results[strat] = {
            "trades": total,
            "win_rate": wins / total if total > 0 else 0,
            "total_pnl_sol": sum(pnl_values),
            "profit_factor": pf,
            "avg_pnl_sol": sum(pnl_values) / total if total > 0 else 0,
        }
    return results


def performance_by_day_of_week(trades: list[dict]) -> dict[str, dict]:
    """Compute performance metrics grouped by day of week.

    Args:
        trades: List of closed trade records.

    Returns:
        Dictionary mapping day name to performance metrics.
    """
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day: dict[str, list[dict]] = defaultdict(list)

    for t in trades:
        entry = t.get("entry_date", "")
        if not entry:
            continue
        try:
            dt = datetime.fromisoformat(entry.replace("Z", "+00:00"))
            day_name = days[dt.weekday()]
            by_day[day_name].append(t)
        except (ValueError, IndexError):
            continue

    results: dict[str, dict] = {}
    for day in days:
        day_trades = by_day.get(day, [])
        if not day_trades:
            continue
        total = len(day_trades)
        wins = sum(1 for t in day_trades if t["outcome"] == "win")
        pnl = sum(t.get("pnl_sol", 0) for t in day_trades if t.get("pnl_sol") is not None)
        results[day] = {
            "trades": total,
            "win_rate": wins / total if total > 0 else 0,
            "total_pnl_sol": pnl,
        }
    return results


def performance_by_hold_time(trades: list[dict]) -> dict[str, dict]:
    """Compute performance grouped by hold time buckets.

    Args:
        trades: List of closed trade records.

    Returns:
        Dictionary mapping hold time bucket to performance metrics.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)

    for t in trades:
        hold = t.get("hold_time_minutes")
        if hold is None:
            continue
        if hold < 30:
            bucket = "< 30 min"
        elif hold < 60:
            bucket = "30-60 min"
        elif hold < 180:
            bucket = "1-3 hours"
        elif hold < 480:
            bucket = "3-8 hours"
        else:
            bucket = "8+ hours"
        buckets[bucket].append(t)

    results: dict[str, dict] = {}
    for bucket in ["< 30 min", "30-60 min", "1-3 hours", "3-8 hours", "8+ hours"]:
        bt = buckets.get(bucket, [])
        if not bt:
            continue
        total = len(bt)
        wins = sum(1 for t in bt if t["outcome"] == "win")
        pnl = sum(t.get("pnl_sol", 0) for t in bt if t.get("pnl_sol") is not None)
        results[bucket] = {
            "trades": total,
            "win_rate": wins / total if total > 0 else 0,
            "total_pnl_sol": pnl,
        }
    return results


# ── Behavioral Pattern Detection ───────────────────────────────────

def detect_revenge_trades(trades: list[dict], max_gap_minutes: int = REVENGE_MAX_GAP_MINUTES) -> list[dict]:
    """Detect revenge trades — entries shortly after a loss.

    Args:
        trades: Chronologically sorted list of closed trade records.
        max_gap_minutes: Maximum minutes between loss exit and next entry to flag.

    Returns:
        List of trades flagged as potential revenge trades.
    """
    revenge: list[dict] = []
    for i in range(1, len(trades)):
        prev, curr = trades[i - 1], trades[i]
        if prev.get("outcome") != "loss":
            continue
        prev_exit = prev.get("exit_date", "")
        curr_entry = curr.get("entry_date", "")
        if not prev_exit or not curr_entry:
            continue
        try:
            prev_dt = datetime.fromisoformat(prev_exit.replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(curr_entry.replace("Z", "+00:00"))
            gap = (curr_dt - prev_dt).total_seconds() / 60
            if gap <= max_gap_minutes:
                revenge.append({
                    "trade": curr,
                    "gap_minutes": round(gap, 1),
                    "preceding_loss_id": prev["id"],
                })
        except ValueError:
            continue
    return revenge


def detect_tilt_trades(trades: list[dict], threshold: float = TILT_SIZE_THRESHOLD) -> list[dict]:
    """Detect tilt — size escalation after losses.

    Args:
        trades: Chronologically sorted list of trade records.
        threshold: Size increase multiplier that triggers a flag.

    Returns:
        List of trades flagged as potential tilt.
    """
    tilt: list[dict] = []
    for i in range(1, len(trades)):
        prev, curr = trades[i - 1], trades[i]
        if prev.get("outcome") != "loss":
            continue
        prev_size = prev.get("size_sol", 0)
        curr_size = curr.get("size_sol", 0)
        if prev_size > 0 and curr_size > prev_size * threshold:
            tilt.append({
                "trade": curr,
                "size_increase": round(curr_size / prev_size, 2),
                "preceding_loss_id": prev["id"],
            })
    return tilt


def detect_loss_streaks(trades: list[dict]) -> list[dict]:
    """Detect consecutive loss streaks.

    Args:
        trades: Chronologically sorted list of trade records.

    Returns:
        List of streak records with start, end, and length.
    """
    streaks: list[dict] = []
    current_start: Optional[int] = None
    current_length = 0

    for i, t in enumerate(trades):
        if t.get("outcome") == "loss":
            if current_start is None:
                current_start = i
            current_length += 1
        else:
            if current_length >= 3:
                streaks.append({
                    "start_trade": trades[current_start]["id"],
                    "end_trade": trades[i - 1]["id"],
                    "length": current_length,
                    "total_loss_sol": sum(
                        abs(trades[j].get("pnl_sol", 0))
                        for j in range(current_start, i)
                    ),
                })
            current_start = None
            current_length = 0

    # Handle streak at end
    if current_length >= 3 and current_start is not None:
        streaks.append({
            "start_trade": trades[current_start]["id"],
            "end_trade": trades[-1]["id"],
            "length": current_length,
            "total_loss_sol": sum(
                abs(trades[j].get("pnl_sol", 0))
                for j in range(current_start, len(trades))
            ),
        })

    return streaks


def winner_loser_hold_comparison(trades: list[dict]) -> dict[str, float]:
    """Compare average hold times for winners vs losers.

    Args:
        trades: List of closed trade records.

    Returns:
        Dictionary with average hold times and a cutting_winners flag.
    """
    win_holds = [
        t["hold_time_minutes"] for t in trades
        if t.get("outcome") == "win" and t.get("hold_time_minutes") is not None
    ]
    loss_holds = [
        t["hold_time_minutes"] for t in trades
        if t.get("outcome") == "loss" and t.get("hold_time_minutes") is not None
    ]

    avg_win = sum(win_holds) / len(win_holds) if win_holds else 0
    avg_loss = sum(loss_holds) / len(loss_holds) if loss_holds else 0

    cutting_winners = avg_loss > 0 and avg_win > 0 and (avg_win / avg_loss < 0.7)

    return {
        "avg_win_hold_min": round(avg_win, 1),
        "avg_loss_hold_min": round(avg_loss, 1),
        "ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0,
        "cutting_winners": cutting_winners,
    }


def setup_quality_analysis(trades: list[dict]) -> dict:
    """Analyze whether setup quality scores predict outcomes.

    Args:
        trades: List of closed trade records with setup_quality.

    Returns:
        Comparison of quality scores for wins vs losses.
    """
    with_quality = [t for t in trades if t.get("setup_quality") is not None]
    if len(with_quality) < MIN_SAMPLE_SIZE:
        return {"status": "insufficient_data"}

    win_quality = [t["setup_quality"] for t in with_quality if t["outcome"] == "win"]
    loss_quality = [t["setup_quality"] for t in with_quality if t["outcome"] == "loss"]

    avg_win_q = sum(win_quality) / len(win_quality) if win_quality else 0
    avg_loss_q = sum(loss_quality) / len(loss_quality) if loss_quality else 0

    # High quality (>= 7) vs low quality (< 7) win rates
    high_q = [t for t in with_quality if t["setup_quality"] >= 7]
    low_q = [t for t in with_quality if t["setup_quality"] < 7]
    high_wr = sum(1 for t in high_q if t["outcome"] == "win") / len(high_q) if high_q else 0
    low_wr = sum(1 for t in low_q if t["outcome"] == "win") / len(low_q) if low_q else 0

    return {
        "avg_quality_winners": round(avg_win_q, 1),
        "avg_quality_losers": round(avg_loss_q, 1),
        "high_quality_win_rate": round(high_wr, 3),
        "low_quality_win_rate": round(low_wr, 3),
        "quality_is_predictive": high_wr > low_wr + 0.1,
    }


# ── Report Generation ──────────────────────────────────────────────

def generate_recommendations(
    trades: list[dict],
    revenge: list[dict],
    tilt: list[dict],
    hold_comp: dict,
    quality: dict,
    strat_perf: dict[str, dict],
) -> list[str]:
    """Generate actionable recommendations from analysis.

    Args:
        trades: All closed trades.
        revenge: Detected revenge trades.
        tilt: Detected tilt trades.
        hold_comp: Hold time comparison results.
        quality: Setup quality analysis results.
        strat_perf: Strategy performance results.

    Returns:
        List of recommendation strings.
    """
    recs: list[str] = []

    if revenge:
        recs.append(
            f"BEHAVIORAL: {len(revenge)} revenge trade(s) detected. "
            "Implement a mandatory 30-minute cooldown after any loss."
        )

    if tilt:
        recs.append(
            f"BEHAVIORAL: {len(tilt)} tilt trade(s) detected (size escalation after loss). "
            "Lock position sizing to prevent emotional increases."
        )

    if hold_comp.get("cutting_winners"):
        recs.append(
            f"EXECUTION: Cutting winners — avg win hold ({hold_comp['avg_win_hold_min']} min) "
            f"is much shorter than avg loss hold ({hold_comp['avg_loss_hold_min']} min). "
            "Consider trailing stops to let winners run."
        )

    if quality.get("quality_is_predictive"):
        recs.append(
            f"EDGE: Setup quality IS predictive — high quality win rate "
            f"({quality['high_quality_win_rate']:.0%}) vs low quality "
            f"({quality['low_quality_win_rate']:.0%}). "
            "Only take setups rated 7+."
        )

    # Flag losing strategies
    for strat, perf in strat_perf.items():
        if perf["trades"] >= MIN_SAMPLE_SIZE and perf["profit_factor"] < 1.0:
            recs.append(
                f"STRATEGY: '{strat}' has negative expectancy "
                f"(PF={perf['profit_factor']:.2f}, {perf['trades']} trades). "
                "Consider pausing this strategy."
            )

    # Flag emotional strategies
    for strat in ["gut-feel", "fomo", "revenge"]:
        if strat in strat_perf:
            recs.append(
                f"STRATEGY: '{strat}' trades should be eliminated. "
                f"P&L: {strat_perf[strat]['total_pnl_sol']:+.4f} SOL "
                f"over {strat_perf[strat]['trades']} trades."
            )

    if not recs:
        recs.append("No critical issues detected. Continue logging and review next week.")

    return recs


def print_report(
    trades: list[dict],
    strat_perf: dict[str, dict],
    day_perf: dict[str, dict],
    hold_perf: dict[str, dict],
    revenge: list[dict],
    tilt: list[dict],
    streaks: list[dict],
    hold_comp: dict,
    quality: dict,
    recs: list[str],
) -> None:
    """Print the full analysis report.

    Args:
        trades: All closed trades.
        strat_perf: Strategy performance data.
        day_perf: Day-of-week performance data.
        hold_perf: Hold-time bucket performance data.
        revenge: Revenge trade detections.
        tilt: Tilt trade detections.
        streaks: Loss streak records.
        hold_comp: Hold time comparison.
        quality: Setup quality analysis.
        recs: Recommendations list.
    """
    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "win")
    pnl = sum(t.get("pnl_sol", 0) for t in trades if t.get("pnl_sol") is not None)

    print("\n" + "=" * 60)
    print("  TRADE JOURNAL ANALYSIS REPORT")
    print("=" * 60)

    # Overview
    print(f"\n  Trades Analyzed: {total}")
    print(f"  Win Rate:        {wins / total:.1%}" if total > 0 else "  Win Rate: N/A")
    print(f"  Net P&L:         {pnl:+.4f} SOL")

    # Strategy performance
    print(f"\n{'─' * 60}")
    print("  PERFORMANCE BY STRATEGY")
    print(f"{'─' * 60}")
    print(f"  {'Strategy':<25} {'Trades':>7} {'WR':>7} {'P&L SOL':>10} {'PF':>7}")
    print(f"  {'-' * 56}")
    for strat, perf in sorted(strat_perf.items(), key=lambda x: x[1]["total_pnl_sol"], reverse=True):
        pf_str = f"{perf['profit_factor']:.2f}" if perf['profit_factor'] < 1000 else "inf"
        print(
            f"  {strat:<25} {perf['trades']:>7} "
            f"{perf['win_rate']:>6.0%} {perf['total_pnl_sol']:>+10.4f} {pf_str:>7}"
        )

    # Day of week
    print(f"\n{'─' * 60}")
    print("  PERFORMANCE BY DAY OF WEEK")
    print(f"{'─' * 60}")
    print(f"  {'Day':<15} {'Trades':>7} {'WR':>7} {'P&L SOL':>10}")
    print(f"  {'-' * 39}")
    for day, perf in day_perf.items():
        print(f"  {day:<15} {perf['trades']:>7} {perf['win_rate']:>6.0%} {perf['total_pnl_sol']:>+10.4f}")

    # Hold time buckets
    print(f"\n{'─' * 60}")
    print("  PERFORMANCE BY HOLD TIME")
    print(f"{'─' * 60}")
    print(f"  {'Bucket':<15} {'Trades':>7} {'WR':>7} {'P&L SOL':>10}")
    print(f"  {'-' * 39}")
    for bucket, perf in hold_perf.items():
        print(f"  {bucket:<15} {perf['trades']:>7} {perf['win_rate']:>6.0%} {perf['total_pnl_sol']:>+10.4f}")

    # Behavioral patterns
    print(f"\n{'─' * 60}")
    print("  BEHAVIORAL PATTERNS")
    print(f"{'─' * 60}")

    print(f"\n  Revenge Trades: {len(revenge)}")
    for r in revenge:
        t = r["trade"]
        print(f"    - {t['id']}: entered {r['gap_minutes']} min after loss {r['preceding_loss_id']}, "
              f"outcome: {t['outcome']}")

    print(f"\n  Tilt Trades (size escalation after loss): {len(tilt)}")
    for ti in tilt:
        t = ti["trade"]
        print(f"    - {t['id']}: size {ti['size_increase']}x previous, outcome: {t['outcome']}")

    print(f"\n  Loss Streaks (3+): {len(streaks)}")
    for s in streaks:
        print(f"    - {s['start_trade']} to {s['end_trade']}: {s['length']} consecutive losses, "
              f"total: {s['total_loss_sol']:.4f} SOL lost")

    # Hold time comparison
    print(f"\n  Winner vs Loser Hold Times:")
    print(f"    Avg win hold:  {hold_comp['avg_win_hold_min']:.0f} min")
    print(f"    Avg loss hold: {hold_comp['avg_loss_hold_min']:.0f} min")
    print(f"    Ratio:         {hold_comp['ratio']:.2f}")
    if hold_comp["cutting_winners"]:
        print("    WARNING: You appear to be cutting winners short.")

    # Setup quality
    if quality.get("status") != "insufficient_data":
        print(f"\n  Setup Quality Analysis:")
        print(f"    Avg quality (winners): {quality['avg_quality_winners']}")
        print(f"    Avg quality (losers):  {quality['avg_quality_losers']}")
        print(f"    High quality WR:       {quality['high_quality_win_rate']:.0%}")
        print(f"    Low quality WR:        {quality['low_quality_win_rate']:.0%}")
        pred = "YES" if quality.get("quality_is_predictive") else "NO"
        print(f"    Quality is predictive: {pred}")

    # Recommendations
    print(f"\n{'─' * 60}")
    print("  RECOMMENDATIONS")
    print(f"{'─' * 60}")
    for i, rec in enumerate(recs, 1):
        print(f"  {i}. {rec}")

    print(f"\n{'=' * 60}")
    print("  This report is informational only — not financial advice.")
    print(f"{'=' * 60}\n")


# ── Demo Mode ──────────────────────────────────────────────────────

def generate_demo_trades(n: int = 50) -> dict:
    """Generate synthetic trade journal data for demo purposes.

    Creates realistic-looking trades across multiple strategies,
    tokens, and time periods with intentional behavioral patterns.

    Args:
        n: Number of trades to generate.

    Returns:
        Journal dictionary with synthetic trades.
    """
    random.seed(42)  # Reproducible output

    strategies = [
        ("momentum-breakout", 0.60),
        ("pullback-entry", 0.55),
        ("oversold-bounce", 0.50),
        ("whale-follow", 0.55),
        ("trend-continuation", 0.58),
        ("volume-spike", 0.45),
        ("gut-feel", 0.30),
        ("fomo", 0.25),
    ]
    tokens = ["SOL", "BONK", "JUP", "WIF", "RAY", "ORCA", "PYTH"]
    emotions = ["calm", "calm", "calm", "excited", "anxious", "frustrated", "fomo", "revenge"]

    journal: dict = {
        "journal_version": "1.0",
        "trader_id": "demo",
        "created": "2025-02-01T00:00:00+00:00",
        "updated": "2025-03-10T00:00:00+00:00",
        "trades": [],
    }

    base_date = datetime(2025, 2, 1, 9, 0, 0, tzinfo=timezone.utc)
    prev_outcome: Optional[str] = None
    prev_exit_dt: Optional[datetime] = None

    for i in range(n):
        # Pick strategy — bias toward gut-feel/fomo after losses
        if prev_outcome == "loss" and random.random() < 0.25:
            strat_name = random.choice(["gut-feel", "fomo", "revenge"])
            strat_wr = dict(strategies).get(strat_name, 0.3)
        else:
            strat_name, strat_wr = random.choice(strategies)

        token = random.choice(tokens)
        direction = "long"

        # Entry timing — sometimes revenge-quick after loss
        if prev_outcome == "loss" and prev_exit_dt and random.random() < 0.2:
            entry_dt = prev_exit_dt + timedelta(minutes=random.randint(3, 12))
        else:
            entry_dt = base_date + timedelta(
                days=i // 3,
                hours=random.randint(0, 8),
                minutes=random.randint(0, 59),
            )

        # Price and size
        if token == "SOL":
            entry_price = round(random.uniform(130, 160), 2)
        elif token == "BONK":
            entry_price = round(random.uniform(0.000015, 0.000030), 8)
        elif token == "JUP":
            entry_price = round(random.uniform(0.70, 1.10), 4)
        elif token == "WIF":
            entry_price = round(random.uniform(1.50, 3.00), 4)
        else:
            entry_price = round(random.uniform(2.0, 8.0), 4)

        base_size = round(random.uniform(2, 10), 1)
        # Tilt: increase size after loss
        if prev_outcome == "loss" and random.random() < 0.2:
            base_size = round(base_size * random.uniform(1.6, 2.5), 1)

        # Outcome based on strategy win rate
        is_win = random.random() < strat_wr
        outcome = "win" if is_win else "loss"

        # P&L
        if is_win:
            pnl_pct = round(random.uniform(0.5, 8.0), 2)
        else:
            pnl_pct = round(-random.uniform(0.3, 5.0), 2)

        if direction == "long":
            exit_price = round(entry_price * (1 + pnl_pct / 100), 8)
        else:
            exit_price = round(entry_price * (1 - pnl_pct / 100), 8)

        pnl_sol = round(base_size * pnl_pct / 100, 6)
        hold_minutes = random.randint(10, 480)
        # Winners held shorter if cutting (intentional pattern)
        if is_win and random.random() < 0.4:
            hold_minutes = random.randint(10, 60)

        exit_dt = entry_dt + timedelta(minutes=hold_minutes)

        quality = random.randint(1, 10)
        if strat_name in ("gut-feel", "fomo"):
            quality = random.randint(1, 4)
        elif strat_name in ("momentum-breakout", "pullback-entry"):
            quality = random.randint(5, 10)

        emotion = "calm"
        if strat_name == "fomo":
            emotion = "fomo"
        elif strat_name == "revenge":
            emotion = "revenge"
        elif prev_outcome == "loss":
            emotion = random.choice(["calm", "frustrated", "anxious"])
        else:
            emotion = random.choice(["calm", "calm", "excited"])

        trade: dict = {
            "id": f"T-{entry_dt.strftime('%Y%m%d')}-{(i % 10) + 1:03d}",
            "token": token,
            "direction": direction,
            "entry_date": entry_dt.isoformat(),
            "entry_price": entry_price,
            "size_sol": base_size,
            "strategy": strat_name,
            "rationale": f"Demo trade {i + 1} — {strat_name} setup on {token}",
            "exit_date": exit_dt.isoformat(),
            "exit_price": exit_price,
            "pnl_sol": pnl_sol,
            "pnl_pct": pnl_pct,
            "outcome": outcome,
            "hold_time_minutes": hold_minutes,
            "setup_quality": quality,
            "emotional_state": emotion,
            "lessons": None,
        }
        journal["trades"].append(trade)

        prev_outcome = outcome
        prev_exit_dt = exit_dt

    return journal


def run_demo() -> None:
    """Run full analysis on 50 synthetic demo trades."""
    print("=" * 60)
    print("  Journal Analyzer — Demo Mode (50 synthetic trades)")
    print("=" * 60)

    journal = generate_demo_trades(50)
    trades = get_closed_trades(journal)
    run_analysis(trades)


# ── Analysis Runner ─────────────────────────────────────────────────

def run_analysis(trades: list[dict], strategy_filter: Optional[str] = None) -> None:
    """Run full analysis pipeline and print report.

    Args:
        trades: List of closed trade records.
        strategy_filter: Optional strategy to filter by.
    """
    if strategy_filter:
        trades = [t for t in trades if t.get("strategy") == strategy_filter]

    if not trades:
        print("No trades to analyze.")
        return

    strat_perf = performance_by_strategy(trades)
    day_perf = performance_by_day_of_week(trades)
    hold_perf = performance_by_hold_time(trades)
    revenge = detect_revenge_trades(trades)
    tilt = detect_tilt_trades(trades)
    streaks = detect_loss_streaks(trades)
    hold_comp = winner_loser_hold_comparison(trades)
    quality = setup_quality_analysis(trades)
    recs = generate_recommendations(trades, revenge, tilt, hold_comp, quality, strat_perf)

    print_report(
        trades, strat_perf, day_perf, hold_perf,
        revenge, tilt, streaks, hold_comp, quality, recs,
    )


# ── CLI ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for the journal analyzer CLI."""
    parser = argparse.ArgumentParser(
        description="Trade Journal Analyzer — behavioral patterns and performance analysis",
    )
    parser.add_argument("--demo", action="store_true", help="Run demo with synthetic trades")
    parser.add_argument("--journal", default=JOURNAL_PATH, help="Path to journal file")
    parser.add_argument("--strategy", help="Filter analysis to a single strategy")

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    try:
        journal = load_journal(args.journal)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Use --demo to run with synthetic data, or specify --journal path.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in journal file — {e}")
        sys.exit(1)

    trades = get_closed_trades(journal)
    run_analysis(trades, strategy_filter=args.strategy)


if __name__ == "__main__":
    main()
