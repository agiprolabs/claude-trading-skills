#!/usr/bin/env python3
"""Layer 1 — Regime Agreement (1h + 30m).

Determines the tradeable regime by requiring two timeframes to agree on
direction. Each timeframe's regime is the **slope of HMA(20)** on that
timeframe's own closes (rising = UP, falling = DOWN, unchanged = NEUTRAL).
Layer 1 "passes" only when both timeframes agree on a non-neutral direction:

    1h == UP   AND  30m == UP    -> PASS, regime = UP
    1h == DOWN AND  30m == DOWN  -> PASS, regime = DOWN
    anything else                -> NO PASS, regime = NEUTRAL

This is the first of four layers in the layered-regime-momentum strategy:

    Layer 1 (this file) -- regime agreement, 1h + 30m
    Layer 2             -- context bias / dynamic scoring, 1h + 15m
    Layer 3             -- directional entry (regime-locked), structure/cross
    Layer 4             -- risk management, 5% margin, 2 positions, 1:1.2 R:R

Only Layer 1 is implemented so far -- see SKILL.md for status.

Alignment / no-lookahead:
    The 1h regime is computed on 1h bars, then aligned onto the 30m bar grid
    with an "as-of, backward" join: at 30m bar close, we use the most
    recently *closed* 1h bar's regime, never a still-forming or future one.
    This mirrors how a live bot would poll both timeframes -- the 1h
    indicator only updates once per hour, four 30m bars at a time.

Usage:
    python layer1_regime.py --demo
    python layer1_regime.py --csv-1h btc_1h.csv --csv-30m btc_30m.csv

Dependencies:
    uv pip install pandas numpy
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

HMA_PERIOD = 20


# ── Indicators (self-contained; no cross-skill imports) ─────────────────
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


# ── Per-timeframe regime ─────────────────────────────────────────────────
def compute_tf_regime(df: pd.DataFrame, hma_period: int = HMA_PERIOD) -> pd.DataFrame:
    """Classify each bar's regime from HMA(20) slope on this timeframe.

    Args:
        df: OHLCV with at least 'timestamp' (ms epoch, ascending) and 'close'.

    Returns:
        DataFrame with columns: timestamp, hma20, regime ('UP'/'DOWN'/'NEUTRAL').
        NEUTRAL during HMA warmup (insufficient bars) or on an exact flat tie.
    """
    out = df[["timestamp", "close"]].copy()
    out["hma20"] = hma(out["close"], hma_period)
    prev = out["hma20"].shift(1)
    conditions = [out["hma20"] > prev, out["hma20"] < prev]
    out["regime"] = np.select(conditions, ["UP", "DOWN"], default="NEUTRAL")
    out.loc[out["hma20"].isna() | prev.isna(), "regime"] = "NEUTRAL"
    return out[["timestamp", "hma20", "regime"]]


# ── Cross-timeframe alignment (no lookahead) ─────────────────────────────
def _infer_interval_ms(timestamps: pd.Series) -> int:
    """Infer a series' bar interval as the median gap between consecutive
    timestamps -- robust to the occasional missing bar."""
    diffs = pd.Series(timestamps).diff().dropna()
    return int(diffs.median())


def align_htf_to_ltf(ltf_timestamps: pd.Series, htf_regime: pd.DataFrame,
                      column_name: str) -> pd.Series:
    """As-of (backward) join: for each LTF bar, take the most recently
    *closed* HTF bar's regime.

    `timestamp` throughout this module is a bar's **open** time (the ccxt/
    Binance convention). A bar is only actually closed at open_time +
    interval. Joining directly on open-time timestamps would match an HTF
    bar that has merely *opened* by the LTF bar's timestamp, not one that has
    *closed* -- a one-bar lookahead. Converting both sides to close time
    before the as-of join removes that off-by-one regardless of the two
    timeframes' relative sizes.
    """
    ltf_ts = pd.Series(ltf_timestamps).reset_index(drop=True)
    ltf_interval = _infer_interval_ms(ltf_ts)
    htf_interval = _infer_interval_ms(htf_regime["timestamp"])

    left = pd.DataFrame({
        "close_time": ltf_ts + ltf_interval,
        "_order": range(len(ltf_ts)),
    }).sort_values("close_time")
    right = pd.DataFrame({
        "close_time": htf_regime["timestamp"] + htf_interval,
        column_name: htf_regime["regime"].values,
    }).sort_values("close_time")

    merged = pd.merge_asof(left, right, on="close_time", direction="backward")
    return merged.sort_values("_order")[column_name].reset_index(drop=True)


# ── Layer 1: regime agreement ────────────────────────────────────────────
def layer1_regime(df_1h: pd.DataFrame, df_30m: pd.DataFrame) -> pd.DataFrame:
    """Compute Layer 1 regime agreement on the 30m bar grid.

    Returns a DataFrame (one row per 30m bar) with columns:
        timestamp, regime_1h, regime_30m, layer1_regime, layer1_pass
    """
    r1h = compute_tf_regime(df_1h)
    r30 = compute_tf_regime(df_30m)

    result = pd.DataFrame({"timestamp": r30["timestamp"]})
    result["regime_30m"] = r30["regime"].values
    result["regime_1h"] = align_htf_to_ltf(result["timestamp"], r1h, "regime_1h")
    result["regime_1h"] = result["regime_1h"].fillna("NEUTRAL")

    agree_up = (result["regime_1h"] == "UP") & (result["regime_30m"] == "UP")
    agree_down = (result["regime_1h"] == "DOWN") & (result["regime_30m"] == "DOWN")
    result["layer1_regime"] = np.select([agree_up, agree_down], ["UP", "DOWN"], default="NEUTRAL")
    result["layer1_pass"] = agree_up | agree_down
    return result


# ── Demo / self-test ──────────────────────────────────────────────────────
def make_demo_data(n_30m: int = 2000, seed: int = 11) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic 30m OHLCV with regime swings, plus its 1h resample."""
    rng = np.random.default_rng(seed)
    price = 100.0
    rows = []
    start_ms = 1_700_000_000_000
    step_ms = 30 * 60 * 1000
    for t in range(n_30m):
        regime = np.sin(t / 200.0)
        drift = regime * 0.10
        ret = drift + rng.normal(0, 0.35)
        open_ = price
        close = max(1.0, price + ret)
        high = max(open_, close) + abs(rng.normal(0, 0.2))
        low = min(open_, close) - abs(rng.normal(0, 0.2))
        vol = max(1.0, rng.normal(1000, 200))
        ts = start_ms + t * step_ms
        rows.append((ts, open_, high, low, close, vol))
        price = close
    df_30m = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])

    # Build 1h bars by resampling the 30m series (2 bars -> 1).
    df = df_30m.copy()
    df["grp"] = df["timestamp"] // (60 * 60 * 1000)
    agg = df.groupby("grp").agg(
        timestamp=("timestamp", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index(drop=True)
    return agg, df_30m


def main() -> int:
    p = argparse.ArgumentParser(description="Layer 1 -- regime agreement (1h + 30m)")
    p.add_argument("--demo", action="store_true", help="Run on synthetic data")
    p.add_argument("--csv-1h", help="Path to 1h OHLCV CSV")
    p.add_argument("--csv-30m", help="Path to 30m OHLCV CSV")
    args = p.parse_args()

    if args.demo:
        df_1h, df_30m = make_demo_data()
    elif args.csv_1h and args.csv_30m:
        df_1h = pd.read_csv(args.csv_1h)
        df_30m = pd.read_csv(args.csv_30m)
    else:
        p.error("Provide --demo or both --csv-1h and --csv-30m")
        return 1

    result = layer1_regime(df_1h, df_30m)
    warm = result["regime_1h"].eq("NEUTRAL").sum()
    n_pass = result["layer1_pass"].sum()
    print(f"30m bars: {len(result)} | Layer1 PASS bars: {n_pass} ({n_pass/len(result):.1%}) "
          f"| still-neutral 1h (warmup): {warm}")
    print(result["layer1_regime"].value_counts().to_string())
    print("\nLast 15 rows:")
    print(result.tail(15).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
