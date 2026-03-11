---
name: jito-bundles
description: Jito bundle submission for MEV protection on Solana — bundle building, tip strategies, block engine endpoints, and landing rate optimization
---

# Jito Bundle Submission for Solana

Jito bundles allow you to submit up to 5 Solana transactions that execute **atomically** — either all land in the same slot or none do. This is the primary mechanism for MEV protection and competitive transaction execution on Solana. Approximately 85%+ of Solana validators run the Jito-modified client, making bundles the standard for reliable, front-run-resistant execution.

> **EXECUTION SKILL — SAFETY WARNING**: Submitting bundles spends real SOL on tips. Always test with `--demo` mode first. Never submit bundles with real funds without explicit confirmation. Default to simulation/dry-run in all scripts and examples.

## When to Use Bundles

| Scenario | Use Bundle? | Why |
|----------|-------------|-----|
| Swap on illiquid token | Yes | Prevents sandwich attacks |
| Multi-step arbitrage | Yes | Atomic execution prevents partial fills |
| Liquidation | Yes | Competitive — tip determines priority |
| Simple SOL transfer | No | Priority fees are cheaper and sufficient |
| Time-insensitive swap | Maybe | Bundles cost tips; priority fees may suffice |
| NFT mint / competitive action | Yes | Guarantees ordering within the slot |

## Core Concepts

### Bundle Anatomy

A Jito bundle is a JSON-RPC request containing 1-5 base58-encoded signed transactions. The transactions execute sequentially and atomically within a single slot.

```
Bundle = [Tx1, Tx2, ..., TxN]  (N <= 5)

- All transactions must be signed
- Transactions execute in order: Tx1 → Tx2 → ... → TxN
- If ANY transaction fails, the ENTIRE bundle is dropped
- The tip instruction goes in the LAST transaction (last instruction)
- Bundle has ~2 slots (~800ms) to land before expiry
```

### Tip Mechanism

Tips are SOL transfers to one of Jito's 8 tip accounts. The tip incentivizes validators to include your bundle.

```python
# Tip is a standard SOL transfer instruction
tip_instruction = transfer(
    from_pubkey=your_wallet,
    to_pubkey=tip_account,      # One of 8 Jito tip accounts
    lamports=tip_amount          # Tip in lamports (1 SOL = 1e9 lamports)
)
# Add as the LAST instruction of the LAST transaction in the bundle
```

Tip accounts are fetched dynamically via `getTipAccounts`. Rotate through them to distribute load.

### Block Engine Endpoints

Jito operates geographically distributed block engines. Choose the one closest to your infrastructure:

| Region | Endpoint |
|--------|----------|
| New York | `https://mainnet.block-engine.jito.wtf` |
| Amsterdam | `https://amsterdam.block-engine.jito.wtf` |
| Frankfurt | `https://frankfurt.block-engine.jito.wtf` |
| Tokyo | `https://tokyo.block-engine.jito.wtf` |

All endpoints accept JSON-RPC over HTTPS on port 443. The `/api/v1/bundles` path handles bundle operations.

## API Methods

### sendBundle

Submit a bundle of up to 5 transactions.

```python
import httpx

BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf"

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "sendBundle",
    "params": [
        [tx1_base58, tx2_base58],  # List of base58-encoded signed txs
    ]
}

resp = httpx.post(f"{BLOCK_ENGINE}/api/v1/bundles", json=payload)
data = resp.json()
bundle_id = data["result"]  # UUID string
```

### getBundleStatuses

Check the landing status of submitted bundles (up to 5 bundle IDs per request).

```python
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getBundleStatuses",
    "params": [[bundle_id]]
}
resp = httpx.post(f"{BLOCK_ENGINE}/api/v1/bundles", json=payload)
statuses = resp.json()["result"]["value"]
# Each status: {bundle_id, status, slot, transactions: [{signature, ...}]}
# status: "Invalid", "Pending", "Failed", "Landed"
```

### getTipAccounts

Fetch the current list of Jito tip accounts.

```python
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getTipAccounts",
    "params": []
}
resp = httpx.post(f"{BLOCK_ENGINE}/api/v1/bundles", json=payload)
tip_accounts = resp.json()["result"]  # List of 8 base58 pubkeys
```

### getInflightBundleStatuses

Check status of bundles that haven't landed yet (in-flight).

```python
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "getInflightBundleStatuses",
    "params": [[bundle_id]]
}
resp = httpx.post(f"{BLOCK_ENGINE}/api/v1/bundles", json=payload)
# status: "Pending", "Failed", "Landed"
```

## Bundle Construction Pattern

A typical bundle for a protected swap:

```python
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction
from solders.system_program import transfer, TransferParams
from solders.pubkey import Pubkey
import random

def build_protected_swap_bundle(
    swap_ix: Instruction,
    payer: Pubkey,
    tip_lamports: int,
    tip_accounts: list[str],
    recent_blockhash: str,
) -> list[VersionedTransaction]:
    """Build a 1-tx bundle: swap + tip in the same transaction.

    For simple swaps, a single-transaction bundle is sufficient.
    The tip instruction is appended as the last instruction.
    """
    # Pick a random tip account
    tip_account = Pubkey.from_string(random.choice(tip_accounts))

    # Tip instruction
    tip_ix = transfer(TransferParams(
        from_pubkey=payer,
        to_pubkey=tip_account,
        lamports=tip_lamports,
    ))

    # Build transaction with swap + tip
    msg = MessageV0.try_compile(
        payer=payer,
        instructions=[swap_ix, tip_ix],
        address_lookup_table_accounts=[],
        recent_blockhash=recent_blockhash,
    )
    tx = VersionedTransaction(msg, [keypair])
    return [tx]
```

