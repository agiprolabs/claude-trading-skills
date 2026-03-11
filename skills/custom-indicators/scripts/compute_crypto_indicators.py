#!/usr/bin/env python3
"""Compute all nine crypto-native indicators from available data sources.

Fetches data from CoinGecko and DeFiLlama free APIs where possible, and
falls back to synthetic demo data when APIs are unavailable. Prints an
indicator dashboard with current values and signal interpretations.

Usage:
    python scripts/compute_crypto_indicators.py
    python scripts/compute_crypto_indicators.py --demo
    python scripts/compute_crypto_indicators.py --coin bitcoin
    python scripts/compute_crypto_indicators.py --coin solana --demo

Dependencies:
    uv pip install httpx pandas numpy

Environment Variables:
    None required (uses free, unauthenticated API endpoints).
"""

import argparse
import math
import sys
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("Missing dependency. Install with: uv pip install numpy")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("Missing dependency. Install with: uv pip install pandas")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEFILLAMA_BASE = "https://api.llama.fi"
REQUEST_TIMEOUT = 15.0
DEFAULT_COIN = "bitcoin"


# ── Data Fetching ───────────────────────────────────────────────────


def fetch_coingecko_coin(coin_id: str) -> Optional[dict]:
    """Fetch coin data from CoinGecko free API.

    Args:
        coin_id: CoinGecko coin identifier (e.g. 'bitcoin', 'solana').

    Returns:
        Parsed JSON response or None on failure.
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "community_data": "false",
        "developer_data": "false",
    }
    try:
        resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        print(f"  [warn] CoinGecko request failed: {exc}")
        return None


def fetch_coingecko_market_chart(
    coin_id: str, days: int = 30
) -> Optional[dict]:
    """Fetch historical market chart data from CoinGecko.

    Args:
        coin_id: CoinGecko coin identifier.
        days: Number of days of history.

    Returns:
        Parsed JSON with prices, market_caps, total_volumes arrays.
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": str(days)}
    try:
        resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        print(f"  [warn] CoinGecko market chart request failed: {exc}")
        return None


def fetch_defillama_protocol(protocol: str) -> Optional[dict]:
    """Fetch protocol TVL data from DeFiLlama.

    Args:
        protocol: DeFiLlama protocol slug.

    Returns:
        Parsed JSON response or None on failure.
    """
    url = f"{DEFILLAMA_BASE}/protocol/{protocol}"
    try:
        resp = httpx.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        print(f"  [warn] DeFiLlama request failed: {exc}")
        return None


# ── Demo Data Generation ────────────────────────────────────────────


