---
name: trade-accounting
description: Double-entry bookkeeping for trading operations with ledger management, P&L statements, balance sheets, and cash flow reporting
license: MIT
metadata:
  author: agipro
  version: "0.1.0"
  category: trading
---

# Trade Accounting

Run your trading operation like a business. Every SOL spent, every token acquired, every fee paid, every gain realized — tracked with double-entry bookkeeping so your books always balance. Whether you trade through a personal wallet or an LLC, proper accounting turns chaos into clarity.

**Core principle**: Every transaction touches at least two accounts. Buy a token? Cash goes down, token holdings go up — by the same amount. This double-entry constraint catches errors automatically: if debits do not equal credits, something is wrong.

## Why Traders Need Accounting

Most traders track P&L loosely — "I started with 50 SOL and now I have 62 SOL." That tells you nothing about:

- How much came from realized trades vs unrealized positions
- What you paid in cumulative fees (gas, priority fees, swap fees)
- Whether your staking and LP income covers your operating costs
- Your actual cost basis for each holding (critical for taxes)
- Cash flow timing — are you profitable but illiquid?

Proper accounting answers all of these. It also separates **trading P&L** (mark-to-market, useful for strategy evaluation) from **tax P&L** (realized gains using a specific cost basis method, required for compliance).

---

## Account Types

A trading operation uses four account categories following standard accounting:

| Category | Normal Balance | Examples |
|----------|---------------|----------|
| **Assets** | Debit | Cash (SOL/USDC), token holdings, LP positions, staking deposits, receivables |
| **Liabilities** | Credit | Margin borrowing, accrued taxes payable |
| **Income** | Credit | Realized trading gains, staking rewards, airdrop income, LP fee income |
| **Expenses** | Debit | Trading fees, gas/priority fees, subscription costs, data feeds |
| **Equity** | Credit | Owner capital contributions, retained earnings, withdrawals (contra) |

### Chart of Accounts

See `references/planned_features.md` for a full chart of accounts. A minimal setup:

```
1000  Assets
  1010  Cash – SOL
  1020  Cash – USDC
  1100  Token Holdings (one sub-account per token)
  1200  LP Positions
  1300  Staking Deposits

3000  Income
  3010  Realized Trading Gains
  3020  Staking Rewards
  3030  Airdrop Income
  3040  LP Fee Income

4000  Expenses
  4010  Trading Fees (DEX swap fees)
  4020  Gas & Priority Fees
  4030  Slippage Cost

5000  Equity
  5010  Owner Capital
  5020  Retained Earnings
  5030  Owner Withdrawals (contra-equity)
```

---

## Double-Entry Bookkeeping

Every transaction records equal debits and credits. Debits increase asset and expense accounts; credits increase liability, income, and equity accounts.

### Entry Examples

**Buy 1000 BONK for 0.5 SOL (0.001 SOL gas fee):**

| Account | Debit | Credit |
|---------|-------|--------|
| Token Holdings – BONK | 0.501 SOL | |
| Cash – SOL | | 0.501 SOL |

Or with the fee broken out explicitly:

| Account | Debit | Credit |
|---------|-------|--------|
| Token Holdings – BONK | 0.5 SOL | |
| Gas & Priority Fees | 0.001 SOL | |
| Cash – SOL | | 0.501 SOL |

**Sell 1000 BONK for 0.8 SOL (cost basis was 0.5 SOL, 0.001 SOL gas):**

| Account | Debit | Credit |
|---------|-------|--------|
| Cash – SOL | 0.799 SOL | |
| Gas & Priority Fees | 0.001 SOL | |
| Token Holdings – BONK | | 0.5 SOL |
| Realized Trading Gains | | 0.3 SOL |

**Receive staking rewards of 0.05 SOL:**

| Account | Debit | Credit |
|---------|-------|--------|
| Cash – SOL | 0.05 SOL | |
| Staking Rewards | | 0.05 SOL |

**Receive airdrop of 5000 JUP (valued at 2.1 SOL at receipt):**

| Account | Debit | Credit |
|---------|-------|--------|
| Token Holdings – JUP | 2.1 SOL | |
| Airdrop Income | | 2.1 SOL |

