#!/usr/bin/env python3
"""Complete EMA crossover backtest using backtrader with synthetic OHLCV data.

Demonstrates:
- Strategy definition with EMA crossover signals
- Broker configuration (cash, commission, slippage)
- Multiple analyzers (Sharpe, DrawDown, TradeAnalyzer, Returns)
- Order and trade notification logging
- Comprehensive results printing

Usage:
    python scripts/backtest_strategy.py --demo
    python scripts/backtest_strategy.py --fast 8 --slow 21 --cash 50000

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


def generate_synthetic_ohlcv(
    days: int = 500,
    start_price: float = 100.0,
    volatility: float = 0.02,
    trend: float = 0.0003,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data with realistic price dynamics.

    Uses geometric Brownian motion with a slight upward drift and
    generates intraday OHLC from the simulated path.

    Args:
        days: Number of trading days to simulate.
        start_price: Initial price.
        volatility: Daily volatility (standard deviation of returns).
        trend: Daily drift (positive = uptrend).
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with DatetimeIndex and columns: open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)

    # Simulate daily returns with GBM
    returns = rng.normal(trend, volatility, days)
    prices = start_price * np.exp(np.cumsum(returns))

    # Generate OHLC from close prices
    opens = np.roll(prices, 1)
    opens[0] = start_price

    # Intraday range scaled by volatility
    intraday_range = prices * volatility * rng.uniform(0.5, 2.0, days)
    highs = np.maximum(opens, prices) + intraday_range * 0.5
    lows = np.minimum(opens, prices) - intraday_range * 0.5

    # Ensure OHLC consistency
    lows = np.minimum(lows, np.minimum(opens, prices))
    highs = np.maximum(highs, np.maximum(opens, prices))

    # Volume with some randomness
    base_volume = 1_000_000
    volume = (base_volume * rng.uniform(0.5, 2.0, days)).astype(int)

    dates = pd.date_range(
        start=datetime.datetime(2024, 1, 1),
        periods=days,
        freq="D",
    )

    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": prices,
            "volume": volume,
        },
        index=dates,
    )

    return df


# ── Strategy ────────────────────────────────────────────────────────


class EMACrossoverStrategy(bt.Strategy):
    """EMA crossover strategy with order and trade logging.

    Buys when fast EMA crosses above slow EMA, sells when it crosses below.
    Tracks all orders and trades for detailed reporting.

    Params:
        fast_period: Fast EMA lookback period.
        slow_period: Slow EMA lookback period.
        printlog: Whether to print log messages.
    """

    params = (
        ("fast_period", 10),
        ("slow_period", 30),
        ("printlog", True),
    )

    def __init__(self) -> None:
        """Initialize indicators and tracking variables."""
        self.ema_fast = bt.ind.EMA(period=self.p.fast_period)
        self.ema_slow = bt.ind.EMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.ema_fast, self.ema_slow)

        # Order tracking
        self.order: Optional[bt.Order] = None
        self.trade_count: int = 0
        self.trade_log: list[dict] = []

    def log(self, txt: str, dt: Optional[datetime.date] = None) -> None:
        """Log a message with the current date.

        Args:
            txt: Message to log.
            dt: Optional date override.
        """
        if self.p.printlog:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"  {dt} | {txt}")

    def next(self) -> None:
        """Process each bar: check crossover signals and manage orders."""
        if self.order:
            return  # waiting for pending order

        if not self.position:
            if self.crossover[0] > 0:
                self.log(
                    f"SIGNAL BUY | Close={self.data.close[0]:.4f} "
                    f"EMA_fast={self.ema_fast[0]:.4f} EMA_slow={self.ema_slow[0]:.4f}"
                )
                self.order = self.buy()
        else:
            if self.crossover[0] < 0:
                self.log(
                    f"SIGNAL SELL | Close={self.data.close[0]:.4f} "
                    f"EMA_fast={self.ema_fast[0]:.4f} EMA_slow={self.ema_slow[0]:.4f}"
                )
                self.order = self.close()

    def notify_order(self, order: bt.Order) -> None:
        """Handle order status changes.

        Args:
            order: The order whose status changed.
        """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    f"BUY EXECUTED | Price={order.executed.price:.4f} "
                    f"Size={order.executed.size:.2f} "
                    f"Commission={order.executed.comm:.4f}"
                )
            else:
                self.log(
                    f"SELL EXECUTED | Price={order.executed.price:.4f} "
                    f"Size={abs(order.executed.size):.2f} "
                    f"Commission={order.executed.comm:.4f}"
                )
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"ORDER FAILED | Status={order.getstatusname()}")

        self.order = None

    def notify_trade(self, trade: bt.Trade) -> None:
        """Handle trade notifications for P&L tracking.

        Args:
            trade: The trade that was opened or closed.
        """
        if not trade.isclosed:
            return

        self.trade_count += 1
        self.trade_log.append(
            {
                "trade_num": self.trade_count,
                "pnl_gross": trade.pnl,
                "pnl_net": trade.pnlcomm,
                "bars_held": trade.barlen,
            }
        )

        self.log(
            f"TRADE CLOSED #{self.trade_count} | "
            f"Gross P&L={trade.pnl:.2f} Net P&L={trade.pnlcomm:.2f} "
            f"Bars held={trade.barlen}"
        )


# ── Results Printer ─────────────────────────────────────────────────


def print_results(
    strat: bt.Strategy,
    initial_cash: float,
    final_value: float,
) -> None:
    """Print comprehensive backtest results from analyzers.

    Args:
        strat: The completed strategy instance.
        initial_cash: Starting portfolio value.
        final_value: Ending portfolio value.
    """
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    # Portfolio summary
    total_return = (final_value - initial_cash) / initial_cash * 100
    print(f"\n  Initial Cash:    ${initial_cash:>12,.2f}")
    print(f"  Final Value:     ${final_value:>12,.2f}")
    print(f"  Total Return:    {total_return:>12.2f}%")

    # Sharpe ratio
    sharpe_dict = strat.analyzers.sharpe.get_analysis()
    sharpe_val = sharpe_dict.get("sharperatio")
    sharpe_str = f"{sharpe_val:.4f}" if sharpe_val is not None else "N/A"
    print(f"\n  Sharpe Ratio:    {sharpe_str:>12}")

    # Drawdown
    dd_dict = strat.analyzers.drawdown.get_analysis()
    max_dd = dd_dict.get("max", {})
    max_dd_pct = max_dd.get("drawdown", 0.0)
    max_dd_money = max_dd.get("moneydown", 0.0)
    max_dd_len = max_dd.get("len", 0)
    print(f"  Max Drawdown:    {max_dd_pct:>11.2f}%")
    print(f"  Max DD ($):      ${max_dd_money:>12,.2f}")
    print(f"  Max DD Length:   {max_dd_len:>12} bars")

    # Returns
    ret_dict = strat.analyzers.returns.get_analysis()
    rnorm = ret_dict.get("rnorm100", 0.0)
    print(f"  Ann. Return:     {rnorm:>11.2f}%")

    # Trade analysis
    trade_dict = strat.analyzers.trades.get_analysis()

    total_trades = trade_dict.get("total", {}).get("total", 0)
    total_open = trade_dict.get("total", {}).get("open", 0)
    total_closed = trade_dict.get("total", {}).get("closed", 0)

    print(f"\n  Total Trades:    {total_trades:>12}")
    print(f"  Open Trades:     {total_open:>12}")
    print(f"  Closed Trades:   {total_closed:>12}")

    if total_closed > 0:
        won = trade_dict.get("won", {}).get("total", 0)
        lost = trade_dict.get("lost", {}).get("total", 0)
        win_rate = won / total_closed * 100 if total_closed > 0 else 0.0
        print(f"  Winners:         {won:>12}")
        print(f"  Losers:          {lost:>12}")
        print(f"  Win Rate:        {win_rate:>11.1f}%")

        # P&L
        pnl_net = trade_dict.get("pnl", {}).get("net", {})
        total_pnl = pnl_net.get("total", 0.0)
        avg_pnl = pnl_net.get("average", 0.0)
        print(f"\n  Total Net P&L:   ${total_pnl:>12,.2f}")
        print(f"  Avg Trade P&L:   ${avg_pnl:>12,.2f}")

        # Won/lost breakdown
        won_pnl = trade_dict.get("won", {}).get("pnl", {})
        lost_pnl = trade_dict.get("lost", {}).get("pnl", {})
        avg_win = won_pnl.get("average", 0.0)
        avg_loss = lost_pnl.get("average", 0.0)
        max_win = won_pnl.get("max", 0.0)
        max_loss = lost_pnl.get("max", 0.0)

        print(f"  Avg Win:         ${avg_win:>12,.2f}")
        print(f"  Avg Loss:        ${avg_loss:>12,.2f}")
        print(f"  Max Win:         ${max_win:>12,.2f}")
        print(f"  Max Loss:        ${max_loss:>12,.2f}")

        if avg_loss != 0:
            profit_factor = abs(avg_win * won / (avg_loss * lost))
            print(f"  Profit Factor:   {profit_factor:>12.2f}")

        # Streak
        streak = trade_dict.get("streak", {})
        won_streak = streak.get("won", {}).get("longest", 0)
        lost_streak = streak.get("lost", {}).get("longest", 0)
        print(f"  Win Streak:      {won_streak:>12}")
        print(f"  Loss Streak:     {lost_streak:>12}")

        # Avg bars in trade
        trade_len = trade_dict.get("len", {})
        avg_bars = trade_len.get("average", 0.0)
        print(f"  Avg Bars/Trade:  {avg_bars:>12.1f}")

    # Trade log
    if strat.trade_log:
        print(f"\n  {'#':>4} {'Gross P&L':>12} {'Net P&L':>12} {'Bars':>6}")
        print(f"  {'-' * 4} {'-' * 12} {'-' * 12} {'-' * 6}")
        for t in strat.trade_log:
            print(
                f"  {t['trade_num']:>4} "
                f"${t['pnl_gross']:>11,.2f} "
                f"${t['pnl_net']:>11,.2f} "
                f"{t['bars_held']:>6}"
            )

    print("\n" + "=" * 70)


# ── Main ────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Backtrader EMA Crossover Backtest (analysis only, not financial advice)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Run with synthetic data (default: True)",
    )
    parser.add_argument("--fast", type=int, default=10, help="Fast EMA period (default: 10)")
    parser.add_argument("--slow", type=int, default=30, help="Slow EMA period (default: 30)")
    parser.add_argument(
        "--cash", type=float, default=100_000.0, help="Starting cash (default: 100000)"
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.003,
        help="Commission per trade side (default: 0.003 = 0.3%%)",
    )
    parser.add_argument("--days", type=int, default=500, help="Days of synthetic data (default: 500)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--plot", action="store_true", help="Show matplotlib plot after backtest")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-trade logging")

    return parser.parse_args()


def main() -> None:
    """Run the EMA crossover backtest."""
    args = parse_args()

    if args.fast >= args.slow:
        print(f"Error: fast period ({args.fast}) must be less than slow period ({args.slow})")
        sys.exit(1)

    # Generate data
    print(f"Generating {args.days} days of synthetic OHLCV data (seed={args.seed})...")
    df = generate_synthetic_ohlcv(days=args.days, seed=args.seed)
    print(f"  Date range: {df.index[0].date()} to {df.index[-1].date()}")
    print(f"  Price range: {df['low'].min():.2f} to {df['high'].max():.2f}")

    # Configure cerebro
    cerebro = bt.Cerebro()

    # Add data
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # Add strategy
    cerebro.addstrategy(
        EMACrossoverStrategy,
        fast_period=args.fast,
        slow_period=args.slow,
        printlog=not args.quiet,
    )

    # Broker settings
    cerebro.broker.setcash(args.cash)
    cerebro.broker.setcommission(commission=args.commission)
    cerebro.broker.set_coo(True)  # cheat on open for realistic execution
    cerebro.broker.set_slippage_perc(0.001)  # 0.1% slippage

    # Sizer: use 95% of available cash
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
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    # Run
    print(f"\nRunning EMA({args.fast}/{args.slow}) crossover backtest...")
    print(f"  Cash: ${args.cash:,.2f} | Commission: {args.commission * 100:.1f}%")
    print(f"  Slippage: 0.1% | Cheat-on-open: enabled\n")

    results = cerebro.run()
    strat = results[0]

    # Print results
    final_value = cerebro.broker.getvalue()
    print_results(strat, args.cash, final_value)

    # Optional plot
    if args.plot:
        try:
            cerebro.plot(style="candlestick", volume=True)
        except Exception as exc:
            print(f"\nPlot failed (headless environment?): {exc}")
            print("Install matplotlib and run in a GUI environment for plotting.")


if __name__ == "__main__":
    main()
