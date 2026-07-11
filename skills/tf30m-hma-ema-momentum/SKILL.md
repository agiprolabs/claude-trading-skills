---
name: tf30m-hma-ema-momentum
description: 30-minute HMA20 gate + EMA5/EMA9 cross momentum strategy with a 4-part confirmation score (ROC, RSI, ADX, Volume), ATR stop/take-profit at 1:1 R:R, and direction-signal early exits. Includes a shared state-machine engine, a backtester, and a live/paper trading bot (ccxt/OKX futures + RiskManager + Telegram).
---

# TF30M HMA20-EMA Cross Momentum

A rules-based trend-momentum strategy for the 30-minute timeframe. It only
takes a trade when three independent filters agree: a **Direction Gate**
(HMA20) that decides whether longs or shorts are even allowed, an **Entry
Trigger** (EMA5 crossing EMA9) that marks the setup, and a **Confirmation
Score** (ROC, RSI, ADX, Volume) that must pass at least 3 of 4 within a
3-bar window. Exits are deliberately fast: a fixed ATR stop / take-profit
(1:1) plus a direction-signal early exit.

The design separates indicators by role. HMA, EMA, and ROC are *direction*
indicators used for both entry and exit. RSI is *momentum confirmation* for
entry only. ADX and Volume are *quality* filters for entry only — they never
close a position, because a falling ADX or thinning volume signals a pause,
not a reversal.

```
Entry = Direction Gate AND Entry Trigger AND (Confirmation Score >= 3/4)
Exit  = HMA reverse  OR  EMA reverse  OR  ROC reverse   (any one)
```

## When It Works / When It Fails

- **Works**: sustained 30m directional moves with participation — the gate
  aligns with an EMA cross and momentum/volume confirm.
- **Fails**: chop. Repeated EMA crosses near a flat HMA generate setups that
  the confirmation window rejects, or entries that the fast signal exit
  stops out. Expect a high share of small SIGNAL exits in ranging regimes.

Pair this with the `regime-detection` skill and only run it when the 30m
regime is trending.

---

## 1. Parameters

| Component | Setting |
|-----------|---------|
| Timeframe | 30 minutes (evaluate on bar close) |
| Direction Gate | HMA(20) |
| Entry Trigger | EMA(5) cross EMA(9) |
| Momentum | ROC(9) |
| Confirmation | RSI(14), ADX(14), Volume SMA(20) |
| Volatility | ATR(14) |
| Stop Loss | entry ∓ ATR(14) × 1.5 |
| Take Profit | entry ± ATR(14) × 1.5 (R:R 1:1) |
| Position margin | 5% of current balance |
| Max positions | 1 per symbol |

---

## 2. Direction Gate (HMA20)

The gate is checked on the bar where the EMA cross occurs, using that bar's
**open** relative to HMA20, plus an HMA-slope guard.

```python
long_gate  = open > hma20 and hma20 >= hma20_prev   # HMA not sloping down
short_gate = open < hma20 and hma20 <= hma20_prev   # HMA not sloping up
```

If the gate fails, no confirmation window opens — an EMA cross alone is not
enough.

## 3. Entry Trigger (EMA5 / EMA9)

A trigger fires when EMA5 crosses EMA9 **on the same bar the gate passes**.
That bar starts a 3-bar Confirmation Window. Throughout the window EMA5 must
stay on the correct side of EMA9 and each bar's open must stay on the correct
side of HMA20.

## 4. Confirmation Score (3 of 4)

Each condition is worth 1 point. Need **≥ 3**.

| # | Condition | Long | Short |
|---|-----------|------|-------|
| 1 | ROC momentum | `roc9 > 0` | `roc9 < 0` |
| 2 | RSI direction | `rsi14 > 50` | `rsi14 < 50` |
| 3 | Trend strength | `adx14 >= 18 and adx14 > adx14_prev` | same |
| 4 | Volume | `volume >= volume_sma20` | same |

