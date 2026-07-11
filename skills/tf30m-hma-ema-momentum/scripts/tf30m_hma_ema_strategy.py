#!/usr/bin/env python3
"""TF30M HMA20-EMA Cross Momentum strategy engine and backtester.

Implements the full three-part system on 30-minute bars:

    1. Direction Gate      -- HMA(20) decides whether Long or Short is allowed
    2. Entry Trigger       -- EMA(5) crossing EMA(9) starts a setup
    3. Confirmation Score  -- ROC / RSI / ADX / Volume must pass >= 3 of 4

Entries are bar-close evaluated. Exits combine a fixed ATR stop / take-profit
(1:1 R:R) with a direction-signal early exit (HMA / EMA / ROC reverse). The
state machine and bar-processing order follow the strategy pseudocode exactly.

Usage:
    python tf30m_hma_ema_strategy.py --demo
    python tf30m_hma_ema_strategy.py --csv candles_30m.csv
    python tf30m_hma_ema_strategy.py --csv candles_30m.csv --balance 10000

CSV format (header required, ascending time):
    timestamp,open,high,low,close,volume

Dependencies:
    uv pip install pandas numpy

This skill provides analytical tools and information only. It does not
constitute financial advice or trading recommendations.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


# ── Strategy parameters ─────────────────────────────────────────────
HMA_PERIOD = 20
EMA_FAST = 5
EMA_SLOW = 9
ROC_PERIOD = 9
RSI_PERIOD = 14
ADX_PERIOD = 14
VOLUME_SMA_PERIOD = 20
ATR_PERIOD = 14

ADX_THRESHOLD = 18.0
ATR_STOP_MULT = 1.5           # SL distance = ATR(14) x 1.5
ATR_TP_MULT = 1.5             # TP distance = ATR(14) x 1.5 (1:1 R:R)
MARGIN_FRACTION = 0.05        # position margin = 5% of balance
CONFIRMATION_BARS = 3         # confirmation window length
MIN_SCORE = 3                 # need >= 3 of 4 confirmation conditions


# ── Indicators ──────────────────────────────────────────────────────
def wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted moving average with linearly increasing weights."""
    weights = np.arange(1, period + 1, dtype=float)

    def _calc(window: np.ndarray) -> float:
        return float(np.dot(window, weights) / weights.sum())

    return series.rolling(period).apply(_calc, raw=True)


def hma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    half = int(period / 2)
    sqrt_n = int(np.sqrt(period))
    raw = 2 * wma(series, half) - wma(series, period)
    return wma(raw, sqrt_n)


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (span form, matches TradingView `ema`)."""
    return series.ewm(span=period, adjust=False).mean()


def roc(series: pd.Series, period: int) -> pd.Series:
    """Rate of change in percent."""
    return (series / series.shift(period) - 1.0) * 100.0


def rsi(series: pd.Series, period: int) -> pd.Series:
    """Wilder's Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When avg_loss is zero, RSI is 100 by definition.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Wilder's Average True Range."""
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Wilder's Average Directional Index (ADX line only)."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    tr = true_range(high, low, close)
    atr_w = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_w
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_w
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Attach every indicator the state machine needs to a copy of `df`."""
    out = df.copy()
    out["hma20"] = hma(out["close"], HMA_PERIOD)
    out["ema5"] = ema(out["close"], EMA_FAST)
    out["ema9"] = ema(out["close"], EMA_SLOW)
    out["roc9"] = roc(out["close"], ROC_PERIOD)
    out["rsi14"] = rsi(out["close"], RSI_PERIOD)
    out["adx14"] = adx(out["high"], out["low"], out["close"], ADX_PERIOD)
    out["volume_sma20"] = out["volume"].rolling(VOLUME_SMA_PERIOD).mean()
    out["atr14"] = atr(out["high"], out["low"], out["close"], ATR_PERIOD)

    out["hma20_prev"] = out["hma20"].shift(1)
    out["adx14_prev"] = out["adx14"].shift(1)

    # EMA cross detection (state at close of each bar).
    above = out["ema5"] > out["ema9"]
    below = out["ema5"] < out["ema9"]
    out["ema_cross_up"] = above & (~above).shift(1, fill_value=False)
    out["ema_cross_down"] = below & (~below).shift(1, fill_value=False)
    return out


