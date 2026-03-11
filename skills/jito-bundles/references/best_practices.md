# Jito Bundles — Best Practices

## Bundle Construction Patterns

### Single-Transaction Bundle (Most Common)

For a simple protected swap, put everything in one transaction:

```
Transaction 1:
  Instruction 1: Compute budget (set compute units)
  Instruction 2: Compute budget (set priority fee — optional alongside tip)
  Instruction 3: Swap instruction (e.g., Jupiter route)
  Instruction 4: Tip transfer (LAST instruction)
```

**Advantages:** Simplest to build, fastest to simulate, highest landing rate.

### Multi-Transaction Bundle

For operations requiring atomicity across multiple transactions:

```
Transaction 1: Setup (create accounts, approve delegations)
Transaction 2: Execute (the core operation)
Transaction 3: Cleanup + Tip (close accounts, collect rent, tip as last ix)
```

**Rules:**
- Tip goes in the LAST instruction of the LAST transaction
- Each transaction must be independently signed
- All transactions share the same recent blockhash
- If ANY transaction fails simulation, the entire bundle is dropped
- Transactions execute in order: Tx1 then Tx2 then Tx3

### Arbitrage Bundle Pattern

```
Transaction 1: Buy on DEX A
Transaction 2: Sell on DEX B + Tip
```

The atomicity guarantees you never get stuck with inventory — if the sell fails, the buy is also reverted.

## Blockhash Management

The blockhash is the single most critical factor for bundle landing. Stale blockhashes are the #1 cause of dropped bundles.

**Best practices:**
1. Fetch `getLatestBlockhash` with `confirmed` commitment immediately before building
2. A blockhash is valid for approximately 60-90 seconds (150 slots)
3. For retries, ALWAYS fetch a new blockhash — never resubmit with the old one
4. Do not cache blockhashes for more than a few seconds

```python
import httpx
import time

class BlockhashManager:
    """Manage blockhash freshness for bundle construction."""

    def __init__(self, rpc_url: str, max_age_seconds: float = 5.0):
        self.rpc_url = rpc_url
        self.max_age = max_age_seconds
        self._blockhash: str | None = None
        self._fetched_at: float = 0.0

    def get_fresh_blockhash(self) -> str:
        """Get a blockhash, refreshing if stale."""
        if (
            self._blockhash is None
            or (time.time() - self._fetched_at) > self.max_age
        ):
            resp = httpx.post(self.rpc_url, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "confirmed"}],
            })
            data = resp.json()
            self._blockhash = data["result"]["value"]["blockhash"]
            self._fetched_at = time.time()
        return self._blockhash
```

## Landing Rate Optimization

### Multi-Region Submission

Submit the same bundle to all block engine endpoints simultaneously. The bundle reaching the current leader first wins.

```python
JITO_ENDPOINTS = [
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
    "https://amsterdam.block-engine.jito.wtf/api/v1/bundles",
    "https://frankfurt.block-engine.jito.wtf/api/v1/bundles",
    "https://tokyo.block-engine.jito.wtf/api/v1/bundles",
]

async def multi_region_submit(
    bundle_txs: list[str],
    endpoints: list[str] = JITO_ENDPOINTS,
) -> list[dict]:
    """Submit bundle to all endpoints in parallel."""
    import asyncio
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "sendBundle",
        "params": [bundle_txs],
    }
    async with httpx.AsyncClient(timeout=5.0) as client:
        tasks = [client.post(ep, json=payload) for ep in endpoints]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        r.json() if not isinstance(r, Exception) else {"error": str(r)}
        for r in results
    ]
```

### Retry Strategy

