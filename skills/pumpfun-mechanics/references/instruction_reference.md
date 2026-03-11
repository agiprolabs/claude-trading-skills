# PumpFun — Instruction & Event Reference

## Program IDs

| Program | Address | Purpose |
|---------|---------|---------|
| PumpFun | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | Bonding curve trades |
| PumpSwap | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | Post-graduation AMM |
| Fee Program | `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` | Fee handling |
| Metaplex Metadata | `metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s` | Token metadata |

## Well-Known Accounts

| Account | Address |
|---------|---------|
| Global | `4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf` |
| Fee Recipient | `62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV` |
| Event Authority | `Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1` |

---

## Instruction Discriminators

Discriminators are the first 8 bytes of instruction data.

### PumpFun Instructions

| Instruction | Hex | Use |
|-------------|-----|-----|
| buy_exact_sol_in (V2) | `38fc74089edfcd5f` | Current buy |
| sell (V2) | `33e685a4017f83ad` | Current sell |
| buy (V1/legacy) | `66063d1201daebea` | Legacy buy |
| create | `181ec828051c0777` | Token creation |
| initialize | `afaf6d1f0d989bed` | Global state init |
| setParams | `a51f8635bdb482ff` | Admin config |

### Buy V2 — Instruction Data (24 bytes)

```
Bytes 0-7:   discriminator         0x38fc74089edfcd5f
Bytes 8-15:  spendable_sol_in      u64 LE (total SOL budget)
Bytes 16-23: min_tokens_out        u64 LE (slippage floor)
```

Note: `spendable_sol_in` is the TOTAL SOL budget. The 1% fee is deducted internally by the program before applying to the curve.

### Sell V2 — Instruction Data (24 bytes)

```
Bytes 0-7:   discriminator         0x33e685a4017f83ad
Bytes 8-15:  amount_tokens         u64 LE (tokens to sell, raw units)
Bytes 16-23: min_sol_output        u64 LE (minimum SOL received)
```

### Buy V2 — Account Layout (17 accounts)

```
 0: global                        (readonly)
 1: feeRecipient                  (writable)
 2: mint                          (readonly)
 3: bondingCurve                  (writable)
 4: associatedBondingCurve        (writable)   ATA(bondingCurve, mint)
 5: associatedUser                (writable)   ATA(user, mint)
 6: user                          (signer)
 7: systemProgram                 (readonly)
 8: tokenProgram                  (readonly)
 9: creatorVault                  (writable)   PDA: ["creator-vault", creator]
10: eventAuthority                (readonly)
11: program                       (readonly)
12: globalVolumeAccumulator       (readonly)
13: userVolumeAccumulator         (writable)   PDA: ["user_volume_accumulator", user]
14: feeConfig                     (readonly)   PDA: ["fee_config", pumpfun_program]
15: feeProgram                    (readonly)
16: bondingCurveV2                (readonly)   PDA: ["bonding-curve-v2", mint]
```

### Sell V2 — Account Layout (15 accounts)

```
 0: global                        (readonly)
 1: feeRecipient                  (writable)
 2: mint                          (readonly)
 3: bondingCurve                  (writable)
 4: associatedBondingCurve        (writable)
 5: associatedUser                (writable)
 6: user                          (signer)
 7: systemProgram                 (readonly)
 8: creatorVault                  (writable)
 9: tokenProgram                  (readonly)
10: eventAuthority                (readonly)
11: program                       (readonly)
12: feeConfig                     (readonly)
13: feeProgram                    (readonly)
14: bondingCurveV2                (readonly)   (remaining account)
```

**Note**: Sell has 15 accounts vs buy's 17. Sell does NOT include volume accumulators. Account ordering differs — `creatorVault` and `tokenProgram` swap positions between buy (8=tokenProgram, 9=creatorVault) and sell (8=creatorVault, 9=tokenProgram).

---

## Event Discriminators

Events use Anchor's convention: `sha256("event:<EventName>")[0..8]`