# ── State machine ───────────────────────────────────────────────────
class State(str, Enum):
    WAITING = "WAITING"
    LONG_CONFIRMATION = "LONG_CONFIRMATION"
    SHORT_CONFIRMATION = "SHORT_CONFIRMATION"
    LONG_POSITION = "LONG_POSITION"
    SHORT_POSITION = "SHORT_POSITION"


@dataclass
class Position:
    direction: str          # "LONG" or "SHORT"
    entry_index: int
    entry_price: float
    stop_loss: float
    take_profit: float
    margin: float
    snapshot: dict = field(default_factory=dict)


@dataclass
class Trade:
    direction: str
    entry_index: int
    exit_index: int
    entry_price: float
    exit_price: float
    reason: str             # "STOP", "TAKE_PROFIT", or "SIGNAL"
    pnl_pct: float
    snapshot: dict


def _long_score(row: pd.Series) -> tuple[int, dict]:
    comps = {
        "ROC": bool(row["roc9"] > 0),
        "RSI": bool(row["rsi14"] > 50),
        "ADX": bool(row["adx14"] >= ADX_THRESHOLD and row["adx14"] > row["adx14_prev"]),
        "Volume": bool(row["volume"] >= row["volume_sma20"]),
    }
    return sum(comps.values()), comps


def _short_score(row: pd.Series) -> tuple[int, dict]:
    comps = {
        "ROC": bool(row["roc9"] < 0),
        "RSI": bool(row["rsi14"] < 50),
        "ADX": bool(row["adx14"] >= ADX_THRESHOLD and row["adx14"] > row["adx14_prev"]),
        "Volume": bool(row["volume"] >= row["volume_sma20"]),
    }
    return sum(comps.values()), comps


def _snapshot(direction: str, row: pd.Series, score: int, comps: dict) -> dict:
    return {
        "entry_direction": direction,
        "entry_price": float(row["close"]),
        "entry_atr": float(row["atr14"]),
        "entry_hma20": float(row["hma20"]),
        "entry_ema5": float(row["ema5"]),
        "entry_ema9": float(row["ema9"]),
        "entry_roc9": float(row["roc9"]),
        "entry_rsi14": float(row["rsi14"]),
        "entry_adx14": float(row["adx14"]),
        "entry_volume": float(row["volume"]),
        "entry_confirmation_score": score,
        "entry_confirmation_components": comps,
    }


class Action(str, Enum):
    NONE = "NONE"
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


@dataclass
class Decision:
    """One signal decision for a single closed bar."""
    action: Action = Action.NONE
    reason: str = ""                       # "SIGNAL" for signal exits
    score: int = 0
    components: dict = field(default_factory=dict)


