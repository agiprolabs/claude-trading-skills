#!/usr/bin/env python3
"""Layer 2 — Context Bias (1h + 15m dynamic scoring).

Takes Layer 1's regime (see layer1_regime.py) and checks whether momentum,
strength, and participation on 1h and 15m actually *support* that regime,
using the same four conditions as tf30m-hma-ema-momentum's confirmation
score (ROC9, RSI14, ADX14, Volume vs SMA20) -- but scored continuously
(0-100 "how strongly does this support the current direction") rather than
as a binary pass/fail count, since the strength of a signal matters, not
just whether it crossed a fixed line.

Per-indicator directional score (0-100, 100 = maximally supportive of the
Layer 1 direction):

    ROC9      -- rolling percentile rank of ROC9 (or -ROC9 for SELL) over
                 the lookback window. Momentum has no fixed scale across
                 assets/volatility regimes, so it's ranked against its own
                 recent history rather than compared to a fixed threshold.
    RSI14     -- already a natural 0-100 momentum gauge: used directly for
                 BULL, `100 - RSI14` for SELL.
    ADX14     -- rolling percentile rank of ADX14. Trend *strength* has no
                 direction of its own -- it amplifies whichever direction
                 Layer 1 already found, so the same score is used for BULL
                 and SELL.
    Volume    -- rolling percentile rank of (volume / volume_sma20).
                 Participation, same reasoning as ADX: non-directional.

A timeframe's bias score is the mean of its 4 component scores. Layer 2's
combined score is a weighted average of the 1h and 15m timeframe scores
(equal weight, 0.5/0.5, by default).

Pass threshold depends on how confirmed Layer 1 already is -- an early,
unconfirmed regime (EARLY_BULL/EARLY_SELL) demands stronger bias evidence
before Layer 3 is allowed to act on it than an already-fully-agreeing one
(BULL/SELL):

    layer1_regime      Layer 2 threshold
    BULL / SELL        score >= CONFIRMED_THRESHOLD (default 55)
    EARLY_BULL/SELL    score >= EARLY_THRESHOLD (default 70)
    NEUTRAL            no pass -- no direction to score bias against

Usage:
    python layer2_bias.py --demo
    python layer2_bias.py --csv-1h btc_1h.csv --csv-15m btc_15m.csv --csv-30m btc_30m.csv

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
from layer1_regime import align_htf_to_ltf, layer1_regime  # noqa: E402

ROC_PERIOD = 9
RSI_PERIOD = 14
ADX_PERIOD = 14
VOLUME_SMA_PERIOD = 20
PCTRANK_LOOKBACK = 100  # bars, for ROC/ADX/Volume percentile-rank normalization

CONFIRMED_THRESHOLD = 55.0   # pass threshold when Layer 1 is BULL/SELL
EARLY_THRESHOLD = 70.0       # pass threshold when Layer 1 is EARLY_BULL/EARLY_SELL

BULL_STATES = ("BULL", "EARLY_BULL")
SELL_STATES = ("SELL", "EARLY_SELL")
EARLY_STATES = ("EARLY_BULL", "EARLY_SELL")
CONFIRMED_STATES = ("BULL", "SELL")


# ── Indicators (self-contained; no cross-skill imports) ──────────────────
def roc(series: pd.Series, period: int = ROC_PERIOD) -> pd.Series:
    return (series / series.shift(period) - 1.0) * 100.0


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.where(avg_loss != 0.0, 100.0)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ADX_PERIOD) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    tr = _true_range(high, low, close)
    atr_w = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_w
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_w
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, adjust=False).mean()


def pctrank(series: pd.Series, lookback: int = PCTRANK_LOOKBACK) -> pd.Series:
    """Rolling percentile rank (0-100) of the current value within its own
    trailing `lookback`-bar window -- a data-adaptive alternative to a fixed
    threshold, since 'strong momentum' means something different on a
    volatile token than on a slow-moving index."""
    return series.rolling(lookback).rank(pct=True) * 100.0


# ── Per-timeframe bias components ────────────────────────────────────────
def compute_bias_components(df: pd.DataFrame, lookback: int = PCTRANK_LOOKBACK) -> pd.DataFrame:
    """Compute the four raw indicators plus their percentile-rank scores.

    Returns columns: timestamp, roc9, rsi14, adx14, vol_ratio,
    roc_pctrank, adx_pctrank, vol_pctrank (all 0-100 except the raw values).
    """
    out = df[["timestamp"]].copy()
    out["roc9"] = roc(df["close"])
    out["rsi14"] = rsi(df["close"])
    out["adx14"] = adx(df["high"], df["low"], df["close"])
    vol_sma = df["volume"].rolling(VOLUME_SMA_PERIOD).mean()
    out["vol_ratio"] = df["volume"] / vol_sma
    out["roc_pctrank"] = pctrank(out["roc9"], lookback)
    out["adx_pctrank"] = pctrank(out["adx14"], lookback)
    out["vol_pctrank"] = pctrank(out["vol_ratio"], lookback)
    return out


def directional_tf_score(bias: pd.DataFrame, direction: pd.Series) -> pd.Series:
    """Combine one timeframe's 4 components into a 0-100 score that supports
    `direction` ('BULL' or 'SELL' per row; any other value -> NaN).

    ROC: percentile rank in the direction's favor (BULL uses the rank as-is,
    SELL mirrors it: 100 - rank, equivalent to ranking -ROC9).
    RSI: used directly for BULL, mirrored (100 - RSI) for SELL.
    ADX / Volume: non-directional -- same percentile-rank score either way.
    """
    is_bull = direction == "BULL"
    is_sell = direction == "SELL"

    roc_score = np.select([is_bull, is_sell], [bias["roc_pctrank"], 100.0 - bias["roc_pctrank"]], default=np.nan)
    rsi_score = np.select([is_bull, is_sell], [bias["rsi14"], 100.0 - bias["rsi14"]], default=np.nan)
    adx_score = bias["adx_pctrank"].where(is_bull | is_sell, np.nan)
    vol_score = bias["vol_pctrank"].where(is_bull | is_sell, np.nan)

    return (pd.Series(roc_score, index=bias.index) + pd.Series(rsi_score, index=bias.index)
            + adx_score + vol_score) / 4.0


# ── Layer 2: combine Layer 1 direction with 1h + 15m bias ────────────────
def layer2_bias(df_1h: pd.DataFrame, df_30m: pd.DataFrame, df_15m: pd.DataFrame,
                 weight_1h: float = 0.5, lookback: int = PCTRANK_LOOKBACK,
                 confirmed_threshold: float = CONFIRMED_THRESHOLD,
                 early_threshold: float = EARLY_THRESHOLD) -> pd.DataFrame:
    """Compute Layer 2 on the 15m bar grid.

    Returns one row per 15m bar:
        timestamp, layer1_regime, layer1_confirmed,
        bias_1h, bias_15m, layer2_score, layer2_threshold, layer2_pass,
        layer2_direction ('BULL'/'SELL'/None)
    """
    l1 = layer1_regime(df_1h, df_30m)  # on the 30m grid

    result = pd.DataFrame({"timestamp": df_15m["timestamp"].reset_index(drop=True)})
    result["layer1_regime"] = align_htf_to_ltf(
        result["timestamp"], l1, "layer1_regime", source_column="layer1_regime"
    ).fillna("NEUTRAL")

    direction = pd.Series(
        np.select(
            [result["layer1_regime"].isin(BULL_STATES), result["layer1_regime"].isin(SELL_STATES)],
            ["BULL", "SELL"],
            default=None,
        ),
        index=result.index,
    )

    bias_1h_raw = compute_bias_components(df_1h, lookback)
    bias_15m_raw = compute_bias_components(df_15m, lookback)

    # Align the 1h bias score onto the 15m grid (no lookahead), then score
    # it against the (per-15m-bar) direction. The 15m bias is native to the
    # grid already, so it's scored directly.
    bias_1h_on_15m = pd.DataFrame({
        "timestamp": result["timestamp"],
        "roc_pctrank": align_htf_to_ltf(result["timestamp"], bias_1h_raw, "roc_pctrank", "roc_pctrank"),
        "rsi14": align_htf_to_ltf(result["timestamp"], bias_1h_raw, "rsi14", "rsi14"),
        "adx_pctrank": align_htf_to_ltf(result["timestamp"], bias_1h_raw, "adx_pctrank", "adx_pctrank"),
        "vol_pctrank": align_htf_to_ltf(result["timestamp"], bias_1h_raw, "vol_pctrank", "vol_pctrank"),
    })

    result["bias_1h"] = directional_tf_score(bias_1h_on_15m, direction)
    result["bias_15m"] = directional_tf_score(bias_15m_raw, direction)
    result["layer2_score"] = weight_1h * result["bias_1h"] + (1 - weight_1h) * result["bias_15m"]

    result["layer2_threshold"] = np.select(
        [result["layer1_regime"].isin(CONFIRMED_STATES), result["layer1_regime"].isin(EARLY_STATES)],
        [confirmed_threshold, early_threshold],
        default=np.nan,
    )
    result["layer2_pass"] = (
        direction.notna()
        & result["layer2_score"].notna()
        & (result["layer2_score"] >= result["layer2_threshold"])
    )
    result["layer2_direction"] = direction
    return result


# ── Demo ──────────────────────────────────────────────────────────────────
def make_demo_data(n_15m: int = 4000, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Synthetic 15m OHLCV with regime swings, resampled to 30m and 1h."""
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
    p = argparse.ArgumentParser(description="Layer 2 -- context bias (1h + 15m dynamic scoring)")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--csv-1h")
    p.add_argument("--csv-30m")
    p.add_argument("--csv-15m")
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

    result = layer2_bias(df_1h, df_30m, df_15m)
    n = len(result)
    n_pass = result["layer2_pass"].sum()
    print(f"15m bars: {n} | Layer2 PASS: {n_pass} ({n_pass/n:.1%})")
    print("\nBy Layer 1 state:")
    for state in ("NEUTRAL", "EARLY_BULL", "BULL", "EARLY_SELL", "SELL"):
        sub = result[result["layer1_regime"] == state]
        if len(sub) == 0:
            continue
        passed = sub["layer2_pass"].sum()
        print(f"  {state:12s} n={len(sub):5d}  pass={passed:5d} ({passed/len(sub):.1%})  "
              f"avg_score={sub['layer2_score'].mean():.1f}")
    print("\nLast 10 rows:")
    cols = ["timestamp", "layer1_regime", "bias_1h", "bias_15m", "layer2_score", "layer2_threshold", "layer2_pass"]
    print(result[cols].tail(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