```python
import asyncio

async def submit_with_landing_check(
    build_bundle_fn,  # Callable that builds fresh bundle
    max_attempts: int = 3,
    poll_interval: float = 0.5,
    poll_timeout: float = 3.0,
) -> dict:
    """Submit bundle, poll for landing, retry if needed."""
    for attempt in range(max_attempts):
        # Build fresh bundle (fresh blockhash each time)
        bundle_txs = build_bundle_fn()
        bundle_id = await submit_to_endpoints(bundle_txs)

        if bundle_id is None:
            continue

        # Poll for landing
        landed = await poll_bundle_status(
            bundle_id, poll_interval, poll_timeout
        )
        if landed:
            return {"status": "landed", "bundle_id": bundle_id,
                    "attempt": attempt + 1}

    return {"status": "failed", "attempts": max_attempts}
```

### Compute Budget Optimization

Set compute units accurately to reduce simulation time:

```python
from solders.compute_budget import set_compute_unit_limit

# Profile your transaction's actual compute usage, then add 10-20% buffer
compute_ix = set_compute_unit_limit(200_000)  # Adjust based on profiling
```

Over-allocating compute units doesn't cost more in fees, but accurate limits help validators simulate bundles faster.

## Common Pitfalls

### 1. Tip in Wrong Position

The tip MUST be the last instruction of the last transaction. Placing it elsewhere causes bundle rejection.

```python
# WRONG — tip is not last
instructions = [tip_ix, swap_ix]

# CORRECT — tip is last
instructions = [swap_ix, tip_ix]
```

### 2. Unsigned Transactions

Every transaction in the bundle must be fully signed before base58 encoding. Partially signed transactions cause immediate rejection.

### 3. Inconsistent Blockhash

All transactions in a multi-tx bundle should use the same recent blockhash. Mixing blockhashes from different fetches can cause intermittent failures.

### 4. Transaction Too Large

Solana transactions have a 1232-byte limit. Adding a tip instruction uses ~52 bytes. If your swap instruction is near the limit, the tip may push it over. Solutions:
- Use versioned transactions with address lookup tables
- Split into a multi-transaction bundle

### 5. Simulating the Bundle as Individual Transactions

When debugging, simulate each transaction individually. But remember that in a bundle, Tx2 sees the state changes from Tx1. If Tx2 depends on Tx1's output (e.g., Tx1 creates an account that Tx2 uses), simulating Tx2 alone will fail.

### 6. Not Handling Partial Information

`getBundleStatuses` may return `null` for a bundle ID if:
- The bundle hasn't been processed yet (check inflight status)
- The bundle expired (rebuild and retry)
- The bundle ID is wrong

Always check for `null` entries in the response.

## When NOT to Use Bundles

1. **Simple SOL transfers**: Priority fees are cheaper and sufficient
2. **Low-value swaps** (< 0.1 SOL): MEV risk is negligible; tip costs more than protection saves
3. **Devnet/testnet**: Jito bundles only work on mainnet
4. **When you need finality guarantees**: Bundles land or drop — they don't provide faster finality than normal transactions

## Debugging Bundles

### Step-by-step debugging workflow:

1. **Simulate each transaction individually** via `simulateTransaction` on your RPC
2. **Check for program errors** in simulation logs
3. **Verify all accounts** are correct and have sufficient balances
4. **Check blockhash freshness** — if the blockhash is > 60s old, refresh
5. **Verify tip account** is in the current `getTipAccounts` list
6. **Check base58 encoding** — ensure transactions are properly serialized

### Logging Best Practices

Log these fields for every bundle submission:
- Bundle ID (from sendBundle response)
- Timestamp of submission
- Tip amount (lamports)
- Tip account used
- Blockhash used
- Number of transactions
- Block engine endpoint(s) submitted to
- Landing status (poll after 2-3 seconds)

```python
import logging

logger = logging.getLogger("jito-bundles")

def log_bundle_submission(
    bundle_id: str,
    tip_lamports: int,
    tip_account: str,
    blockhash: str,
    num_txs: int,
    endpoints: list[str],
) -> None:
    logger.info(
        "Bundle submitted | id=%s tip=%d tip_acct=%s blockhash=%s "
        "txs=%d endpoints=%s",
        bundle_id, tip_lamports, tip_account[:8] + "...",
        blockhash[:8] + "...", num_txs, len(endpoints),
    )
```
