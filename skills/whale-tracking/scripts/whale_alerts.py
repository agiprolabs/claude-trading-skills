#!/usr/bin/env python3
"""Monitor whale wallets and generate alerts for large transactions.

Watches a configurable list of whale wallet addresses, checks for new
large transactions, classifies each as a buy or sell, estimates market
impact, and prints formatted alerts.

Usage:
    python scripts/whale_alerts.py --demo
    python scripts/whale_alerts.py --wallets wallet1,wallet2 --min-sol 100

Dependencies:
    uv pip install httpx

Environment Variables:
    HELIUS_API_KEY: Your Helius API key (optional in demo mode)
    SOLANA_RPC_URL: Custom RPC endpoint (optional)
"""

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
HELIUS_API_BASE = "https://api.helius.xyz/v0"

# Default alert thresholds
DEFAULT_MIN_SOL = 100.0  # Minimum trade size in SOL to trigger alert
SOL_PRICE_USD = 150.0  # Approximate SOL price for USD estimates

# Known exchange wallet prefixes for transfer classification
EXCHANGE_PREFIXES: dict[str, str] = {
    "5tzFkiKsc": "Binance",
    "JCnc": "OKX",
    "AC5R": "Bybit",
    "9WzDX": "Coinbase",
}


# ── Data Models ─────────────────────────────────────────────────────
@dataclass
class WhaleAlert:
    """A single whale transaction alert."""

    wallet: str
    wallet_label: str
    signature: str
    timestamp: float
    action: str  # "buy", "sell", "transfer_out", "transfer_in"
    token_mint: str
    token_symbol: str
    token_amount: float
    sol_value: float
    usd_value: float
    exchange_name: Optional[str]
    impact_estimate: str  # "low", "medium", "high", "extreme"
    priority: str  # "info", "warning", "critical"


# ── Helius API ──────────────────────────────────────────────────────
def fetch_wallet_transactions(
    client: httpx.Client,
    wallet: str,
    limit: int = 10,
) -> list[dict]:
    """Fetch recent enhanced transactions for a wallet from Helius.

    Args:
        client: httpx Client instance.
        wallet: Wallet address to query.
        limit: Maximum transactions to return.

    Returns:
        List of enhanced transaction dicts.

    Raises:
        httpx.HTTPStatusError: On API errors.
    """
    if not HELIUS_API_KEY:
        return []

    url = (
        f"{HELIUS_API_BASE}/addresses/{wallet}/transactions"
        f"?api-key={HELIUS_API_KEY}&limit={limit}"
    )
    try:
        resp = client.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"  API error for {wallet[:8]}...: {e.response.status_code}")
        return []
    except Exception as e:
        print(f"  Error fetching transactions for {wallet[:8]}...: {e}")
        return []


