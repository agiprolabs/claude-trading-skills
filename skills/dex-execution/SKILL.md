---
name: dex-execution
description: Solana DEX swap execution via Jupiter aggregator including quoting, transaction building, signing, and confirmation
---

# DEX Execution — Solana Swap Execution via Jupiter

Execute token swaps on Solana through Jupiter, the dominant DEX aggregator routing across Raydium, Orca, Meteora, Phoenix, Lifinity, and 20+ other venues.

## Overview

Jupiter aggregates liquidity across all major Solana DEXes to find optimal swap routes. A single swap may split across multiple pools and hop through intermediate tokens to minimize price impact. The Jupiter v6 API handles route discovery, transaction building, and fee optimization — your code handles quoting, user confirmation, signing, and submission.

**Base URL**: `https://quote-api.jup.ag/v6`

## Execution Pipeline

Every swap follows this seven-step pipeline. Never skip steps 2-3 (display and confirm).

### Step 1 — Get Quote

```python
import httpx

params = {
    "inputMint": "So11111111111111111111111111111111111111112",   # SOL
    "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
    "amount": 1_000_000_000,  # 1 SOL in lamports
    "slippageBps": 50,        # 0.5%
}
resp = httpx.get("https://quote-api.jup.ag/v6/quote", params=params)
quote = resp.json()
```

### Step 2 — Display Quote to User

Always show these fields before proceeding:

| Field | Source |
|---|---|
| Input amount | `quote["inAmount"]` (in token decimals) |
| Output amount | `quote["outAmount"]` |
| Minimum received | `quote["otherAmountThreshold"]` |
| Price impact | `quote["priceImpactPct"]` |
| Route | `quote["routePlan"]` — DEXes used |
| Slippage | The `slippageBps` you requested |

### Step 3 — Require User Confirmation

```
⚠️  SWAP PREVIEW
    Selling:   1.000 SOL
    Buying:    ~142.50 USDC
    Min recv:  141.79 USDC (0.5% slippage)
    Impact:    0.01%
    Route:     Raydium V4 → USDC

    Proceed? [y/N]
```

**NEVER proceed without explicit "yes" from the user.**

### Step 4 — Build Transaction

```python
swap_body = {
    "quoteResponse": quote,
    "userPublicKey": "YourPubkeyBase58...",
    "wrapAndUnwrapSol": True,
    "dynamicComputeUnitLimit": True,
    "prioritizationFeeLamports": "auto",
}
resp = httpx.post("https://quote-api.jup.ag/v6/swap", json=swap_body)
swap_data = resp.json()
swap_tx = swap_data["swapTransaction"]  # base64-encoded transaction
```

### Step 5 — Sign Transaction

```python
import base64
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair

raw_tx = base64.b64decode(swap_tx)
tx = VersionedTransaction.from_bytes(raw_tx)
keypair = Keypair.from_base58_string(os.environ["WALLET_PRIVATE_KEY"])
tx.sign([keypair])
```

### Step 6 — Submit Transaction

```python
rpc_url = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
signed_bytes = bytes(tx)
payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "sendTransaction",
    "params": [
        base64.b64encode(signed_bytes).decode(),
        {"encoding": "base64", "skipPreflight": False,
         "maxRetries": 3, "preflightCommitment": "confirmed"}
    ],
}
resp = httpx.post(rpc_url, json=payload)
sig = resp.json()["result"]
print(f"Submitted: https://solscan.io/tx/{sig}")
```

### Step 7 — Confirm Transaction

```python
import time

for attempt in range(30):
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignatureStatuses",
        "params": [[sig], {"searchTransactionHistory": False}],
    }
    resp = httpx.post(rpc_url, json=payload)
    status = resp.json()["result"]["value"][0]
    if status and status.get("confirmationStatus") in ("confirmed", "finalized"):
        print(f"Confirmed at slot {status['slot']}")
        break
    time.sleep(2)
else:
    print("Transaction not confirmed within 60s — check explorer")
```

## Jupiter API v6 Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/quote` | GET | Get best-price quote with routing |
| `/swap` | POST | Build a swap transaction from a quote |
| `/swap-instructions` | POST | Get individual instructions (advanced) |
| `/price?ids=token1,token2` | GET | Simple price lookup (v2) |
| `/tokens` | GET | List all supported tokens |

See `references/jupiter_api.md` for full parameter and response documentation.

## Key Parameters

### Slippage (`slippageBps`)

| Token Type | Recommended Range | Notes |
|---|---|---|
| SOL, USDC, major tokens | 50-100 (0.5-1%) | Stable liquidity |
| Mid-cap tokens | 100-300 (1-3%) | Variable liquidity |
| PumpFun / meme tokens | 500-2000 (5-20%) | Thin books, high volatility |
| New launches (<1h old) | 1000-3000 (10-30%) | Extreme volatility |