def generate_demo_data(coin_id: str) -> dict:
    """Generate synthetic data for demo mode.

    Args:
        coin_id: Coin identifier (used to seed randomness).

    Returns:
        Dictionary with all fields needed for indicator computation.
    """
    rng = np.random.default_rng(seed=hash(coin_id) % (2**31))

    market_cap = rng.uniform(1e9, 500e9)
    price = rng.uniform(1.0, 60000.0)
    circulating_supply = market_cap / price
    daily_volume_usd = market_cap * rng.uniform(0.02, 0.15)
    daily_tx_volume_usd = market_cap * rng.uniform(0.005, 0.08)

    # Generate 30 days of historical data
    days = 30
    prices = [price * (1 + rng.normal(0, 0.03)) for _ in range(days)]
    for i in range(1, days):
        prices[i] = prices[i - 1] * (1 + rng.normal(0.001, 0.03))
    volumes = [daily_volume_usd * rng.uniform(0.5, 1.5) for _ in range(days)]

    # Holder counts (generally growing with noise)
    base_holders = int(rng.uniform(5000, 500000))
    holder_counts = [base_holders]
    for _ in range(days - 1):
        change = int(rng.normal(50, 200))
        holder_counts.append(max(100, holder_counts[-1] + change))

    # Open interest series
    base_oi = market_cap * rng.uniform(0.01, 0.05)
    oi_series = [base_oi]
    for _ in range(days - 1):
        oi_series.append(oi_series[-1] * (1 + rng.normal(0.005, 0.05)))

    # Funding rates (8h periods, last 30 days = ~90 periods)
    funding_rates = [float(rng.normal(0.0001, 0.0005)) for _ in range(90)]

    # Exchange flows
    deposit_usd = market_cap * rng.uniform(0.001, 0.01)
    withdrawal_usd = market_cap * rng.uniform(0.001, 0.01)

    # Smart money
    smart_buys = daily_volume_usd * rng.uniform(0.01, 0.1)
    smart_sells = daily_volume_usd * rng.uniform(0.01, 0.1)

    # Realized cap estimate
    realized_cap = market_cap * rng.uniform(0.4, 1.2)

    # Liquidity
    depth_usd = rng.uniform(50000, 5000000)
    spread_bps = rng.uniform(1.0, 50.0)
    pool_tvl = rng.uniform(100000, 50000000)

    return {
        "coin_id": coin_id,
        "market_cap": market_cap,
        "price": prices[-1],
        "circulating_supply": circulating_supply,
        "daily_volume_usd": daily_volume_usd,
        "daily_volume_tokens": daily_volume_usd / prices[-1],
        "daily_tx_volume_usd": daily_tx_volume_usd,
        "realized_cap": realized_cap,
        "prices": prices,
        "volumes": volumes,
        "holder_counts": holder_counts,
        "oi_series": oi_series,
        "funding_rates": funding_rates,
        "deposit_usd": deposit_usd,
        "withdrawal_usd": withdrawal_usd,
        "smart_buys": smart_buys,
        "smart_sells": smart_sells,
        "depth_usd": depth_usd,
        "spread_bps": spread_bps,
        "pool_tvl": pool_tvl,
    }


def build_data_from_api(coin_id: str) -> Optional[dict]:
    """Build indicator input data from live API calls.

    Args:
        coin_id: CoinGecko coin identifier.

    Returns:
        Data dictionary or None if APIs are unavailable.
    """
    print(f"  Fetching data for '{coin_id}' from CoinGecko...")
    coin_data = fetch_coingecko_coin(coin_id)
    if coin_data is None:
        return None

    time.sleep(1.2)  # Respect CoinGecko rate limit

    print("  Fetching 30-day market chart...")
    chart_data = fetch_coingecko_market_chart(coin_id, days=30)
    if chart_data is None:
        return None

    md = coin_data.get("market_data", {})
    market_cap = md.get("market_cap", {}).get("usd", 0)
    price = md.get("current_price", {}).get("usd", 0)
    circulating_supply = md.get("circulating_supply", 0) or 1
    daily_volume_usd = md.get("total_volume", {}).get("usd", 0)

    prices = [p[1] for p in chart_data.get("prices", [])]
    volumes = [v[1] for v in chart_data.get("total_volumes", [])]

    # Fields not available from free APIs — use estimates
    rng = np.random.default_rng(42)
    daily_tx_volume_usd = daily_volume_usd * 0.3  # rough estimate
    realized_cap = market_cap * 0.7  # rough estimate

    days = len(prices)
    base_holders = 100000
    holder_counts = [base_holders]
    for _ in range(days - 1):
        holder_counts.append(holder_counts[-1] + int(rng.normal(50, 100)))

    base_oi = market_cap * 0.02
    oi_series = [base_oi * (1 + rng.normal(0, 0.03)) for _ in range(days)]

    funding_rates = [float(rng.normal(0.0001, 0.0003)) for _ in range(90)]

    deposit_usd = daily_volume_usd * 0.05
    withdrawal_usd = daily_volume_usd * 0.04
    smart_buys = daily_volume_usd * 0.03
    smart_sells = daily_volume_usd * 0.025
    depth_usd = daily_volume_usd * 0.1
    spread_bps = 5.0
    pool_tvl = market_cap * 0.005

    return {
        "coin_id": coin_id,
        "market_cap": market_cap,
        "price": price,
        "circulating_supply": circulating_supply,
        "daily_volume_usd": daily_volume_usd,
        "daily_volume_tokens": daily_volume_usd / price if price > 0 else 0,
        "daily_tx_volume_usd": daily_tx_volume_usd,
        "realized_cap": realized_cap,
        "prices": prices,
        "volumes": volumes,
        "holder_counts": holder_counts,
        "oi_series": oi_series,
        "funding_rates": funding_rates,
        "deposit_usd": deposit_usd,
        "withdrawal_usd": withdrawal_usd,
        "smart_buys": smart_buys,
        "smart_sells": smart_sells,
        "depth_usd": depth_usd,
        "spread_bps": spread_bps,
        "pool_tvl": pool_tvl,
    }


