#!/usr/bin/env python3
"""Free-route pump.fun risk screen against the loophole tape API.

Calls only free routes (radar, coverage, watch) and fetches the unpaid
HTTP 402 quote of the paid compact check so the price and payment options
can be shown to a human. It never signs or sends a payment.

Usage:
    python risk_check.py --demo              # offline, mock responses
    python risk_check.py                     # use the first radar candidate
    python risk_check.py --mint <MINT>       # screen a specific mint

Dependencies:
    uv pip install httpx
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any, Optional

BASE = "https://api.loopholetape.com"

DEMO_MINT = "DemoMint1111111111111111111111111111111pump"

DEMO_RADAR: dict[str, Any] = {
    "data": {
        "feed": {"lag_s": 0.02, "is_stale": False},
        "top_rug_risk": [
            {
                "mint": DEMO_MINT,
                "age_s": 12.4,
                "flags": ["serial_rugger_creator"],
                "probabilities": {"rug_within_300s": 0.91, "true_graduation": 0.0},
                "check_url": f"{BASE}/v1/check/mint/{DEMO_MINT}",
            }
        ],
    }
}

DEMO_COVERAGE: dict[str, Any] = {
    "data": {
        "ready": True,
        "items": [{"mint": DEMO_MINT, "coverage": "full", "available": True, "reason": None}],
        "prices_usd": {"single": 0.005, "batch_up_to_five": 0.01},
    }
}

DEMO_WATCH: dict[str, Any] = {
    "data": {"has_new_events": False, "cursor": "demo-cursor", "next_check_after_s": 15, "price_usd": 0.005}
}

DEMO_QUOTE: dict[str, Any] = {
    "x402Version": 2,
    "accepts": [
        {"network": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", "amount": "5000",
         "asset": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
         "payTo": "9HkwyUhDMyjbpSpnyu5xuZ9vRaFQeajnJsavhie7XcsT"},
        {"network": "eip155:8453", "amount": "5000",
         "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
         "payTo": "0x25d408eF54e60F3006bD13d5A040d525E2F359c2"},
    ],
}


def get_json(client: Any, path: str, params: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """GET a free route and return its JSON body."""
    resp = client.get(f"{BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def decode_quote(header_value: str) -> dict[str, Any]:
    """Decode a base64 PAYMENT-REQUIRED header (x402 v2) into a dict."""
    return json.loads(base64.b64decode(header_value))


def fetch_quote(client: Any, mint: str) -> Optional[dict[str, Any]]:
    """Request the paid check without payment and return the 402 quote, or None."""
    resp = client.get(f"{BASE}/v1/check/mint/{mint}", timeout=10)
    if resp.status_code != 402:
        print(f"  no quote: HTTP {resp.status_code} {resp.text[:200]}")
        return None
    header = resp.headers.get("payment-required")
    return decode_quote(header) if header else None


def usd(amount_base_units: str) -> float:
    """Convert a 6-decimal USDC base-unit string to dollars."""
    return int(amount_base_units) / 1_000_000


def report(radar: dict[str, Any], coverage: dict[str, Any], watch: dict[str, Any],
           quote: Optional[dict[str, Any]], mint: str) -> None:
    """Print the free-route findings and the quote, with the approval reminder."""
    feed = radar["data"].get("feed", {})
    print(f"feed lag {feed.get('lag_s')} s, stale={feed.get('is_stale')}")
    for key in ("top_rug_risk", "top_graduation"):
        for item in radar["data"].get(key, [])[:3]:
            print(f"  radar {key} {item['mint']} age {item['age_s']} s "
                  f"p={item.get('probabilities')} flags={item.get('flags')}")
    cov_items = coverage["data"].get("items", [])
    available = bool(cov_items) and all(i.get("available") for i in cov_items)
    print(f"mint {mint}: available={available} prices={coverage['data'].get('prices_usd')}")
    print(f"watch: has_new_events={watch['data'].get('has_new_events')} "
          f"next_check_after_s={watch['data'].get('next_check_after_s')}")
    if not available:
        print("not covered: a paid check would be refused unpaid; skip this mint")
        return
    if quote:
        for acc in quote.get("accepts", []):
            print(f"  quote {acc['network']}: ${usd(acc['amount']):.3f} USDC to {acc['payTo']}")
    print("A paid check costs real USDC. Ask your human before paying; this script never pays.")


def main() -> int:
    """Parse arguments and run the free screen (live or demo)."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mint", help="pump.fun mint to screen (default: first radar candidate)")
    parser.add_argument("--demo", action="store_true", help="run offline on mock responses")
    args = parser.parse_args()

    if args.demo:
        mint = args.mint or DEMO_MINT
        report(DEMO_RADAR, DEMO_COVERAGE, DEMO_WATCH, DEMO_QUOTE, mint)
        return 0

    import httpx

    with httpx.Client(headers={"accept": "application/json"}) as client:
        try:
            radar = get_json(client, "/v1/radar")
            candidates = radar["data"].get("top_rug_risk", []) + radar["data"].get("top_graduation", [])
            mint = args.mint or (candidates[0]["mint"] if candidates else None)
            if not mint:
                print("radar is empty right now; pass --mint")
                return 1
            coverage = get_json(client, "/v1/check/coverage", {"mints": mint})
            watch = get_json(client, "/v1/check/watch", {"mints": mint})
            quote = fetch_quote(client, mint)
        except httpx.HTTPStatusError as exc:
            print(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}")
            return 1
    report(radar, coverage, watch, quote, mint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
