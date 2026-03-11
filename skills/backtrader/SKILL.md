---
name: backtrader
description: Event-driven backtesting with bar-by-bar execution, complex order types, multiple analyzers, and custom indicators
---

# Backtrader

Backtrader is a Python event-driven backtesting framework that processes data bar-by-bar, simulating realistic execution with a built-in broker, order management, and position tracking. Unlike vectorized frameworks (vectorbt, pandas), backtrader walks through history one bar at a time, firing callbacks that let you implement complex order logic that depends on previous fills, partial executions, and conditional brackets.

## Event-Driven vs Vectorized

| Aspect | Backtrader (event-driven) | vectorbt (vectorized) |
|---|---|---|
| Execution model | Bar-by-bar callbacks | Whole-array operations |
| Speed | Slower (Python loop) | Fast (NumPy/Numba) |
| Order types | Market, limit, stop, stop-limit, bracket, OCO | Market only (native) |
| Realism | Built-in broker with commission, slippage, margin | Manual slippage modeling |
| Multi-timeframe | Native resampledata | Manual alignment |
| Best for | Complex strategies, bracket orders, portfolio | Fast parameter sweeps, simple signals |

**Use backtrader when you need:**
- Bracket orders (entry + stop loss + take profit as a unit)
- Stop-limit or trailing stop orders
- Order-dependent logic (scale in after first fill, cancel if not filled in N bars)
- Multi-timeframe strategies (daily signals, hourly execution)
- Realistic commission and slippage modeling

**Use vectorbt when you need:**
- Fast parameter optimization over thousands of combinations
- Simple long/short signals without complex order management
- Quick prototyping and statistical analysis of results

---

## Core Concepts

Backtrader has five core objects that interact through an event loop:

### 1. Cerebro (the engine)

The central orchestrator. You add strategies, data feeds, analyzers, and sizers to Cerebro, then call `run()`.

```python
import backtrader as bt

cerebro = bt.Cerebro()
cerebro.addstrategy(MyStrategy, fast_period=10, slow_period=30)
cerebro.adddata(data_feed)
cerebro.broker.setcash(100_000)
cerebro.broker.setcommission(commission=0.003)  # 0.3%
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
cerebro.run()
```

### 2. Strategy (your logic)

A Strategy subclass contains all trading logic. Key methods:

- `__init__()` — Define indicators. Runs once before backtesting starts.
- `next()` — Called on every bar. Place orders here.
- `notify_order(order)` — Called when order status changes (submitted, accepted, completed, canceled, margin, expired).
- `notify_trade(trade)` — Called when a trade opens or closes. Access P&L here.

```python
class EMACrossover(bt.Strategy):
    params = (
        ("fast_period", 10),
        ("slow_period", 30),
    )

    def __init__(self) -> None:
        self.ema_fast = bt.ind.EMA(period=self.p.fast_period)
        self.ema_slow = bt.ind.EMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.ema_fast, self.ema_slow)

    def next(self) -> None:
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.close()
```

### 3. Data Feed

Backtrader data feeds provide OHLCV lines. The most common approach is loading from a pandas DataFrame:

```python
import pandas as pd

df = pd.DataFrame({
    "open": [...], "high": [...], "low": [...],
    "close": [...], "volume": [...],
}, index=pd.DatetimeIndex([...]))

data = bt.feeds.PandasData(dataname=df)
cerebro.adddata(data)
```

For CSV files:

```python
data = bt.feeds.GenericCSVData(
    dataname="ohlcv.csv",
    dtformat="%Y-%m-%d",
    openinterest=-1,  # no open interest column
)
```

### 4. Broker

The built-in broker simulates order execution with configurable cash, commission, and slippage.

```python
cerebro.broker.setcash(100_000)
cerebro.broker.setcommission(commission=0.003)  # 0.3% per trade

# Cheat-on-open: execute at the open of the signal bar (avoids lookahead)
cerebro.broker.set_coo(True)
```

### 5. Analyzers

Analyzers compute performance metrics after the backtest completes.

```python
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                    riskfreerate=0.0, annualize=True, timeframe=bt.TimeFrame.Days)
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

results = cerebro.run()
strat = results[0]

sharpe = strat.analyzers.sharpe.get_analysis()
dd = strat.analyzers.drawdown.get_analysis()
trades = strat.analyzers.trades.get_analysis()
```

---

## Order Types

Backtrader supports complex order types critical for realistic crypto backtesting.

### Market Order

```python
self.buy()  # market buy
self.sell()  # market sell
self.close()  # close current position
```

### Limit Order

```python
self.buy(exectype=bt.Order.Limit, price=95.0)
self.sell(exectype=bt.Order.Limit, price=105.0)
```

### Stop Order

Triggers a market order when price reaches the stop level:

