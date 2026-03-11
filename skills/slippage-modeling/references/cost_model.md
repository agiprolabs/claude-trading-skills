# Total Execution Cost Model

## Component Breakdown

Every trade on Solana DEXes incurs multiple cost components. Understanding each one is critical for accurate break-even analysis and position sizing.

### 1. Price Impact (AMM Slippage)

The largest and most variable cost. Depends on trade size relative to pool liquidity.

| Pool TVL   | 0.1 SOL | 1 SOL   | 10 SOL   | 50 SOL    |
|-----------|---------|---------|----------|-----------|
| $1M+      | <1 bps  | 1-5 bps | 5-50 bps | 50-200 bps|
| $100K     | 1-5 bps | 10-50 bps| 100-500 bps| 500+ bps |
| $10K      | 5-50 bps| 50-500 bps| Often unfeasible | — |
| <$5K      | 50+ bps | 500+ bps | —        | —         |

### 2. DEX Swap Fees

Fees are taken from the input amount before the swap executes.

| Protocol     | Fee Rate | Basis Points | Notes                        |
|-------------|----------|-------------|------------------------------|
| Raydium AMM | 0.25%    | 25 bps      | Standard constant-product     |
| Raydium CLMM| 0.01-1%  | 1-100 bps   | Varies by pool fee tier       |
| Orca Whirlpool| 0.01-1%| 1-100 bps   | Fee tiers: 1, 4, 8, 64, 128 bps|
| Meteora DLMM| 0.1-2%   | 10-200 bps  | Dynamic fees increase with volatility|
| PumpFun     | 1.0%     | 100 bps     | Bonding curve phase           |

Jupiter typically selects the lowest-fee route automatically.

### 3. Solana Base Transaction Fee

- Base fee: 5000 lamports = 0.000005 SOL
- Cost in bps: For a 1 SOL trade, this is 0.0005 bps — completely negligible
- This is the only guaranteed fixed cost

### 4. Priority Fee (Compute Unit Price)

Required for timely inclusion during congestion or competitive trading.

| Scenario           | Priority Fee    | For 1 SOL Trade |
|-------------------|----------------|-----------------|
| Low congestion    | 0.0001 SOL     | 1 bps           |
| Normal            | 0.001 SOL      | 10 bps          |
| High congestion   | 0.005-0.01 SOL | 50-100 bps      |
| Extreme/sniping   | 0.05-0.5 SOL   | 500-5000 bps    |

Priority fees are fixed per transaction, so they have **higher bps impact on smaller trades**.

### 5. MEV Cost (Sandwich Attacks)

Estimated additional cost from MEV extraction. Not guaranteed to occur, but should be budgeted for high-value trades.

**Risk factors**:
- Trade size > 5 SOL on thin pools: high risk
- Slippage tolerance > 5%: high risk
- Popular meme tokens during launch: very high risk
- Blue chip tokens with deep liquidity: low risk

**Estimated MEV cost**:

| Risk Level | Estimated Cost | When                              |
|-----------|---------------|-----------------------------------|
| Negligible | 0 bps         | Small trades, deep liquidity       |
| Low        | 5-20 bps      | Medium trades, good liquidity      |
| Medium     | 20-100 bps    | Large trades on mid-cap tokens     |
| High       | 100-500 bps   | Large trades on thin/hyped tokens  |

**Mitigation**: Use Jupiter's exact-out mode, set tight slippage tolerance, use Jito bundles for MEV protection.

## Total Cost Formula

```
total_bps = impact_bps + fee_bps + priority_bps + mev_bps
total_sol = trade_size_sol * total_bps / 10_000
```

### Example: Buy 5 SOL of a Mid-Cap Token ($500K TVL Pool)

| Component     | Estimate   |
|--------------|-----------|
| Price impact  | 80 bps    |
| DEX fee       | 25 bps    |
| Priority fee  | 10 bps    |
| MEV risk      | 20 bps    |
| **Total**     | **135 bps** |
| **Cost in SOL** | **0.0675 SOL** |

## Break-Even Analysis

### Roundtrip Cost

A complete trade (entry + exit) incurs costs twice:

```
roundtrip_bps = entry_impact + exit_impact + 2 * fee_bps + 2 * priority_bps + mev_bps
```

Note: Exit slippage may differ from entry because:
- Pool liquidity may have changed
- Selling into a pool you bought from has the same reserves minus your tokens
- Market conditions and priority fees may differ

### Conservative Roundtrip Estimates

| Token Category | Entry Cost | Exit Cost | Roundtrip | Min Move to Profit |
|---------------|-----------|----------|-----------|-------------------|
| Blue chip      | 30 bps    | 30 bps   | 60 bps    | 0.6%              |
| Mid-cap        | 135 bps   | 150 bps  | 285 bps   | 2.85%             |
| Small-cap      | 300 bps   | 400 bps  | 700 bps   | 7.0%              |
| Micro/PumpFun  | 800 bps   | 1200 bps | 2000 bps  | 20%               |

### Required Return Calculation

```
required_return = roundtrip_cost_bps / (10_000 - roundtrip_cost_bps)
```

For 285 bps roundtrip: `285 / 9715 = 2.93%` actual price move needed.

### Risk-Adjusted Analysis

Factor in win rate to determine if execution costs make a strategy viable:

```
expected_pnl = win_rate * avg_win - (1 - win_rate) * avg_loss - roundtrip_cost
```

If roundtrip cost is 285 bps per trade and you make 100 trades per month:
- Monthly execution cost: 28,500 bps equivalent
- With 1 SOL average position: 2.85 SOL/month in execution costs alone

## When Costs Make a Trade Unprofitable

Rules of thumb for whether execution costs are prohibitive:

1. **Roundtrip cost > 5% of trade value**: Only trade if expecting 10%+ move
2. **Slippage > expected daily range**: The token cannot reasonably move enough to cover costs in your timeframe
3. **Priority fee > 10% of expected profit**: Reduce urgency or wait for lower congestion
4. **MEV risk is "high"**: Use MEV protection (Jito bundles) or reduce trade size

## Cost Optimization Strategies

### Reduce Price Impact
- Split large orders into tranches (see SKILL.md on multi-tranche execution)
- Trade during high-liquidity hours (US market hours for Solana)
- Use limit orders when available (Jupiter DCA or limit order program)

### Reduce Fees
- Jupiter automatically routes to lowest-fee pools
- Raydium CLMM 1 bps fee tier pools exist for major pairs
- Avoid PumpFun bonding curve when Raydium pool exists

### Reduce Priority Fees
- Avoid trading during network congestion spikes
- Use dynamic priority fee estimation (query recent slot leaders)
- Accept slightly longer confirmation times for non-urgent trades

### Reduce MEV Exposure
- Set slippage tolerance as tight as possible (1-3% for liquid tokens)
- Use Jito bundles for MEV-protected execution
- Trade smaller sizes (not worth sandwiching)
- Avoid mempool-visible transactions where possible
