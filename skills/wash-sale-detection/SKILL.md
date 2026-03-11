---
name: wash-sale-detection
description: Wash sale detection under 2025 US crypto rules with 61-day window monitoring, disallowed loss tracking, and safe re-entry countdown
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Wash Sale Detection

Detect wash sales under current US crypto tax rules (effective 2025), monitor the 61-day window around realized losses, track disallowed losses with basis adjustments, and compute safe re-entry countdowns.

> **Disclaimer**: This skill provides informational analysis only. It is NOT tax advice. Consult a qualified tax professional or CPA for guidance on your specific situation. Tax law is complex, and the application of wash sale rules to cryptocurrency may vary based on individual circumstances, IRS guidance updates, and court rulings.

## Background

Before 2025, cryptocurrency was not subject to the wash sale rule because digital assets were classified as property rather than securities. The **Infrastructure Investment and Jobs Act** and subsequent IRS rulemaking extended wash sale treatment to digital assets beginning January 1, 2025.

Under **IRC Section 1091** (as amended for digital assets), if you sell or dispose of a cryptocurrency at a loss and acquire a **substantially identical** asset within a **61-day window** (30 days before the sale through 30 days after), the loss is **disallowed** for tax purposes. The disallowed loss is added to the cost basis of the replacement position.

## Key Concepts

### The 61-Day Window

```
Day -30 ................. Day 0 ................. Day +30
  |--- 30 days before ---|--- sale day ---|--- 30 days after ---|
  ^                       ^                                      ^
  Window opens        Loss realized                    Window closes
```

- **Day 0**: The day you sell a position at a realized loss
- **Days -30 to -1**: Purchases in this range trigger a wash sale retroactively
- **Days +1 to +30**: Purchases in this range trigger a wash sale prospectively
- The window is **calendar days**, not trading days

### Substantially Identical Assets

For crypto, "substantially identical" generally means the **same token**. Selling SOL at a loss and buying SOL within 30 days is a wash sale. Selling SOL and buying ETH is not (they are different assets).

Edge cases that may be scrutinized:
- Wrapped vs unwrapped versions of the same token (e.g., SOL vs wSOL)
- Tokens across different chains (e.g., USDC on Solana vs USDC on Ethereum)
- Derivative tokens that track the same underlying (e.g., stSOL and SOL)

### Disallowed Loss and Basis Adjustment

When a wash sale occurs:
1. The realized loss is **disallowed** — you cannot deduct it in the current tax year
2. The disallowed loss is **added to the cost basis** of the replacement position
3. The holding period of the original position may carry over to the replacement

**Example**:
- Buy 10 SOL at $100 each (cost basis: $1,000)
- Sell 10 SOL at $80 each (proceeds: $800, loss: $200)
- Buy 10 SOL at $85 within 15 days (wash sale triggered)
- New cost basis: $850 + $200 disallowed loss = **$1,050**
- The $200 loss is not gone — it is deferred into the new position

## Prerequisites

- Python 3.10+
- No external dependencies required (standard library only)
- Trade history data in CSV or structured format with: date, action (buy/sell), token, quantity, price, proceeds, cost basis

## Capabilities

1. **Wash Sale Scanning** — Analyze a trade history and flag all wash sale violations
2. **61-Day Window Monitoring** — Track open windows for recent loss-generating sales
3. **Disallowed Loss Calculation** — Compute the exact disallowed amount per wash sale
4. **Basis Adjustment Tracking** — Show adjusted cost basis for replacement positions
5. **Safe Re-Entry Countdown** — For each token sold at a loss, show days remaining until safe to re-enter
6. **Automation Hazard Detection** — Flag copy-trade systems or bot strategies that may inadvertently trigger wash sales

## Quick Start

```python
from datetime import date

# Define your trade history
trades = [
    {"date": date(2025, 3, 1), "action": "buy",  "token": "SOL", "qty": 10, "price": 100.0},
    {"date": date(2025, 3, 15), "action": "sell", "token": "SOL", "qty": 10, "price": 80.0},
    {"date": date(2025, 3, 25), "action": "buy",  "token": "SOL", "qty": 10, "price": 85.0},
]

# Check for wash sales
from scripts.wash_sale_scanner import WashSaleScanner

scanner = WashSaleScanner(trades)
results = scanner.scan()

for ws in results.wash_sales:
    print(f"WASH SALE: {ws.token} — Loss ${ws.disallowed_loss:.2f} disallowed")
    print(f"  Sale: {ws.sale_date} | Re-entry: {ws.replacement_date}")
    print(f"  Adjusted basis: ${ws.adjusted_basis:.2f}")

# Check safe re-entry countdowns
for countdown in results.countdowns:
    print(f"{countdown.token}: {countdown.days_remaining} days until safe re-entry")
```

