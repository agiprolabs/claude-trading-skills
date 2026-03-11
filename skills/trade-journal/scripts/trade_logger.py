#!/usr/bin/env python3
"""Trade journal logger — add, list, update, and analyze trades.

A command-line trade journal that stores records in JSON format.
Supports adding trades, listing with filters, updating fields,
computing running statistics, and a demo mode with example data.

Usage:
    python scripts/trade_logger.py --demo
    python scripts/trade_logger.py add --token SOL --direction long --entry-price 142.5 --size 5.0 --strategy momentum-breakout --rationale "Breaking 4h resistance"
    python scripts/trade_logger.py list --strategy momentum-breakout --outcome win
    python scripts/trade_logger.py update T-20250310-001 --exit-price 146.2 --outcome win --lessons "Patience paid off"
    python scripts/trade_logger.py stats
    python scripts/trade_logger.py stats --strategy momentum-breakout

Dependencies:
    None — uses Python standard library only (json, datetime, argparse)

Environment Variables:
    TRADE_JOURNAL_PATH: Path to journal JSON file (default: trade_journal.json)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional


# ── Configuration ───────────────────────────────────────────────────

JOURNAL_PATH = os.getenv("TRADE_JOURNAL_PATH", "trade_journal.json")

VALID_DIRECTIONS = {"long", "short"}
VALID_OUTCOMES = {"win", "loss", "breakeven"}
VALID_EMOTIONS = {"calm", "anxious", "excited", "frustrated", "fomo", "revenge"}

JOURNAL_TEMPLATE: dict = {
    "journal_version": "1.0",
    "trader_id": "anon",
    "created": "",
    "updated": "",
    "trades": [],
}


# ── Journal I/O ─────────────────────────────────────────────────────

def load_journal(path: str) -> dict:
    """Load journal from JSON file, creating a new one if it doesn't exist.

    Args:
        path: Path to the journal JSON file.

    Returns:
        Parsed journal dictionary.
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    now = datetime.now(timezone.utc).isoformat()
    journal = {**JOURNAL_TEMPLATE, "created": now, "updated": now}
    return journal


def save_journal(journal: dict, path: str) -> None:
    """Save journal to JSON file.

    Args:
        journal: Journal dictionary to save.
        path: Output file path.
    """
    journal["updated"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False)
    print(f"Journal saved to {path}")


# ── Trade ID Generation ────────────────────────────────────────────

def generate_trade_id(journal: dict) -> str:
    """Generate the next sequential trade ID for today.

    Args:
        journal: Current journal dictionary.

    Returns:
        Trade ID in format T-YYYYMMDD-NNN.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"T-{today}-"
    existing = [
        t["id"] for t in journal["trades"]
        if t["id"].startswith(prefix)
    ]
    next_num = len(existing) + 1
    return f"{prefix}{next_num:03d}"


# ── Trade Operations ───────────────────────────────────────────────

def add_trade(
    journal: dict,
    token: str,
    direction: str,
    entry_price: float,
    size_sol: float,
    strategy: str,
    rationale: str,
    setup_quality: Optional[int] = None,
    emotional_state: Optional[str] = None,
    stop_price: Optional[float] = None,
    target_price: Optional[float] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Add a new trade to the journal.

    Args:
        journal: Journal dictionary.
        token: Token symbol (e.g., SOL, BONK).
        direction: Trade direction — long or short.
        entry_price: Entry price.
        size_sol: Position size in SOL.
        strategy: Strategy tag from taxonomy.
        rationale: Written reason for the trade.
        setup_quality: Self-rated 1-10 quality score.
        emotional_state: Emotional state at entry.
        stop_price: Planned stop-loss price.
        target_price: Planned take-profit price.
        tags: Freeform tags for filtering.

    Returns:
        The created trade record.

    Raises:
        ValueError: If direction or emotional_state is invalid.
    """
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of {VALID_DIRECTIONS}")
    if emotional_state and emotional_state not in VALID_EMOTIONS:
        raise ValueError(f"emotional_state must be one of {VALID_EMOTIONS}")
    if setup_quality is not None and not (1 <= setup_quality <= 10):
        raise ValueError("setup_quality must be between 1 and 10")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if size_sol <= 0:
        raise ValueError("size_sol must be positive")

    trade: dict = {
        "id": generate_trade_id(journal),
        "token": token.upper(),
        "direction": direction,
        "entry_date": datetime.now(timezone.utc).isoformat(),
        "entry_price": entry_price,
        "size_sol": size_sol,
        "strategy": strategy,
        "rationale": rationale,
        "exit_date": None,
        "exit_price": None,
        "pnl_sol": None,
        "pnl_pct": None,
        "outcome": None,
        "hold_time_minutes": None,
        "lessons": None,
    }

    if setup_quality is not None:
        trade["setup_quality"] = setup_quality
    if emotional_state:
        trade["emotional_state"] = emotional_state
    if stop_price is not None:
        trade["stop_price"] = stop_price
    if target_price is not None:
        trade["target_price"] = target_price
    if tags:
        trade["tags"] = tags

    journal["trades"].append(trade)
    print(f"Added trade {trade['id']}: {direction} {size_sol} SOL of {token} at {entry_price}")
    return trade