The score is evaluated each bar of the window. The trade opens on the first
bar that reaches 3/4 (entry price = that bar's close). If the window closes
(bar 3) still below 3, or any structural condition breaks, the setup fails
and the system waits for a **fresh** EMA cross under a passing gate.

## 5. Entry, Stop, Target

```python
entry_price = close                      # of the confirming bar
sl_distance = atr14 * 1.5
long_sl,  long_tp  = entry - sl_distance, entry + sl_distance
short_sl, short_tp = entry + sl_distance, entry - sl_distance
margin = balance * 0.05
```

An **Entry Snapshot** (direction, price, ATR, every indicator value, the
score, and which components passed) is stored for journaling and backtest
analysis. The snapshot is *record-only* — it does not create an exit rule
that all entry indicators must flip.

## 6. Exits

The exchange SL/TP is always live. On each bar close, if neither was hit, a
**direction-signal early exit** is evaluated:

```python
long_exit  = close < hma20 or ema_cross_down or roc9 < 0
short_exit = close > hma20 or ema_cross_up   or roc9 > 0
```

Any single condition closes 100% at market. ADX, Volume, and RSI are **never**
standalone exits in this version. Priority order: emergency risk → SL → TP →
signal exit → monitoring. If SL/TP already executed, no duplicate signal exit
is sent.

**No immediate reversal**: closing a long on a reverse signal cannot open a
short on the same bar (and vice-versa). The system returns to WAITING and
requires a new cross under a fresh gate.

---

## State Machine

```
WAITING
  → gate passes AND EMA cross           → LONG/SHORT_CONFIRMATION (bar 1..3)
  → score >= 3 within window            → LONG/SHORT_POSITION
  → SL / TP / signal exit               → RESET → WAITING
```

Bar-processing order (exactly as implemented in the engine): manage open
position first (intrabar SL/TP, then bar-close signal exit) → if a position
exists or a reversal was just blocked, stop → else start a new setup or
advance the active confirmation window.

See `references/strategy_spec.md` for the complete rule set, failure
conditions, and annotated pseudocode.

The signal state machine lives in one place — `TF30MStateMachine` — and both
the backtester and the live bot drive it, so live behaviour cannot diverge
from backtest behaviour.

---

## Live / Paper Trading Bot

`scripts/run_bot.py` runs the strategy against a live exchange feed:

```
ccxt (OKX futures) → TF30MStateMachine → RiskManager → TelegramNotifier
   market data          entry/exit          sizing & guards    alerts + commands
```

- **Data/execution**: ccxt, default exchange `okx`, USDT perpetuals
  (`BTC/USDT:USDT`) — supports both **long and short**.
- **Risk**: `RiskManager` sizes the margin (`MARGIN_FRACTION` × balance,
  default 5%); `run_bot.py` then scales that into the actual traded notional
  by `LEVERAGE` (`notional = balance × MARGIN_FRACTION × LEVERAGE`), same as a
  real leveraged futures position — margin locked stays 5% of balance, but
  exposure and PnL swings scale with leverage. A
  **portfolio-wide cap of `MAX_OPEN_POSITIONS` (default 2)**, a hard
  **1-position-per-symbol limit** (a symbol already holding a LONG cannot also
  open a SHORT, or a second LONG — enforced in `RiskManager.can_open`
  regardless of symbol count), and a max-drawdown halt (default 15%, with
  auto-recovery) round out the guardrails. ATR(14)×1.5 stop/take-profit (1:1)
  are passed explicitly, overriding the module's percentage defaults so the
  bot matches the TF30M spec.
- **Alerts/commands**: `TelegramNotifier` sends entry/exit/halt alerts and
  serves `/stats`, `/status`, `/positions`, `/log`, `/stop`.
- **PAPER by default** — fills are simulated against each closed bar's
  high/low and balance is tracked internally. Set `PAPER=false` (plus OKX
  keys) only after testing.

⚠️ **LEVERAGE scales real risk, not just margin efficiency.** With
`MARGIN_FRACTION=0.05` and `LEVERAGE=20`, each trade's notional is ~100% of
balance — the ATR(14)×1.5 stop distance in price terms doesn't change, but
the same price move now represents 20× more of your account. High leverage
also adds **liquidation risk**: if price gaps past your maintenance margin
before the bot's own stop-loss order fires (API lag, fast moves, exchange
downtime), the exchange can liquidate the position at a worse price than the
strategy's intended SL. Paper-test at your target leverage first, and confirm
OKX's maintenance margin requirement at that leverage leaves headroom beyond
the ATR stop distance.

⚠️ **LIVE mode places real orders.** Verify order placement on OKX (position
mode, margin mode, contract size) on a small size or testnet first — the
reduce-only SL/TP params may need tuning for your account configuration.

```bash
uv pip install pandas numpy ccxt aiohttp

# Paper trade OKX BTC + ETH perpetuals (no keys required):
SYMBOLS="BTC/USDT:USDT,ETH/USDT:USDT" python scripts/run_bot.py

# Offline: replay a CSV bar-by-bar through the full bot pipeline:
python scripts/run_bot.py --replay candles_30m.csv --symbol BTC/USDT:USDT

# Live (real orders — requires keys + explicit opt-in):
PAPER=false OKX_API_KEY=... OKX_API_SECRET=... OKX_API_PASSWORD=... \
    SYMBOLS="BTC/USDT:USDT" python scripts/run_bot.py
```

