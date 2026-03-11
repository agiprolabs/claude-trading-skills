# Backtrader Strategy Patterns

## 1. EMA Crossover with Bracket Orders

Entry on EMA crossover, with ATR-based stop loss and risk-reward take profit.

```python
class EMABracket(bt.Strategy):
    params = (
        ("fast", 10), ("slow", 30),
        ("atr_period", 14), ("atr_mult", 2.0),
        ("rr_ratio", 2.0),  # risk:reward
    )

    def __init__(self) -> None:
        self.ema_fast = bt.ind.EMA(period=self.p.fast)
        self.ema_slow = bt.ind.EMA(period=self.p.slow)
        self.crossover = bt.ind.CrossOver(self.ema_fast, self.ema_slow)
        self.atr = bt.ind.ATR(period=self.p.atr_period)

    def next(self) -> None:
        if self.position:
            return

        if self.crossover > 0:
            entry = self.data.close[0]
            stop_dist = self.atr[0] * self.p.atr_mult
            stop_price = entry - stop_dist
            tp_price = entry + stop_dist * self.p.rr_ratio

            self.buy_bracket(
                limitprice=tp_price,
                stopprice=stop_price,
                exectype=bt.Order.Market,
            )

    def notify_order(self, order: bt.Order) -> None:
        if order.status == order.Completed:
            action = "BUY" if order.isbuy() else "SELL"
            dt = self.data.datetime.date(0)
            print(f"{dt} | {action} @ {order.executed.price:.4f}")
```

**Key points:**
- `buy_bracket` with `exectype=bt.Order.Market` enters immediately; the stop and limit are placed as child orders.
- When the stop fills, the take-profit is auto-canceled (and vice versa).
- ATR-based distances adapt to current volatility.

---

## 2. RSI Mean Reversion with Stop-Limit

Enter on RSI oversold, exit on RSI overbought or stop loss.

```python
class RSIMeanReversion(bt.Strategy):
    params = (
        ("rsi_period", 14),
        ("oversold", 30), ("overbought", 70),
        ("stop_pct", 0.05),
    )

    def __init__(self) -> None:
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)
        self.order = None

    def next(self) -> None:
        if self.order:
            return

        if not self.position:
            if self.rsi[0] < self.p.oversold:
                entry = self.data.close[0]
                stop = entry * (1 - self.p.stop_pct)
                self.order = self.buy()
                self.sell(exectype=bt.Order.Stop, price=stop)
        else:
            if self.rsi[0] > self.p.overbought:
                self.order = self.close()

    def notify_order(self, order: bt.Order) -> None:
        if order.status in [order.Completed, order.Canceled, order.Margin]:
            self.order = None
```

**Key points:**
- Tracks pending order to avoid duplicate entries.
- Stop loss placed immediately after entry fill.
- Exits on RSI overbought or stop hit.

---

## 3. Multi-Timeframe Strategy

Use daily trend direction with hourly entry timing.

```python
class MultiTimeframe(bt.Strategy):
    params = (("ema_period", 20),)

    def __init__(self) -> None:
        # datas[0] = hourly, datas[1] = daily (resampled)
        self.ema_hourly = bt.ind.EMA(self.datas[0], period=self.p.ema_period)
        self.ema_daily = bt.ind.EMA(self.datas[1], period=self.p.ema_period)

    def next(self) -> None:
        daily_trend_up = self.datas[1].close[0] > self.ema_daily[0]

        if not self.position:
            # Only buy when daily trend is up and hourly pulls back to EMA
            if daily_trend_up and self.datas[0].close[0] > self.ema_hourly[0]:
                if self.datas[0].close[-1] <= self.ema_hourly[-1]:
                    self.buy()
        else:
            if not daily_trend_up:
                self.close()
```

**Setup in Cerebro:**

```python
data_1h = bt.feeds.PandasData(dataname=df_1h)
cerebro.adddata(data_1h)
cerebro.resampledata(data_1h, timeframe=bt.TimeFrame.Days, compression=1)
cerebro.addstrategy(MultiTimeframe)
```

---

## 4. Custom Indicator

Creating a Bollinger Band Width indicator:

