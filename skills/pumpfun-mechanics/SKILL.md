---
name: pumpfun-mechanics
description: PumpFun bonding curve math, graduation mechanics, instruction parsing, and PumpSwap migration
---

# PumpFun Mechanics — Bonding Curves, Graduation & Instruction Parsing

PumpFun is the dominant Solana token launchpad. Understanding its bonding curve math, graduation process, and instruction formats is essential for analyzing new token launches, building trading strategies around graduation events, and parsing on-chain PumpFun activity.

## Bonding Curve Math

PumpFun uses a **virtual constant-product (CPMM)** bonding curve:

```
k = virtualSolReserves × virtualTokenReserves
```

### Initial Parameters

| Parameter | Value |
|-----------|-------|
| Initial Virtual SOL | 30 SOL (30,000,000,000 lamports) |
| Initial Virtual Tokens | ~1.073B tokens (1,073,000,000,000,000 raw, 6 decimals) |
| Token Total Supply | 1B tokens (1,000,000,000,000,000 raw) |
| Real Token Reserves | ~793M tokens (793,000,000,000,000 raw) |
| Real SOL Reserves | 0 (no real SOL at launch) |
| Fee | 1% (applied externally by the program) |

**Virtual vs Real**: Virtual reserves define the curve shape. Real reserves track actual withdrawable funds. The difference (1.073B - 793M = 280M virtual tokens) shapes the initial price but can never be withdrawn.

### Spot Price

```python
price_sol_per_token = virtual_sol_reserves / virtual_token_reserves

# In human-readable units:
price = (virtual_sol / 1e9) / (virtual_token / 1e6)

# At genesis: 30 / 1,073,000,000 ≈ 2.796e-8 SOL/token
# At graduation: ~4.1e-7 SOL/token (~14.7x from launch)
```

### Buy Tokens (SOL → Tokens)

```python
def buy_tokens(v_sol: int, v_tok: int, real_tok: int, sol_in: int) -> int:
    """Calculate tokens received for a given SOL input.

    Args:
        v_sol: Virtual SOL reserves (lamports).
        v_tok: Virtual token reserves (raw).
        real_tok: Real token reserves (raw).
        sol_in: SOL to spend (lamports, BEFORE 1% fee).

    Returns:
        Tokens received (raw units).
    """
    k = v_sol * v_tok
    new_v_sol = v_sol + sol_in
    new_v_tok = k // new_v_sol + 1  # +1 matches on-chain rounding
    tokens_out = v_tok - new_v_tok
    return min(tokens_out, real_tok)
```

### Sell Tokens (Tokens → SOL)

```python
def sell_tokens(v_sol: int, v_tok: int, real_sol: int, tokens_in: int) -> int:
    """Calculate SOL received for selling tokens.

    Args:
        v_sol: Virtual SOL reserves (lamports).
        v_tok: Virtual token reserves (raw).
        real_sol: Real SOL reserves (lamports).
        tokens_in: Tokens to sell (raw units).

    Returns:
        SOL received (lamports, BEFORE 1% fee).
    """
    k = v_sol * v_tok
    new_v_tok = v_tok + tokens_in
    new_v_sol = k // new_v_tok
    sol_out = v_sol - new_v_sol - 1  # -1 matches on-chain floor rounding
    return min(sol_out, real_sol)
```

### Buy Cost (Exact token amount → SOL needed)

```python
def buy_cost(v_sol: int, v_tok: int, tokens_wanted: int) -> int:
    """Calculate SOL needed to buy exact token amount.

    Returns:
        SOL cost in lamports (before fee). Returns max int if impossible.
    """
    if tokens_wanted >= v_tok:
        return 2**64 - 1  # impossible
    k = v_sol * v_tok
    new_v_tok = v_tok - tokens_wanted
    new_v_sol = k // new_v_tok + 1
    return new_v_sol - v_sol
```

### Fee Handling

The 1% fee is **not** part of the curve math. It's applied externally:

```python
# Buying: fee deducted from SOL input before curve
actual_sol_to_curve = sol_input * 0.99

# Selling: fee deducted from SOL output after curve
actual_sol_received = sol_from_curve * 0.99

# Roundtrip minimum cost: ~2% from fees alone, plus price impact
```

### Market Cap

```python
market_cap_sol = (token_total_supply * virtual_sol_reserves) / virtual_token_reserves
```

## Graduation

Graduation occurs when `realSolReserves` reaches **~85 SOL** (~$12K-14K depending on SOL price). Only ~1.4% of PumpFun tokens ever graduate.

### What Happens

1. `complete` flag set to `true` on bonding curve account
2. `CompleteEvent` emitted (discriminator `5f72619cd42e9808`)
3. Bonding curve stops accepting trades
4. ~$12K liquidity deposited to the destination DEX
5. Token becomes tradeable on PumpSwap (or Raydium for older tokens)

