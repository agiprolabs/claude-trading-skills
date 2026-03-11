#!/usr/bin/env python3
"""Cost basis calculator supporting FIFO, LIFO, HIFO, Specific ID, and Average Cost.

Computes cost basis under all five methods for the same trade history,
then displays a comparison table showing which method minimizes tax liability.

Usage:
    python scripts/cost_basis_calculator.py
    python scripts/cost_basis_calculator.py --demo

Dependencies:
    None (standard library only)

Environment Variables:
    None required.
"""

import argparse
import copy
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────

@dataclass
class Lot:
    """A single tax lot representing an acquisition of tokens."""
    lot_id: str
    date: str
    token: str
    qty: float
    cost_per_unit: float
    source: str = "purchase"  # purchase, airdrop, staking, lp_redemption

    @property
    def total_cost(self) -> float:
        return self.qty * self.cost_per_unit

    def __repr__(self) -> str:
        return (f"Lot({self.lot_id}: {self.qty:.4f} {self.token} "
                f"@ ${self.cost_per_unit:.4f}, {self.date})")


@dataclass
class RealizedGain:
    """A single realized gain/loss event from a sale."""
    sell_date: str
    token: str
    qty: float
    proceeds_per_unit: float
    cost_per_unit: float
    lot_id: str
    source: str = "purchase"

    @property
    def proceeds(self) -> float:
        return self.qty * self.proceeds_per_unit

    @property
    def basis(self) -> float:
        return self.qty * self.cost_per_unit

    @property
    def gain(self) -> float:
        return self.proceeds - self.basis


@dataclass
class MethodResult:
    """Result of processing all trades under a single method."""
    method: str
    realized_gains: list[RealizedGain] = field(default_factory=list)
    remaining_lots: list[Lot] = field(default_factory=list)

    @property
    def total_gain(self) -> float:
        return sum(g.gain for g in self.realized_gains)

    @property
    def total_proceeds(self) -> float:
        return sum(g.proceeds for g in self.realized_gains)

    @property
    def total_basis_used(self) -> float:
        return sum(g.basis for g in self.realized_gains)

    @property
    def remaining_basis(self) -> float:
        return sum(lot.total_cost for lot in self.remaining_lots)


# ── Trade Record ────────────────────────────────────────────────────

@dataclass
class Trade:
    """A single trade action."""
    date: str
    action: str  # buy, sell, airdrop, staking_reward, split
    token: str
    qty: float
    price_usd: float
    fee_usd: float = 0.0
    lot_ids: Optional[list[tuple[str, float]]] = None  # For specific ID sells
    split_ratio: float = 1.0  # For splits


# ── Core Engine ─────────────────────────────────────────────────────

