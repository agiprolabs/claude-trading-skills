#!/usr/bin/env python3
"""Two-strategy backtest and a small sweep with manifoldbt, on synthetic bars.

Runs, on one synthetic hourly OHLCV series:
  1. SMA crossover (20/50), long only.
  2. RSI mean reversion with a stateful band (hold()) and a bracket exit.
Then sweeps the SMA crossover over a 3 x 3 grid of fast/slow lengths and prints
the whole surface, not only its best cell.

Everything here runs on the free (Community) tier.

Usage:
    python scripts/backtest_example.py

Dependencies:
    uv pip install manifoldbt pandas numpy
"""

import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

try:
    import manifoldbt as bt
    from manifoldbt.expr import col, hold, lit, param, when
    from manifoldbt.helpers import Interval, Slippage, time_range
    from manifoldbt.indicators import rsi, sma
except ImportError:
    print("manifoldbt is required. Install with: uv pip install manifoldbt")
    sys.exit(1)

SYMBOL_ID = 1
START, END = "2023-01-01", "2024-12-31"


def synthetic_bars(seed: int = 7) -> pd.DataFrame:
    """Hourly OHLCV from a geometric random walk with a slow drift."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range(START, END, freq="1h", tz="UTC")
    ret = rng.normal(0.00002, 0.004, len(ts))
    close = 100.0 * np.exp(np.cumsum(ret))
    open_ = np.r_[close[0], close[:-1]]
    span = np.abs(rng.normal(0, 0.002, len(ts))) * close
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": np.maximum(open_, close) + span,
            "low": np.minimum(open_, close) - span,
            "close": close,
            "volume": rng.uniform(100, 1000, len(ts)),
        }
    )


def make_config(warmup: int) -> "bt.BacktestConfig":
    start, end = time_range(START, END)  # both bounds, always
    return bt.BacktestConfig(
        universe=[SYMBOL_ID],
        time_range_start=start,
        time_range_end=end,
        bar_interval=Interval.hours(1),
        initial_capital=100_000.0,
        warmup_bars=warmup,  # must cover the longest indicator window
        execution=bt.ExecutionConfig(
            signal_delay=1,  # the signal of bar t fills on bar t+1
            execution_price="AtClose",
            allow_short=False,
            position_sizing_mode="FractionOfEquity",
        ),
        # A take-profit exit is a maker fill, a stop a taker fill: set both.
        fees=bt.FeeConfig(taker_fee_bps=5.0, maker_fee_bps=2.0),
        slippage=Slippage.none(),
    )


def show(name: str, result: "bt.BacktestResult") -> None:
    m = result.metrics  # fractions, not percents
    ts = m["trade_stats"]
    print(
        f"{name:<22} return {m['total_return'] * 100:7.2f}%  "
        f"maxDD {m['max_drawdown'] * 100:7.2f}%  sharpe {m['sharpe']:6.2f}  "
        f"fills {ts['total_trades']:4d}  round trips {ts['round_trips']:4d}"
    )


def main() -> None:
    workdir = tempfile.mkdtemp(prefix="mbt_")  # a store keeps its sqlite file open
    try:
        store = bt.import_dataframe(
            synthetic_bars(),
            symbol="SYNTH",
            symbol_id=SYMBOL_ID,
            interval="1h",
            data_root=f"{workdir}/data",
            metadata_db=f"{workdir}/meta.sqlite",
        )

        # 1. SMA crossover: the rule returns a fraction of equity per bar.
        fast, slow = sma(col("close"), 20), sma(col("close"), 50)
        sma_cross = (
            bt.Strategy.create("sma-cross")
            .signal("pos", when(fast > slow, lit(1.0), lit(0.0)))
            .size(col("pos"))
        )
        show("SMA 20/50", bt.run(sma_cross, make_config(warmup=50), store))

        # 2. RSI band: enter below 30, leave above 55, otherwise keep the position.
        r = rsi(col("close"), 14)
        band = when(r < lit(30.0), lit(1.0), when(r > lit(55.0), lit(0.0), hold()))
        rsi_band = (
            bt.Strategy.create("rsi-band")
            .signal("pos", band)
            .size(col("pos"))
            .stop_loss(pct=3.0)
            .take_profit(pct=4.0)
        )
        show("RSI band + bracket", bt.run(rsi_band, make_config(warmup=50), store))

        # 3. Sweep: read the whole surface, a lone best cell is mostly noise.
        sweep_strat = (
            bt.Strategy.create("sma-cross-sweep")
            .signal(
                "pos",
                when(
                    sma(col("close"), param("fast", default=20))
                    > sma(col("close"), param("slow", default=50)),
                    lit(1.0),
                    lit(0.0),
                ),
            )
            .size(col("pos"))
        )
        grid = {"fast": [10, 20, 30], "slow": [50, 100, 150]}
        sweep = bt.run_sweep(sweep_strat, grid, make_config(warmup=150), store)
        surface = sweep.to_df().pivot_table(
            index="param_fast", columns="param_slow", values="sharpe"
        )
        print("\nSharpe surface, fast (rows) x slow (columns):")
        print(surface.round(2).to_string())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
