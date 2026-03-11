#!/usr/bin/env python3
"""Tokenomics Analyzer — Fetch and analyze token supply metrics.

Fetches token data from CoinGecko's free API and calculates key tokenomics
metrics including dilution risk, supply dynamics, and basic valuation ratios.

Usage:
    python scripts/tokenomics_analyzer.py                  # uses --demo mode
    python scripts/tokenomics_analyzer.py --token solana
    python scripts/tokenomics_analyzer.py --token uniswap
    TOKEN_ID=raydium python scripts/tokenomics_analyzer.py

Dependencies:
    uv pip install httpx

Environment Variables:
    TOKEN_ID: CoinGecko token ID (optional, can use --token flag instead)
"""

import argparse
import sys
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("Missing dependency. Install with: uv pip install httpx")
    sys.exit(1)


# ── Configuration ───────────────────────────────────────────────────
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT = 30
RATE_LIMIT_WAIT = 65  # CoinGecko free tier: wait if rate-limited


# ── Data Models ─────────────────────────────────────────────────────
class TokenData:
    """Container for token data fetched from CoinGecko."""

    def __init__(self, raw: dict) -> None:
        self.name: str = raw.get("name", "Unknown")
        self.symbol: str = raw.get("symbol", "???").upper()
        self.coingecko_id: str = raw.get("id", "")

        md = raw.get("market_data", {})
        self.price: float = md.get("current_price", {}).get("usd", 0.0)
        self.market_cap: float = md.get("market_cap", {}).get("usd", 0.0)
        self.fdv: float = md.get("fully_diluted_valuation", {}).get("usd", 0.0)
        self.total_volume_24h: float = md.get("total_volume", {}).get("usd", 0.0)
        self.circulating_supply: float = md.get("circulating_supply") or 0.0
        self.total_supply: float = md.get("total_supply") or 0.0
        self.max_supply: Optional[float] = md.get("max_supply")

        self.price_change_24h: float = md.get("price_change_percentage_24h") or 0.0
        self.price_change_7d: float = md.get("price_change_percentage_7d") or 0.0
        self.price_change_30d: float = md.get("price_change_percentage_30d") or 0.0
        self.ath: float = md.get("ath", {}).get("usd", 0.0)
        self.ath_change_pct: float = md.get("ath_change_percentage", {}).get("usd", 0.0)


class TokenomicsReport:
    """Calculated tokenomics metrics and risk assessment."""

    def __init__(self, data: TokenData) -> None:
        self.data = data
        self.metrics = self._calculate_metrics()
        self.risks = self._assess_risks()
        self.valuation = self._basic_valuation()

    def _calculate_metrics(self) -> dict:
        """Calculate core tokenomics metrics."""
        d = self.data
        circulating_pct = (
            (d.circulating_supply / d.total_supply * 100) if d.total_supply > 0 else 0.0
        )
        fdv_mcap_ratio = d.fdv / d.market_cap if d.market_cap > 0 else 0.0
        locked_supply = d.total_supply - d.circulating_supply
        locked_value = locked_supply * d.price if d.price > 0 else 0.0

        return {
            "circulating_pct": round(circulating_pct, 2),
            "fdv_mcap_ratio": round(fdv_mcap_ratio, 2),
            "locked_supply": locked_supply,
            "locked_value_usd": locked_value,
            "has_max_supply": d.max_supply is not None,
            "max_supply_pct": (
                round(d.circulating_supply / d.max_supply * 100, 2)
                if d.max_supply and d.max_supply > 0
                else None
            ),
        }

    def _assess_risks(self) -> list[dict]:
        """Identify tokenomics risk factors."""
        risks = []
        m = self.metrics
        d = self.data

        # Dilution risk
        if m["fdv_mcap_ratio"] > 5.0:
            risks.append({
                "category": "Dilution",
                "severity": "HIGH",
                "detail": (
                    f"FDV/MCap ratio is {m['fdv_mcap_ratio']:.1f}x — "
                    f"significant future dilution ahead"
                ),
            })
        elif m["fdv_mcap_ratio"] > 3.0:
            risks.append({
                "category": "Dilution",
                "severity": "MEDIUM",
                "detail": (
                    f"FDV/MCap ratio is {m['fdv_mcap_ratio']:.1f}x — "
                    f"moderate dilution risk"
                ),
            })
        elif m["fdv_mcap_ratio"] > 1.5:
            risks.append({
                "category": "Dilution",
                "severity": "LOW",
                "detail": (
                    f"FDV/MCap ratio is {m['fdv_mcap_ratio']:.1f}x — "
                    f"some dilution expected but manageable"
                ),
            })

        # Low circulating supply
        if m["circulating_pct"] < 20:
            risks.append({
                "category": "Supply",
                "severity": "HIGH",
                "detail": (
                    f"Only {m['circulating_pct']:.1f}% of supply circulating — "
                    f"extreme dilution risk as tokens unlock"
                ),
            })
        elif m["circulating_pct"] < 50:
            risks.append({
                "category": "Supply",
                "severity": "MEDIUM",
                "detail": (
                    f"{m['circulating_pct']:.1f}% of supply circulating — "
                    f"majority of tokens still locked"
                ),
            })

        # Low volume relative to market cap
        if d.market_cap > 0 and d.total_volume_24h > 0:
            volume_mcap_ratio = d.total_volume_24h / d.market_cap
            if volume_mcap_ratio < 0.01:
                risks.append({
                    "category": "Liquidity",
                    "severity": "MEDIUM",
                    "detail": (
                        f"24h volume is only {volume_mcap_ratio:.2%} of market cap — "
                        f"low liquidity relative to valuation"
                    ),
                })

        # Distance from ATH
        if d.ath_change_pct < -90:
            risks.append({
                "category": "Price",
                "severity": "INFO",
                "detail": f"Token is {d.ath_change_pct:.1f}% from ATH — deeply discounted or declining",
            })

        # No max supply
        if not m["has_max_supply"]:
            risks.append({
                "category": "Inflation",
                "severity": "INFO",
                "detail": "No max supply cap — potential for unlimited inflation",
            })

        return risks

    def _basic_valuation(self) -> dict:
        """Calculate basic valuation metrics."""
        d = self.data
        metrics: dict = {}

        # FDV per volume (lower = more activity per dollar of valuation)
        if d.total_volume_24h > 0:
            fdv_volume = d.fdv / (d.total_volume_24h * 365)
            metrics["fdv_annualized_volume"] = round(fdv_volume, 2)
            if fdv_volume < 1:
                metrics["fdv_volume_assessment"] = "High activity relative to FDV"
            elif fdv_volume < 10:
                metrics["fdv_volume_assessment"] = "Moderate activity"
            else:
                metrics["fdv_volume_assessment"] = "Low activity relative to FDV"

        # Market cap per volume (daily turnover)
        if d.market_cap > 0 and d.total_volume_24h > 0:
            daily_turnover = d.total_volume_24h / d.market_cap * 100
            metrics["daily_turnover_pct"] = round(daily_turnover, 2)

        return metrics


