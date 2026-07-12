#!/usr/bin/env python3
"""Layer 4 — Risk Management (sizing, position limits, split TP1/TP2).

Ties Layers 1-3 together into a full, runnable portfolio backtest. Layer 3
only says "enter LONG/SHORT here" -- Layer 4 decides whether that's actually
allowed right now (position limits) and manages the trade from entry to
exit:

    Margin per position   5% of current balance (no leverage -- margin IS
                           the notional; not specified by this layer's
                           spec, so not assumed)
    Position limits        max 2 concurrent positions across the whole
                           portfolio; at most 1 position per symbol (a
                           symbol already holding a position cannot open
                           a second one, long or short)
    Risk unit (1R)          ATR(14) x 1.5, in price terms, at entry
    Stop loss               entry -/+ 1R
    Take-profit split       TP1 at 0.5R  -- closes 50% of the position
                            TP2 at 1.2R  -- closes the remaining 50%

One design choice beyond the literal spec: once TP1 fills, the stop for the
remaining 50% moves to breakeven **plus a small buffer** (entry + 0.1R for
a LONG, entry - 0.1R for a SHORT), not exactly breakeven -- confirmed with
the user (see `breakeven_offset_r`). This locks in a small guaranteed gain
on the runner rather than a guaranteed flat/zero, and is easy to change
(`move_to_breakeven=False` for a fixed original stop, or a different
`breakeven_offset_r`) if wanted.

Usage:
    python layer4_risk.py --demo
    python layer4_risk.py --data-dir clean_data --symbols BTC,ETH,SOL,XRP,XAU,XAG

Each symbol needs three CSVs in --data-dir: {SYMBOL}_1h.csv, {SYMBOL}_30m.csv,
{SYMBOL}_15m.csv (columns: timestamp,open,high,low,close,volume).

Dependencies:
    uv pip install pandas numpy
"""

from __future__ import annotations

import argparse
import heapq
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layer3_entry import layer3_entry, make_demo_data  # noqa: E402

ATR_PERIOD = 14
ATR_STOP_MULT = 1.5   # 1R = ATR14 * 1.5
TP1_R = 0.5            # first target, 50% of size
TP2_R = 1.2            # second target, remaining 50%
TP1_FRACTION = 0.5
BREAKEVEN_OFFSET_R = 0.1  # post-TP1 stop = entry +/- this many R (confirmed: BE+0.1R, not exact BE)

MARGIN_FRACTION = 0.05
MAX_POSITIONS = 2


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


@dataclass
class Position:
    symbol: str
    direction: str          # "LONG" or "SHORT"
    entry_price: float
    entry_ts: int
    sl: float
    tp1: float
    tp2: float
    risk_distance: float     # 1R in price terms, at entry -- needed to compute the BE+offset stop later
    margin: float            # original margin; remaining_margin shrinks after TP1
    remaining_margin: float
    tp1_hit: bool = False


@dataclass
class Fill:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    entry_ts: int
    exit_ts: int
    reason: str              # "SL", "TP1", "TP2", "BE_STOP"
    portion_margin: float     # dollar margin closed in this fill
    pnl: float
    pnl_pct: float            # price % move on this leg