def update_trade(
    journal: dict,
    trade_id: str,
    exit_price: Optional[float] = None,
    outcome: Optional[str] = None,
    lessons: Optional[str] = None,
    emotional_state: Optional[str] = None,
) -> Optional[dict]:
    """Update an existing trade with exit information.

    Args:
        journal: Journal dictionary.
        trade_id: ID of the trade to update.
        exit_price: Exit price.
        outcome: Trade outcome — win, loss, or breakeven.
        lessons: Post-trade reflection.
        emotional_state: Emotional state (can be updated post-trade).

    Returns:
        Updated trade record, or None if not found.
    """
    trade = next((t for t in journal["trades"] if t["id"] == trade_id), None)
    if trade is None:
        print(f"Trade {trade_id} not found")
        return None

    if exit_price is not None:
        trade["exit_price"] = exit_price
        trade["exit_date"] = datetime.now(timezone.utc).isoformat()

        # Compute P&L
        if trade["direction"] == "long":
            pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"] * 100
        else:
            pnl_pct = (trade["entry_price"] - exit_price) / trade["entry_price"] * 100
        trade["pnl_pct"] = round(pnl_pct, 4)
        trade["pnl_sol"] = round(trade["size_sol"] * pnl_pct / 100, 6)

        # Compute hold time
        entry_dt = datetime.fromisoformat(trade["entry_date"].replace("Z", "+00:00"))
        exit_dt = datetime.fromisoformat(trade["exit_date"].replace("Z", "+00:00"))
        trade["hold_time_minutes"] = int((exit_dt - entry_dt).total_seconds() / 60)

    if outcome is not None:
        if outcome not in VALID_OUTCOMES:
            print(f"Invalid outcome '{outcome}'. Must be one of {VALID_OUTCOMES}")
            return trade
        trade["outcome"] = outcome

    if lessons is not None:
        trade["lessons"] = lessons

    if emotional_state is not None:
        if emotional_state not in VALID_EMOTIONS:
            print(f"Invalid emotional_state. Must be one of {VALID_EMOTIONS}")
            return trade
        trade["emotional_state"] = emotional_state

    print(f"Updated trade {trade_id}")
    return trade


# ── Filtering ──────────────────────────────────────────────────────

