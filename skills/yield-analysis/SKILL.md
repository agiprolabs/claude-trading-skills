---
name: yield-analysis
description: DeFi yield evaluation including fee APR, real vs nominal yield, net APY after costs, and yield sustainability analysis
---

# Yield Analysis — DeFi Yield Evaluation & Comparison

DeFi yields are often misleading. A pool advertising 200% APY may deliver negative real returns once you account for impermanent loss, gas costs, and emission token depreciation. This skill provides the framework to decompose, evaluate, and compare yield opportunities accurately.

## Why Yield Analysis Matters

Most DeFi yield dashboards show **nominal** yield — the headline number. Real yield requires decomposing that number into its components and subtracting all costs. Without this decomposition:

- LPs chase high-APY pools that destroy capital through IL
- Emission-driven yields collapse as reward tokens lose value
- Gas and rebalancing costs eat into thin margins
- Opportunity cost is ignored (you could be staking SOL at ~7%)

## Yield Components

Every DeFi yield breaks down into one or more of these sources:

### 1. Trading Fee Income
Swap fees earned by liquidity providers. This is the most sustainable yield source because it comes from real economic activity.

```python
fee_apr = (daily_volume * fee_rate / tvl) * 365
your_daily_fees = daily_volume * fee_rate * (your_liquidity / total_liquidity)
```

For CLMM pools (concentrated liquidity), fee income is amplified by how tightly you concentrate your range. See the `lp-math` skill for CLMM mechanics.

### 2. Token Emissions / Incentives
Protocol reward tokens distributed to LPs. Often the largest component of advertised yields, but frequently unsustainable.

```python
emission_apr = (daily_emission_tokens * token_price * 365) / tvl
```

The critical question: will the emission token hold its value? If everyone farms and dumps, the token depreciates and actual USD yield is much lower.

### 3. Lending Interest
Interest earned from lending protocol deposits (Marginfi, Kamino, Solend). Driven by borrowing demand — more sustainable than emissions but fluctuates with utilization.

### 4. Staking Rewards
Validator staking yield (~7% APR on Solana) or liquid staking token (LST) yield. The baseline risk-free rate for the Solana ecosystem.

## Real vs Nominal Yield

| Metric | What It Includes | What It Ignores |
|--------|-----------------|-----------------|
| Nominal APY | Fee APR + emission APR (compounded) | IL, gas, depreciation, risk |
| Real Yield | Everything, net of all costs | Nothing — this is the true return |

### Real Yield Formula

```
real_yield = fee_apr
           + emission_apr × (1 - emission_depreciation)
           - il_cost
           - gas_cost
           - rebalancing_cost
```

Where:
- `fee_apr`: annualized fee income as fraction of position value
- `emission_apr`: annualized emission income at current token price
- `emission_depreciation`: expected decline in emission token price (0.0 to 1.0)
- `il_cost`: expected impermanent loss as annualized rate (see `impermanent-loss` skill)
- `gas_cost`: transaction fees for deposits, withdrawals, claims, compounds
- `rebalancing_cost`: for CLMM positions, cost of rebalancing out-of-range positions

### Example: SOL-USDC Pool

```
Nominal APY displayed:    45%
Decomposition:
  Fee APR:               18%
  Emission APR:          30%  (RAY token rewards)
  Emission depreciation: 40%  (RAY down 40% over 30d)
  Effective emission:    18%  (30% × 0.6)
  IL cost (estimated):   12%  (SOL volatile against USDC)
  Gas + rebalance:        1%

Real yield = 18% + 18% - 12% - 1% = 23%
```

The 45% nominal yield is really 23% after accounting for all factors.

## Fee APR Calculation

### Constant-Product Pools

```python
fee_apr = fee_rate * daily_volume / tvl * 365
```

For a pool with 0.25% fee rate, $2M daily volume, and $10M TVL:

```
fee_apr = 0.0025 * 2_000_000 / 10_000_000 * 365 = 18.25%
```

### Concentrated Liquidity (CLMM) Pools

CLMM fee income depends on your position range relative to trading activity:

```python
# Simplified — see lp-math skill for full CLMM math
fee_apr = fee_rate * daily_volume_in_range / position_liquidity * 365
```

Tighter ranges earn higher fees per dollar deployed but go out of range more frequently, requiring rebalancing.

### Per-LP Share

```python
your_share = your_liquidity / total_pool_liquidity
your_daily_fees = total_daily_fees * your_share
```

## Emission Sustainability

### The Death Spiral Pattern

1. Protocol launches with high emission rewards → attracts LPs
2. TVL grows → yield per LP drops → protocol increases emissions
3. LPs farm and dump emission tokens → token price drops
4. Lower token price → lower USD-denominated yield
5. LPs leave → TVL drops → protocol increases emissions further
6. Spiral continues until emissions stop or protocol fails

### Sustainability Metrics

