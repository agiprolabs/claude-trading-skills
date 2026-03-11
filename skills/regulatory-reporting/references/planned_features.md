# Regulatory Reporting — Planned Features & Requirements Overview

> **DISCLAIMER**: This document is for informational purposes only and does not constitute tax or legal advice. Consult a qualified tax professional before making any filing decisions.

## IRS Form 8949 — Sales and Dispositions of Capital Assets

### Purpose

Report each sale, exchange, or disposition of a capital asset. For cryptocurrency, every taxable event (trade, swap, spend, gift) generates a line item on Form 8949.

### Parts

- **Part I**: Short-term transactions (held one year or less). Check Box A, B, or C.
- **Part II**: Long-term transactions (held more than one year). Check Box D, E, or F.

### Box Codes (Basis Reporting)

| Box | Meaning |
|-----|---------|
| A/D | Basis reported to IRS (1099-B received with basis) |
| B/E | Basis NOT reported to IRS (1099-B received, no basis) |
| C/F | No 1099-B received at all |

Most crypto transactions through 2025 fall under Box C/F. Starting in 2026, centralized exchanges must issue 1099-DA forms, shifting many transactions to Box A/D.

### Column Definitions

| Column | Field | Description | Example |
|--------|-------|-------------|---------|
| (a) | Description | Asset name and quantity | "10.5 SOL" |
| (b) | Date Acquired | Purchase or receipt date | "01/15/2025" |
| (c) | Date Sold | Sale or disposition date | "08/20/2025" |
| (d) | Proceeds | Amount received in USD | "$2,500.00" |
| (e) | Cost Basis | Original cost in USD + fees | "$1,800.00" |
| (f) | Adjustment Code | W (wash sale), B (basis incorrect), etc. | "W" |
| (g) | Adjustment Amount | Dollar amount of adjustment | "$200.00" |
| (h) | Gain or Loss | Column (d) minus (e), adjusted by (g) | "$700.00" |

### Taxable Events in Crypto

| Event | Taxable? | Notes |
|-------|----------|-------|
| Crypto-to-fiat sale | Yes | Gain/loss = proceeds minus basis |
| Crypto-to-crypto swap | Yes | Fair market value at time of swap |
| Spending crypto | Yes | Treated as a sale at FMV |
| Receiving as payment | Yes (income) | Ordinary income at FMV when received |
| Mining/staking rewards | Yes (income) | Ordinary income at FMV when received |
| Airdrops | Yes (income) | Ordinary income at FMV when received |
| Gifts received | No (until sold) | Basis carries over from donor |
| Transfers between wallets | No | Same owner, no disposition |
| Buying crypto with fiat | No | Establishes cost basis |

## Schedule D — Capital Gains and Losses

### Key Lines

| Line | Description |
|------|-------------|
| 1b | Short-term totals from Form 8949, Box A |
| 1c | Short-term totals from Form 8949, Box B |
| 2 | Short-term totals from Form 8949, Box C |
| 7 | Net short-term capital gain or (loss) |
| 8b | Long-term totals from Form 8949, Box D |
| 8c | Long-term totals from Form 8949, Box E |
| 9 | Long-term totals from Form 8949, Box F |
| 15 | Net long-term capital gain or (loss) |
| 16 | Combine lines 7 and 15 |
| 21 | Net capital loss deduction (max $3,000/year) |

### Capital Loss Carryforward

If net capital losses exceed $3,000 in a tax year, the excess carries forward to future years indefinitely. Track cumulative carryforward balances across tax years.

## FinCEN FBAR (Form 114)

### Filing Requirement

A U.S. person must file FinCEN Form 114 if they have a financial interest in, or signature authority over, foreign financial accounts with an **aggregate value exceeding $10,000** at any time during the calendar year.

### Key Thresholds

| Threshold | Amount | Notes |
|-----------|--------|-------|
| Filing trigger | $10,000 aggregate | Sum of ALL foreign accounts on any single day |
| Non-willful penalty | Up to $12,500 per violation | Per account, per year |
| Willful penalty | Up to $100,000 or 50% of balance | Whichever is greater |

