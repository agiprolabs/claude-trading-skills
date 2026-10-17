# manifoldbt API guide

Covers manifoldbt 0.27. Check the installed version with
`manifoldbt.__version__`; the documentation for older versions is not maintained.

## Data

```python
store = bt.import_dataframe(df, symbol="BTCUSDT", symbol_id=1, interval="1h",
                            data_root="store/data", metadata_db="store/meta.sqlite")
store = bt.import_csv(...)      # same idea, from a file
store = bt.ingest(...)          # built-in connectors (crypto on the free tier)
```

`df` needs the columns `timestamp, open, high, low, close, volume`, with
timestamps as UTC. The symbol id is what `BacktestConfig(universe=[...])` refers to.

Reopen an existing store with the Arrow pointer:

```python
store = bt.DataStore("store/data", "store/meta.sqlite", arrow_dir="store/data/mega")
```

An external series (an indicator computed elsewhere, funding, on-chain) enters as
an exogenous series, not as an extra DataFrame column:

```python
bt.register_exo("hashrate", frame_with_timestamp, store=store)   # drop NaN rows first
cfg = bt.BacktestConfig(..., exo_data=["hashrate"])
# in an expression: exo("hashrate", "value")  (from manifoldbt.expr import exo)
```

## Strategy

| Call | Purpose |
|------|---------|
| `bt.Strategy.create(name)` | Start a strategy |
| `.signal(name, expr)` | A named series. At least one is required. A signal may reference an earlier signal |
| `.size(expr)` | Fraction of equity per bar. Reads signals by name |
| `.stop_loss(pct=...)`, `.take_profit(pct=...)`, `.trailing_stop(...)` | Bracket exits |
| `.limit_entry(...)`, `.stop_entry(...)`, `.stop_limit_entry(...)`, `.market_if_touched(...)` | Resting entry orders. These need `signal_delay >= 1` |

Expressions come from `manifoldbt.expr`: `col`, `lit`, `when`, `hold`, `param`,
`exo`. Indicators come from `manifoldbt.indicators` (`sma`, `ema`, `rsi`, `atr`,
`bollinger_bands`, `keltner_channels`, `supertrend`, ...). Rolling helpers hang
off an expression: `.lag(1)`, `.rolling_max(50)`, `.rolling_mean(50)`,
`.zscore(200)`.

A tuple indicator (`bollinger_bands`) returns `(upper, middle, lower)`. It cannot
be indexed as one expression; unpack it.

## BacktestConfig

| Field | Notes |
|-------|-------|
| `universe` | `[1]` for symbol ids, or `{"provider": ["TICKER", ...]}` with `symbol_ref()` |
| `time_range_start`, `time_range_end` | From `time_range("YYYY-MM-DD", "YYYY-MM-DD")`. Half-open window |
| `bar_interval` | `Interval.minutes(5)`, `.hours(1)`, `.days(1)`. One minute or coarser on the free tier |
| `initial_capital` | Starting cash |
| `warmup_bars` | At least the longest indicator window. The first fill lands at bar `warmup_bars + signal_delay` |
| `extra_timeframes` | `{"24h": Interval.hours(24)}` for `bt.tf("24h")` |
| `exo_data` | Names registered with `register_exo` |
| `execution` | `ExecutionConfig` |
| `fees`, `slippage` | `FeeConfig`, a `Slippage` model |
| `trading_days_per_year`, `risk_free_rate` | Annualization of the metrics |

`ExecutionConfig` fields: `signal_delay` (1 fills the signal of bar t on bar
t+1), `execution_price` (`"AtClose"` or `"AtOpen"`), `allow_short`,
`allow_fractional`, `max_position_pct`, `position_sizing_mode`
(`"FractionOfEquity"` fixes the quantity at each fill and does not rebalance by
itself), `pyramiding`, `skip_gap_bars`.

`FeeConfig` fields: `taker_fee_bps`, `maker_fee_bps`, `min_fee`,
`funding_rate_column`, `borrow_rate_annual_bps`. Slippage models:
`Slippage.none()`, `.fixed_bps(...)`, `.spread_based(...)`, `.volume_impact(...)`.

## Running

| Call | Use |
|------|-----|
| `bt.run(strategy, config, store)` | One backtest |
| `bt.run_sweep(strategy, grid, config, store)` | Cartesian grid over `param()` names |
| `bt.run_sweep_lite(...)` | Metrics only, cheaper, no trade log |
| `bt.run_sweep_2d(strategy, sweep_config, config, store)` | Two parameters shaped as a heatmap |
| `bt.run_batch(...)`, `bt.run_portfolio(...)` | Several strategies or legs. A portfolio is independent legs summed |
| `bt.run_stability(strategy, stability_config, config, store)` | Varies one parameter (`param_name`, `values`, `metric`) and returns `stability_score`, `mean_metric`, `std_metric`. Pro |
| `bt.run_walk_forward(strategy, wf_config, config, store)` | Anchored, blocked, Pardo or custom folds, with a warmed-up out-of-sample run. Paid tier |

The free tier allows 256 combinations per session, spent cumulatively across
`run_sweep`, `run_sweep_2d`, `run_batch` and `run_stability`. A 300-combination
grid is refused, and so is a second 150-combination grid after a first one.

## Result

```python
m = result.metrics                 # dict, fractions not percents
m["total_return"], m["max_drawdown"], m["sharpe"], m["sortino"], m["calmar"]
m["trade_stats"]                   # total_trades (fills), round_trips, win_rate, ...
result.equity_df()                 # timestamp, equity
result.trades_df()                 # one row per fill
result.positions_df()              # per-bar position trace
result.daily_returns_series()
result.warnings                    # read it after every run
result.brackets_not_armed          # bracket distances that were NaN and armed nothing
```

`sharpe` is computed on daily equity returns with `ddof=1` and annualized with
`trading_days_per_year` (365.25 by default). A run shorter than two days has no
meaningful Sharpe.