class TF30MStateMachine:
    """Pure signal state machine — the single source of truth for the strategy.

    It owns only the WAITING / CONFIRMATION / POSITION state and the
    confirmation-bar counter. It does **not** track P&L, size positions, or
    execute orders — it just returns a `Decision` per closed bar. Stop-loss and
    take-profit are handled by the caller (they are "always live" on the
    exchange); when SL/TP closes a position externally, the caller must call
    `on_position_closed()` so the machine returns to WAITING.

    Both the backtester (`StrategyEngine`) and the live bot (`run_bot.py`) drive
    this same class so their entry/exit logic can never diverge.
    """

    def __init__(self) -> None:
        self.state = State.WAITING
        self.confirmation_bar = 0

    def reset(self) -> None:
        self.state = State.WAITING
        self.confirmation_bar = 0

    # Called by the caller when SL/TP (or any external close) ends the trade.
    on_position_closed = reset

    @staticmethod
    def is_warm(row: pd.Series) -> bool:
        return not (
            pd.isna(row["hma20"])
            or pd.isna(row["hma20_prev"])
            or pd.isna(row["adx14_prev"])
        )

    def step(self, row: pd.Series) -> Decision:
        """Advance the machine one closed bar and return the resulting action.

        Mirrors the pseudocode exactly, minus the intrabar SL/TP block which the
        caller runs *before* calling `step` (and then skips the bar on a fill).
        """
        if not self.is_warm(row):
            return Decision(Action.NONE)

        open_, close = float(row["open"]), float(row["close"])
        hma20, hma20_prev = float(row["hma20"]), float(row["hma20_prev"])
        ema5, ema9 = float(row["ema5"]), float(row["ema9"])
        roc9 = float(row["roc9"])
        cross_up, cross_down = bool(row["ema_cross_up"]), bool(row["ema_cross_down"])

        # Manage open LONG (signal exit on bar close). No immediate reversal:
        # `step` returns here, so no new entry is evaluated on the same bar.
        if self.state == State.LONG_POSITION:
            if close < hma20 or cross_down or roc9 < 0:
                self.reset()
                return Decision(Action.EXIT_LONG, reason="SIGNAL")
            return Decision(Action.NONE)

        if self.state == State.SHORT_POSITION:
            if close > hma20 or cross_up or roc9 > 0:
                self.reset()
                return Decision(Action.EXIT_SHORT, reason="SIGNAL")
            return Decision(Action.NONE)

        # START LONG SETUP
        if self.state == State.WAITING:
            long_gate = open_ > hma20 and hma20 >= hma20_prev
            if long_gate and cross_up:
                self.state = State.LONG_CONFIRMATION
                self.confirmation_bar = 1
                return Decision(Action.NONE)
            # START SHORT SETUP
            short_gate = open_ < hma20 and hma20 <= hma20_prev
            if short_gate and cross_down:
                self.state = State.SHORT_CONFIRMATION
                self.confirmation_bar = 1
                return Decision(Action.NONE)
            return Decision(Action.NONE)

        # PROCESS LONG CONFIRMATION
        if self.state == State.LONG_CONFIRMATION:
            if open_ <= hma20 or hma20 < hma20_prev or ema5 <= ema9 or cross_down:
                self.reset()
                return Decision(Action.NONE)
            score, comps = _long_score(row)
            if score >= MIN_SCORE:
                self.state = State.LONG_POSITION
                self.confirmation_bar = 0
                return Decision(Action.ENTER_LONG, score=score, components=comps)
            if self.confirmation_bar >= CONFIRMATION_BARS:
                self.reset()
                return Decision(Action.NONE)
            self.confirmation_bar += 1
            return Decision(Action.NONE)

        # PROCESS SHORT CONFIRMATION
        if self.state == State.SHORT_CONFIRMATION:
            if open_ >= hma20 or hma20 > hma20_prev or ema5 >= ema9 or cross_up:
                self.reset()
                return Decision(Action.NONE)
            score, comps = _short_score(row)
            if score >= MIN_SCORE:
                self.state = State.SHORT_POSITION
                self.confirmation_bar = 0
                return Decision(Action.ENTER_SHORT, score=score, components=comps)
            if self.confirmation_bar >= CONFIRMATION_BARS:
                self.reset()
                return Decision(Action.NONE)
            self.confirmation_bar += 1
            return Decision(Action.NONE)

        return Decision(Action.NONE)