**Collect LP fees of 0.03 SOL:**

| Account | Debit | Credit |
|---------|-------|--------|
| Cash – SOL | 0.03 SOL | |
| LP Fee Income | | 0.03 SOL |

**Partial close — sell half a position:**

If you hold 2000 BONK at cost basis 1.0 SOL and sell 1000 for 0.7 SOL:

| Account | Debit | Credit |
|---------|-------|--------|
| Cash – SOL | 0.699 SOL | |
| Gas & Priority Fees | 0.001 SOL | |
| Token Holdings – BONK | | 0.5 SOL |
| Realized Trading Gains | | 0.2 SOL |

The cost basis of the sold portion (0.5 SOL = half of 1.0 SOL) is removed from the asset account.

---

## Transaction Types

The ledger handles these trading flows:

| Flow | Accounts Touched |
|------|-----------------|
| Fund account | Cash (debit), Owner Capital (credit) |
| Withdraw funds | Owner Withdrawals (debit), Cash (credit) |
| Buy token | Token Holdings (debit), Cash (credit), Gas Expense (debit) |
| Sell token | Cash (debit), Token Holdings (credit), Realized Gains (credit or debit for loss), Gas Expense (debit) |
| Partial close | Same as sell, pro-rated cost basis |
| Swap token for token | Token B (debit), Token A (credit), fees |
| Staking deposit | Staking Deposits (debit), Cash (credit) |
| Staking reward | Cash (debit), Staking Rewards (credit) |
| Airdrop received | Token Holdings (debit), Airdrop Income (credit) |
| LP fee collected | Cash (debit), LP Fee Income (credit) |
| Trading fee | Trading Fees (debit), Cash (credit) |
| Gas/priority fee | Gas & Priority Fees (debit), Cash (credit) |

---

## Reports

### Profit & Loss Statement

Shows income minus expenses for a period:

```
═══════════════════════════════════════════
  P&L Statement: 2026-02-01 to 2026-02-28
═══════════════════════════════════════════
INCOME
  Realized Trading Gains ........  4.200 SOL
  Staking Rewards ...............  0.150 SOL
  Airdrop Income ................  2.100 SOL
  LP Fee Income .................  0.090 SOL
                                  ─────────
  Total Income                     6.540 SOL

EXPENSES
  Trading Fees ..................  0.120 SOL
  Gas & Priority Fees ...........  0.045 SOL
  Slippage Cost .................  0.030 SOL
                                  ─────────
  Total Expenses                   0.195 SOL

═══════════════════════════════════════════
  NET INCOME                       6.345 SOL
═══════════════════════════════════════════
```

### Balance Sheet

Shows the accounting equation: Assets = Liabilities + Equity.

```
═══════════════════════════════════════════
  Balance Sheet: 2026-02-28
═══════════════════════════════════════════
ASSETS
  Cash – SOL ....................  32.450 SOL
  Cash – USDC ...................   0.000 SOL
  Token Holdings ................  12.300 SOL
  LP Positions ..................   5.000 SOL
  Staking Deposits ..............  10.000 SOL
                                  ─────────
  Total Assets                    59.750 SOL

EQUITY
  Owner Capital .................  50.000 SOL
  Retained Earnings .............   3.405 SOL
  Net Income (current period) ...   6.345 SOL
                                  ─────────
  Total Equity                    59.750 SOL

═══════════════════════════════════════════
  Assets - Equity = 0.000 SOL  ✓ Balanced
═══════════════════════════════════════════
```

### Cash Flow Statement

Tracks where cash came from and where it went:

