# DEX Execution Safety Checklist

## Pre-Execution Checks

Run all checks before requesting user confirmation. Block execution if any critical check fails.

### 1. Token Validation (Critical)

```python
def validate_token(mint: str, expected_symbol: str) -> bool:
    """Verify mint address matches expected token."""
    resp = httpx.get(f"https://quote-api.jup.ag/v6/tokens")
    tokens = {t["address"]: t for t in resp.json()}
    if mint not in tokens:
        print(f"WARNING: {mint} not in Jupiter token list")
        return False
    actual = tokens[mint]["symbol"]
    if actual != expected_symbol:
        print(f"MISMATCH: expected {expected_symbol}, got {actual}")
        return False
    return True
```

- Verify mint address is correct (copy-paste errors are common)
- Cross-reference symbol with known token list
- Watch for fake tokens that mimic real token names

### 2. Liquidity Check (Critical)

- Query pool depth before quoting
- Minimum liquidity threshold: trade size should be < 2% of total pool TVL
- For tokens with < $10K liquidity, warn the user explicitly
- See the `liquidity-analysis` skill for detailed pool assessment

### 3. Price Impact Assessment (Critical)

| Impact | Action |
|---|---|
| < 1% | Proceed normally |
| 1-2% | Show warning, proceed if user confirms |
| 2-5% | Strong warning — suggest smaller trade or limit order |
| 5-10% | Block by default — require explicit override |
| > 10% | Block — almost certainly a mistake or scam token |

```python
impact = float(quote["priceImpactPct"])
if impact > 10.0:
    print("BLOCKED: Price impact exceeds 10%. This is likely an error.")
    return False
elif impact > 5.0:
    print(f"WARNING: {impact:.2f}% price impact. Requires explicit override.")
    return confirm_with_user("Proceed despite high impact?")
elif impact > 2.0:
    print(f"CAUTION: {impact:.2f}% price impact. Consider reducing trade size.")
```

### 4. Slippage Validation (Critical)

- Never accept slippage >= 50% (5000 bps) — almost always a mistake or exploit
- Warn if slippage > 10% (1000 bps) for non-meme tokens
- For meme tokens, cap at 30% (3000 bps) with explicit user acknowledgment

```python
MAX_SLIPPAGE_BPS = 5000  # absolute max, never exceed

def validate_slippage(slippage_bps: int, is_meme: bool = False) -> bool:
    if slippage_bps >= MAX_SLIPPAGE_BPS:
        print("BLOCKED: Slippage >= 50% is never acceptable")
        return False
    if not is_meme and slippage_bps > 1000:
        print(f"WARNING: {slippage_bps/100:.1f}% slippage is high for this token")
    return True
```

### 5. Balance Verification (Critical)

```python
def check_balance(rpc_url: str, pubkey: str, input_mint: str,
                  amount: int, is_sol: bool) -> bool:
    """Verify sufficient balance for trade + fees."""
    SOL_RESERVE = 50_000_000  # 0.05 SOL for rent + fees

    if is_sol:
        # Need amount + reserve for fees
        sol_balance = get_sol_balance(rpc_url, pubkey)
        required = amount + SOL_RESERVE
        if sol_balance < required:
            print(f"Insufficient SOL: have {sol_balance}, need {required}")
            return False
    else:
        # Need token amount + SOL for fees
        token_balance = get_token_balance(rpc_url, pubkey, input_mint)
        sol_balance = get_sol_balance(rpc_url, pubkey)
        if token_balance < amount:
            print(f"Insufficient token balance: have {token_balance}, need {amount}")
            return False
        if sol_balance < SOL_RESERVE:
            print(f"Insufficient SOL for fees: have {sol_balance}, need {SOL_RESERVE}")
            return False
    return True
```

### 6. Quote Freshness

- Quotes are valid for approximately 30 seconds
- If more than 30 seconds have elapsed since the quote, fetch a new one
- In volatile markets, re-quote even more frequently (10-15 seconds)