def filter_trades(
    trades: list[dict],
    strategy: Optional[str] = None,
    outcome: Optional[str] = None,
    token: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Filter trades by various criteria.

    Args:
        trades: List of trade records.
        strategy: Filter by strategy tag.
        outcome: Filter by outcome.
        token: Filter by token symbol.
        date_from: ISO date string for start of range.
        date_to: ISO date string for end of range.

    Returns:
        Filtered list of trades.
    """
    result = trades
    if strategy:
        result = [t for t in result if t.get("strategy") == strategy]
    if outcome:
        result = [t for t in result if t.get("outcome") == outcome]
    if token:
        result = [t for t in result if t.get("token", "").upper() == token.upper()]
    if date_from:
        result = [t for t in result if t.get("entry_date", "") >= date_from]
    if date_to:
        result = [t for t in result if t.get("entry_date", "") <= date_to]
    return result


# ── Statistics ─────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> dict:
    """Compute trading statistics from a list of completed trades.

    Args:
        trades: List of trade records (only closed trades are analyzed).

    Returns:
        Dictionary of computed statistics.
    """
    closed = [t for t in trades if t.get("outcome") is not None]
    if not closed:
        return {"status": "no_closed_trades"}

    wins = [t for t in closed if t["outcome"] == "win"]
    losses = [t for t in closed if t["outcome"] == "loss"]
    breakevens = [t for t in closed if t["outcome"] == "breakeven"]

    total = len(closed)
    win_count = len(wins)
    loss_count = len(losses)

    # P&L stats
    pnl_values = [t.get("pnl_sol", 0) for t in closed if t.get("pnl_sol") is not None]
    total_pnl = sum(pnl_values)
    gross_wins = sum(t.get("pnl_sol", 0) for t in wins if t.get("pnl_sol") is not None)
    gross_losses = sum(abs(t.get("pnl_sol", 0)) for t in losses if t.get("pnl_sol") is not None)
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    avg_win = gross_wins / win_count if win_count > 0 else 0
    avg_loss = gross_losses / loss_count if loss_count > 0 else 0

    # Win rate
    win_rate = win_count / total if total > 0 else 0

    # Expectancy
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # Hold time
    hold_times = [t["hold_time_minutes"] for t in closed if t.get("hold_time_minutes") is not None]
    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0

    # Consecutive losses
    max_consec_losses = 0
    current_streak = 0
    for t in closed:
        if t["outcome"] == "loss":
            current_streak += 1
            max_consec_losses = max(max_consec_losses, current_streak)
        else:
            current_streak = 0

    return {
        "total_trades": total,
        "wins": win_count,
        "losses": loss_count,
        "breakevens": len(breakevens),
        "win_rate": round(win_rate, 4),
        "total_pnl_sol": round(total_pnl, 6),
        "gross_wins_sol": round(gross_wins, 6),
        "gross_losses_sol": round(gross_losses, 6),
        "profit_factor": round(profit_factor, 4),
        "avg_win_sol": round(avg_win, 6),
        "avg_loss_sol": round(avg_loss, 6),
        "expectancy_sol": round(expectancy, 6),
        "avg_hold_minutes": round(avg_hold, 1),
        "max_consecutive_losses": max_consec_losses,
    }


def print_stats(stats: dict, label: str = "Overall") -> None:
    """Print statistics in a formatted table.

    Args:
        stats: Statistics dictionary from compute_stats.
        label: Label for the statistics section.
    """
    if stats.get("status") == "no_closed_trades":
        print(f"\n{label}: No closed trades to analyze.")
        return

    print(f"\n{'=' * 50}")
    print(f"  {label} Statistics")
    print(f"{'=' * 50}")
    print(f"  Total Trades:       {stats['total_trades']}")
    print(f"  Wins / Losses / BE: {stats['wins']} / {stats['losses']} / {stats['breakevens']}")
    print(f"  Win Rate:           {stats['win_rate']:.1%}")
    print(f"  Total P&L:          {stats['total_pnl_sol']:+.4f} SOL")
    print(f"  Profit Factor:      {stats['profit_factor']:.2f}")
    print(f"  Avg Win:            {stats['avg_win_sol']:+.4f} SOL")
    print(f"  Avg Loss:           {stats['avg_loss_sol']:.4f} SOL")
    print(f"  Expectancy:         {stats['expectancy_sol']:+.4f} SOL")
    print(f"  Avg Hold Time:      {stats['avg_hold_minutes']:.0f} min")
    print(f"  Max Consec Losses:  {stats['max_consecutive_losses']}")
    print(f"{'=' * 50}")


# ── Display ────────────────────────────────────────────────────────

def print_trades(trades: list[dict]) -> None:
    """Print a formatted list of trades.

    Args:
        trades: List of trade records to display.
    """
    if not trades:
        print("No trades found.")
        return

    print(f"\n{'ID':<20} {'Token':<8} {'Dir':<6} {'Entry':>10} {'Exit':>10} {'P&L SOL':>10} {'Outcome':<10} {'Strategy'}")
    print("-" * 100)
    for t in trades:
        exit_p = f"{t['exit_price']:.4f}" if t.get("exit_price") else "—"
        pnl = f"{t['pnl_sol']:+.4f}" if t.get("pnl_sol") is not None else "—"
        outcome = t.get("outcome", "open")
        print(
            f"{t['id']:<20} {t['token']:<8} {t['direction']:<6} "
            f"{t['entry_price']:>10.4f} {exit_p:>10} {pnl:>10} "
            f"{outcome:<10} {t['strategy']}"
        )
    print(f"\nTotal: {len(trades)} trades")


# ── Demo Mode ──────────────────────────────────────────────────────

def run_demo() -> None:
    """Run demo mode: create 10 example trades and show statistics.

    Generates synthetic trades across multiple strategies and tokens
    to demonstrate the journal's capabilities.
    """
    print("=" * 50)
    print("  Trade Journal — Demo Mode")
    print("=" * 50)

    journal: dict = {
        "journal_version": "1.0",
        "trader_id": "demo",
        "created": "2025-03-01T00:00:00+00:00",
        "updated": "2025-03-10T00:00:00+00:00",
        "trades": [],
    }

    demo_trades: list[dict] = [
        {"token": "SOL", "dir": "long", "entry": 142.5, "exit": 146.2, "size": 5.0,
         "strat": "momentum-breakout", "outcome": "win", "hold": 135,
         "rationale": "4h resistance break with volume", "quality": 8, "emotion": "calm"},
        {"token": "BONK", "dir": "long", "entry": 0.000023, "exit": 0.000021, "size": 10.0,
         "strat": "volume-spike", "outcome": "loss", "hold": 45,
         "rationale": "Volume spike 3x avg on 5m", "quality": 6, "emotion": "excited"},
        {"token": "JUP", "dir": "long", "entry": 0.85, "exit": 0.92, "size": 8.0,
         "strat": "pullback-entry", "outcome": "win", "hold": 240,
         "rationale": "Pullback to 20 EMA in uptrend", "quality": 9, "emotion": "calm"},
        {"token": "SOL", "dir": "long", "entry": 145.0, "exit": 143.5, "size": 7.0,
         "strat": "momentum-breakout", "outcome": "loss", "hold": 60,
         "rationale": "Breaking daily high with volume", "quality": 7, "emotion": "calm"},
        {"token": "WIF", "dir": "long", "entry": 2.10, "exit": 2.35, "size": 4.0,
         "strat": "whale-follow", "outcome": "win", "hold": 180,
         "rationale": "Large wallet accumulated 500K tokens", "quality": 7, "emotion": "calm"},
        {"token": "BONK", "dir": "long", "entry": 0.000020, "exit": 0.000019, "size": 15.0,
         "strat": "gut-feel", "outcome": "loss", "hold": 20,
         "rationale": "Felt like it would bounce", "quality": 3, "emotion": "revenge"},
        {"token": "SOL", "dir": "long", "entry": 140.0, "exit": 144.0, "size": 6.0,
         "strat": "oversold-bounce", "outcome": "win", "hold": 300,
         "rationale": "RSI 25 on 4h, at strong support", "quality": 8, "emotion": "calm"},
        {"token": "RAY", "dir": "long", "entry": 4.50, "exit": 4.80, "size": 5.0,
         "strat": "pullback-entry", "outcome": "win", "hold": 120,
         "rationale": "Pullback to VWAP in uptrend", "quality": 8, "emotion": "calm"},
        {"token": "JUP", "dir": "long", "entry": 0.90, "exit": 0.87, "size": 12.0,
         "strat": "fomo", "outcome": "loss", "hold": 30,
         "rationale": "Already up 15% but entering anyway", "quality": 2, "emotion": "fomo"},
        {"token": "SOL", "dir": "long", "entry": 143.0, "exit": 147.5, "size": 5.0,
         "strat": "trend-continuation", "outcome": "win", "hold": 360,
         "rationale": "Higher low confirmed, trend intact", "quality": 9, "emotion": "calm"},
    ]

    base_date = datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    for i, dt in enumerate(demo_trades):
        entry_dt = base_date.replace(day=1 + i, hour=10 + (i % 6))
        exit_dt = entry_dt.replace(
            hour=entry_dt.hour + dt["hold"] // 60,
            minute=dt["hold"] % 60,
        )

        if dt["dir"] == "long":
            pnl_pct = (dt["exit"] - dt["entry"]) / dt["entry"] * 100
        else:
            pnl_pct = (dt["entry"] - dt["exit"]) / dt["entry"] * 100

        trade: dict = {
            "id": f"T-2025030{1 + i}-001",
            "token": dt["token"],
            "direction": dt["dir"],
            "entry_date": entry_dt.isoformat(),
            "entry_price": dt["entry"],
            "size_sol": dt["size"],
            "strategy": dt["strat"],
            "rationale": dt["rationale"],
            "exit_date": exit_dt.isoformat(),
            "exit_price": dt["exit"],
            "pnl_sol": round(dt["size"] * pnl_pct / 100, 6),
            "pnl_pct": round(pnl_pct, 4),
            "outcome": dt["outcome"],
            "hold_time_minutes": dt["hold"],
            "setup_quality": dt["quality"],
            "emotional_state": dt["emotion"],
            "lessons": None,
        }
        journal["trades"].append(trade)

    print(f"\nGenerated {len(journal['trades'])} demo trades.\n")

    # Show all trades
    print_trades(journal["trades"])

    # Overall stats
    stats = compute_stats(journal["trades"])
    print_stats(stats, "Overall")

    # Stats by strategy
    strategies = {t["strategy"] for t in journal["trades"]}
    for strat in sorted(strategies):
        strat_trades = [t for t in journal["trades"] if t["strategy"] == strat]
        strat_stats = compute_stats(strat_trades)
        print_stats(strat_stats, f"Strategy: {strat}")

    # Flag behavioral issues
    print(f"\n{'=' * 50}")
    print("  Behavioral Flags")
    print(f"{'=' * 50}")

    revenge_trades = [
        t for t in journal["trades"]
        if t.get("emotional_state") == "revenge"
    ]
    fomo_trades = [
        t for t in journal["trades"]
        if t.get("emotional_state") == "fomo"
    ]
    low_quality = [
        t for t in journal["trades"]
        if t.get("setup_quality") is not None and t["setup_quality"] <= 4
    ]

    print(f"  Revenge trades:     {len(revenge_trades)}")
    print(f"  FOMO trades:        {len(fomo_trades)}")
    print(f"  Low quality (<= 4): {len(low_quality)}")
    if revenge_trades or fomo_trades:
        emotional_pnl = sum(
            t.get("pnl_sol", 0) for t in revenge_trades + fomo_trades
            if t.get("pnl_sol") is not None
        )
        print(f"  Emotional trade P&L: {emotional_pnl:+.4f} SOL")
    print(f"{'=' * 50}")

    print("\nDemo complete. No files were written.")


# ── CLI ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the trade logger CLI.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Trade Journal Logger — log, list, update, and analyze trades",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--demo", action="store_true", help="Run demo with example trades")
    parser.add_argument("--journal", default=JOURNAL_PATH, help="Path to journal file")

    sub = parser.add_subparsers(dest="command")

    # Add trade
    add_p = sub.add_parser("add", help="Add a new trade")
    add_p.add_argument("--token", required=True, help="Token symbol")
    add_p.add_argument("--direction", required=True, choices=["long", "short"])
    add_p.add_argument("--entry-price", required=True, type=float)
    add_p.add_argument("--size", required=True, type=float, help="Size in SOL")
    add_p.add_argument("--strategy", required=True, help="Strategy tag")
    add_p.add_argument("--rationale", required=True, help="Trade rationale")
    add_p.add_argument("--setup-quality", type=int, help="Setup quality 1-10")
    add_p.add_argument("--emotion", help="Emotional state")
    add_p.add_argument("--stop", type=float, help="Stop-loss price")
    add_p.add_argument("--target", type=float, help="Take-profit price")
    add_p.add_argument("--tags", nargs="+", help="Freeform tags")

    # List trades
    list_p = sub.add_parser("list", help="List trades with optional filters")
    list_p.add_argument("--strategy", help="Filter by strategy")
    list_p.add_argument("--outcome", choices=["win", "loss", "breakeven"])
    list_p.add_argument("--token", help="Filter by token")
    list_p.add_argument("--from", dest="date_from", help="Start date (ISO)")
    list_p.add_argument("--to", dest="date_to", help="End date (ISO)")

    # Update trade
    upd_p = sub.add_parser("update", help="Update a trade")
    upd_p.add_argument("trade_id", help="Trade ID to update")
    upd_p.add_argument("--exit-price", type=float)
    upd_p.add_argument("--outcome", choices=["win", "loss", "breakeven"])
    upd_p.add_argument("--lessons", help="Post-trade lessons")
    upd_p.add_argument("--emotion", help="Emotional state")

    # Stats
    stats_p = sub.add_parser("stats", help="Compute trading statistics")
    stats_p.add_argument("--strategy", help="Filter by strategy")
    stats_p.add_argument("--token", help="Filter by token")

    return parser


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for the trade logger CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not args.command:
        parser.print_help()
        sys.exit(0)

    journal = load_journal(args.journal)

    if args.command == "add":
        add_trade(
            journal,
            token=args.token,
            direction=args.direction,
            entry_price=args.entry_price,
            size_sol=args.size,
            strategy=args.strategy,
            rationale=args.rationale,
            setup_quality=args.setup_quality,
            emotional_state=args.emotion,
            stop_price=args.stop,
            target_price=args.target,
            tags=args.tags,
        )
        save_journal(journal, args.journal)

    elif args.command == "list":
        filtered = filter_trades(
            journal["trades"],
            strategy=args.strategy,
            outcome=args.outcome,
            token=args.token,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        print_trades(filtered)

    elif args.command == "update":
        update_trade(
            journal,
            trade_id=args.trade_id,
            exit_price=args.exit_price,
            outcome=args.outcome,
            lessons=args.lessons,
            emotional_state=args.emotion,
        )
        save_journal(journal, args.journal)

    elif args.command == "stats":
        trades = journal["trades"]
        if args.strategy:
            trades = [t for t in trades if t.get("strategy") == args.strategy]
        if args.token:
            trades = [t for t in trades if t.get("token", "").upper() == args.token.upper()]
        stats = compute_stats(trades)
        label = "Overall"
        if args.strategy:
            label = f"Strategy: {args.strategy}"
        if args.token:
            label = f"Token: {args.token}"
        print_stats(stats, label)


if __name__ == "__main__":
    main()