class Layer4RiskManager:
    """Position sizing, portfolio-wide + per-symbol limits, and split-TP
    exit mechanics for one backtest run. Holds no dependency on Layers 1-3
    -- callers decide *when* to call open()/check_exit(); this class only
    enforces the risk rules once told to act.
    """

    def __init__(self, balance: float = 10_000.0, margin_fraction: float = MARGIN_FRACTION,
                 max_positions: int = MAX_POSITIONS, move_to_breakeven: bool = True,
                 breakeven_offset_r: float = BREAKEVEN_OFFSET_R):
        self.balance = balance
        self.margin_fraction = margin_fraction
        self.max_positions = max_positions
        self.move_to_breakeven = move_to_breakeven
        self.breakeven_offset_r = breakeven_offset_r
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []

    def can_open(self, symbol: str) -> tuple[bool, str]:
        if symbol in self.positions:
            return False, f"{symbol} already has an open position"
        if len(self.positions) >= self.max_positions:
            return False, f"max positions ({self.max_positions}) reached"
        return True, "ok"

    def open(self, symbol: str, direction: str, entry_price: float, entry_ts: int, atr_value: float) -> Position:
        risk_distance = atr_value * ATR_STOP_MULT
        if direction == "LONG":
            sl = entry_price - risk_distance
            tp1 = entry_price + TP1_R * risk_distance
            tp2 = entry_price + TP2_R * risk_distance
        else:
            sl = entry_price + risk_distance
            tp1 = entry_price - TP1_R * risk_distance
            tp2 = entry_price - TP2_R * risk_distance
        margin = self.balance * self.margin_fraction
        pos = Position(
            symbol=symbol, direction=direction, entry_price=entry_price, entry_ts=entry_ts,
            sl=sl, tp1=tp1, tp2=tp2, risk_distance=risk_distance,
            margin=margin, remaining_margin=margin,
        )
        self.positions[symbol] = pos
        return pos

    def _record_fill(self, pos: Position, exit_price: float, exit_ts: int,
                      reason: str, portion_margin: float) -> None:
        if pos.direction == "LONG":
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price
        pnl = portion_margin * pnl_pct
        self.balance += pnl
        self.fills.append(Fill(
            symbol=pos.symbol, direction=pos.direction, entry_price=pos.entry_price,
            exit_price=exit_price, entry_ts=pos.entry_ts, exit_ts=exit_ts, reason=reason,
            portion_margin=portion_margin, pnl=pnl, pnl_pct=pnl_pct,
        ))

    def check_exit(self, symbol: str, high: float, low: float, ts: int) -> None:
        """Check one bar's high/low against the open position's levels.
        Same-bar ordering is conservative: if both a stop and a target could
        have been touched within one bar, the stop is assumed to have hit
        first (matches the precedent in tf30m-hma-ema-momentum's engine).
        A position is only ever checked against ONE tier per bar -- TP1 and
        TP2/BE-stop are never both evaluated in the same call, since in
        reality the stop only moves up *after* TP1 actually fills.
        """
        pos = self.positions.get(symbol)
        if pos is None:
            return

        if not pos.tp1_hit:
            if pos.direction == "LONG":
                if low <= pos.sl:
                    self._record_fill(pos, pos.sl, ts, "SL", pos.remaining_margin)
                    del self.positions[symbol]
                    return
                if high >= pos.tp1:
                    self._record_fill(pos, pos.tp1, ts, "TP1", pos.margin * TP1_FRACTION)
                    pos.remaining_margin = pos.margin * (1 - TP1_FRACTION)
                    pos.tp1_hit = True
                    if self.move_to_breakeven:
                        pos.sl = pos.entry_price + self.breakeven_offset_r * pos.risk_distance
            else:
                if high >= pos.sl:
                    self._record_fill(pos, pos.sl, ts, "SL", pos.remaining_margin)
                    del self.positions[symbol]
                    return
                if low <= pos.tp1:
                    self._record_fill(pos, pos.tp1, ts, "TP1", pos.margin * TP1_FRACTION)
                    pos.remaining_margin = pos.margin * (1 - TP1_FRACTION)
                    pos.tp1_hit = True
                    if self.move_to_breakeven:
                        pos.sl = pos.entry_price - self.breakeven_offset_r * pos.risk_distance
        else:
            # tp1_hit is already True here, so any stop hit in this branch is
            # necessarily the post-TP1 protective stop (BE + offset), never
            # the original stop -- that can only fire in the branch above.
            if pos.direction == "LONG":
                if low <= pos.sl:
                    self._record_fill(pos, pos.sl, ts, "BE_STOP", pos.remaining_margin)
                    del self.positions[symbol]
                elif high >= pos.tp2:
                    self._record_fill(pos, pos.tp2, ts, "TP2", pos.remaining_margin)
                    del self.positions[symbol]
            else:
                if high >= pos.sl:
                    self._record_fill(pos, pos.sl, ts, "BE_STOP", pos.remaining_margin)
                    del self.positions[symbol]
                elif low <= pos.tp2:
                    self._record_fill(pos, pos.tp2, ts, "TP2", pos.remaining_margin)
                    del self.positions[symbol]


