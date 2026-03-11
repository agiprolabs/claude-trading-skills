# Pool Types — AMM Designs on Solana

## Constant Product (xy = k)

### Implementations

- **Raydium V4 (AMM)**: The most common pool type for new Solana tokens. PumpFun tokens graduate to Raydium V4 pools. Program ID: `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`
- **Orca Legacy**: Older constant-product pools being phased out in favor of Whirlpools.

### Mechanics

Both reserves (SOL and TOKEN) maintain the invariant `x * y = k`. Liquidity is distributed uniformly across the entire price range from 0 to infinity.

```
Price = x / y (SOL per TOKEN)
After trade: x_new * y_new = k
Slippage = Δx / (x + Δx)
```

### Characteristics

| Property | Value |
|----------|-------|
| Capital efficiency | Low — liquidity spread across all prices |
| Slippage predictability | High — deterministic from reserves |
| Range exhaustion risk | None — always has liquidity |
| Impermanent loss | Standard IL curve |
| LP complexity | Low — deposit and forget |

### Identifying On-Chain

Raydium V4 pools have a fixed account layout. Key accounts:
- Pool state: contains reserves, fees, LP mint
- Token vaults: two SPL token accounts holding reserves
- LP mint: SPL token minted to liquidity providers

```python
# Raydium V4 program
RAYDIUM_AMM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
```

## Concentrated Liquidity (CLMM / Whirlpool)

### Implementations

- **Orca Whirlpool**: Primary CLMM on Solana. Program ID: `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc`
- **Raydium CLMM**: Raydium's concentrated liquidity implementation. Program ID: `CAMMCzo5YL8w4VFF8KVHr7UfsuqSrsNyZ5bfWQ5KSBhH`

### Mechanics

LPs choose a price range `[p_low, p_high]` to concentrate their liquidity. Within this range, the pool behaves like a constant-product pool with much higher virtual reserves.

```
Concentration factor = sqrt(p_high / p_low) / (sqrt(p_high / p_low) - 1)
```

For a +/-5% range: concentration factor is approximately 10x. The LP provides 10x the effective depth per dollar of capital.

### Tick System

Prices are discretized into ticks. Each tick represents a 0.01% price change (1 basis point). LPs deposit liquidity between two ticks.

```
tick = floor(log(price) / log(1.0001))
price = 1.0001^tick
```

Ticks are grouped into tick arrays. Liquidity can vary between tick groups, creating an uneven depth profile.

### Characteristics

| Property | Value |
|----------|-------|
| Capital efficiency | High — 10-100x within range |
| Slippage predictability | Low — depends on tick distribution |
| Range exhaustion risk | High — zero liquidity outside range |
| Impermanent loss | Higher within range (amplified) |
| LP complexity | High — must manage range |

### Impact on Traders

- **Small trades**: Much less slippage than constant-product at same TVL
- **Large trades**: Risk of exhausting the active range, causing sudden slippage spike
- **Volatility**: If price moves outside most LP ranges, liquidity can vanish quickly

## Dynamic AMM (Meteora DLMM)

### Implementation

- **Meteora DLMM**: Dynamic Liquidity Market Maker. Program ID: `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`

### Mechanics

Meteora uses a bin-based system. Price is divided into discrete bins, each representing a fixed price point. LPs deposit into specific bins.

```
bin_id = floor(log(price) / log(1 + bin_step/10000))
```

Bin step sizes vary by pool (e.g., 1 bps, 5 bps, 25 bps, 100 bps). Smaller bin steps = more granular pricing but more bins to manage.

### Dynamic Fees

Meteora adjusts fees based on volatility. High volatility = higher fees, compensating LPs for impermanent loss risk. Fee formula:

```
total_fee = base_fee + variable_fee
variable_fee = volatility_accumulator * bin_step^2
```

### Characteristics

| Property | Value |
|----------|-------|
| Capital efficiency | High — bin-based concentration |
| Slippage predictability | Medium — depends on bin distribution |
| Range exhaustion risk | Medium — bins can be empty |
| Fee structure | Dynamic — adjusts to volatility |
| LP complexity | Medium — choose bins |

## PumpFun Token Lifecycle

Tokens launched on PumpFun follow a standard liquidity path:

1. **Bonding curve phase**: Token trades on PumpFun's internal bonding curve. No DEX pool yet. Liquidity is synthetic.
2. **Graduation**: At ~$69K market cap, PumpFun deploys a Raydium V4 pool with approximately 79 SOL + the remaining token supply.
3. **Post-graduation**: Additional pools may appear on Orca, Meteora, or other DEXes as market makers and LPs enter.

### Implications for Liquidity Analysis

- Immediately after graduation, there is exactly 1 pool with ~79 SOL of liquidity
- Pool TVL will be approximately $15-20K at typical SOL prices
- LP tokens from PumpFun graduation are typically burned (locked)
- Additional pools are a positive signal — means market makers see opportunity

## Comparison Table

| Feature | Raydium V4 | Orca Whirlpool | Raydium CLMM | Meteora DLMM |
|---------|-----------|----------------|--------------|---------------|
| Model | xy = k | Concentrated | Concentrated | Bin-based |
| Capital efficiency | 1x | 10-100x | 10-100x | 10-50x |
| Min TVL for trading | High | Low | Low | Low |
| Slippage predictability | High | Low | Low | Medium |
| Fee model | Fixed | Fixed per pool | Fixed per pool | Dynamic |
| LP token | Fungible SPL | NFT position | NFT position | Fungible per bin |
| Best for | New tokens | Major pairs | Major pairs | Volatile pairs |
| Worst for | Large caps | Microcaps | Microcaps | Stable pairs |

## Identifying Pool Type from DexScreener Data

DexScreener's `dexId` and `labels` fields help identify pool type:

```python
def classify_pool(pair: dict) -> str:
    """Classify a DexScreener pair by pool type."""
    dex = pair.get("dexId", "").lower()
    labels = [l.lower() for l in pair.get("labels", [])]

    if dex == "raydium":
        if "clmm" in labels or "concentrated" in labels:
            return "raydium_clmm"
        return "raydium_v4"
    elif dex == "orca":
        return "orca_whirlpool"  # Almost all Orca pools are Whirlpools now
    elif dex == "meteora":
        if "dlmm" in labels:
            return "meteora_dlmm"
        return "meteora_amm"
    else:
        return dex
```
