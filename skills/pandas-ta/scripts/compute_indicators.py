#!/usr/bin/env python3
"""Compute standard technical indicators on OHLCV data and generate signal summary.

Fetches OHLCV data from the Birdeye API (or generates synthetic demo data) and
computes a standard set of indicators: RSI, MACD, Bollinger Bands, EMA(20,50),
ATR, OBV, and SuperTrend. Outputs a signal summary and the last 10 bars with
indicator values.

Usage:
    python scripts/compute_indicators.py              # Demo mode with synthetic data
    python scripts/compute_indicators.py --demo       # Explicit demo mode
    python scripts/compute_indicators.py --live       # Fetch from Birdeye API

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
TOKEN_MINT = os.getenv("TOKEN_MINT", "So11111111111111111111111111111111111111112")  # SOL
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"

# Indicator parameters
RSI_LENGTH = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_LENGTH = 20
BB_STD = 2.0
EMA_FAST = 20
EMA_SLOW = 50
ATR_LENGTH = 14
SUPERTREND_LENGTH = 10
SUPERTREND_MULTIPLIER = 3.0


# ── Demo Data Generation ───────────────────────────────────────────
def generate_demo_ohlcv(bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic price action.

    Creates a random walk with trend, mean reversion, and volume patterns
    that approximate real crypto price behavior on a 1h timeframe.

    Args:
        bars: Number of OHLCV bars to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns: open, high, low, close, volume and DatetimeIndex.
    """
    rng = np.random.default_rng(seed)

    # Start price around $150 (SOL-like)
    price = 150.0
    prices = []

    for _ in range(bars):
        # Random returns with slight upward drift and mean reversion
        ret = rng.normal(0.0002, 0.015)  # ~1.5% hourly vol
        price *= (1 + ret)
        price = max(price, 1.0)  # Floor at $1

        # Generate OHLC from close
        intra_vol = abs(rng.normal(0, 0.008))
        high = price * (1 + intra_vol)
        low = price * (1 - intra_vol)
        open_price = price * (1 + rng.normal(0, 0.003))

        # Ensure OHLC consistency
        high = max(high, open_price, price)
        low = min(low, open_price, price)

        # Volume with some spikes
        base_vol = rng.lognormal(mean=12, sigma=0.8)
        if rng.random() < 0.05:  # 5% chance of volume spike
            base_vol *= rng.uniform(3, 8)

        prices.append({
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(price, 4),
            "volume": round(base_vol, 2),
        })

    # Create DatetimeIndex (1h bars)
    end_time = pd.Timestamp.now(tz="UTC").floor("h")
    index = pd.date_range(end=end_time, periods=bars, freq="1h")

    df = pd.DataFrame(prices, index=index)
    df.index.name = "datetime"
    return df


