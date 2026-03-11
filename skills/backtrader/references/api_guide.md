# Backtrader API Guide

## Cerebro

The engine that ties everything together.

### Constructor & Configuration

```python
import backtrader as bt

cerebro = bt.Cerebro(
    preload=True,       # preload data feeds (default True)
    runonce=True,        # vectorized indicator calc (default True)
    optreturn=True,      # return lightweight results in optimize mode
    stdstats=True,       # add default observers (Broker, Trades, BuySell)
    cheat_on_open=False, # execute orders at next bar open
)
```

### Key Methods

| Method | Description |
|---|---|
| `addstrategy(cls, **kwargs)` | Add a strategy class with parameters |
| `adddata(data, name=None)` | Add a data feed |
| `resampledata(data, timeframe, compression)` | Resample data to a higher timeframe |
| `addanalyzer(cls, _name=str)` | Attach an analyzer |
| `addsizer(cls, **kwargs)` | Set a position sizer |
| `addwriter(cls, **kwargs)` | Add output writer (CSV) |
| `optstrategy(cls, **kwargs)` | Add strategy for parameter optimization (pass lists) |
| `run(**kwargs)` | Execute the backtest; returns list of strategy instances |
| `plot(style, volume, numfigs)` | Plot results with matplotlib |

### Broker Configuration

```python
cerebro.broker.setcash(100_000.0)
cerebro.broker.setcommission(commission=0.003)  # 0.3%
cerebro.broker.set_coo(True)                    # cheat on open
cerebro.broker.set_slippage_perc(0.001)          # 0.1% slippage
cerebro.broker.getvalue()                        # current portfolio value
cerebro.broker.getcash()                         # current cash
cerebro.broker.getposition(data)                 # position for data feed
```

Commission models:

```python
# Percentage-based (crypto default)
cerebro.broker.setcommission(commission=0.003)

# Fixed per-unit (equities)
cerebro.broker.setcommission(commission=0.005, commtype=bt.CommInfoBase.COMM_FIXED)

# Custom CommissionInfo
class CryptoCommission(bt.CommInfoBase):
    params = (("commission", 0.003), ("mult", 1.0), ("margin", None),
              ("commtype", bt.CommInfoBase.COMM_PERC),
              ("stocklike", True),)
cerebro.broker.addcommissioninfo(CryptoCommission())
```

---

## Strategy

### Class Structure

```python
class MyStrategy(bt.Strategy):
    params = (
        ("fast_period", 10),
        ("slow_period", 30),
        ("risk_pct", 0.02),
    )

    def __init__(self) -> None:
        """Define indicators. Runs once before backtesting."""
        self.ema_fast = bt.ind.EMA(period=self.p.fast_period)
        self.ema_slow = bt.ind.EMA(period=self.p.slow_period)

    def next(self) -> None:
        """Called on every bar. Place orders here."""
        pass

    def notify_order(self, order: bt.Order) -> None:
        """Called when order status changes."""
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY @ {order.executed.price:.2f}")
            else:
                self.log(f"SELL @ {order.executed.price:.2f}")

    def notify_trade(self, trade: bt.Trade) -> None:
        """Called when trade opens or closes."""
        if trade.isclosed:
            self.log(f"TRADE P&L: gross={trade.pnl:.2f} net={trade.pnlcomm:.2f}")

    def log(self, txt: str) -> None:
        dt = self.datas[0].datetime.date(0)
        print(f"{dt} | {txt}")
```

### Accessing Data Lines

```python
# Current bar values
self.data.open[0]    # current open
self.data.high[0]    # current high
self.data.low[0]     # current low
self.data.close[0]   # current close (alias: self.data[0])
self.data.volume[0]  # current volume

# Previous bars
self.data.close[-1]  # previous close
self.data.close[-2]  # two bars ago

# Named data feeds
self.datas[0]  # first data feed
self.datas[1]  # second data feed (e.g., resampled)
```

### Order Methods