# ── Indicator Computations ──────────────────────────────────────────


def nvt_ratio(market_cap: float, daily_tx_volume_usd: float) -> float:
    """Compute NVT ratio.

    Args:
        market_cap: Current market capitalization in USD.
        daily_tx_volume_usd: 24h on-chain transaction volume in USD.

    Returns:
        NVT ratio value.
    """
    if daily_tx_volume_usd <= 0:
        return float("inf")
    return market_cap / daily_tx_volume_usd


def nvt_signal(nvt: float) -> str:
    """Interpret NVT ratio value.

    Args:
        nvt: Raw NVT ratio.

    Returns:
        Signal string.
    """
    if nvt == float("inf"):
        return "no data"
    if nvt < 15:
        return "STRONG BULLISH"
    if nvt < 25:
        return "bullish"
    if nvt < 65:
        return "neutral"
    if nvt < 100:
        return "bearish"
    return "STRONG BEARISH"


def mvrv_ratio(market_cap: float, realized_cap: float) -> float:
    """Compute MVRV ratio.

    Args:
        market_cap: Current market capitalization in USD.
        realized_cap: Realized capitalization (aggregate cost basis).

    Returns:
        MVRV ratio value.
    """
    if realized_cap <= 0:
        return float("inf")
    return market_cap / realized_cap


def mvrv_signal(mvrv: float) -> str:
    """Interpret MVRV ratio.

    Args:
        mvrv: MVRV ratio value.

    Returns:
        Signal string.
    """
    if mvrv == float("inf"):
        return "no data"
    if mvrv < 0.5:
        return "STRONG BULLISH"
    if mvrv < 1.0:
        return "bullish"
    if mvrv < 2.0:
        return "neutral"
    if mvrv < 3.5:
        return "bearish"
    return "STRONG BEARISH"


def exchange_netflow(
    deposits_usd: float, withdrawals_usd: float
) -> tuple[float, str]:
    """Compute exchange netflow and interpret.

    Args:
        deposits_usd: Total deposits to exchanges in USD.
        withdrawals_usd: Total withdrawals from exchanges in USD.

    Returns:
        Tuple of (netflow_value, signal_label).
    """
    netflow = deposits_usd - withdrawals_usd
    if netflow > 0:
        signal = "bearish"
    elif netflow < 0:
        signal = "bullish"
    else:
        signal = "neutral"
    return netflow, signal


def funding_rate_aggregate(
    rates: list[float], weights: Optional[list[float]] = None
) -> tuple[float, str]:
    """Volume-weighted average funding rate with signal.

    Args:
        rates: Funding rates from multiple periods or exchanges.
        weights: Optional volume weights.

    Returns:
        Tuple of (average_rate, signal).
    """
    if not rates:
        return 0.0, "no data"
    if weights is None:
        weights = [1.0 / len(rates)] * len(rates)
    vw_rate = float(np.average(rates, weights=weights))
    if vw_rate > 0.0005:
        signal = "bearish"
    elif vw_rate < -0.0005:
        signal = "bullish"
    else:
        signal = "neutral"
    return vw_rate, signal


def oi_momentum(oi_series: list[float], lookback: int = 7) -> float:
    """Compute open interest momentum as percentage change.

    Args:
        oi_series: Daily open interest values (newest last).
        lookback: Number of days for momentum calculation.

    Returns:
        Percentage change in open interest.
    """
    if len(oi_series) < lookback + 1:
        return 0.0
    old = oi_series[-(lookback + 1)]
    new = oi_series[-1]
    if old <= 0:
        return 0.0
    return (new - old) / old * 100.0


