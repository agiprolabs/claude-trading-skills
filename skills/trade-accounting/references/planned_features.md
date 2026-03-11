# Trade Accounting — Reference Guide

## Chart of Accounts

A complete chart of accounts for a Solana trading operation:

```
1000  ASSETS
  1010  Cash – SOL
  1020  Cash – USDC
  1030  Cash – USDT
  1100  Token Holdings
    1101  Token Holdings – BONK
    1102  Token Holdings – JUP
    1103  Token Holdings – WIF
    (one sub-account per token held)
  1200  LP Positions
    1201  LP – SOL/USDC (Orca)
    1202  LP – SOL/BONK (Raydium)
  1300  Staking Deposits
    1301  Staked SOL (Marinade)
    1302  Staked SOL (Jito)
  1400  Receivables
    1401  Pending Airdrop Claims

2000  LIABILITIES
  2010  Margin Borrowing
  2020  Accrued Taxes Payable
  2030  Accounts Payable

3000  INCOME
  3010  Realized Trading Gains
  3020  Staking Rewards
  3030  Airdrop Income
  3040  LP Fee Income
  3050  Interest Income
  3060  Referral Income

4000  EXPENSES
  4010  Trading Fees (DEX swap fees)
  4020  Gas & Priority Fees
  4030  Slippage Cost
  4040  Data & Tool Subscriptions
  4050  Infrastructure Costs (RPC nodes)

5000  EQUITY
  5010  Owner Capital (contributions)
  5020  Retained Earnings (prior periods)
  5030  Owner Withdrawals (contra-equity, debit balance)
```

### Sub-Account Convention

Token holdings use dynamic sub-accounts. When you buy a new token for the first time, create account `1100 + next_id`. The ledger script handles this automatically.

---

## Double-Entry Examples

### Example 1: Full Trade Lifecycle

Starting state: 50 SOL in cash, no positions.

**Day 1 — Buy 500,000 BONK for 2.0 SOL + 0.002 SOL gas:**

| # | Account | Debit | Credit |
|---|---------|-------|--------|
| 1 | 1101 Token Holdings – BONK | 2.000 | |
| 2 | 4020 Gas & Priority Fees | 0.002 | |
| 3 | 1010 Cash – SOL | | 2.002 |

Cash: 47.998. BONK holding: 2.000 (cost basis).

**Day 3 — Sell 250,000 BONK for 1.5 SOL + 0.002 SOL gas:**

Cost basis of sold portion: 2.000 * (250,000 / 500,000) = 1.000 SOL.
Realized gain: 1.5 - 1.0 = 0.5 SOL.

| # | Account | Debit | Credit |
|---|---------|-------|--------|
| 1 | 1010 Cash – SOL | 1.498 | |
| 2 | 4020 Gas & Priority Fees | 0.002 | |
| 3 | 1101 Token Holdings – BONK | | 1.000 |
| 4 | 3010 Realized Trading Gains | | 0.500 |

Cash: 49.496. BONK holding: 1.000 (remaining cost basis).

**Day 5 — Sell remaining 250,000 BONK for 0.8 SOL + 0.002 SOL gas:**

Cost basis: 1.000 SOL. Realized loss: 0.8 - 1.0 = -0.2 SOL.

| # | Account | Debit | Credit |
|---|---------|-------|--------|
| 1 | 1010 Cash – SOL | 0.798 | |
| 2 | 4020 Gas & Priority Fees | 0.002 | |
| 3 | 3010 Realized Trading Gains | 0.200 | |
| 4 | 1101 Token Holdings – BONK | | 1.000 |

Note: When there is a loss, Realized Trading Gains is debited (reducing income).

Cash: 50.294. BONK: 0.000. Net gain from BONK: 0.300 SOL. Total fees: 0.006 SOL.

### Example 2: Staking Flow

**Deposit 10 SOL to staking:**

| Account | Debit | Credit |
|---------|-------|--------|
| 1301 Staked SOL | 10.000 | |
| 1010 Cash – SOL | | 10.000 |

**Receive 0.05 SOL staking reward:**

| Account | Debit | Credit |
|---------|-------|--------|
| 1010 Cash – SOL | 0.050 | |
| 3020 Staking Rewards | | 0.050 |

### Example 3: Airdrop

**Receive 5,000 JUP airdrop (market value 2.1 SOL at time of receipt):**

| Account | Debit | Credit |
|---------|-------|--------|
| 1102 Token Holdings – JUP | 2.100 | |
| 3030 Airdrop Income | | 2.100 |

