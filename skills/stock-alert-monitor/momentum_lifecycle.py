#!/usr/bin/env python3
"""Six-tier momentum lifecycle state machine for intraday alerts.

Turns a stream of intraday bars into staged buy / hold / sell alerts that follow
a single name through its momentum life: find it, confirm it, optimize the entry,
track continuation, detect weakness, declare failure.

    Tier 1  WATCHLIST    WATCH   "Stock added to active momentum watchlist."
    Tier 2  ENTRY_SETUP  BUY     "Primary momentum setup detected."
    Tier 3  OPTIMAL_ENTRY BUY    "Optimal pullback entry detected."
    Tier 4  ACCELERATION HOLD    "Momentum accelerating."
    Tier 5  WEAKNESS     REDUCE  "Momentum weakening."
    Tier 6  FAILURE      SELL    "Momentum setup invalidated."

Design
------
* **Feed-agnostic.** You push `Bar`s (from Polygon/Alpaca/Tradier/...) plus a
  light `Context` (30-day avg volume, previous close, premarket high, whether a
  news catalyst is live, halt count). The tracker owns VWAP / 9-EMA / opening
  range / RVOL and the transition logic.
* **State machine, not a pipeline.** Transitions are checked **risk-first**
  (Failure, then Weakness, then upgrades) so a breakdown is never masked by a
  stale buy. A name can skip stages (setup -> failure) or recover (weakness ->
  acceleration). Tier 6 removes the name; if it re-qualifies later it re-enters
  at Tier 1.
* **One alert per transition.** `on_bar` returns an `Alert` only when the tier
  changes, so you ping once per stage, not once per bar.
* Stdlib only. This is a discovery/workflow tool, not trade execution or advice.

The thresholds in `Config` are deliberately exposed and conservative — tune to
your instrument and timeframe.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Deque, Optional


class Tier(IntEnum):
    WATCHLIST = 1
    ENTRY_SETUP = 2
    OPTIMAL_ENTRY = 3
    ACCELERATION = 4
    WEAKNESS = 5
    FAILURE = 6


# Tier -> (buy/hold/sell bucket, headline message, suggested action)
SIGNAL = {
    Tier.WATCHLIST: "WATCH",
    Tier.ENTRY_SETUP: "BUY",
    Tier.OPTIMAL_ENTRY: "BUY",
    Tier.ACCELERATION: "HOLD",
    Tier.WEAKNESS: "REDUCE",
    Tier.FAILURE: "SELL",
}
MESSAGE = {
    Tier.WATCHLIST: "Stock added to active momentum watchlist.",
    Tier.ENTRY_SETUP: "Primary momentum setup detected.",
    Tier.OPTIMAL_ENTRY: "Optimal pullback entry detected.",
    Tier.ACCELERATION: "Momentum accelerating.",
    Tier.WEAKNESS: "Momentum weakening.",
    Tier.FAILURE: "Momentum setup invalidated.",
}
ACTION = {
    Tier.WATCHLIST: "Monitor closely — no entry setup yet.",
    Tier.ENTRY_SETUP: "Evaluate for entry.",
    Tier.OPTIMAL_ENTRY: "Highest-quality setup — best risk/reward.",
    Tier.ACCELERATION: "Reassess opportunity; monitor for continuation.",
    Tier.WEAKNESS: "Increased caution; consider trimming.",
    Tier.FAILURE: "Exit / remove from active watchlist.",
}


@dataclass
class Config:
    # Tier 1 — watchlist
    watch_rvol: float = 3.0          # RVOL > 3 puts it on the radar
    # Tier 2 — entry setup
    setup_vol_mult: float = 2.0      # bar volume > 2x previous bar
    opening_range_min: float = 15.0  # opening range = first N minutes
    max_spread_pct: float = 0.5      # (ask-bid)/price <= 0.5% when quote present
    # Tier 3 — optimal entry
    elevated_rvol: float = 2.0       # volume still elevated on the pullback
    pullback_touch_pct: float = 0.4  # low within 0.4% of VWAP/9EMA counts as a touch
    # Tier 4 — acceleration
    expansion_bars: int = 3          # N consecutive rising-volume bars
    # Tier 5 — weakness
    dry_rvol: float = 1.0            # RVOL falling below this = volume drying up
    failed_highs_for_weak: int = 2   # multiple failed highs
    # Tier 6 — failure
    vwap_loss_streak: int = 2        # consecutive closes below VWAP = invalidation
    session_minutes: float = 390.0   # regular session length for RVOL pacing


@dataclass
class Bar:
    """One intraday candle. `minutes_since_open` < 0 means premarket."""
    ts: float                 # epoch seconds (ordering only)
    open: float
    high: float
    low: float
    close: float
    volume: float
    minutes_since_open: float
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass
class Context:
    avg_vol_30d: float                 # 30-day average daily volume
    prev_close: float
    premarket_high: Optional[float] = None
    news_catalyst: bool = False
    halt_count: int = 0                # cumulative halts so far this session


@dataclass
class Alert:
    ticker: str
    tier: Tier
    signal: str
    message: str
    action: str
    reasons: list
    price: float
    vwap: float
    rvol: float
    ts: float

    def text(self) -> str:
        flt = f"{self.rvol:.1f}x" if not math.isnan(self.rvol) else "?"
        return (
            f"[{self.signal}] T{int(self.tier)} {self.ticker} ${self.price:.2f} "
            f"vwap ${self.vwap:.2f} rvol {flt} :: {self.message} "
            f"({'; '.join(self.reasons)})"
        )


@dataclass
class _State:
    tier: Optional[Tier] = None
    cum_pv: float = 0.0
    cum_v: float = 0.0
    ema9: Optional[float] = None
    highest_high: float = 0.0
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    prev_volume: Optional[float] = None
    prev_rvol: float = float("nan")
    recent_vols: Deque[float] = field(default_factory=lambda: deque(maxlen=4))
    vwap_loss_streak: int = 0
    failed_highs: int = 0
    entry_ref: Optional[float] = None
    stop_ref: Optional[float] = None
    halt_count: int = 0


_EMA_ALPHA = 2 / (9 + 1)


class MomentumTracker:
    """Per-ticker six-tier momentum state machine."""

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self._states: dict[str, _State] = {}

    # -- public API --------------------------------------------------------
    def on_bar(self, ticker: str, bar: Bar, ctx: Context) -> Optional[Alert]:
        st = self._states.get(ticker) or _State()
        self._update_indicators(st, bar)
        vwap = (st.cum_pv / st.cum_v) if st.cum_v else bar.close
        rvol = self._rvol(st, bar, ctx)
        flags = self._flags(st, bar, ctx, vwap, rvol)
        new_tier, reasons = self._transition(st.tier, st, flags)

        # roll per-bar memory forward (after flags computed)
        st.prev_volume = bar.volume
        st.prev_rvol = rvol
        st.halt_count = ctx.halt_count
        st.vwap_loss_streak = (st.vwap_loss_streak + 1) if bar.close < vwap else 0

        if new_tier is None or new_tier == st.tier:
            self._states[ticker] = st
            return None

        # entering a position tier: pin entry + stop references
        if new_tier in (Tier.ENTRY_SETUP, Tier.OPTIMAL_ENTRY) and st.entry_ref is None:
            st.entry_ref = bar.close
            st.stop_ref = st.or_low if st.or_low is not None else bar.low

        st.tier = new_tier
        alert = Alert(
            ticker=ticker, tier=new_tier, signal=SIGNAL[new_tier],
            message=MESSAGE[new_tier], action=ACTION[new_tier], reasons=reasons,
            price=bar.close, vwap=vwap, rvol=rvol, ts=bar.ts,
        )
        if new_tier == Tier.FAILURE:
            self._states.pop(ticker, None)   # invalidated -> drop; may re-enter at T1
        else:
            self._states[ticker] = st
        return alert

    # -- internals ---------------------------------------------------------
    def _update_indicators(self, st: _State, bar: Bar) -> None:
        typical = (bar.high + bar.low + bar.close) / 3
        st.cum_pv += typical * bar.volume
        st.cum_v += bar.volume
        st.ema9 = bar.close if st.ema9 is None else st.ema9 + _EMA_ALPHA * (bar.close - st.ema9)
        st.highest_high = max(st.highest_high, bar.high)
        if 0 <= bar.minutes_since_open <= self.cfg.opening_range_min:
            st.or_high = bar.high if st.or_high is None else max(st.or_high, bar.high)
            st.or_low = bar.low if st.or_low is None else min(st.or_low, bar.low)
        st.recent_vols.append(bar.volume)

    def _rvol(self, st: _State, bar: Bar, ctx: Context) -> float:
        if not ctx.avg_vol_30d:
            return float("nan")
        frac = max(bar.minutes_since_open, 1.0) / self.cfg.session_minutes
        frac = min(max(frac, 0.02), 1.0)
        expected = ctx.avg_vol_30d * frac
        return st.cum_v / expected if expected else float("nan")

    def _spread_ok(self, bar: Bar) -> bool:
        if bar.bid is None or bar.ask is None or bar.close <= 0:
            return True  # no quote -> don't block on spread
        return (bar.ask - bar.bid) / bar.close * 100 <= self.cfg.max_spread_pct

    def _flags(self, st: _State, bar: Bar, ctx: Context, vwap: float, rvol: float) -> dict:
        c = self.cfg
        rising = list(st.recent_vols)
        consec_expansion = (
            len(rising) >= c.expansion_bars
            and all(rising[-i - 1] < rising[-i] for i in range(1, c.expansion_bars))
        )
        new_high = bar.high >= st.highest_high
        ref = max(v for v in (vwap, st.ema9) if v is not None)
        near = min(v for v in (vwap, st.ema9) if v is not None)
        pullback = (
            bar.low <= ref * (1 + c.pullback_touch_pct / 100)
            and bar.close >= near * (1 - c.pullback_touch_pct / 100)
            and bar.close >= vwap
        )
        rvol_up = not math.isnan(rvol) and not math.isnan(st.prev_rvol) and rvol > st.prev_rvol
        failed_high = (
            st.or_high is not None and bar.high > st.or_high and bar.close < st.or_high
        )
        if failed_high:
            st.failed_highs += 1
        return {
            "premarket_break": ctx.premarket_high is not None and bar.high > ctx.premarket_high,
            "rvol": rvol,
            "volume_surge": not math.isnan(rvol) and rvol > c.watch_rvol,
            "news": ctx.news_catalyst,
            "orb_break": st.or_high is not None and bar.close > st.or_high,
            "vol_gt_prev": st.prev_volume is not None and bar.volume > c.setup_vol_mult * st.prev_volume,
            "above_vwap": bar.close > vwap,
            "spread_ok": self._spread_ok(bar),
            "pullback": pullback,
            "vol_elevated": not math.isnan(rvol) and rvol >= c.elevated_rvol,
            "new_high": new_high,
            "rvol_up": rvol_up,
            "consec_expansion": consec_expansion,
            "halts": ctx.halt_count > st.halt_count,
            "loss_vwap": bar.close < vwap,
            "failed_breakout": failed_high,
            "vol_dry": not math.isnan(rvol) and rvol < c.dry_rvol,
            "multi_failed_highs": st.failed_highs >= c.failed_highs_for_weak,
            "break_stop": st.stop_ref is not None and bar.low < st.stop_ref,
            "support_break": st.or_low is not None and bar.close < st.or_low,
            "vwap_loss_sustained": (st.vwap_loss_streak + (1 if bar.close < vwap else 0)) >= c.vwap_loss_streak,
        }

    def _transition(self, t: Optional[Tier], st: _State, f: dict):
        """Risk-first state machine. Returns (new_tier|None, reasons)."""
        active = {Tier.ENTRY_SETUP, Tier.OPTIMAL_ENTRY, Tier.ACCELERATION, Tier.WEAKNESS}

        # --- Failure (highest priority) — only once we have a position thesis
        if t in active:
            r = [k for k in ("break_stop", "support_break", "vwap_loss_sustained") if f[k]]
            if r:
                return Tier.FAILURE, _reasons(r)

        # --- Weakness
        if t in {Tier.ENTRY_SETUP, Tier.OPTIMAL_ENTRY, Tier.ACCELERATION}:
            r = [k for k in ("loss_vwap", "failed_breakout", "vol_dry", "multi_failed_highs") if f[k]]
            if r:
                return Tier.WEAKNESS, _reasons(r)

        # --- Acceleration (also the recovery path out of weakness)
        if t in {Tier.ENTRY_SETUP, Tier.OPTIMAL_ENTRY, Tier.WEAKNESS}:
            if f["new_high"] and f["rvol_up"] and (f["consec_expansion"] or f["halts"]) and f["above_vwap"]:
                return Tier.ACCELERATION, _reasons(["new_high", "rvol_up",
                                                    "consec_expansion" if f["consec_expansion"] else "halts"])

        # --- Optimal entry
        if t == Tier.ENTRY_SETUP:
            if f["pullback"] and f["above_vwap"] and f["vol_elevated"]:
                return Tier.OPTIMAL_ENTRY, _reasons(["pullback", "trend_intact", "vol_elevated"])

        # --- Entry setup
        if t == Tier.WATCHLIST:
            if f["orb_break"] and f["vol_gt_prev"] and f["above_vwap"] and f["spread_ok"]:
                return Tier.ENTRY_SETUP, _reasons(["orb_break", "vol_gt_2x_prev", "above_vwap", "spread_ok"])

        # --- Entry to watchlist
        if t is None:
            r = [k for k in ("premarket_break", "volume_surge", "news") if f[k]]
            if r:
                return Tier.WATCHLIST, _reasons(r)

        return None, []


_REASON_LABELS = {
    "premarket_break": "premarket high break",
    "volume_surge": "RVOL > 3",
    "news": "news catalyst",
    "orb_break": "opening-range breakout",
    "vol_gt_2x_prev": "volume > 2x prev candle",
    "above_vwap": "above VWAP",
    "spread_ok": "spread within limits",
    "pullback": "pullback to VWAP/9EMA",
    "trend_intact": "trend intact",
    "vol_elevated": "volume elevated",
    "new_high": "new intraday high",
    "rvol_up": "RVOL increasing",
    "consec_expansion": "consecutive volume expansion",
    "halts": "halt / strong continuation",
    "loss_vwap": "loss of VWAP",
    "failed_breakout": "failed breakout",
    "vol_dry": "volume drying up",
    "multi_failed_highs": "multiple failed highs",
    "break_stop": "break below stop reference",
    "support_break": "key support breakdown",
    "vwap_loss_sustained": "sustained close below VWAP",
}


def _reasons(keys: list) -> list:
    return [_REASON_LABELS.get(k, k) for k in keys]


if __name__ == "__main__":  # tiny synthetic walk-through
    trk = MomentumTracker()
    ctx = Context(avg_vol_30d=1_000_000, prev_close=4.00, premarket_high=4.20, news_catalyst=True)
    bars = [
        Bar(1, 4.10, 4.25, 4.05, 4.22, 400_000, -5),      # premarket break + news -> T1
        Bar(2, 4.22, 4.40, 4.20, 4.38, 250_000, 5),       # builds opening range
        Bar(3, 4.38, 4.55, 4.36, 4.52, 600_000, 16),      # ORB + 2x vol + >VWAP -> T2
        Bar(4, 4.52, 4.54, 4.36, 4.50, 650_000, 22),      # pullback to VWAP, vol elevated -> T3
        Bar(5, 4.50, 4.85, 4.49, 4.82, 800_000, 28),      # new high + rvol up + expansion -> T4
        Bar(6, 4.82, 4.83, 4.40, 4.40, 400_000, 34),      # loss of VWAP -> T5
        Bar(7, 4.40, 4.42, 4.05, 4.10, 300_000, 40),      # break support/stop -> T6
    ]
    for b in bars:
        a = trk.on_bar("DEMO", b, ctx)
        if a:
            print(a.text())