```python
self.sell(exectype=bt.Order.Stop, price=90.0)  # stop loss
```

### Stop-Limit Order

Triggers a limit order when price reaches the stop level:

```python
self.buy(exectype=bt.Order.StopLimit, price=100.0, plimit=101.0)
```

### Bracket Order

Entry + stop loss + take profit as an atomic unit. If the stop fills, the take profit is canceled (and vice versa).

```python
self.buy_bracket(
    price=100.0,           # entry limit
    stopprice=95.0,        # stop loss
    limitprice=110.0,      # take profit
    exectype=bt.Order.Limit,
    stopexec=bt.Order.Stop,
    limitexec=bt.Order.Limit,
)
```

See `references/strategy_patterns.md` for bracket order patterns with ATR-based stops.

---

## Position Sizing (Sizers)

Sizers determine how many units to buy/sell per order.

```python
# Fixed size
cerebro.addsizer(bt.sizers.FixedSize, stake=100)

# Percent of portfolio
cerebro.addsizer(bt.sizers.PercentSizer, percents=95)

# All available cash
cerebro.addsizer(bt.sizers.AllInSizer, percents=95)
```

Custom sizer:

```python
class RiskSizer(bt.Sizer):
    params = (("risk_pct", 0.02),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        risk_amount = cash * self.p.risk_pct
        atr = self.strategy.atr[0]
        if atr <= 0:
            return 0
        size = risk_amount / atr
        return int(size)
```

---

## Crypto Considerations

### 24/7 Markets

Crypto trades around the clock. When using daily bars, there are no weekends to skip. Set the session times or use `sessionstart`/`sessionend` if analyzing specific windows.

### High Fees

DEX swaps on Solana typically cost 0.25-0.30% per trade. Set commission accordingly:

```python
cerebro.broker.setcommission(commission=0.003)  # 0.3% round trip per side
```

### Fractional Sizing

Crypto allows fractional units. Backtrader supports this natively -- no special config needed.

### Slippage

For realistic simulation, enable cheat-on-open and add slippage:

```python
cerebro.broker.set_coo(True)
cerebro.broker.set_slippage_perc(0.001)  # 0.1% slippage
```

### Volatile Data

Crypto OHLCV data often has extreme wicks. Use ATR-based stops rather than fixed percentage stops to adapt to volatility.

---

## Multi-Timeframe

Backtrader can resample data to multiple timeframes within a single strategy:

```python
data_1h = bt.feeds.PandasData(dataname=df_1h)
cerebro.adddata(data_1h)

# Resample 1h to daily
cerebro.resampledata(data_1h, timeframe=bt.TimeFrame.Days, compression=1)
```

Access in strategy:

```python
def __init__(self):
    self.ema_1h = bt.ind.EMA(self.datas[0], period=20)    # hourly
    self.ema_daily = bt.ind.EMA(self.datas[1], period=20)  # daily
```

---

## Custom Indicators

```python
class SpreadIndicator(bt.Indicator):
    lines = ("spread", "zscore",)
    params = (("period", 20),)

    def __init__(self):
        mean = bt.ind.SMA(self.data, period=self.p.period)
        std = bt.ind.StdDev(self.data, period=self.p.period)
        self.lines.spread = self.data - mean
        self.lines.zscore = self.lines.spread / std
```

---

## Plotting

Backtrader includes matplotlib-based plotting:

```python
cerebro.plot(style="candlestick", volume=True)
```

For headless environments, save to file:

```python
import matplotlib
matplotlib.use("Agg")
figs = cerebro.plot(style="candlestick")
figs[0][0].savefig("backtest_result.png", dpi=150)
```

---

## Integration with Other Skills

- **pandas-ta**: Compute indicators externally, add as data feed columns. See `references/api_guide.md` for adding extra lines.
- **trading-visualization**: Export trade log from `notify_trade` and plot with the visualization skill.
- **position-sizing**: Use the `position-sizing` skill for Kelly or volatility-targeting sizers.
- **risk-management**: Apply portfolio-level guardrails from the `risk-management` skill as strategy filters.
- **slippage-modeling**: Use slippage estimates from the `slippage-modeling` skill to configure `set_slippage_perc`.

---

## Files

### References
- `references/api_guide.md` — Cerebro, Strategy, Broker, Analyzer, Data Feed API reference
- `references/strategy_patterns.md` — Reusable strategy patterns: crossover, mean reversion, multi-timeframe, custom indicators

### Scripts
- `scripts/backtest_strategy.py` — Complete EMA crossover backtest with analyzers and synthetic data
- `scripts/bracket_orders.py` — Bracket order demonstration with RSI entry and ATR-based stops

---

## Quick Start

```bash
uv pip install backtrader pandas numpy matplotlib
python scripts/backtest_strategy.py --demo
python scripts/bracket_orders.py --demo
```