def parse_transaction_to_alert(
    tx: dict,
    wallet: str,
    wallet_label: str,
    min_sol: float,
) -> Optional[WhaleAlert]:
    """Parse an enhanced transaction into a WhaleAlert if it meets thresholds.

    Args:
        tx: Enhanced transaction dict from Helius.
        wallet: The tracked wallet address.
        wallet_label: Human-readable label for the wallet.
        min_sol: Minimum SOL value to generate an alert.

    Returns:
        WhaleAlert if the transaction is notable, None otherwise.
    """
    tx_type = tx.get("type", "UNKNOWN")
    signature = tx.get("signature", "unknown")
    timestamp = tx.get("timestamp", 0)
    token_transfers = tx.get("tokenTransfers", [])
    native_transfers = tx.get("nativeTransfers", [])

    # Check native SOL transfers
    sol_moved = 0.0
    for nt in native_transfers:
        if nt.get("fromUserAccount") == wallet:
            sol_moved -= nt.get("amount", 0) / 1e9
        elif nt.get("toUserAccount") == wallet:
            sol_moved += nt.get("amount", 0) / 1e9

    # Check token transfers for the main token movement
    token_mint = ""
    token_symbol = ""
    token_amount = 0.0
    action = "unknown"
    exchange_name = None

    for tt in token_transfers:
        from_addr = tt.get("fromUserAccount", "")
        to_addr = tt.get("toUserAccount", "")
        amount = float(tt.get("tokenAmount", 0) or 0)
        mint = tt.get("mint", "")

        if to_addr == wallet and amount > 0:
            action = "buy" if tx_type == "SWAP" else "transfer_in"
            token_mint = mint
            token_amount = amount
        elif from_addr == wallet and amount > 0:
            action = "sell" if tx_type == "SWAP" else "transfer_out"
            token_mint = mint
            token_amount = amount
            # Check if transfer to exchange
            for prefix, name in EXCHANGE_PREFIXES.items():
                if to_addr.startswith(prefix):
                    exchange_name = name
                    break

    # Estimate SOL value (use native transfer as proxy)
    sol_value = abs(sol_moved)
    if sol_value < min_sol:
        return None

    usd_value = sol_value * SOL_PRICE_USD

    # Impact estimate
    if sol_value >= 1000:
        impact = "extreme"
    elif sol_value >= 500:
        impact = "high"
    elif sol_value >= 200:
        impact = "medium"
    else:
        impact = "low"

    # Alert priority
    if sol_value >= 500 or exchange_name:
        priority = "critical"
    elif sol_value >= 200:
        priority = "warning"
    else:
        priority = "info"

    return WhaleAlert(
        wallet=wallet,
        wallet_label=wallet_label,
        signature=signature,
        timestamp=timestamp,
        action=action,
        token_mint=token_mint or "unknown",
        token_symbol=token_symbol or mint_to_symbol(token_mint),
        token_amount=token_amount,
        sol_value=round(sol_value, 2),
        usd_value=round(usd_value, 2),
        exchange_name=exchange_name,
        impact_estimate=impact,
        priority=priority,
    )


def mint_to_symbol(mint: str) -> str:
    """Map common token mints to symbols.

    Args:
        mint: Token mint address.

    Returns:
        Token symbol or shortened mint address.
    """
    known = {
        "So11111111111111111111111111111111111111112": "SOL",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    }
    return known.get(mint, f"{mint[:6]}..." if mint else "UNKNOWN")


# ── Demo Mode ───────────────────────────────────────────────────────
def generate_demo_alerts() -> list[WhaleAlert]:
    """Generate 5 synthetic whale trade alerts for demonstration.

    Returns:
        List of WhaleAlert objects with simulated data.
    """
    random.seed(123)
    base_time = time.time()

    demo_trades = [
        {
            "wallet": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            "label": "Smart Money Alpha",
            "action": "buy",
            "token": "BONK",
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "token_amount": 25_000_000_000.0,
            "sol_value": 350.0,
        },
        {
            "wallet": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
            "label": "Whale Distributor",
            "action": "sell",
            "token": "WIF",
            "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "token_amount": 500_000.0,
            "sol_value": 800.0,
        },
        {
            "wallet": "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",
            "label": "Fund Wallet #3",
            "action": "transfer_out",
            "token": "JUP",
            "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "token_amount": 2_000_000.0,
            "sol_value": 600.0,
            "exchange": "Binance",
        },
        {
            "wallet": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
            "label": "DCA Accumulator",
            "action": "buy",
            "token": "PYTH",
            "mint": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
            "token_amount": 1_500_000.0,
            "sol_value": 150.0,
        },
        {
            "wallet": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
            "label": "Known Insider",
            "action": "sell",
            "token": "RNDR",
            "mint": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",
            "token_amount": 100_000.0,
            "sol_value": 1200.0,
        },
    ]

    alerts: list[WhaleAlert] = []
    for i, trade in enumerate(demo_trades):
        sol_val = trade["sol_value"]
        usd_val = sol_val * SOL_PRICE_USD

        if sol_val >= 1000:
            impact = "extreme"
        elif sol_val >= 500:
            impact = "high"
        elif sol_val >= 200:
            impact = "medium"
        else:
            impact = "low"

        exchange_name = trade.get("exchange")
        if sol_val >= 500 or exchange_name:
            priority = "critical"
        elif sol_val >= 200:
            priority = "warning"
        else:
            priority = "info"

        alert = WhaleAlert(
            wallet=trade["wallet"],
            wallet_label=trade["label"],
            signature=f"DemoSig{i + 1}{'x' * 60}",
            timestamp=base_time - (i * 300),  # 5 min apart
            action=trade["action"],
            token_mint=trade["mint"],
            token_symbol=trade["token"],
            token_amount=trade["token_amount"],
            sol_value=sol_val,
            usd_value=round(usd_val, 2),
            exchange_name=exchange_name,
            impact_estimate=impact,
            priority=priority,
        )
        alerts.append(alert)

    return alerts