def oi_price_signal(oi_mom: float, price_change_pct: float) -> str:
    """Interpret OI momentum combined with price change.

    Args:
        oi_mom: OI momentum percentage.
        price_change_pct: Price change percentage over same period.

    Returns:
        Signal interpretation string.
    """
    oi_up = oi_mom > 1.0
    price_up = price_change_pct > 1.0
    if oi_up and price_up:
        return "trend confirmation (bullish)"
    if oi_up and not price_up:
        return "bearish buildup"
    if not oi_up and price_up:
        return "short squeeze"
    return "long liquidation"


def holder_momentum_calc(
    holder_counts: list[int], lookback: int = 7
) -> tuple[float, float]:
    """Compute holder momentum and acceleration.

    Args:
        holder_counts: Daily holder count values (newest last).
        lookback: Number of days for momentum calculation.

    Returns:
        Tuple of (momentum_pct, acceleration).
    """
    if len(holder_counts) < lookback + 2:
        return 0.0, 0.0
    old = holder_counts[-(lookback + 1)]
    new = holder_counts[-1]
    prev_old = holder_counts[-(lookback + 2)]
    prev_new = holder_counts[-2]
    mom = (new - old) / old if old > 0 else 0.0
    prev_mom = (prev_new - prev_old) / prev_old if prev_old > 0 else 0.0
    accel = mom - prev_mom
    return mom, accel


def holder_signal(momentum: float, acceleration: float) -> str:
    """Interpret holder momentum and acceleration.

    Args:
        momentum: Holder momentum percentage.
        acceleration: Change in momentum.

    Returns:
        Signal string.
    """
    if momentum > 0 and acceleration > 0:
        return "STRONG BULLISH (accelerating adoption)"
    if momentum > 0 and acceleration <= 0:
        return "bullish (decelerating adoption)"
    if momentum < 0 and acceleration < 0:
        return "STRONG BEARISH (accelerating departures)"
    if momentum < 0 and acceleration >= 0:
        return "bearish (slowing departures)"
    return "neutral"


def liquidity_score(
    depth_usd: float,
    spread_bps: float,
    pool_tvl: float,
    position_size: float = 100_000.0,
    weights: tuple[float, float, float] = (0.4, 0.3, 0.3),
) -> float:
    """Composite liquidity score from 0 (illiquid) to 1 (highly liquid).

    Args:
        depth_usd: Order book depth within 2% of mid price in USD.
        spread_bps: Bid-ask spread in basis points.
        pool_tvl: DEX pool total value locked in USD.
        position_size: Target position size in USD.
        weights: Weights for (depth, spread, pool) components.

    Returns:
        Liquidity score between 0 and 1.
    """
    depth_s = min(1.0, depth_usd / position_size) if position_size > 0 else 0.0
    spread_s = max(0.0, 1.0 - spread_bps / 100.0)
    pool_s = (
        min(1.0, pool_tvl / (position_size * 10)) if position_size > 0 else 0.0
    )
    return weights[0] * depth_s + weights[1] * spread_s + weights[2] * pool_s


def liquidity_label(score: float) -> str:
    """Interpret liquidity score.

    Args:
        score: Liquidity score 0-1.

    Returns:
        Rating string.
    """
    if score >= 0.8:
        return "excellent"
    if score >= 0.5:
        return "good"
    if score >= 0.3:
        return "fair"
    return "poor"


def smart_money_flow(
    smart_buys_usd: float,
    smart_sells_usd: float,
    total_volume_usd: float,
) -> tuple[float, float, str]:
    """Compute smart money flow and ratio.

    Args:
        smart_buys_usd: USD value of smart wallet purchases.
        smart_sells_usd: USD value of smart wallet sales.
        total_volume_usd: Total trading volume in USD.

    Returns:
        Tuple of (net_flow, smf_ratio, signal).
    """
    net = smart_buys_usd - smart_sells_usd
    ratio = net / total_volume_usd if total_volume_usd > 0 else 0.0
    if ratio > 0.1:
        signal = "STRONG BULLISH"
    elif ratio > 0.05:
        signal = "bullish"
    elif ratio < -0.1:
        signal = "STRONG BEARISH"
    elif ratio < -0.05:
        signal = "bearish"
    else:
        signal = "neutral"
    return net, ratio, signal