# ── Birdeye API Fetch ──────────────────────────────────────────────
def fetch_ohlcv_birdeye(
    token_mint: str,
    interval: str = "1H",
    limit: int = 200,
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from the Birdeye API.

    Args:
        token_mint: Solana token mint address.
        interval: Candle interval (1m, 5m, 15m, 30m, 1H, 4H, 1D).
        limit: Number of candles to fetch (max 1000).

    Returns:
        DataFrame with OHLCV data, or None if the request fails.

    Raises:
        SystemExit: If BIRDEYE_API_KEY is not set.
    """
    if not BIRDEYE_API_KEY:
        print("Error: BIRDEYE_API_KEY environment variable not set.")
        print("Set it with: export BIRDEYE_API_KEY=your_key_here")
        sys.exit(1)

    try:
        import httpx
    except ImportError:
        print("Error: httpx not installed. Run: uv pip install httpx")
        sys.exit(1)

    import time

    url = f"{BIRDEYE_BASE_URL}/defi/ohlcv"
    time_to = int(time.time())
    # Map interval to seconds for time_from calculation
    interval_seconds = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1H": 3600, "4H": 14400, "1D": 86400,
    }
    secs = interval_seconds.get(interval, 3600)
    time_from = time_to - (limit * secs)

    params = {
        "address": token_mint,
        "type": interval,
        "time_from": time_from,
        "time_to": time_to,
    }
    headers = {
        "X-API-KEY": BIRDEYE_API_KEY,
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code} — {e.response.text[:200]}")
        return None
    except httpx.RequestError as e:
        print(f"Request error: {e}")
        return None

    items = data.get("data", {}).get("items", [])
    if not items:
        print("No OHLCV data returned from Birdeye.")
        return None

    df = pd.DataFrame(items)
    df["datetime"] = pd.to_datetime(df["unixTime"], unit="s", utc=True)
    df = df.set_index("datetime")
    df = df.rename(columns={
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df.sort_index()
    return df


# ── Indicator Computation ──────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute standard technical indicators on an OHLCV DataFrame.

    Adds the following indicators as new columns:
    - RSI(14), MACD(12,26,9), Bollinger Bands(20,2), EMA(20), EMA(50),
      ATR(14), OBV, SuperTrend(10,3)

    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume.

    Returns:
        DataFrame with indicator columns appended.
    """
    df = df.copy()

    # Trend
    df[f"EMA_{EMA_FAST}"] = df.ta.ema(length=EMA_FAST)
    df[f"EMA_{EMA_SLOW}"] = df.ta.ema(length=EMA_SLOW)

    st = df.ta.supertrend(length=SUPERTREND_LENGTH, multiplier=SUPERTREND_MULTIPLIER)
    if st is not None:
        df = pd.concat([df, st], axis=1)

    # Momentum
    df[f"RSI_{RSI_LENGTH}"] = df.ta.rsi(length=RSI_LENGTH)

    macd = df.ta.macd(fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
    if macd is not None:
        df = pd.concat([df, macd], axis=1)

    # Volatility
    bb = df.ta.bbands(length=BB_LENGTH, std=BB_STD)
    if bb is not None:
        df = pd.concat([df, bb], axis=1)

    df[f"ATRr_{ATR_LENGTH}"] = df.ta.atr(length=ATR_LENGTH)

    # Volume
    df["OBV"] = df.ta.obv()

    return df


# ── Signal Generation ──────────────────────────────────────────────
def generate_signals(df: pd.DataFrame) -> dict:
    """Generate trading signals from computed indicators.

    Evaluates the last bar's indicator values and classifies each
    as bullish, bearish, or neutral.

    Args:
        df: DataFrame with indicator columns (from compute_indicators).

    Returns:
        Dictionary with signal assessments per indicator and overall bias.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals: dict = {}

    # RSI
    rsi_col = f"RSI_{RSI_LENGTH}"
    if rsi_col in df.columns and pd.notna(last[rsi_col]):
        rsi_val = last[rsi_col]
        if rsi_val < 30:
            signals["RSI"] = {"value": round(rsi_val, 2), "signal": "oversold (bullish reversal zone)"}
        elif rsi_val > 70:
            signals["RSI"] = {"value": round(rsi_val, 2), "signal": "overbought (bearish reversal zone)"}
        elif rsi_val > 50:
            signals["RSI"] = {"value": round(rsi_val, 2), "signal": "bullish momentum"}
        else:
            signals["RSI"] = {"value": round(rsi_val, 2), "signal": "bearish momentum"}

    # MACD
    macd_h_col = f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    if macd_h_col in df.columns and pd.notna(last[macd_h_col]):
        macd_val = last[macd_h_col]
        macd_prev = prev[macd_h_col] if pd.notna(prev[macd_h_col]) else 0
        if macd_val > 0 and macd_val > macd_prev:
            signals["MACD"] = {"value": round(macd_val, 4), "signal": "bullish (histogram rising)"}
        elif macd_val > 0:
            signals["MACD"] = {"value": round(macd_val, 4), "signal": "bullish (histogram falling)"}
        elif macd_val < 0 and macd_val < macd_prev:
            signals["MACD"] = {"value": round(macd_val, 4), "signal": "bearish (histogram falling)"}
        else:
            signals["MACD"] = {"value": round(macd_val, 4), "signal": "bearish (histogram rising)"}

    # EMA crossover
    ema_f_col = f"EMA_{EMA_FAST}"
    ema_s_col = f"EMA_{EMA_SLOW}"
    if ema_f_col in df.columns and ema_s_col in df.columns:
        if pd.notna(last[ema_f_col]) and pd.notna(last[ema_s_col]):
            if last[ema_f_col] > last[ema_s_col]:
                signals["EMA_Cross"] = {
                    "value": f"{last[ema_f_col]:.4f} / {last[ema_s_col]:.4f}",
                    "signal": "bullish (fast above slow)",
                }
            else:
                signals["EMA_Cross"] = {
                    "value": f"{last[ema_f_col]:.4f} / {last[ema_s_col]:.4f}",
                    "signal": "bearish (fast below slow)",
                }

    # Bollinger Bands position
    bbp_col = f"BBP_{BB_LENGTH}_{BB_STD}"
    if bbp_col in df.columns and pd.notna(last[bbp_col]):
        bbp = last[bbp_col]
        if bbp < 0:
            signals["BBands"] = {"value": round(bbp, 4), "signal": "below lower band (oversold)"}
        elif bbp > 1:
            signals["BBands"] = {"value": round(bbp, 4), "signal": "above upper band (overbought)"}
        elif bbp < 0.3:
            signals["BBands"] = {"value": round(bbp, 4), "signal": "near lower band (bullish zone)"}
        elif bbp > 0.7:
            signals["BBands"] = {"value": round(bbp, 4), "signal": "near upper band (bearish zone)"}
        else:
            signals["BBands"] = {"value": round(bbp, 4), "signal": "mid-band (neutral)"}

    # SuperTrend
    st_d_col = f"SUPERTd_{SUPERTREND_LENGTH}_{SUPERTREND_MULTIPLIER}"
    if st_d_col in df.columns and pd.notna(last[st_d_col]):
        st_dir = int(last[st_d_col])
        signals["SuperTrend"] = {
            "value": st_dir,
            "signal": "bullish" if st_dir == 1 else "bearish",
        }

    # ATR (informational)
    atr_col = f"ATRr_{ATR_LENGTH}"
    if atr_col in df.columns and pd.notna(last[atr_col]):
        atr_val = last[atr_col]
        atr_pct = (atr_val / last["close"]) * 100
        signals["ATR"] = {
            "value": round(atr_val, 4),
            "signal": f"{atr_pct:.2f}% of price (volatility gauge)",
        }

    # OBV trend
    if "OBV" in df.columns and pd.notna(last["OBV"]):
        obv_sma = df["OBV"].rolling(20).mean().iloc[-1]
        if pd.notna(obv_sma):
            if last["OBV"] > obv_sma:
                signals["OBV"] = {"value": int(last["OBV"]), "signal": "above 20-bar average (accumulation)"}
            else:
                signals["OBV"] = {"value": int(last["OBV"]), "signal": "below 20-bar average (distribution)"}

    # Overall bias
    bullish_count = sum(
        1 for s in signals.values()
        if "bullish" in str(s.get("signal", "")).lower()
        or "oversold" in str(s.get("signal", "")).lower()
        or "accumulation" in str(s.get("signal", "")).lower()
    )
    bearish_count = sum(
        1 for s in signals.values()
        if "bearish" in str(s.get("signal", "")).lower()
        or "overbought" in str(s.get("signal", "")).lower()
        or "distribution" in str(s.get("signal", "")).lower()
    )
    total = len(signals)
    if total > 0:
        if bullish_count > bearish_count + 1:
            signals["_overall"] = "BULLISH"
        elif bearish_count > bullish_count + 1:
            signals["_overall"] = "BEARISH"
        else:
            signals["_overall"] = "NEUTRAL"
        signals["_score"] = f"{bullish_count} bullish / {bearish_count} bearish / {total - bullish_count - bearish_count} neutral"

    return signals


# ── Display ─────────────────────────────────────────────────────────
def print_signal_summary(signals: dict) -> None:
    """Print a formatted signal summary.

    Args:
        signals: Dictionary from generate_signals().
    """
    print("\n" + "=" * 60)
    print("  SIGNAL SUMMARY")
    print("=" * 60)

    overall = signals.pop("_overall", "N/A")
    score = signals.pop("_score", "")

    for name, info in signals.items():
        if isinstance(info, dict):
            print(f"  {name:<14} {str(info['value']):>12}  →  {info['signal']}")

    print("-" * 60)
    print(f"  Overall Bias: {overall}")
    if score:
        print(f"  Score:        {score}")
    print("=" * 60)


def print_last_bars(df: pd.DataFrame, n: int = 10) -> None:
    """Print the last N bars with key indicator values.

    Args:
        df: DataFrame with OHLCV and indicator columns.
        n: Number of bars to display.
    """
    display_cols = ["close", f"RSI_{RSI_LENGTH}", f"EMA_{EMA_FAST}", f"EMA_{EMA_SLOW}"]

    macd_h_col = f"MACDh_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"
    if macd_h_col in df.columns:
        display_cols.append(macd_h_col)

    bbp_col = f"BBP_{BB_LENGTH}_{BB_STD}"
    if bbp_col in df.columns:
        display_cols.append(bbp_col)

    atr_col = f"ATRr_{ATR_LENGTH}"
    if atr_col in df.columns:
        display_cols.append(atr_col)

    available_cols = [c for c in display_cols if c in df.columns]

    print(f"\n  Last {n} bars:")
    print("-" * 100)
    tail = df[available_cols].tail(n)
    # Format for readable output
    with pd.option_context("display.float_format", "{:.4f}".format, "display.width", 120):
        print(tail.to_string())
    print()


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Main entry point: fetch data, compute indicators, display signals."""
    parser = argparse.ArgumentParser(description="Compute technical indicators on OHLCV data")
    parser.add_argument("--live", action="store_true", help="Fetch live data from Birdeye API")
    parser.add_argument("--demo", action="store_true", help="Use synthetic demo data (default)")
    parser.add_argument("--bars", type=int, default=200, help="Number of bars (default: 200)")
    args = parser.parse_args()

    # Default to demo mode
    use_live = args.live and not args.demo

    if use_live:
        print(f"Fetching OHLCV data from Birdeye for {TOKEN_MINT[:8]}...")
        df = fetch_ohlcv_birdeye(TOKEN_MINT, interval="1H", limit=args.bars)
        if df is None:
            print("Failed to fetch live data. Falling back to demo mode.")
            df = generate_demo_ohlcv(bars=args.bars)
    else:
        print("Using synthetic demo data (1H bars, SOL-like price action)")
        df = generate_demo_ohlcv(bars=args.bars)

    print(f"Data: {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    print(f"Price range: {df['close'].min():.2f} — {df['close'].max():.2f}")

    # Compute indicators
    print("\nComputing indicators...")
    df = compute_indicators(df)

    indicator_cols = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
    print(f"Added {len(indicator_cols)} indicator columns")

    # Generate and display signals
    signals = generate_signals(df)
    print_signal_summary(signals)

    # Show last N bars
    print_last_bars(df, n=10)

    # Information notice
    print("Note: This output is for informational and educational purposes only.")
    print("It does not constitute financial advice or a recommendation to trade.\n")


if __name__ == "__main__":
    main()
