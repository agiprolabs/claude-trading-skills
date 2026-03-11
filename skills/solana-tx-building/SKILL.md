---
name: solana-tx-building
description: Solana transaction construction including instruction building, account resolution, compute budget, priority fees, and versioned transactions
---

# Solana Transaction Building

This skill covers how to construct, simulate, and inspect Solana transactions programmatically. It addresses the full anatomy of a Solana transaction — from raw instruction encoding to versioned transaction formats, compute budget management, priority fees, and address lookup tables.

**Safety**: This skill is for transaction *construction* and *analysis* only. Scripts in this skill NEVER sign or submit real transactions. Always simulate before sending. Never auto-sign.

## Transaction Anatomy

A Solana transaction consists of:

1. **Signatures**: One or more Ed25519 signatures (64 bytes each)
2. **Message**: The serializable payload containing:
   - **Header**: Counts of required signers, read-only signers, read-only non-signers
   - **Account keys**: Array of all pubkeys referenced by instructions
   - **Recent blockhash**: 32-byte hash for replay protection (expires ~60-90 seconds)
   - **Instructions**: Array of program calls

### Transaction Size Limit

The hard limit is **1232 bytes** for the entire serialized transaction. This constrains how many instructions and accounts you can include. Strategies to stay within the limit:

- Use versioned transactions with Address Lookup Tables (ALTs)
- Minimize the number of accounts per instruction
- Combine related operations into single instructions where supported
- Split complex operations across multiple transactions

### Instruction Format

Each instruction contains three fields:

```
Instruction {
    program_id_index: u8,      // Index into the account keys array
    accounts: [u8],            // Indices into account keys array
    data: [u8],                // Opaque byte array interpreted by the program
}
```

### Account Meta

Every account referenced in an instruction has metadata:

```
AccountMeta {
    pubkey: Pubkey,            // 32-byte public key
    is_signer: bool,           // Must sign the transaction
    is_writable: bool,         // Will be written to by this instruction
}
```

The four combinations determine the account's role:

| is_signer | is_writable | Role |
|-----------|-------------|------|
| true | true | Fee payer, token owner performing transfer |
| true | false | Multisig co-signer, read-only authority |
| false | true | Destination account, PDA being written |
| false | false | Program ID, sysvar, clock |

## Legacy vs Versioned Transactions

### Legacy Transactions

The original format. All accounts must be listed in the account keys array. With the 1232-byte limit, you can fit roughly 20-35 accounts depending on instruction data size.

### Versioned Transactions (v0)

Introduced to support **Address Lookup Tables (ALTs)**. A v0 transaction includes:

- A version prefix byte (`0x80` for v0)
- The same message structure as legacy
- An additional `address_table_lookups` array

ALTs let you reference accounts by a compact index into an on-chain table rather than including the full 32-byte pubkey. This dramatically increases the number of accounts a transaction can reference.

```
AddressTableLookup {
    account_key: Pubkey,           // The ALT account address
    writable_indexes: [u8],        // Indices for writable accounts
    readonly_indexes: [u8],        // Indices for read-only accounts
}
```

**When to use v0**: Any transaction referencing more than ~20 accounts, Jupiter swaps with multi-hop routes, complex DeFi interactions.

## Compute Budget

Every transaction has a compute budget that determines how many compute units (CUs) it can consume and what priority fee to pay.

### Compute Budget Instructions

Two key instructions from the Compute Budget Program (`ComputeBudget111111111111111111111111111111`):

**1. Set Compute Unit Limit**
```
Instruction data: [0x02, <units as u32 LE>]
```
Sets the maximum CUs this transaction can consume. Default is 200,000 per instruction (max 1,400,000 per transaction). Setting this lower than needed causes the transaction to fail. Setting it higher wastes budget but does not cost more (you only pay for requested, not consumed).

**2. Set Compute Unit Price**
```
Instruction data: [0x03, <micro_lamports as u64 LE>]
```
Sets the price per CU in micro-lamports. This is the priority fee mechanism. The total priority fee is:

```
priority_fee = compute_unit_limit * compute_unit_price / 1_000_000
```

### Priority Fee Estimation

To estimate an appropriate priority fee:

1. Call `getRecentPrioritizationFees` RPC method with the accounts your transaction touches
2. Look at the median or 75th percentile fee from recent slots
3. During congestion, fees spike — monitor and adjust dynamically

```python
import httpx

def get_priority_fees(rpc_url: str, accounts: list[str]) -> list[dict]:
    """Fetch recent prioritization fees for given accounts."""
    resp = httpx.post(rpc_url, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getRecentPrioritizationFees",
        "params": [accounts]
    })
    return resp.json()["result"]
```

## Common Transaction Patterns

### 1. SOL Transfer

The simplest transaction: a System Program transfer.

```python
# System Program transfer instruction data layout:
# [2, 0, 0, 0]  (u32 LE = instruction index 2 = Transfer)
# + amount as u64 LE (lamports)
import struct

def build_sol_transfer_data(lamports: int) -> bytes:
    """Build instruction data for a SOL transfer."""
    return struct.pack("<I", 2) + struct.pack("<Q", lamports)
```

Accounts required:
1. Sender (signer, writable)
2. Recipient (writable)

### 2. SPL Token Transfer

Transferring SPL tokens requires the Token Program.

```python
# Token Program transfer instruction:
# [3]  (instruction index 3 = Transfer)
# + amount as u64 LE
def build_token_transfer_data(amount: int) -> bytes:
    """Build instruction data for an SPL token transfer."""
    return bytes([3]) + struct.pack("<Q", amount)
```

