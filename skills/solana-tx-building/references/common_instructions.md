# Common Solana Instructions Reference

## Program IDs

| Program | Address |
|---------|---------|
| System Program | `11111111111111111111111111111111` |
| Token Program | `TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA` |
| Token-2022 | `TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb` |
| Associated Token Account | `ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL` |
| Compute Budget | `ComputeBudget111111111111111111111111111111` |
| Memo Program | `MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr` |
| Memo Program (v1) | `Memo1UhkJBfCR6MNhJeXukzT2hbXzgnQ8e7MY1WDvN8` |
| Address Lookup Table | `AddressLookupTab1e1111111111111111111111111` |
| Jupiter v6 | `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` |

## System Program Instructions

### Transfer SOL

- **Instruction index**: 2 (u32 LE)
- **Data**: `[02 00 00 00] + [amount as u64 LE]`

```python
import struct

def system_transfer_data(lamports: int) -> bytes:
    """Build System Program transfer instruction data."""
    return struct.pack("<I", 2) + struct.pack("<Q", lamports)
```

**Accounts** (in order):
1. Source (signer, writable)
2. Destination (writable)

### Create Account

- **Instruction index**: 0 (u32 LE)
- **Data**: `[00 00 00 00] + [lamports u64 LE] + [space u64 LE] + [owner Pubkey 32 bytes]`

```python
def system_create_account_data(
    lamports: int, space: int, owner: bytes
) -> bytes:
    """Build System Program createAccount instruction data."""
    return (
        struct.pack("<I", 0)
        + struct.pack("<Q", lamports)
        + struct.pack("<Q", space)
        + owner  # 32 bytes
    )
```

**Accounts**:
1. Payer (signer, writable)
2. New account (signer, writable)

### Allocate

- **Instruction index**: 8 (u32 LE)
- **Data**: `[08 00 00 00] + [space u64 LE]`

**Accounts**:
1. Account to allocate (signer, writable)

## Token Program Instructions

### Transfer

- **Instruction index**: 3
- **Data**: `[03] + [amount u64 LE]`

```python
def token_transfer_data(amount: int) -> bytes:
    """Build Token Program transfer instruction data."""
    return bytes([3]) + struct.pack("<Q", amount)
```

**Accounts**:
1. Source token account (writable)
2. Destination token account (writable)
3. Owner (signer)

### Transfer Checked

- **Instruction index**: 12
- **Data**: `[0c] + [amount u64 LE] + [decimals u8]`

```python
def token_transfer_checked_data(amount: int, decimals: int) -> bytes:
    """Build Token Program transferChecked instruction data."""
    return bytes([12]) + struct.pack("<Q", amount) + bytes([decimals])
```

**Accounts**:
1. Source token account (writable)
2. Token mint (read-only)
3. Destination token account (writable)
4. Owner (signer)

Preferred over plain `transfer` because it validates the mint and decimals.

### Approve

- **Instruction index**: 4
- **Data**: `[04] + [amount u64 LE]`

**Accounts**:
1. Source token account (writable)
2. Delegate (read-only)
3. Owner (signer)

### Mint To

- **Instruction index**: 7
- **Data**: `[07] + [amount u64 LE]`

**Accounts**:
1. Mint (writable)
2. Destination token account (writable)
3. Mint authority (signer)

### Burn

- **Instruction index**: 8
- **Data**: `[08] + [amount u64 LE]`

**Accounts**:
1. Source token account (writable)
2. Mint (writable)
3. Owner (signer)

## Associated Token Account Program

### Create ATA

- **Instruction index**: 0 (implicit — no instruction data)
- **Data**: empty (`b""`)

```python
def ata_create_data() -> bytes:
    """ATA create instruction has no data."""
    return b""
```

**Accounts** (in order):
1. Payer (signer, writable) — pays rent for new account
2. Associated token account (writable) — the ATA to create
3. Wallet address (read-only) — owner of the ATA
4. Token mint (read-only)
5. System Program (read-only)
6. Token Program (read-only)

### Create Idempotent

- **Instruction index**: 1
- **Data**: `[01]`

Same accounts as Create ATA. Does not error if the ATA already exists. Preferred for transaction builders since you don't need to check existence first.

### ATA Derivation

The ATA address is a PDA derived from:
```
seeds = [wallet_address, token_program_id, mint_address]
program_id = ATA_PROGRAM_ID
```

```python
import hashlib

def derive_ata(wallet: bytes, mint: bytes) -> bytes:
    """Derive Associated Token Account address (simplified).

    Note: This is illustrative. Production code should use
    a proper PDA derivation with bump seed search.
    """
    TOKEN_PROGRAM = bytes.fromhex(
        "06ddf6e1d765a193d9cbe146ceeb79ac1cb485ed5f5b37913a8cf5857eff00a9"
    )
    ATA_PROGRAM = bytes.fromhex(
        "8c97258f4e2489f1bb3d1029148e0d830b5a1399daff1084048e7bd8dbe9f859"
    )
    # findProgramAddress searches for bump 255..0
    for bump in range(255, -1, -1):
        seed = wallet + TOKEN_PROGRAM + mint + bytes([bump])
        candidate = hashlib.sha256(seed + ATA_PROGRAM + b"ProgramDerivedAddress").digest()
        # Valid PDA must not be on the ed25519 curve (simplified check omitted)
        return candidate
    raise ValueError("Could not derive ATA")
```

## Compute Budget Program

### Set Compute Unit Limit

- **Discriminator**: `0x02`
- **Data**: `[02] + [units u32 LE]`

```python
def compute_budget_set_units(units: int) -> bytes:
    """Set compute unit limit for the transaction."""
    return bytes([2]) + struct.pack("<I", units)
```

**Accounts**: None required.

### Set Compute Unit Price

- **Discriminator**: `0x03`
- **Data**: `[03] + [micro_lamports u64 LE]`

```python
def compute_budget_set_price(micro_lamports: int) -> bytes:
    """Set compute unit price (priority fee) in micro-lamports."""
    return bytes([3]) + struct.pack("<Q", micro_lamports)
```

**Accounts**: None required.

### Request Heap Frame

- **Discriminator**: `0x01`
- **Data**: `[01] + [bytes u32 LE]`

Must be a multiple of 1024. Maximum 262,144 (256 KB).

**Accounts**: None required.

## Memo Program

### Add Memo

- **Data**: UTF-8 encoded memo string (arbitrary bytes)

```python
def memo_data(message: str) -> bytes:
    """Build memo instruction data."""
    return message.encode("utf-8")
```

**Accounts**: At least one signer (optional, but recommended for attribution).

The memo is stored in the transaction log and is visible in explorers. Maximum length is constrained by transaction size.

## Jupiter Swap Instructions

Jupiter provides swap instructions via the `/swap-instructions` API endpoint rather than requiring manual construction.

### API Flow

```python
import httpx

def get_jupiter_swap_instructions(
    quote: dict,
    user_pubkey: str,
) -> dict:
    """Get swap instructions from Jupiter API.

    Args:
        quote: Quote response from /quote endpoint.
        user_pubkey: The user's wallet public key.

    Returns:
        Dict with setupInstructions, swapInstruction,
        cleanupInstruction, and addressLookupTableAddresses.
    """
    resp = httpx.post(
        "https://quote-api.jup.ag/v6/swap-instructions",
        json={
            "quoteResponse": quote,
            "userPublicKey": user_pubkey,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        },
    )
    resp.raise_for_status()
    return resp.json()
```

The response contains pre-encoded instructions that you deserialize and include in your transaction. See the `jupiter-api` skill for full endpoint documentation.
