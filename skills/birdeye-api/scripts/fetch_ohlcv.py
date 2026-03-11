#!/usr/bin/env python3
"""Fetch OHLCV candle data from Birdeye with automatic pagination.

Retrieves historical price candles for any Solana token and outputs as
a pandas DataFrame suitable for backtesting. Handles the 1000-candle
per-request limit by sliding the time window automatically.

Usage:
    python scripts/fetch_ohlcv.py
    TOKEN_ADDRESS="EPjFWdd5..." TIMEFRAME="1H" python scripts/fetch_ohlcv.py

Dependencies:
    uv pip install httpx pandas python-dotenv

Environment Variables:
    BIRDEYE_API_KEY: Your Birdeye API key
    TOKEN_ADDRESS: Token mint address (default: SOL)
    TIMEFRAME: Candle interval (default: 1H)
    DAYS_BACK: How many days of history to fetch (default: 30)
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import pandas as pd

# ── Configuration ───────────────────────────────────────────────────

API_KEY = os.getenv("BIRDEYE_API_KEY", "")
if not API_KEY:
    print("Set BIRDEYE_API_KEY environment variable")
    print("  Get a key at https://birdeye.so")
    sys.exit(1)

TOKEN_ADDRESS = os.getenv(
    "TOKEN_ADDRESS", "So11111111111111111111111111111111111111112"
)
TIMEFRAME = os.getenv("TIMEFRAME", "1H")
DAYS_BACK = int(os.getenv("DAYS_BACK", "30"))

BASE_URL = "https://public-api.birdeye.so"
HEADERS = {
    "X-API-KEY": API_KEY,
    "x-chain": "solana",
    "accept": "application/json",
}

# Seconds per candle for each timeframe
TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1H": 3600, "2H": 7200, "4H": 14400, "6H": 21600,
    "8H": 28800, "12H": 43200, "1D": 86400, "3D": 259200,
    "1W": 604800, "1M": 2592000,
}

# Rate limit: pause between requests
RATE_LIMIT_DELAY = 0.2  # 5 rps (conservative for free tier)

# ── API Functions ───────────────────────────────────────────────────


def fetch_ohlcv_page(
    address: str,
    timeframe: str,
    time_from: int,
    time_to: int,
) -> list[dict]:
    """Fetch a single page of OHLCV data (max 1000 candles).

    Args:
        address: Token mint address.
        timeframe: Candle interval (e.g., '1H', '15m', '1D').
        time_from: Start unix timestamp.
        time_to: End unix timestamp.

    Returns:
        List of candle dicts with o, h, l, c, v, unixTime fields.

    Raises:
        httpx.HTTPStatusError: On API error.
        RuntimeError: On Birdeye-level error.
    """
    resp = httpx.get(
        f"{BASE_URL}/defi/ohlcv",
        headers=HEADERS,
        params={
            "address": address,
            "type": timeframe,
            "time_from": time_from,
            "time_to": time_to,
        },
        timeout=30.0,
    )

    if resp.status_code == 429:
        print("  Rate limited — waiting 5s...")
        time.sleep(5.0)
        return fetch_ohlcv_page(address, timeframe, time_from, time_to)

    resp.raise_for_status()
    data = resp.json()

    if not data.get("success"):
        raise RuntimeError(f"Birdeye error: {data.get('message', 'unknown')}")

    return data.get("data", {}).get("items", [])


def fetch_full_ohlcv(
    address: str,
    timeframe: str,
    start_time: int,
    end_time: int,
) -> pd.DataFrame:
    """Fetch complete OHLCV history with automatic pagination.

    Handles the 1000-candle limit by sliding the time window forward.

    Args:
        address: Token mint address.
        timeframe: Candle interval.
        start_time: Start unix timestamp.
        end_time: End unix timestamp.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    tf_secs = TIMEFRAME_SECONDS.get(timeframe)
    if tf_secs is None:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. "
            f"Valid: {', '.join(TIMEFRAME_SECONDS.keys())}"
        )

    window_secs = tf_secs * 999  # slightly under 1000 to avoid edge cases
    all_candles: list[dict] = []
    current_start = start_time
    page = 0

    while current_start < end_time:
        current_end = min(current_start + window_secs, end_time)
        page += 1

        print(
            f"  Page {page}: "
            f"{datetime.fromtimestamp(current_start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} → "
            f"{datetime.fromtimestamp(current_end, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            end="",
        )

        candles = fetch_ohlcv_page(address, timeframe, current_start, current_end)
        print(f" — {len(candles)} candles")

        if not candles:
            # No data in this window, skip forward
            current_start = current_end + 1
            time.sleep(RATE_LIMIT_DELAY)
            continue

        all_candles.extend(candles)

        # Move start to after the last candle we received
        last_time = max(c["unixTime"] for c in candles)
        current_start = last_time + 1

        time.sleep(RATE_LIMIT_DELAY)

    if not all_candles:
        print("No candle data returned.")
        return pd.DataFrame()

    # Build DataFrame
    df = pd.DataFrame(all_candles)
    df = df.rename(columns={
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    })
    df["timestamp"] = pd.to_datetime(df["unixTime"], unit="s", utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


# ── Analysis ────────────────────────────────────────────────────────


def print_summary(df: pd.DataFrame, symbol: str) -> None:
    """Print a summary of the fetched OHLCV data.

    Args:
        df: OHLCV DataFrame.
        symbol: Token symbol for display.
    """
    if df.empty:
        print("No data to summarize.")
        return

    print(f"\n{'='*60}")
    print(f"OHLCV Summary: {symbol}")
    print(f"{'='*60}")
    print(f"  Period:     {df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]}")
    print(f"  Candles:    {len(df)}")
    print(f"  Timeframe:  {TIMEFRAME}")
    print(f"  Open:       ${df['open'].iloc[0]:.4f}")
    print(f"  Close:      ${df['close'].iloc[-1]:.4f}")
    print(f"  High:       ${df['high'].max():.4f}")
    print(f"  Low:        ${df['low'].min():.4f}")
    change = (df["close"].iloc[-1] / df["open"].iloc[0] - 1) * 100
    print(f"  Change:     {change:+.2f}%")
    print(f"  Avg Volume: ${df['volume'].mean():,.0f}")
    print(f"  Total Vol:  ${df['volume'].sum():,.0f}")

    # Check for gaps
    if len(df) > 1:
        expected_diff = pd.Timedelta(seconds=TIMEFRAME_SECONDS[TIMEFRAME])
        actual_diffs = df["timestamp"].diff().dropna()
        gaps = actual_diffs[actual_diffs > expected_diff * 1.5]
        if len(gaps) > 0:
            print(f"  Gaps:       {len(gaps)} (max: {gaps.max()})")
        else:
            print(f"  Gaps:       None")


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Fetch OHLCV data and print summary."""
    now = datetime.now(tz=timezone.utc)
    end_time = int(now.timestamp())
    start_time = int((now - timedelta(days=DAYS_BACK)).timestamp())

    print(f"Token:     {TOKEN_ADDRESS}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Period:    {DAYS_BACK} days")
    print(f"Fetching OHLCV data...\n")

    df = fetch_full_ohlcv(TOKEN_ADDRESS, TIMEFRAME, start_time, end_time)

    if df.empty:
        print("No data returned. Check the token address and try again.")
        sys.exit(1)

    # Get token symbol for display
    try:
        resp = httpx.get(
            f"{BASE_URL}/defi/token_overview",
            headers=HEADERS,
            params={"address": TOKEN_ADDRESS},
            timeout=10.0,
        )
        symbol = resp.json().get("data", {}).get("symbol", TOKEN_ADDRESS[:8])
    except Exception:
        symbol = TOKEN_ADDRESS[:8]

    print_summary(df, symbol)

    # Save to CSV
    csv_path = f"ohlcv_{symbol}_{TIMEFRAME}_{DAYS_BACK}d.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved to {csv_path}")
    print(f"Load with: df = pd.read_csv('{csv_path}', parse_dates=['timestamp'])")


if __name__ == "__main__":
    main()