# ── Alert Formatting ────────────────────────────────────────────────
PRIORITY_ICONS = {
    "info": "[INFO]",
    "warning": "[WARN]",
    "critical": "[CRIT]",
}

ACTION_LABELS = {
    "buy": "BOUGHT",
    "sell": "SOLD",
    "transfer_out": "TRANSFERRED OUT",
    "transfer_in": "RECEIVED",
    "unknown": "MOVED",
}


def format_alert(alert: WhaleAlert) -> str:
    """Format a single whale alert as a readable string.

    Args:
        alert: The whale alert to format.

    Returns:
        Multi-line formatted alert string.
    """
    icon = PRIORITY_ICONS.get(alert.priority, "[???]")
    action_label = ACTION_LABELS.get(alert.action, "ACTIVITY")
    ts = datetime.fromtimestamp(alert.timestamp, tz=timezone.utc)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    wallet_short = f"{alert.wallet[:6]}...{alert.wallet[-4:]}"

    lines = [
        f"  {icon} {alert.wallet_label} ({wallet_short})",
        f"    Action:  {action_label} {alert.token_amount:,.2f} {alert.token_symbol}",
        f"    Value:   {alert.sol_value:,.2f} SOL (~${alert.usd_value:,.0f})",
        f"    Impact:  {alert.impact_estimate.upper()}",
        f"    Time:    {ts_str}",
        f"    Tx:      {alert.signature[:16]}...",
    ]

    if alert.exchange_name:
        lines.insert(
            3, f"    Dest:    {alert.exchange_name} (exchange deposit)"
        )

    return "\n".join(lines)


def print_alerts(
    alerts: list[WhaleAlert], is_demo: bool = False
) -> None:
    """Print all whale alerts in a formatted report.

    Args:
        alerts: List of whale alerts to display.
        is_demo: Whether these are demo alerts.
    """
    header = "WHALE ALERTS"
    if is_demo:
        header += " [DEMO MODE - SIMULATED DATA]"

    print("\n" + "=" * 72)
    print(f"  {header}")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Alerts: {len(alerts)}")
    print("=" * 72)

    # Summary
    buys = [a for a in alerts if a.action == "buy"]
    sells = [a for a in alerts if a.action in ("sell", "transfer_out")]
    total_buy_sol = sum(a.sol_value for a in buys)
    total_sell_sol = sum(a.sol_value for a in sells)

    print(f"\n  Buy alerts:  {len(buys)} ({total_buy_sol:,.2f} SOL)")
    print(f"  Sell alerts: {len(sells)} ({total_sell_sol:,.2f} SOL)")

    if total_buy_sol > total_sell_sol * 1.5:
        print("  Net flow:    BULLISH (more whale buying than selling)")
    elif total_sell_sol > total_buy_sol * 1.5:
        print("  Net flow:    BEARISH (more whale selling than buying)")
    else:
        print("  Net flow:    NEUTRAL")

    # Print each alert
    critical = [a for a in alerts if a.priority == "critical"]
    warning = [a for a in alerts if a.priority == "warning"]
    info = [a for a in alerts if a.priority == "info"]

    if critical:
        print("\n" + "-" * 72)
        print("  CRITICAL ALERTS")
        print("-" * 72)
        for alert in critical:
            print(format_alert(alert))
            print()

    if warning:
        print("-" * 72)
        print("  WARNING ALERTS")
        print("-" * 72)
        for alert in warning:
            print(format_alert(alert))
            print()

    if info:
        print("-" * 72)
        print("  INFO ALERTS")
        print("-" * 72)
        for alert in info:
            print(format_alert(alert))
            print()

    print("=" * 72)
    print("  Note: This is informational analysis only, not financial advice.")
    print("=" * 72 + "\n")