### Crypto and FBAR

The applicability of FBAR to crypto accounts on foreign exchanges is an evolving area. FinCEN proposed rules in 2020 to include virtual currency, but final rules have not been issued as of this writing. Conservative guidance: if you hold crypto on a foreign exchange, consult a tax professional about FBAR obligations.

### Required Information per Account

- Name and address of the foreign financial institution
- Account number
- Type of account
- Maximum value during the calendar year
- Currency type

### Filing Details

- **Where**: Filed electronically via BSA E-Filing System (not with your tax return)
- **Deadline**: April 15, with automatic extension to October 15
- **No tax due**: FBAR is an information return, not a tax form

## FATCA — Form 8938

### Filing Thresholds

| Filing Status | Living in U.S. | Living Abroad |
|---------------|---------------|---------------|
| Single | $50,000 (year-end) / $75,000 (any time) | $200,000 (year-end) / $300,000 (any time) |
| Married filing jointly | $100,000 (year-end) / $150,000 (any time) | $400,000 (year-end) / $600,000 (any time) |

Form 8938 is filed with your tax return, unlike FBAR. Both may be required for the same accounts.

## State-Specific Requirements

### States with Notable Crypto Provisions (as of 2025)

| State | Requirement | Notes |
|-------|-------------|-------|
| California | Conforms to federal treatment | No special crypto rules; high marginal rates |
| New York | BitLicense for businesses | Individual reporting follows federal |
| Wyoming | No state income tax | Favorable crypto legislation |
| Texas | No state income tax | No additional reporting |
| Florida | No state income tax | No additional reporting |
| Colorado | Accepts crypto for tax payments | Standard capital gains treatment |
| Illinois | Follows federal treatment | Additional state capital gains |

### General State Guidance

- Most states conform to federal capital gains treatment
- Some states tax capital gains as ordinary income (no preferential long-term rate)
- State-level wash sale rules may differ from federal
- Check state Department of Revenue for current guidance

## Reporting Deadlines Calendar

| Date | Form | Description |
|------|------|-------------|
| January 15 | 1040-ES | Q4 estimated tax payment |
| January 31 | 1099 forms | Exchanges issue 1099s to taxpayers |
| April 15 | 1040 + Schedules | Federal tax return (with 8949, Schedule D) |
| April 15 | FBAR (Form 114) | Foreign account reporting |
| April 15 | 1040-ES | Q1 estimated tax payment |
| June 15 | 1040-ES | Q2 estimated tax payment |
| September 15 | 1040-ES | Q3 estimated tax payment |
| October 15 | Extended 1040 | Extended federal return deadline |
| October 15 | Extended FBAR | Automatic FBAR extension deadline |

## Large Transaction Reporting (Form 8300)

Businesses receiving more than $10,000 in cash (which may include digital assets under the Infrastructure Investment and Jobs Act) must file Form 8300 within 15 days. As of 2024, the IRS has indicated that digital assets will be treated as cash for Form 8300 purposes for transactions occurring after January 1, 2024.

### Key Points

- Applies to businesses, not individual traders
- Structuring transactions to avoid the $10,000 threshold is illegal
- Must report the identity of the person from whom cash was received
- Filed with FinCEN, not the IRS

## Planned Implementation Features

### Phase 1 — Core Reporting (Current Focus)
- Form 8949 line-item generation from trade CSV data
- FIFO cost-basis calculation
- Short-term vs. long-term classification
- Schedule D summary totals

### Phase 2 — Enhanced Calculations
- Multiple cost-basis methods (LIFO, HIFO, Specific ID)
- Wash sale detection and flagging
- Like-kind exchange analysis (pre-2018 trades only)
- Capital loss carryforward tracking

### Phase 3 — Additional Forms
- FinCEN FBAR data compilation
- FATCA Form 8938 threshold checking
- Form 8300 large-transaction flagging
- 1040-ES quarterly estimated tax worksheet

### Phase 4 — Output & Integration
- IRS-compatible CSV export
- PDF form generation
- Exchange API import (Coinbase, Kraken, Binance)
- Multi-year reporting with carryforward