Accounts required:
1. Source token account (writable)
2. Destination token account (writable)
3. Owner/delegate (signer)

### 3. Create Associated Token Account (ATA)

Before transferring tokens, the recipient must have an Associated Token Account.

```python
# ATA Program: instruction index 0 = Create
# No instruction data needed (empty bytes)
ATA_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
```

Accounts required (in order):
1. Payer (signer, writable) — pays rent
2. Associated token account (writable) — the ATA to create
3. Wallet address — owner of the new ATA
4. Token mint
5. System Program
6. Token Program

### 4. Jupiter Swap

Jupiter provides a `/swap-instructions` endpoint that returns pre-built instructions. See the `jupiter-api` skill for full details.

General flow:
1. Get a quote from `/quote`
2. Get swap instructions from `/swap-instructions`
3. Build transaction with setup instructions + swap instruction + cleanup instructions
4. Add compute budget instructions
5. Simulate, then sign and send

## Simulation

Always simulate before sending. Use the `simulateTransaction` RPC method:

```python
def simulate_transaction(rpc_url: str, tx_base64: str) -> dict:
    """Simulate a transaction without submitting it.

    Args:
        rpc_url: Solana RPC endpoint URL.
        tx_base64: Base64-encoded serialized transaction.

    Returns:
        Simulation result with logs and compute units consumed.
    """
    resp = httpx.post(rpc_url, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": [
            tx_base64,
            {"encoding": "base64", "replaceRecentBlockhash": True}
        ]
    })
    result = resp.json()["result"]
    if result["value"]["err"]:
        print(f"Simulation failed: {result['value']['err']}")
        for log in result["value"].get("logs", []):
            print(f"  {log}")
    else:
        cu = result["value"].get("unitsConsumed", 0)
        print(f"Simulation OK — {cu} compute units consumed")
    return result
```

The `replaceRecentBlockhash: True` flag lets you simulate even if your blockhash has expired, which is useful for testing transaction construction without timing pressure.

## Error Handling

Common transaction errors and their causes:

| Error | Cause | Fix |
|-------|-------|-----|
| `BlockhashNotFound` | Blockhash expired (~60-90s) | Fetch new blockhash and rebuild |
| `InsufficientFunds` | Not enough SOL for fees + transfer | Check balance before building |
| `AccountNotFound` | Token account doesn't exist | Create ATA first |
| `ProgramFailedToComplete` | Exceeded compute budget | Increase compute unit limit |
| `TransactionTooLarge` | Over 1232 bytes | Use ALTs or split into multiple txs |
| `InvalidAccountData` | Wrong account passed to instruction | Verify account derivation |
| `SignatureVerificationFailed` | Missing or wrong signer | Check all `is_signer` accounts signed |

### Retry Strategy

```python
import time

def send_with_retry(
    rpc_url: str,
    build_fn,
    max_retries: int = 3,
    base_delay: float = 0.5
) -> dict:
    """Build and send a transaction with blockhash refresh on expiry.

    Args:
        rpc_url: Solana RPC endpoint.
        build_fn: Callable that takes a blockhash and returns a signed tx.
        max_retries: Maximum retry attempts.
        base_delay: Base delay between retries in seconds.

    Returns:
        Send result from RPC.
    """
    for attempt in range(max_retries):
        blockhash = get_latest_blockhash(rpc_url)
        tx = build_fn(blockhash)
        result = send_transaction(rpc_url, tx)
        if "error" not in result:
            return result
        err = result["error"]
        if "BlockhashNotFound" in str(err):
            time.sleep(base_delay * (attempt + 1))
            continue
        raise RuntimeError(f"Transaction failed: {err}")
    raise RuntimeError("Max retries exceeded")
```

## Transaction Decoding

To decode an existing transaction from the chain:

```python
def decode_transaction(rpc_url: str, signature: str) -> dict:
    """Fetch and return a parsed transaction.

    Args:
        rpc_url: Solana RPC endpoint.
        signature: Transaction signature (base58).

    Returns:
        Parsed transaction data.
    """
    resp = httpx.post(rpc_url, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ]
    })
    return resp.json()["result"]
```

## Integration with Other Skills

- **`solana-rpc`**: Provides the RPC connection layer for submitting and querying transactions
- **`jupiter-api`**: Supplies swap instructions that this skill assembles into transactions
- **`dex-execution`**: Orchestrates the full execution flow using transactions built by this skill
- **`mev-analysis`**: Evaluates MEV risk of constructed transactions before submission
- **`helius-api`**: Enhanced transaction parsing and webhook-based confirmation tracking

## Safety Checklist

Before submitting any transaction to mainnet:

1. **Simulate first** — always call `simulateTransaction` before `sendTransaction`
2. **Verify accounts** — confirm all account addresses are correct (especially for token transfers)
3. **Check balances** — ensure sufficient SOL for fees and any transfers
4. **Review compute budget** — set appropriate CU limit based on simulation
5. **Confirm priority fee** — check current network fees, do not overpay
6. **Never auto-sign** — require explicit user confirmation before signing
7. **Use devnet for testing** — build and test on devnet before mainnet
8. **Log everything** — record transaction signatures, simulation results, and errors

## Files

### References
- `references/transaction_anatomy.md` — Message format, versioned transactions, compute budget, blockhash management
- `references/common_instructions.md` — Instruction layouts for System, Token, ATA, Compute Budget, Memo, and Jupiter programs

### Scripts
- `scripts/build_transfer.py` — Build and simulate a SOL transfer transaction (demo mode, never signs)
- `scripts/decode_transaction.py` — Fetch and decode on-chain transactions with program identification