class StrategyEngine:
    """Bar-by-bar backtest executor built on `TF30MStateMachine`.

    The state machine produces signals; this class layers paper execution on
    top: intrabar Stop Loss / Take Profit against each bar's high/low, entries
    and signal exits at bar close, and P&L on a 5%-of-balance notional.
    """

    def __init__(self, balance: float = 10_000.0) -> None:
        self.balance = balance
        self.sm = TF30MStateMachine()
        self.position: Optional[Position] = None
        self.trades: list[Trade] = []

    @property
    def state(self) -> State:
        return self.sm.state

    @property
    def confirmation_bar(self) -> int:
        return self.sm.confirmation_bar

    # -- exits ------------------------------------------------------
    def _close(self, i: int, exit_price: float, reason: str) -> None:
        pos = self.position
        assert pos is not None
        if pos.direction == "LONG":
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price
        # Realise P&L on the margined notional (margin = 5% of balance used
        # as notional here; leverage is out of scope for the reference model).
        self.balance += pos.margin * pnl_pct
        self.trades.append(
            Trade(
                direction=pos.direction,
                entry_index=pos.entry_index,
                exit_index=i,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                reason=reason,
                pnl_pct=pnl_pct,
                snapshot=pos.snapshot,
            )
        )
        self.position = None

    def _check_stop_tp(self, i: int, row: pd.Series) -> bool:
        """Intrabar SL/TP. Returns True if the position was closed."""
        pos = self.position
        if pos is None:
            return False
        high, low = float(row["high"]), float(row["low"])
        if pos.direction == "LONG":
            # Conservative ordering: assume stop is touched before target when
            # both lie inside the bar.
            if low <= pos.stop_loss:
                self._close(i, pos.stop_loss, "STOP")
                return True
            if high >= pos.take_profit:
                self._close(i, pos.take_profit, "TAKE_PROFIT")
                return True
        else:
            if high >= pos.stop_loss:
                self._close(i, pos.stop_loss, "STOP")
                return True
            if low <= pos.take_profit:
                self._close(i, pos.take_profit, "TAKE_PROFIT")
                return True
        return False

    # -- entries ----------------------------------------------------
    def _open(self, direction: str, i: int, row: pd.Series, score: int, comps: dict) -> None:
        entry = float(row["close"])
        atr = float(row["atr14"])
        if direction == "LONG":
            sl, tp = entry - atr * ATR_STOP_MULT, entry + atr * ATR_TP_MULT
        else:
            sl, tp = entry + atr * ATR_STOP_MULT, entry - atr * ATR_TP_MULT
        self.position = Position(
            direction=direction,
            entry_index=i,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            margin=self.balance * MARGIN_FRACTION,
            snapshot=_snapshot(direction, row, score, comps),
        )

    # -- per-bar driver ---------------------------------------------
    def on_bar(self, i: int, row: pd.Series) -> None:
        if not TF30MStateMachine.is_warm(row):
            return

        # 1) Intrabar stop / take-profit have top priority while in a trade.
        # If filled, tell the state machine and skip the bar (no signal exit,
        # no new entry) -- mirrors the pseudocode's early return.
        if self.position is not None and self._check_stop_tp(i, row):
            self.sm.on_position_closed()
            return

        # 2) Signal state machine decides the rest (exit / entry / nothing).
        decision = self.sm.step(row)
        if decision.action in (Action.EXIT_LONG, Action.EXIT_SHORT):
            self._close(i, float(row["close"]), decision.reason)
        elif decision.action == Action.ENTER_LONG:
            self._open("LONG", i, row, decision.score, decision.components)
        elif decision.action == Action.ENTER_SHORT:
            self._open("SHORT", i, row, decision.score, decision.components)


# ── Backtest driver ─────────────────────────────────────────────────
def run_backtest(df: pd.DataFrame, balance: float = 10_000.0) -> tuple[StrategyEngine, pd.DataFrame]:
    """Run the engine over an OHLCV frame and return the engine + indicators."""
    ind = compute_indicators(df)
    engine = StrategyEngine(balance=balance)
    for i, (_, row) in enumerate(ind.iterrows()):
        engine.on_bar(i, row)
    return engine, ind