| Event | Hex Discriminator |
|-------|------------------|
| CreateEvent | `1b72a94ddeeb6376` |
| TradeEvent | `bddb7fd34ee661ee` |
| CompleteEvent | `5f72619cd42e9808` |

### CreateEvent Layout (after discriminator)

```
name:           string    (4-byte LE length prefix + UTF-8 data)
symbol:         string    (4-byte LE length prefix + UTF-8 data)
uri:            string    (4-byte LE length prefix + UTF-8 data)
mint:           pubkey    32 bytes
bondingCurve:   pubkey    32 bytes
user:           pubkey    32 bytes (the creator)
```

### TradeEvent Layout (after discriminator)

```
mint:                   pubkey    32 bytes
solAmount:              u64        8 bytes LE
tokenAmount:            u64        8 bytes LE
isBuy:                  bool       1 byte (1=buy, 0=sell)
user:                   pubkey    32 bytes
timestamp:              i64        8 bytes LE (unix seconds)
virtualSolReserves:     u64        8 bytes LE
virtualTokenReserves:   u64        8 bytes LE
realSolReserves:        u64        8 bytes LE
realTokenReserves:      u64        8 bytes LE
```

Total: 121 bytes. Every field is fixed-size — no variable-length data.

### CompleteEvent Layout (after discriminator)

```
user:           pubkey    32 bytes
mint:           pubkey    32 bytes
bondingCurve:   pubkey    32 bytes
timestamp:      i64        8 bytes LE
```

Total: 104 bytes.

---

## Parsing Pattern

Events are emitted via CPI (Cross-Program Invocation), so they appear in **inner instructions**, not top-level instructions. The discriminator may not be at byte offset 0.

```python
def find_event(data: bytes, discriminator: bytes) -> int:
    """Find event discriminator anywhere in instruction data.

    Args:
        data: Raw instruction data bytes.
        discriminator: 8-byte event discriminator.

    Returns:
        Byte offset of the event data (after discriminator), or -1 if not found.
    """
    idx = data.find(discriminator)
    if idx == -1:
        return -1
    return idx + 8  # skip discriminator, return start of event data
```

---

## Bonding Curve Account Layout

Account data for the bonding curve PDA (`["bonding-curve", mint]`):

```
Offset 0:    discriminator          u64    8 bytes
Offset 8:    virtualTokenReserves   u64    8 bytes
Offset 16:   virtualSolReserves     u64    8 bytes
Offset 24:   realTokenReserves      u64    8 bytes
Offset 32:   realSolReserves        u64    8 bytes
Offset 40:   tokenTotalSupply       u64    8 bytes
Offset 48:   complete               bool   1 byte
Offset 49:   creator                pubkey 32 bytes
```

Total minimum: 81 bytes.

```python
import struct

def parse_bonding_curve(data: bytes) -> dict:
    """Parse bonding curve account data."""
    if len(data) < 81:
        return {}
    return {
        "virtualTokenReserves": struct.unpack_from("<Q", data, 8)[0],
        "virtualSolReserves":   struct.unpack_from("<Q", data, 16)[0],
        "realTokenReserves":    struct.unpack_from("<Q", data, 24)[0],
        "realSolReserves":      struct.unpack_from("<Q", data, 32)[0],
        "tokenTotalSupply":     struct.unpack_from("<Q", data, 40)[0],
        "complete":             bool(data[48]),
        "creator":              data[49:81],  # 32-byte pubkey
    }
```

---

## PDA Seeds

| PDA | Seeds | Program |
|-----|-------|---------|
| Bonding Curve | `["bonding-curve", mint_pubkey]` | PumpFun |
| Bonding Curve V2 | `["bonding-curve-v2", mint_pubkey]` | PumpFun |
| Mint Authority | `["mint-authority"]` | PumpFun |
| Global | `["global"]` | PumpFun |
| Creator Vault | `["creator-vault", creator_pubkey]` | PumpFun |
| Global Volume Acc | `["global_volume_accumulator"]` | PumpFun |
| User Volume Acc | `["user_volume_accumulator", user_pubkey]` | PumpFun |
| Fee Config | `["fee_config", pumpfun_program_id]` | Fee Program |
