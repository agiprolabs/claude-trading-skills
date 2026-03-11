#!/usr/bin/env python3
"""Constant Product AMM Calculator.

Simulates a constant product (xy=k) automated market maker with trade execution,
LP share calculations, fee accrual tracking, and multi-trade simulation.

Usage:
    python scripts/amm_calculator.py
    python scripts/amm_calculator.py --demo

Dependencies:
    None (pure math, standard library only)

Environment Variables:
    None required
"""

import argparse
import math
import sys
from dataclasses import dataclass, field
from typing import Optional


# ── Data Models ─────────────────────────────────────────────────────


@dataclass
class TradeResult:
    """Result of executing a trade against the AMM."""

    input_token: str
    output_token: str
    input_amount: float
    output_amount: float
    fee_amount: float
    spot_price_before: float
    spot_price_after: float
    execution_price: float
    price_impact_pct: float
    k_before: float
    k_after: float


@dataclass
class LPPosition:
    """An LP's position in the pool."""

    address: str
    shares: float
    deposit_x: float
    deposit_y: float


@dataclass
class ConstantProductPool:
    """A constant product (xy=k) AMM pool."""

    token_x: str
    token_y: str
    reserve_x: float
    reserve_y: float
    fee_rate: float  # e.g., 0.003 for 0.3%
    lp_fee_share: float  # fraction of fee going to LPs, e.g., 0.88
    total_shares: float = 0.0
    total_fees_x: float = 0.0
    total_fees_y: float = 0.0
    trade_count: int = 0
    positions: list = field(default_factory=list)

    @property
    def k(self) -> float:
        """Current invariant value."""
        return self.reserve_x * self.reserve_y

    @property
    def spot_price(self) -> float:
        """Price of token X in terms of token Y."""
        if self.reserve_x == 0:
            return 0.0
        return self.reserve_y / self.reserve_x

    @property
    def tvl(self) -> float:
        """Total value locked (in terms of token Y, assuming spot price)."""
        return self.reserve_y * 2  # Both sides equal value at equilibrium

    def swap_x_for_y(self, delta_x: float) -> TradeResult:
        """Swap token X into the pool for token Y.

        Args:
            delta_x: Amount of token X to sell.

        Returns:
            TradeResult with execution details.

        Raises:
            ValueError: If delta_x is non-positive or output exceeds reserves.
        """
        if delta_x <= 0:
            raise ValueError(f"Trade amount must be positive, got {delta_x}")

        spot_before = self.spot_price
        k_before = self.k

        # Apply fee to input
        fee_x = delta_x * self.fee_rate
        effective_input = delta_x - fee_x

        # Calculate output
        delta_y = self.reserve_y * effective_input / (self.reserve_x + effective_input)

        if delta_y >= self.reserve_y:
            raise ValueError(
                f"Output {delta_y:.4f} {self.token_y} exceeds reserves "
                f"{self.reserve_y:.4f} {self.token_y}"
            )

        # Update reserves
        self.reserve_x += delta_x  # Full input (fee stays in pool as X)
        self.reserve_y -= delta_y

        # Track fees and trades
        self.total_fees_x += fee_x
        self.trade_count += 1

        spot_after = self.spot_price
        execution_price = delta_y / delta_x if delta_x > 0 else 0
        price_impact = 1 - (execution_price / spot_before) if spot_before > 0 else 0

        return TradeResult(
            input_token=self.token_x,
            output_token=self.token_y,
            input_amount=delta_x,
            output_amount=delta_y,
            fee_amount=fee_x,
            spot_price_before=spot_before,
            spot_price_after=spot_after,
            execution_price=execution_price,
            price_impact_pct=price_impact * 100,
            k_before=k_before,
            k_after=self.k,
        )

    def swap_y_for_x(self, delta_y: float) -> TradeResult:
        """Swap token Y into the pool for token X.

        Args:
            delta_y: Amount of token Y to sell.

        Returns:
            TradeResult with execution details.

        Raises:
            ValueError: If delta_y is non-positive or output exceeds reserves.
        """
        if delta_y <= 0:
            raise ValueError(f"Trade amount must be positive, got {delta_y}")

        spot_before = self.spot_price
        k_before = self.k

        fee_y = delta_y * self.fee_rate
        effective_input = delta_y - fee_y

        delta_x = self.reserve_x * effective_input / (self.reserve_y + effective_input)

        if delta_x >= self.reserve_x:
            raise ValueError(
                f"Output {delta_x:.4f} {self.token_x} exceeds reserves "
                f"{self.reserve_x:.4f} {self.token_x}"
            )

        self.reserve_y += delta_y
        self.reserve_x -= delta_x

        self.total_fees_y += fee_y
        self.trade_count += 1

        spot_after = self.spot_price
        # Price in terms of Y per X; buying X means inverse
        execution_price_y_per_x = delta_y / delta_x if delta_x > 0 else 0
        price_impact = (execution_price_y_per_x / spot_before - 1) if spot_before > 0 else 0

        return TradeResult(
            input_token=self.token_y,
            output_token=self.token_x,
            input_amount=delta_y,
            output_amount=delta_x,
            fee_amount=fee_y,
            spot_price_before=spot_before,
            spot_price_after=spot_after,
            execution_price=execution_price_y_per_x,
            price_impact_pct=price_impact * 100,
            k_before=k_before,
            k_after=self.k,
        )

    def calculate_required_input_x(self, desired_y: float) -> float:
        """Calculate token X needed to receive a specific amount of token Y.

        Args:
            desired_y: Desired output of token Y.

        Returns:
            Required input of token X (before fees).

        Raises:
            ValueError: If desired_y exceeds or equals reserves.
        """
        if desired_y >= self.reserve_y:
            raise ValueError(
                f"Desired output {desired_y} >= reserves {self.reserve_y}"
            )
        # delta_x_effective = reserve_x * desired_y / (reserve_y - desired_y)
        effective = self.reserve_x * desired_y / (self.reserve_y - desired_y)
        # Account for fee: effective = delta_x * (1 - fee), so delta_x = effective / (1 - fee)
        return effective / (1 - self.fee_rate)

    def add_liquidity(
        self, address: str, amount_x: float, amount_y: float
    ) -> LPPosition:
        """Add liquidity to the pool.

        For the first deposit, shares = sqrt(x * y).
        For subsequent deposits, shares are proportional to the smaller ratio.

        Args:
            address: Identifier for the LP.
            amount_x: Amount of token X to deposit.
            amount_y: Amount of token Y to deposit.

        Returns:
            LPPosition with share details.

        Raises:
            ValueError: If amounts are non-positive.
        """
        if amount_x <= 0 or amount_y <= 0:
            raise ValueError("Deposit amounts must be positive")

        if self.total_shares == 0:
            # Initial deposit
            shares = math.sqrt(amount_x * amount_y)
            self.reserve_x = amount_x
            self.reserve_y = amount_y
        else:
            # Proportional deposit
            ratio_x = amount_x / self.reserve_x
            ratio_y = amount_y / self.reserve_y
            share_ratio = min(ratio_x, ratio_y)
            shares = share_ratio * self.total_shares

            # Only use proportional amounts
            used_x = share_ratio * self.reserve_x
            used_y = share_ratio * self.reserve_y
            self.reserve_x += used_x
            self.reserve_y += used_y

            # Adjust amounts to what was actually used
            amount_x = used_x
            amount_y = used_y

        self.total_shares += shares
        position = LPPosition(
            address=address,
            shares=shares,
            deposit_x=amount_x,
            deposit_y=amount_y,
        )
        self.positions.append(position)
        return position

    def remove_liquidity(self, shares: float) -> tuple[float, float]:
        """Remove liquidity by burning shares.

        Args:
            shares: Number of LP shares to burn.

        Returns:
            Tuple of (token_x_out, token_y_out).

        Raises:
            ValueError: If shares exceed total supply.
        """
        if shares > self.total_shares:
            raise ValueError(
                f"Cannot burn {shares} shares, only {self.total_shares} exist"
            )
        if shares <= 0:
            raise ValueError("Shares must be positive")

        fraction = shares / self.total_shares
        x_out = fraction * self.reserve_x
        y_out = fraction * self.reserve_y

        self.reserve_x -= x_out
        self.reserve_y -= y_out
        self.total_shares -= shares

        return x_out, y_out

    def share_value(self, shares: float) -> tuple[float, float]:
        """Calculate the current value of LP shares.

        Args:
            shares: Number of shares to value.

        Returns:
            Tuple of (token_x_value, token_y_value).
        """
        if self.total_shares == 0:
            return 0.0, 0.0
        fraction = shares / self.total_shares
        return fraction * self.reserve_x, fraction * self.reserve_y

    def fee_apr_estimate(self, daily_volume: float) -> float:
        """Estimate annualized fee APR.

        Args:
            daily_volume: Expected daily trading volume (in token Y terms).

        Returns:
            Estimated APR as a decimal (e.g., 0.274 for 27.4%).
        """
        daily_fees = daily_volume * self.fee_rate * self.lp_fee_share
        if self.tvl == 0:
            return 0.0
        return (daily_fees * 365) / self.tvl


