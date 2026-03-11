#!/usr/bin/env python3
"""Bracket order demonstration with RSI-based entry and ATR-based stops.

Demonstrates:
- Bracket orders (entry + stop loss + take profit as atomic unit)
- RSI oversold entry signals
- ATR-based dynamic stop loss and take profit distances
- Detailed order notification and trade tracking
- Trade log with entry/exit prices and P&L

Usage:
    python scripts/bracket_orders.py --demo
    python scripts/bracket_orders.py --rsi-period 14 --rsi-entry 30 --atr-mult 2.0

Dependencies:
    uv pip install backtrader pandas numpy
"""

import argparse
import datetime
import sys
from typing import Optional

import backtrader as bt
import numpy as np
import pandas as pd


# ── Synthetic Data Generator ────────────────────────────────────────


def generate_mean_reverting_ohlcv(
    days: int = 600,
    start_price: float = 100.0,
    volatility: float = 0.025,
    mean_reversion_strength: float = 0.01,
    seed: int = 123,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with mean-reverting characteristics.

    Mean-reverting data produces more RSI oversold/overbought signals,
    which is better suited for demonstrating bracket orders with RSI entry.

    Args:
        days: Number of trading days to simulate.
        start_price: Initial price and mean to revert toward.
        volatility: Daily volatility.
        mean_reversion_strength: Pull toward the mean (higher = faster reversion).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with DatetimeIndex and OHLCV columns.
    """
    rng = np.random.default_rng(seed)

    prices = np.zeros(days)
    prices[0] = start_price

    for i in range(1, days):
        # Mean-reverting drift
        drift = -mean_reversion_strength * (prices[i - 1] - start_price) / start_price
        shock = rng.normal(0, volatility)
        log_return = drift + shock
        prices[i] = prices[i - 1] * np.exp(log_return)

    opens = np.roll(prices, 1)
    opens[0] = start_price

    intraday_range = prices * volatility * rng.uniform(0.5, 2.5, days)
    highs = np.maximum(opens, prices) + intraday_range * 0.5
    lows = np.minimum(opens, prices) - intraday_range * 0.5

    # Ensure OHLC consistency
    lows = np.minimum(lows, np.minimum(opens, prices))
    highs = np.maximum(highs, np.maximum(opens, prices))

    volume = (1_000_000 * rng.uniform(0.5, 2.0, days)).astype(int)

    dates = pd.date_range(
        start=datetime.datetime(2024, 1, 1),
        periods=days,
        freq="D",
    )

    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volume,
        },
        index=dates,
    )


# ── Strategy ────────────────────────────────────────────────────────


class RSIBracketStrategy(bt.Strategy):
    """RSI-based entry with ATR bracket orders.

    Entry: Market buy when RSI crosses below oversold threshold.
    Exit: Bracket order with ATR-based stop loss and take profit.
    The stop and take-profit are placed as OCO children of the entry.
    When one fills, the other is automatically canceled.

    Params:
        rsi_period: RSI calculation period.
        rsi_entry: RSI threshold for entry (buy when RSI < this).
        atr_period: ATR calculation period.
        atr_stop_mult: ATR multiplier for stop loss distance.
        atr_tp_mult: ATR multiplier for take profit distance.
        printlog: Whether to print trade-by-trade logs.
    """

    params = (
        ("rsi_period", 14),
        ("rsi_entry", 30),
        ("atr_period", 14),
        ("atr_stop_mult", 2.0),
        ("atr_tp_mult", 3.0),
        ("printlog", True),
    )

    def __init__(self) -> None:
        """Initialize indicators and order tracking."""
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)
        self.atr = bt.ind.ATR(period=self.p.atr_period)

        # Order tracking
        self.entry_order: Optional[bt.Order] = None
        self.stop_order: Optional[bt.Order] = None
        self.tp_order: Optional[bt.Order] = None

        # Trade log
        self.trade_log: list[dict] = []
        self.trade_count: int = 0

        # Pending bracket flag
        self.has_pending_bracket: bool = False

    def log(self, txt: str, dt: Optional[datetime.date] = None) -> None:
        """Log a message with date prefix.

        Args:
            txt: Message text.
            dt: Optional date override.
        """
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"  {dt} | {txt}")

    def next(self) -> None:
        """Check for RSI entry signal and place bracket orders."""
        if self.position or self.has_pending_bracket:
            return

        # Entry signal: RSI below oversold threshold
        if self.rsi[0] < self.p.rsi_entry:
            price = self.data.close[0]
            atr_val = self.atr[0]

            if atr_val <= 0:
                return

            stop_dist = atr_val * self.p.atr_stop_mult
            tp_dist = atr_val * self.p.atr_tp_mult

            stop_price = price - stop_dist
            tp_price = price + tp_dist

            self.log(
                f"RSI ENTRY SIGNAL | RSI={self.rsi[0]:.1f} "
                f"Price={price:.4f} ATR={atr_val:.4f}"
            )
            self.log(
                f"  BRACKET | Stop={stop_price:.4f} "
                f"(dist={stop_dist:.4f}) TP={tp_price:.4f} "
                f"(dist={tp_dist:.4f})"
            )

            # Place bracket order
            orders = self.buy_bracket(
                limitprice=tp_price,
                stopprice=stop_price,
                exectype=bt.Order.Market,
                stopexec=bt.Order.Stop,
                limitexec=bt.Order.Limit,
            )

            self.entry_order = orders[0]
            self.stop_order = orders[1]
            self.tp_order = orders[2]
            self.has_pending_bracket = True

    def notify_order(self, order: bt.Order) -> None:
        """Handle order status changes for all bracket components.

        Args:
            order: The order whose status changed.
        """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            order_type = self._identify_order(order)
            action = "BUY" if order.isbuy() else "SELL"

            self.log(
                f"{order_type} {action} FILLED | "
                f"Price={order.executed.price:.4f} "
                f"Size={abs(order.executed.size):.2f} "
                f"Comm={order.executed.comm:.4f}"
            )

            # If the entry order filled, we now have a position with bracket
            if order is self.entry_order:
                self.has_pending_bracket = False

            # If stop or TP filled, the other is auto-canceled by bracket
            if order is self.stop_order:
                self.log("  >> STOP LOSS triggered")
                self._clear_orders()
            elif order is self.tp_order:
                self.log("  >> TAKE PROFIT triggered")
                self._clear_orders()

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            order_type = self._identify_order(order)
            self.log(f"{order_type} {order.getstatusname()}")

            # If entry was rejected, clear everything
            if order is self.entry_order:
                self.has_pending_bracket = False
                self._clear_orders()

    def _identify_order(self, order: bt.Order) -> str:
        """Identify which bracket component this order is.

        Args:
            order: Order to identify.

        Returns:
            String label for the order type.
        """
        if order is self.entry_order:
            return "ENTRY"
        elif order is self.stop_order:
            return "STOP"
        elif order is self.tp_order:
            return "TP"
        return "UNKNOWN"

    def _clear_orders(self) -> None:
        """Reset all order references."""
        self.entry_order = None
        self.stop_order = None
        self.tp_order = None
        self.has_pending_bracket = False

    def notify_trade(self, trade: bt.Trade) -> None:
        """Track completed trades for the final summary.

        Args:
            trade: Trade that opened or closed.
        """
        if not trade.isclosed:
            return

        self.trade_count += 1

        exit_type = "UNKNOWN"
        if trade.pnl < 0:
            exit_type = "STOP LOSS"
        elif trade.pnl > 0:
            exit_type = "TAKE PROFIT"

        record = {
            "num": self.trade_count,
            "entry_price": trade.price,
            "pnl_gross": trade.pnl,
            "pnl_net": trade.pnlcomm,
            "bars": trade.barlen,
            "exit_type": exit_type,
        }
        self.trade_log.append(record)

        self.log(
            f"TRADE #{self.trade_count} CLOSED | "
            f"Exit={exit_type} Gross={trade.pnl:.2f} "
            f"Net={trade.pnlcomm:.2f} Bars={trade.barlen}"
        )


# ── Results Printer ─────────────────────────────────────────────────


def print_results(
    strat: RSIBracketStrategy,
    initial_cash: float,
    final_value: float,
) -> None:
    """Print bracket order backtest results.

    Args:
        strat: Completed strategy instance.
        initial_cash: Starting cash.
        final_value: Ending portfolio value.
    """
    print("\n" + "=" * 70)
    print("BRACKET ORDER BACKTEST RESULTS")
    print("=" * 70)

    total_return = (final_value - initial_cash) / initial_cash * 100
    print(f"\n  Initial Cash:    ${initial_cash:>12,.2f}")
    print(f"  Final Value:     ${final_value:>12,.2f}")
    print(f"  Total Return:    {total_return:>12.2f}%")

    # Sharpe
    sharpe_dict = strat.analyzers.sharpe.get_analysis()
    sharpe_val = sharpe_dict.get("sharperatio")
    sharpe_str = f"{sharpe_val:.4f}" if sharpe_val is not None else "N/A"
    print(f"  Sharpe Ratio:    {sharpe_str:>12}")

    # Drawdown
    dd_dict = strat.analyzers.drawdown.get_analysis()
    max_dd = dd_dict.get("max", {})
    print(f"  Max Drawdown:    {max_dd.get('drawdown', 0.0):>11.2f}%")

    # Trade summary
    trades = strat.trade_log
    if not trades:
        print("\n  No completed trades.")
        print("=" * 70)
        return

    total = len(trades)
    winners = [t for t in trades if t["pnl_net"] > 0]
    losers = [t for t in trades if t["pnl_net"] <= 0]
    stops = [t for t in trades if t["exit_type"] == "STOP LOSS"]
    tps = [t for t in trades if t["exit_type"] == "TAKE PROFIT"]

    print(f"\n  Total Trades:    {total:>12}")
    print(f"  Winners:         {len(winners):>12}")
    print(f"  Losers:          {len(losers):>12}")
    print(f"  Win Rate:        {len(winners) / total * 100:>11.1f}%")
    print(f"  Stop Outs:       {len(stops):>12}")
    print(f"  TP Hits:         {len(tps):>12}")

    total_pnl = sum(t["pnl_net"] for t in trades)
    avg_pnl = total_pnl / total
    avg_win = sum(t["pnl_net"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["pnl_net"] for t in losers) / len(losers) if losers else 0
    avg_bars = sum(t["bars"] for t in trades) / total

    print(f"\n  Total Net P&L:   ${total_pnl:>12,.2f}")
    print(f"  Avg Trade P&L:   ${avg_pnl:>12,.2f}")
    print(f"  Avg Win:         ${avg_win:>12,.2f}")
    print(f"  Avg Loss:        ${avg_loss:>12,.2f}")
    print(f"  Avg Bars/Trade:  {avg_bars:>12.1f}")

    if avg_loss != 0:
        pf = abs(sum(t["pnl_net"] for t in winners) / sum(t["pnl_net"] for t in losers))
        print(f"  Profit Factor:   {pf:>12.2f}")

    # Detailed trade log
    print(f"\n  {'#':>4} {'Entry':>10} {'Exit Type':>12} {'Gross P&L':>12} {'Net P&L':>12} {'Bars':>6}")
    print(f"  {'-' * 4} {'-' * 10} {'-' * 12} {'-' * 12} {'-' * 12} {'-' * 6}")
    for t in trades:
        print(
            f"  {t['num']:>4} "
            f"{t['entry_price']:>10.4f} "
            f"{t['exit_type']:>12} "
            f"${t['pnl_gross']:>11,.2f} "
            f"${t['pnl_net']:>11,.2f} "
            f"{t['bars']:>6}"
        )

    print("\n" + "=" * 70)


# ── Main ────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Bracket Order Backtest (analysis only, not financial advice)"
    )
    parser.add_argument(
        "--demo", action="store_true", default=True, help="Run with synthetic data (default)"
    )
    parser.add_argument("--rsi-period", type=int, default=14, help="RSI period (default: 14)")
    parser.add_argument("--rsi-entry", type=int, default=30, help="RSI entry threshold (default: 30)")
    parser.add_argument(
        "--atr-mult", type=float, default=2.0, help="ATR multiplier for stop loss (default: 2.0)"
    )
    parser.add_argument(
        "--tp-mult", type=float, default=3.0, help="ATR multiplier for take profit (default: 3.0)"
    )
    parser.add_argument(
        "--cash", type=float, default=100_000.0, help="Starting cash (default: 100000)"
    )
    parser.add_argument(
        "--commission", type=float, default=0.003, help="Commission per side (default: 0.003)"
    )
    parser.add_argument("--days", type=int, default=600, help="Days of synthetic data (default: 600)")
    parser.add_argument("--seed", type=int, default=123, help="Random seed (default: 123)")
    parser.add_argument("--plot", action="store_true", help="Show matplotlib plot")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-trade logging")

    return parser.parse_args()


def main() -> None:
    """Run the RSI bracket order backtest."""
    args = parse_args()

    # Generate mean-reverting data (better for RSI signals)
    print(f"Generating {args.days} days of mean-reverting synthetic OHLCV data (seed={args.seed})...")
    df = generate_mean_reverting_ohlcv(days=args.days, seed=args.seed)
    print(f"  Date range: {df.index[0].date()} to {df.index[-1].date()}")
    print(f"  Price range: {df['low'].min():.2f} to {df['high'].max():.2f}")

    # Configure cerebro
    cerebro = bt.Cerebro()

    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    cerebro.addstrategy(
        RSIBracketStrategy,
        rsi_period=args.rsi_period,
        rsi_entry=args.rsi_entry,
        atr_period=14,
        atr_stop_mult=args.atr_mult,
        atr_tp_mult=args.tp_mult,
        printlog=not args.quiet,
    )

    # Broker
    cerebro.broker.setcash(args.cash)
    cerebro.broker.setcommission(commission=args.commission)
    cerebro.broker.set_coo(True)
    cerebro.broker.set_slippage_perc(0.001)

    # Size: 95% of portfolio
    cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

    # Analyzers
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        riskfreerate=0.0,
        annualize=True,
        timeframe=bt.TimeFrame.Days,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

    # Run
    print(
        f"\nRunning RSI({args.rsi_period}) bracket backtest "
        f"(entry<{args.rsi_entry}, stop={args.atr_mult}xATR, tp={args.tp_mult}xATR)..."
    )
    print(f"  Cash: ${args.cash:,.2f} | Commission: {args.commission * 100:.1f}%\n")

    results = cerebro.run()
    strat = results[0]

    final_value = cerebro.broker.getvalue()
    print_results(strat, args.cash, final_value)

    if args.plot:
        try:
            cerebro.plot(style="candlestick", volume=True)
        except Exception as exc:
            print(f"\nPlot failed: {exc}")


if __name__ == "__main__":
    main()
