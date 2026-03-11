# Wash Sale Detection — Rules, Mechanics, and Planned Features

## IRS Wash Sale Rule — IRC Section 1091

### Statutory Foundation

The wash sale rule was originally enacted in 1921 to prevent taxpayers from claiming artificial tax losses by selling securities at a loss and immediately repurchasing them. The rule was codified as **Internal Revenue Code Section 1091**.

Prior to 2025, cryptocurrency was classified as "property" (IRS Notice 2014-21) and was explicitly **excluded** from wash sale treatment. The **Infrastructure Investment and Jobs Act** (signed November 2021) and subsequent IRS rulemaking extended the definition of covered assets to include "specified digital assets" effective **January 1, 2025**.

### What Triggers a Wash Sale

A wash sale occurs when ALL of the following conditions are met:

1. A taxpayer disposes of a digital asset at a **realized loss**
2. Within the **61-day window** (30 days before through 30 days after the sale), the taxpayer acquires a **substantially identical** digital asset
3. The acquisition is by **purchase**, receipt as compensation, or through a contract or option

### What Does NOT Trigger a Wash Sale

- Selling at a **gain** — wash sale rules only apply to losses
- Buying a **different** token after selling at a loss (SOL loss, then buying ETH)
- Repurchasing the same token **after 30 calendar days** have elapsed
- Gifting the asset (though gift tax rules may apply separately)

## 61-Day Window Mechanics

### Calendar Day Counting

The 61-day window uses **calendar days**, not trading days or business days.

```
Example: Sale on March 15, 2025

Pre-sale window:  Feb 13, 2025 — Mar 14, 2025  (30 calendar days)
Sale day:         Mar 15, 2025                  (Day 0)
Post-sale window: Mar 16, 2025 — Apr 14, 2025   (30 calendar days)

Total window:     Feb 13, 2025 — Apr 14, 2025   (61 calendar days)
```

### Retroactive Triggering

A wash sale can be triggered **retroactively**. If you buy a token on March 1 and then sell the same token at a loss on March 20, the March 1 purchase falls within the 30-day pre-sale window. The loss is disallowed.

### Multiple Sales and Purchases

When multiple purchases fall within the wash sale window of a single loss-generating sale, the wash sale rule applies to purchases in **chronological order** up to the quantity of the loss sale.

```
Mar 1:  Buy 50 SOL @ $100
Mar 15: Sell 100 SOL @ $80 (loss of $2,000)
Mar 20: Buy 30 SOL @ $85
Mar 25: Buy 40 SOL @ $82
Apr 1:  Buy 50 SOL @ $90

Wash sales:
  Mar 20 purchase: 30 SOL matched → $600 disallowed
  Mar 25 purchase: 40 SOL matched → $800 disallowed
  Total matched: 70 of 100 SOL → $1,400 of $2,000 disallowed
  Remaining deductible loss: $600 (for the unmatched 30 SOL)
  Apr 1 purchase: outside window (Day 17 is within window — recalculate)
```

Important: count days carefully. April 1 is Day 17 after March 15, still within the 30-day window. All 100 SOL would be matched in this example.

### Partial Quantity Matching

If you sell 100 tokens at a loss but only repurchase 60 within the window:
- 60 tokens' worth of loss is disallowed (proportional)
- 40 tokens' worth of loss is deductible
- The disallowed amount is added to the basis of the 60 replacement tokens

## Basis Adjustment Examples

### Simple Case

```
Jan 10: Buy 10 SOL @ $200  (basis: $2,000)
Feb 5:  Sell 10 SOL @ $150 (proceeds: $1,500, loss: $500)
Feb 20: Buy 10 SOL @ $160  (basis before adj: $1,600)

Wash sale: $500 loss disallowed
Adjusted basis: $1,600 + $500 = $2,100
Per-unit adjusted basis: $210 (not $160)
```

### Partial Match Case

```
Jan 10: Buy 100 SOL @ $200  (basis: $20,000)
Feb 5:  Sell 100 SOL @ $150 (proceeds: $15,000, loss: $5,000)
Feb 20: Buy 40 SOL @ $160   (basis before adj: $6,400)

Wash sale on 40 of 100 SOL:
  Disallowed loss: $5,000 * (40/100) = $2,000
  Deductible loss: $5,000 - $2,000 = $3,000
  Adjusted basis of 40 new SOL: $6,400 + $2,000 = $8,400
  Per-unit adjusted basis: $210 per SOL
```