# ── API Functions ───────────────────────────────────────────────────
def fetch_token_data(token_id: str) -> TokenData:
    """Fetch token data from CoinGecko free API.

    Args:
        token_id: CoinGecko token identifier (e.g., 'solana', 'uniswap').

    Returns:
        TokenData object with parsed market data.

    Raises:
        httpx.HTTPStatusError: On non-2xx response after retries.
        ValueError: If token not found.
    """
    url = f"{COINGECKO_BASE}/coins/{token_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }

    for attempt in range(3):
        try:
            resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                print(f"  Rate limited, waiting {RATE_LIMIT_WAIT}s...")
                time.sleep(RATE_LIMIT_WAIT)
                continue
            if resp.status_code == 404:
                raise ValueError(
                    f"Token '{token_id}' not found on CoinGecko. "
                    f"Check the ID at https://www.coingecko.com/en/coins/{token_id}"
                )
            resp.raise_for_status()
            return TokenData(resp.json())
        except httpx.ConnectError:
            if attempt < 2:
                print(f"  Connection failed, retrying ({attempt + 1}/3)...")
                time.sleep(2)
            else:
                raise
    raise RuntimeError("Failed to fetch data after 3 attempts")


def search_token(query: str) -> Optional[str]:
    """Search for a token on CoinGecko and return its ID.

    Args:
        query: Search query (token name or symbol).

    Returns:
        CoinGecko token ID if found, None otherwise.
    """
    url = f"{COINGECKO_BASE}/search"
    try:
        resp = httpx.get(url, params={"query": query}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        coins = resp.json().get("coins", [])
        if coins:
            return coins[0]["id"]
        return None
    except httpx.HTTPError:
        return None


# ── Demo Data ───────────────────────────────────────────────────────
def get_demo_data() -> TokenData:
    """Return demo data for illustration (based on a well-known L1 token).

    Returns:
        TokenData populated with example values.
    """
    demo_raw = {
        "id": "demo-token",
        "name": "DemoChain",
        "symbol": "DEMO",
        "market_data": {
            "current_price": {"usd": 150.0},
            "market_cap": {"usd": 65_000_000_000},
            "fully_diluted_valuation": {"usd": 89_000_000_000},
            "total_volume": {"usd": 2_500_000_000},
            "circulating_supply": 433_000_000,
            "total_supply": 590_000_000,
            "max_supply": None,
            "price_change_percentage_24h": -2.5,
            "price_change_percentage_7d": 5.1,
            "price_change_percentage_30d": -8.3,
            "ath": {"usd": 260.0},
            "ath_change_percentage": {"usd": -42.3},
        },
    }
    return TokenData(demo_raw)


# ── Display ─────────────────────────────────────────────────────────
def format_number(n: float, decimals: int = 2) -> str:
    """Format large numbers with K/M/B suffixes.

    Args:
        n: Number to format.
        decimals: Decimal places.

    Returns:
        Formatted string.
    """
    if abs(n) >= 1_000_000_000:
        return f"${n / 1_000_000_000:.{decimals}f}B"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.{decimals}f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.{decimals}f}K"
    return f"${n:.{decimals}f}"