def summarize(engine: StrategyEngine, starting_balance: float) -> dict:
    trades = engine.trades
    n = len(trades)
    wins = [t for t in trades if t.pnl_pct > 0]
    losses = [t for t in trades if t.pnl_pct <= 0]
    gross_win = sum(t.pnl_pct for t in wins)
    gross_loss = -sum(t.pnl_pct for t in losses)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / n) if n else 0.0,
        "avg_pnl_pct": (sum(t.pnl_pct for t in trades) / n) if n else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "starting_balance": starting_balance,
        "ending_balance": engine.balance,
        "return_pct": (engine.balance / starting_balance - 1.0) * 100.0,
        "exit_breakdown": {
            r: sum(1 for t in trades if t.reason == r)
            for r in ("STOP", "TAKE_PROFIT", "SIGNAL")
        },
    }


# ── Demo data ───────────────────────────────────────────────────────
def make_demo_data(n: int = 1200, seed: int = 7) -> pd.DataFrame:
    """Generate synthetic 30m OHLCV with alternating trend / chop regimes."""
    rng = np.random.default_rng(seed)
    price = 100.0
    rows = []
    for t in range(n):
        # Regime drift flips every ~150 bars, with noise.
        regime = np.sin(t / 150.0)
        drift = regime * 0.08
        ret = drift + rng.normal(0, 0.4)
        open_ = price
        close = max(1.0, price + ret)
        high = max(open_, close) + abs(rng.normal(0, 0.25))
        low = min(open_, close) - abs(rng.normal(0, 0.25))
        vol = max(1.0, rng.normal(1000, 250) * (1 + 0.5 * abs(regime)))
        rows.append((t, open_, high, low, close, vol))
        price = close
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(c.lower() for c in df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    df.columns = [c.lower() for c in df.columns]
    return df


# ── CLI ─────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="TF30M HMA20-EMA Cross Momentum backtester")
    p.add_argument("--csv", help="Path to 30m OHLCV CSV (open,high,low,close,volume)")
    p.add_argument("--demo", action="store_true", help="Run on synthetic demo data")
    p.add_argument("--balance", type=float, default=10_000.0, help="Starting balance")
    p.add_argument("--show-trades", type=int, default=10, help="Print first N trades")
    args = p.parse_args()

    if args.csv:
        df = load_csv(args.csv)
    elif args.demo:
        df = make_demo_data()
    else:
        p.error("Provide --csv PATH or --demo")

    engine, _ = run_backtest(df, balance=args.balance)
    stats = summarize(engine, args.balance)

    print("=" * 60)
    print("TF30M HMA20-EMA Cross Momentum -- Backtest Summary")
    print("=" * 60)
    print(f"Bars processed     : {len(df)}")
    print(f"Trades             : {stats['trades']}")
    print(f"Win rate           : {stats['win_rate']:.1%} "
          f"({stats['wins']}W / {stats['losses']}L)")
    print(f"Avg P&L per trade  : {stats['avg_pnl_pct']:.2%}")
    print(f"Profit factor      : {stats['profit_factor']:.2f}")
    print(f"Exit breakdown     : {stats['exit_breakdown']}")
    print(f"Starting balance   : {stats['starting_balance']:,.2f}")
    print(f"Ending balance     : {stats['ending_balance']:,.2f}")
    print(f"Return             : {stats['return_pct']:+.2f}%")

    if args.show_trades and engine.trades:
        print("\nFirst trades:")
        print(f"{'#':>3} {'dir':<5} {'entry':>9} {'exit':>9} {'reason':<11} {'pnl%':>7} score")
        for k, t in enumerate(engine.trades[: args.show_trades], 1):
            comps = t.snapshot["entry_confirmation_components"]
            passed = "".join(name[0] for name, ok in comps.items() if ok) or "-"
            print(f"{k:>3} {t.direction:<5} {t.entry_price:>9.3f} {t.exit_price:>9.3f} "
                  f"{t.reason:<11} {t.pnl_pct:>+6.2%} "
                  f"{t.snapshot['entry_confirmation_score']}/4 [{passed}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