## Use Cases

### 1. End-of-Year Tax Review

Scan your full year of trading activity to identify all wash sales before filing taxes. Generate a report showing total disallowed losses and adjusted cost bases.

### 2. Real-Time Monitoring

Before placing a buy order, check whether the token has an open wash sale window from a recent loss. Avoid inadvertent wash sales by waiting for the countdown to expire.

### 3. Copy-Trade and Bot Audit

Automated trading systems (copy-trading bots, DCA bots, grid bots) frequently trigger wash sales because they buy and sell the same tokens repeatedly. Run this scanner on bot trade exports to quantify the tax impact.

### 4. Tax-Loss Harvesting Coordination

When executing a tax-loss harvesting strategy, use the safe re-entry countdown to plan when you can re-enter positions. Swap into a non-identical asset during the 30-day window if you want to maintain market exposure.

### 5. Multi-Account Wash Sale Detection

The wash sale rule applies across all accounts controlled by the same taxpayer. If you trade SOL on multiple exchanges or wallets, aggregate the trade history before scanning.

## Edge Cases and Automation Hazards

### DCA Bots and Grid Bots

Dollar-cost averaging bots that buy a token weekly will almost certainly trigger wash sales if the token is also sold at a loss during the same period. The scanner flags overlapping buy/sell patterns within the 61-day window.

### Copy-Trading

If a copy-trade system sells a token at a loss and the leader re-enters within 30 days, your copied trades inherit the wash sale. There is no "I didn't place the trade" exception.

### Partial Fills and Multiple Lots

When a sale at a loss is followed by multiple smaller purchases, the wash sale applies to each purchase up to the quantity of the loss-generating sale. The scanner handles partial matching.

### Cross-Wallet Transfers

Transferring tokens to another wallet you control and selling there does not avoid the wash sale rule. The rule follows the taxpayer, not the account.

## Safe Re-Entry Strategy

After selling a token at a loss:

1. **Wait 31 calendar days** before repurchasing the same token
2. During the waiting period, consider holding a **non-identical substitute** (e.g., sell SOL, hold ETH for exposure to crypto broadly)
3. Use the countdown timer to know exactly when re-entry is safe
4. Set calendar reminders for window expiration dates

```
Token: SOL
Sale Date: 2025-03-15
Loss: $200.00
Window Closes: 2025-04-14
Days Remaining: 12
Status: DO NOT BUY — wash sale window active
```

## Basis Adjustment Walkthrough

Detailed step-by-step basis adjustment example:

```
TRADE 1: Buy 100 SOL @ $150.00    → Basis: $15,000.00
TRADE 2: Sell 100 SOL @ $120.00   → Proceeds: $12,000.00, Loss: $3,000.00
TRADE 3: Buy 100 SOL @ $125.00    → Basis before adjustment: $12,500.00
         (within 30 days of Trade 2)

WASH SALE TRIGGERED:
  Disallowed loss:    $3,000.00
  Adjusted basis:     $12,500.00 + $3,000.00 = $15,500.00
  Effective price:    $155.00 per SOL (not $125.00)

Later sale at $160.00:
  Proceeds:    $16,000.00
  Adj. basis:  $15,500.00
  Gain:        $500.00 (not $3,500.00)
  The $3,000 loss is recovered through the higher basis.
```

## Files

### References
- `references/planned_features.md` — Wash sale rules in depth, 61-day window mechanics, basis adjustment examples, automation edge cases, IRS guidance references

### Scripts
- `scripts/wash_sale_scanner.py` — Complete wash sale scanner: loads trade history, identifies wash sales, computes disallowed losses and basis adjustments, shows safe re-entry countdowns. Run with `--demo` for example scenarios.

## Limitations

- This tool implements a simplified interpretation of wash sale rules as applied to crypto
- "Substantially identical" determination for wrapped tokens and derivatives may require professional judgment
- The scanner does not handle options, futures, or other derivative instruments on crypto
- Multi-account detection requires you to aggregate trade data manually
- Rules may change as IRS issues further guidance on digital asset wash sales
- State tax rules may differ from federal treatment