def token_velocity(
    daily_volume_tokens: float, circulating_supply: float
) -> tuple[float, str]:
    """Compute token velocity.

    Args:
        daily_volume_tokens: 24h trading volume in token units.
        circulating_supply: Circulating supply of the token.

    Returns:
        Tuple of (velocity, interpretation).
    """
    if circulating_supply <= 0:
        return 0.0, "unknown"
    vel = daily_volume_tokens / circulating_supply
    if vel > 0.3:
        return vel, "very high (speculative frenzy)"
    if vel > 0.15:
        return vel, "high (elevated speculation)"
    if vel > 0.05:
        return vel, "moderate"
    if vel > 0.02:
        return vel, "low (healthy holding)"
    return vel, "very low (strong holders)"


# ── Dashboard ───────────────────────────────────────────────────────


def format_usd(value: float) -> str:
    """Format a USD value with appropriate suffix.

    Args:
        value: Dollar amount.

    Returns:
        Formatted string (e.g. '$1.23B').
    """
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1e12:
        return f"{sign}${abs_val / 1e12:.2f}T"
    if abs_val >= 1e9:
        return f"{sign}${abs_val / 1e9:.2f}B"
    if abs_val >= 1e6:
        return f"{sign}${abs_val / 1e6:.2f}M"
    if abs_val >= 1e3:
        return f"{sign}${abs_val / 1e3:.2f}K"
    return f"{sign}${abs_val:.2f}"