class CostBasisEngine:
    """Multi-method cost basis computation engine."""

    def __init__(self) -> None:
        self._trades: list[Trade] = []
        self._lot_counter: int = 0

    def _next_lot_id(self) -> str:
        self._lot_counter += 1
        return f"L{self._lot_counter:04d}"

    def add_buy(self, date: str, token: str, qty: float, price_usd: float,
                fee_usd: float = 0.0) -> None:
        """Record a token purchase."""
        self._trades.append(Trade(date=date, action="buy", token=token,
                                  qty=qty, price_usd=price_usd, fee_usd=fee_usd))

    def add_sell(self, date: str, token: str, qty: float, price_usd: float,
                 fee_usd: float = 0.0,
                 lot_ids: Optional[list[tuple[str, float]]] = None) -> None:
        """Record a token sale. lot_ids used only for specific identification."""
        self._trades.append(Trade(date=date, action="sell", token=token,
                                  qty=qty, price_usd=price_usd, fee_usd=fee_usd,
                                  lot_ids=lot_ids))

    def add_airdrop(self, date: str, token: str, qty: float,
                    fmv_usd: float) -> None:
        """Record an airdrop (income at FMV)."""
        self._trades.append(Trade(date=date, action="airdrop", token=token,
                                  qty=qty, price_usd=fmv_usd))

    def add_staking_reward(self, date: str, token: str, qty: float,
                           fmv_usd: float) -> None:
        """Record a staking reward (income at FMV)."""
        self._trades.append(Trade(date=date, action="staking_reward",
                                  token=token, qty=qty, price_usd=fmv_usd))

    def add_split(self, date: str, token: str, split_ratio: float) -> None:
        """Record a token split (e.g., 10.0 for 1:10 split)."""
        self._trades.append(Trade(date=date, action="split", token=token,
                                  qty=0, price_usd=0, split_ratio=split_ratio))

    # ── Method Implementations ──────────────────────────────────────

    def _process_fifo(self, trades: list[Trade]) -> MethodResult:
        """Process trades using FIFO method."""
        lots: list[Lot] = []
        result = MethodResult(method="FIFO")

        for trade in trades:
            if trade.action in ("buy", "airdrop", "staking_reward"):
                cost = trade.price_usd + (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                lots.append(Lot(lot_id=self._next_lot_id(), date=trade.date,
                                token=trade.token, qty=trade.qty,
                                cost_per_unit=cost, source=trade.action))
            elif trade.action == "sell":
                token_lots = [l for l in lots if l.token == trade.token]
                token_lots.sort(key=lambda l: l.date)  # oldest first
                remaining = trade.qty
                sell_price = trade.price_usd - (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                for lot in token_lots:
                    if remaining <= 0:
                        break
                    used = min(lot.qty, remaining)
                    result.realized_gains.append(RealizedGain(
                        sell_date=trade.date, token=trade.token, qty=used,
                        proceeds_per_unit=sell_price, cost_per_unit=lot.cost_per_unit,
                        lot_id=lot.lot_id, source=lot.source))
                    lot.qty -= used
                    remaining -= used
                lots[:] = [l for l in lots if l.qty > 1e-12]
            elif trade.action == "split":
                for lot in lots:
                    if lot.token == trade.token:
                        lot.qty *= trade.split_ratio
                        lot.cost_per_unit /= trade.split_ratio

        result.remaining_lots = [l for l in lots if l.qty > 1e-12]
        return result

    def _process_lifo(self, trades: list[Trade]) -> MethodResult:
        """Process trades using LIFO method."""
        lots: list[Lot] = []
        result = MethodResult(method="LIFO")

        for trade in trades:
            if trade.action in ("buy", "airdrop", "staking_reward"):
                cost = trade.price_usd + (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                lots.append(Lot(lot_id=self._next_lot_id(), date=trade.date,
                                token=trade.token, qty=trade.qty,
                                cost_per_unit=cost, source=trade.action))
            elif trade.action == "sell":
                token_lots = [l for l in lots if l.token == trade.token]
                token_lots.sort(key=lambda l: l.date, reverse=True)  # newest first
                remaining = trade.qty
                sell_price = trade.price_usd - (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                for lot in token_lots:
                    if remaining <= 0:
                        break
                    used = min(lot.qty, remaining)
                    result.realized_gains.append(RealizedGain(
                        sell_date=trade.date, token=trade.token, qty=used,
                        proceeds_per_unit=sell_price, cost_per_unit=lot.cost_per_unit,
                        lot_id=lot.lot_id, source=lot.source))
                    lot.qty -= used
                    remaining -= used
                lots[:] = [l for l in lots if l.qty > 1e-12]
            elif trade.action == "split":
                for lot in lots:
                    if lot.token == trade.token:
                        lot.qty *= trade.split_ratio
                        lot.cost_per_unit /= trade.split_ratio

        result.remaining_lots = [l for l in lots if l.qty > 1e-12]
        return result

    def _process_hifo(self, trades: list[Trade]) -> MethodResult:
        """Process trades using HIFO (Highest-In, First-Out) method."""
        lots: list[Lot] = []
        result = MethodResult(method="HIFO")

        for trade in trades:
            if trade.action in ("buy", "airdrop", "staking_reward"):
                cost = trade.price_usd + (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                lots.append(Lot(lot_id=self._next_lot_id(), date=trade.date,
                                token=trade.token, qty=trade.qty,
                                cost_per_unit=cost, source=trade.action))
            elif trade.action == "sell":
                token_lots = [l for l in lots if l.token == trade.token]
                token_lots.sort(key=lambda l: l.cost_per_unit, reverse=True)  # highest cost first
                remaining = trade.qty
                sell_price = trade.price_usd - (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                for lot in token_lots:
                    if remaining <= 0:
                        break
                    used = min(lot.qty, remaining)
                    result.realized_gains.append(RealizedGain(
                        sell_date=trade.date, token=trade.token, qty=used,
                        proceeds_per_unit=sell_price, cost_per_unit=lot.cost_per_unit,
                        lot_id=lot.lot_id, source=lot.source))
                    lot.qty -= used
                    remaining -= used
                lots[:] = [l for l in lots if l.qty > 1e-12]
            elif trade.action == "split":
                for lot in lots:
                    if lot.token == trade.token:
                        lot.qty *= trade.split_ratio
                        lot.cost_per_unit /= trade.split_ratio

        result.remaining_lots = [l for l in lots if l.qty > 1e-12]
        return result

    def _process_average(self, trades: list[Trade]) -> MethodResult:
        """Process trades using Average Cost method."""
        avg_costs: dict[str, float] = {}
        quantities: dict[str, float] = {}
        result = MethodResult(method="Average Cost")

        for trade in trades:
            token = trade.token
            if trade.action in ("buy", "airdrop", "staking_reward"):
                cost = trade.price_usd + (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                old_qty = quantities.get(token, 0.0)
                old_avg = avg_costs.get(token, 0.0)
                new_qty = old_qty + trade.qty
                if new_qty > 0:
                    avg_costs[token] = (old_avg * old_qty + cost * trade.qty) / new_qty
                quantities[token] = new_qty
            elif trade.action == "sell":
                avg = avg_costs.get(token, 0.0)
                sell_qty = min(trade.qty, quantities.get(token, 0.0))
                sell_price = trade.price_usd - (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                if sell_qty > 0:
                    result.realized_gains.append(RealizedGain(
                        sell_date=trade.date, token=token, qty=sell_qty,
                        proceeds_per_unit=sell_price, cost_per_unit=avg,
                        lot_id="AVG", source="average"))
                    quantities[token] = quantities.get(token, 0.0) - sell_qty
            elif trade.action == "split":
                if token in quantities and quantities[token] > 0:
                    quantities[token] *= trade.split_ratio
                    avg_costs[token] /= trade.split_ratio

        for token, qty in quantities.items():
            if qty > 1e-12:
                result.remaining_lots.append(Lot(
                    lot_id="AVG", date="aggregate", token=token,
                    qty=qty, cost_per_unit=avg_costs.get(token, 0.0),
                    source="average"))
        return result

    def _process_specific_id(self, trades: list[Trade]) -> MethodResult:
        """Process trades using Specific Identification.

        Falls back to HIFO ordering when lot_ids are not specified on a sell.
        """
        lots: list[Lot] = []
        lot_map: dict[str, Lot] = {}
        result = MethodResult(method="Specific ID")

        for trade in trades:
            if trade.action in ("buy", "airdrop", "staking_reward"):
                cost = trade.price_usd + (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                lot = Lot(lot_id=self._next_lot_id(), date=trade.date,
                          token=trade.token, qty=trade.qty,
                          cost_per_unit=cost, source=trade.action)
                lots.append(lot)
                lot_map[lot.lot_id] = lot
            elif trade.action == "sell":
                sell_price = trade.price_usd - (trade.fee_usd / trade.qty if trade.qty > 0 else 0)
                if trade.lot_ids:
                    for lot_id, qty_to_sell in trade.lot_ids:
                        if lot_id in lot_map:
                            lot = lot_map[lot_id]
                            used = min(lot.qty, qty_to_sell)
                            result.realized_gains.append(RealizedGain(
                                sell_date=trade.date, token=trade.token,
                                qty=used, proceeds_per_unit=sell_price,
                                cost_per_unit=lot.cost_per_unit,
                                lot_id=lot.lot_id, source=lot.source))
                            lot.qty -= used
                else:
                    # Fallback: HIFO ordering when no specific lots designated
                    token_lots = [l for l in lots if l.token == trade.token and l.qty > 1e-12]
                    token_lots.sort(key=lambda l: l.cost_per_unit, reverse=True)
                    remaining = trade.qty
                    for lot in token_lots:
                        if remaining <= 0:
                            break
                        used = min(lot.qty, remaining)
                        result.realized_gains.append(RealizedGain(
                            sell_date=trade.date, token=trade.token,
                            qty=used, proceeds_per_unit=sell_price,
                            cost_per_unit=lot.cost_per_unit,
                            lot_id=lot.lot_id, source=lot.source))
                        lot.qty -= used
                        remaining -= used
                lots[:] = [l for l in lots if l.qty > 1e-12]
                lot_map = {l.lot_id: l for l in lots}
            elif trade.action == "split":
                for lot in lots:
                    if lot.token == trade.token:
                        lot.qty *= trade.split_ratio
                        lot.cost_per_unit /= trade.split_ratio

        result.remaining_lots = [l for l in lots if l.qty > 1e-12]
        return result

    # ── Public API ──────────────────────────────────────────────────

    def compute_all_methods(self) -> dict[str, MethodResult]:
        """Run all trades through every method and return results."""
        self._lot_counter = 0
        results: dict[str, MethodResult] = {}

        for name, processor in [
            ("FIFO", self._process_fifo),
            ("LIFO", self._process_lifo),
            ("HIFO", self._process_hifo),
            ("Average Cost", self._process_average),
            ("Specific ID", self._process_specific_id),
        ]:
            self._lot_counter = 0
            results[name] = processor(list(self._trades))

        return results

    def sell_compare(self, date: str, token: str, qty: float,
                     price_usd: float) -> dict[str, MethodResult]:
        """Add a sell and compute comparison across all methods."""
        self.add_sell(date, token, qty, price_usd)
        return self.compute_all_methods()

    def print_comparison(self, results: dict[str, MethodResult],
                         tax_rate: float = 0.30) -> None:
        """Print a formatted comparison table."""
        print("\n" + "=" * 78)
        print("COST BASIS METHOD COMPARISON")
        print("=" * 78)
        print(f"{'Method':<16} {'Proceeds':>12} {'Basis Used':>12} "
              f"{'Gain/Loss':>12} {'Tax @{:.0%}'.format(tax_rate):>12} "
              f"{'Rem. Basis':>12}")
        print("-" * 78)

        best_method = ""
        best_tax = float("inf")

        for name, res in results.items():
            tax = res.total_gain * tax_rate if res.total_gain > 0 else 0.0
            print(f"{name:<16} {res.total_proceeds:>12,.2f} "
                  f"{res.total_basis_used:>12,.2f} "
                  f"{res.total_gain:>12,.2f} {tax:>12,.2f} "
                  f"{res.remaining_basis:>12,.2f}")
            if tax < best_tax:
                best_tax = tax
                best_method = name

        print("-" * 78)
        print(f">>> Lowest current liability: {best_method} "
              f"(${best_tax:,.2f} estimated tax)")
        print("=" * 78)

    def print_detailed(self, result: MethodResult) -> None:
        """Print detailed lot-by-lot gains for a single method."""
        print(f"\n--- {result.method} Detail ---")
        for g in result.realized_gains:
            direction = "GAIN" if g.gain >= 0 else "LOSS"
            print(f"  {g.sell_date} | Sell {g.qty:>10.4f} {g.token} | "
                  f"Proceeds ${g.proceeds:>10.2f} | Basis ${g.basis:>10.2f} | "
                  f"{direction} ${abs(g.gain):>10.2f} | Lot {g.lot_id}")
        if result.remaining_lots:
            print(f"  Remaining lots:")
            for lot in result.remaining_lots:
                print(f"    {lot.lot_id}: {lot.qty:.4f} {lot.token} "
                      f"@ ${lot.cost_per_unit:.4f} "
                      f"(basis ${lot.total_cost:.2f})")


# ── Demo Data ───────────────────────────────────────────────────────

def build_demo_trades() -> CostBasisEngine:
    """Build a realistic demo trade history with accumulation and partial sells.

    Scenario: A trader accumulates SOL and a memecoin (BONK) over several
    months, takes partial profits, receives staking rewards and an airdrop,
    and experiences a token split.

    Returns:
        Configured CostBasisEngine with all trades loaded.
    """
    engine = CostBasisEngine()

    # ── SOL accumulation (DCA pattern) ──────────────────────────────
    engine.add_buy("2025-01-05", "SOL", 10.0, 95.00)    # Buy 10 SOL @ $95
    engine.add_buy("2025-01-20", "SOL", 8.0, 105.00)    # Buy 8 SOL @ $105
    engine.add_buy("2025-02-10", "SOL", 12.0, 88.00)    # Buy 12 SOL @ $88 (dip)
    engine.add_buy("2025-03-01", "SOL", 5.0, 130.00)    # Buy 5 SOL @ $130

    # Staking rewards
    engine.add_staking_reward("2025-02-01", "SOL", 0.15, 100.00)
    engine.add_staking_reward("2025-03-01", "SOL", 0.18, 130.00)

    # Partial sell: take profit on 15 SOL at $140
    engine.add_sell("2025-03-15", "SOL", 15.0, 140.00, fee_usd=0.50)

    # ── BONK accumulation ───────────────────────────────────────────
    engine.add_buy("2025-01-10", "BONK", 5_000_000, 0.000025)
    engine.add_buy("2025-02-01", "BONK", 3_000_000, 0.000040)
    engine.add_buy("2025-02-20", "BONK", 2_000_000, 0.000018)

    # Airdrop of BONK
    engine.add_airdrop("2025-02-15", "BONK", 500_000, 0.000035)

    # Partial sell: 4 million BONK at $0.000055 (price pump)
    engine.add_sell("2025-03-10", "BONK", 4_000_000, 0.000055, fee_usd=0.10)

    # ── WIF with token split ────────────────────────────────────────
    engine.add_buy("2025-01-15", "WIF", 200, 2.50)
    engine.add_buy("2025-02-05", "WIF", 100, 3.20)

    # 1:5 token split
    engine.add_split("2025-02-28", "WIF", 5.0)

    # Sell 500 WIF (post-split) at $0.80
    engine.add_sell("2025-03-20", "WIF", 500, 0.80)

    return engine


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    """Run the cost basis calculator."""
    parser = argparse.ArgumentParser(
        description="Cost basis calculator with multi-method comparison")
    parser.add_argument("--demo", action="store_true",
                        help="Run with demo trade data")
    parser.add_argument("--tax-rate", type=float, default=0.30,
                        help="Tax rate for liability estimation (default: 0.30)")
    parser.add_argument("--detail", action="store_true",
                        help="Show detailed lot-by-lot breakdown for each method")
    args = parser.parse_args()

    if not args.demo:
        print("Cost Basis Calculator")
        print("Run with --demo to see a full example with realistic trades.")
        print("In production, use the CostBasisEngine class directly.")
        print("\nExample:")
        print("  python scripts/cost_basis_calculator.py --demo")
        print("  python scripts/cost_basis_calculator.py --demo --detail")
        print("  python scripts/cost_basis_calculator.py --demo --tax-rate 0.37")
        return

    print("=" * 78)
    print("COST BASIS ENGINE — DEMO")
    print("=" * 78)
    print()
    print("Scenario: Trader DCA-accumulates SOL and BONK, receives staking")
    print("rewards and an airdrop, experiences a WIF token split, and takes")
    print("partial profits on each position.")
    print()
    print("NOTE: This is for informational purposes only. Consult a tax")
    print("professional for advice on your specific situation.")
    print()

    engine = build_demo_trades()
    results = engine.compute_all_methods()

    # Print trade summary
    print("Trade Summary:")
    print("-" * 50)
    tokens_traded = set()
    buy_count = 0
    sell_count = 0
    for t in engine._trades:
        tokens_traded.add(t.token)
        if t.action == "buy":
            buy_count += 1
        elif t.action == "sell":
            sell_count += 1
    print(f"  Tokens: {', '.join(sorted(tokens_traded))}")
    print(f"  Buy events: {buy_count}")
    print(f"  Sell events: {sell_count}")
    print(f"  Special events: staking rewards, airdrop, token split")

    # Print comparison
    engine.print_comparison(results, tax_rate=args.tax_rate)

    # Print income events summary
    print("\nINCOME EVENTS (taxed as ordinary income):")
    print("-" * 50)
    for t in engine._trades:
        if t.action in ("airdrop", "staking_reward"):
            income = t.qty * t.price_usd
            label = "Airdrop" if t.action == "airdrop" else "Staking"
            print(f"  {t.date} | {label:>8} | {t.qty:>12.2f} {t.token} "
                  f"@ ${t.price_usd:.6f} = ${income:>10.2f} income")

    if args.detail:
        for name, res in results.items():
            engine.print_detailed(res)

    print()
    print("Disclaimer: This output is for informational and educational")
    print("purposes only. It does not constitute tax or financial advice.")


if __name__ == "__main__":
    main()
