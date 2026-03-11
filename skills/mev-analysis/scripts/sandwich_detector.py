#!/usr/bin/env python3
"""Detect sandwich attacks around a Solana transaction.

Analyzes a transaction and its surrounding slot transactions to identify
potential sandwich attack patterns: same-token buy before and sell after
the target transaction by the same wallet.

Usage:
    python scripts/sandwich_detector.py                          # demo mode
    python scripts/sandwich_detector.py --tx <SIGNATURE>         # analyze real tx
    python scripts/sandwich_detector.py --demo                   # explicit demo

Dependencies:
    uv pip install httpx

Environment Variables:
    SOLANA_RPC_URL: Solana RPC endpoint (default: public mainnet-beta)
    HELIUS_API_KEY: Optional Helius API key for enhanced transaction parsing
    TX_SIGNATURE: Transaction signature to analyze (alternative to --tx flag)
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Configuration ───────────────────────────────────────────────────
SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
)
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
TX_SIGNATURE = os.getenv("TX_SIGNATURE", "")

# If Helius key is available, use Helius RPC for better parsing
if HELIUS_API_KEY:
    SOLANA_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Known MEV bot patterns (partial list — real detection uses heuristics)
KNOWN_MEV_PROGRAMS = [
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  # Jupiter v6
]

# Jito tip program addresses
JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4bVqkfRtQ7NmXwkiYGganbN",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2o2J5Yfc54gXokGe4vDbvL",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]

REQUEST_TIMEOUT = 30.0
MAX_SLOT_TXS = 50  # Max transactions to fetch from a slot


# ── Data Classes ────────────────────────────────────────────────────
@dataclass
class TokenTransfer:
    """A token transfer within a transaction."""

    mint: str
    source: str
    destination: str
    amount: float
    decimals: int


@dataclass
class ParsedTransaction:
    """Simplified parsed transaction for MEV analysis."""

    signature: str
    slot: int
    block_time: Optional[int]
    signer: str
    success: bool
    fee_lamports: int
    token_transfers: list[TokenTransfer] = field(default_factory=list)
    has_jito_tip: bool = False
    instruction_count: int = 0


@dataclass
class SandwichResult:
    """Result of sandwich detection analysis."""

    is_sandwiched: bool
    confidence: str  # "HIGH", "MEDIUM", "LOW", "NONE"
    attacker_wallet: Optional[str]
    front_run_tx: Optional[str]
    back_run_tx: Optional[str]
    token_mint: Optional[str]
    estimated_cost_usd: float
    details: list[str] = field(default_factory=list)


# ── RPC Helpers ─────────────────────────────────────────────────────
def rpc_request(method: str, params: list, client: httpx.Client) -> dict:
    """Send a JSON-RPC request to Solana RPC.

    Args:
        method: RPC method name.
        params: Method parameters.
        client: httpx Client instance.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
        RuntimeError: On RPC error response.
    """
    resp = client.post(
        SOLANA_RPC_URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result", {})


def fetch_transaction(
    signature: str, client: httpx.Client
) -> Optional[ParsedTransaction]:
    """Fetch and parse a transaction by signature.

    Args:
        signature: Transaction signature (base58).
        client: httpx Client instance.

    Returns:
        ParsedTransaction or None if not found.
    """
    try:
        result = rpc_request(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "commitment": "confirmed",
                },
            ],
            client,
        )
    except RuntimeError:
        return None

    if not result:
        return None

    tx_data = result.get("transaction", {})
    meta = result.get("meta", {})
    message = tx_data.get("message", {})
    account_keys = message.get("accountKeys", [])

    # Extract signer (first account key)
    signer = ""
    if account_keys:
        if isinstance(account_keys[0], dict):
            signer = account_keys[0].get("pubkey", "")
        else:
            signer = account_keys[0]

    # Parse token transfers from inner instructions and post/pre token balances
    transfers = _extract_token_transfers(meta)

    # Check for Jito tip
    has_jito_tip = _check_jito_tip(meta, message)

    # Count instructions
    instructions = message.get("instructions", [])
    inner = meta.get("innerInstructions", [])
    total_ix = len(instructions) + sum(
        len(ix_set.get("instructions", [])) for ix_set in inner
    )

    return ParsedTransaction(
        signature=signature,
        slot=result.get("slot", 0),
        block_time=result.get("blockTime"),
        signer=signer,
        success=meta.get("err") is None,
        fee_lamports=meta.get("fee", 0),
        token_transfers=transfers,
        has_jito_tip=has_jito_tip,
        instruction_count=total_ix,
    )


def _extract_token_transfers(meta: dict) -> list[TokenTransfer]:
    """Extract token transfers from transaction metadata.

    Args:
        meta: Transaction metadata from RPC response.

    Returns:
        List of TokenTransfer objects.
    """
    transfers = []
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])

    # Build balance change map: (account_index, mint) -> change
    pre_map: dict[tuple[int, str], float] = {}
    for bal in pre_balances:
        idx = bal.get("accountIndex", -1)
        mint = bal.get("mint", "")
        amount = float(bal.get("uiTokenAmount", {}).get("uiAmount") or 0)
        pre_map[(idx, mint)] = amount

    for bal in post_balances:
        idx = bal.get("accountIndex", -1)
        mint = bal.get("mint", "")
        post_amount = float(
            bal.get("uiTokenAmount", {}).get("uiAmount") or 0
        )
        pre_amount = pre_map.get((idx, mint), 0.0)
        change = post_amount - pre_amount

        if abs(change) > 0:
            owner = bal.get("owner", "")
            decimals = bal.get("uiTokenAmount", {}).get("decimals", 0)
            transfers.append(
                TokenTransfer(
                    mint=mint,
                    source=owner if change < 0 else "",
                    destination=owner if change > 0 else "",
                    amount=change,
                    decimals=decimals,
                )
            )

    return transfers


def _check_jito_tip(meta: dict, message: dict) -> bool:
    """Check if the transaction includes a Jito tip.

    Args:
        meta: Transaction metadata.
        message: Transaction message.

    Returns:
        True if a Jito tip transfer is detected.
    """
    # Check if any account in the transaction is a Jito tip account
    account_keys = message.get("accountKeys", [])
    for key in account_keys:
        pubkey = key.get("pubkey", "") if isinstance(key, dict) else key
        if pubkey in JITO_TIP_ACCOUNTS:
            return True
    return False


def fetch_slot_transactions(
    slot: int, client: httpx.Client
) -> list[str]:
    """Fetch transaction signatures from a specific slot.

    Args:
        slot: Slot number.
        client: httpx Client instance.

    Returns:
        List of transaction signatures in the slot.
    """
    try:
        result = rpc_request(
            "getBlock",
            [
                slot,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                    "transactionDetails": "signatures",
                    "rewards": False,
                },
            ],
            client,
        )
    except RuntimeError:
        return []

    if not result:
        return []

    signatures = result.get("signatures", [])
    return signatures[:MAX_SLOT_TXS]


# ── Sandwich Detection ─────────────────────────────────────────────
def detect_sandwich(
    target_tx: ParsedTransaction,
    slot_txs: list[ParsedTransaction],
) -> SandwichResult:
    """Analyze whether a transaction was sandwiched.

    Looks for the pattern:
    1. TX_A: Wallet W buys token T (front-run)
    2. TARGET: Your swap of token T (victim)
    3. TX_B: Wallet W sells token T (back-run)

    Where TX_A appears before TARGET and TX_B after in slot ordering.

    Args:
        target_tx: The target transaction to analyze.
        slot_txs: Other transactions in the same slot.

    Returns:
        SandwichResult with detection outcome.
    """
    details: list[str] = []

    # Get mints involved in target transaction
    target_mints = set()
    for t in target_tx.token_transfers:
        if t.mint:
            target_mints.add(t.mint)

    if not target_mints:
        return SandwichResult(
            is_sandwiched=False,
            confidence="NONE",
            attacker_wallet=None,
            front_run_tx=None,
            back_run_tx=None,
            token_mint=None,
            estimated_cost_usd=0.0,
            details=["No token transfers found in target transaction"],
        )

    details.append(
        f"Target tx involves {len(target_mints)} token mint(s): "
        f"{', '.join(list(target_mints)[:3])}"
    )

    # Find potential front-run/back-run pairs
    # Group slot transactions by signer and mint
    candidates: dict[str, dict[str, list[ParsedTransaction]]] = {}
    for tx in slot_txs:
        if tx.signature == target_tx.signature:
            continue
        if not tx.success:
            continue
        for transfer in tx.token_transfers:
            if transfer.mint in target_mints:
                signer = tx.signer
                mint = transfer.mint
                if signer not in candidates:
                    candidates[signer] = {}
                if mint not in candidates[signer]:
                    candidates[signer][mint] = []
                candidates[signer][mint].append(tx)

    if not candidates:
        return SandwichResult(
            is_sandwiched=False,
            confidence="NONE",
            attacker_wallet=None,
            front_run_tx=None,
            back_run_tx=None,
            token_mint=None,
            estimated_cost_usd=0.0,
            details=details
            + ["No other transactions in this slot touch the same tokens"],
        )

    # Look for buy-before + sell-after pattern
    best_match: Optional[SandwichResult] = None
    best_confidence_rank = 0

    for signer, mint_txs in candidates.items():
        for mint, txs in mint_txs.items():
            if len(txs) < 2:
                continue

            # Check for opposite-direction transfers (buy and sell)
            buys = [
                tx
                for tx in txs
                if any(
                    t.amount > 0 and t.mint == mint
                    for t in tx.token_transfers
                )
            ]
            sells = [
                tx
                for tx in txs
                if any(
                    t.amount < 0 and t.mint == mint
                    for t in tx.token_transfers
                )
            ]

            if buys and sells:
                # Potential sandwich found
                has_jito = any(tx.has_jito_tip for tx in txs)
                high_ix_count = any(tx.instruction_count > 5 for tx in txs)

                confidence_score = 0
                indicators = []

                if has_jito:
                    confidence_score += 3
                    indicators.append("Uses Jito bundles")
                if high_ix_count:
                    confidence_score += 1
                    indicators.append("High instruction count")
                if len(buys) == 1 and len(sells) == 1:
                    confidence_score += 2
                    indicators.append("Single buy + single sell pattern")
                if signer != target_tx.signer:
                    confidence_score += 1
                    indicators.append("Different signer from target")

                if confidence_score >= 4:
                    confidence = "HIGH"
                elif confidence_score >= 2:
                    confidence = "MEDIUM"
                else:
                    confidence = "LOW"

                confidence_rank = confidence_score

                if confidence_rank > best_confidence_rank:
                    best_confidence_rank = confidence_rank
                    best_match = SandwichResult(
                        is_sandwiched=confidence_score >= 2,
                        confidence=confidence,
                        attacker_wallet=signer,
                        front_run_tx=buys[0].signature,
                        back_run_tx=sells[0].signature,
                        token_mint=mint,
                        estimated_cost_usd=0.0,  # Would need price data
                        details=details + indicators,
                    )

    if best_match:
        return best_match

    return SandwichResult(
        is_sandwiched=False,
        confidence="NONE",
        attacker_wallet=None,
        front_run_tx=None,
        back_run_tx=None,
        token_mint=None,
        estimated_cost_usd=0.0,
        details=details
        + [
            "No buy-sell pairs found from the same wallet "
            "around the target transaction"
        ],
    )


# ── MEV Wallet Heuristics ──────────────────────────────────────────
def is_likely_mev_wallet(
    tx_count: int,
    avg_hold_time_seconds: float,
    jito_usage_pct: float,
) -> dict:
    """Heuristic check for MEV bot wallet characteristics.

    Args:
        tx_count: Number of transactions in last 24h.
        avg_hold_time_seconds: Average time tokens are held.
        jito_usage_pct: Percentage of transactions using Jito.

    Returns:
        Assessment dict with probability and indicators.
    """
    score = 0
    indicators = []

    if tx_count > 500:
        score += 3
        indicators.append(f"Very high tx count ({tx_count}/day)")
    elif tx_count > 100:
        score += 2
        indicators.append(f"High tx count ({tx_count}/day)")

    if avg_hold_time_seconds < 5:
        score += 3
        indicators.append(
            f"Near-zero hold time ({avg_hold_time_seconds:.1f}s)"
        )
    elif avg_hold_time_seconds < 60:
        score += 2
        indicators.append(f"Very short hold time ({avg_hold_time_seconds:.0f}s)")

    if jito_usage_pct > 80:
        score += 3
        indicators.append(f"Heavy Jito usage ({jito_usage_pct:.0f}%)")
    elif jito_usage_pct > 40:
        score += 2
        indicators.append(f"Moderate Jito usage ({jito_usage_pct:.0f}%)")

    if score >= 7:
        probability = "VERY HIGH"
    elif score >= 5:
        probability = "HIGH"
    elif score >= 3:
        probability = "MEDIUM"
    else:
        probability = "LOW"

    return {
        "probability": probability,
        "score": score,
        "max_score": 9,
        "indicators": indicators,
    }


# ── Demo Mode ───────────────────────────────────────────────────────
def run_demo() -> None:
    """Run a demonstration with synthetic sandwich attack data."""
    print("=" * 70)
    print("SANDWICH ATTACK DETECTOR — DEMO MODE")
    print("=" * 70)
    print()
    print("Simulating analysis of a sandwiched SOL → TOKEN_X swap...")
    print()

    # Synthetic target transaction
    target = ParsedTransaction(
        signature="5xDemoTargetTx111111111111111111111111111111111111",
        slot=280_000_000,
        block_time=1710000000,
        signer="UserWa11et1111111111111111111111111111111111",
        success=True,
        fee_lamports=5000,
        token_transfers=[
            TokenTransfer(
                mint="DemoToken111111111111111111111111111111111111",
                source="",
                destination="UserWa11et1111111111111111111111111111111111",
                amount=9850.0,  # Got less than expected (10000)
                decimals=6,
            ),
            TokenTransfer(
                mint="So11111111111111111111111111111111111111112",
                source="UserWa11et1111111111111111111111111111111111",
                destination="",
                amount=-10.0,  # Spent 10 SOL
                decimals=9,
            ),
        ],
        has_jito_tip=False,
        instruction_count=4,
    )

    # Synthetic attacker front-run
    front_run = ParsedTransaction(
        signature="5xDemoFrontRun11111111111111111111111111111111111",
        slot=280_000_000,
        block_time=1710000000,
        signer="MEVBot111111111111111111111111111111111111111",
        success=True,
        fee_lamports=5000,
        token_transfers=[
            TokenTransfer(
                mint="DemoToken111111111111111111111111111111111111",
                source="",
                destination="MEVBot111111111111111111111111111111111111111",
                amount=50000.0,
                decimals=6,
            ),
        ],
        has_jito_tip=True,
        instruction_count=8,
    )

    # Synthetic attacker back-run
    back_run = ParsedTransaction(
        signature="5xDemoBackRun111111111111111111111111111111111111",
        slot=280_000_000,
        block_time=1710000000,
        signer="MEVBot111111111111111111111111111111111111111",
        success=True,
        fee_lamports=5000,
        token_transfers=[
            TokenTransfer(
                mint="DemoToken111111111111111111111111111111111111",
                source="MEVBot111111111111111111111111111111111111111",
                destination="",
                amount=-50000.0,
                decimals=6,
            ),
        ],
        has_jito_tip=True,
        instruction_count=8,
    )

    slot_txs = [front_run, target, back_run]
    result = detect_sandwich(target, slot_txs)

    _print_result(target, result)

    # Also demo the MEV wallet heuristic
    print()
    print("-" * 70)
    print("MEV WALLET HEURISTIC ANALYSIS")
    print("-" * 70)
    wallet_assessment = is_likely_mev_wallet(
        tx_count=2400,
        avg_hold_time_seconds=1.2,
        jito_usage_pct=92.0,
    )
    print(f"  Wallet: MEVBot111...111")
    print(f"  MEV probability: {wallet_assessment['probability']}")
    print(f"  Score: {wallet_assessment['score']}/{wallet_assessment['max_score']}")
    print(f"  Indicators:")
    for ind in wallet_assessment["indicators"]:
        print(f"    - {ind}")

    print()
    print("=" * 70)
    print("NOTE: This is synthetic demo data. Use --tx <SIGNATURE> to analyze")
    print("a real transaction with live on-chain data.")
    print("=" * 70)


def _print_result(
    target: ParsedTransaction, result: SandwichResult
) -> None:
    """Print sandwich detection results.

    Args:
        target: The target transaction.
        result: Detection result.
    """
    print("-" * 70)
    print("SANDWICH DETECTION RESULT")
    print("-" * 70)
    print(f"  Target TX:    {target.signature[:20]}...")
    print(f"  Slot:         {target.slot}")
    print(f"  Signer:       {target.signer[:20]}...")
    print()

    if result.is_sandwiched:
        print(f"  *** SANDWICH DETECTED (Confidence: {result.confidence}) ***")
        print()
        print(f"  Attacker:     {result.attacker_wallet or 'Unknown'}")
        print(f"  Front-run TX: {(result.front_run_tx or '')[:20]}...")
        print(f"  Back-run TX:  {(result.back_run_tx or '')[:20]}...")
        print(f"  Token mint:   {(result.token_mint or '')[:20]}...")
        if result.estimated_cost_usd > 0:
            print(f"  Est. cost:    ${result.estimated_cost_usd:.2f}")
    else:
        print(f"  No sandwich detected (Confidence: {result.confidence})")

    if result.details:
        print()
        print("  Analysis details:")
        for detail in result.details:
            print(f"    - {detail}")


# ── Live Analysis ───────────────────────────────────────────────────
def analyze_transaction(signature: str) -> None:
    """Analyze a real transaction for sandwich attacks.

    Args:
        signature: Transaction signature to analyze.
    """
    print(f"Fetching transaction: {signature[:20]}...")
    print(f"RPC endpoint: {SOLANA_RPC_URL[:50]}...")
    print()

    with httpx.Client() as client:
        # Fetch target transaction
        target = fetch_transaction(signature, client)
        if not target:
            print("ERROR: Could not fetch transaction. Check the signature")
            print("and ensure the RPC endpoint is accessible.")
            sys.exit(1)

        print(f"Transaction found in slot {target.slot}")
        print(f"Signer: {target.signer}")
        print(f"Success: {target.success}")
        print(f"Token transfers: {len(target.token_transfers)}")
        print()

        if not target.token_transfers:
            print("No token transfers found. This may not be a swap transaction.")
            print("Sandwich detection requires a token swap to analyze.")
            return

        # Fetch slot transactions
        print(f"Fetching transactions from slot {target.slot}...")
        slot_sigs = fetch_slot_transactions(target.slot, client)
        print(f"Found {len(slot_sigs)} transactions in slot")
        print()

        if len(slot_sigs) < 2:
            print("Too few transactions in slot for sandwich analysis.")
            return

        # Parse surrounding transactions (limit to avoid rate limits)
        print("Parsing surrounding transactions for sandwich patterns...")
        slot_txs: list[ParsedTransaction] = []
        analyzed = 0
        for sig in slot_sigs:
            if sig == signature:
                continue
            if analyzed >= MAX_SLOT_TXS:
                break
            tx = fetch_transaction(sig, client)
            if tx and tx.success:
                slot_txs.append(tx)
            analyzed += 1

        print(f"Parsed {len(slot_txs)} surrounding transactions")
        print()

        # Run detection
        result = detect_sandwich(target, slot_txs)
        _print_result(target, result)


# ── Main ────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point for sandwich detector."""
    parser = argparse.ArgumentParser(
        description="Detect sandwich attacks around a Solana transaction"
    )
    parser.add_argument(
        "--tx",
        type=str,
        default="",
        help="Transaction signature to analyze",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic demo data",
    )
    args = parser.parse_args()

    signature = args.tx or TX_SIGNATURE

    if args.demo or not signature:
        run_demo()
    else:
        analyze_transaction(signature)


if __name__ == "__main__":
    main()