### Chained Wash Sales

A wash sale can chain: if the replacement position is also sold at a loss and repurchased within 30 days, the accumulated disallowed losses carry forward.

```
Jan 10: Buy 10 SOL @ $200  (basis: $2,000)
Feb 1:  Sell 10 SOL @ $150 (loss: $500 → disallowed)
Feb 15: Buy 10 SOL @ $155  (adj basis: $1,550 + $500 = $2,050)
Mar 1:  Sell 10 SOL @ $140 (loss: $2,050 - $1,400 = $650 → disallowed)
Mar 15: Buy 10 SOL @ $145  (adj basis: $1,450 + $650 = $2,100)

After two chained wash sales, the new position carries $1,150
of accumulated disallowed losses in its adjusted basis.
```

## Automation Edge Cases

### DCA Bot Hazard

A DCA bot buying SOL every week creates a near-guaranteed wash sale scenario if SOL is ever sold at a loss:

```
Weekly DCA: Buy 1 SOL every Monday
Mar 3:  Buy 1 SOL @ $180
Mar 10: Buy 1 SOL @ $170
Mar 17: Sell 5 SOL @ $160 (loss)
Mar 24: Buy 1 SOL @ $155  ← Wash sale (Day +7)
Mar 31: Buy 1 SOL @ $150  ← Wash sale (Day +14)

The DCA bot must be paused for 31 days after any loss-generating sale
to avoid wash sales on that token.
```

### Copy-Trading Systems

Copy-trade bots replicate a leader's trades. If the leader sells at a loss and re-enters within 30 days, all copiers inherit the wash sale. The copier has no defense — the rule applies regardless of intent or automation.

**Mitigation**: Filter copy-trade signals to suppress re-entry buys for tokens with active wash sale windows.

### Grid Bot Hazard

Grid bots place buy and sell orders at fixed intervals. They frequently sell and rebuy the same token within minutes. Every loss-generating sell followed by a grid buy is a wash sale.

**Mitigation**: Grid bots on tokens expected to be volatile should account for wash sale costs in profitability calculations.

### Multi-Exchange / Multi-Wallet

The wash sale rule applies to the **taxpayer**, not to individual accounts. A sale on Exchange A and a purchase on Exchange B within the window is a wash sale. This includes:
- Multiple CEX accounts
- DEX wallets
- Custodial vs self-custody
- Spouse's accounts (for joint filers)

## IRS Guidance References

| Source | Key Point |
|--------|-----------|
| IRC § 1091 | Statutory wash sale rule |
| IRS Notice 2014-21 | Crypto treated as property |
| Infrastructure Investment and Jobs Act (2021) | Extended reporting and wash sale rules to digital assets |
| IRC § 6045 (amended) | Broker reporting requirements for digital assets |
| IRS Publication 550 | Investment income and expenses, wash sale details |
| Rev. Rul. 2019-24 | Hard forks and airdrops treatment |

### Effective Dates

- **January 1, 2025**: Wash sale rule applies to digital assets
- **January 1, 2025**: Broker reporting (Form 1099-DA) requirements begin phased rollout
- **January 1, 2026**: Full cost basis reporting by brokers mandatory

### Open Questions in IRS Guidance

As of early 2025, the IRS has not issued definitive guidance on several crypto-specific questions:

1. Are wrapped tokens (wSOL) "substantially identical" to the unwrapped token (SOL)?
2. Are cross-chain versions of the same token (USDC on Solana vs Ethereum) substantially identical?
3. Are liquid staking derivatives (stSOL, mSOL, jitoSOL) substantially identical to SOL?
4. How do LP tokens interact with wash sale rules when the LP contains the sold token?
5. Does staking/unstaking constitute a disposition for wash sale purposes?

**Conservative approach**: Treat all of the above as substantially identical until IRS clarifies otherwise.

## Planned Scanner Features

- [ ] CSV and JSON trade history import
- [ ] Multi-token parallel scanning
- [ ] Partial quantity matching with proportional loss allocation
- [ ] Chained wash sale detection across sequential trades
- [ ] Multi-account aggregation from combined exports
- [ ] Integration with exchange API exports (Coinbase, Kraken, Binance)
- [ ] Holding period carryover tracking
- [ ] Tax-loss harvesting coordination with substitute asset suggestions
- [ ] Real-time pre-trade wash sale warning
- [ ] Annual tax summary report generation