```python
class BollingerWidth(bt.Indicator):
    lines = ("bbwidth", "bbpctb",)
    params = (("period", 20), ("devfactor", 2.0),)

    def __init__(self) -> None:
        bb = bt.ind.BollingerBands(
            self.data, period=self.p.period, devfactor=self.p.devfactor
        )
        self.lines.bbwidth = (bb.top - bb.bot) / bb.mid * 100.0
        self.lines.bbpctb = (self.data - bb.bot) / (bb.top - bb.bot)
```

**Usage in strategy:**

```python
def __init__(self):
    self.bbw = BollingerWidth(self.data, period=20)

def next(self):
    if self.bbw.bbwidth[0] < 5.0:   # squeeze
        if self.bbw.bbpctb[0] > 0.8:  # near upper band
            self.buy()
```

---

## 5. Position Management: Pyramiding

Scale into a position across multiple bars:

```python
class PyramidStrategy(bt.Strategy):
    params = (("max_entries", 3), ("entry_spacing_pct", 0.02),)

    def __init__(self) -> None:
        self.ema = bt.ind.EMA(period=20)
        self.entry_count = 0
        self.last_entry_price = 0.0

    def next(self) -> None:
        price = self.data.close[0]

        if price > self.ema[0] and self.entry_count < self.p.max_entries:
            if self.entry_count == 0:
                self.buy(size=100)
                self.last_entry_price = price
                self.entry_count += 1
            elif price > self.last_entry_price * (1 + self.p.entry_spacing_pct):
                self.buy(size=100)
                self.last_entry_price = price
                self.entry_count += 1

        elif price < self.ema[0] and self.position:
            self.close()
            self.entry_count = 0
            self.last_entry_price = 0.0
```

---

## 6. Scaling Out (Partial Exits)

Take partial profits at targets:

```python
class ScaleOut(bt.Strategy):
    params = (("tp1_pct", 0.03), ("tp2_pct", 0.06),)

    def __init__(self) -> None:
        self.entry_price = 0.0
        self.took_tp1 = False

    def next(self) -> None:
        if not self.position:
            if self.some_entry_signal():
                self.buy(size=200)
                self.entry_price = self.data.close[0]
                self.took_tp1 = False
            return

        pnl_pct = (self.data.close[0] - self.entry_price) / self.entry_price

        if not self.took_tp1 and pnl_pct >= self.p.tp1_pct:
            self.sell(size=100)  # sell half
            self.took_tp1 = True
        elif pnl_pct >= self.p.tp2_pct:
            self.close()  # sell remainder

    def some_entry_signal(self) -> bool:
        return False  # replace with actual logic
```

---

## Common Pitfalls

### 1. Lookahead Bias

Using `self.data.close[0]` in `next()` is the current bar's close, which is only known at bar close. If you place a market order based on close, it executes at the next bar's open. Use `cheat_on_open` to execute at the current bar's open instead.

### 2. Forgetting to Check Position

Always check `self.position` before entering. Without this check, you will stack orders every bar.

### 3. Not Handling Order Rejections

Orders can be rejected due to insufficient cash (Margin status). Always handle this in `notify_order`:

```python
def notify_order(self, order):
    if order.status == order.Margin:
        print("WARNING: Order rejected - insufficient margin")
```

### 4. Indicator Warm-up

Indicators need `period` bars to produce values. Backtrader handles this automatically -- `next()` is not called until all indicators are ready. But if you manually check `len(self)`, be aware that it starts at `period`, not 0.

### 5. Multiple Data Feed Alignment

When using multiple data feeds (multi-timeframe), the slower feed may not have data for every bar. Always check `len(self.datas[1])` before accessing its values.

### 6. Parameter Optimization Overfitting

Using `optstrategy` to find optimal parameters on in-sample data will overfit. Always reserve an out-of-sample period:

```python
# Split data: first 80% for optimization, last 20% for validation
split_idx = int(len(df) * 0.8)
df_train = df.iloc[:split_idx]
df_test = df.iloc[split_idx:]
```

### 7. Commission Double-Counting

`setcommission(commission=0.003)` applies per trade side. A round trip (buy + sell) costs 0.6% total. Make sure you are not doubling this.
