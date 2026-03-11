#!/usr/bin/env python3
"""Volume profile analysis for Solana tokens.

Builds hourly volume profiles, detects trends and anomalies, and identifies
peak trading hours. Useful for timing entries and understanding activity patterns.

Usage:
    python scripts/volume_profile.py                    # demo mode
    python scripts/volume_profile.py --demo             # explicit demo
    TOKEN_MINT=EPjF... BIRDEYE_API_KEY=xxx python scripts/volume_profile.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_MINT: Solana token mint address to analyze
    BIRDEYE_API_KEY: Birdeye API key (optional — falls back to demo data)
"""

import math
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import httpx
except ImportError:
    print("Install httpx: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────
TOKEN_MINT = os.getenv("TOKEN_MINT", "")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
DEMO_MODE = "--demo" in sys.argv or (not TOKEN_MINT and not BIRDEYE_API_KEY)

ANOMALY_THRESHOLD = 3.0  # Volume spike = 3x rolling average


# ── Data Fetching ──────────────────────────────────────────────────

def fetch_ohlcv_birdeye(
    token_mint: str, api_key: str, interval: str = "1H", limit: int = 168
) -> list[dict]:
    """Fetch OHLCV candle data from Birdeye.

    Args:
        token_mint: Token mint address.
        api_key: Birdeye API key.
        interval: Candle interval (1H, 4H, 1D).
        limit: Number of candles to fetch (168 = 7 days of hourly).

    Returns:
        List of candle dicts with keys: timestamp, open, high, low, close,
        volume_usd, trades_count.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    url = "https://public-api.birdeye.so/defi/ohlcv"
    headers = {"X-API-KEY": api_key, "accept": "application/json"}

    now = int(time.time())
    time_from = now - (limit * 3600)  # approximate for 1H candles

    params = {
        "address": token_mint,
        "type": interval,
        "time_from": time_from,
        "time_to": now,
    }

    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    candles: list[dict] = []
    for item in data.get("data", {}).get("items", []):
        candles.append({
            "timestamp": item.get("unixTime", 0),
            "open": item.get("o", 0),
            "high": item.get("h", 0),
            "low": item.get("l", 0),
            "close": item.get("c", 0),
            "volume_usd": item.get("v", 0),
            "trades_count": item.get("trades", 0),
        })

    candles.sort(key=lambda c: c["timestamp"])
    return candles


def generate_demo_candles(hours: int = 168) -> list[dict]:
    """Generate synthetic hourly candle data for demonstration.

    Creates realistic volume patterns with:
    - Daily cyclicality (higher during US/EU hours)
    - Random volume spikes
    - Gradual trend
    - Weekend dips

    Args:
        hours: Number of hourly candles to generate.

    Returns:
        List of candle dicts.
    """
    now = int(time.time())
    candles: list[dict] = []
    base_volume = 50000.0  # Base hourly volume in USD
    price = 0.001  # Starting price

    for i in range(hours):
        ts = now - (hours - i) * 3600
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour_of_day = dt.hour
        day_of_week = dt.weekday()

        # Daily cycle: peak at 14-18 UTC, low at 2-6 UTC
        hour_factor = 0.5 + 0.8 * math.sin(math.pi * (hour_of_day - 6) / 12) ** 2
        if hour_of_day < 6 or hour_of_day > 22:
            hour_factor *= 0.6

        # Weekend dip
        weekend_factor = 0.6 if day_of_week >= 5 else 1.0

        # Random variation
        noise = random.lognormvariate(0, 0.4)

        # Occasional spikes
        spike = 1.0
        if random.random() < 0.03:
            spike = random.uniform(3.0, 8.0)

        # Gradual volume trend (slight increase)
        trend = 1.0 + (i / hours) * 0.3

        volume = base_volume * hour_factor * weekend_factor * noise * spike * trend
        volume = max(100, volume)

        trades = max(1, int(volume / random.uniform(100, 500)))

        # Price random walk
        price *= 1 + random.gauss(0.0002, 0.01)
        o = price
        h = price * (1 + abs(random.gauss(0, 0.02)))
        l = price * (1 - abs(random.gauss(0, 0.02)))
        c = price * (1 + random.gauss(0, 0.005))
        price = c

        candles.append({
            "timestamp": ts,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume_usd": volume,
            "trades_count": trades,
        })

    return candles


# ── Analysis Functions ─────────────────────────────────────────────

def build_hourly_profile(candles: list[dict]) -> dict[int, dict]:
    """Aggregate candles by hour-of-day to build a volume profile.

    Args:
        candles: List of hourly candle dicts.

    Returns:
        Dict mapping hour (0-23) to aggregated stats.
    """
    profile: dict[int, dict] = {
        h: {"total_volume": 0, "candle_count": 0, "total_trades": 0, "volumes": []}
        for h in range(24)
    }

    for c in candles:
        dt = datetime.fromtimestamp(c["timestamp"], tz=timezone.utc)
        hour = dt.hour
        vol = c["volume_usd"]
        profile[hour]["total_volume"] += vol
        profile[hour]["candle_count"] += 1
        profile[hour]["total_trades"] += c.get("trades_count", 0)
        profile[hour]["volumes"].append(vol)

    for hour in range(24):
        p = profile[hour]
        count = p["candle_count"]
        if count > 0:
            p["avg_volume"] = p["total_volume"] / count
            p["avg_trades"] = p["total_trades"] / count
        else:
            p["avg_volume"] = 0
            p["avg_trades"] = 0

    return profile


def detect_volume_trend(candles: list[dict], window: int = 24) -> dict:
    """Detect volume trend by comparing recent vs prior period.

    Args:
        candles: List of hourly candle dicts, sorted by time.
        window: Hours to compare (default 24 = last day vs prior day).

    Returns:
        Dict with trend classification and ratio.
    """
    if len(candles) < window * 2:
        return {"trend": "insufficient_data", "ratio": 1.0}

    recent = candles[-window:]
    prior = candles[-window * 2 : -window]

    recent_vol = sum(c["volume_usd"] for c in recent)
    prior_vol = sum(c["volume_usd"] for c in prior)

    if prior_vol == 0:
        return {"trend": "no_prior_data", "ratio": 0}

    ratio = recent_vol / prior_vol

    if ratio > 1.5:
        trend = "strongly_increasing"
    elif ratio > 1.1:
        trend = "increasing"
    elif ratio > 0.9:
        trend = "stable"
    elif ratio > 0.5:
        trend = "decreasing"
    else:
        trend = "strongly_decreasing"

    return {
        "trend": trend,
        "ratio": ratio,
        "recent_volume_usd": recent_vol,
        "prior_volume_usd": prior_vol,
    }


def detect_anomalies(
    candles: list[dict], threshold: float = ANOMALY_THRESHOLD, lookback: int = 24
) -> list[dict]:
    """Identify volume anomalies (spikes exceeding threshold * rolling average).

    Args:
        candles: List of hourly candle dicts, sorted by time.
        threshold: Multiple of rolling average to flag as anomaly.
        lookback: Rolling window size in candles.

    Returns:
        List of anomaly dicts with timestamp, volume, average, and ratio.
    """
    anomalies: list[dict] = []

    for i in range(lookback, len(candles)):
        window = candles[i - lookback : i]
        avg = statistics.mean(c["volume_usd"] for c in window)
        current = candles[i]["volume_usd"]

        if avg > 0 and current / avg > threshold:
            dt = datetime.fromtimestamp(
                candles[i]["timestamp"], tz=timezone.utc
            )
            anomalies.append({
                "timestamp": candles[i]["timestamp"],
                "datetime": dt.strftime("%Y-%m-%d %H:%M UTC"),
                "volume_usd": current,
                "rolling_avg": avg,
                "ratio": current / avg,
            })

    return anomalies


def compute_volume_stats(candles: list[dict]) -> dict:
    """Compute summary volume statistics.

    Args:
        candles: List of candle dicts.

    Returns:
        Dict with total, mean, median, stdev, max, min volumes.
    """
    volumes = [c["volume_usd"] for c in candles]
    if not volumes:
        return {}

    return {
        "total_usd": sum(volumes),
        "mean_usd": statistics.mean(volumes),
        "median_usd": statistics.median(volumes),
        "stdev_usd": statistics.stdev(volumes) if len(volumes) > 1 else 0,
        "max_usd": max(volumes),
        "min_usd": min(volumes),
        "candle_count": len(volumes),
    }


# ── Reporting ──────────────────────────────────────────────────────

def print_bar(value: float, max_value: float, width: int = 30) -> str:
    """Generate a text-based bar for display.

    Args:
        value: Current value.
        max_value: Maximum value (full bar width).
        width: Character width of full bar.

    Returns:
        Bar string made of block characters.
    """
    if max_value <= 0:
        return ""
    filled = int((value / max_value) * width)
    filled = min(filled, width)
    return "\u2588" * filled


def print_report(candles: list[dict], token_label: str) -> None:
    """Print formatted volume profile report.

    Args:
        candles: List of hourly candle dicts.
        token_label: Display label for the token.
    """
    print("=" * 70)
    print(f"  VOLUME PROFILE — {token_label}")
    print(f"  Candles analyzed: {len(candles)}")
    if candles:
        start = datetime.fromtimestamp(candles[0]["timestamp"], tz=timezone.utc)
        end = datetime.fromtimestamp(candles[-1]["timestamp"], tz=timezone.utc)
        print(f"  Period: {start.strftime('%Y-%m-%d %H:%M')} to "
              f"{end.strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 70)

    # ── Summary Stats ──────────────────────────────────────────────
    stats = compute_volume_stats(candles)
    if stats:
        print("\n── Volume Summary ────────────────────────────────────")
        print(f"  Total Volume:  ${stats['total_usd']:>14,.0f}")
        print(f"  Hourly Mean:   ${stats['mean_usd']:>14,.0f}")
        print(f"  Hourly Median: ${stats['median_usd']:>14,.0f}")
        print(f"  Std Deviation: ${stats['stdev_usd']:>14,.0f}")
        print(f"  Max Hour:      ${stats['max_usd']:>14,.0f}")
        print(f"  Min Hour:      ${stats['min_usd']:>14,.0f}")

    # ── Hourly Profile ─────────────────────────────────────────────
    profile = build_hourly_profile(candles)
    max_avg = max(p["avg_volume"] for p in profile.values())

    print("\n── Hourly Volume Profile (UTC) ───────────────────────")
    print(f"  {'Hour':>4}  {'Avg Volume':>12}  {'Avg Trades':>10}  Bar")
    print(f"  {'----':>4}  {'----------':>12}  {'----------':>10}  ---")
    for hour in range(24):
        p = profile[hour]
        bar = print_bar(p["avg_volume"], max_avg)
        print(f"  {hour:>4}  ${p['avg_volume']:>10,.0f}  {p['avg_trades']:>10.0f}  {bar}")

    # Peak and quiet hours
    sorted_hours = sorted(
        range(24), key=lambda h: profile[h]["avg_volume"], reverse=True
    )
    peak_hours = sorted_hours[:3]
    quiet_hours = sorted_hours[-3:]

    print(f"\n  Peak hours (UTC):  {', '.join(f'{h:02d}:00' for h in sorted(peak_hours))}")
    print(f"  Quiet hours (UTC): {', '.join(f'{h:02d}:00' for h in sorted(quiet_hours))}")

    # ── Volume Trend ───────────────────────────────────────────────
    trend = detect_volume_trend(candles)
    print("\n── Volume Trend (24h vs prior 24h) ───────────────────")
    print(f"  Trend:          {trend['trend']}")
    print(f"  Ratio:          {trend.get('ratio', 0):.2f}x")
    if "recent_volume_usd" in trend:
        print(f"  Recent 24h:     ${trend['recent_volume_usd']:>12,.0f}")
        print(f"  Prior 24h:      ${trend['prior_volume_usd']:>12,.0f}")

    # ── Anomalies ──────────────────────────────────────────────────
    anomalies = detect_anomalies(candles)
    print(f"\n── Volume Anomalies (>{ANOMALY_THRESHOLD:.0f}x average) "
          f"──────────────────────")
    if anomalies:
        print(f"  Found {len(anomalies)} anomalies:")
        for a in anomalies[-10:]:  # Show most recent 10
            print(f"    {a['datetime']}  "
                  f"${a['volume_usd']:>10,.0f}  "
                  f"({a['ratio']:.1f}x avg)")
    else:
        print("  No volume anomalies detected.")

    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for volume profile analysis."""
    if DEMO_MODE:
        print("[DEMO MODE] Using synthetic candle data\n")
        candles = generate_demo_candles(168)
        print_report(candles, "DEMO TOKEN")
        return

    print(f"Fetching OHLCV for {TOKEN_MINT[:8]}...{TOKEN_MINT[-4:]}")

    if not BIRDEYE_API_KEY:
        print("  BIRDEYE_API_KEY not set. Use --demo for synthetic data.")
        sys.exit(1)

    try:
        candles = fetch_ohlcv_birdeye(TOKEN_MINT, BIRDEYE_API_KEY)
        print(f"  Fetched {len(candles)} hourly candles")
    except Exception as e:
        print(f"  Fetch failed: {e}")
        print("  Use --demo for synthetic data.")
        sys.exit(1)

    if not candles:
        print("  No candle data returned. Use --demo for synthetic data.")
        sys.exit(0)

    label = f"{TOKEN_MINT[:8]}...{TOKEN_MINT[-4:]}"
    print_report(candles, label)


if __name__ == "__main__":
    main()
