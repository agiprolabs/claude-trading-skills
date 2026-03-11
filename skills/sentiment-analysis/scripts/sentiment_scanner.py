#!/usr/bin/env python3
"""Sentiment scanner that fetches live data from free APIs and computes composite scores.

Pulls data from:
- Alternative.me Fear & Greed Index (no auth required)
- CoinGecko community data (no auth required, rate limited)
- Binance funding rates and long/short ratios (no auth required)

Computes a composite sentiment score from -100 (extreme fear) to +100 (extreme greed)
and flags contrarian opportunities.

Usage:
    python scripts/sentiment_scanner.py                     # Live scan for SOL
    python scripts/sentiment_scanner.py --symbol ETH        # Live scan for ETH
    python scripts/sentiment_scanner.py --demo              # Demo with synthetic data

Dependencies:
    uv pip install httpx
"""

import argparse
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"

# CoinGecko ID mapping for common tokens
COINGECKO_IDS: dict[str, str] = {
    "SOL": "solana",
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "ARB": "arbitrum",
    "OP": "optimism",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "ADA": "cardano",
}

# Binance futures symbol mapping
BINANCE_SYMBOLS: dict[str, str] = {
    "SOL": "SOLUSDT",
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "AVAX": "AVAXUSDT",
    "MATIC": "MATICUSDT",
    "ARB": "ARBUSDT",
    "OP": "OPUSDT",
    "LINK": "LINKUSDT",
    "DOT": "DOTUSDT",
    "ADA": "ADAUSDT",
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "social": 0.30,
    "velocity": 0.15,
    "fear_greed": 0.30,
    "funding": 0.25,
}

REQUEST_TIMEOUT = 15.0


# ── Data Classes ────────────────────────────────────────────────────


@dataclass
class FearGreedData:
    """Fear & Greed Index reading."""

    value: int
    classification: str
    timestamp: int


@dataclass
class CommunityData:
    """CoinGecko community statistics."""

    twitter_followers: int = 0
    reddit_subscribers: int = 0
    reddit_active_48h: int = 0
    telegram_members: int = 0
    sentiment_up_pct: float = 50.0
    sentiment_down_pct: float = 50.0
    developer_commits_4w: int = 0


@dataclass
class FundingData:
    """Binance futures funding rate and long/short ratio."""

    funding_rate: float = 0.0
    funding_time: int = 0
    long_short_ratio: float = 1.0
    long_account_pct: float = 0.5
    short_account_pct: float = 0.5


@dataclass
class SentimentResult:
    """Complete sentiment analysis result."""

    symbol: str
    fear_greed: Optional[FearGreedData] = None
    community: Optional[CommunityData] = None
    funding: Optional[FundingData] = None
    social_polarity: float = 0.0
    mention_velocity: float = 1.0
    composite_score: float = 0.0
    contrarian_signals: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── API Fetchers ────────────────────────────────────────────────────


