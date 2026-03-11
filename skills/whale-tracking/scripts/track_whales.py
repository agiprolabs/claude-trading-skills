#!/usr/bin/env python3
"""Track whale wallets for a Solana token and classify their activity.

Fetches the top holders of a given token mint, identifies whale wallets
by balance threshold, checks their recent transaction activity, and
classifies each as accumulating, distributing, or holding.

Usage:
    python scripts/track_whales.py --mint <TOKEN_MINT>
    python scripts/track_whales.py --demo

Dependencies:
    uv pip install httpx

Environment Variables:
    HELIUS_API_KEY: Your Helius API key (optional in demo mode)
    SOLANA_RPC_URL: Custom RPC endpoint (optional, defaults to public mainnet)
"""

import argparse
import json
import os
import random
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
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)
HELIUS_RPC_URL = (
    f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    if HELIUS_API_KEY
    else ""
)
HELIUS_API_BASE = "https://api.helius.xyz/v0"

# Whale classification thresholds (in token units, relative)
WHALE_MIN_PCT_SUPPLY = 2.0  # Minimum % of supply to be considered a whale
WHALE_TOP_N = 20  # Track top N holders

# Activity classification thresholds
ACCUMULATION_THRESHOLD = 4  # Score >= this = accumulating
DISTRIBUTION_THRESHOLD = 4  # Score >= this = distributing


# ── Data Models ─────────────────────────────────────────────────────
@dataclass
class TokenHolder:
    """A token holder with balance and ownership data."""

    token_account: str
    wallet_address: str
    balance: float
    pct_supply: float
    rank: int


@dataclass
class WhaleActivity:
    """Whale wallet activity summary."""

    wallet: str
    balance: float
    pct_supply: float
    rank: int
    buy_count: int = 0
    sell_count: int = 0
    total_bought: float = 0.0
    total_sold: float = 0.0
    transfers_to_exchange: int = 0
    classification: str = "holding"
    accumulation_score: int = 0
    distribution_score: int = 0
    recent_transactions: list = field(default_factory=list)


# ── RPC Helpers ─────────────────────────────────────────────────────
def rpc_call(
    client: httpx.Client,
    method: str,
    params: list,
    rpc_url: Optional[str] = None,
) -> dict:
    """Make a JSON-RPC call to a Solana RPC endpoint.

    Args:
        client: httpx Client instance.
        method: RPC method name.
        params: Method parameters.
        rpc_url: Override RPC URL.

    Returns:
        The 'result' field from the RPC response.

    Raises:
        RuntimeError: If the RPC call returns an error.
    """
    url = rpc_url or HELIUS_RPC_URL or SOLANA_RPC_URL
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    resp = client.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result", {})


def get_top_holders(
    client: httpx.Client, mint: str
) -> list[TokenHolder]:
    """Fetch the top token holders for a given mint.

    Uses getTokenLargestAccounts and resolves each token account
    to its owning wallet address.

    Args:
        client: httpx Client instance.
        mint: Token mint address.

    Returns:
        List of TokenHolder objects sorted by balance descending.
    """
    result = rpc_call(client, "getTokenLargestAccounts", [mint])
    accounts = result.get("value", [])
    if not accounts:
        print(f"No holders found for mint {mint}")
        return []

    total_supply = sum(
        float(a.get("uiAmount", 0) or 0) for a in accounts
    )
    if total_supply == 0:
        total_supply = 1.0  # Avoid division by zero

    holders: list[TokenHolder] = []
    for rank, acct in enumerate(accounts, 1):
        token_account = acct["address"]
        balance = float(acct.get("uiAmount", 0) or 0)
        pct = (balance / total_supply) * 100

        # Resolve token account to wallet address
        wallet = resolve_token_account_owner(client, token_account)
        holders.append(
            TokenHolder(
                token_account=token_account,
                wallet_address=wallet,
                balance=balance,
                pct_supply=round(pct, 2),
                rank=rank,
            )
        )
        time.sleep(0.1)  # Rate limit politeness

    return holders


def resolve_token_account_owner(
    client: httpx.Client, token_account: str
) -> str:
    """Resolve a token account address to its owner wallet.

    Args:
        client: httpx Client instance.
        token_account: SPL token account address.

    Returns:
        Wallet address that owns the token account.
    """
    try:
        result = rpc_call(
            client,
            "getAccountInfo",
            [token_account, {"encoding": "jsonParsed"}],
        )
        if result and result.get("value"):
            parsed = result["value"]["data"]["parsed"]["info"]
            return parsed.get("owner", token_account)
    except Exception:
        pass
    return token_account  # Fallback to token account address