```python
# Protocol P/E ratio
pe_ratio = fully_diluted_valuation / annual_protocol_revenue

# Revenue-to-emission ratio (> 1.0 is sustainable)
sustainability = annual_revenue / annual_emission_value

# Token velocity (high = lots of sell pressure)
velocity = daily_emission_selling / daily_token_volume
```

**Interpretation:**
- P/E < 20 and sustainability > 1.0: Likely sustainable yield
- P/E 20-100 and sustainability 0.3-1.0: Moderate risk
- P/E > 100 or sustainability < 0.3: Emission-dependent, high risk

### Red Flags

- APY > 100% sourced primarily from emissions
- Emission token price declining consistently over 30+ days
- TVL declining while emission rate stays constant or increases
- Protocol revenue is a small fraction of emission cost
- No vesting or lockup on emission tokens

## Yield Comparison Framework

When comparing yield opportunities, normalize across these dimensions:

### 1. Same-Asset Basis

Compare like for like. For SOL:

| Strategy | Expected APR | Risk Level | IL Exposure |
|----------|-------------|------------|-------------|
| Native staking | ~7% | Low | None |
| Liquid staking (mSOL) | ~7.5% | Low | Minimal |
| SOL-USDC LP (Orca) | ~15-25% | Medium | High |
| SOL lending (Marginfi) | ~3-8% | Low-Med | None |
| Leveraged yield | ~20-50% | High | Varies |

### 2. Risk-Adjusted Yield

```python
risk_score = (
    il_risk * 0.3 +
    smart_contract_risk * 0.25 +
    emission_sustainability_risk * 0.2 +
    liquidity_risk * 0.15 +
    protocol_risk * 0.1
)

risk_adjusted_yield = net_apr / risk_score
```

### 3. Total Cost Accounting

Include all costs:
- Impermanent loss (see `impermanent-loss` skill)
- Gas fees for all transactions (deposit, withdraw, claim, compound)
- Opportunity cost (what you could earn risk-free)
- Smart contract risk premium
- Rebalancing costs (CLMM positions)

## Solana Yield Sources

### Liquidity Provision

| Protocol | Pool Types | Fee Tiers | Notes |
|----------|-----------|-----------|-------|
| Raydium | CPMM, CLMM | 0.01-1% | Largest Solana DEX by volume |
| Orca | CLMM (Whirlpool) | 0.01-2% | Concentrated liquidity focused |
| Meteora | DLMM, Dynamic | Variable | Dynamic fee adjustment |

### Lending

| Protocol | Assets | Typical APR | Notes |
|----------|--------|-------------|-------|
| Marginfi | SOL, USDC, etc. | 2-10% | Points program active |
| Kamino | SOL, USDC, etc. | 2-12% | Auto-compound vaults |
| Solend | SOL, USDC, etc. | 1-8% | Established protocol |

### Staking

| Method | APR | Lock Period | Notes |
|--------|-----|------------|-------|
| Native SOL staking | ~7% | 1 epoch (~2d) | Validator selection matters |
| mSOL (Marinade) | ~7.2% | Instant | Liquid, usable in DeFi |
| jitoSOL (Jito) | ~7.5% | Instant | Includes MEV rewards |
| bSOL (BlazeStake) | ~7% | Instant | Decentralized validator set |

## Data Sources

### DeFiLlama Yields API (Free, No Auth)

```python
import httpx

# All yield pools
pools = httpx.get("https://yields.llama.fi/pools").json()

# Filter for Solana
solana_pools = [p for p in pools["data"] if p["chain"] == "Solana"]

# Sort by TVL
solana_pools.sort(key=lambda p: p.get("tvlUsd", 0), reverse=True)
```

Response fields: `pool`, `chain`, `project`, `symbol`, `tvlUsd`, `apy`, `apyBase`, `apyReward`, `il7d`, `exposure`.

### Protocol-Specific APIs

- Raydium: `https://api-v3.raydium.io/pools/info/list`
- Orca: `https://api.mainnet.orca.so/v1/whirlpool/list`
- Marginfi: On-chain account data via Solana RPC

## Integration with Other Skills

- **`lp-math`**: AMM formulas for fee calculation and position math
- **`impermanent-loss`**: IL estimation for real yield calculation
- **`defillama-api`**: Fetching yield and TVL data across protocols
- **`risk-management`**: Portfolio-level yield allocation decisions
- **`position-sizing`**: How much capital to allocate to yield strategies

## Files

### References
- `references/yield_math.md` — Fee APR, APR/APY conversion, net yield formulas, break-even analysis
- `references/sustainability_analysis.md` — Emission sustainability metrics, death spiral patterns, real yield identification

### Scripts
- `scripts/yield_calculator.py` — Offline yield calculator with fee APR, IL estimation, net yield, break-even, and sensitivity analysis
- `scripts/yield_comparison.py` — Fetches DeFiLlama yield data and compares Solana yield opportunities with risk-adjusted ranking
