#!/usr/bin/env python3
"""Real-time tax liability tracker for active crypto traders.

Demonstrates proportional cost basis tracking, short-term vs long-term gain
classification, tax-aware trading signals, and quarterly tax projection.

Usage:
    python scripts/tax_tracker.py              # Run demo scenario
    python scripts/tax_tracker.py --demo       # Same as above

Dependencies:
    None — uses Python standard library only.

Environment Variables:
    None required for demo mode.

Disclaimer:
    Tax calculations are for informational tracking purposes only.
    Consult a qualified tax professional for actual tax filing.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class GainType(Enum):
    SHORT_TERM = "short-term"
    LONG_TERM = "long-term"


class AccountingMethod(Enum):
    FIFO = "fifo"
    LIFO = "lifo"


@dataclass
class Trade:
    """A single trade event."""

    timestamp: str  # ISO 8601
    side: str  # "buy" or "sell"
    token: str
    amount: float
    price_usd: float  # Per-unit price in USD
    total_usd: float  # Total value in USD

    @property
    def dt(self) -> datetime:
        ts = self.timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)


@dataclass
class TaxLot:
    """A single cost basis lot."""

    acquisition_date: datetime
    amount: float
    per_unit_basis: float
    token: str

    @property
    def total_basis(self) -> float:
        return self.amount * self.per_unit_basis

    def days_held(self, as_of: Optional[datetime] = None) -> int:
        ref = as_of or datetime.now()
        # Normalize both to naive datetimes for comparison
        acq = self.acquisition_date.replace(tzinfo=None)
        ref = ref.replace(tzinfo=None)
        return (ref - acq).days

    def is_long_term(self, as_of: Optional[datetime] = None) -> bool:
        return self.days_held(as_of) >= 365

    def days_until_long_term(self, as_of: Optional[datetime] = None) -> int:
        remaining = 365 - self.days_held(as_of)
        return max(0, remaining)


@dataclass
class RealizedGain:
    """A realized gain or loss from a sale."""

    token: str
    sell_date: datetime
    amount_sold: float
    proceeds: float
    cost_basis: float
    gain: float
    gain_type: GainType
    holding_days: int


@dataclass
class TaxSignal:
    """A tax-aware trading signal."""

    signal_type: str
    token: str
    message: str
    value: Optional[float] = None


@dataclass
class PositionSummary:
    """Summary of a token position for display."""

    token: str
    total_amount: float
    total_cost_basis: float
    realized_gain: float
    unrealized_gain: float
    gain_type: str
    remaining_cost_basis: float
    lots: int


@dataclass
class QuarterlyEstimate:
    """Estimated tax liability for a quarter."""

    quarter: str
    period_start: str
    period_end: str
    due_date: str
    short_term_gains: float
    long_term_gains: float
    estimated_federal: float
    estimated_state: float
    estimated_total: float


# ── Tax Tracker ─────────────────────────────────────────────────────


class TaxTracker:
    """Real-time tax liability tracker with proportional cost basis.

    Tracks tax lots, computes proportional cost basis on partial sells,
    classifies gains as short-term or long-term, and generates tax-aware
    trading signals.

    Args:
        accounting_method: "fifo" or "lifo" for lot selection order.
        federal_bracket: Marginal federal income tax rate (0.0-0.37).
        state_rate: State income tax rate (0.0-0.133).
        long_term_rate: Long-term capital gains rate (0.0, 0.15, or 0.20).
    """

    def __init__(
        self,
        accounting_method: str = "fifo",
        federal_bracket: float = 0.32,
        state_rate: float = 0.05,
        long_term_rate: float = 0.15,
    ) -> None:
        self.accounting_method = AccountingMethod(accounting_method)
        self.federal_bracket = federal_bracket
        self.state_rate = state_rate
        self.long_term_rate = long_term_rate

        self.lots: dict[str, list[TaxLot]] = {}
        self.realized_gains: list[RealizedGain] = []
        self.trades: list[Trade] = []

    def add_trade(self, trade: Trade) -> Optional[list[RealizedGain]]:
        """Record a trade and update tax lots.

        For buys, creates a new tax lot. For sells, consumes lots using
        the configured accounting method and records realized gains.

        Args:
            trade: The trade to record.

        Returns:
            List of realized gains for sell trades, None for buys.
        """
        self.trades.append(trade)

        if trade.side == "buy":
            return self._process_buy(trade)
        elif trade.side == "sell":
            return self._process_sell(trade)
        else:
            raise ValueError(f"Unknown trade side: {trade.side}")

    def _process_buy(self, trade: Trade) -> None:
        """Create a new tax lot from a buy trade."""
        lot = TaxLot(
            acquisition_date=trade.dt,
            amount=trade.amount,
            per_unit_basis=trade.price_usd,
            token=trade.token,
        )
        if trade.token not in self.lots:
            self.lots[trade.token] = []
        self.lots[trade.token].append(lot)
        return None

    def _process_sell(self, trade: Trade) -> list[RealizedGain]:
        """Consume tax lots and record realized gains from a sell trade.

        Uses proportional cost basis: each lot's basis is allocated
        proportionally to the amount sold from that lot.
        """
        if trade.token not in self.lots or not self.lots[trade.token]:
            raise ValueError(
                f"No tax lots for {trade.token} — cannot sell what you don't own"
            )

        token_lots = self.lots[trade.token]
        if self.accounting_method == AccountingMethod.LIFO:
            token_lots = list(reversed(token_lots))

        remaining_to_sell = trade.amount
        sell_price = trade.price_usd
        sell_date = trade.dt
        gains: list[RealizedGain] = []

        lots_to_remove: list[int] = []

        for i, lot in enumerate(token_lots):
            if remaining_to_sell <= 0:
                break

            if lot.amount <= remaining_to_sell:
                # Consume entire lot
                amount_from_lot = lot.amount
                basis_from_lot = lot.total_basis
                lots_to_remove.append(i)
            else:
                # Partial consumption — proportional basis
                amount_from_lot = remaining_to_sell
                basis_from_lot = amount_from_lot * lot.per_unit_basis
                lot.amount -= amount_from_lot

            proceeds = amount_from_lot * sell_price
            gain_amount = proceeds - basis_from_lot
            holding_days = (sell_date - lot.acquisition_date).days

            gain = RealizedGain(
                token=trade.token,
                sell_date=sell_date,
                amount_sold=amount_from_lot,
                proceeds=proceeds,
                cost_basis=basis_from_lot,
                gain=gain_amount,
                gain_type=(
                    GainType.LONG_TERM
                    if holding_days >= 365
                    else GainType.SHORT_TERM
                ),
                holding_days=holding_days,
            )
            gains.append(gain)
            self.realized_gains.append(gain)
            remaining_to_sell -= amount_from_lot

        # Remove fully consumed lots (reverse order to preserve indices)
        original_lots = self.lots[trade.token]
        for i in sorted(lots_to_remove, reverse=True):
            if self.accounting_method == AccountingMethod.LIFO:
                actual_idx = len(original_lots) - 1 - i
            else:
                actual_idx = i
            original_lots.pop(actual_idx)

        if remaining_to_sell > 1e-10:
            raise ValueError(
                f"Tried to sell {trade.amount} {trade.token} but only had "
                f"{trade.amount - remaining_to_sell} in tax lots"
            )

        return gains

    def position_summary(self, token: str) -> PositionSummary:
        """Get a summary of current position and realized gains for a token.

        Args:
            token: The token symbol.

        Returns:
            PositionSummary with current holdings and realized gain totals.
        """
        lots = self.lots.get(token, [])
        total_amount = sum(lot.amount for lot in lots)
        total_basis = sum(lot.total_basis for lot in lots)

        token_gains = [g for g in self.realized_gains if g.token == token]
        realized = sum(g.gain for g in token_gains)

        gain_types = set(g.gain_type.value for g in token_gains)
        if len(gain_types) == 1:
            gain_type = gain_types.pop()
        elif len(gain_types) > 1:
            gain_type = "mixed"
        else:
            gain_type = "none"

        return PositionSummary(
            token=token,
            total_amount=total_amount,
            total_cost_basis=total_basis,
            realized_gain=realized,
            unrealized_gain=0.0,
            gain_type=gain_type,
            remaining_cost_basis=total_basis,
            lots=len(lots),
        )

    def get_signals(
        self, token: str, current_price_usd: float
    ) -> list[TaxSignal]:
        """Generate tax-aware trading signals for a token.

        Args:
            token: The token symbol.
            current_price_usd: Current per-unit price in USD.

        Returns:
            List of tax-aware signals.
        """
        signals: list[TaxSignal] = []
        lots = self.lots.get(token, [])
        if not lots:
            return signals

        now = datetime.now()

        # Long-term threshold countdown
        for lot in lots:
            days_left = lot.days_until_long_term(now)
            if 0 < days_left <= 90:
                target_date = lot.acquisition_date + timedelta(days=365)
                signals.append(TaxSignal(
                    signal_type="long_term_countdown",
                    token=token,
                    message=(
                        f"{lot.amount:.0f} tokens cross long-term threshold "
                        f"in {days_left} days ({target_date.strftime('%Y-%m-%d')})"
                    ),
                    value=float(days_left),
                ))

        # Profit-taking tax cost
        total_amount = sum(lot.amount for lot in lots)
        total_basis = sum(lot.total_basis for lot in lots)
        market_value = total_amount * current_price_usd
        unrealized = market_value - total_basis

        if unrealized > 0:
            st_lots = [l for l in lots if not l.is_long_term(now)]
            st_amount = sum(l.amount for l in st_lots)
            st_basis = sum(l.total_basis for l in st_lots)
            st_value = st_amount * current_price_usd
            st_gain = st_value - st_basis

            if st_gain > 0:
                st_tax = st_gain * self.federal_bracket
                signals.append(TaxSignal(
                    signal_type="profit_taking_cost",
                    token=token,
                    message=(
                        f"Taking full profit triggers ${st_tax:,.2f} "
                        f"short-term federal liability on ${st_gain:,.2f} gain"
                    ),
                    value=st_tax,
                ))

        # Loss harvesting opportunity
        if unrealized < 0:
            tax_savings = abs(unrealized) * self.federal_bracket
            signals.append(TaxSignal(
                signal_type="loss_harvest",
                token=token,
                message=(
                    f"${abs(unrealized):,.2f} unrealized loss available to harvest "
                    f"(saves ~${tax_savings:,.2f} in taxes)"
                ),
                value=abs(unrealized),
            ))

        # General unrealized position info
        if unrealized != 0:
            direction = "gain" if unrealized > 0 else "loss"
            signals.append(TaxSignal(
                signal_type="unrealized_position",
                token=token,
                message=(
                    f"Unrealized {direction}: ${abs(unrealized):,.2f} "
                    f"on {total_amount:,.0f} tokens "
                    f"(basis: ${total_basis:,.2f}, market: ${market_value:,.2f})"
                ),
                value=unrealized,
            ))

        return signals

    def quarterly_projection(self, tax_year: int = 2025) -> list[QuarterlyEstimate]:
        """Project quarterly estimated tax payments.

        Allocates realized gains to quarters based on sell date and
        computes estimated federal + state liability per quarter.

        Args:
            tax_year: The tax year to project for.

        Returns:
            List of QuarterlyEstimate objects, one per quarter.
        """
        quarters = [
            ("Q1", f"{tax_year}-01-01", f"{tax_year}-03-31", f"{tax_year}-04-15"),
            ("Q2", f"{tax_year}-04-01", f"{tax_year}-05-31", f"{tax_year}-06-15"),
            ("Q3", f"{tax_year}-06-01", f"{tax_year}-08-31", f"{tax_year}-09-15"),
            ("Q4", f"{tax_year}-09-01", f"{tax_year}-12-31", f"{tax_year + 1}-01-15"),
        ]

        estimates: list[QuarterlyEstimate] = []

        for label, start_str, end_str, due_str in quarters:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str + "T23:59:59")

            q_gains = [
                g for g in self.realized_gains
                if start <= g.sell_date.replace(tzinfo=None) <= end
            ]

            st_gains = sum(
                g.gain for g in q_gains if g.gain_type == GainType.SHORT_TERM
            )
            lt_gains = sum(
                g.gain for g in q_gains if g.gain_type == GainType.LONG_TERM
            )

            federal = (
                max(0, st_gains) * self.federal_bracket
                + max(0, lt_gains) * self.long_term_rate
            )
            state = max(0, st_gains + lt_gains) * self.state_rate
            total = federal + state

            estimates.append(QuarterlyEstimate(
                quarter=label,
                period_start=start_str,
                period_end=end_str,
                due_date=due_str,
                short_term_gains=st_gains,
                long_term_gains=lt_gains,
                estimated_federal=federal,
                estimated_state=state,
                estimated_total=total,
            ))

        return estimates

    def after_tax_pnl(self) -> dict[str, float]:
        """Compute aggregate after-tax P&L from all realized gains.

        Returns:
            Dictionary with gross_pnl, estimated_tax, and after_tax_pnl.
        """
        st_gains = sum(
            g.gain for g in self.realized_gains
            if g.gain_type == GainType.SHORT_TERM
        )
        lt_gains = sum(
            g.gain for g in self.realized_gains
            if g.gain_type == GainType.LONG_TERM
        )

        gross = st_gains + lt_gains
        federal = (
            max(0, st_gains) * self.federal_bracket
            + max(0, lt_gains) * self.long_term_rate
        )
        state = max(0, gross) * self.state_rate
        total_tax = federal + state

        return {
            "gross_pnl": gross,
            "short_term_gains": st_gains,
            "long_term_gains": lt_gains,
            "estimated_federal_tax": federal,
            "estimated_state_tax": state,
            "estimated_total_tax": total_tax,
            "after_tax_pnl": gross - total_tax,
        }


# ── Demo ────────────────────────────────────────────────────────────


def print_header(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def run_demo() -> None:
    """Run the accumulate/house-money demo scenario.

    Demonstrates:
    1. Buy tokens
    2. Partial sell to recover capital (proportional cost basis)
    3. Position summary showing correct basis allocation
    4. Tax-aware signals on remaining position
    5. Quarterly tax projection
    6. After-tax P&L
    """
    print_header("Tax Liability Tracker — Demo Scenario")
    print("\nScenario: Accumulate / House-Money Play on BONK")
    print("Accounting method: FIFO")
    print("Federal bracket: 32% | State rate: 5% | LT rate: 15%")

    tracker = TaxTracker(
        accounting_method="fifo",
        federal_bracket=0.32,
        state_rate=0.05,
        long_term_rate=0.15,
    )

    # ── Step 1: Buy ─────────────────────────────────────────────────

    print_header("Step 1: Buy 1,000,000 BONK at $0.00002")

    buy_trade = Trade(
        timestamp="2025-06-15T10:00:00Z",
        side="buy",
        token="BONK",
        amount=1_000_000,
        price_usd=0.00002,
        total_usd=20.00,
    )
    tracker.add_trade(buy_trade)

    summary = tracker.position_summary("BONK")
    print(f"  Amount: {summary.total_amount:,.0f} BONK")
    print(f"  Cost basis: ${summary.total_cost_basis:.2f}")
    print(f"  Per-unit basis: ${summary.total_cost_basis / summary.total_amount:.8f}")
    print(f"  Tax lots: {summary.lots}")

    # ── Step 2: Partial sell (recover capital) ──────────────────────

    print_header("Step 2: Sell 800,000 BONK at $0.000025 (recover capital)")

    sell_trade = Trade(
        timestamp="2025-07-20T14:30:00Z",
        side="sell",
        token="BONK",
        amount=800_000,
        price_usd=0.000025,
        total_usd=20.00,
    )
    gains = tracker.add_trade(sell_trade)

    print("\n  Realized gains from partial sell:")
    for g in gains:
        print(f"    Amount sold: {g.amount_sold:,.0f} BONK")
        print(f"    Proceeds: ${g.proceeds:.2f}")
        print(f"    Cost basis: ${g.cost_basis:.2f}")
        print(f"    Gain: ${g.gain:.2f}")
        print(f"    Type: {g.gain_type.value} ({g.holding_days} days)")

    # ── Step 3: Position summary ────────────────────────────────────

    print_header("Step 3: Remaining Position")

    summary = tracker.position_summary("BONK")
    print(f"  Remaining amount: {summary.total_amount:,.0f} BONK")
    print(f"  Remaining cost basis: ${summary.remaining_cost_basis:.2f}")
    if summary.total_amount > 0:
        print(
            f"  Per-unit basis: "
            f"${summary.remaining_cost_basis / summary.total_amount:.8f}"
        )
    print(f"  Total realized gain: ${summary.realized_gain:.2f}")
    print(f"  Gain classification: {summary.gain_type}")

    print("\n  KEY INSIGHT: The remaining 200,000 BONK have basis = $4.00")
    print("  (200,000 x $0.00002 = $4.00), NOT $0.00")
    print("  The $4.00 realized gain came from the partial sell,")
    print("  not deferred to the remaining position.")

    # ── Step 4: Tax-aware signals ───────────────────────────────────

    print_header("Step 4: Tax-Aware Signals")
    print("  (Current BONK price: $0.00005 — 2.5x from entry)")

    signals = tracker.get_signals("BONK", current_price_usd=0.00005)
    if signals:
        for s in signals:
            print(f"  [{s.signal_type}] {s.message}")
    else:
        print("  No signals generated.")

    # ── Step 5: Sell remaining at a profit ──────────────────────────

    print_header("Step 5: Sell remaining 200,000 BONK at $0.00005")

    final_sell = Trade(
        timestamp="2025-08-10T09:00:00Z",
        side="sell",
        token="BONK",
        amount=200_000,
        price_usd=0.00005,
        total_usd=10.00,
    )
    gains2 = tracker.add_trade(final_sell)

    print("\n  Realized gains from final sell:")
    for g in gains2:
        print(f"    Amount sold: {g.amount_sold:,.0f} BONK")
        print(f"    Proceeds: ${g.proceeds:.2f}")
        print(f"    Cost basis: ${g.cost_basis:.2f}")
        print(f"    Gain: ${g.gain:.2f}")
        print(f"    Type: {g.gain_type.value} ({g.holding_days} days)")

    # ── Step 6: Quarterly projection ────────────────────────────────

    print_header("Step 6: Quarterly Tax Projection (2025)")

    estimates = tracker.quarterly_projection(tax_year=2025)
    for est in estimates:
        if est.short_term_gains != 0 or est.long_term_gains != 0:
            print(f"\n  {est.quarter} ({est.period_start} to {est.period_end})")
            print(f"    Due: {est.due_date}")
            print(f"    Short-term gains: ${est.short_term_gains:,.2f}")
            print(f"    Long-term gains:  ${est.long_term_gains:,.2f}")
            print(f"    Federal estimate: ${est.estimated_federal:,.2f}")
            print(f"    State estimate:   ${est.estimated_state:,.2f}")
            print(f"    Total estimate:   ${est.estimated_total:,.2f}")

    # ── Step 7: After-tax P&L ───────────────────────────────────────

    print_header("Step 7: After-Tax P&L Summary")

    pnl = tracker.after_tax_pnl()
    print(f"  Gross P&L:           ${pnl['gross_pnl']:,.2f}")
    print(f"    Short-term gains:  ${pnl['short_term_gains']:,.2f}")
    print(f"    Long-term gains:   ${pnl['long_term_gains']:,.2f}")
    print(f"  Federal tax est:     ${pnl['estimated_federal_tax']:,.2f}")
    print(f"  State tax est:       ${pnl['estimated_state_tax']:,.2f}")
    print(f"  Total tax est:       ${pnl['estimated_total_tax']:,.2f}")
    print(f"  After-tax P&L:       ${pnl['after_tax_pnl']:,.2f}")

    # ── Verification ────────────────────────────────────────────────

    print_header("Verification")
    total_proceeds = 20.00 + 10.00  # $20 from partial + $10 from final
    total_basis = 20.00  # Original purchase
    expected_gain = total_proceeds - total_basis
    actual_gain = pnl["gross_pnl"]
    print(f"  Total proceeds:  ${total_proceeds:.2f}")
    print(f"  Total basis:     ${total_basis:.2f}")
    print(f"  Expected gain:   ${expected_gain:.2f}")
    print(f"  Tracked gain:    ${actual_gain:.2f}")
    print(f"  Match: {'YES' if abs(expected_gain - actual_gain) < 0.01 else 'NO'}")

    print(f"\n{'=' * 60}")
    print("  DISCLAIMER: Tax calculations are for informational")
    print("  tracking purposes only. Consult a qualified tax")
    print("  professional for actual tax filing.")
    print(f"{'=' * 60}\n")


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tax liability tracker for active crypto traders"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Run the demo scenario (default)",
    )
    args = parser.parse_args()

    run_demo()