# ── Display Functions ───────────────────────────────────────────────


def print_pool_state(pool: ConstantProductPool) -> None:
    """Print the current state of the pool."""
    print(f"\n{'─' * 60}")
    print(f"  Pool: {pool.token_x}/{pool.token_y}")
    print(f"  Reserves: {pool.reserve_x:,.4f} {pool.token_x} / "
          f"{pool.reserve_y:,.4f} {pool.token_y}")
    print(f"  Spot Price: 1 {pool.token_x} = {pool.spot_price:,.4f} {pool.token_y}")
    print(f"  k = {pool.k:,.2f}")
    print(f"  TVL ≈ {pool.tvl:,.2f} {pool.token_y}")
    print(f"  Fee: {pool.fee_rate * 100:.2f}%")
    print(f"  Total Trades: {pool.trade_count}")
    print(f"  Total Fees: {pool.total_fees_x:,.4f} {pool.token_x} / "
          f"{pool.total_fees_y:,.4f} {pool.token_y}")
    print(f"  LP Shares: {pool.total_shares:,.4f}")
    print(f"{'─' * 60}")


def print_trade_result(result: TradeResult) -> None:
    """Print trade execution details."""
    print(f"\n  Trade: {result.input_amount:,.4f} {result.input_token} → "
          f"{result.output_amount:,.4f} {result.output_token}")
    print(f"  Fee paid: {result.fee_amount:,.6f} {result.input_token}")
    print(f"  Spot price before: {result.spot_price_before:,.4f}")
    print(f"  Execution price:   {result.execution_price:,.4f}")
    print(f"  Spot price after:  {result.spot_price_after:,.4f}")
    print(f"  Price impact:      {result.price_impact_pct:,.4f}%")
    print(f"  k change:          {result.k_before:,.2f} → {result.k_after:,.2f} "
          f"(+{result.k_after - result.k_before:,.2f})")


