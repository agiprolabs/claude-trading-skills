---
name: solana-rpc
description: Direct Solana blockchain interaction via JSON-RPC — account lookups, token balances, transaction submission, and program queries
---

# Solana RPC — Direct Blockchain Interaction

The Solana JSON-RPC API provides direct read/write access to the blockchain. Use it for account state queries, token balance lookups, transaction building and submission, and program account enumeration. This is the low-level foundation when higher-level APIs (Birdeye, Helius, SolanaTracker) don't have the data you need.

## Quick Start

```python
import httpx

RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

def rpc_call(method: str, params: list = None) -> dict:
    resp = httpx.post(RPC, json={
        "jsonrpc": "2.0", "id": 1,
        "method": method, "params": params or [],
    }, timeout=30.0)
    return resp.json()

# Get SOL balance
result = rpc_call("getBalance", ["WALLET_PUBKEY"])
sol_balance = result["result"]["value"] / 1e9

# Get latest blockhash
result = rpc_call("getLatestBlockhash")
blockhash = result["result"]["value"]["blockhash"]
```

## RPC Providers

| Provider | Free Tier | Paid | Notes |
|----------|-----------|------|-------|
| Helius | 50K credits/day | $49+/mo | Enhanced RPCs, DAS API |
| QuickNode | Limited | $49+/mo | Multi-chain, WebSocket |
| Triton | No free tier | ~$300+/mo | Yellowstone gRPC bundled |
| Shyft | Limited | $49+/mo | Yellowstone gRPC bundled |
| Alchemy | 300M CU/mo | Scaling | Good free tier |
| Public (mainnet-beta) | Free | — | Rate limited, unreliable |

**Recommendation**: Use Helius or QuickNode for development. Never use public RPC for production trading.

## Core Read Methods

### Account & Balance

```python
# SOL balance (in lamports, divide by 1e9 for SOL)
getBalance(pubkey, {commitment: "confirmed"})

# Full account info (data, owner, lamports, executable)
getAccountInfo(pubkey, {encoding: "jsonParsed"})

# Multiple accounts in one call
getMultipleAccounts([pubkey1, pubkey2], {encoding: "jsonParsed"})
```

### Token Accounts

```python
# All SPL token accounts owned by a wallet
getTokenAccountsByOwner(wallet_pubkey, {
    "programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
}, {"encoding": "jsonParsed"})

# Token balance for a specific token account
getTokenAccountBalance(token_account_pubkey)

# Largest token accounts (top holders)
getTokenLargestAccounts(mint_pubkey)

# Total supply of a token
getTokenSupply(mint_pubkey)
```

### Transaction Data

```python
# Get parsed transaction by signature
getTransaction(signature, {
    "encoding": "jsonParsed",
    "maxSupportedTransactionVersion": 0,
})

# Recent transaction signatures for an address
getSignaturesForAddress(pubkey, {
    "limit": 20,
    "before": "optional_signature",  # pagination cursor
})

# Transaction status
getSignatureStatuses([sig1, sig2])
```

### Block & Slot

```python
# Current slot
getSlot({commitment: "confirmed"})

# Block data
getBlock(slot, {
    "encoding": "jsonParsed",
    "transactionDetails": "full",
    "maxSupportedTransactionVersion": 0,
})

# Latest blockhash (needed for tx building)
getLatestBlockhash({commitment: "confirmed"})

# Slot leader schedule
getLeaderSchedule()
```

### Program Accounts

```python
# All accounts owned by a program (with filters)
getProgramAccounts(program_pubkey, {
    "encoding": "jsonParsed",
    "filters": [
        {"dataSize": 165},  # Filter by account data size
        {"memcmp": {         # Filter by data content
            "offset": 32,
            "bytes": "base58_encoded_value",
        }},
    ],
})
```

**Warning**: `getProgramAccounts` without filters can return millions of results and timeout. Always use `dataSize` and/or `memcmp` filters.

### Priority Fees

```python
# Recent priority fee estimates
getRecentPrioritizationFees([account_pubkey])
# Returns array of { slot, prioritizationFee } for recent slots

# Minimum rent for account
getMinimumBalanceForRentExemption(data_length)
```

## Write Methods

### Send Transaction

```python
# Send a signed, serialized transaction
sendTransaction(base64_tx, {
    "encoding": "base64",
    "skipPreflight": False,
    "preflightCommitment": "confirmed",
    "maxRetries": 3,
})

# Simulate before sending
simulateTransaction(base64_tx, {
    "encoding": "base64",
    "sigVerify": False,
    "commitment": "confirmed",
})
```