Key environment variables (see the header of `run_bot.py` for the full list):
`EXCHANGE_ID`, `SYMBOLS`, `PAPER`, `BALANCE`, `LEVERAGE`, `MARGIN_FRACTION`,
`MARGIN_MODE`, `MAX_OPEN_POSITIONS` (default 2), `MAX_DRAWDOWN_PCT`,
`POLL_SECONDS`, `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_API_PASSWORD`,
`TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID`. `.env.example` in this skill's root
lists every variable with the recommended starting values.

### Deploying on Railway

The skill folder is ready to deploy as a Railway worker service (no HTTP port
needed — it's a background loop, not a web server):

1. **New Project → Deploy from GitHub repo**, pick this repo.
2. In the service's **Settings → Root Directory**, set it to
   `skills/tf30m-hma-ema-momentum`. Railway (Nixpacks) then finds
   `requirements.txt` there and installs it automatically.
3. **Settings → Deploy**: the start command comes from `railway.json`
   (`python scripts/run_bot.py`) — no need to set it manually. `Procfile` is
   included too as a fallback if you switch builders.
4. **Variables tab**: copy every key from `.env.example` and set your values
   (`SYMBOLS`, `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID`, and OKX keys once you're
   ready for `PAPER=false`). Leave `PAPER=true` for the first deploy.
5. Deploy, then watch the **Deployments → Logs** tab — you should see
   `TF30M bot started | okx | PAPER | symbols=[...]` and, a bar or two later,
   `synced to bar ...`.
6. If Telegram is configured, `/stats` and `/status` work immediately;
   `restartPolicyType: ON_FAILURE` in `railway.json` restarts the worker if it
   crashes (e.g. a transient exchange API error).

`MAX_OPEN_POSITIONS=2` and the 1-per-symbol rule are the safety rails to keep
in place before flipping to live trading — increase `MAX_OPEN_POSITIONS`
only once you're comfortable with the drawdown behavior in paper mode.

---

## Files

### Scripts
- `scripts/tf30m_hma_ema_strategy.py` — indicators (HMA, EMA, ROC, RSI, ADX,
  ATR, volume SMA), `TF30MStateMachine` (pure signal logic), the
  `StrategyEngine` backtester, and a CLI. Run `--demo` for synthetic data or
  `--csv` for your own 30m OHLCV.
- `scripts/run_bot.py` — live/paper bot: ccxt (OKX futures) data + execution,
  wired to `RiskManager` and `TelegramNotifier`. `--replay` runs the whole
  pipeline offline against a CSV.
- `scripts/risk_manager.py` — position sizing, SL/TP, position limits, and the
  drawdown-halt guard.
- `scripts/telegram_notifier.py` — Telegram alerts and command handler.

### Deployment
- `requirements.txt` — pinned deps for Railway/Nixpacks (root of this skill).
- `Procfile` — `worker: python scripts/run_bot.py`.
- `railway.json` — Nixpacks build + start command + restart policy.
- `.env.example` — every environment variable with recommended defaults.

### References
- `references/strategy_spec.md` — full specification: gates, triggers,
  confirmation scoring, entry/exit logic, setup-failure rules, indicator
  classification, entry snapshot, and state-machine pseudocode.

---

## Quick Start

```bash
uv pip install pandas numpy          # backtester only
uv pip install pandas numpy ccxt aiohttp   # + live/paper bot

# Synthetic demo (mechanics + summary stats)
python scripts/tf30m_hma_ema_strategy.py --demo

# Your own 30m candles: CSV with open,high,low,close,volume (ascending time)
python scripts/tf30m_hma_ema_strategy.py --csv candles_30m.csv --balance 10000

# Paper-trade live on OKX (no keys needed)
SYMBOLS="BTC/USDT:USDT" python scripts/run_bot.py
```

Programmatic use:

```python
from tf30m_hma_ema_strategy import run_backtest, summarize
engine, indicators = run_backtest(df, balance=10_000)
print(summarize(engine, 10_000))
for trade in engine.trades:
    print(trade.direction, trade.reason, trade.pnl_pct, trade.snapshot)
```

## Integration with Other Skills

| Skill | Integration |
|-------|------------|
| `pandas-ta` / `ta-lib` | Alternative indicator implementations |
| `regime-detection` | Filter: only run in trending 30m regimes |
| `atr` via `custom-indicators` | Volatility inputs for stop sizing |
| `position-sizing` | Replace the flat 5% margin with vol-adjusted sizing |
| `risk-management` | Portfolio guardrails around per-symbol trades |
| `vectorbt` / `backtrader` | Larger-scale parameter sweeps and analytics |
| `trade-journal` | Persist the Entry Snapshot per trade |

*This skill provides analytical tools and information only. It does not
constitute financial advice or trading recommendations.*
