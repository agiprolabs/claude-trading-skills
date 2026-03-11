# Solana Transaction Anatomy

## Message Format

A Solana transaction message contains four sections:

### 1. Header (3 bytes)

```
MessageHeader {
    num_required_signatures: u8,          // Total signers required
    num_readonly_signed_accounts: u8,     // Signers that are read-only
    num_readonly_unsigned_accounts: u8,   // Non-signers that are read-only
}
```

The header determines how accounts in the account keys array are categorized:

```
Account keys array layout:
[0..num_required_signatures)                          → writable signers
[num_required_signatures - num_readonly_signed..num_required_signatures)  → read-only signers
[num_required_signatures..len - num_readonly_unsigned) → writable non-signers
[len - num_readonly_unsigned..len)                     → read-only non-signers
```

The first account in the writable signers section is always the **fee payer**.

### 2. Account Keys

A compact array of 32-byte public keys. Every account referenced by any instruction must appear here exactly once. The order matters because instructions reference accounts by index.

Deduplication rules:
- If an account is both writable and read-only across instructions, it is listed as writable
- If an account is both a signer and non-signer across instructions, it is listed as a signer
- The most permissive role wins

### 3. Recent Blockhash

A 32-byte hash that:
- Prevents replay attacks (same transaction cannot be submitted twice)
- Expires after ~60-90 seconds (~150 slots)
- Must be fetched fresh before building each transaction

### 4. Instructions

A compact array of compiled instructions:

```
CompiledInstruction {
    program_id_index: u8,    // Index of the program in account keys
    accounts: [u8],          // Indices of accounts in account keys
    data: [u8],              // Program-specific instruction data
}
```

## Versioned Transactions

### Legacy Format

```
[signatures_length, ...signatures, message_bytes]
```

Where `message_bytes` is:
```
[header(3), account_keys_length, ...account_keys(32 each),
 recent_blockhash(32), instructions_length, ...compiled_instructions]
```

### V0 Format

V0 transactions add a version prefix and address table lookups:

```
[0x80,  // version prefix (0x80 = v0)
 signatures_length, ...signatures,
 message_bytes,
 address_table_lookups_length, ...address_table_lookups]
```

Each address table lookup:
```
AddressTableLookup {
    account_key: Pubkey,           // 32 bytes — the ALT account
    writable_indexes: [u8],        // Compact array of writable indices
    readonly_indexes: [u8],        // Compact array of read-only indices
}
```

### Address Lookup Tables (ALTs)

ALTs are on-chain accounts that store up to 256 public keys. Instead of including a full 32-byte pubkey in the transaction, you reference it with a 1-byte index into the ALT.

**Space savings**: Each ALT reference saves 31 bytes per account (32-byte pubkey replaced by 1-byte index, plus the 32-byte ALT address amortized across lookups).

**Creating an ALT**:
```python
# AddressLookupTable program: AddressLookupTab1e1111111111111111111111111
# Instruction 0: CreateLookupTable
# Instruction 1: ExtendLookupTable (add addresses)
# Instruction 2: FreezeLookupTable
# Instruction 3: DeactivateLookupTable
# Instruction 4: CloseLookupTable
```

**Lookup flow**:
1. Transaction includes ALT account key + indices
2. Runtime loads the ALT account data
3. Resolves each index to the stored pubkey
4. Passes resolved accounts to the program

**Restrictions**:
- ALT accounts must be active (not deactivated)
- Newly added addresses require one slot to become usable
- Maximum 256 addresses per ALT
- Multiple ALTs can be used in a single transaction

## Compute Budget

### Default Limits

| Parameter | Default | Maximum |
|-----------|---------|---------|
| Compute units per instruction | 200,000 | — |
| Compute units per transaction | 200,000 * num_instructions | 1,400,000 |
| Heap size | 32 KB | 256 KB |
| Call depth | — | 4 |
| Stack frame size | — | 4 KB |

### Compute Budget Instructions

Program ID: `ComputeBudget111111111111111111111111111111`

**Set Compute Unit Limit** (instruction discriminator: `0x02`):
```
Data layout: [0x02, units: u32 LE]
Example: Set 300,000 CUs → [0x02, 0xe0, 0x93, 0x04, 0x00]
```

**Set Compute Unit Price** (instruction discriminator: `0x03`):
```
Data layout: [0x03, micro_lamports: u64 LE]
Example: Set 1000 micro-lamports → [0x03, 0xe8, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
```

**Request Heap Frame** (instruction discriminator: `0x01`):
```
Data layout: [0x01, bytes: u32 LE]
Must be multiple of 1024, max 256 KB (262144)
```

### Priority Fee Calculation

```
priority_fee_lamports = compute_unit_limit * compute_unit_price_micro_lamports / 1_000_000
```

Example: 300,000 CU limit at 5,000 micro-lamports/CU:
```
300,000 * 5,000 / 1,000,000 = 1,500 lamports = 0.0000015 SOL
```

The base transaction fee (5,000 lamports per signature) is always charged in addition to the priority fee.

## Transaction Size: 1232 Bytes

The maximum transaction size is 1232 bytes. This is a hard network limit (MTU-derived). Here is how the bytes break down for a typical transaction:

| Component | Size |
|-----------|------|
| Signatures length (compact-u16) | 1 byte |
| Each signature | 64 bytes |
| Header | 3 bytes |
| Account keys length (compact-u16) | 1-2 bytes |
| Each account key | 32 bytes |
| Recent blockhash | 32 bytes |
| Instructions length (compact-u16) | 1-2 bytes |
| Each instruction (variable) | ~5-100+ bytes |

**Budget estimation for a single-signer transaction**:
```
Fixed overhead: 64 (sig) + 1 (sig count) + 3 (header) + 32 (blockhash)
              + 2 (account count) + 2 (instruction count) = 104 bytes
Remaining for accounts + instructions: 1232 - 104 = 1128 bytes
Each account key: 32 bytes → ~35 accounts max with minimal instruction data
```

### Strategies to Fit Within 1232 Bytes

1. **Use v0 transactions with ALTs** — compress account references
2. **Minimize accounts** — only include necessary accounts
3. **Batch wisely** — split large operations across transactions
4. **Use compact instruction data** — avoid unnecessary padding

## Blockhash Management

### Fetching a Blockhash

```python
import httpx

def get_latest_blockhash(rpc_url: str) -> dict:
    """Get latest blockhash and its last valid block height.

    Returns:
        Dict with 'blockhash' (str) and 'lastValidBlockHeight' (int).
    """
    resp = httpx.post(rpc_url, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "getLatestBlockhash",
        "params": [{"commitment": "finalized"}]
    })
    return resp.json()["result"]["value"]
```

### Blockhash Expiry and Retry

- A blockhash is valid for ~150 slots (~60-90 seconds)
- `lastValidBlockHeight` tells you the exact block height after which the blockhash expires
- If a transaction fails with `BlockhashNotFound`, fetch a new blockhash and rebuild
- For time-sensitive operations, use `commitment: "confirmed"` for faster (but slightly less safe) blockhashes
- For high-value operations, use `commitment: "finalized"` and accept the latency

### Durable Nonces (Advanced)

For transactions that need to remain valid longer than ~90 seconds:

1. Create a nonce account with `SystemProgram.createNonceAccount`
2. Use the nonce value as the "blockhash" in your transaction
3. Include an `AdvanceNonce` instruction as the first instruction
4. The transaction remains valid until the nonce is advanced

Use cases: offline signing, multi-party signatures, scheduled transactions.