```python
# Market orders
order = self.buy(size=100)
order = self.sell(size=100)
self.close()  # close entire position

# Limit order
self.buy(exectype=bt.Order.Limit, price=95.0, size=50)

# Stop order
self.sell(exectype=bt.Order.Stop, price=90.0, size=50)

# Stop-limit order
self.buy(exectype=bt.Order.StopLimit, price=100.0, plimit=101.0, size=50)

# Bracket order (entry + stop loss + take profit)
orders = self.buy_bracket(
    price=100.0,            # entry price (limit)
    stopprice=95.0,         # stop loss trigger
    limitprice=110.0,       # take profit
    size=50,
)
# returns (main_order, stop_order, limit_order)

# Cancel an order
self.cancel(order)

# Order valid for N bars
self.buy(exectype=bt.Order.Limit, price=95.0,
         valid=self.data.datetime.date(0) + datetime.timedelta(days=3))
```

### Order Status Values

| Status | Meaning |
|---|---|
| `Order.Created` | Order created but not yet submitted |
| `Order.Submitted` | Sent to broker |
| `Order.Accepted` | Accepted by broker |
| `Order.Partial` | Partially filled |
| `Order.Completed` | Fully filled |
| `Order.Canceled` | Canceled (by user or broker) |
| `Order.Expired` | Validity period expired |
| `Order.Margin` | Insufficient margin/cash |
| `Order.Rejected` | Rejected by broker |

---

## Built-in Analyzers

| Analyzer | Key Output Fields |
|---|---|
| `SharpeRatio` | `sharperatio` |
| `DrawDown` | `max.drawdown`, `max.len`, `max.moneydown` |
| `TradeAnalyzer` | `total.total`, `won.total`, `lost.total`, `pnl.net.total` |
| `Returns` | `rtot`, `ravg`, `rnorm`, `rnorm100` |
| `SQN` | `sqn`, `trades` |
| `TimeReturn` | Dict of `{datetime: return}` |
| `AnnualReturn` | Dict of `{year: return}` |
| `Calmar` | `calmar` |
| `VWR` | `vwr` |
| `PeriodStats` | `average`, `stddev`, `positive`, `negative`, `best`, `worst` |

### Accessing Analyzer Results

```python
results = cerebro.run()
strat = results[0]

sharpe_dict = strat.analyzers.sharpe.get_analysis()
sharpe_value = sharpe_dict.get("sharperatio", 0.0)

dd_dict = strat.analyzers.drawdown.get_analysis()
max_dd = dd_dict.max.drawdown  # percentage

trades_dict = strat.analyzers.trades.get_analysis()
total_trades = trades_dict.total.total
won = trades_dict.won.total
lost = trades_dict.lost.total
```

---

## Data Feeds

### From pandas DataFrame

```python
import pandas as pd

df = pd.read_csv("ohlcv.csv", parse_dates=["date"], index_col="date")
# Columns must include: open, high, low, close, volume
# Index must be DatetimeIndex

data = bt.feeds.PandasData(dataname=df)
cerebro.adddata(data)
```

### Adding Extra Lines (e.g., external indicators)

```python
class PandasDataWithSignal(bt.feeds.PandasData):
    lines = ("signal",)
    params = (("signal", -1),)  # -1 = column index or column name

# DataFrame must have a 'signal' column
data = PandasDataWithSignal(dataname=df)
```

### From CSV

```python
data = bt.feeds.GenericCSVData(
    dataname="ohlcv.csv",
    dtformat="%Y-%m-%d %H:%M:%S",
    datetime=0, open=1, high=2, low=3, close=4, volume=5,
    openinterest=-1,
)
```

---

## Sizers

| Sizer | Description |
|---|---|
| `FixedSize(stake=N)` | Buy exactly N units |
| `PercentSizer(percents=P)` | Use P% of portfolio value |
| `AllInSizer(percents=P)` | Use P% of available cash |
| `FixedReverser(stake=N)` | Reverse position with fixed size |

### Custom Sizer

```python
class ATRSizer(bt.Sizer):
    params = (("risk_pct", 0.02),)

    def _getsizing(self, comminfo, cash, data, isbuy) -> int:
        atr = self.strategy.atr[0]
        if atr <= 0:
            return 0
        risk_amount = self.broker.getvalue() * self.p.risk_pct
        return int(risk_amount / atr)
```

---

## Parameter Optimization

```python
cerebro.optstrategy(MyStrategy,
    fast_period=range(5, 20, 5),
    slow_period=range(20, 60, 10),
)
results = cerebro.run(maxcpus=4)

for run in results:
    for strat in run:
        sharpe = strat.analyzers.sharpe.get_analysis().get("sharperatio", 0)
        params = strat.params._getkwargs()
        print(f"  {params} -> Sharpe: {sharpe}")
```
