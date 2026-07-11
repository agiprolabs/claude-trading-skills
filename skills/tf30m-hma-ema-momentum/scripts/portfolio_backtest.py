#!/usr/bin/env python3
"""Multi-symbol portfolio backtest for the TF30M HMA20-EMA Cross Momentum bot.

Unlike running scripts/tf30m_hma_ema_strategy.py or run_bot.py --replay
independently per symbol, this drives every symbol's bars through
`TF30MBot.process_bar()` in **true chronological order across the whole
portfolio**, sharing one `RiskManager` instance, one balance, and one
`MAX_OPEN_POSITIONS` cap -- exactly how the deployed bot behaves when it
polls several symbols against one account. That makes this the realistic
multi-symbol counterpart to the single-symbol --replay mode: the same code
path (state machine, leverage scaling, ATR stop/target, drawdown halt) runs
against historical data instead of a live feed.

Input: a directory containing one CSV per symbol named "{SYMBOL}.csv" with
columns timestamp(ms),open,high,low,close,volume, ascending time.

Usage:
    python portfolio_backtest.py --data-dir clean_data --symbols BTC,ETH,SOL,XRP,XAU,XAG \
        --out report.json

Configuration mirrors run_bot.py's env vars (LEVERAGE, MARGIN_FRACTION,
MAX_OPEN_POSITIONS, MAX_DRAWDOWN_PCT, BALANCE) so results reflect whatever is
actually deployed.
"""

from __future__ import annotations

import argparse
import heapq
import json
import os
import sys
from pathlib import Path

import pandas as pd

from tf30m_hma_ema_strategy import compute_indicators
from run_bot import TF30MBot


def _load_symbol_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    return df


def run_portfolio_backtest(
    data_dir: str,
    symbols: list[str],
    ccxt_symbol_fmt: str = "{}/USDT:USDT",
) -> tuple[TF30MBot, dict]:
    """Load per-symbol CSVs, run the shared-portfolio simulation, return
    (bot, indicator_frames) so callers can build reports/charts from
    bot.traders[*].trade_log and indicator_frames[*] (for price overlays).
    """
    ccxt_symbols = [ccxt_symbol_fmt.format(s) for s in symbols]
    os.environ["SYMBOLS"] = ",".join(ccxt_symbols)
    os.environ.setdefault("PAPER", "true")

    bot = TF30MBot()

    frames: dict[str, pd.DataFrame] = {}
    for sym, ccxt_sym in zip(symbols, ccxt_symbols):
        raw = _load_symbol_csv(Path(data_dir) / f"{sym}.csv")
        frames[ccxt_sym] = compute_indicators(raw)

    # Chronological merge across all symbols via a min-heap of (timestamp, symbol, row_idx).
    heap: list[tuple[int, str, int]] = []
    lengths = {sym: len(df) for sym, df in frames.items()}
    for sym, df in frames.items():
        if len(df):
            heap.append((int(df["timestamp"].iloc[0]), sym, 0))
    heapq.heapify(heap)

    while heap:
        ts, sym, idx = heapq.heappop(heap)
        trader = bot.traders[sym]
        bot.process_bar(trader, frames[sym], idx)
        nxt = idx + 1
        if nxt < lengths[sym]:
            heapq.heappush(heap, (int(frames[sym]["timestamp"].iloc[nxt]), sym, nxt))

    return bot, frames


def summarize(bot: TF30MBot, starting_balance: float, start_ts: int = 0) -> dict:
    all_trades = []
    for sym, trader in bot.traders.items():
        all_trades.extend(trader.trade_log)
    all_trades.sort(key=lambda t: t["exit_ts"] or 0)

    wins = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)

    equity_curve = [{"ts": start_ts, "balance": starting_balance}]
    for t in all_trades:
        equity_curve.append({"ts": t["exit_ts"], "balance": t["balance_after"]})

    peak = starting_balance
    max_dd = 0.0
    for pt in equity_curve:
        peak = max(peak, pt["balance"])
        dd = (peak - pt["balance"]) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    per_symbol = {}
    for sym, trader in bot.traders.items():
        n = trader.trades
        per_symbol[sym] = {
            "trades": n,
            "wins": trader.wins,
            "losses": trader.losses,
            "win_rate": (trader.wins / n) if n else 0.0,
            "net_pnl": trader.net_pnl,
            "last_20": trader.trade_log[-20:],
        }

    return {
        "starting_balance": starting_balance,
        "ending_balance": bot.balance,
        "return_pct": (bot.balance / starting_balance - 1.0) * 100.0,
        "total_trades": len(all_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(all_trades)) if all_trades else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "max_drawdown_pct": max_dd * 100.0,
        "halted": bot.risk.is_halted,
        "equity_curve": equity_curve,
        "per_symbol": per_symbol,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="TF30M multi-symbol portfolio backtest")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--symbols", required=True, help="Comma-separated short symbol names, e.g. BTC,ETH,SOL")
    p.add_argument("--out", help="Write JSON summary to this path")
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    bot, frames = run_portfolio_backtest(args.data_dir, symbols)
    starting_balance = float(os.getenv("BALANCE", "10000"))
    start_ts = min(int(df["timestamp"].iloc[0]) for df in frames.values() if len(df))
    summary = summarize(bot, starting_balance, start_ts=start_ts)

    print(f"Trades: {summary['total_trades']} | Win rate: {summary['win_rate']:.1%} | "
          f"PF: {summary['profit_factor']:.2f} | Return: {summary['return_pct']:+.2f}% | "
          f"Max DD: {summary['max_drawdown_pct']:.2f}%")
    for sym, s in summary["per_symbol"].items():
        print(f"  {sym}: {s['trades']} trades, {s['win_rate']:.1%} WR, net_pnl={s['net_pnl']:+.2f}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Wrote {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
