# Solana Transaction Lifecycle

## Overview

Every Solana swap follows a strict lifecycle: build, simulate, sign, send, confirm. Understanding each step prevents lost funds and failed transactions.

## 1. Build Transaction

Jupiter's POST /swap returns a base64-encoded versioned transaction. To work with it:

```python
import base64
from solders.transaction import VersionedTransaction

raw_tx = base64.b64decode(swap_response["swapTransaction"])
tx = VersionedTransaction.from_bytes(raw_tx)
```

**Versioned vs Legacy Transactions**:
- Versioned transactions (v0) support address lookup tables, reducing account size
- Legacy transactions have a 35-account hard limit
- Use `asLegacyTransaction: true` only if the signing wallet requires it
- Jupiter defaults to versioned transactions

## 2. Simulate Transaction

Always simulate before signing to catch errors without spending fees.

```python
import base64, httpx

rpc_url = "https://api.mainnet-beta.solana.com"
raw_bytes = bytes(tx)  # unsigned transaction bytes
payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "simulateTransaction",
    "params": [
        base64.b64encode(raw_bytes).decode(),
        {
            "encoding": "base64",
            "commitment": "confirmed",
            "sigVerify": False,
            "replaceRecentBlockhash": True,
        }
    ],
}
resp = httpx.post(rpc_url, json=payload)
result = resp.json()["result"]["value"]

if result["err"]:
    print(f"Simulation failed: {result['err']}")
    print(f"Logs: {result['logs']}")
else:
    print(f"Simulation OK — {result['unitsConsumed']} compute units")
```

Key simulation parameters:
- **`sigVerify: False`**: Skip signature verification (transaction isn't signed yet)
- **`replaceRecentBlockhash: True`**: Use a fresh blockhash so simulation doesn't fail on expiry

## 3. Sign Transaction

```python
from solders.keypair import Keypair

keypair = Keypair.from_base58_string(private_key)
tx.sign([keypair])
```

**Security rules**:
- Load private key from environment variable only
- Never log, print, or persist the private key
- Never sign without user confirmation
- Clear the keypair from memory after signing (Python GC handles this)

## 4. Send Transaction

```python
signed_bytes = bytes(tx)
payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "sendTransaction",
    "params": [
        base64.b64encode(signed_bytes).decode(),
        {
            "encoding": "base64",
            "skipPreflight": False,
            "preflightCommitment": "confirmed",
            "maxRetries": 3,
        }
    ],
}
resp = httpx.post(rpc_url, json=payload)
sig = resp.json()["result"]
```

**`skipPreflight` options**:
- `False` (default): RPC simulates before forwarding. Catches errors early.
- `True`: Skip simulation, send directly. Use only when you already simulated and need speed.

## 5. Confirm Transaction

```python
import time

def confirm_transaction(rpc_url: str, signature: str,
                        timeout: int = 60, interval: int = 2) -> dict:
    """Poll for transaction confirmation."""
    start = time.time()
    while time.time() - start < timeout:
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getSignatureStatuses",
            "params": [[signature], {"searchTransactionHistory": False}],
        }
        resp = httpx.post(rpc_url, json=payload)
        statuses = resp.json()["result"]["value"]
        if statuses[0]:
            status = statuses[0]
            if status.get("err"):
                return {"confirmed": False, "error": status["err"]}
            if status["confirmationStatus"] in ("confirmed", "finalized"):
                return {"confirmed": True, "slot": status["slot"],
                        "status": status["confirmationStatus"]}
        time.sleep(interval)
    return {"confirmed": False, "error": "timeout"}
```

**Commitment levels**:
- **`processed`**: Seen by the leader, not yet voted on (~400ms)
- **`confirmed`**: Voted on by supermajority (~5-10s) — sufficient for most swaps
- **`finalized`**: Rooted, irreversible (~15-30s) — use for high-value transactions

## Priority Fees

Solana uses a fee market based on compute unit price. Higher fees = higher priority in block scheduling.

### How Priority Fees Work

Total fee = `base_fee (5000 lamports)` + `compute_units * compute_unit_price`

```python
# compute_unit_price is in microLamports (1 lamport = 1_000_000 microLamports)
# Example: 100,000 microLamports * 200,000 CU = 20,000 lamports = 0.00002 SOL
```

### Estimating Priority Fees

**Option A — Jupiter auto**:
Set `prioritizationFeeLamports: "auto"` in the /swap request. Jupiter estimates based on recent blocks.

**Option B — Helius API**:
```python
payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "getPriorityFeeEstimate",
    "params": [{
        "accountKeys": [input_mint, output_mint],
        "options": {"recommended": True}
    }],
}
resp = httpx.post(helius_rpc_url, json=payload)
estimate = resp.json()["result"]
# Returns: {"priorityFeeEstimate": 50000}
```

**Option C — Fixed tiers**:

| Tier | microLamports | Typical Cost (200K CU) |
|---|---|---|
| Economy | 10,000 | 0.000002 SOL |
| Standard | 50,000 | 0.00001 SOL |
| Fast | 200,000 | 0.00004 SOL |
| Turbo | 1,000,000 | 0.0002 SOL |
| Emergency | 5,000,000 | 0.001 SOL |

### When to Increase Priority Fees

- Token launches (first minutes): Turbo/Emergency
- High market volatility: Fast/Turbo
- Normal trading: Standard
- Non-urgent rebalancing: Economy

## Blockhash Expiry and Retries

Transactions include a `recentBlockhash` that expires after ~60 seconds (~150 slots).

### Retry Strategy

```
1. Get quote → Build tx → Simulate → Sign → Send
2. Poll for 30 seconds
3. If not confirmed:
   a. Get fresh quote (prices may have changed)
   b. Build new tx with new blockhash
   c. Simulate → Sign → Send
4. Repeat up to 3 total attempts
5. If still not confirmed, abort and alert user
```

Never resubmit a signed transaction with an expired blockhash — it will be rejected.

## Common Failure Modes

| Failure | Cause | Solution |
|---|---|---|
| `BlockhashNotFound` | Blockhash expired | Rebuild transaction with fresh blockhash |
| `InsufficientFundsForRent` | Account needs rent-exempt minimum | Ensure 0.05 SOL reserve |
| `SlippageToleranceExceeded` | Price moved beyond limit | Increase slippage or retry quickly |
| `AccountNotFound` | Token account doesn't exist | Enable `wrapAndUnwrapSol`, check ATAs |
| `ProgramError` | AMM-specific error | Check simulation logs for details |
| Transaction dropped | Leader didn't include it | Resubmit with higher priority fee |

## Verifying Execution

After confirmation, verify the swap executed correctly:

```python
# Check token balance changed
payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "getTokenAccountsByOwner",
    "params": [
        user_pubkey,
        {"mint": output_mint},
        {"encoding": "jsonParsed"}
    ],
}
```

Compare post-swap balance with pre-swap balance to calculate actual execution price.