# ── Demo Mode ───────────────────────────────────────────────────────


def run_demo() -> None:
    """Run a demonstration of the AMM calculator."""
    print("=" * 60)
    print("  Constant Product AMM Calculator — Demo")
    print("=" * 60)

    # Create pool
    pool = ConstantProductPool(
        token_x="SOL",
        token_y="USDC",
        reserve_x=0,
        reserve_y=0,
        fee_rate=0.003,
        lp_fee_share=0.88,
    )

    # Step 1: Initial liquidity
    print("\n\n▸ STEP 1: Initial Liquidity Deposit")
    print("  Alice deposits 100 SOL + 10,000 USDC")
    pos_alice = pool.add_liquidity("Alice", 100, 10_000)
    print(f"  Alice receives {pos_alice.shares:,.4f} LP shares")
    print_pool_state(pool)

    # Step 2: Second LP
    print("\n\n▸ STEP 2: Second LP Deposit")
    print("  Bob deposits 50 SOL + 5,000 USDC (proportional)")
    pos_bob = pool.add_liquidity("Bob", 50, 5_000)
    print(f"  Bob receives {pos_bob.shares:,.4f} LP shares")
    print(f"  Alice's share: {pos_alice.shares / pool.total_shares * 100:.1f}%")
    print(f"  Bob's share:   {pos_bob.shares / pool.total_shares * 100:.1f}%")
    print_pool_state(pool)

    # Step 3: Series of trades
    print("\n\n▸ STEP 3: Execute Trades")

    trades = [
        ("x_for_y", 5, "Trader sells 5 SOL for USDC"),
        ("x_for_y", 10, "Trader sells 10 SOL for USDC"),
        ("y_for_x", 2000, "Trader buys SOL with 2,000 USDC"),
        ("x_for_y", 2, "Trader sells 2 SOL for USDC"),
        ("y_for_x", 500, "Trader buys SOL with 500 USDC"),
    ]

    for direction, amount, description in trades:
        print(f"\n  {description}")
        if direction == "x_for_y":
            result = pool.swap_x_for_y(amount)
        else:
            result = pool.swap_y_for_x(amount)
        print_trade_result(result)

    print_pool_state(pool)

    # Step 4: Show k growth from fees
    print("\n\n▸ STEP 4: Fee Accrual Analysis")
    initial_k = 100 * 10_000  # 1,000,000
    print(f"  Initial k:  {initial_k:>16,.2f}")
    print(f"  Current k:  {pool.k:>16,.2f}")
    print(f"  k growth:   {(pool.k / initial_k - 1) * 100:>15.4f}%")
    print(f"  Accumulated fees: {pool.total_fees_x:,.4f} {pool.token_x} + "
          f"{pool.total_fees_y:,.4f} {pool.token_y}")

    # Step 5: LP position values
    print("\n\n▸ STEP 5: LP Position Values")
    alice_x, alice_y = pool.share_value(pos_alice.shares)
    bob_x, bob_y = pool.share_value(pos_bob.shares)

    print(f"  Alice deposited: {pos_alice.deposit_x:,.4f} SOL + "
          f"{pos_alice.deposit_y:,.2f} USDC")
    print(f"  Alice current:   {alice_x:,.4f} SOL + {alice_y:,.2f} USDC")
    alice_value = alice_x * pool.spot_price + alice_y
    alice_deposit_value = pos_alice.deposit_x * 100 + pos_alice.deposit_y  # original price
    print(f"  Alice value (USDC): {alice_value:,.2f} "
          f"(deposited ~{alice_deposit_value:,.2f})")

    print()
    print(f"  Bob deposited:   {pos_bob.deposit_x:,.4f} SOL + "
          f"{pos_bob.deposit_y:,.2f} USDC")
    print(f"  Bob current:     {bob_x:,.4f} SOL + {bob_y:,.2f} USDC")
    bob_value = bob_x * pool.spot_price + bob_y
    bob_deposit_value = pos_bob.deposit_x * 100 + pos_bob.deposit_y
    print(f"  Bob value (USDC):   {bob_value:,.2f} "
          f"(deposited ~{bob_deposit_value:,.2f})")

    # Step 6: Fee APR estimate
    print("\n\n▸ STEP 6: Fee APR Estimate")
    for daily_vol in [100_000, 500_000, 1_000_000]:
        apr = pool.fee_apr_estimate(daily_vol)
        print(f"  Daily volume ${daily_vol:>10,} → Fee APR: {apr * 100:>7.2f}%")

    # Step 7: Required input calculation
    print("\n\n▸ STEP 7: Required Input Calculation")
    desired_usdc = 1000
    required_sol = pool.calculate_required_input_x(desired_usdc)
    print(f"  To receive exactly {desired_usdc:,} USDC, "
          f"you need {required_sol:,.4f} SOL")
    print(f"  Effective price: {desired_usdc / required_sol:,.4f} USDC/SOL "
          f"(spot: {pool.spot_price:,.4f})")

    # Step 8: Price impact for various sizes
    print("\n\n▸ STEP 8: Price Impact by Trade Size")
    print(f"  {'Trade Size':>12} {'Output':>12} {'Impact':>10} {'Eff. Price':>12}")
    print(f"  {'─' * 12} {'─' * 12} {'─' * 10} {'─' * 12}")
    for size in [1, 5, 10, 25, 50, 100]:
        impact = size / (pool.reserve_x + size) * 100
        output = pool.reserve_y * size * (1 - pool.fee_rate) / (pool.reserve_x + size * (1 - pool.fee_rate))
        eff_price = output / size
        print(f"  {size:>10.1f} {pool.token_x} {output:>10.2f} {pool.token_y} "
              f"{impact:>8.2f}%  {eff_price:>10.4f}")

    # Step 9: Withdrawal
    print("\n\n▸ STEP 9: LP Withdrawal")
    print(f"  Bob burns all {pos_bob.shares:,.4f} shares")
    x_out, y_out = pool.remove_liquidity(pos_bob.shares)
    print(f"  Bob receives: {x_out:,.4f} {pool.token_x} + {y_out:,.2f} {pool.token_y}")
    print_pool_state(pool)

    print("\n" + "=" * 60)
    print("  Demo Complete")
    print("=" * 60)