# ── Portfolio backtest driver (ties Layers 1-4 together) ─────────────────
def run_layer4_backtest(
    symbol_data: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]],
    balance: float = 10_000.0,
    margin_fraction: float = MARGIN_FRACTION,
    max_positions: int = MAX_POSITIONS,
) -> tuple[Layer4RiskManager, dict[str, pd.DataFrame]]:
    """symbol_data: symbol -> (df_1h, df_30m, df_15m). Returns the risk
    manager (balance + fills) and each symbol's full Layer 1-3 signal frame
    (for inspection/charting)."""
    risk = Layer4RiskManager(balance, margin_fraction, max_positions)

    signals: dict[str, pd.DataFrame] = {}
    for symbol, (df_1h, df_30m, df_15m) in symbol_data.items():
        sig = layer3_entry(df_1h, df_30m, df_15m)
        sig["atr14"] = atr(df_15m["high"], df_15m["low"], df_15m["close"]).reset_index(drop=True)
        sig["high"] = df_15m["high"].reset_index(drop=True)
        sig["low"] = df_15m["low"].reset_index(drop=True)
        sig["close"] = df_15m["close"].reset_index(drop=True)
        signals[symbol] = sig

    heap: list[tuple[int, str, int]] = []
    lengths = {s: len(df) for s, df in signals.items()}
    for symbol, df in signals.items():
        if len(df):
            heapq.heappush(heap, (int(df["timestamp"].iloc[0]), symbol, 0))

    while heap:
        ts, symbol, idx = heapq.heappop(heap)
        row = signals[symbol].iloc[idx]

        if symbol in risk.positions:
            risk.check_exit(symbol, float(row["high"]), float(row["low"]), int(row["timestamp"]))

        if symbol not in risk.positions and row["layer3_entry"] in ("LONG", "SHORT") and not pd.isna(row["atr14"]):
            can, _ = risk.can_open(symbol)
            if can:
                risk.open(symbol, row["layer3_entry"], float(row["close"]),
                          int(row["timestamp"]), float(row["atr14"]))

        nxt = idx + 1
        if nxt < lengths[symbol]:
            heapq.heappush(heap, (int(signals[symbol]["timestamp"].iloc[nxt]), symbol, nxt))

    return risk, signals


def summarize(risk: Layer4RiskManager, starting_balance: float) -> dict:
    fills = risk.fills
    wins = [f for f in fills if f.pnl > 0]
    losses = [f for f in fills if f.pnl <= 0]
    gross_win = sum(f.pnl for f in wins)
    gross_loss = -sum(f.pnl for f in losses)
    by_symbol: dict[str, dict] = {}
    for f in fills:
        s = by_symbol.setdefault(f.symbol, {"fills": 0, "pnl": 0.0})
        s["fills"] += 1
        s["pnl"] += f.pnl
    return {
        "starting_balance": starting_balance,
        "ending_balance": risk.balance,
        "return_pct": (risk.balance / starting_balance - 1.0) * 100.0,
        "total_fills": len(fills),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(fills)) if fills else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "by_reason": {r: sum(1 for f in fills if f.reason == r) for r in ("SL", "TP1", "TP2", "BE_STOP")},
        "by_symbol": by_symbol,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Layer 4 -- risk management + full portfolio backtest")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--data-dir")
    p.add_argument("--symbols", help="Comma-separated symbol names, matching {SYMBOL}_1h.csv etc.")
    p.add_argument("--balance", type=float, default=10_000.0)
    args = p.parse_args()

    if args.demo:
        symbol_data = {}
        for i, sym in enumerate(("DEMO_A", "DEMO_B")):
            df_1h, df_30m, df_15m = make_demo_data(seed=i + 1)
            symbol_data[sym] = (df_1h, df_30m, df_15m)
    elif args.data_dir and args.symbols:
        symbol_data = {}
        for sym in args.symbols.split(","):
            sym = sym.strip()
            d = Path(args.data_dir)
            symbol_data[sym] = (
                pd.read_csv(d / f"{sym}_1h.csv"),
                pd.read_csv(d / f"{sym}_30m.csv"),
                pd.read_csv(d / f"{sym}_15m.csv"),
            )
    else:
        p.error("Provide --demo or both --data-dir and --symbols")
        return 1

    risk, _ = run_layer4_backtest(symbol_data, balance=args.balance)
    summary = summarize(risk, args.balance)

    print(f"Fills: {summary['total_fills']} | Win rate: {summary['win_rate']:.1%} | "
          f"PF: {summary['profit_factor']:.2f} | Return: {summary['return_pct']:+.2f}%")
    print(f"By reason: {summary['by_reason']}")
    print("\nBy symbol:")
    for sym, s in summary["by_symbol"].items():
        print(f"  {sym}: {s['fills']} fills, pnl={s['pnl']:+.2f}")
    print(f"\nBalance: {summary['starting_balance']:,.2f} -> {summary['ending_balance']:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
