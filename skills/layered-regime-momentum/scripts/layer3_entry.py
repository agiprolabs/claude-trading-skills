#!/usr/bin/env python3
"""Layer 3 — Directional Entry (regime-locked, structure break).

Layer 1 (regime) + Layer 2 (bias) together say "yes, trade this direction
right now, or not at all" -- they never disagree with each other on
direction by construction (Layer 2's direction is read straight off Layer
1's state). Layer 3's only job is to find *where* to enter within whatever
direction is currently permitted, using **market structure**: a fresh break
above the last confirmed swing high triggers a long; a fresh break below
the last confirmed swing low triggers a short. A permitted uptrend can only
ever produce LONG signals -- SHORT is structurally impossible while
`layer2_direction == "BULL"`, and vice versa.

Swing detection (fractal, symmetric window `swing_lookback` bars each side):
a bar is a confirmed swing high once `swing_lookback` bars have closed
*after* it and none of them (nor the `swing_lookback` before it) has a
higher high. Confirmation is therefore always `swing_lookback` bars late by
construction -- there is no way to know a bar was a local peak until enough
subsequent price action has ruled out a higher one. This mirrors Layer 1's
close-time alignment discipline: nothing is used before it could actually
be known.

A break is a **one-shot trigger**: once `close` breaks above the current
swing high, that level is consumed (set back to "none") so the same
breakout doesn't refire every bar price stays above it -- a new swing high
must form before the next long trigger.

Usage:
    python layer3_entry.py --demo
    python layer3_entry.py --csv-1h btc_1h.csv --csv-30m btc_30m.csv --csv-15m btc_15m.csv

Dependencies:
    uv pip install pandas numpy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layer2_bias import layer2_bias  # noqa: E402

SWING_LOOKBACK = 3  # bars each side required to confirm a fractal swing point


def compute_structure_breaks(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> pd.DataFrame:
    """Walk forward bar by bar tracking confirmed swing highs/lows and firing
    one-shot break-of-structure signals.

    A plain sequential loop (not a vectorized rolling scan) is used
    deliberately: swing confirmation and break-detection both have state
    that depends on *when* something became knowable, not just on a fixed
    window's contents, and a loop is much easier to verify has no lookahead
    (see tests/test_layer3_entry.py).

    Returns columns: timestamp, last_swing_high, last_swing_low, bos_up, bos_down.
    """
    n = len(df)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()

    last_swing_high = np.full(n, np.nan)
    last_swing_low = np.full(n, np.nan)
    bos_up = np.zeros(n, dtype=bool)
    bos_down = np.zeros(n, dtype=bool)

    cur_high = np.nan
    cur_low = np.nan

    for i in range(n):
        # A candidate swing point at (i - lookback) is confirmable once bar i
        # has closed -- that gives it `lookback` bars on both sides, all
        # already known (no future data used).
        candidate = i - lookback
        if candidate >= lookback:
            h_window = high[candidate - lookback: i + 1]
            l_window = low[candidate - lookback: i + 1]
            h_max = h_window.max()
            l_min = l_window.min()
            if high[candidate] == h_max and (h_window == h_max).sum() == 1:
                cur_high = h_max
            if low[candidate] == l_min and (l_window == l_min).sum() == 1:
                cur_low = l_min

        last_swing_high[i] = cur_high
        last_swing_low[i] = cur_low

        if not np.isnan(cur_high) and close[i] > cur_high:
            bos_up[i] = True
            cur_high = np.nan  # consumed -- needs a fresh swing high before firing again
        if not np.isnan(cur_low) and close[i] < cur_low:
            bos_down[i] = True
            cur_low = np.nan

    return pd.DataFrame({
        "timestamp": df["timestamp"].reset_index(drop=True),
        "last_swing_high": last_swing_high,
        "last_swing_low": last_swing_low,
        "bos_up": bos_up,
        "bos_down": bos_down,
    })


def layer3_entry(df_1h: pd.DataFrame, df_30m: pd.DataFrame, df_15m: pd.DataFrame,
                  swing_lookback: int = SWING_LOOKBACK) -> pd.DataFrame:
    """Compute Layer 3 entries on the 15m grid (same grid Layer 2 uses).

    Returns Layer 2's full output plus: last_swing_high, last_swing_low,
    bos_up, bos_down, layer3_entry ('LONG'/'SHORT'/None).

    A LONG can only fire when layer2_direction == 'BULL' and layer2_pass is
    True (Layer 1/2 both permit it) *and* a fresh bos_up occurs on the same
    bar -- structurally impossible to go long in a permitted downtrend or
    short in a permitted uptrend.
    """
    result = layer2_bias(df_1h, df_30m, df_15m)
    structure = compute_structure_breaks(df_15m, swing_lookback)

    result["last_swing_high"] = structure["last_swing_high"].values
    result["last_swing_low"] = structure["last_swing_low"].values
    result["bos_up"] = structure["bos_up"].values
    result["bos_down"] = structure["bos_down"].values

    permit_long = (result["layer2_direction"] == "BULL") & result["layer2_pass"]
    permit_short = (result["layer2_direction"] == "SELL") & result["layer2_pass"]

    result["layer3_entry"] = np.select(
        [permit_long & result["bos_up"], permit_short & result["bos_down"]],
        ["LONG", "SHORT"],
        default=None,
    )
    return result


# ── Demo ──────────────────────────────────────────────────────────────────
def make_demo_data(n_15m: int = 4000, seed: int = 3) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    price = 100.0
    rows = []
    start_ms = 1_700_000_000_000
    step_ms = 15 * 60 * 1000
    for t in range(n_15m):
        regime = np.sin(t / 400.0)
        drift = regime * 0.06
        ret = drift + rng.normal(0, 0.3)
        open_ = price
        close = max(1.0, price + ret)
        high = max(open_, close) + abs(rng.normal(0, 0.15))
        low = min(open_, close) - abs(rng.normal(0, 0.15))
        vol = max(1.0, rng.normal(1000, 250) * (1 + 0.4 * abs(regime)))
        ts = start_ms + t * step_ms
        rows.append((ts, open_, high, low, close, vol))
        price = close
    df_15m = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])

    def resample(df: pd.DataFrame, bucket_ms: int) -> pd.DataFrame:
        d = df.copy()
        d["grp"] = d["timestamp"] // bucket_ms
        return d.groupby("grp").agg(
            timestamp=("timestamp", "first"), open=("open", "first"),
            high=("high", "max"), low=("low", "min"),
            close=("close", "last"), volume=("volume", "sum"),
        ).reset_index(drop=True)

    df_30m = resample(df_15m, 30 * 60 * 1000)
    df_1h = resample(df_15m, 60 * 60 * 1000)
    return df_1h, df_30m, df_15m


def main() -> int:
    p = argparse.ArgumentParser(description="Layer 3 -- directional entry (structure break)")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--csv-1h")
    p.add_argument("--csv-30m")
    p.add_argument("--csv-15m")
    p.add_argument("--swing-lookback", type=int, default=SWING_LOOKBACK)
    args = p.parse_args()

    if args.demo:
        df_1h, df_30m, df_15m = make_demo_data()
    elif args.csv_1h and args.csv_30m and args.csv_15m:
        df_1h = pd.read_csv(args.csv_1h)
        df_30m = pd.read_csv(args.csv_30m)
        df_15m = pd.read_csv(args.csv_15m)
    else:
        p.error("Provide --demo or all of --csv-1h, --csv-30m, --csv-15m")
        return 1

    result = layer3_entry(df_1h, df_30m, df_15m, args.swing_lookback)
    longs = (result["layer3_entry"] == "LONG").sum()
    shorts = (result["layer3_entry"] == "SHORT").sum()
    print(f"15m bars: {len(result)} | LONG signals: {longs} | SHORT signals: {shorts}")

    entries = result[result["layer3_entry"].notna()]
    print("\nLast 15 entry signals:")
    cols = ["timestamp", "layer1_regime", "layer2_score", "last_swing_high", "last_swing_low", "layer3_entry"]
    print(entries[cols].tail(15).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
