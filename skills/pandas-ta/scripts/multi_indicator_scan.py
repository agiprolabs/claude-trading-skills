#!/usr/bin/env python3
"""Run multiple indicator strategy profiles and score signal alignment.

Defines three strategy profiles (trend following, mean reversion, momentum),
runs all three on the same OHLCV data, scores each strategy's current signal
strength, and reports which strategy is most aligned with current conditions.

Usage:
    python scripts/multi_indicator_scan.py              # Demo mode
    python scripts/multi_indicator_scan.py --demo       # Explicit demo mode
    python scripts/multi_indicator_scan.py --live       # Fetch from Birdeye API

Dependencies:
    uv pip install pandas pandas-ta httpx numpy

Environment Variables:
    BIRDEYE_API_KEY: Your Birdeye API key (required for --live mode)
    TOKEN_MINT: Solana token mint address (default: SOL)
"""

import argparse
import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta


# ── Configuration ───────────────────────────────────────────────────
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
TOKEN_MINT = os.getenv("TOKEN_MINT", "So11111111111111111111111111111111111111112")
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"


# ── Strategy Definitions ───────────────────────────────────────────
TREND_STRATEGY = ta.Strategy(
    name="Trend Following",
    description="EMA crossover with ADX filter and SuperTrend confirmation",
    ta=[
        {"kind": "ema", "length": 20},
        {"kind": "ema", "length": 50},
        {"kind": "adx", "length": 14},
        {"kind": "supertrend", "length": 10, "multiplier": 3.0},
        {"kind": "atr", "length": 14},
        {"kind": "sma", "length": 200},
    ],
)

REVERSION_STRATEGY = ta.Strategy(
    name="Mean Reversion",
    description="Oversold/overbought detection with BB and oscillators",
    ta=[
        {"kind": "rsi", "length": 14},
        {"kind": "bbands", "length": 20, "std": 2.0},
        {"kind": "stoch", "k": 14, "d": 3, "smooth_k": 3},
        {"kind": "cci", "length": 20},
        {"kind": "willr", "length": 14},
    ],
)

MOMENTUM_STRATEGY = ta.Strategy(
    name="Momentum",
    description="MACD + RSI + volume confirmation for momentum trades",
    ta=[
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "rsi", "length": 14},
        {"kind": "obv"},
        {"kind": "roc", "length": 10},
        {"kind": "mfi", "length": 14},
    ],
)


