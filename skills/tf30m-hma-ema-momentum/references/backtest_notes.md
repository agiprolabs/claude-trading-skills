# Backtest Notes — BTC/ETH/SOL/XRP/XAU/XAG, Jan–Jun 2026

Findings from a 6-month, 6-symbol portfolio backtest run with
`scripts/portfolio_backtest.py` against historical OHLCV, using the exact
defaults baked into `run_bot.py` (15m bars, `LEVERAGE=20`,
`MARGIN_FRACTION=0.05`, `MAX_OPEN_POSITIONS=2`, ATR(14)×1.5 SL/TP). Recorded
here so the reasoning behind the `TIMEFRAME=15m` default and the known
drawdown-halt bug isn't lost.

## Why 15m, not 30m

A source dataset covering BTC, ETH, SOL, XRP, XAU, XAG had complete 6-month
history at **15m** for all six symbols, but 30m data existed only for BTC and
XAU (and only partially — 5 of 6 months). Since the strategy's indicator
periods are bar counts, not durations, they carry over unchanged to 15m (see
SKILL.md "Timeframe"). 15m is therefore the default that is actually validated
against real data across the whole watchlist; 30m remains supported and
should be re-validated with its own complete dataset before relying on it.

## Critical bug: the drawdown halt is a one-way lock in practice

The backtest hit `MAX_DRAWDOWN_PCT=0.15` on day ~40 and **never traded again
for the remaining ~4.5 months** — `RiskManager.is_halted` was still `True` at
the end of the run.

Root cause, in `risk_manager.py`:

```python
def check_drawdown(self, current_balance: float) -> bool:
    ...
    if self._halted and drawdown < self.max_drawdown_pct * 0.5:
        self._halted = False  # intended auto-recovery
    return not self._halted
```

`check_drawdown` (via `run_bot.py`'s `_update_drawdown()`) is only called
from `_exit()` — i.e. when a trade closes. Once halted, `RiskManager.can_open`
blocks every new entry, so no trade can open, so none can ever close, so
`_update_drawdown()` never runs again, so the recovery condition is never
re-evaluated. The halt is a **permanent lock** for the life of the process,
not the "auto-resets... preventing the bot from staying halted indefinitely"
behavior the docstring describes. A live deployment that hits a 15% drawdown
will sit idle forever unless the process is restarted (which resets
`RiskManager` state from scratch).

**Status: known, not yet fixed.** Fix candidates: periodically re-check
`check_drawdown` against current unrealized equity even while flat, or
change the recovery condition to not depend on a trade closing.

## Why win rate came out low (36.0%, 444 trades)

Breaking the same 444 trades down by exit reason explains it:

| Exit reason | Count | Share | Win rate | Avg P&L |
|---|---|---|---|---|
| SIGNAL (HMA/EMA/ROC reversal) | 252 | 56.8% | 14.7% | -$18.88 |
| STOP | 69 | 15.5% | 0% (by definition) | -$77.89 |
| TAKE_PROFIT | 123 | 27.7% | 100% (by definition) | +$77.25 |

The **entry** requires three things to align (HMA gate, EMA cross, ≥3-of-4
confirmation score) — strict. The **exit** fires on any *one* of three
reversal conditions (§15/16 of the spec) — loose, by design, to cut losers
fast. In practice that asymmetry means most trades (57%) get closed by a
reversal signal long before reaching the ATR×1.5 target, and 85% of those
signal-exits close at a small loss rather than a small gain — the position
often hasn't moved far when the reversing condition (most often ROC9
flipping sign) fires.

Two more data points from this run:
- **Direction asymmetry**: LONG win rate 39.2% vs SHORT 33.6% over this
  6-symbol, 40-trading-day sample. Not necessarily a general property of the
  strategy — plausibly reflects this specific window's regime — but worth
  re-checking on a longer sample.
- **Confirmation score barely mattered**: score-4 trades won 37.8% of the
  time vs 35.7% for score-3. ADX/Volume (the two conditions that can push a
  3 to a 4) did not meaningfully separate winners from losers in this sample.

None of this means the strategy is broken — profit factor was 0.94 (close to
breakeven) despite the low win rate, because `TAKE_PROFIT` trades are worth
roughly as much on average as `STOP` trades cost, and win rate alone doesn't
determine profitability at a 1:1 R:R. But a win rate this low means the
strategy has very little room for slippage, fees, or funding costs before
turning solidly negative — worth stress-testing before increasing leverage or
position size further.

## Reproducing

```bash
python scripts/portfolio_backtest.py --data-dir <dir-of-{SYMBOL}.csv> \
    --symbols BTC,ETH,SOL,XRP,XAU,XAG --out report.json
```

Each `{SYMBOL}.csv` needs `timestamp` (ms epoch), `open`, `high`, `low`,
`close`, `volume` columns, ascending time, one row per closed bar.
