---
name: manifoldbt
description: >-
  Rust-powered backtesting engine driven from Python with a declarative
  expression DSL. Use to backtest rules over OHLCV bars, size positions as a
  fraction of equity, attach stop-loss and take-profit brackets, model fees by
  maker/taker fill, and sweep parameters across a grid.
license: MIT
metadata:
  author: manifoldbt
  version: "1.0.0"
  category: trading
---

# Backtesting with manifoldbt

## Overview

manifoldbt runs strategies in a Rust core. A strategy is not a callback: it is a
set of **expressions** (`when(fast > slow, 1.0, 0.0)`) that the engine compiles
and evaluates over every bar. The expression returns the **fraction of equity**
to hold on that bar. Fills, fees, brackets and metrics are computed by the
engine, so parameter grids of thousands of runs stay cheap.

**Key strengths:**
- Expression DSL: indicators, `when()` branches, `hold()` for stateful rules
- Bracket exits (stop-loss, take-profit, trailing) with stated fill semantics
- Fees charged per fill, split taker/maker, plus a slippage model
- Native parameter sweeps with `param()`, Monte Carlo and walk-forward
- Higher-timeframe filters (`bt.tf("24h")`) and cross-asset `symbol_ref()`

**Ways it differs from vectorbt and Backtrader:** you write the rule once as an
expression and the engine owns execution. You do not build entry/exit boolean
arrays, and you do not subclass a strategy class.

## Installation

```bash
uv pip install manifoldbt pandas
```

The package is distributed under Apache 2.0 with the Commons Clause (source
available, not OSI-approved). Runs, Monte Carlo and sweeps on bars at one minute
or coarser work on the free tier; sweeps share a budget of 256 combinations per
session. Walk-forward, larger sweeps, bars finer than one minute and the tick
layer need a paid licence. Check before building around them:
`manifoldbt.license_info()`.

## Quick Start

```python
import manifoldbt as bt
from manifoldbt.expr import col, lit, when
from manifoldbt.helpers import Interval, Slippage, time_range
from manifoldbt.indicators import sma

# 1. Bars in memory -> a store. Columns: timestamp, open, high, low, close, volume.
store = bt.import_dataframe(
    df, symbol="BTCUSDT", symbol_id=1, interval="1h",
    data_root="store/data", metadata_db="store/meta.sqlite",
)

# 2. The rule: a fraction of equity per bar (1.0 long, 0.0 flat, -1.0 short).
fast, slow = sma(col("close"), 20), sma(col("close"), 50)
strategy = (
    bt.Strategy.create("sma-cross")
    .signal("pos", when(fast > slow, lit(1.0), lit(0.0)))
    .size(col("pos"))                       # sizing reads signals by name
)

# 3. The run. Both time bounds are required.
start, end = time_range("2023-01-01", "2024-12-31")
config = bt.BacktestConfig(
    universe=[1],                           # symbol ids from the store
    time_range_start=start, time_range_end=end,
    bar_interval=Interval.hours(1),
    initial_capital=100_000.0,
    warmup_bars=50,                         # >= the longest lookback
    execution=bt.ExecutionConfig(
        signal_delay=1,                     # bar t's signal fills on bar t+1
        execution_price="AtClose",
        allow_short=False,
        position_sizing_mode="FractionOfEquity",
    ),
    fees=bt.FeeConfig(taker_fee_bps=5.0, maker_fee_bps=2.0),
    slippage=Slippage.none(),
)
result = bt.run(strategy, config, store)

m = result.metrics                          # fractions, not percents
print(m["total_return"], m["max_drawdown"], m["sharpe"])
print(m["trade_stats"]["total_trades"],     # FILLS: entry + exit = 2
      m["trade_stats"]["round_trips"])      # completed trades
equity = result.equity_df()                 # columns: timestamp, equity
```

A complete, runnable version on synthetic data (two strategies and a sweep) is
in `scripts/backtest_example.py`.

## Core Concepts

### 1. The sizing rule is a fraction, and `hold()` is "do nothing"

Return `1.0`, `0.0` or `-1.0` (shorts need `allow_short=True`). A rule that
should keep its current position on bars where no condition fires ends with
`hold()`. Without it the position flips on every bar the entry condition is
false.

```python
from manifoldbt.expr import hold
r = rsi(col("close"), 14)
pos = when(r < lit(30.0), lit(1.0),
      when(r > lit(55.0), lit(0.0), hold()))   # last branch = otherwise
```

