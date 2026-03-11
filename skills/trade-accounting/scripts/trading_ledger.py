#!/usr/bin/env python3
"""Double-entry bookkeeping ledger for trading operations.

Provides a complete accounting system for crypto trading with:
- Double-entry journal entries (debits always equal credits)
- FIFO cost basis tracking per token
- P&L statement, balance sheet, and cash flow reports
- Support for buys, sells, partial closes, fees, staking, airdrops, LP fees

Usage:
    python scripts/trading_ledger.py --demo

Dependencies:
    None (standard library only)

Environment Variables:
    None required.
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# ── Account Types ───────────────────────────────────────────────────

class AccountType(Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"
    EQUITY = "equity"


# Normal balance: assets and expenses are debit-normal;
# liabilities, income, and equity are credit-normal.
DEBIT_NORMAL = {AccountType.ASSET, AccountType.EXPENSE}
CREDIT_NORMAL = {AccountType.LIABILITY, AccountType.INCOME, AccountType.EQUITY}


@dataclass
class Account:
    """A single account in the chart of accounts."""
    code: str
    name: str
    account_type: AccountType
    debit_total: float = 0.0
    credit_total: float = 0.0

    @property
    def balance(self) -> float:
        """Return the balance according to normal balance convention."""
        if self.account_type in DEBIT_NORMAL:
            return self.debit_total - self.credit_total
        return self.credit_total - self.debit_total

    def debit(self, amount: float) -> None:
        """Record a debit to this account."""
        self.debit_total += amount

    def credit(self, amount: float) -> None:
        """Record a credit to this account."""
        self.credit_total += amount


# ── Journal Entry ───────────────────────────────────────────────────

@dataclass
class JournalLine:
    """One line of a journal entry (either a debit or credit)."""
    account_code: str
    debit: float = 0.0
    credit: float = 0.0


@dataclass
class JournalEntry:
    """A complete journal entry with balanced debits and credits."""
    entry_id: int
    entry_date: date
    memo: str
    lines: list[JournalLine] = field(default_factory=list)

    @property
    def total_debits(self) -> float:
        return sum(line.debit for line in self.lines)

    @property
    def total_credits(self) -> float:
        return sum(line.credit for line in self.lines)

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debits - self.total_credits) < 1e-10


# ── Cost Basis Lot ──────────────────────────────────────────────────

@dataclass
class CostLot:
    """A single cost basis lot for FIFO tracking."""
    quantity: float
    cost_per_unit: float
    acquired_date: date

    @property
    def total_cost(self) -> float:
        return self.quantity * self.cost_per_unit


# ── Ledger ──────────────────────────────────────────────────────────

class Ledger:
    """Double-entry bookkeeping ledger for trading operations.

    Tracks all transactions with balanced journal entries, maintains
    FIFO cost basis lots per token, and generates financial reports.

    Args:
        base_currency: The denomination currency for all amounts.
    """

    def __init__(self, base_currency: str = "SOL") -> None:
        self.base_currency = base_currency
        self.accounts: dict[str, Account] = {}
        self.journal: list[JournalEntry] = []
        self.cost_lots: dict[str, list[CostLot]] = {}  # token -> lots
        self._next_entry_id = 1
        self._setup_default_accounts()

    def _setup_default_accounts(self) -> None:
        """Create the default chart of accounts."""
        defaults = [
            ("1010", "Cash – SOL", AccountType.ASSET),
            ("1020", "Cash – USDC", AccountType.ASSET),
            ("3010", "Realized Trading Gains", AccountType.INCOME),
            ("3020", "Staking Rewards", AccountType.INCOME),
            ("3030", "Airdrop Income", AccountType.INCOME),
            ("3040", "LP Fee Income", AccountType.INCOME),
            ("4010", "Trading Fees", AccountType.EXPENSE),
            ("4020", "Gas & Priority Fees", AccountType.EXPENSE),
            ("4030", "Slippage Cost", AccountType.EXPENSE),
            ("5010", "Owner Capital", AccountType.EQUITY),
            ("5020", "Retained Earnings", AccountType.EQUITY),
            ("5030", "Owner Withdrawals", AccountType.EQUITY),
        ]
        for code, name, atype in defaults:
            self.accounts[code] = Account(code, name, atype)

    def _get_or_create_token_account(self, token: str) -> str:
        """Get or create a token holdings sub-account. Returns account code."""
        # Search existing accounts for this token
        for code, acct in self.accounts.items():
            if acct.name == f"Token Holdings – {token}":
                return code
        # Create new sub-account
        existing_codes = [
            int(c) for c in self.accounts if c.startswith("11") and len(c) == 4
        ]
        next_code = max(existing_codes, default=1100) + 1
        code = str(next_code)
        self.accounts[code] = Account(
            code, f"Token Holdings – {token}", AccountType.ASSET
        )
        return code

    def _post_entry(self, entry: JournalEntry) -> None:
        """Post a journal entry to the accounts."""
        if not entry.is_balanced:
            raise ValueError(
                f"Entry {entry.entry_id} is not balanced: "
                f"debits={entry.total_debits:.6f}, "
                f"credits={entry.total_credits:.6f}"
            )
        for line in entry.lines:
            acct = self.accounts[line.account_code]
            if line.debit > 0:
                acct.debit(line.debit)
            if line.credit > 0:
                acct.credit(line.credit)
        self.journal.append(entry)

    def _next_id(self) -> int:
        """Get the next journal entry ID."""
        eid = self._next_entry_id
        self._next_entry_id += 1
        return eid

    # ── High-Level Recording Methods ────────────────────────────────

    def record_funding(
        self,
        amount: float,
        entry_date: Optional[date] = None,
        memo: str = "Capital contribution",
    ) -> None:
        """Record an owner funding / capital contribution.

        Args:
            amount: Amount in base currency.
            entry_date: Date of transaction.
            memo: Description.
        """
        d = entry_date or date.today()
        entry = JournalEntry(self._next_id(), d, memo)
        entry.lines.append(JournalLine("1010", debit=amount))
        entry.lines.append(JournalLine("5010", credit=amount))
        self._post_entry(entry)

    def record_withdrawal(
        self,
        amount: float,
        entry_date: Optional[date] = None,
        memo: str = "Owner withdrawal",
    ) -> None:
        """Record an owner withdrawal.

        Args:
            amount: Amount in base currency.
            entry_date: Date of transaction.
            memo: Description.
        """
        d = entry_date or date.today()
        entry = JournalEntry(self._next_id(), d, memo)
        # Owner Withdrawals is contra-equity (debit-normal in practice)
        entry.lines.append(JournalLine("5030", debit=amount))
        entry.lines.append(JournalLine("1010", credit=amount))
        self._post_entry(entry)

    def record_buy(
        self,
        token: str,
        quantity: float,
        cost_sol: float,
        fee_sol: float = 0.0,
        entry_date: Optional[date] = None,
        memo: str = "",
    ) -> None:
        """Record a token purchase.

        Args:
            token: Token symbol.
            quantity: Number of tokens purchased.
            cost_sol: Cost in base currency (excluding fees).
            fee_sol: Gas/priority fee in base currency.
            entry_date: Date of transaction.
            memo: Description.
        """
        d = entry_date or date.today()
        token_acct = self._get_or_create_token_account(token)
        entry = JournalEntry(self._next_id(), d, memo or f"Buy {token}")

        entry.lines.append(JournalLine(token_acct, debit=cost_sol))
        if fee_sol > 0:
            entry.lines.append(JournalLine("4020", debit=fee_sol))
        entry.lines.append(JournalLine("1010", credit=cost_sol + fee_sol))
        self._post_entry(entry)

        # Track cost lot
        if token not in self.cost_lots:
            self.cost_lots[token] = []
        self.cost_lots[token].append(
            CostLot(quantity, cost_sol / quantity, d)
        )

    def record_sell(
        self,
        token: str,
        quantity: float,
        proceeds_sol: float,
        fee_sol: float = 0.0,
        entry_date: Optional[date] = None,
        memo: str = "",
    ) -> None:
        """Record a token sale with FIFO cost basis.

        Args:
            token: Token symbol.
            quantity: Number of tokens sold.
            proceeds_sol: Sale proceeds in base currency (before fees).
            fee_sol: Gas/priority fee in base currency.
            entry_date: Date of transaction.
            memo: Description.
        """
        d = entry_date or date.today()
        token_acct = self._get_or_create_token_account(token)

        # Calculate FIFO cost basis
        cost_basis = self._consume_lots(token, quantity)

        gain = proceeds_sol - cost_basis
        entry = JournalEntry(self._next_id(), d, memo or f"Sell {token}")

        # Cash received (net of fee)
        entry.lines.append(JournalLine("1010", debit=proceeds_sol - fee_sol))
        if fee_sol > 0:
            entry.lines.append(JournalLine("4020", debit=fee_sol))

        # Remove cost basis from token holdings
        entry.lines.append(JournalLine(token_acct, credit=cost_basis))

        # Record gain or loss
        if gain >= 0:
            entry.lines.append(JournalLine("3010", credit=gain))
        else:
            entry.lines.append(JournalLine("3010", debit=abs(gain)))

        self._post_entry(entry)

    def _consume_lots(self, token: str, quantity: float) -> float:
        """Consume FIFO cost lots and return total cost basis.

        Args:
            token: Token symbol.
            quantity: Number of tokens to consume.

        Returns:
            Total cost basis of consumed lots.

        Raises:
            ValueError: If insufficient lots available.
        """
        if token not in self.cost_lots:
            raise ValueError(f"No cost lots for {token}")

        remaining = quantity
        cost_basis = 0.0
        lots = self.cost_lots[token]

        while remaining > 1e-10 and lots:
            lot = lots[0]
            if lot.quantity <= remaining + 1e-10:
                cost_basis += lot.total_cost
                remaining -= lot.quantity
                lots.pop(0)
            else:
                consumed = remaining
                cost_basis += consumed * lot.cost_per_unit
                lot.quantity -= consumed
                remaining = 0.0

        if remaining > 1e-10:
            raise ValueError(
                f"Insufficient {token} lots: needed {quantity}, "
                f"shortfall {remaining}"
            )

        return cost_basis

    def record_income(
        self,
        income_type: str,
        amount_sol: float,
        token: Optional[str] = None,
        token_quantity: float = 0.0,
        entry_date: Optional[date] = None,
        memo: str = "",
    ) -> None:
        """Record income (staking rewards, airdrops, LP fees).

        Args:
            income_type: One of 'staking', 'airdrop', 'lp_fee'.
            amount_sol: Value in base currency.
            token: For airdrops, the token symbol received.
            token_quantity: For airdrops, number of tokens received.
            entry_date: Date of transaction.
            memo: Description.
        """
        d = entry_date or date.today()
        income_accounts = {
            "staking": "3020",
            "airdrop": "3030",
            "lp_fee": "3040",
        }
        income_acct = income_accounts.get(income_type)
        if not income_acct:
            raise ValueError(
                f"Unknown income type: {income_type}. "
                f"Use: {list(income_accounts.keys())}"
            )

        entry = JournalEntry(
            self._next_id(), d, memo or f"{income_type} income"
        )

        if income_type == "airdrop" and token:
            token_acct = self._get_or_create_token_account(token)
            entry.lines.append(JournalLine(token_acct, debit=amount_sol))
            # Create cost lot for the airdrop tokens
            if token not in self.cost_lots:
                self.cost_lots[token] = []
            if token_quantity > 0:
                self.cost_lots[token].append(
                    CostLot(token_quantity, amount_sol / token_quantity, d)
                )
        else:
            entry.lines.append(JournalLine("1010", debit=amount_sol))

        entry.lines.append(JournalLine(income_acct, credit=amount_sol))
        self._post_entry(entry)

    def record_expense(
        self,
        expense_type: str,
        amount_sol: float,
        entry_date: Optional[date] = None,
        memo: str = "",
    ) -> None:
        """Record a standalone expense (not tied to a trade).

        Args:
            expense_type: One of 'trading_fee', 'gas', 'slippage'.
            amount_sol: Amount in base currency.
            entry_date: Date of transaction.
            memo: Description.
        """
        d = entry_date or date.today()
        expense_accounts = {
            "trading_fee": "4010",
            "gas": "4020",
            "slippage": "4030",
        }
        expense_acct = expense_accounts.get(expense_type)
        if not expense_acct:
            raise ValueError(
                f"Unknown expense type: {expense_type}. "
                f"Use: {list(expense_accounts.keys())}"
            )

        entry = JournalEntry(self._next_id(), d, memo or f"{expense_type}")
        entry.lines.append(JournalLine(expense_acct, debit=amount_sol))
        entry.lines.append(JournalLine("1010", credit=amount_sol))
        self._post_entry(entry)

    # ── Reports ─────────────────────────────────────────────────────

    def _entries_in_range(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[JournalEntry]:
        """Filter journal entries by date range."""
        entries = self.journal
        if start:
            entries = [e for e in entries if e.entry_date >= start]
        if end:
            entries = [e for e in entries if e.entry_date <= end]
        return entries

    def _period_balances(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> dict[str, float]:
        """Calculate net balance changes per account for a period.

        Positive = net debit, negative = net credit.
        """
        entries = self._entries_in_range(start, end)
        balances: dict[str, float] = {}
        for entry in entries:
            for line in entry.lines:
                code = line.account_code
                balances[code] = balances.get(code, 0.0) + line.debit - line.credit
                balances[code] = balances.get(code, 0.0)
        return balances

    def get_pnl(
        self, start: Optional[date] = None, end: Optional[date] = None
    ) -> dict:
        """Calculate P&L for a period.

        Returns:
            Dict with income items, expense items, totals, and net income.
        """
        entries = self._entries_in_range(start, end)

        income: dict[str, float] = {}
        expenses: dict[str, float] = {}

        for entry in entries:
            for line in entry.lines:
                acct = self.accounts.get(line.account_code)
                if not acct:
                    continue
                if acct.account_type == AccountType.INCOME:
                    # Credits increase income, debits decrease it
                    income[acct.name] = income.get(acct.name, 0.0) + (
                        line.credit - line.debit
                    )
                elif acct.account_type == AccountType.EXPENSE:
                    # Debits increase expenses
                    expenses[acct.name] = expenses.get(acct.name, 0.0) + (
                        line.debit - line.credit
                    )

        total_income = sum(income.values())
        total_expenses = sum(expenses.values())

        return {
            "income": income,
            "expenses": expenses,
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_income": total_income - total_expenses,
        }

    def print_pnl(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> None:
        """Print a formatted P&L statement.

        Args:
            start: Start date as YYYY-MM-DD string.
            end: End date as YYYY-MM-DD string.
        """
        s = date.fromisoformat(start) if start else None
        e = date.fromisoformat(end) if end else None
        pnl = self.get_pnl(s, e)
        cur = self.base_currency

        label_start = start or "inception"
        label_end = end or "now"

        print()
        print("=" * 52)
        print(f"  P&L Statement: {label_start} to {label_end}")
        print("=" * 52)
        print("INCOME")
        for name, val in sorted(pnl["income"].items()):
            if abs(val) > 1e-10:
                print(f"  {name:<34s} {val:>8.3f} {cur}")
        print(f"  {'':─<34s} ─────────")
        print(f"  {'Total Income':<34s} {pnl['total_income']:>8.3f} {cur}")
        print()
        print("EXPENSES")
        for name, val in sorted(pnl["expenses"].items()):
            if abs(val) > 1e-10:
                print(f"  {name:<34s} {val:>8.3f} {cur}")
        print(f"  {'':─<34s} ─────────")
        print(f"  {'Total Expenses':<34s} {pnl['total_expenses']:>8.3f} {cur}")
        print()
        print("=" * 52)
        print(f"  {'NET INCOME':<34s} {pnl['net_income']:>8.3f} {cur}")
        print("=" * 52)
        print()

    def print_balance_sheet(self, as_of: Optional[str] = None) -> None:
        """Print a formatted balance sheet.

        Args:
            as_of: Date as YYYY-MM-DD string (uses all entries if None).
        """
        as_of_date = date.fromisoformat(as_of) if as_of else None
        pnl = self.get_pnl(end=as_of_date)
        cur = self.base_currency

        # Calculate cumulative balances from all entries up to as_of
        entries = self._entries_in_range(end=as_of_date)

        balances: dict[str, float] = {}
        for entry in entries:
            for line in entry.lines:
                code = line.account_code
                acct = self.accounts.get(code)
                if not acct:
                    continue
                if acct.account_type in DEBIT_NORMAL:
                    balances[code] = balances.get(code, 0.0) + line.debit - line.credit
                else:
                    balances[code] = balances.get(code, 0.0) + line.credit - line.debit

        label = as_of or "current"
        print()
        print("=" * 52)
        print(f"  Balance Sheet: {label}")
        print("=" * 52)

        # Assets
        print("ASSETS")
        total_assets = 0.0
        for code in sorted(balances):
            acct = self.accounts[code]
            if acct.account_type == AccountType.ASSET:
                val = balances[code]
                if abs(val) > 1e-10:
                    print(f"  {acct.name:<34s} {val:>8.3f} {cur}")
                    total_assets += val
        print(f"  {'':─<34s} ─────────")
        print(f"  {'Total Assets':<34s} {total_assets:>8.3f} {cur}")
        print()

        # Equity
        print("EQUITY")
        total_equity = 0.0
        for code in sorted(balances):
            acct = self.accounts[code]
            if acct.account_type == AccountType.EQUITY:
                val = balances[code]
                # Withdrawals is contra-equity: val is negative (more debits
                # than credits), so we display the absolute value as a
                # deduction and subtract it from total equity.
                if code == "5030":
                    if abs(val) > 1e-10:
                        print(f"  Less: {acct.name:<28s} ({abs(val):>7.3f}) {cur}")
                        total_equity += val  # val is negative, so this subtracts
                else:
                    if abs(val) > 1e-10:
                        print(f"  {acct.name:<34s} {val:>8.3f} {cur}")
                        total_equity += val
        # Add net income as current-period retained earnings
        ni = pnl["net_income"]
        if abs(ni) > 1e-10:
            print(f"  {'Net Income (current period)':<34s} {ni:>8.3f} {cur}")
            total_equity += ni
        print(f"  {'':─<34s} ─────────")
        print(f"  {'Total Equity':<34s} {total_equity:>8.3f} {cur}")
        print()

        diff = total_assets - total_equity
        status = "Balanced" if abs(diff) < 1e-6 else "UNBALANCED"
        print("=" * 52)
        print(
            f"  Assets - Equity = {diff:.3f} {cur}  "
            f"{'✓' if status == 'Balanced' else '✗'} {status}"
        )
        print("=" * 52)
        print()

    def print_journal(self, last_n: int = 0) -> None:
        """Print journal entries.

        Args:
            last_n: Number of recent entries to show (0 = all).
        """
        entries = self.journal[-last_n:] if last_n else self.journal
        cur = self.base_currency
        print()
        print("=" * 62)
        print("  Journal Entries")
        print("=" * 62)
        for entry in entries:
            print(
                f"  #{entry.entry_id:>3d}  {entry.entry_date}  {entry.memo}"
            )
            for line in entry.lines:
                acct = self.accounts[line.account_code]
                if line.debit > 0:
                    print(
                        f"        {acct.name:<30s}  DR {line.debit:>8.4f} {cur}"
                    )
                if line.credit > 0:
                    print(
                        f"        {acct.name:<30s}  CR {line.credit:>8.4f} {cur}"
                    )
            print()

    def print_trial_balance(self) -> None:
        """Print a trial balance showing all account balances."""
        cur = self.base_currency
        print()
        print("=" * 58)
        print("  Trial Balance")
        print("=" * 58)
        print(f"  {'Account':<34s} {'Debit':>10s} {'Credit':>10s}")
        print(f"  {'':─<34s} {'':─>10s} {'':─>10s}")

        total_dr = 0.0
        total_cr = 0.0

        for code in sorted(self.accounts):
            acct = self.accounts[code]
            bal = acct.balance
            if abs(bal) < 1e-10:
                continue
            if acct.account_type in DEBIT_NORMAL:
                print(f"  {acct.name:<34s} {bal:>10.4f} {'':>10s}")
                total_dr += bal
            else:
                # Contra-equity accounts (like withdrawals) have negative
                # credit-normal balances; display them on the debit side.
                if bal < 0:
                    print(f"  {acct.name:<34s} {abs(bal):>10.4f} {'':>10s}")
                    total_dr += abs(bal)
                else:
                    print(f"  {acct.name:<34s} {'':>10s} {bal:>10.4f}")
                    total_cr += bal

        print(f"  {'':─<34s} {'':─>10s} {'':─>10s}")
        print(f"  {'TOTAL':<34s} {total_dr:>10.4f} {total_cr:>10.4f}")
        diff = total_dr - total_cr
        status = "Balanced" if abs(diff) < 1e-6 else "UNBALANCED"
        print(f"  Difference: {diff:.4f} {cur}  {'✓' if status == 'Balanced' else '✗'} {status}")
        print("=" * 58)
        print()


# ── Demo ────────────────────────────────────────────────────────────

def run_demo() -> None:
    """Run a demo showing a full month of trading activity."""
    print()
    print("=" * 62)
    print("  Trade Accounting Demo — February 2026")
    print("  A simulated month of Solana trading activity")
    print("=" * 62)
    print()

    ledger = Ledger(base_currency="SOL")

    # Week 1: Fund account
    ledger.record_funding(
        amount=50.0,
        entry_date=date(2026, 2, 1),
        memo="Initial capital contribution",
    )
    print("[Feb 01] Funded account with 50.0 SOL")

    # Week 1: First trade — buy BONK
    ledger.record_buy(
        token="BONK",
        quantity=500_000,
        cost_sol=2.0,
        fee_sol=0.002,
        entry_date=date(2026, 2, 2),
        memo="BONK entry — volume breakout",
    )
    print("[Feb 02] Bought 500,000 BONK for 2.0 SOL (+0.002 gas)")

    # Week 1: Buy WIF
    ledger.record_buy(
        token="WIF",
        quantity=100,
        cost_sol=3.5,
        fee_sol=0.003,
        entry_date=date(2026, 2, 3),
        memo="WIF entry — trend follow",
    )
    print("[Feb 03] Bought 100 WIF for 3.5 SOL (+0.003 gas)")

    # Week 2: Partial close BONK at profit
    ledger.record_sell(
        token="BONK",
        quantity=250_000,
        proceeds_sol=1.5,
        fee_sol=0.002,
        entry_date=date(2026, 2, 8),
        memo="BONK partial exit — take profit at 50%",
    )
    print("[Feb 08] Sold 250,000 BONK for 1.5 SOL (+0.002 gas)  [+0.5 gain]")

    # Week 2: Staking reward
    ledger.record_income(
        income_type="staking",
        amount_sol=0.15,
        entry_date=date(2026, 2, 10),
        memo="Epoch 580 staking rewards",
    )
    print("[Feb 10] Received 0.15 SOL staking rewards")

    # Week 3: Close remaining BONK at loss
    ledger.record_sell(
        token="BONK",
        quantity=250_000,
        proceeds_sol=0.7,
        fee_sol=0.002,
        entry_date=date(2026, 2, 15),
        memo="BONK exit — stop loss hit",
    )
    print("[Feb 15] Sold 250,000 BONK for 0.7 SOL (+0.002 gas)  [-0.3 loss]")

    # Week 3: Airdrop
    ledger.record_income(
        income_type="airdrop",
        amount_sol=2.1,
        token="JUP",
        token_quantity=5000,
        entry_date=date(2026, 2, 16),
        memo="JUP airdrop claim",
    )
    print("[Feb 16] Received 5,000 JUP airdrop (valued at 2.1 SOL)")

    # Week 3: LP fee income
    ledger.record_income(
        income_type="lp_fee",
        amount_sol=0.09,
        entry_date=date(2026, 2, 18),
        memo="SOL/USDC LP fees collected",
    )
    print("[Feb 18] Collected 0.09 SOL in LP fees")

    # Week 4: Sell WIF at profit
    ledger.record_sell(
        token="WIF",
        quantity=100,
        proceeds_sol=5.2,
        fee_sol=0.003,
        entry_date=date(2026, 2, 22),
        memo="WIF exit — target reached",
    )
    print("[Feb 22] Sold 100 WIF for 5.2 SOL (+0.003 gas)  [+1.7 gain]")

    # Week 4: Buy more BONK (second round)
    ledger.record_buy(
        token="BONK",
        quantity=300_000,
        cost_sol=1.2,
        fee_sol=0.002,
        entry_date=date(2026, 2, 24),
        memo="BONK re-entry — dip buy",
    )
    print("[Feb 24] Bought 300,000 BONK for 1.2 SOL (+0.002 gas)")

    # Week 4: Sell airdropped JUP
    ledger.record_sell(
        token="JUP",
        quantity=5000,
        proceeds_sol=2.8,
        fee_sol=0.003,
        entry_date=date(2026, 2, 26),
        memo="Sell airdropped JUP",
    )
    print("[Feb 26] Sold 5,000 JUP for 2.8 SOL (+0.003 gas)  [+0.7 gain]")

    # Week 4: Withdrawal
    ledger.record_withdrawal(
        amount=5.0,
        entry_date=date(2026, 2, 28),
        memo="Monthly withdrawal",
    )
    print("[Feb 28] Withdrew 5.0 SOL")

    # ── Reports ─────────────────────────────────────────────────────

    print()
    print("-" * 62)
    print("  REPORTS")
    print("-" * 62)

    ledger.print_pnl(start="2026-02-01", end="2026-02-28")
    ledger.print_balance_sheet(as_of="2026-02-28")
    ledger.print_trial_balance()
    ledger.print_journal(last_n=5)

    # Summary
    print("-" * 62)
    print("  SUMMARY")
    print("-" * 62)
    pnl = ledger.get_pnl(
        start=date(2026, 2, 1), end=date(2026, 2, 28)
    )
    print(f"  Total trades:        6 (4 sells, 2 re-entries)")
    print(f"  Gross trading gains: {pnl['income'].get('Realized Trading Gains', 0):.3f} SOL")
    print(f"  Other income:        {sum(v for k, v in pnl['income'].items() if k != 'Realized Trading Gains'):.3f} SOL")
    print(f"  Total fees:          {pnl['total_expenses']:.3f} SOL")
    print(f"  Net income:          {pnl['net_income']:.3f} SOL")
    print(f"  Fee drag:            {pnl['total_expenses'] / pnl['total_income'] * 100:.1f}% of gross income")
    print()
    print("  This is demo data for illustrative purposes only.")
    print("  Not financial or tax advice.")
    print()


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(
        description="Double-entry trading ledger with P&L and balance sheet."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the demo with a simulated month of trading",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        print("Use --demo to run the example trading month.")
        print("Import Ledger class for programmatic use:")
        print("  from trading_ledger import Ledger")
        sys.exit(0)


if __name__ == "__main__":
    main()