### Fill Percentage

```python
GRADUATION_THRESHOLD = 85_000_000_000  # 85 SOL in lamports

fill_pct = (real_sol_reserves / GRADUATION_THRESHOLD) * 100.0
```

### Migration Targets

- **March 2025+**: PumpSwap (`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`) — native AMM, no migration fee
- **Before March 2025**: Raydium V4 (`675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`) — 6 SOL fee

### PumpSwap Post-Graduation

PumpSwap is a constant-product AMM with 1% fee (same as bonding curve). Key differences:
- Base asset is always WSOL, quote is token
- Instruction semantics are inverted: "buy" instruction sells tokens, "sell" instruction buys tokens
- Supports creator revenue sharing (0.05% of volume to original creator)

## Program IDs & Addresses

| Program/Account | Address |
|-----------------|---------|
| PumpFun Program | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` |
| PumpSwap Program | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` |
| Fee Program | `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` |
| Global Account | `4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf` |
| Fee Recipient | `62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV` |
| Event Authority | `Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1` |

## Event Parsing

Events are Anchor-style: `sha256("event:<EventName>")[0..8]`

| Event | Discriminator (hex) |
|-------|-------------------|
| CreateEvent | `1b72a94ddeeb6376` |
| TradeEvent | `bddb7fd34ee661ee` |
| CompleteEvent | `5f72619cd42e9808` |

### TradeEvent Layout (after 8-byte discriminator)

```
mint:                  pubkey   32 bytes
solAmount:             u64       8 bytes
tokenAmount:           u64       8 bytes
isBuy:                 bool      1 byte
user:                  pubkey   32 bytes
timestamp:             i64       8 bytes
virtualSolReserves:    u64       8 bytes
virtualTokenReserves:  u64       8 bytes
realSolReserves:       u64       8 bytes
realTokenReserves:     u64       8 bytes
```

**Critical**: Events are in CPI inner instructions. Search for discriminators **anywhere** in instruction data, not just at offset 0.

### Bonding Curve Account Layout

```
Offset 0:   discriminator          8 bytes
Offset 8:   virtualTokenReserves   u64
Offset 16:  virtualSolReserves     u64
Offset 24:  realTokenReserves      u64
Offset 32:  realSolReserves        u64
Offset 40:  tokenTotalSupply       u64
Offset 48:  complete               bool (1 byte)
Offset 49:  creator                pubkey (32 bytes)
```

### PDA Derivation

| PDA | Seeds |
|-----|-------|
| Bonding Curve | `["bonding-curve", mint]` |
| Bonding Curve V2 | `["bonding-curve-v2", mint]` |
| Creator Vault | `["creator-vault", creator]` |

## Instruction Discriminators

| Instruction | Hex | Notes |
|-------------|-----|-------|
| buy_exact_sol_in (V2) | `38fc74089edfcd5f` | Current production buy |
| sell (V2) | `33e685a4017f83ad` | Current production sell |
| buy (V1/legacy) | `66063d1201daebea` | Legacy, still seen occasionally |
| create | `181ec828051c0777` | Token creation |

### Buy Instruction Data (24 bytes)

```
[0..8]:   discriminator
[8..16]:  spendable_sol_in    u64 LE (total SOL budget, fees deducted internally)
[16..24]: min_tokens_out      u64 LE (slippage floor)
```

### Sell Instruction Data (24 bytes)

```
[0..8]:   discriminator
[8..16]:  amount_tokens       u64 LE (tokens to sell, raw)
[16..24]: min_sol_output      u64 LE (minimum SOL out, lamports)
```

## Price Impact & Sizing

```python
def price_impact(v_sol: int, v_tok: int, sol_in: int) -> float:
    """Calculate price impact for a buy as a percentage."""
    spot = v_sol / v_tok
    tokens = buy_tokens(v_sol, v_tok, v_tok, sol_in)
    if tokens == 0:
        return float('inf')
    exec_price = sol_in / tokens
    return (exec_price / spot - 1) * 100

# Example: 1 SOL buy at genesis
# impact = price_impact(30_000_000_000, 1_073_000_000_000_000, 1_000_000_000)
# ≈ 3.3% price impact
```

## Files

### References
- `references/bonding_curve_math.md` — Complete mathematical derivations with worked examples
- `references/graduation_process.md` — Graduation threshold, migration, PumpSwap mechanics
- `references/instruction_reference.md` — Full instruction and event layouts for parsing

### Scripts
- `scripts/curve_calculator.py` — Interactive bonding curve calculator: price, impact, fill %
- `scripts/parse_events.py` — Parse PumpFun events from transaction data
