"""Fetch optional Adanos stock or crypto sentiment without mixing scoring models."""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import httpx

STOCK_PATHS = {
    "reddit": "/reddit/stocks/v1/stock",
    "x": "/x/stocks/v1/stock",
    "news": "/news/stocks/v1/stock",
    "polymarket": "/polymarket/stocks/v1/stock",
}
CRYPTO_PATH = "/reddit/crypto/v1/token"
BASE_URL = "https://api.adanos.org"


def fetch_sentiment(
    client: httpx.Client,
    *,
    asset_class: str,
    symbol: str,
    source: str,
    start: date,
    end: date,
    api_key: str,
) -> dict:
    """Return the source's original response, preserving missing-data semantics."""
    if asset_class == "crypto" and source != "reddit":
        raise ValueError("Crypto sentiment is available from Reddit only")
    path = CRYPTO_PATH if asset_class == "crypto" else STOCK_PATHS[source]
    response = client.get(
        f"{BASE_URL}{path}/{symbol}",
        params={"from": start.isoformat(), "to": end.isoformat()},
        headers={"X-API-Key": api_key},
    )
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="US stock ticker or crypto symbol")
    parser.add_argument("--asset-class", choices=("stock", "crypto"), default="stock")
    parser.add_argument("--source", choices=tuple(STOCK_PATHS), default="reddit")
    parser.add_argument("--from", dest="start", type=date.fromisoformat)
    parser.add_argument("--to", dest="end", type=date.fromisoformat)
    args = parser.parse_args(argv)

    symbol = args.symbol.upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", symbol):
        parser.error("symbol must be an asset symbol, not a URL or path")
    if args.asset_class == "crypto" and args.source != "reddit":
        parser.error("crypto supports Reddit only")

    end = args.end or datetime.now(timezone.utc).date()
    start = args.start or end - timedelta(days=6)
    if start > end:
        parser.error("--from must be on or before --to")

    api_key = os.environ.get("ADANOS_API_KEY", "").strip()
    if not api_key:
        parser.error("set ADANOS_API_KEY in the environment")

    try:
        with httpx.Client(timeout=15.0) as client:
            data = fetch_sentiment(
                client,
                asset_class=args.asset_class,
                symbol=symbol,
                source=args.source,
                start=start,
                end=end,
                api_key=api_key,
            )
    except httpx.HTTPStatusError as exc:
        print(f"Adanos returned HTTP {exc.response.status_code}", file=sys.stderr)
        return 1
    except httpx.RequestError:
        print("Adanos request failed", file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
