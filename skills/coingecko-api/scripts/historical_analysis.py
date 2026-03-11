#!/usr/bin/env python3
"""Fetch historical price data from CoinGecko and compute basic analytics.

Retrieves OHLC or market chart data for a given coin and computes returns,
rolling volatility, maximum drawdown, and summary statistics. Supports
--demo mode with embedded sample data so no API key or network is required.

Usage:
    python scripts/historical_analysis.py                         # Live: SOL, 90 days
    python scripts/historical_analysis.py --coin bitcoin --days 365
    python scripts/historical_analysis.py --demo                  # Sample data

Dependencies:
    uv pip install httpx pandas numpy

Environment Variables:
    COINGECKO_API_KEY: (Optional) CoinGecko Pro API key for higher rate limits.
                       Free tier (30 calls/min) is used when not set.
"""

import argparse
import math
import os
import sys
import time
from typing import Any, Optional

try:
    import httpx
except ImportError:
    print("httpx is required. Install with: uv pip install httpx")
    sys.exit(1)

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("pandas and numpy are required. Install with: uv pip install pandas numpy")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────
API_KEY = os.getenv("COINGECKO_API_KEY", "")
if API_KEY:
    BASE_URL = "https://pro-api.coingecko.com/api/v3"
    HEADERS: dict[str, str] = {"x-cg-pro-api-key": API_KEY}
else:
    BASE_URL = "https://api.coingecko.com/api/v3"
    HEADERS = {}

DEFAULT_COIN = "solana"
DEFAULT_DAYS = 90

# ── Demo Data ───────────────────────────────────────────────────────
# 30 days of synthetic SOL daily prices for demo mode
_DEMO_BASE_TS = 1738368000000  # 2025-02-01 in ms
_DEMO_PRICES = [
    195.0, 198.5, 192.3, 189.7, 194.2, 200.1, 205.8, 203.4, 199.6, 196.1,
    201.5, 208.3, 212.7, 210.1, 206.4, 198.9, 193.5, 188.2, 191.7, 196.3,
    202.8, 209.5, 215.1, 218.4, 213.6, 208.9, 204.2, 210.7, 216.3, 220.8,
]

DEMO_MARKET_CHART = {
    "prices": [
        [_DEMO_BASE_TS + i * 86400000, p] for i, p in enumerate(_DEMO_PRICES)
    ],
    "market_caps": [
        [_DEMO_BASE_TS + i * 86400000, p * 480_000_000]
        for i, p in enumerate(_DEMO_PRICES)
    ],
    "total_volumes": [
        [_DEMO_BASE_TS + i * 86400000, 2_000_000_000 + (i % 5) * 500_000_000]
        for i, p in enumerate(_DEMO_PRICES)
    ],
}

# Synthetic OHLC candles (30 candles, 4h each for demo)
DEMO_OHLC = [
    [_DEMO_BASE_TS + i * 14400000,
     p, p + abs(p * 0.02), p - abs(p * 0.015), p + ((-1) ** i) * p * 0.005]
    for i, p in enumerate(_DEMO_PRICES)
]


# ── API Functions ───────────────────────────────────────────────────
def cg_get(endpoint: str, params: Optional[dict[str, Any]] = None,
           max_retries: int = 3) -> Any:
    """Make a GET request to CoinGecko with retry on rate limit.

    Args:
        endpoint: API path.
        params: Query parameters.
        max_retries: Number of retries on 429.

    Returns:
        Parsed JSON response.
    """
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params or {}, headers=HEADERS, timeout=15.0)
        if resp.status_code == 429:
            wait = 2 ** attempt * 10
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Rate limited after {max_retries} retries")


def fetch_market_chart(coin_id: str, days: int) -> dict[str, Any]:
    """Fetch historical market chart data (price, mcap, volume)."""
    return cg_get(f"/coins/{coin_id}/market_chart", params={
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily",
    })


def fetch_ohlc(coin_id: str, days: int) -> list[list[float]]:
    """Fetch OHLC candle data. Days must be 1/7/14/30/90/180/365."""
    valid_days = [1, 7, 14, 30, 90, 180, 365]
    ohlc_days = min(valid_days, key=lambda d: abs(d - days))
    return cg_get(f"/coins/{coin_id}/ohlc", params={
        "vs_currency": "usd",
        "days": str(ohlc_days),
    })


