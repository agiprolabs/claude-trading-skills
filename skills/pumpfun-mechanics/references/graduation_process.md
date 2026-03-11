# PumpFun Graduation — Process & PumpSwap Migration

## Graduation Threshold

A token graduates when its **realSolReserves** reaches approximately **85 SOL** (85,000,000,000 lamports).

At graduation:
- Virtual SOL ≈ 115 SOL (30 initial + 85 real)
- Virtual Tokens ≈ 279.9M
- Spot price ≈ 4.109 × 10⁻⁷ SOL/token
- Market cap ≈ 115 SOL × supply ratio ≈ $12-14K USD (varies with SOL price)
- Price is approximately **14.7x** the initial launch price

## Graduation Rate

Only approximately **1.4%** of tokens launched on PumpFun ever graduate. The vast majority die before reaching the 85 SOL threshold.

## Graduation Event Sequence

1. A buy transaction pushes `realSolReserves` past the graduation threshold
2. The PumpFun program sets `complete = true` on the bonding curve account
3. A `CompleteEvent` is emitted (discriminator `5f72619cd42e9808`)
4. The bonding curve stops accepting new trades (attempts revert)
5. Liquidity (~$12K worth) is automatically deposited to the destination DEX
6. Token becomes tradeable on the destination DEX

## CompleteEvent Layout

After the 8-byte discriminator:

```
user:           pubkey   32 bytes  (wallet that triggered graduation)
mint:           pubkey   32 bytes  (token mint address)
bondingCurve:   pubkey   32 bytes  (bonding curve account)
timestamp:      i64       8 bytes  (unix seconds)
```

Total: 104 bytes after discriminator.

## Migration Targets

### PumpSwap (March 2025+, current default)

- **Program**: `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`
- **Type**: Constant-product AMM
- **Fee**: 1% (100 bps), same as bonding curve
- **Migration fee**: None (free)
- **Creator revenue**: 0.05% of PumpSwap trading volume
- **95%+** of current graduations go to PumpSwap

### Raydium V4 (legacy, before March 2025)

- **Program**: `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`
- **Type**: Constant-product AMM
- **Fee**: 0.25% (25 bps)
- **Migration fee**: 6 SOL (deducted from reserves)
- **Status**: No longer the default migration target

## PumpSwap Mechanics

### Instruction Semantics Inversion

PumpSwap uses base=WSOL, quote=token. This creates an unintuitive naming:

| Action You Want | PumpSwap Instruction | What It Does |
|-----------------|---------------------|-------------|
| Buy tokens (spend SOL) | `sell` | "Sell" SOL base to receive token quote |
| Sell tokens (receive SOL) | `buy` | "Buy" SOL base by spending token quote |

This is a common source of bugs. The discriminators:
- PumpSwap `buy` (selling tokens): `66063d1201daebea`
- PumpSwap `sell` (buying tokens): `33e685a4017f83ad`

### PumpSwap Pool Layout

```
Offset 0:    discriminator        8 bytes
Offset 8:    bump                 1 byte
Offset 9:    index                2 bytes
Offset 11:   creator              32 bytes (pool creator, NOT token creator)
Offset 43:   base_mint            32 bytes (always WSOL)
Offset 75:   quote_mint           32 bytes (the token)
Offset 107:  lp_mint              32 bytes
Offset 139:  pool_base_account    32 bytes (SOL vault)
Offset 171:  pool_quote_account   32 bytes (token vault)
Offset 203:  lp_supply            8 bytes
Offset 211:  coin_creator         32 bytes (original token creator)
```

### PumpSwap PDAs

| PDA | Seeds | Program |
|-----|-------|---------|
| Global Config | `["global_config"]` | PumpSwap |
| Event Authority | `["__event_authority"]` | PumpSwap |
| Creator Vault Authority | `["creator_vault", coin_creator]` | PumpSwap |
| Fee Config | `["fee_config", pumpswap_program_id]` | Fee Program |

## Tracking Graduation Progress

### Fill Percentage

```python
GRAD_THRESHOLD = 85_000_000_000  # 85 SOL in lamports

def fill_percentage(real_sol_reserves: int) -> float:
    """Calculate how close a token is to graduation."""
    return (real_sol_reserves / GRAD_THRESHOLD) * 100.0
```

### Fill Velocity

Track the rate of SOL accumulation to predict graduation timing:

```python
def estimated_time_to_graduation(
    current_sol: int,
    previous_sol: int,
    time_delta_seconds: float,
) -> float | None:
    """Estimate seconds until graduation based on current velocity."""
    remaining = GRAD_THRESHOLD - current_sol
    if remaining <= 0:
        return 0
    velocity = (current_sol - previous_sol) / time_delta_seconds  # lamports/sec
    if velocity <= 0:
        return None  # not progressing
    return remaining / velocity
```

### Monitoring via gRPC

Subscribe to the PumpFun program via Yellowstone gRPC to receive:
- **TradeEvents**: Every buy/sell with updated reserves
- **CompleteEvents**: Graduation trigger

Filter by program ID `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` in your subscription.

## Fee Comparison Post-Graduation

| DEX | Fee | Notes |
|-----|-----|-------|
| PumpFun bonding curve | 1.00% | Before graduation |
| PumpSwap | 1.00% | After graduation (PumpSwap) |
| Raydium V4 | 0.25% | After graduation (legacy) |
| Raydium CPMM | 0.25% | — |
| Orca Whirlpool | 0.30% | — |
| Meteora DLMM | 0.30% | — |

Note: PumpSwap's 1% fee is higher than other Solana DEXes. This is relevant for cost modeling.
