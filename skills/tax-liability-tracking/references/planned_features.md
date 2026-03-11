# Tax Liability Tracking — Planned Features & Methodology

## Feature Overview

### Core Tracking
- Per-trade tax lot creation with acquisition date, amount, per-unit cost basis
- Proportional cost basis allocation on partial sells
- FIFO, LIFO, and specific identification accounting methods
- Realized vs unrealized gain classification
- Short-term vs long-term gain classification with countdown timers

### Tax Projection
- Progressive federal bracket estimation
- Configurable state tax rate
- Quarterly estimated payment projection (Q1-Q4)
- Year-to-date cumulative liability tracking
- After-tax P&L view per position and aggregate

### Tax-Aware Signals
- Long-term threshold countdown per lot
- Profit-taking tax cost estimation
- Loss harvesting opportunity detection
- Timing value analysis (sell now vs wait N days)
- Wash sale proximity warning (30-day window)

### SOL/USD Conversion
- Historical SOL/USD price lookup at each event timestamp
- Token price in SOL converted to USD via SOL/USD rate
- All tax figures reported in USD per IRS requirements

---

## Proportional Cost Basis — Detailed Math

### The Rule

When selling a fraction of a position, cost basis is allocated proportionally:

```
sold_basis = (amount_sold / total_amount) * total_cost_basis
remaining_basis = total_cost_basis - sold_basis
```

This is equivalent to:

```
per_unit_basis = total_cost_basis / total_amount
sold_basis = amount_sold * per_unit_basis
remaining_basis = amount_remaining * per_unit_basis
```

### Worked Example 1 — House-Money Play

**Setup**: Buy 1,000 tokens at $1.00 each.

| Field | Value |
|---|---|
| Total amount | 1,000 |
| Per-unit basis | $1.00 |
| Total basis | $1,000.00 |

**Partial sell**: Sell 800 tokens at $1.25 each.

| Calculation | Value |
|---|---|
| Proceeds | 800 x $1.25 = $1,000.00 |
| Sold basis | 800 x $1.00 = $800.00 |
| Realized gain | $1,000.00 - $800.00 = **$200.00** |
| Remaining amount | 200 |
| Remaining basis | 200 x $1.00 = **$200.00** |

**Later sell**: Sell remaining 200 tokens at $2.00 each.

| Calculation | Value |
|---|---|
| Proceeds | 200 x $2.00 = $400.00 |
| Sold basis | 200 x $1.00 = $200.00 |
| Realized gain | $400.00 - $200.00 = **$200.00** |

**Total gain across both sells**: $200 + $200 = $400.

**Verification**: Total proceeds ($1,000 + $400 = $1,400) minus total basis ($1,000) = $400. Correct.

### Worked Example 2 — Multiple Accumulations

**Buy 1**: 500 tokens at $0.50 = $250 basis.
**Buy 2**: 300 tokens at $0.80 = $240 basis.
**Total**: 800 tokens, $490 total basis.

**Partial sell (FIFO)**: Sell 600 tokens at $1.00.

Under FIFO, the 600 sold tokens come from:
- Lot 1: 500 tokens at $0.50 = $250 basis
- Lot 2: 100 tokens at $0.80 = $80 basis
- Total sold basis = $330

| Calculation | Value |
|---|---|
| Proceeds | 600 x $1.00 = $600.00 |
| Sold basis (FIFO) | $250 + $80 = $330.00 |
| Realized gain | $600 - $330 = **$270.00** |
| Remaining | 200 tokens from Lot 2 |
| Remaining basis | 200 x $0.80 = **$160.00** |

### Worked Example 3 — Zero-Basis Misconception

**The wrong way** (do NOT do this):

Buy 1,000 at $1.00 ($1,000 basis). Sell 800 at $1.25 ($1,000 proceeds). "I recovered my capital, so remaining basis = $0."

This is **incorrect** because:
- It records $0 realized gain on the partial sell (understated by $200)
- It records $400 gain on the final sell of 200 tokens at $2.00 (overstated by $200)
- If the partial sell is in one tax year and the final sell in another, income shifts between years
- If the holding period crosses the 1-year boundary between sells, the gain classification changes

---

## Gain Classification Rules

### Holding Period Determination

- **Start date**: The date the tokens were acquired (trade settlement)
- **End date**: The date the tokens were disposed of
- **Short-term**: Holding period < 1 year (365 days)
- **Long-term**: Holding period >= 1 year

### Special Cases

**Token-to-token swaps**: Treated as two events — a sale of the source token and a purchase of the destination token. Both events use the USD value at the time of the swap.

**Wash sales**: If you sell at a loss and repurchase the same or "substantially identical" token within 30 days (before or after the sale), the loss may be disallowed. The disallowed loss is added to the basis of the repurchased tokens. Crypto wash sale rules are not yet codified in US tax law but may apply under proposed legislation.

**Airdrops and staking rewards**: Treated as ordinary income at fair market value when received. The FMV becomes the cost basis for future disposition.

---

## Quarterly Estimation Methodology

### US Estimated Tax Payments

Self-employed and high-income taxpayers must make quarterly estimated payments:

| Quarter | Period | Due Date |
|---|---|---|
| Q1 | Jan 1 — Mar 31 | April 15 |
| Q2 | Apr 1 — May 31 | June 15 |
| Q3 | Jun 1 — Aug 31 | September 15 |
| Q4 | Sep 1 — Dec 31 | January 15 (next year) |

### Estimation Formula

```
quarterly_liability = (realized_short_term_gains * short_term_rate
                     + realized_long_term_gains * long_term_rate
                     + state_gains * state_rate)
```

Where:
- `short_term_rate` = marginal federal income tax rate
- `long_term_rate` = 0%, 15%, or 20% based on total income
- `state_rate` = state income tax rate (varies by state, 0-13.3%)

### Safe Harbor Rule

To avoid underpayment penalties, pay the lesser of:
- 90% of current year tax liability, or
- 100% of prior year tax liability (110% if AGI > $150,000)

The tracker projects based on year-to-date realized gains annualized, then compares against safe harbor thresholds.

---

## Planned Enhancements

### Phase 1 (Current)
- Core proportional cost basis tracking
- FIFO accounting method
- Short-term / long-term classification
- Basic quarterly projection
- Tax-aware trading signals

### Phase 2
- LIFO and specific identification methods
- Wash sale detection and basis adjustment
- Multi-year tracking with carryover losses
- CSV/JSON import from exchange exports

### Phase 3
- Staking reward and airdrop income tracking
- DeFi yield as ordinary income events
- LP position entry/exit as taxable events
- Integration with Helius transaction history API

### Phase 4
- Form 8949 data export
- TurboTax/TaxAct import format
- CoinTracker/Koinly reconciliation
- Multi-jurisdiction support (UK, EU, AU)