### Transaction Confirmation

```python
import time

def confirm_transaction(rpc_url: str, signature: str, timeout: float = 30.0) -> bool:
    """Poll for transaction confirmation."""
    start = time.time()
    while time.time() - start < timeout:
        result = rpc_call("getSignatureStatuses", [[signature]])
        statuses = result.get("result", {}).get("value", [None])
        if statuses[0] is not None:
            status = statuses[0]
            if status.get("err"):
                return False
            if status.get("confirmationStatus") in ("confirmed", "finalized"):
                return True
        time.sleep(0.5)
    return False
```

## Commitment Levels

| Level | Description | Use When |
|-------|-------------|----------|
| `processed` | Single node confirmation | Speed over safety |
| `confirmed` | Supermajority (2/3+) | **Default for trading** |
| `finalized` | Maximum supermajority + 31 slots | Critical operations |

Always specify commitment explicitly. Default varies by provider.

## Common Patterns

### Get All Token Holdings for a Wallet

```python
def get_wallet_tokens(wallet: str) -> list[dict]:
    """Get all SPL token holdings with metadata."""
    result = rpc_call("getTokenAccountsByOwner", [
        wallet,
        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
        {"encoding": "jsonParsed"},
    ])
    tokens = []
    for acct in result["result"]["value"]:
        info = acct["account"]["data"]["parsed"]["info"]
        tokens.append({
            "mint": info["mint"],
            "amount": int(info["tokenAmount"]["amount"]),
            "decimals": info["tokenAmount"]["decimals"],
            "ui_amount": info["tokenAmount"]["uiAmount"],
        })
    return [t for t in tokens if t["amount"] > 0]
```

### Get Top Holders of a Token

```python
def get_top_holders(mint: str) -> list[dict]:
    """Get the 20 largest holders of a token."""
    result = rpc_call("getTokenLargestAccounts", [mint])
    supply_result = rpc_call("getTokenSupply", [mint])
    total_supply = int(supply_result["result"]["value"]["amount"])

    holders = []
    for acct in result["result"]["value"]:
        amount = int(acct["amount"])
        holders.append({
            "address": acct["address"],
            "amount": amount,
            "decimals": acct["decimals"],
            "ui_amount": acct["uiAmount"],
            "percentage": amount / total_supply * 100 if total_supply > 0 else 0,
        })
    return holders
```

### Batch RPC Calls

```python
def rpc_batch(calls: list[tuple[str, list]]) -> list[dict]:
    """Execute multiple RPC calls in a single HTTP request."""
    payload = [
        {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
        for i, (method, params) in enumerate(calls)
    ]
    resp = httpx.post(RPC, json=payload, timeout=30.0)
    results = resp.json()
    results.sort(key=lambda r: r["id"])
    return [r.get("result") for r in results]
```

## Key Program IDs

| Program | ID |
|---------|-----|
| System | `11111111111111111111111111111111` |
| SPL Token | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` |
| Token-2022 | `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` |
| Associated Token | `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL` |
| Raydium AMM | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` |
| Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` |
| Orca Whirlpool | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` |
| Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` |
| PumpFun | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` |
| Jupiter v6 | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` |
| Compute Budget | `ComputeBudget111111111111111111111111111111` |

## When to Use Direct RPC vs Higher-Level APIs

| Need | Use |
|------|-----|
| Token balance check | **Direct RPC** (`getTokenAccountsByOwner`) |
| Top 20 holders | **Direct RPC** (`getTokenLargestAccounts`) |
| Historical OHLCV | Birdeye or SolanaTracker |
| Parsed transaction history | Helius Enhanced Transactions |
| Token metadata (name, image) | Helius DAS API |
| Real-time streaming | Yellowstone gRPC |
| Wallet PnL tracking | SolanaTracker |
| Token risk scoring | SolanaTracker |
| Cross-chain data | DexScreener or CoinGecko |

## Files

### References
- `references/methods.md` — Complete RPC method reference with parameters and response schemas
- `references/error_handling.md` — Error codes, rate limits, timeout handling, retry strategies
- `references/providers.md` — RPC provider comparison with pricing and features

### Scripts
- `scripts/wallet_scanner.py` — Scan wallet for all token holdings with balances
- `scripts/token_holders.py` — Get top holders and concentration metrics for any token