# ── Analysis Functions ──────────────────────────────────────────────
def build_price_dataframe(chart_data: dict[str, Any]) -> pd.DataFrame:
    """Convert market chart response to a DataFrame with daily returns.

    Args:
        chart_data: Response from /coins/{id}/market_chart.

    Returns:
        DataFrame with columns: price, market_cap, volume, daily_return.
    """
    df_price = pd.DataFrame(chart_data["prices"], columns=["timestamp", "price"])
    df_mcap = pd.DataFrame(chart_data["market_caps"], columns=["timestamp", "market_cap"])
    df_vol = pd.DataFrame(chart_data["total_volumes"], columns=["timestamp", "volume"])

    df = df_price.copy()
    df["market_cap"] = df_mcap["market_cap"]
    df["volume"] = df_vol["volume"]
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("date").drop(columns=["timestamp"])

    df["daily_return"] = df["price"].pct_change()
    return df


def build_ohlc_dataframe(ohlc_data: list[list[float]]) -> pd.DataFrame:
    """Convert OHLC response to a DataFrame.

    Args:
        ohlc_data: List of [timestamp, open, high, low, close].

    Returns:
        DataFrame with columns: open, high, low, close.
    """
    df = pd.DataFrame(ohlc_data, columns=["timestamp", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("date").drop(columns=["timestamp"])
    return df


def compute_max_drawdown(prices: pd.Series) -> tuple[float, Any, Any]:
    """Compute maximum drawdown from a price series.

    Args:
        prices: Series of prices.

    Returns:
        Tuple of (max_drawdown_pct, peak_date, trough_date).
    """
    cummax = prices.cummax()
    drawdown = (prices - cummax) / cummax
    trough_idx = drawdown.idxmin()
    peak_idx = prices.loc[:trough_idx].idxmax()
    return float(drawdown.min()) * 100, peak_idx, trough_idx


def compute_stats(df: pd.DataFrame) -> dict[str, float]:
    """Compute summary statistics from a price DataFrame.

    Args:
        df: DataFrame with 'price' and 'daily_return' columns.

    Returns:
        Dictionary of computed metrics.
    """
    returns = df["daily_return"].dropna()
    prices = df["price"]
    n_days = len(returns)

    total_return = (prices.iloc[-1] / prices.iloc[0] - 1) * 100
    ann_return = ((1 + total_return / 100) ** (365 / max(n_days, 1)) - 1) * 100
    ann_vol = float(returns.std() * math.sqrt(365)) * 100
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0
    max_dd, dd_peak, dd_trough = compute_max_drawdown(prices)

    return {
        "start_price": float(prices.iloc[0]),
        "end_price": float(prices.iloc[-1]),
        "high": float(prices.max()),
        "low": float(prices.min()),
        "total_return_pct": total_return,
        "annualized_return_pct": ann_return,
        "annualized_volatility_pct": ann_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd,
        "max_dd_peak": str(dd_peak.date()) if hasattr(dd_peak, "date") else str(dd_peak),
        "max_dd_trough": str(dd_trough.date()) if hasattr(dd_trough, "date") else str(dd_trough),
        "avg_daily_volume": float(df["volume"].mean()) if "volume" in df.columns else 0,
        "days": n_days,
    }


# ── Display Functions ───────────────────────────────────────────────
def display_stats(stats: dict[str, float], coin_id: str) -> None:
    """Print formatted statistics."""
    print(f"\n{'=' * 55}")
    print(f"  HISTORICAL ANALYSIS: {coin_id.upper()}")
    print(f"  Period: {stats['days']} days")
    print(f"{'=' * 55}")
    print(f"  Start Price:            ${stats['start_price']:>12,.2f}")
    print(f"  End Price:              ${stats['end_price']:>12,.2f}")
    print(f"  Period High:            ${stats['high']:>12,.2f}")
    print(f"  Period Low:             ${stats['low']:>12,.2f}")
    print(f"  {'─' * 45}")
    print(f"  Total Return:           {stats['total_return_pct']:>+11.2f}%")
    print(f"  Annualized Return:      {stats['annualized_return_pct']:>+11.2f}%")
    print(f"  Annualized Volatility:  {stats['annualized_volatility_pct']:>11.2f}%")
    print(f"  Sharpe Ratio (0% rf):   {stats['sharpe_ratio']:>11.2f}")
    print(f"  Max Drawdown:           {stats['max_drawdown_pct']:>11.2f}%")
    print(f"    Peak:                 {stats['max_dd_peak']}")
    print(f"    Trough:               {stats['max_dd_trough']}")
    if stats["avg_daily_volume"] > 0:
        avg_vol = stats["avg_daily_volume"]
        vol_str = f"${avg_vol / 1e9:.1f}B" if avg_vol >= 1e9 else f"${avg_vol / 1e6:.0f}M"
        print(f"  Avg Daily Volume:       {vol_str:>12}")
    print()


def display_ohlc_summary(df: pd.DataFrame) -> None:
    """Print a summary of OHLC data."""
    print(f"\n{'=' * 55}")
    print(f"  OHLC CANDLE SUMMARY ({len(df)} candles)")
    print(f"{'=' * 55}")
    print(f"  First candle:  {df.index[0]}")
    print(f"  Last candle:   {df.index[-1]}")
    print(f"  Overall range: ${df['low'].min():.2f} — ${df['high'].max():.2f}")

    # Show last 5 candles
    print(f"\n  Last 5 candles:")
    print(f"  {'Date':<22} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}")
    print(f"  {'─' * 62}")
    for idx, row in df.tail(5).iterrows():
        date_str = str(idx)[:19]
        print(f"  {date_str:<22} ${row['open']:>9.2f} ${row['high']:>9.2f} "
              f"${row['low']:>9.2f} ${row['close']:>9.2f}")
    print()


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run the historical analysis pipeline."""
    parser = argparse.ArgumentParser(
        description="Fetch CoinGecko historical data and compute analytics"
    )
    parser.add_argument("--coin", default=DEFAULT_COIN,
                        help=f"CoinGecko coin ID (default: {DEFAULT_COIN})")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"Number of days of history (default: {DEFAULT_DAYS})")
    parser.add_argument("--demo", action="store_true",
                        help="Use embedded sample data instead of live API")
    args = parser.parse_args()

    coin_id = args.coin
    days = args.days

    if args.demo:
        print("[DEMO MODE] Using embedded sample data (SOL, 30 days)\n")
        chart_data = DEMO_MARKET_CHART
        ohlc_data = DEMO_OHLC
        coin_id = "solana (demo)"
    else:
        print(f"Fetching {days}-day history for '{coin_id}' from CoinGecko...\n")
        try:
            chart_data = fetch_market_chart(coin_id, days)
            time.sleep(2)  # Respect rate limit
            ohlc_data = fetch_ohlc(coin_id, days)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                print(f"Coin '{coin_id}' not found. Use /search to find the correct ID.")
                print("See references/id_mapping.md for help.")
            else:
                print(f"API error: {e.response.status_code} — {e.response.text[:200]}")
            sys.exit(1)
        except httpx.ConnectError:
            print("Connection error. Check your internet or try --demo mode.")
            sys.exit(1)

    # Build DataFrames
    df = build_price_dataframe(chart_data)
    df_ohlc = build_ohlc_dataframe(ohlc_data)

    # Compute and display stats
    stats = compute_stats(df)
    display_stats(stats, coin_id)
    display_ohlc_summary(df_ohlc)

    # Rolling volatility (7-day window)
    if len(df) >= 7:
        df["rolling_vol_7d"] = df["daily_return"].rolling(7).std() * math.sqrt(365) * 100
        recent_vol = df["rolling_vol_7d"].dropna()
        if len(recent_vol) > 0:
            print(f"  7-Day Rolling Volatility (annualized):")
            print(f"    Current:  {recent_vol.iloc[-1]:.1f}%")
            print(f"    Average:  {recent_vol.mean():.1f}%")
            print(f"    Min:      {recent_vol.min():.1f}%")
            print(f"    Max:      {recent_vol.max():.1f}%")
            print()


if __name__ == "__main__":
    main()