# ── Live Monitoring ─────────────────────────────────────────────────
def monitor_wallets(
    wallets: dict[str, str],
    min_sol: float,
    poll_interval: int = 60,
    max_checks: int = 5,
) -> list[WhaleAlert]:
    """Poll whale wallets for new transactions and generate alerts.

    Args:
        wallets: Dict mapping wallet address to label.
        min_sol: Minimum SOL value to trigger an alert.
        poll_interval: Seconds between polling cycles.
        max_checks: Maximum number of polling cycles (0 = unlimited).

    Returns:
        All alerts generated across polling cycles.
    """
    if not HELIUS_API_KEY:
        print(
            "Error: HELIUS_API_KEY required for live monitoring. "
            "Use --demo for simulated alerts."
        )
        return []

    all_alerts: list[WhaleAlert] = []
    seen_signatures: set[str] = set()
    check_count = 0

    print(f"Monitoring {len(wallets)} whale wallets (min: {min_sol} SOL)...")
    print(f"Polling every {poll_interval} seconds. Press Ctrl+C to stop.\n")

    with httpx.Client() as client:
        try:
            while max_checks == 0 or check_count < max_checks:
                check_count += 1
                print(
                    f"[Check #{check_count}] "
                    f"{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
                )

                cycle_alerts: list[WhaleAlert] = []

                for wallet, label in wallets.items():
                    txs = fetch_wallet_transactions(
                        client, wallet, limit=5
                    )
                    for tx in txs:
                        sig = tx.get("signature", "")
                        if sig in seen_signatures:
                            continue
                        seen_signatures.add(sig)

                        alert = parse_transaction_to_alert(
                            tx, wallet, label, min_sol
                        )
                        if alert:
                            cycle_alerts.append(alert)

                    time.sleep(0.2)  # Rate limit

                if cycle_alerts:
                    print(f"  Found {len(cycle_alerts)} new alert(s)")
                    for alert in cycle_alerts:
                        print(format_alert(alert))
                        print()
                    all_alerts.extend(cycle_alerts)
                else:
                    print("  No new whale activity above threshold")

                if max_checks == 0 or check_count < max_checks:
                    time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user.")

    return all_alerts


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Run whale alert monitoring."""
    parser = argparse.ArgumentParser(
        description="Monitor whale wallets for large transactions"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with simulated whale alerts (no API keys required)",
    )
    parser.add_argument(
        "--wallets",
        type=str,
        help="Comma-separated wallet addresses to monitor",
    )
    parser.add_argument(
        "--min-sol",
        type=float,
        default=DEFAULT_MIN_SOL,
        help=f"Minimum SOL value to trigger alert (default: {DEFAULT_MIN_SOL})",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--max-checks",
        type=int,
        default=5,
        help="Max polling cycles, 0 for unlimited (default: 5)",
    )
    args = parser.parse_args()

    if args.demo:
        print("Running in demo mode with simulated whale alerts...")
        alerts = generate_demo_alerts()
        print_alerts(alerts, is_demo=True)
        return

    if not args.wallets:
        print(
            "Error: --wallets required (comma-separated addresses) "
            "or use --demo for simulated alerts"
        )
        sys.exit(1)

    if not HELIUS_API_KEY:
        print(
            "Error: Set HELIUS_API_KEY environment variable for live monitoring."
        )
        sys.exit(1)

    # Parse wallet list into dict (address -> short label)
    wallet_list = [w.strip() for w in args.wallets.split(",") if w.strip()]
    wallets = {
        addr: f"Whale #{i + 1} ({addr[:6]}...)"
        for i, addr in enumerate(wallet_list)
    }

    alerts = monitor_wallets(
        wallets=wallets,
        min_sol=args.min_sol,
        poll_interval=args.interval,
        max_checks=args.max_checks,
    )

    if alerts:
        print(f"\nTotal alerts generated: {len(alerts)}")
    else:
        print("\nNo whale alerts generated during monitoring period.")


if __name__ == "__main__":
    main()