The cost basis for tax purposes is the FMV at time of receipt (2.1 SOL). If you later sell the JUP for 3.0 SOL, you realize a 0.9 SOL gain.

---

## Report Formats

### P&L Statement Structure

```
INCOME
  Realized Trading Gains          sum of 3010
  Staking Rewards                 sum of 3020
  Airdrop Income                  sum of 3030
  LP Fee Income                   sum of 3040
  ────────────────────────────
  Total Income                    sum of all 3xxx

EXPENSES
  Trading Fees                    sum of 4010
  Gas & Priority Fees             sum of 4020
  Slippage Cost                   sum of 4030
  ────────────────────────────
  Total Expenses                  sum of all 4xxx

NET INCOME = Total Income - Total Expenses
```

### Balance Sheet Structure

```
ASSETS
  Cash accounts                   sum of 1010-1030
  Token Holdings                  sum of 1100s
  LP Positions                    sum of 1200s
  Staking Deposits                sum of 1300s
  ────────────────────────────
  Total Assets                    sum of all 1xxx

LIABILITIES
  (sum of all 2xxx)

EQUITY
  Owner Capital                   5010 balance
  Retained Earnings               5020 balance
  Current Period Net Income       calculated
  Less: Withdrawals               5030 balance
  ────────────────────────────
  Total Equity                    sum of all 5xxx

Assets = Liabilities + Equity  (must balance)
```

### Cash Flow Statement Structure

```
OPERATING (trading activity)
  Token sale proceeds
  Token purchase costs
  Fees paid
  Income received (staking, LP fees)

INVESTING (long-term positions)
  LP deposits/withdrawals
  Staking deposits/withdrawals

FINANCING (capital movements)
  Owner contributions
  Owner withdrawals
```

---

## Trading P&L vs Tax P&L

### The Core Difference

**Trading P&L** includes unrealized gains and uses average cost for simplicity. It tells you how your strategy is performing right now.

**Tax P&L** only includes realized gains and uses a specific cost basis method (FIFO, LIFO, or specific identification). It determines what you owe.

### Worked Example: Same Trades, Different P&L

Three buys of BONK:
1. Buy 100,000 BONK at 0.001 SOL each = 0.100 SOL total
2. Buy 100,000 BONK at 0.002 SOL each = 0.200 SOL total
3. Buy 100,000 BONK at 0.003 SOL each = 0.300 SOL total

Total: 300,000 BONK, total cost 0.600 SOL.

Now sell 100,000 BONK at 0.004 SOL each = 0.400 SOL proceeds.

**FIFO (First In, First Out):**
- Cost basis of sold lot: 0.100 SOL (the first buy)
- Realized gain: 0.400 - 0.100 = **0.300 SOL**

**LIFO (Last In, First Out):**
- Cost basis of sold lot: 0.300 SOL (the third buy)
- Realized gain: 0.400 - 0.300 = **0.100 SOL**

**Average Cost:**
- Average cost: 0.600 / 300,000 = 0.000002 SOL each
- Cost basis of sold lot: 100,000 * 0.000002 = 0.200 SOL
- Realized gain: 0.400 - 0.200 = **0.200 SOL**

Same trade, three different gain amounts: 0.300, 0.100, or 0.200 SOL.

### Airdrops: Income at Receipt

Airdrops are taxable as ordinary income at the fair market value on the date received. This creates a cost basis equal to that FMV. Any subsequent gain or loss on sale is a separate capital gain/loss event.

### Wash Sale Considerations

Some jurisdictions apply wash sale rules to crypto. If you sell at a loss and repurchase the same token within 30 days, the loss may be disallowed and added to the cost basis of the new purchase. The ledger does not enforce wash sale rules — consult a tax professional.

---

## Planned Enhancements

Features under consideration for future versions:

- **Multi-currency support** — Track in SOL with USD/EUR conversion at transaction time
- **Wash sale tracking** — Flag potential wash sales with adjustable lookback period
- **Lot-level tracking** — Specific identification for optimal tax lot selection
- **On-chain import** — Parse Solana transactions into journal entries automatically
- **CSV/JSON export** — Export ledger for import into accounting software
- **Mark-to-market overlay** — Add unrealized P&L layer for trading evaluation
- **Entity-level accounts** — Management fees, distributions, payroll for LLC/S-Corp
- **Multi-wallet consolidation** — Merge ledgers across wallets into one view