### 7. User Confirmation (Critical)

Display all of the following before asking for confirmation:

```
╔══════════════════════════════════════╗
║         SWAP CONFIRMATION            ║
╠══════════════════════════════════════╣
║  Sell:     1.000 SOL                 ║
║  Buy:      ~142.50 USDC             ║
║  Min recv: 141.79 USDC              ║
║  Impact:   0.01%                     ║
║  Slippage: 0.5%                      ║
║  Route:    SOL → Raydium → USDC     ║
║  Fee:      ~0.00005 SOL             ║
╠══════════════════════════════════════╣
║  Proceed? Type YES to confirm        ║
╚══════════════════════════════════════╝
```

## During Execution

### 8. Simulate Before Sending

- Always call `simulateTransaction` before `sendTransaction`
- Check `result.value.err` — if not null, do not proceed
- Parse simulation logs for warnings
- Note compute units consumed for fee estimation

### 9. Monitor Confirmation

- Poll `getSignatureStatuses` every 2 seconds
- Set a timeout of 60 seconds maximum
- If timeout: do NOT assume failure — the transaction may still land
- Check the explorer before retrying to avoid double-execution

### 10. Handle Timeout Gracefully

```python
def handle_timeout(rpc_url: str, signature: str) -> str:
    """Determine transaction fate after timeout."""
    # Check one more time with history search
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "getSignatureStatuses",
        "params": [[signature], {"searchTransactionHistory": True}],
    }
    resp = httpx.post(rpc_url, json=payload)
    status = resp.json()["result"]["value"][0]

    if status is None:
        return "dropped"  # Transaction was never processed — safe to retry
    elif status.get("err"):
        return "failed"   # Transaction failed on-chain — safe to retry
    else:
        return "pending"  # Still processing — DO NOT retry yet
```

## Post-Execution

### 11. Verify Balance Change

After confirmation, verify the expected token was received:

```python
def verify_execution(rpc_url: str, pubkey: str, output_mint: str,
                     pre_balance: int, expected_min: int) -> dict:
    """Verify swap executed correctly."""
    post_balance = get_token_balance(rpc_url, pubkey, output_mint)
    received = post_balance - pre_balance

    return {
        "received": received,
        "expected_min": expected_min,
        "within_slippage": received >= expected_min,
        "execution_quality": received / expected_min if expected_min > 0 else 0,
    }
```

### 12. Log Transaction

Record for analysis (never log private keys):

```python
execution_log = {
    "timestamp": datetime.utcnow().isoformat(),
    "signature": sig,
    "input_mint": input_mint,
    "output_mint": output_mint,
    "input_amount": in_amount,
    "quoted_output": quoted_output,
    "actual_output": actual_output,
    "price_impact_pct": price_impact,
    "slippage_bps": slippage_bps,
    "priority_fee_lamports": priority_fee,
    "route": route_labels,
}
```

### 13. Calculate Execution Quality

```python
quoted_price = float(quoted_output) / float(in_amount)
actual_price = float(actual_output) / float(in_amount)
execution_cost_bps = (1 - actual_price / quoted_price) * 10000
print(f"Execution cost: {execution_cost_bps:.1f} bps vs quoted price")
```

## What NOT to Do

1. **Never auto-execute** — always require explicit user confirmation
2. **Never hardcode private keys** — environment variables only
3. **Never log private keys** — not to console, files, or remote services
4. **Never ignore simulation errors** — if simulation fails, do not send
5. **Never set slippage to 100%** — this is a common attack vector
6. **Never retry without checking** — verify the first tx didn't land before retrying
7. **Never skip balance checks** — insufficient balance errors waste fees
8. **Never trust token symbols alone** — always verify by mint address
9. **Never execute on behalf of user** without showing full trade details first
10. **Never assume a timeout means failure** — always check transaction status