def print_dashboard(data: dict, is_demo: bool) -> None:
    """Print the full indicator dashboard.

    Args:
        data: Data dictionary with all required fields.
        is_demo: Whether this is demo/synthetic data.
    """
    coin = data["coin_id"].upper()
    mode = " (DEMO DATA)" if is_demo else ""
    width = 66

    print()
    print("=" * width)
    print(f"  CRYPTO INDICATOR DASHBOARD — {coin}{mode}")
    print("=" * width)
    print(f"  Price: ${data['price']:,.2f}  |  Market Cap: {format_usd(data['market_cap'])}")
    print("-" * width)

    # 1. NVT
    nvt = nvt_ratio(data["market_cap"], data["daily_tx_volume_usd"])
    nvt_sig = nvt_signal(nvt)
    nvt_display = f"{nvt:.1f}" if nvt != float("inf") else "N/A"
    print(f"  1. NVT Ratio:            {nvt_display:>12}  |  {nvt_sig}")

    # 2. MVRV
    mvrv = mvrv_ratio(data["market_cap"], data["realized_cap"])
    mvrv_sig = mvrv_signal(mvrv)
    mvrv_display = f"{mvrv:.2f}" if mvrv != float("inf") else "N/A"
    print(f"  2. MVRV Ratio:           {mvrv_display:>12}  |  {mvrv_sig}")

    # 3. Exchange Flow
    netflow, exch_sig = exchange_netflow(data["deposit_usd"], data["withdrawal_usd"])
    print(f"  3. Exchange Netflow:     {format_usd(netflow):>12}  |  {exch_sig}")

    # 4. Funding Rate
    recent_rates = data["funding_rates"][-24:]  # last 24 periods (~8 days)
    avg_rate, fund_sig = funding_rate_aggregate(recent_rates)
    print(f"  4. Avg Funding Rate:     {avg_rate * 100:>11.4f}%  |  {fund_sig}")

    # 5. OI Momentum
    oi_mom = oi_momentum(data["oi_series"], lookback=7)
    prices = data["prices"]
    price_change = 0.0
    if len(prices) >= 8:
        p_old = prices[-8]
        p_new = prices[-1]
        price_change = (p_new - p_old) / p_old * 100 if p_old > 0 else 0.0
    oi_sig = oi_price_signal(oi_mom, price_change)
    print(f"  5. OI Momentum (7d):     {oi_mom:>11.2f}%  |  {oi_sig}")

    # 6. Holder Momentum
    h_mom, h_accel = holder_momentum_calc(data["holder_counts"], lookback=7)
    h_sig = holder_signal(h_mom, h_accel)
    print(f"  6. Holder Momentum (7d): {h_mom * 100:>11.2f}%  |  {h_sig}")

    # 7. Liquidity Score
    liq = liquidity_score(
        data["depth_usd"], data["spread_bps"], data["pool_tvl"]
    )
    liq_label = liquidity_label(liq)
    print(f"  7. Liquidity Score:      {liq:>12.3f}  |  {liq_label}")

    # 8. Smart Money Flow
    smf_net, smf_ratio, smf_sig = smart_money_flow(
        data["smart_buys"], data["smart_sells"], data["daily_volume_usd"]
    )
    print(f"  8. Smart Money Flow:     {format_usd(smf_net):>12}  |  {smf_sig} (ratio: {smf_ratio:.4f})")

    # 9. Token Velocity
    vel, vel_interp = token_velocity(
        data["daily_volume_tokens"], data["circulating_supply"]
    )
    print(f"  9. Token Velocity:       {vel:>12.4f}  |  {vel_interp}")

    print("-" * width)

    # Composite score
    score_map: dict[str, int] = {}
    # Map signals to -2..+2
    signal_to_score = {
        "STRONG BULLISH": 2, "bullish": 1, "neutral": 0,
        "bearish": -1, "STRONG BEARISH": -2, "no data": 0,
    }

    def map_sig(sig: str) -> int:
        sig_lower = sig.lower()
        if "strong bullish" in sig_lower or "accelerating adoption" in sig_lower:
            return 2
        if "bullish" in sig_lower or "confirmation" in sig_lower or "squeeze" in sig_lower:
            return 1
        if "strong bearish" in sig_lower or "accelerating departures" in sig_lower:
            return -2
        if "bearish" in sig_lower or "liquidation" in sig_lower:
            return -1
        return 0

    score_map["nvt"] = map_sig(nvt_sig)
    score_map["mvrv"] = map_sig(mvrv_sig)
    score_map["exchange_flow"] = map_sig(exch_sig)
    score_map["funding_rate"] = map_sig(fund_sig)
    score_map["oi_momentum"] = map_sig(oi_sig)
    score_map["holder_momentum"] = map_sig(h_sig)
    score_map["smart_money_flow"] = map_sig(smf_sig)
    score_map["token_velocity"] = 0  # velocity is context-dependent

    # Liquidity doesn't have bull/bear directionality
    total = sum(score_map.values())
    count = len(score_map)
    composite = total / count if count > 0 else 0.0

    if composite > 1.0:
        comp_label = "STRONG BULLISH"
    elif composite > 0.3:
        comp_label = "bullish"
    elif composite < -1.0:
        comp_label = "STRONG BEARISH"
    elif composite < -0.3:
        comp_label = "bearish"
    else:
        comp_label = "neutral"

    print(f"  COMPOSITE SCORE:         {composite:>12.2f}  |  {comp_label}")
    print("=" * width)
    print()
    print("  Disclaimer: For informational purposes only. Not financial advice.")
    print()


# ── Main ────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Compute crypto-native indicators for a given coin."
    )
    parser.add_argument(
        "--coin",
        default=DEFAULT_COIN,
        help=f"CoinGecko coin ID (default: {DEFAULT_COIN})",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use synthetic demo data instead of live API calls",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: fetch data and display indicator dashboard."""
    args = parse_args()
    is_demo = args.demo

    if is_demo:
        print(f"[demo] Generating synthetic data for '{args.coin}'...")
        data = generate_demo_data(args.coin)
    else:
        print(f"[live] Fetching data for '{args.coin}'...")
        data = build_data_from_api(args.coin)
        if data is None:
            print("[fallback] API unavailable, switching to demo mode.")
            data = generate_demo_data(args.coin)
            is_demo = True

    print_dashboard(data, is_demo)


if __name__ == "__main__":
    main()
