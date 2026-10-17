# Reading manifoldbt results honestly

A backtest engine reports what the rule would have done on the bars it was
given. Whether that means anything is a separate question. This guide covers the
checks that belong between "the run finished" and "the strategy works".

## Fills before metrics

- Read `result.warnings` and `result.brackets_not_armed` after every run. A
  bracket whose distance was NaN on the signal bar arms nothing and is only
  reported by `brackets_not_armed`; a Sharpe over a very short run comes with a
  warning.
- `trade_stats["total_trades"]` counts **fills**. An entry and an exit are two.
  Win rate, average win and average loss are per **round trip**.
- Open `result.trades_df()` on at least one run and read the fills against the
  bars. It is the quickest way to catch a signal that lands a bar early or late.

## Look-ahead

- `signal_delay=1` fills the signal computed on bar t on bar t+1. `0` fills on
  the bar that produced the signal, which is look-ahead for any signal computed
  from that bar's close.
- A higher-timeframe value changes only on the first bar after its candle
  closes. Build it with `bt.tf(...).apply(...)`, not by resampling yourself.
- An external series must be forward-filled from its own timestamps. Drop NaN
  rows before `register_exo` so the as-of join does not start from nothing.
- Never fit a threshold on the full sample and then report the same sample.

## Fees decide scalping and breakout results

- Set `taker_fee_bps` **and** `maker_fee_bps`. Stops and trailing exits pay the
  taker fee, take-profit exits pay the maker fee.
- Fees are charged per fill on notional. A rule that flips every few bars pays
  for each flip: compare `total_fees` against `pnl` before looking at Sharpe.
- A reversal is one fill carrying both legs, so it costs one fee on the sum.

## Sweeps inflate their own best result

Trying many combinations and keeping the best selects for luck as well as
skill. The best in-sample Sharpe climbs with the grid size even on pure noise.

1. Print the whole surface (`pivot_table`), not `idxmax`.
2. Look for a **contiguous region** of good cells. A lone spike surrounded by
   poor neighbours is overfitting.
3. Prefer a parameter set from the middle of a plateau over the argmax. Pool the
   cells of the plateau if you need one answer.
4. Count the cells you tried. The more you tried, the less the winner is worth.
5. Confirm on data the sweep never saw. `run_walk_forward` does this on a paid
   tier; the `walk-forward-validation` skill covers the method for any engine.

The synthetic series in `scripts/backtest_example.py` has no edge by
construction. Its sweep still shows positive-Sharpe cells at the long end of the
grid: slower averages trade less and pay fewer fees. That gradient is what a
noise surface looks like, which is why a single number from it is not a result.

## Metrics

- `sharpe` uses daily equity returns, sample standard deviation, annualized by
  `trading_days_per_year` (365.25 by default). A run shorter than two days has no
  meaningful value.
- Read `tstat_sharpe` next to `sharpe`. Below roughly 2 the Sharpe is not
  distinguishable from luck. A 1.5 Sharpe on 30 trades is a hint; on 800 trades
  over ten years it is evidence.
- `max_drawdown` is a negative fraction. Compare it with `max_drawdown_duration_days`.
- Metrics use the sample standard deviation (`ddof=1`); indicators such as
  `zscore` use the population one. Do not mix them when recomputing by hand.
- Recompute any figure you rely on from `result.equity_df()`.

## Position sizing semantics

- The sizing expression is a fraction of equity. With
  `position_sizing_mode="FractionOfEquity"` the quantity is fixed at each fill
  and is not rebalanced between two changes of target.
- `hold()` keeps the current position. `-1.0` is a short, not "do nothing".
- A portfolio is independent legs summed. It is not a risk engine and does not
  enforce a joint exposure limit.