# ── Data Generation / Fetching ─────────────────────────────────────
def generate_demo_ohlcv(bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic crypto price action.

    Args:
        bars: Number of bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        OHLCV DataFrame with DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    price = 150.0
    prices = []

    for i in range(bars):
        # Add regime changes: trending and mean-reverting phases
        phase = (i // 50) % 3
        if phase == 0:
            drift = 0.001  # Uptrend
        elif phase == 1:
            drift = -0.0005  # Mild downtrend
        else:
            drift = 0.0  # Range

        ret = rng.normal(drift, 0.015)
        price *= (1 + ret)
        price = max(price, 1.0)

        intra_vol = abs(rng.normal(0, 0.008))
        high = price * (1 + intra_vol)
        low = price * (1 - intra_vol)
        open_price = price * (1 + rng.normal(0, 0.003))
        high = max(high, open_price, price)
        low = min(low, open_price, price)

        base_vol = rng.lognormal(mean=12, sigma=0.8)
        if rng.random() < 0.05:
            base_vol *= rng.uniform(3, 8)

        prices.append({
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(price, 4),
            "volume": round(base_vol, 2),
        })

    end_time = pd.Timestamp.now(tz="UTC").floor("h")
    index = pd.date_range(end=end_time, periods=bars, freq="1h")
    df = pd.DataFrame(prices, index=index)
    df.index.name = "datetime"
    return df


def fetch_ohlcv_birdeye(
    token_mint: str,
    interval: str = "1H",
    limit: int = 200,
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from the Birdeye API.

    Args:
        token_mint: Solana token mint address.
        interval: Candle interval.
        limit: Number of candles to fetch.

    Returns:
        OHLCV DataFrame or None on failure.
    """
    if not BIRDEYE_API_KEY:
        print("Error: BIRDEYE_API_KEY not set.")
        sys.exit(1)

    try:
        import httpx
    except ImportError:
        print("Error: httpx not installed. Run: uv pip install httpx")
        sys.exit(1)

    import time

    url = f"{BIRDEYE_BASE_URL}/defi/ohlcv"
    interval_seconds = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1H": 3600, "4H": 14400, "1D": 86400,
    }
    secs = interval_seconds.get(interval, 3600)
    time_to = int(time.time())
    time_from = time_to - (limit * secs)

    headers = {"X-API-KEY": BIRDEYE_API_KEY, "Accept": "application/json"}
    params = {
        "address": token_mint,
        "type": interval,
        "time_from": time_from,
        "time_to": time_to,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        print(f"Request error: {e}")
        return None

    items = data.get("data", {}).get("items", [])
    if not items:
        print("No data returned from Birdeye.")
        return None

    df = pd.DataFrame(items)
    df["datetime"] = pd.to_datetime(df["unixTime"], unit="s", utc=True)
    df = df.set_index("datetime").rename(columns={
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]].astype(float).sort_index()
    return df


# ── Strategy Scoring ───────────────────────────────────────────────
def score_trend(df: pd.DataFrame) -> dict:
    """Score trend following strategy signals.

    Evaluates EMA crossover, ADX strength, SuperTrend direction, and
    price position relative to SMA200.

    Args:
        df: DataFrame with trend strategy indicators computed.

    Returns:
        Dictionary with individual scores and total.
    """
    last = df.iloc[-1]
    scores: dict = {}

    # EMA crossover: EMA20 vs EMA50
    if "EMA_20" in df.columns and "EMA_50" in df.columns:
        if pd.notna(last["EMA_20"]) and pd.notna(last["EMA_50"]):
            diff_pct = (last["EMA_20"] - last["EMA_50"]) / last["EMA_50"] * 100
            scores["ema_cross"] = {
                "score": min(max(diff_pct * 10, -100), 100),
                "detail": f"EMA20/50 diff: {diff_pct:+.2f}%",
            }

    # ADX trend strength
    if "ADX_14" in df.columns and pd.notna(last.get("ADX_14")):
        adx = last["ADX_14"]
        if adx > 40:
            strength = 100
        elif adx > 25:
            strength = 60
        elif adx > 20:
            strength = 30
        else:
            strength = -20  # No trend = bad for trend strategy
        scores["adx"] = {"score": strength, "detail": f"ADX: {adx:.1f}"}

    # SuperTrend direction
    st_col = f"SUPERTd_10_3.0"
    if st_col in df.columns and pd.notna(last.get(st_col)):
        direction = int(last[st_col])
        scores["supertrend"] = {
            "score": direction * 80,
            "detail": f"SuperTrend: {'bullish' if direction == 1 else 'bearish'}",
        }

    # Price vs SMA200
    if "SMA_200" in df.columns and pd.notna(last.get("SMA_200")):
        above = last["close"] > last["SMA_200"]
        pct_diff = (last["close"] - last["SMA_200"]) / last["SMA_200"] * 100
        scores["sma200"] = {
            "score": min(max(pct_diff * 5, -100), 100),
            "detail": f"Price {'above' if above else 'below'} SMA200 by {abs(pct_diff):.1f}%",
        }

    total = sum(s["score"] for s in scores.values()) / max(len(scores), 1)
    return {"scores": scores, "total": round(total, 1)}


def score_reversion(df: pd.DataFrame) -> dict:
    """Score mean reversion strategy signals.

    Evaluates RSI, Bollinger Band position, Stochastic, CCI, and Williams %R
    for oversold/overbought conditions.

    Args:
        df: DataFrame with reversion strategy indicators computed.

    Returns:
        Dictionary with individual scores and total.
    """
    last = df.iloc[-1]
    scores: dict = {}

    # RSI: oversold = bullish for reversion buy
    if "RSI_14" in df.columns and pd.notna(last.get("RSI_14")):
        rsi = last["RSI_14"]
        # Map: 30→+100 (oversold=buy), 50→0, 70→-100 (overbought=sell)
        score = (50 - rsi) * 5
        scores["rsi"] = {
            "score": min(max(score, -100), 100),
            "detail": f"RSI: {rsi:.1f}",
        }

    # Bollinger Band %B
    if "BBP_20_2.0" in df.columns and pd.notna(last.get("BBP_20_2.0")):
        bbp = last["BBP_20_2.0"]
        # 0→+100 (at lower band=buy), 0.5→0, 1→-100 (at upper band=sell)
        score = (0.5 - bbp) * 200
        scores["bbands"] = {
            "score": min(max(score, -100), 100),
            "detail": f"BB %B: {bbp:.3f}",
        }

    # Stochastic %K
    stoch_col = "STOCHk_14_3_3"
    if stoch_col in df.columns and pd.notna(last.get(stoch_col)):
        stoch_k = last[stoch_col]
        score = (50 - stoch_k) * 2.5
        scores["stoch"] = {
            "score": min(max(score, -100), 100),
            "detail": f"Stoch %K: {stoch_k:.1f}",
        }

    # CCI
    cci_col = [c for c in df.columns if c.startswith("CCI_")]
    if cci_col and pd.notna(last.get(cci_col[0])):
        cci = last[cci_col[0]]
        score = -cci * 0.5  # CCI -200→+100, CCI +200→-100
        scores["cci"] = {
            "score": min(max(score, -100), 100),
            "detail": f"CCI: {cci:.1f}",
        }

    # Williams %R
    if "WILLR_14" in df.columns and pd.notna(last.get("WILLR_14")):
        willr = last["WILLR_14"]
        # -100→+100 (oversold=buy), -50→0, 0→-100 (overbought=sell)
        score = (-50 - willr) * 2
        scores["willr"] = {
            "score": min(max(score, -100), 100),
            "detail": f"Williams %R: {willr:.1f}",
        }

    total = sum(s["score"] for s in scores.values()) / max(len(scores), 1)
    return {"scores": scores, "total": round(total, 1)}


def score_momentum(df: pd.DataFrame) -> dict:
    """Score momentum strategy signals.

    Evaluates MACD histogram, RSI direction, OBV trend, ROC, and MFI
    for momentum strength.

    Args:
        df: DataFrame with momentum strategy indicators computed.

    Returns:
        Dictionary with individual scores and total.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    scores: dict = {}

    # MACD histogram
    macd_h = "MACDh_12_26_9"
    if macd_h in df.columns and pd.notna(last.get(macd_h)):
        val = last[macd_h]
        rising = val > (prev.get(macd_h, 0) if pd.notna(prev.get(macd_h)) else 0)
        score = 80 if val > 0 and rising else 40 if val > 0 else -40 if val < 0 and not rising else -80
        scores["macd"] = {"score": score, "detail": f"MACD-H: {val:.4f} ({'rising' if rising else 'falling'})"}

    # RSI momentum (above/below 50)
    if "RSI_14" in df.columns and pd.notna(last.get("RSI_14")):
        rsi = last["RSI_14"]
        score = (rsi - 50) * 2  # 60→+20, 40→-20
        scores["rsi"] = {
            "score": min(max(score, -100), 100),
            "detail": f"RSI: {rsi:.1f}",
        }

    # OBV trend (above/below 20-period SMA)
    if "OBV" in df.columns and pd.notna(last.get("OBV")):
        obv_sma = df["OBV"].rolling(20).mean().iloc[-1]
        if pd.notna(obv_sma) and obv_sma != 0:
            pct_diff = (last["OBV"] - obv_sma) / abs(obv_sma) * 100
            score = min(max(pct_diff * 2, -100), 100)
            scores["obv"] = {"score": score, "detail": f"OBV vs SMA20: {pct_diff:+.1f}%"}

    # ROC
    if "ROC_10" in df.columns and pd.notna(last.get("ROC_10")):
        roc = last["ROC_10"]
        score = min(max(roc * 10, -100), 100)
        scores["roc"] = {"score": score, "detail": f"ROC(10): {roc:+.2f}%"}

    # MFI
    if "MFI_14" in df.columns and pd.notna(last.get("MFI_14")):
        mfi = last["MFI_14"]
        score = (mfi - 50) * 2
        scores["mfi"] = {
            "score": min(max(score, -100), 100),
            "detail": f"MFI: {mfi:.1f}",
        }

    total = sum(s["score"] for s in scores.values()) / max(len(scores), 1)
    return {"scores": scores, "total": round(total, 1)}


# ── Display ─────────────────────────────────────────────────────────
def print_strategy_report(name: str, result: dict) -> None:
    """Print a formatted strategy score report.

    Args:
        name: Strategy name.
        result: Score dictionary from a score_* function.
    """
    total = result["total"]
    bar_len = 20
    filled = int(abs(total) / 100 * bar_len)
    if total >= 0:
        bar = "[" + "#" * filled + "." * (bar_len - filled) + "]"
        direction = "BULLISH"
    else:
        bar = "[" + "." * (bar_len - filled) + "#" * filled + "]"
        direction = "BEARISH"

    print(f"\n  {name}")
    print(f"  {'─' * 50}")

    for indicator_name, info in result["scores"].items():
        score = info["score"]
        detail = info["detail"]
        arrow = "▲" if score > 0 else "▼" if score < 0 else "─"
        print(f"    {arrow} {indicator_name:<14} {score:>+6.0f}  {detail}")

    print(f"  {'─' * 50}")
    print(f"    Total: {total:>+6.1f} / 100  {bar}  {direction}")


def print_recommendation(
    trend_result: dict,
    reversion_result: dict,
    momentum_result: dict,
) -> None:
    """Print which strategy best matches current conditions.

    Args:
        trend_result: Trend strategy scores.
        reversion_result: Mean reversion strategy scores.
        momentum_result: Momentum strategy scores.
    """
    strategies = {
        "Trend Following": trend_result["total"],
        "Mean Reversion": reversion_result["total"],
        "Momentum": momentum_result["total"],
    }

    # Find most aligned (highest absolute score with positive = bullish bias)
    best_name = max(strategies, key=lambda k: abs(strategies[k]))
    best_score = strategies[best_name]

    print("\n" + "=" * 60)
    print("  STRATEGY ALIGNMENT SUMMARY")
    print("=" * 60)

    for name, score in sorted(strategies.items(), key=lambda x: abs(x[1]), reverse=True):
        marker = " ◀ BEST FIT" if name == best_name else ""
        direction = "BULL" if score > 0 else "BEAR" if score < 0 else "FLAT"
        print(f"    {name:<20} {score:>+6.1f}  [{direction}]{marker}")

    print("-" * 60)

    if abs(best_score) < 20:
        print("  Condition: MIXED — no clear strategy alignment.")
        print("  Consider: Reducing position size or waiting for clearer signals.")
    elif best_score > 0:
        print(f"  Condition: {best_name} signals are bullish.")
        print(f"  Strength: {'Strong' if abs(best_score) > 60 else 'Moderate' if abs(best_score) > 35 else 'Weak'}")
    else:
        print(f"  Condition: {best_name} signals are bearish.")
        print(f"  Strength: {'Strong' if abs(best_score) > 60 else 'Moderate' if abs(best_score) > 35 else 'Weak'}")

    print("=" * 60)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run multi-strategy indicator scan and display results."""
    parser = argparse.ArgumentParser(description="Multi-indicator strategy scan")
    parser.add_argument("--live", action="store_true", help="Fetch live data from Birdeye API")
    parser.add_argument("--demo", action="store_true", help="Use synthetic demo data (default)")
    parser.add_argument("--bars", type=int, default=200, help="Number of bars (default: 200)")
    args = parser.parse_args()

    use_live = args.live and not args.demo

    if use_live:
        print(f"Fetching data from Birdeye for {TOKEN_MINT[:8]}...")
        df = fetch_ohlcv_birdeye(TOKEN_MINT, interval="1H", limit=args.bars)
        if df is None:
            print("Falling back to demo mode.")
            df = generate_demo_ohlcv(bars=args.bars)
    else:
        print("Using synthetic demo data (1H bars, SOL-like price action)")
        df = generate_demo_ohlcv(bars=args.bars)

    print(f"Data: {len(df)} bars | Price: {df['close'].iloc[-1]:.2f}")
    print(f"Range: {df.index[0]} to {df.index[-1]}")

    # Run each strategy on a copy to avoid column collisions
    print("\nRunning strategy scans...")

    # Trend
    df_trend = df.copy()
    df_trend.ta.strategy(TREND_STRATEGY)
    trend_result = score_trend(df_trend)
    print_strategy_report("Trend Following", trend_result)

    # Mean Reversion
    df_rev = df.copy()
    df_rev.ta.strategy(REVERSION_STRATEGY)
    reversion_result = score_reversion(df_rev)
    print_strategy_report("Mean Reversion", reversion_result)

    # Momentum
    df_mom = df.copy()
    df_mom.ta.strategy(MOMENTUM_STRATEGY)
    momentum_result = score_momentum(df_mom)
    print_strategy_report("Momentum", momentum_result)

    # Recommendation
    print_recommendation(trend_result, reversion_result, momentum_result)

    print("\nNote: This analysis is for informational and educational purposes only.")
    print("It does not constitute financial advice or a recommendation to trade.\n")


if __name__ == "__main__":
    main()