def format_supply(n: float) -> str:
    """Format supply numbers with M/B suffixes.

    Args:
        n: Supply number.

    Returns:
        Formatted string without dollar sign.
    """
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.2f}K"
    return f"{n:.0f}"


def print_report(report: TokenomicsReport) -> None:
    """Print formatted tokenomics report.

    Args:
        report: TokenomicsReport to display.
    """
    d = report.data
    m = report.metrics

    print("\n" + "=" * 65)
    print(f"  TOKENOMICS REPORT: {d.name} ({d.symbol})")
    print("=" * 65)

    # Price overview
    print(f"\n  Price:            ${d.price:,.4f}")
    print(f"  Market Cap:       {format_number(d.market_cap)}")
    print(f"  FDV:              {format_number(d.fdv)}")
    print(f"  24h Volume:       {format_number(d.total_volume_24h)}")

    # Price changes
    print(f"\n  Price Change:")
    print(f"    24h:  {d.price_change_24h:+.1f}%")
    print(f"    7d:   {d.price_change_7d:+.1f}%")
    print(f"    30d:  {d.price_change_30d:+.1f}%")
    print(f"    ATH:  {d.ath_change_pct:+.1f}% (ATH: ${d.ath:,.2f})")

    # Supply analysis
    print(f"\n  Supply:")
    print(f"    Circulating:    {format_supply(d.circulating_supply)}")
    print(f"    Total:          {format_supply(d.total_supply)}")
    if d.max_supply:
        print(f"    Max:            {format_supply(d.max_supply)}")
    else:
        print(f"    Max:            No cap")
    print(f"    Circulating %:  {m['circulating_pct']:.1f}%")
    print(f"    Locked Supply:  {format_supply(m['locked_supply'])}")
    print(f"    Locked Value:   {format_number(m['locked_value_usd'])}")

    # Dilution metrics
    print(f"\n  Dilution:")
    print(f"    FDV/MCap Ratio: {m['fdv_mcap_ratio']:.2f}x")
    if m["max_supply_pct"] is not None:
        print(f"    % of Max Minted: {m['max_supply_pct']:.1f}%")

    # Valuation
    if report.valuation:
        print(f"\n  Valuation:")
        if "fdv_annualized_volume" in report.valuation:
            print(f"    FDV/Ann.Volume: {report.valuation['fdv_annualized_volume']:.2f}x")
            print(f"    Assessment:     {report.valuation.get('fdv_volume_assessment', 'N/A')}")
        if "daily_turnover_pct" in report.valuation:
            print(f"    Daily Turnover: {report.valuation['daily_turnover_pct']:.2f}%")

    # Risk flags
    if report.risks:
        print(f"\n  Risk Flags:")
        for risk in report.risks:
            icon = {"HIGH": "[!]", "MEDIUM": "[*]", "LOW": "[-]", "INFO": "[i]"}.get(
                risk["severity"], "[?]"
            )
            print(f"    {icon} {risk['severity']:6s} | {risk['category']:10s} | {risk['detail']}")
    else:
        print(f"\n  Risk Flags: None identified")

    print("\n" + "=" * 65)
    print("  NOTE: This is informational analysis, not financial advice.")
    print("=" * 65 + "\n")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point for the tokenomics analyzer."""
    parser = argparse.ArgumentParser(
        description="Analyze token supply dynamics and valuation metrics"
    )
    parser.add_argument(
        "--token", "-t",
        type=str,
        default=None,
        help="CoinGecko token ID (e.g., 'solana', 'uniswap', 'raydium')",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with demo data (no API call needed)",
    )
    parser.add_argument(
        "--search", "-s",
        type=str,
        default=None,
        help="Search for a token by name or symbol",
    )
    args = parser.parse_args()

    import os
    token_id = args.token or os.getenv("TOKEN_ID", "")

    if args.demo or (not token_id and not args.search):
        print("Running in demo mode (use --token <id> for live data)")
        data = get_demo_data()
    elif args.search:
        print(f"Searching for '{args.search}'...")
        found_id = search_token(args.search)
        if not found_id:
            print(f"No token found for '{args.search}'")
            sys.exit(1)
        print(f"Found: {found_id}")
        print(f"Fetching data for '{found_id}'...")
        data = fetch_token_data(found_id)
    else:
        print(f"Fetching data for '{token_id}'...")
        try:
            data = fetch_token_data(token_id)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except httpx.HTTPError as e:
            print(f"HTTP error: {e}")
            sys.exit(1)

    report = TokenomicsReport(data)
    print_report(report)


if __name__ == "__main__":
    main()