def fetch_fear_greed(client: httpx.Client, limit: int = 7) -> Optional[FearGreedData]:
    """Fetch the crypto Fear & Greed Index from alternative.me.

    Args:
        client: HTTP client instance.
        limit: Number of historical days to fetch.

    Returns:
        Most recent FearGreedData or None on failure.
    """
    try:
        resp = client.get(FEAR_GREED_URL, params={"limit": limit})
        resp.raise_for_status()
        data = resp.json()
        latest = data["data"][0]
        return FearGreedData(
            value=int(latest["value"]),
            classification=latest["value_classification"],
            timestamp=int(latest["timestamp"]),
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        print(f"  [WARN] Fear & Greed fetch failed: {exc}")
        return None


def fetch_community_data(
    client: httpx.Client, coingecko_id: str
) -> Optional[CommunityData]:
    """Fetch community statistics from CoinGecko.

    Args:
        client: HTTP client instance.
        coingecko_id: CoinGecko coin identifier (e.g., 'solana').

    Returns:
        CommunityData or None on failure.
    """
    try:
        resp = client.get(
            f"{COINGECKO_BASE}/coins/{coingecko_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "true",
                "developer_data": "true",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        cd = data.get("community_data", {})
        dd = data.get("developer_data", {})
        return CommunityData(
            twitter_followers=cd.get("twitter_followers") or 0,
            reddit_subscribers=cd.get("reddit_subscribers") or 0,
            reddit_active_48h=cd.get("reddit_accounts_active_48h") or 0,
            telegram_members=cd.get("telegram_channel_user_count") or 0,
            sentiment_up_pct=data.get("sentiment_votes_up_percentage") or 50.0,
            sentiment_down_pct=data.get("sentiment_votes_down_percentage") or 50.0,
            developer_commits_4w=dd.get("commit_count_4_weeks") or 0,
        )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        print(f"  [WARN] CoinGecko community fetch failed: {exc}")
        return None


def fetch_funding_data(
    client: httpx.Client, binance_symbol: str
) -> Optional[FundingData]:
    """Fetch funding rate and long/short ratio from Binance Futures.

    Args:
        client: HTTP client instance.
        binance_symbol: Binance futures symbol (e.g., 'SOLUSDT').

    Returns:
        FundingData or None on failure.
    """
    funding_rate = 0.0
    funding_time = 0
    ls_ratio = 1.0
    long_pct = 0.5
    short_pct = 0.5

    # Fetch funding rate
    try:
        resp = client.get(
            f"{BINANCE_FUTURES_BASE}/fapi/v1/fundingRate",
            params={"symbol": binance_symbol, "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            funding_rate = float(data[-1]["fundingRate"])
            funding_time = int(data[-1]["fundingTime"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        print(f"  [WARN] Funding rate fetch failed: {exc}")

    # Fetch long/short ratio
    try:
        resp = client.get(
            f"{BINANCE_FUTURES_BASE}/futures/data/globalLongShortAccountRatio",
            params={"symbol": binance_symbol, "period": "1h", "limit": 1},
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            ls_ratio = float(data[-1]["longShortRatio"])
            long_pct = float(data[-1]["longAccount"])
            short_pct = float(data[-1]["shortAccount"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        print(f"  [WARN] Long/short ratio fetch failed: {exc}")

    return FundingData(
        funding_rate=funding_rate,
        funding_time=funding_time,
        long_short_ratio=ls_ratio,
        long_account_pct=long_pct,
        short_account_pct=short_pct,
    )


# ── Scoring Functions ───────────────────────────────────────────────


def compute_social_polarity(community: Optional[CommunityData]) -> float:
    """Derive social polarity from CoinGecko sentiment votes.

    Args:
        community: CommunityData with sentiment percentages.

    Returns:
        Polarity from -1.0 (bearish) to +1.0 (bullish).
    """
    if community is None:
        return 0.0
    up = community.sentiment_up_pct
    down = community.sentiment_down_pct
    total = up + down
    if total == 0:
        return 0.0
    return (up - down) / total


def estimate_mention_velocity(community: Optional[CommunityData]) -> float:
    """Estimate mention velocity from Reddit active users.

    Uses reddit_active_48h relative to subscriber count as a proxy.
    Normal engagement is ~0.5-2% of subscribers active.

    Args:
        community: CommunityData with Reddit stats.

    Returns:
        Velocity estimate (1.0 = normal, >3.0 = elevated).
    """
    if community is None or community.reddit_subscribers == 0:
        return 1.0
    active_ratio = community.reddit_active_48h / community.reddit_subscribers
    # Baseline: 1% of subscribers active in 48h is normal
    baseline_ratio = 0.01
    if baseline_ratio <= 0:
        return 1.0
    return active_ratio / baseline_ratio


def compute_composite_score(
    social_polarity: float,
    mention_velocity: float,
    fear_greed_value: int,
    funding_rate: float,
    weights: Optional[dict[str, float]] = None,
) -> float:
    """Compute weighted composite sentiment score.

    Args:
        social_polarity: Social sentiment from -1.0 to +1.0.
        mention_velocity: Mention rate vs baseline (1.0 = normal).
        fear_greed_value: Fear & Greed Index (0-100).
        funding_rate: Perpetual futures funding rate.
        weights: Custom component weights.

    Returns:
        Composite score from -100.0 (extreme fear) to +100.0 (extreme greed).
    """
    w = weights or DEFAULT_WEIGHTS

    s_social = max(-1.0, min(1.0, social_polarity))
    s_velocity = min(mention_velocity / 10.0, 1.0)
    s_fg = (fear_greed_value - 50) / 50.0
    s_funding = max(-1.0, min(1.0, -10.0 * funding_rate))

    raw = (
        w["social"] * s_social
        + w["velocity"] * s_velocity
        + w["fear_greed"] * s_fg
        + w["funding"] * s_funding
    )
    return round(raw * 100, 1)


def detect_contrarian_signals(result: SentimentResult) -> list[str]:
    """Identify contrarian trading signals from sentiment data.

    Args:
        result: SentimentResult with all computed metrics.

    Returns:
        List of contrarian signal descriptions.
    """
    signals: list[str] = []

    # Extreme composite scores
    if result.composite_score <= -70:
        signals.append(
            f"EXTREME FEAR (composite={result.composite_score:.1f}): "
            "Historically a potential accumulation zone"
        )
    elif result.composite_score >= 70:
        signals.append(
            f"EXTREME GREED (composite={result.composite_score:.1f}): "
            "Historically a potential distribution zone"
        )

    # Funding rate extremes
    if result.funding and result.funding.funding_rate > 0.0005:
        signals.append(
            f"HIGH FUNDING ({result.funding.funding_rate:.4%}): "
            "Longs paying significant premium — crowded long risk"
        )
    elif result.funding and result.funding.funding_rate < -0.0005:
        signals.append(
            f"NEGATIVE FUNDING ({result.funding.funding_rate:.4%}): "
            "Shorts paying premium — potential short squeeze"
        )

    # Long/short ratio extremes
    if result.funding and result.funding.long_short_ratio > 2.0:
        signals.append(
            f"CROWDED LONG (L/S ratio={result.funding.long_short_ratio:.2f}): "
            "Liquidation cascade risk if price drops"
        )
    elif result.funding and result.funding.long_short_ratio < 0.5:
        signals.append(
            f"CROWDED SHORT (L/S ratio={result.funding.long_short_ratio:.2f}): "
            "Short squeeze risk if price rises"
        )

    # High velocity + extreme polarity
    if result.mention_velocity > 5.0 and result.social_polarity > 0.6:
        signals.append(
            f"EUPHORIC SPIKE (velocity={result.mention_velocity:.1f}x, "
            f"polarity={result.social_polarity:.2f}): Potential fade opportunity"
        )
    elif result.mention_velocity > 5.0 and result.social_polarity < -0.6:
        signals.append(
            f"PANIC SPIKE (velocity={result.mention_velocity:.1f}x, "
            f"polarity={result.social_polarity:.2f}): Potential bounce opportunity"
        )

    # Fear & Greed extremes
    if result.fear_greed and result.fear_greed.value <= 10:
        signals.append(
            f"EXTREME FEAR INDEX ({result.fear_greed.value}): "
            "Rare reading — bottom formation historically likely"
        )
    elif result.fear_greed and result.fear_greed.value >= 90:
        signals.append(
            f"EXTREME GREED INDEX ({result.fear_greed.value}): "
            "Rare reading — top formation historically likely"
        )

    return signals


# ── Display ─────────────────────────────────────────────────────────


def classify_score(score: float) -> str:
    """Classify a composite score into a human-readable label.

    Args:
        score: Composite score from -100 to +100.

    Returns:
        Classification string.
    """
    if score <= -70:
        return "Extreme Fear"
    elif score <= -30:
        return "Fear"
    elif score <= 30:
        return "Neutral"
    elif score <= 70:
        return "Greed"
    else:
        return "Extreme Greed"


def display_result(result: SentimentResult) -> None:
    """Print a formatted sentiment analysis report.

    Args:
        result: Complete SentimentResult.
    """
    print("\n" + "=" * 60)
    print(f"  SENTIMENT ANALYSIS: {result.symbol}")
    print("=" * 60)

    # Fear & Greed
    print("\n--- Market Fear & Greed Index ---")
    if result.fear_greed:
        bar_len = result.fear_greed.value // 2
        bar = "#" * bar_len + "." * (50 - bar_len)
        print(f"  Value: {result.fear_greed.value}/100 ({result.fear_greed.classification})")
        print(f"  [{bar}]")
    else:
        print("  Not available")

    # Community Data
    print("\n--- Social / Community Data ---")
    if result.community:
        print(f"  Twitter Followers:   {result.community.twitter_followers:>12,}")
        print(f"  Reddit Subscribers:  {result.community.reddit_subscribers:>12,}")
        print(f"  Reddit Active (48h): {result.community.reddit_active_48h:>12,}")
        print(f"  Telegram Members:    {result.community.telegram_members:>12,}")
        print(f"  Sentiment Up:        {result.community.sentiment_up_pct:>11.1f}%")
        print(f"  Sentiment Down:      {result.community.sentiment_down_pct:>11.1f}%")
        print(f"  Dev Commits (4w):    {result.community.developer_commits_4w:>12,}")
    else:
        print("  Not available")

    # Funding & Positioning
    print("\n--- On-Chain Positioning ---")
    if result.funding:
        print(f"  Funding Rate:      {result.funding.funding_rate:>12.4%}")
        print(f"  Long/Short Ratio:  {result.funding.long_short_ratio:>12.2f}")
        print(f"  Long Accounts:     {result.funding.long_account_pct:>11.1%}")
        print(f"  Short Accounts:    {result.funding.short_account_pct:>11.1%}")
    else:
        print("  Not available")

    # Derived Metrics
    print("\n--- Derived Metrics ---")
    print(f"  Social Polarity:     {result.social_polarity:>+.3f}  (-1 to +1)")
    print(f"  Mention Velocity:    {result.mention_velocity:>.2f}x  (1.0 = normal)")

    # Composite Score
    label = classify_score(result.composite_score)
    print("\n--- Composite Sentiment Score ---")
    score_bar_pos = int((result.composite_score + 100) / 4)
    score_bar_pos = max(0, min(50, score_bar_pos))
    bar = "." * score_bar_pos + "|" + "." * (50 - score_bar_pos)
    print(f"  Score: {result.composite_score:>+6.1f}  ({label})")
    print(f"  -100 [{bar}] +100")

    # Contrarian Signals
    print("\n--- Contrarian Signals ---")
    if result.contrarian_signals:
        for sig in result.contrarian_signals:
            print(f"  >> {sig}")
    else:
        print("  No contrarian signals detected (sentiment in normal range)")

    # Errors
    if result.errors:
        print("\n--- Warnings ---")
        for err in result.errors:
            print(f"  [!] {err}")

    print("\n" + "=" * 60)
    print("  NOTE: This is analytical information only, not financial advice.")
    print("=" * 60 + "\n")


# ── Demo Mode ───────────────────────────────────────────────────────


def run_demo() -> None:
    """Run demo mode with synthetic sentiment data showing a fear/greed cycle.

    Generates 5 synthetic scenarios to illustrate different sentiment regimes.
    """
    print("\n" + "=" * 60)
    print("  SENTIMENT SCANNER — DEMO MODE")
    print("  Synthetic data showing different sentiment regimes")
    print("=" * 60)

    scenarios: list[dict] = [
        {
            "name": "Extreme Fear (Capitulation)",
            "symbol": "SOL",
            "fear_greed": FearGreedData(value=8, classification="Extreme Fear", timestamp=0),
            "community": CommunityData(
                twitter_followers=2_500_000, reddit_subscribers=300_000,
                reddit_active_48h=45_000, telegram_members=100_000,
                sentiment_up_pct=20.0, sentiment_down_pct=80.0,
                developer_commits_4w=150,
            ),
            "funding": FundingData(
                funding_rate=-0.0008, funding_time=0,
                long_short_ratio=0.4, long_account_pct=0.286, short_account_pct=0.714,
            ),
        },
        {
            "name": "Fear (Declining Market)",
            "symbol": "SOL",
            "fear_greed": FearGreedData(value=30, classification="Fear", timestamp=0),
            "community": CommunityData(
                twitter_followers=2_500_000, reddit_subscribers=300_000,
                reddit_active_48h=6_000, telegram_members=100_000,
                sentiment_up_pct=35.0, sentiment_down_pct=65.0,
                developer_commits_4w=160,
            ),
            "funding": FundingData(
                funding_rate=-0.0002, funding_time=0,
                long_short_ratio=0.8, long_account_pct=0.444, short_account_pct=0.556,
            ),
        },
        {
            "name": "Neutral (Consolidation)",
            "symbol": "SOL",
            "fear_greed": FearGreedData(value=50, classification="Neutral", timestamp=0),
            "community": CommunityData(
                twitter_followers=2_500_000, reddit_subscribers=300_000,
                reddit_active_48h=3_000, telegram_members=100_000,
                sentiment_up_pct=52.0, sentiment_down_pct=48.0,
                developer_commits_4w=180,
            ),
            "funding": FundingData(
                funding_rate=0.0001, funding_time=0,
                long_short_ratio=1.1, long_account_pct=0.524, short_account_pct=0.476,
            ),
        },
        {
            "name": "Greed (Bull Market)",
            "symbol": "SOL",
            "fear_greed": FearGreedData(value=72, classification="Greed", timestamp=0),
            "community": CommunityData(
                twitter_followers=2_500_000, reddit_subscribers=300_000,
                reddit_active_48h=15_000, telegram_members=100_000,
                sentiment_up_pct=78.0, sentiment_down_pct=22.0,
                developer_commits_4w=200,
            ),
            "funding": FundingData(
                funding_rate=0.0004, funding_time=0,
                long_short_ratio=1.8, long_account_pct=0.643, short_account_pct=0.357,
            ),
        },
        {
            "name": "Extreme Greed (Euphoria)",
            "symbol": "SOL",
            "fear_greed": FearGreedData(value=92, classification="Extreme Greed", timestamp=0),
            "community": CommunityData(
                twitter_followers=2_500_000, reddit_subscribers=300_000,
                reddit_active_48h=60_000, telegram_members=100_000,
                sentiment_up_pct=92.0, sentiment_down_pct=8.0,
                developer_commits_4w=120,
            ),
            "funding": FundingData(
                funding_rate=0.0012, funding_time=0,
                long_short_ratio=3.5, long_account_pct=0.778, short_account_pct=0.222,
            ),
        },
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'~' * 60}")
        print(f"  Scenario {i}/5: {scenario['name']}")
        print(f"{'~' * 60}")

        result = SentimentResult(symbol=scenario["symbol"])
        result.fear_greed = scenario["fear_greed"]
        result.community = scenario["community"]
        result.funding = scenario["funding"]

        result.social_polarity = compute_social_polarity(result.community)
        result.mention_velocity = estimate_mention_velocity(result.community)

        fg_value = result.fear_greed.value if result.fear_greed else 50
        fr_value = result.funding.funding_rate if result.funding else 0.0

        result.composite_score = compute_composite_score(
            social_polarity=result.social_polarity,
            mention_velocity=result.mention_velocity,
            fear_greed_value=fg_value,
            funding_rate=fr_value,
        )
        result.contrarian_signals = detect_contrarian_signals(result)

        display_result(result)


# ── Live Scanner ────────────────────────────────────────────────────


def run_live_scan(symbol: str) -> SentimentResult:
    """Run a live sentiment scan for the given symbol.

    Fetches data from all free API sources, computes derived metrics,
    and identifies contrarian signals.

    Args:
        symbol: Token symbol (e.g., 'SOL', 'BTC', 'ETH').

    Returns:
        Complete SentimentResult.
    """
    symbol = symbol.upper()
    result = SentimentResult(symbol=symbol)

    coingecko_id = COINGECKO_IDS.get(symbol)
    binance_symbol = BINANCE_SYMBOLS.get(symbol)

    if not coingecko_id:
        result.errors.append(
            f"No CoinGecko mapping for {symbol}. "
            f"Supported: {', '.join(sorted(COINGECKO_IDS.keys()))}"
        )
    if not binance_symbol:
        result.errors.append(
            f"No Binance mapping for {symbol}. "
            f"Supported: {', '.join(sorted(BINANCE_SYMBOLS.keys()))}"
        )

    print(f"\nScanning sentiment for {symbol}...")

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        # Fetch Fear & Greed (market-wide)
        print("  Fetching Fear & Greed Index...")
        result.fear_greed = fetch_fear_greed(client)

        # Fetch community data (token-specific)
        if coingecko_id:
            print(f"  Fetching CoinGecko community data for {coingecko_id}...")
            result.community = fetch_community_data(client, coingecko_id)

        # Fetch funding data (token-specific)
        if binance_symbol:
            print(f"  Fetching Binance futures data for {binance_symbol}...")
            result.funding = fetch_funding_data(client, binance_symbol)

    # Compute derived metrics
    result.social_polarity = compute_social_polarity(result.community)
    result.mention_velocity = estimate_mention_velocity(result.community)

    fg_value = result.fear_greed.value if result.fear_greed else 50
    fr_value = result.funding.funding_rate if result.funding else 0.0

    result.composite_score = compute_composite_score(
        social_polarity=result.social_polarity,
        mention_velocity=result.mention_velocity,
        fear_greed_value=fg_value,
        funding_rate=fr_value,
    )

    result.contrarian_signals = detect_contrarian_signals(result)

    return result


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point: parse arguments and run scanner."""
    parser = argparse.ArgumentParser(
        description="Crypto sentiment scanner using free APIs"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="SOL",
        help="Token symbol to scan (default: SOL)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode with synthetic data",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        result = run_live_scan(args.symbol)
        display_result(result)


if __name__ == "__main__":
    main()