```
═══════════════════════════════════════════
  Cash Flow: 2026-02-01 to 2026-02-28
═══════════════════════════════════════════
OPERATING ACTIVITIES
  Trading proceeds ..............  8.500 SOL
  Token purchases ...............  (4.300) SOL
  Fees paid .....................  (0.195) SOL
  Staking rewards received ......  0.150 SOL
  LP fees received ..............  0.090 SOL
                                  ─────────
  Net Operating Cash Flow        4.245 SOL

INVESTING ACTIVITIES
  LP deposits ...................  (5.000) SOL
  Staking deposits ..............  (2.000) SOL
                                  ─────────
  Net Investing Cash Flow       (7.000) SOL

FINANCING ACTIVITIES
  Capital contributions .........  10.000 SOL
  Withdrawals ...................  (1.000) SOL
                                  ─────────
  Net Financing Cash Flow        9.000 SOL

═══════════════════════════════════════════
  Net Change in Cash              6.245 SOL
  Beginning Cash Balance         26.205 SOL
  Ending Cash Balance            32.450 SOL
═══════════════════════════════════════════
```

---

## Trading P&L vs Tax P&L

These are different numbers and serve different purposes:

| Aspect | Trading P&L | Tax P&L |
|--------|------------|---------|
| **Purpose** | Strategy evaluation | Compliance, filing |
| **Unrealized gains** | Included (mark-to-market) | Excluded (until realized) |
| **Cost basis method** | Average cost (simple) | FIFO, LIFO, or specific ID (jurisdiction-dependent) |
| **Timing** | Real-time | At disposal event |
| **Airdrops** | Valued at receipt | Ordinary income at FMV on receipt |
| **LP IL** | Tracked as unrealized loss | Not a taxable event until withdrawal |

The ledger in `scripts/trading_ledger.py` tracks realized gains using FIFO by default. For trading P&L, you can overlay mark-to-market valuations on open positions.

See `references/planned_features.md` for detailed worked examples of how the same trades produce different P&L under FIFO vs average cost.

---

## Entity Considerations

Traders operating through an LLC or S-Corp should track additional accounts:

- **Management fees** — if the entity charges a management fee
- **Distributions** — payments from entity to owner (not the same as withdrawals from a trading account)
- **Payroll expenses** — S-Corp officer salary
- **Tax provisions** — estimated quarterly tax payments

The accounting principles are identical; the chart of accounts simply expands. The scripts in this skill focus on the trading-level ledger, which is the foundation for entity-level reporting.

---

## Quick Start

```python
from trading_ledger import Ledger, Amount

ledger = Ledger(base_currency="SOL")

# Fund the account
ledger.record_funding(amount=50.0, memo="Initial capital")

# Buy a token
ledger.record_buy(
    token="BONK",
    quantity=100_000,
    cost_sol=0.5,
    fee_sol=0.001,
    memo="Entry on volume spike"
)

# Sell for profit
ledger.record_sell(
    token="BONK",
    quantity=100_000,
    proceeds_sol=0.8,
    fee_sol=0.001,
    memo="Target hit"
)

# Record staking reward
ledger.record_income(
    income_type="staking",
    amount_sol=0.05,
    memo="Epoch 580 rewards"
)

# Generate reports
ledger.print_pnl(start="2026-02-01", end="2026-02-28")
ledger.print_balance_sheet(as_of="2026-02-28")
```

Run the demo script to see a full month of trading activity with all report types:

```bash
python scripts/trading_ledger.py --demo
```

---

## Use Cases

1. **Track real P&L** — Know exactly how much you made after all fees, not just entry/exit prices
2. **Tax preparation** — Hand your accountant a clean ledger with cost basis and realized gains
3. **Fee analysis** — Discover that gas and priority fees are eating 3% of your gross profits
4. **Strategy comparison** — Compare net P&L across strategies, not just win rates
5. **Cash flow planning** — Know if you have enough liquid SOL for the next trade
6. **Audit trail** — Every number traces back to a dated, memo-tagged journal entry

---

## Prerequisites

- Python 3.10+
- No external dependencies (the ledger uses only the standard library)

---

## Files

| File | Description |
|------|-------------|
| `references/planned_features.md` | Chart of accounts, double-entry examples, report formats, trading vs tax P&L |
| `scripts/trading_ledger.py` | Double-entry ledger with P&L, balance sheet, and demo mode |

---

> **Disclaimer**: This skill provides accounting structure and calculations for informational and organizational purposes only. It is not tax advice, legal advice, or financial advice. Consult a qualified tax professional or CPA for guidance on your specific tax obligations. Cryptocurrency tax treatment varies by jurisdiction and changes frequently.
