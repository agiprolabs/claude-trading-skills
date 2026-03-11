# Tax-Loss Harvesting — Planned Features Reference

## TLH Mechanics

Tax-loss harvesting (TLH) converts unrealized portfolio losses into realized losses that offset taxable gains. The core loop:

1. **Scan** — Identify positions where `current_value < cost_basis`.
2. **Score** — Rank each opportunity by a composite metric (see Scoring Formula below).
3. **Filter** — Exclude opportunities where net benefit is negative or wash sale risk is too high.
4. **Plan** — Generate sell orders with quantities, expected proceeds, and re-entry dates.
5. **Execute** — Sell the position (outside this skill's scope — see `jupiter-swap` or `dex-execution`).
6. **Track** — Record the realized loss, update carryforward, set wash sale window alerts.

### Lot-Level Tracking

When a position was acquired across multiple purchases ("lots"), each lot has its own cost basis and acquisition date. TLH should evaluate lots independently because:
- Some lots may have gains while others have losses.
- Lot-level selection (specific identification) lets you harvest only the losing lots.
- FIFO, LIFO, and specific identification methods produce different tax outcomes.

### Realized vs Unrealized

| Term | Definition |
|------|-----------|
| Unrealized loss | Paper loss — position held, not yet sold |
| Realized loss | Loss locked in by selling the position |
| Harvested loss | Realized loss intentionally created for tax purposes |

Only realized losses can offset gains on a tax return.

## Scoring Formula

The composite TLH score ranks opportunities on four equally-weighted-by-default dimensions, each normalized to [0, 1]:

### Magnitude Score

```
magnitude = min(abs(unrealized_loss) / reference_amount, 1.0)
```

`reference_amount` defaults to $10,000 but should scale with portfolio size. A $500 loss in a $10K portfolio is significant; in a $1M portfolio it is noise.

### Urgency Score

```
urgency = max(0, 1.0 - days_to_long_term / 365)
```

A position 10 days from crossing into long-term territory scores 0.97 urgency. One purchased yesterday scores near 0. This reflects the fact that short-term losses offset higher-taxed short-term gains.

### Wash Safety Score

```
wash_safety = 1.0 - wash_sale_risk
```

Where `wash_sale_risk` is:
- `1.0` — Same-token re-entry planned within 30 days.
- `0.5–0.9` — Highly correlated substitute held or planned.
- `0.0` — No re-entry or uncorrelated substitute.

### Offset Match Score

```
offset_match = min(1.0, available_matching_gains / abs(unrealized_loss))
```

A loss of $5,000 with $5,000 in matching gains scores 1.0. A loss of $5,000 with only $1,000 in matching gains scores 0.2. Losses beyond available gains still have value (up to $3K deduction + carryforward), but immediate benefit is lower.

### Composite

```
score = w_mag * magnitude + w_urg * urgency + w_wash * wash_safety + w_off * offset_match
```

Default weights: `{magnitude: 0.35, urgency: 0.25, wash_safety: 0.20, offset_match: 0.20}`.

Adjust weights based on context:
- **Year-end rush**: Increase urgency weight.
- **High wash sale environment**: Increase wash_safety weight.
- **Large realized gains**: Increase offset_match weight.

## Wash Sale Interaction

### The 61-Day Window

A wash sale is triggered when a taxpayer sells a security at a loss and, within **30 days before or after** the sale, acquires a "substantially identical" security.

```
wash_sale_window_start = sale_date - 30 days
wash_sale_window_end   = sale_date + 30 days
```

### Consequences of Triggering a Wash Sale

The loss is **disallowed** for the current tax year. However:
- The disallowed loss is **added to the cost basis** of the replacement shares.
- The holding period of the replacement shares includes the holding period of the original shares.
- The loss is deferred, not permanently lost.

### Planning Around Wash Sales

**Before selling** — Check if you purchased the same token within the prior 30 days. If so, that purchase triggers a retroactive wash sale on the planned harvest.

**After selling** — Set a 31-day calendar reminder before re-entering the position. Any purchase of the same token within 30 days disallows the loss.

**Substitute positions** — If you want continuous market exposure, buy a different but correlated token. For Solana tokens, consider:
- Selling SOL and buying a SOL-correlated token (e.g., JTO, BONK) — generally not "substantially identical."
- Selling one memecoin and buying another in the same sector — generally safe.
- Selling a wrapped token and buying the unwrapped version — potentially risky, may be considered identical.

## Carryforward Rules

### Annual Deduction Limit

Net capital losses exceeding net capital gains may offset up to **$3,000** of ordinary income per year ($1,500 for married filing separately).

### Carryforward Mechanics

Excess losses carry forward **indefinitely** to future tax years. The carryforward retains its character (short-term or long-term) in most cases.

**Year-by-year tracking example:**

| Year | Realized Gains | Realized Losses | Net | Deduction Used | Carryforward |
|------|---------------|----------------|-----|---------------|-------------|
| 2025 | $5,000 | -$15,000 | -$10,000 | $3,000 | $7,000 |
| 2026 | $8,000 | -$2,000 | -$1,000* | $1,000 | $0 |

*Year 2026 net = $8,000 - $2,000 - $7,000 (carryforward) = -$1,000.

### Order of Application

1. Short-term losses offset short-term gains.
2. Long-term losses offset long-term gains.
3. Net short-term loss offsets net long-term gain (and vice versa).
4. Remaining net loss up to $3,000 offsets ordinary income.
5. Excess carries forward.

## Year-End Strategies

### Strategy 1: Gain-Matching Harvest

Identify all realized gains for the year. Harvest losses equal to those gains to zero out the tax liability. Stop harvesting once gains are fully offset plus the $3K ordinary income deduction.

### Strategy 2: Aggressive Harvest

Harvest every available loss regardless of current gains. Benefits:
- Builds a large carryforward for future years.
- Useful if you expect large gains next year.

Drawbacks:
- Transaction costs on many small positions.
- Opportunity cost of being out of positions for 31 days.

### Strategy 3: Threshold Harvest

Set a minimum loss threshold (e.g., $500 or 10% of position value). Only harvest losses exceeding the threshold to balance tax savings against complexity.

### Strategy 4: Continuous Harvest

Monitor positions throughout the year rather than waiting for year-end. Benefits:
- Captures losses that may recover by December.
- Spreads transaction costs over time.
- Avoids year-end liquidity crunches.

### Year-End Checklist

1. Tally all realized gains and losses year-to-date.
2. Apply any prior-year carryforward.
3. Compute remaining taxable gain.
4. Scan portfolio for unrealized losses.
5. Score and rank harvesting opportunities.
6. Filter by net benefit > 0.
7. Check wash sale windows for recent purchases.
8. Execute harvests with enough time for settlement before Dec 31.
9. Set 31-day reminders for re-entry eligibility.
10. Update carryforward tracker for next year.

## Crypto-Specific Notes

- **IRS Notice 2014-21** treats cryptocurrency as property, subject to capital gains rules.
- The wash sale rule (IRC Section 1091) technically applies to "stock or securities." Whether crypto qualifies is debated, but proposed legislation (e.g., Build Back Better Act) aimed to extend it explicitly to digital assets.
- **Conservative approach**: Treat crypto as subject to wash sales.
- **Aggressive approach**: Argue crypto is not a "security" and wash sales do not apply. This carries audit risk.
- **Cost basis methods**: FIFO is the IRS default; specific identification requires contemporaneous records.
- **Staking rewards**: Received tokens have a cost basis equal to fair market value at time of receipt. These can also generate TLH opportunities if value drops.
