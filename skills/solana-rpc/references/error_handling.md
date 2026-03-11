# Solana RPC — Error Handling & Rate Limits

## JSON-RPC Error Codes

| Code | Message | Cause | Action |
|------|---------|-------|--------|
| -32600 | Invalid request | Malformed JSON | Fix request format |
| -32601 | Method not found | Typo in method name | Check method name |
| -32602 | Invalid params | Wrong parameter types | Check param format |
| -32003 | Transaction simulation failed | Tx would fail on-chain | Check simulation logs |
| -32004 | Block not available | Slot was skipped | Try adjacent slot |
| -32005 | Node is behind | Node not synced | Use different node or retry |
| -32007 | Transaction precompile verification failure | Bad signature | Re-sign transaction |
| -32009 | Transaction has already been processed | Duplicate submission | Tx already landed |
| -32010 | Transaction version unsupported | Missing version param | Add `maxSupportedTransactionVersion: 0` |
| -32014 | Slot was skipped | Leader didn't produce block | Normal, try next slot |
| -32015 | No snapshot | Node doesn't have snapshot | Use different node |

## Rate Limits by Provider

| Provider | Requests/sec | Daily Limit | Batch Size |
|----------|-------------|-------------|------------|
| Public mainnet-beta | ~10-40 | Unlimited | 10 |
| Helius Free | ~50 | 50K credits | 100 |
| Helius Paid | ~500+ | By plan | 100 |
| QuickNode | By plan | By plan | 100 |
| Alchemy | ~25 CU/s free | 300M CU/mo | 100 |

## Retry Strategy

```python
import time
import httpx
from typing import Any

def rpc_call_with_retry(
    rpc_url: str,
    method: str,
    params: list,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Make an RPC call with exponential backoff retry.

    Args:
        rpc_url: RPC endpoint URL.
        method: RPC method name.
        params: Method parameters.
        max_retries: Maximum retry attempts.
        timeout: Request timeout in seconds.

    Returns:
        The 'result' field from the response.

    Raises:
        RuntimeError: On persistent failure or RPC error.
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    for attempt in range(max_retries):
        try:
            resp = httpx.post(rpc_url, json=payload, timeout=timeout)

            if resp.status_code == 429:
                wait = 2.0 * (attempt + 1)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                time.sleep(1.0 * (attempt + 1))
                continue

            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                err = data["error"]
                code = err.get("code", 0)

                # Retriable errors
                if code in (-32005, -32014):
                    time.sleep(1.0)
                    continue

                raise RuntimeError(f"RPC error {code}: {err.get('message')}")

            return data.get("result", {})

        except httpx.TimeoutException:
            if attempt < max_retries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise

    raise RuntimeError(f"RPC call {method} failed after {max_retries} retries")
```

## Common Pitfalls

### 1. Versioned transactions require explicit opt-in
```python
# Wrong — will fail on versioned (v0) transactions
rpc_call("getTransaction", [sig])

# Right
rpc_call("getTransaction", [sig, {
    "encoding": "jsonParsed",
    "maxSupportedTransactionVersion": 0,
}])
```

### 2. getProgramAccounts without filters
This can return millions of accounts and timeout or OOM:
```python
# Wrong — returns ALL token accounts
rpc_call("getProgramAccounts", ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"])

# Right — filter by data size and/or memcmp
rpc_call("getProgramAccounts", ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", {
    "filters": [{"dataSize": 165}],
    "encoding": "jsonParsed",
}])
```

### 3. Lamport vs SOL confusion
All RPC values are in lamports (1 SOL = 1,000,000,000 lamports).
All token amounts are in raw units (check decimals).

```python
sol = lamports / 1e9
token_amount = raw_amount / (10 ** decimals)
```

### 4. Commitment level defaults
Different providers may default to different commitment levels. Always specify explicitly:
```python
rpc_call("getBalance", [pubkey, {"commitment": "confirmed"}])
```

### 5. Blockhash expiration
Blockhashes expire after ~60-90 seconds. If building transactions:
- Fetch blockhash right before signing
- Submit immediately after signing
- Monitor `lastValidBlockHeight` to know when to retry

### 6. Null results
Many methods return `null` for accounts/transactions that don't exist:
```python
result = rpc_call("getAccountInfo", [pubkey])
if result["value"] is None:
    print("Account does not exist")
```