def get_wallet_transactions(
    client: httpx.Client, wallet: str, limit: int = 20
) -> list[dict]:
    """Fetch recent enhanced transactions for a wallet via Helius.

    Falls back to basic RPC signatures if Helius key is not available.

    Args:
        client: httpx Client instance.
        wallet: Wallet address.
        limit: Maximum number of transactions.

    Returns:
        List of transaction dicts with type and transfer info.
    """
    if HELIUS_API_KEY:
        try:
            url = (
                f"{HELIUS_API_BASE}/addresses/{wallet}/transactions"
                f"?api-key={HELIUS_API_KEY}&limit={limit}"
            )
            resp = client.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"  Helius API error for {wallet[:8]}...: {e}")
            return []
    else:
        # Fallback: basic signatures (less detail)
        try:
            result = rpc_call(
                client,
                "getSignaturesForAddress",
                [wallet, {"limit": limit}],
            )
            return [
                {"signature": s["signature"], "type": "UNKNOWN"}
                for s in (result if isinstance(result, list) else [])
            ]
        except Exception as e:
            print(f"  RPC error for {wallet[:8]}...: {e}")
            return []


# ── Activity Classification ────────────────────────────────────────
KNOWN_EXCHANGE_PREFIXES = [
    "5tzFkiKsc",  # Binance
    "JCnc",  # OKX
    "AC5R",  # Bybit
    "9WzDX",  # Coinbase
]


def classify_whale_activity(
    holder: TokenHolder, transactions: list[dict]
) -> WhaleActivity:
    """Classify a whale's recent activity as accumulating, distributing, or holding.

    Analyzes token transfers in recent transactions to determine
    buy/sell counts and compute accumulation/distribution scores.

    Args:
        holder: The token holder information.
        transactions: List of enhanced transaction dicts.

    Returns:
        WhaleActivity with classification and scores.
    """
    activity = WhaleActivity(
        wallet=holder.wallet_address,
        balance=holder.balance,
        pct_supply=holder.pct_supply,
        rank=holder.rank,
    )

    for tx in transactions:
        tx_type = tx.get("type", "UNKNOWN")
        token_transfers = tx.get("tokenTransfers", [])

        for transfer in token_transfers:
            from_addr = transfer.get("fromUserAccount", "")
            to_addr = transfer.get("toUserAccount", "")
            amount = float(transfer.get("tokenAmount", 0) or 0)

            if to_addr == holder.wallet_address:
                activity.buy_count += 1
                activity.total_bought += amount
            elif from_addr == holder.wallet_address:
                activity.sell_count += 1
                activity.total_sold += amount
                # Check for exchange transfers
                for prefix in KNOWN_EXCHANGE_PREFIXES:
                    if to_addr.startswith(prefix):
                        activity.transfers_to_exchange += 1
                        break

    # Compute accumulation score
    acc = 0
    if activity.buy_count > activity.sell_count * 2:
        acc += 2
    elif activity.buy_count > activity.sell_count:
        acc += 1
    avg_buy = (
        activity.total_bought / activity.buy_count
        if activity.buy_count
        else 0
    )
    avg_sell = (
        activity.total_sold / activity.sell_count
        if activity.sell_count
        else 0
    )
    if avg_buy > avg_sell * 1.5 and avg_sell > 0:
        acc += 1
    if activity.buy_count >= 4:
        acc += 1  # Frequent buying
    activity.accumulation_score = acc

    # Compute distribution score
    dist = 0
    if activity.sell_count > activity.buy_count * 2:
        dist += 2
    elif activity.sell_count > activity.buy_count:
        dist += 1
    if activity.transfers_to_exchange > 0:
        dist += 3
    if activity.total_sold > activity.total_bought * 2:
        dist += 2
    activity.distribution_score = dist

    # Classify
    if acc >= ACCUMULATION_THRESHOLD and acc > dist:
        activity.classification = "accumulating"
    elif dist >= DISTRIBUTION_THRESHOLD and dist > acc:
        activity.classification = "distributing"
    else:
        activity.classification = "holding"

    activity.recent_transactions = transactions[:5]
    return activity