### Dynamic Slippage

Set `dynamicSlippage: true` in the swap request to let Jupiter auto-adjust slippage based on current market conditions. Preferred for most use cases.

### Priority Fees (`prioritizationFeeLamports`)

Priority fees determine transaction ordering within a block.

| Level | microLamports | When to Use |
|---|---|---|
| Low | 10,000-50,000 | Normal conditions |
| Medium | 50,000-200,000 | Moderate congestion |
| High | 200,000-1,000,000 | High congestion / time-sensitive |
| Urgent | 1,000,000-5,000,000 | Meme coin launches, NFT mints |
| Auto | `"auto"` | Jupiter estimates for you |

Use `"auto"` for most cases. For fine-grained control, query Helius `getPriorityFeeEstimate`.

### Other Parameters

- **`onlyDirectRoutes`**: Skip multi-hop routing. Faster but may get worse price.
- **`asLegacyTransaction`**: Use legacy format instead of versioned transactions. Required for some older wallets.
- **`maxAccounts`**: Limit accounts in transaction (default 64). Lower values reduce route options but improve confirmation reliability.
- **`platformFeeBps`**: Integrator fee in basis points. Taken from output amount.
- **`wrapAndUnwrapSol`**: Auto wrap/unwrap SOL ↔ wSOL (default true).
- **`dynamicComputeUnitLimit`**: Auto-set compute budget based on simulation.

## Priority Fee Estimation

```python
# Using Helius getPriorityFeeEstimate
helius_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"
payload = {
    "jsonrpc": "2.0", "id": 1,
    "method": "getPriorityFeeEstimate",
    "params": [{"accountKeys": [input_mint, output_mint],
                "options": {"recommended": True}}],
}
resp = httpx.post(helius_url, json=payload)
fee = resp.json()["result"]["priorityFeeEstimate"]
```

## Transaction Confirmation Strategy

See `references/transaction_lifecycle.md` for the full Solana transaction lifecycle.

1. **Submit** with `skipPreflight: False` to catch obvious errors
2. **Poll** `getSignatureStatuses` every 2 seconds for up to 60 seconds
3. **If not confirmed**: rebuild transaction with fresh blockhash and retry (max 3 attempts)
4. **Blockhash expiry**: transactions expire ~60 seconds after blockhash was fetched
5. **Final check**: verify token balance changed as expected

## Error Handling

| Error | Cause | Recovery |
|---|---|---|
| `"Slippage tolerance exceeded"` | Price moved beyond slippageBps | Increase slippage or retry |
| `"Insufficient funds"` | Not enough input token or SOL for fees | Check balance before quoting |
| `"Transaction expired"` | Blockhash too old | Rebuild with fresh blockhash |
| `"Transaction simulation failed"` | Various — check logs | Parse simulation logs for root cause |
| `"Too many accounts"` | Route uses too many accounts | Set `maxAccounts` lower or use `onlyDirectRoutes` |
| HTTP 429 | Rate limited | Back off and retry with exponential delay |
| HTTP 400 `"No route found"` | No liquidity path exists | Check token mints are correct, try larger slippage |

## Safety Requirements

> **These are non-negotiable requirements for any execution code.**

1. **ALWAYS show quote details** (amounts, price impact, route) before execution
2. **ALWAYS require explicit user confirmation** — never auto-execute
3. **Default to simulation mode** — do not sign or submit unless explicitly enabled
4. **Never store or log private keys** — load from env vars, use immediately, discard
5. **Never use 100% slippage** — this is a common scam/exploit vector
6. **Verify token addresses** — confirm mints match expected tokens before swapping
7. **Check price impact** — warn if >2%, block if >10% unless user overrides
8. **Maintain SOL reserve** — keep 0.05 SOL minimum for rent and future fees

See `references/safety_checklist.md` for the complete pre/during/post execution checklist.

## Integration with Other Skills

| Skill | Integration |
|---|---|
| `slippage-modeling` | Estimate optimal slippageBps based on token liquidity profile |
| `liquidity-analysis` | Verify pool depth supports trade size before quoting |
| `position-sizing` | Calculate trade amount based on risk parameters |
| `risk-management` | Enforce portfolio-level exposure limits before execution |
| `jupiter-api` | Underlying API documentation for Jupiter endpoints |
| `helius-api` | Priority fee estimation and transaction monitoring |

## Files

### References
- `references/jupiter_api.md` — Complete Jupiter v6 API parameter and response reference
- `references/transaction_lifecycle.md` — Solana transaction lifecycle, priority fees, retry strategies
- `references/safety_checklist.md` — Pre/during/post execution verification checklist

### Scripts
- `scripts/get_quote.py` — Fetch and display Jupiter swap quotes with route analysis
- `scripts/simulate_swap.py` — Build and simulate swap transactions without submitting