## Tip Sizing Guide

| Scenario | Tip Range (lamports) | Tip Range (SOL) |
|----------|---------------------|-----------------|
| Normal swap (low urgency) | 1,000 - 10,000 | 0.000001 - 0.00001 |
| Normal swap (standard) | 10,000 - 50,000 | 0.00001 - 0.00005 |
| Competitive action (arb, liquidation) | 50,000 - 500,000 | 0.00005 - 0.0005 |
| Highly competitive (NFT mint, MEV) | 500,000 - 5,000,000 | 0.0005 - 0.005 |
| Emergency (must land this slot) | 5,000,000+ | 0.005+ |

Dynamic tip calculation based on recent tip levels:

```python
def calculate_dynamic_tip(
    base_tip: int = 10_000,
    urgency_multiplier: float = 1.0,
    recent_tip_percentile_50: int = 15_000,
) -> int:
    """Calculate tip based on urgency and recent network tips.

    Args:
        base_tip: Minimum tip in lamports.
        urgency_multiplier: 1.0 = normal, 2.0 = urgent, 5.0 = critical.
        recent_tip_percentile_50: Median tip from recent bundles.

    Returns:
        Tip amount in lamports.
    """
    dynamic_tip = max(base_tip, int(recent_tip_percentile_50 * urgency_multiplier))
    # Cap at 0.01 SOL to prevent accidents
    return min(dynamic_tip, 10_000_000)
```

## Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Bundle dropped (slot expired)` | Bundle didn't land within 2 slots | Retry with fresh blockhash; consider higher tip |
| `Transaction simulation failed` | A tx in the bundle would fail on-chain | Simulate each tx individually to find the failing one |
| `Bundle already processed` | Duplicate bundle ID | Expected on retry; check status instead |
| `Rate limited` | Too many requests to block engine | Back off; rotate between block engine endpoints |
| `Invalid transaction` | Malformed or unsigned transaction | Verify all txs are signed and base58-encoded |
| `Blockhash not found` | Stale blockhash | Use `getLatestBlockhash` with `finalized` commitment |

## Landing Rate Optimization

Strategies to maximize bundle landing probability:

1. **Multi-region submission**: Send the same bundle to multiple block engines simultaneously. The first to reach the current leader wins.

2. **Fresh blockhash**: Use `getLatestBlockhash` with `confirmed` commitment immediately before building. Stale blockhashes are the #1 cause of dropped bundles.

3. **Retry with backoff**: If a bundle doesn't land within 2-3 seconds, rebuild with a fresh blockhash and resubmit. Do NOT resubmit with the same blockhash.

4. **Adequate tipping**: Under-tipped bundles are deprioritized. Monitor the network's tip distribution and tip at or above the 50th percentile for your urgency level.

5. **Minimal bundle size**: Fewer transactions = less simulation time = higher landing rate. Use single-transaction bundles when possible.

```python
async def submit_with_retry(
    bundle_txs: list[str],
    endpoints: list[str],
    max_retries: int = 3,
) -> str | None:
    """Submit bundle to multiple endpoints with retry logic.

    Returns bundle_id if submitted, None if all retries exhausted.
    """
    for attempt in range(max_retries):
        # Submit to all endpoints in parallel
        async with httpx.AsyncClient() as client:
            tasks = [
                client.post(
                    f"{ep}/api/v1/bundles",
                    json={
                        "jsonrpc": "2.0", "id": 1,
                        "method": "sendBundle",
                        "params": [bundle_txs],
                    },
                    timeout=5.0,
                )
                for ep in endpoints
            ]
            # Process first successful response
            for resp in asyncio.as_completed(tasks):
                result = (await resp).json()
                if "result" in result:
                    return result["result"]

        # Wait before retry with fresh blockhash
        await asyncio.sleep(0.5 * (attempt + 1))
    return None
```

## Safety Checklist (Execution)

Before submitting any bundle with real funds:

- [ ] Simulated all transactions individually via `simulateTransaction`
- [ ] Verified tip amount is reasonable (not accidentally SOL instead of lamports)
- [ ] Confirmed blockhash is fresh (< 60 seconds old)
- [ ] Verified all transactions are properly signed
- [ ] Checked wallet balance covers all transaction costs + tip
- [ ] Tested with devnet or --demo mode first
- [ ] Set maximum tip cap to prevent accidental overpayment

## Files

### References
- `references/bundle_api.md` — Complete JSON-RPC API reference with request/response schemas and error codes
- `references/tip_strategies.md` — Tip calculation strategies, dynamic tipping, cost optimization
- `references/best_practices.md` — Bundle construction patterns, landing rate optimization, common pitfalls

### Scripts
- `scripts/build_bundle.py` — Bundle construction with tip instruction; `--demo` mode builds but does not submit
- `scripts/check_bundle_status.py` — Bundle status checking and tip account fetching; `--demo` mode uses mock responses