# ── Interactive Mode ────────────────────────────────────────────────


def run_interactive() -> None:
    """Run interactive AMM calculator."""
    print("=" * 60)
    print("  Constant Product AMM Calculator — Interactive Mode")
    print("=" * 60)

    print("\nConfigure your pool:")
    try:
        token_x = input("  Token X name [SOL]: ").strip() or "SOL"
        token_y = input("  Token Y name [USDC]: ").strip() or "USDC"
        reserve_x = float(input(f"  Initial {token_x} reserve [100]: ").strip() or "100")
        reserve_y = float(input(f"  Initial {token_y} reserve [10000]: ").strip() or "10000")
        fee_pct = float(input("  Fee % [0.3]: ").strip() or "0.3")
    except (ValueError, EOFError):
        print("Invalid input, using defaults.")
        token_x, token_y = "SOL", "USDC"
        reserve_x, reserve_y = 100, 10_000
        fee_pct = 0.3

    pool = ConstantProductPool(
        token_x=token_x,
        token_y=token_y,
        reserve_x=0,
        reserve_y=0,
        fee_rate=fee_pct / 100,
        lp_fee_share=0.88,
    )
    pool.add_liquidity("initial", reserve_x, reserve_y)
    print_pool_state(pool)

    print("\nCommands:")
    print("  sell_x <amount>  — Sell token X for token Y")
    print("  sell_y <amount>  — Sell token Y for token X")
    print("  need_y <amount>  — Calculate X needed for specific Y output")
    print("  add <x> <y>      — Add liquidity")
    print("  state            — Show pool state")
    print("  quit             — Exit")

    while True:
        try:
            cmd = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd:
            continue

        parts = cmd.split()
        action = parts[0]

        try:
            if action == "quit" or action == "q":
                break
            elif action == "state":
                print_pool_state(pool)
            elif action == "sell_x" and len(parts) == 2:
                result = pool.swap_x_for_y(float(parts[1]))
                print_trade_result(result)
            elif action == "sell_y" and len(parts) == 2:
                result = pool.swap_y_for_x(float(parts[1]))
                print_trade_result(result)
            elif action == "need_y" and len(parts) == 2:
                needed = pool.calculate_required_input_x(float(parts[1]))
                print(f"  Need {needed:,.4f} {pool.token_x} to get "
                      f"{float(parts[1]):,.4f} {pool.token_y}")
            elif action == "add" and len(parts) == 3:
                pos = pool.add_liquidity("user", float(parts[1]), float(parts[2]))
                print(f"  Received {pos.shares:,.4f} shares")
                print_pool_state(pool)
            else:
                print("  Unknown command. Type 'quit' to exit.")
        except (ValueError, ZeroDivisionError) as e:
            print(f"  Error: {e}")

    print("\nFinal state:")
    print_pool_state(pool)


# ── Main ────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Constant Product AMM Calculator"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo mode with pre-configured trades",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        run_interactive()


if __name__ == "__main__":
    main()