# ── Demo Mode ───────────────────────────────────────────────────────
def generate_demo_data() -> list[WhaleActivity]:
    """Generate synthetic whale data for demonstration purposes.

    Returns:
        List of WhaleActivity objects with simulated data.
    """
    random.seed(42)
    demo_whales = [
        ("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "accumulating"),
        ("DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", "distributing"),
        ("HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH", "holding"),
        ("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "accumulating"),
        ("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", "distributing"),
        ("FmHzNJkx6HqgjcC3kcEJU8hDUBfPcWwkm3u4MXJaxjms", "holding"),
        ("2AQdpHFicFaDB5xKs3oFZ8nSm3ALFVsGQ7LKRGBHVVWL", "accumulating"),
    ]

    results: list[WhaleActivity] = []
    total_supply = 1_000_000_000.0

    for rank, (wallet, behavior) in enumerate(demo_whales, 1):
        balance = random.uniform(10_000_000, 80_000_000)
        pct = (balance / total_supply) * 100

        if behavior == "accumulating":
            buy_count = random.randint(8, 20)
            sell_count = random.randint(0, 3)
            total_bought = balance * random.uniform(0.3, 0.8)
            total_sold = total_bought * random.uniform(0.0, 0.2)
            acc_score = random.randint(5, 8)
            dist_score = random.randint(0, 2)
        elif behavior == "distributing":
            buy_count = random.randint(0, 3)
            sell_count = random.randint(8, 15)
            total_sold = balance * random.uniform(0.3, 0.6)
            total_bought = total_sold * random.uniform(0.0, 0.15)
            acc_score = random.randint(0, 1)
            dist_score = random.randint(5, 9)
        else:
            buy_count = random.randint(1, 4)
            sell_count = random.randint(1, 4)
            total_bought = balance * random.uniform(0.02, 0.1)
            total_sold = total_bought * random.uniform(0.8, 1.2)
            acc_score = random.randint(0, 2)
            dist_score = random.randint(0, 2)

        activity = WhaleActivity(
            wallet=wallet,
            balance=round(balance, 2),
            pct_supply=round(pct, 2),
            rank=rank,
            buy_count=buy_count,
            sell_count=sell_count,
            total_bought=round(total_bought, 2),
            total_sold=round(total_sold, 2),
            transfers_to_exchange=random.randint(1, 3)
            if behavior == "distributing"
            else 0,
            classification=behavior,
            accumulation_score=acc_score,
            distribution_score=dist_score,
        )
        results.append(activity)

    return results


# ── Report Formatting ───────────────────────────────────────────────
def print_whale_report(
    whales: list[WhaleActivity], mint: str, is_demo: bool = False
) -> None:
    """Print a formatted whale activity report.

    Args:
        whales: List of classified whale activities.
        mint: Token mint address.
        is_demo: Whether this is demo data.
    """
    header = "WHALE ACTIVITY REPORT"
    if is_demo:
        header += " [DEMO MODE - SYNTHETIC DATA]"

    print("\n" + "=" * 72)
    print(f"  {header}")
    print(f"  Token: {mint[:16]}...{mint[-8:]}" if len(mint) > 24 else f"  Token: {mint}")
    print(f"  Whales tracked: {len(whales)}")
    print("=" * 72)

    # Summary counts
    acc_count = sum(1 for w in whales if w.classification == "accumulating")
    dist_count = sum(1 for w in whales if w.classification == "distributing")
    hold_count = sum(1 for w in whales if w.classification == "holding")

    print(f"\n  Summary: {acc_count} accumulating | {dist_count} distributing | {hold_count} holding")

    # Net signal
    if acc_count > dist_count * 2:
        net_signal = "STRONG ACCUMULATION"
    elif acc_count > dist_count:
        net_signal = "NET ACCUMULATION"
    elif dist_count > acc_count * 2:
        net_signal = "STRONG DISTRIBUTION"
    elif dist_count > acc_count:
        net_signal = "NET DISTRIBUTION"
    else:
        net_signal = "NEUTRAL"
    print(f"  Net signal: {net_signal}")

    print("\n" + "-" * 72)
    print(f"  {'Rank':<5} {'Wallet':<16} {'Balance %':<10} {'Buys':<6} {'Sells':<6} {'Classification':<16} {'Score'}")
    print("-" * 72)

    for w in sorted(whales, key=lambda x: x.rank):
        wallet_short = f"{w.wallet[:6]}...{w.wallet[-4:]}"
        if w.classification == "accumulating":
            score_str = f"Acc:{w.accumulation_score}"
        elif w.classification == "distributing":
            score_str = f"Dist:{w.distribution_score}"
        else:
            score_str = f"A:{w.accumulation_score}/D:{w.distribution_score}"

        print(
            f"  {w.rank:<5} {wallet_short:<16} {w.pct_supply:<10.2f} "
            f"{w.buy_count:<6} {w.sell_count:<6} {w.classification:<16} {score_str}"
        )

    print("-" * 72)

    # Detailed view for accumulating and distributing whales
    notable = [w for w in whales if w.classification != "holding"]
    if notable:
        print("\n  NOTABLE WHALE DETAILS")
        print("-" * 72)
        for w in notable:
            wallet_short = f"{w.wallet[:6]}...{w.wallet[-4:]}"
            print(f"\n  [{w.classification.upper()}] {wallet_short} (Rank #{w.rank})")
            print(f"    Balance: {w.balance:,.2f} tokens ({w.pct_supply:.2f}% of supply)")
            print(f"    Buys: {w.buy_count} trades | Total bought: {w.total_bought:,.2f}")
            print(f"    Sells: {w.sell_count} trades | Total sold: {w.total_sold:,.2f}")
            if w.transfers_to_exchange > 0:
                print(f"    Exchange transfers: {w.transfers_to_exchange} (distribution signal)")
            print(f"    Accumulation score: {w.accumulation_score}/10")
            print(f"    Distribution score: {w.distribution_score}/10")

    print("\n" + "=" * 72)
    print("  Note: This is informational analysis only, not financial advice.")
    print("=" * 72 + "\n")


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run whale tracking analysis."""
    parser = argparse.ArgumentParser(
        description="Track whale wallets for a Solana token"
    )
    parser.add_argument(
        "--mint",
        type=str,
        help="Token mint address to analyze",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic demo data (no API keys required)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=WHALE_TOP_N,
        help=f"Number of top holders to track (default: {WHALE_TOP_N})",
    )
    args = parser.parse_args()

    if args.demo:
        print("Running in demo mode with synthetic data...")
        demo_mint = "DemoTokenMint111111111111111111111111111111"
        whales = generate_demo_data()
        print_whale_report(whales, demo_mint, is_demo=True)
        return

    if not args.mint:
        print("Error: --mint is required (or use --demo for synthetic data)")
        sys.exit(1)

    if not HELIUS_API_KEY:
        print(
            "Warning: HELIUS_API_KEY not set. Using public RPC with limited "
            "transaction detail. Set HELIUS_API_KEY for enhanced data."
        )

    print(f"Fetching top holders for {args.mint[:16]}...")

    with httpx.Client() as client:
        # Step 1: Get top holders
        holders = get_top_holders(client, args.mint)
        if not holders:
            print("No holders found. Check the mint address.")
            sys.exit(1)

        # Filter to whale-level holders
        whale_holders = [
            h
            for h in holders[: args.top_n]
            if h.pct_supply >= WHALE_MIN_PCT_SUPPLY
        ]
        if not whale_holders:
            print(
                f"No holders found with >= {WHALE_MIN_PCT_SUPPLY}% of supply. "
                f"Top holder has {holders[0].pct_supply:.2f}%."
            )
            # Fall back to top N
            whale_holders = holders[: min(args.top_n, len(holders))]

        print(f"Found {len(whale_holders)} whale wallets. Analyzing activity...")

        # Step 2: Analyze each whale's activity
        whale_activities: list[WhaleActivity] = []
        for i, holder in enumerate(whale_holders):
            short_addr = f"{holder.wallet_address[:8]}..."
            print(f"  [{i + 1}/{len(whale_holders)}] Analyzing {short_addr}")

            transactions = get_wallet_transactions(
                client, holder.wallet_address, limit=20
            )
            activity = classify_whale_activity(holder, transactions)
            whale_activities.append(activity)
            time.sleep(0.2)  # Rate limit politeness

        # Step 3: Print report
        print_whale_report(whale_activities, args.mint)


if __name__ == "__main__":
    main()
