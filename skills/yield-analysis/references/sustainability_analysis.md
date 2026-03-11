# Sustainability Analysis — Evaluating DeFi Yield Durability

## Protocol Revenue vs Emissions

Every DeFi protocol that pays yield through token emissions faces a fundamental question: can the protocol generate enough real revenue to justify its token's value?

### Revenue Sources

- **Trading fees**: Protocol's share of swap fees (e.g., Raydium takes a cut of LP fees)
- **Lending spread**: Difference between borrow and lend rates
- **Liquidation fees**: Earned when undercollateralized positions are liquidated
- **Protocol-owned liquidity (POL)**: Yield from the protocol's own LP positions
- **Treasury yield**: Interest on treasury holdings

### Emission Costs

- **LP incentives**: Tokens distributed to liquidity providers
- **Staking rewards**: Tokens for governance stakers
- **Referral/growth programs**: Tokens for user acquisition
- **Team/investor unlocks**: Vesting schedules adding supply

### The Core Equation

```
sustainable = (annual_protocol_revenue >= annual_emission_cost_usd)
```

When revenue exceeds emission costs, the protocol can sustain its yield without diluting token holders. When emissions exceed revenue, the protocol is paying for growth with inflation.

## The Yield Farming Death Spiral

### Phase 1: Launch (Weeks 1-4)
- Protocol announces high emission rewards (200%+ APY)
- Capital floods in seeking yield
- TVL grows rapidly
- Token price rises on hype and buying pressure from yield seekers

### Phase 2: Peak (Weeks 4-12)
- TVL stabilizes at high level
- Yield per LP drops as more capital enters
- Early farmers begin selling emission tokens
- Token price plateaus

### Phase 3: Decline (Weeks 12-26)
- Farmers sell emission tokens → price drops
- Lower token price → lower USD yield
- LPs start leaving → TVL drops
- Protocol may increase emissions to retain LPs → more sell pressure
- Remaining LPs earn less and face higher IL from declining token

### Phase 4: Collapse or Stabilization
- **Collapse**: TVL drops 90%+, token price drops 95%+, protocol becomes ghost chain
- **Stabilization**: Revenue-generating protocols find equilibrium where real fees sustain modest yield

### Key Observation

The difference between collapse and stabilization is whether the protocol generates real trading volume and fees independent of emission incentives. Protocols with genuine product-market fit (Raydium, Orca) stabilize. Pure yield farms collapse.

## Sustainability Metrics

### Protocol P/E Ratio

```
pe_ratio = fully_diluted_valuation / annual_protocol_revenue
```

| P/E Range | Interpretation |
|-----------|---------------|
| < 10 | Strong value — revenue well supports valuation |
| 10-30 | Healthy — typical for established DeFi |
| 30-100 | Growth premium — market expects revenue growth |
| 100-500 | Speculative — valuation not supported by current revenue |
| > 500 | Extremely speculative — almost entirely narrative-driven |

### Revenue-to-Emission Ratio

```
rev_emission_ratio = annual_revenue / annual_emission_value_usd
```

| Ratio | Interpretation |
|-------|---------------|
| > 1.0 | Sustainable — revenue covers emissions |
| 0.5-1.0 | Approaching sustainability |
| 0.1-0.5 | Emission-dependent — moderate risk |
| < 0.1 | Highly unsustainable — yield is almost entirely inflationary |

### Emission Sell Pressure

```
daily_sell_pressure = daily_emissions_usd / daily_token_volume
```

| Sell Pressure | Interpretation |
|--------------|---------------|
| < 1% | Minimal impact on token price |
| 1-5% | Noticeable but manageable |
| 5-15% | Significant downward pressure |
| > 15% | Severe — token likely in decline |

### TVL Retention Rate

```
tvl_retention_30d = current_tvl / tvl_30d_ago
```

Values below 0.8 (20% TVL loss in 30 days) signal potential death spiral.

## Real Yield vs Inflationary Yield

### Real Yield Protocols

Yield comes from actual economic activity:
- **DEX fees**: Traders pay to swap tokens — LPs earn from real demand
- **Lending interest**: Borrowers pay interest — lenders earn from real demand
- **Staking rewards**: Network inflation distributed to validators/delegators (predictable, protocol-level)
- **MEV sharing**: Jito shares MEV revenue with jitoSOL holders

### Inflationary Yield