Combine conditions with `&` and `|`, never the words `and`/`or`. Price columns
are bare names: `col("close")`, `col("high")`.

### 2. Brackets attach to the strategy

```python
strategy = (bt.Strategy.create("breakout")
            .signal("pos", entry).size(col("pos"))
            .stop_loss(pct=2.0).take_profit(pct=4.0))
```

The engine watches high and low from the bar **after** the entry filled. If both
levels are hit on one bar the stop wins. A gap through the stop fills at the
open; a gap through the target still fills at the target. A take-profit is a
**maker** fill and a stop is a **taker** fill, so set both fee fields:
`taker_fee_bps` alone lets every target exit out for free.

### 3. Fees and slippage are per fill

`FeeConfig(taker_fee_bps=..., maker_fee_bps=...)` charges notional per fill. A
reversal is one fill whose quantity is both legs added together.
`Slippage.none()` turns slippage off; pick `fixed_bps`, `spread_based` or
`volume_impact` explicitly when the market justifies it.

### 4. Parameters and sweeps

```python
from manifoldbt.expr import param
fast = sma(col("close"), param("fast", default=20))
slow = sma(col("close"), param("slow", default=50))
sweep = bt.run_sweep(strategy, {"fast": [10, 20, 30], "slow": [50, 100, 150]},
                     config, store)
df = sweep.to_df()      # one row per combination, columns param_fast, param_slow, ...
```

`warmup_bars` must cover the **largest** period in the grid. Read the whole
surface (`pivot_table`), not only its best cell. See
`references/research_guide.md`.

### 5. Higher timeframes and other markets

```python
d = bt.tf("24h")
trend = d.apply(sma(col("close"), 20))          # 20 DAILY candles, closed ones only
# BacktestConfig(..., extra_timeframes={"24h": Interval.hours(24)}, warmup_bars=500)
```

`symbol_ref("provider:TICKER", "close")` reads another market inside a
`.signal()` (never in `.size()`) with a dict universe such as
`{"dataframe": ["A", "B"]}`. Write the traded market's own price as
`col("close")` and only the other leg as `symbol_ref(...)`.

## Common Pitfalls

- **Empty window:** a missing end date is an empty window, not "until now". Use
  `time_range(start, end)`.
- **Reopening a store:** `DataStore(data_root, db)` alone reads Parquet and finds
  no bars. Pass `arrow_dir=f"{data_root}/mega"`. The error
  `empty bar dataset for symbol` while `list_symbols()` still answers means this.
- **`total_trades` counts fills,** `round_trips` counts trades. Compare win
  rates and averages on round trips.
- **Indicator periods:** `sma(d.close, 20)` on a daily frame counts hourly bars,
  `d.apply(sma(close, 20))` counts days.
- **ddof differs:** metrics use the sample std, indicators the population one.
- **Windows:** a store keeps its SQLite file open, so
  `tempfile.TemporaryDirectory()` raises on cleanup. Use `mkdtemp()` and
  `shutil.rmtree(..., ignore_errors=True)`.

## Use Cases

1. **Rule testing:** state a hypothesis as one expression, run it, read
   `trade_stats` and the equity curve.
2. **Parameter surfaces:** sweep a grid and look for a plateau, not a peak.
3. **Exit design:** compare stop/target distances with correct maker/taker fees.
4. **Multi-timeframe filters:** gate hourly entries on a daily trend.
5. **Pairs and spreads:** `symbol_ref()` with a stateful z-score band.

## Integration with Other Skills

- **pandas-ta** — compute indicators there and feed them in as an exogenous
  series: `bt.register_exo("name", frame, store=store)`,
  `BacktestConfig(exo_data=["name"])`, `exo("name", "column")` in an expression.
  A column added to the input DataFrame is not visible to expressions.
- **strategy-framework** — write the rule, risk and exit definition first, then
  implement it here.
- **walk-forward-validation** — manifoldbt's own `run_walk_forward` needs a paid
  tier; the method in that skill applies to any engine.
- **position-sizing** and **risk-management** — feed the sizing fraction.

## Files

### References
- `references/api_guide.md` — Store, Strategy, BacktestConfig, execution and result API
- `references/research_guide.md` — Reading sweeps, fees, look-ahead and honest metrics

### Scripts
- `scripts/backtest_example.py` — SMA crossover, RSI band with bracket, and a 3 x 3 sweep on synthetic bars

## Disclaimer

Backtests are simulations. Results on historical or synthetic data do not
predict returns. This skill is not financial advice.