Yield comes from new token creation:
- **Farm rewards**: Protocol mints tokens and distributes them
- **Points programs**: Promise of future token airdrop (deferred inflation)
- **Governance staking rewards**: Staking rewards funded by token inflation

### How to Identify Real Yield

```python
def is_real_yield(pool: dict) -> bool:
    """Check if a pool's yield is primarily from real sources.

    Args:
        pool: Pool data with apyBase and apyReward fields.

    Returns:
        True if base (fee) APY exceeds reward (emission) APY.
    """
    base_apy = pool.get("apyBase", 0) or 0
    reward_apy = pool.get("apyReward", 0) or 0
    total = base_apy + reward_apy
    if total == 0:
        return False
    return base_apy / total > 0.5
```

DeFiLlama separates `apyBase` (real, from fees) and `apyReward` (from emissions), making this check straightforward.

## Red Flags Checklist

### High Risk Indicators

- [ ] APY > 100% with majority from emissions
- [ ] Emission token price down > 30% in 30 days
- [ ] TVL declining while emissions stay constant
- [ ] Protocol revenue < 10% of emission cost
- [ ] No token vesting — all emissions immediately sellable
- [ ] Team allocation > 30% of total supply
- [ ] Emission schedule increases over time (not decreasing)
- [ ] No working product beyond yield farm
- [ ] Anonymous team with no track record
- [ ] Forked code with minimal changes

### Moderate Risk Indicators

- [ ] APY 50-100% with mixed fee/emission sources
- [ ] Emission token price stable but flat
- [ ] TVL stable but not growing
- [ ] Protocol revenue covers 30-80% of emissions
- [ ] Some token vesting (3-12 month)

### Low Risk Indicators

- [ ] APY < 30% primarily from fees
- [ ] Established protocol (6+ months, audited)
- [ ] Growing or stable TVL
- [ ] Revenue exceeds emissions
- [ ] Long vesting schedules for team tokens
- [ ] Multiple audits from reputable firms

## Historical Patterns

### Common Yield Farming Collapse Patterns

**Pattern 1: The Vampire Attack Fade**
- Protocol launches by offering higher yields than competitors
- Attracts TVL initially
- Cannot sustain yields without real product differentiation
- TVL leaves when emissions drop

**Pattern 2: The Governance Token Illusion**
- Protocol distributes governance token with no revenue sharing
- Token has voting power but no cash flow
- Market initially values governance, then realizes it is worthless
- Token price trends to zero, yield trends to zero

**Pattern 3: The Leverage Spiral**
- Protocol enables leveraged yield farming
- Users borrow to farm, multiplying apparent TVL
- Market downturn triggers cascading liquidations
- TVL collapses 80%+ in days

### Solana-Specific Examples

Solana's low transaction costs enable more frequent compounding and rebalancing, which amplifies both the benefits and risks of yield strategies. Protocols that survived the 2022-2023 bear market (Raydium, Orca, Marinade) proved their revenue models. Newer protocols should be evaluated more skeptically until they demonstrate sustainable revenue.

## Evaluation Framework

When assessing any yield opportunity:

1. **Decompose**: What percentage comes from fees vs emissions?
2. **Validate**: Is the fee APR consistent with actual trading volume?
3. **Project**: If emission token drops 50%, is the yield still attractive?
4. **Compare**: Does the risk-adjusted yield beat SOL staking (7%)?
5. **Monitor**: Set alerts for TVL changes, emission token price, volume trends

```python
def yield_sustainability_score(
    fee_pct: float,
    rev_emission_ratio: float,
    tvl_retention_30d: float,
    token_price_change_30d: float,
) -> float:
    """Score yield sustainability from 0 (unsustainable) to 100 (sustainable).

    Args:
        fee_pct: Fraction of yield from fees (0-1).
        rev_emission_ratio: Protocol revenue / emission cost.
        tvl_retention_30d: Current TVL / TVL 30 days ago.
        token_price_change_30d: Price change ratio (e.g. 0.8 = down 20%).

    Returns:
        Sustainability score 0-100.
    """
    score = 0.0
    score += min(fee_pct, 1.0) * 35          # Max 35 for 100% fee-based
    score += min(rev_emission_ratio, 1.0) * 25 # Max 25 for revenue-backed
    score += min(tvl_retention_30d, 1.2) / 1.2 * 20  # Max 20 for stable TVL
    price_factor = max(min(token_price_change_30d, 1.5), 0) / 1.5
    score += price_factor * 20                 # Max 20 for stable/rising token
    return round(score, 1)
```
