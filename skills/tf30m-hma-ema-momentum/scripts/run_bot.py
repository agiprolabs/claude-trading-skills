#!/usr/bin/env python3
"""Live / paper trading bot for the TF30M HMA20-EMA Cross Momentum strategy.

Wires three pieces together:

    ccxt (OKX futures)  →  TF30MStateMachine  →  RiskManager  →  TelegramNotifier
      market data            entry/exit signals    sizing & guards   alerts + commands

The signal logic is the *same* `TF30MStateMachine` the backtester uses, so live
behaviour cannot drift from `run_backtest`. Exits combine the exchange-side ATR
stop/take-profit (1:1) with the bar-close direction-signal exit.

PAPER mode (default) is fully self-contained: it simulates fills against each
closed bar's high/low and tracks balance internally. LIVE mode places ccxt
market orders plus reduce-only stop/take-profit orders and reconciles fills
from `fetch_positions`. Test on PAPER (and your exchange testnet) before ever
setting PAPER=false.

Usage:
    # Paper trade the default watchlist (BTC/ETH/SOL/XRP/XAU/XAG), no keys needed:
    python run_bot.py

    # Replay a CSV bar-by-bar through the full pipeline (offline test):
    python run_bot.py --replay candles_30m.csv --symbol BTC/USDT:USDT

    # Live (requires OKX keys + explicit PAPER=false opt-in; everything else
    # -- symbols, timeframe, leverage, risk limits -- uses the defaults below):
    PAPER=false OKX_API_KEY=... OKX_API_SECRET=... OKX_API_PASSWORD=... \
        python run_bot.py

Configuration (environment variables) -- all optional, sensible defaults below:
    EXCHANGE_ID        ccxt exchange id           (default: okx)
    TIMEFRAME          ccxt bar size, e.g. 15m/30m/1h  (default: 30m)
    SYMBOLS            comma-separated symbols     (default: BTC/ETH/SOL/XRP/
                                                     XAU/XAG USDT perpetuals,
                                                     see DEFAULT_SYMBOLS below)
    PAPER              true/false                  (default: true -- stays true even
                                                     if OKX keys are set; flip
                                                     explicitly to go live)
    BALANCE            paper starting balance; ignored in LIVE mode, where
                       the real OKX account balance is fetched instead (default: 10000)
    LEVERAGE           futures leverage, scales position size (default: 20)
    MARGIN_FRACTION    fraction of balance used as margin/trade (default: 0.05)
    MARGIN_MODE        okx tdMode: cross|isolated  (default: cross)
    MAX_DRAWDOWN_PCT   halt trading at drawdown    (default: 0.15)
    POLL_SECONDS       new-bar check interval      (default: 20)
    MAX_OPEN_POSITIONS portfolio-wide position cap  (default: 2)
    OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSWORD   live credentials
    TELEGRAM_TOKEN / TELEGRAM_CHAT_ID                 optional alerts

Timeframe:
    Set TIMEFRAME to any ccxt-supported bar size (this strategy was designed
    for 30m; 15m is also supported). Indicator periods (HMA20, EMA5/9, ROC9,
    RSI14, ADX14, ATR14, Volume SMA20) are bar counts and are used unchanged
    on any timeframe -- on 15m they cover half the wall-clock lookback of 30m,
    so expect more (and noisier) signals. Run one timeframe per deployment;
    the state machine, RiskManager keys, and Telegram labels are all tagged
    with the configured TIMEFRAME so logs/positions stay unambiguous.

Leverage and position size:
    notional_per_trade = balance * MARGIN_FRACTION * LEVERAGE
    e.g. MARGIN_FRACTION=0.05, LEVERAGE=20 -> ~100% of balance notional per
    trade. Margin locked stays MARGIN_FRACTION*balance; leverage multiplies
    exposure (and therefore PnL swings) on top of that margin, same as a real
    leveraged futures position. Higher leverage does NOT change the ATR-based
    stop distance (still ATR14 x 1.5 in price terms) -- it changes how much of
    the account that same price move represents. Sizing higher than your
    liquidation buffer risks the exchange liquidating you before the bot's own
    stop-loss order fires (network/API lag, fast moves). Test thoroughly in
    PAPER mode at your intended LEVERAGE before going live.

Position limits (both enforced by RiskManager, independent of symbol count):
    - At most MAX_OPEN_POSITIONS positions open across the whole bot (default 2).
    - At most 1 open position per symbol at any time -- a symbol already in a
      LONG cannot also open a SHORT (or a second LONG). This matches the
      strategy's "Maximum Position: 1 Position per Symbol" rule.

Dependencies:
    uv pip install pandas numpy ccxt aiohttp

This is an analysis/automation tool, not financial advice. Trade at your own risk.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from risk_manager import RiskManager
from telegram_notifier import TelegramNotifier
from tf30m_hma_ema_strategy import (
    ATR_STOP_MULT,
    ATR_TP_MULT,
    Action,
    TF30MStateMachine,
    compute_indicators,
    _snapshot,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("tf30m_bot")

MIN_WARMUP_BARS = 60          # bars needed before indicators are usable
FETCH_LIMIT = 320             # history depth per poll (indicator warmup + margin)

# Default watchlist: BTC, ETH, SOL, XRP, and the gold/silver perpetuals
# (XAU/XAG) on OKX USDT-margined swaps. Override with SYMBOLS to change it.
DEFAULT_SYMBOLS = (
    "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,"
    "XRP/USDT:USDT,XAU/USDT:USDT,XAG/USDT:USDT"
)


def _timeframe_minutes(tf: str) -> float:
    """Parse a ccxt timeframe string ('15m', '30m', '1h', ...) to minutes.

    The strategy's indicator periods (HMA20, EMA5/9, ROC9, RSI14, ADX14,
    ATR14, Volume SMA20) are bar counts, not durations -- they apply unchanged
    to whatever timeframe is configured. Only the wall-clock warmup estimate
    shown in /stats needs to know the bar length.
    """
    unit = tf[-1]
    value = float(tf[:-1])
    return {"m": value, "h": value * 60, "d": value * 1440}[unit]


# ── Per-symbol trader ───────────────────────────────────────────────
@dataclass
class SymbolTrader:
    """Holds the state machine and bookkeeping for one symbol.

    Exposes the small surface the TelegramNotifier's /stats and /positions
    commands expect (get_status / get_performance_summary / current_trade /
    position_open).
    """
    symbol: str
    account_balance: float
    bar_minutes: float = 30.0
    sm: TF30MStateMachine = field(default_factory=TF30MStateMachine)
    last_closed_ts: int = 0
    position_open: bool = False
    current_trade: dict = field(default_factory=dict)
    trades: int = 0
    wins: int = 0
    losses: int = 0
    net_pnl: float = 0.0
    market_state: str = "live"
    _log: deque = field(default_factory=lambda: deque(maxlen=40))

    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._log.append(f"{stamp} {msg}")
        logger.info("[%s] %s", self.symbol, msg)

    # --- Telegram command surface ---
    def get_status(self) -> dict:
        warm = max(0, MIN_WARMUP_BARS - self._bars_seen) * self.bar_minutes
        return {
            "total_trades": self.trades,
            "market_state": self.market_state,
            "position_open": self.position_open,
            "state": self.sm.state.value,
            "warmup_remaining_m": warm,
            "account_balance": self.account_balance,
            "recent_log": list(self._log),
        }

    def get_performance_summary(self) -> dict:
        return {
            "win_rate": (self.wins / self.trades) if self.trades else 0.0,
            "net_pnl": self.net_pnl,
            "wins": self.wins,
            "losses": self.losses,
        }

    _bars_seen: int = 0


# ── Bot orchestrator ────────────────────────────────────────────────
class TF30MBot:
    def __init__(self) -> None:
        self.exchange_id = os.getenv("EXCHANGE_ID", "okx")
        self.timeframe = os.getenv("TIMEFRAME", "30m")
        self.bar_minutes = _timeframe_minutes(self.timeframe)
        # Bookkeeping tag for RiskManager position keys and Telegram labels --
        # reflects the configured timeframe so /stats and logs aren't
        # misleading when running 15m (indicator periods are unchanged; see
        # references/strategy_spec.md for the bar-count vs. duration distinction).
        self.strategy_tag = f"hma_ema_{self.timeframe}"
        self.symbols = [
            s.strip() for s in os.getenv("SYMBOLS", DEFAULT_SYMBOLS).split(",") if s.strip()
        ]
        # PAPER stays true by default even if OKX keys are present -- going
        # live requires explicitly setting PAPER=false, never inferred from
        # the presence of credentials.
        self.paper = os.getenv("PAPER", "true").lower() != "false"
        self.balance = float(os.getenv("BALANCE", "10000"))  # overwritten by
        # _sync_balance() from the real OKX account once PAPER=false.
        self.leverage = float(os.getenv("LEVERAGE", "20"))
        self.margin_fraction = float(os.getenv("MARGIN_FRACTION", "0.05"))
        self.margin_mode = os.getenv("MARGIN_MODE", "cross")
        self.poll_seconds = float(os.getenv("POLL_SECONDS", "20"))
        self.max_open_positions = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
        self.pnl_total = 0.0
        self.running = False

        self.risk = RiskManager(
            max_risk_per_trade_pct=self.margin_fraction,
            max_open_positions=self.max_open_positions,
            max_drawdown_pct=float(os.getenv("MAX_DRAWDOWN_PCT", "0.15")),
        )
        self.risk.update_peak(self.balance)
        self._halt_notified = False

        self.traders: dict[str, SymbolTrader] = {
            s: SymbolTrader(symbol=s, account_balance=self.balance, bar_minutes=self.bar_minutes)
            for s in self.symbols
        }
        self._stop_event = threading.Event()
        self.exchange = None                      # set in run() for live/paper feed

        # Telegram (optional).
        self.notifier = TelegramNotifier(
            token=os.getenv("TELEGRAM_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        )
        self.notifier.bot = self
        self.notifier.bots_dict = {s: (t, None) for s, t in self.traders.items()}
        self.notifier.stop_bot_fn = self.stop

    # --- facade used by TelegramNotifier /status /positions ---
    @property
    def _paper(self) -> bool:
        return self.paper

    def get_state(self) -> dict:
        positions = []
        for t in self.traders.values():
            if t.position_open:
                ct = t.current_trade
                positions.append({
                    "symbol": t.symbol,
                    "side": ct.get("direction", "").lower(),
                    "strategy": self.strategy_tag,
                    "entry": ct.get("entry", 0.0),
                    "stop_loss": ct.get("sl"),
                    "take_profit": ct.get("tp1"),
                })
        return {
            "running": self.running,
            "paper": self.paper,
            "balance": self.balance,
            "pnl_total": self.pnl_total,
            "positions": positions,
        }

    async def manual_buy(self, symbol: str) -> str:
        return ("Manual entries are disabled — TF30M is fully rule-driven "
                "(HMA gate + EMA cross + confirmation). Use /stats to watch setups.")

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()

    # ── Exchange helpers ────────────────────────────────────────────
    def _make_exchange(self):
        import ccxt  # lazy import so --replay works without ccxt installed
        klass = getattr(ccxt, self.exchange_id)
        cfg = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        key = os.getenv("OKX_API_KEY", "")
        secret = os.getenv("OKX_API_SECRET", "")
        password = os.getenv("OKX_API_PASSWORD", "")
        if not self.paper and key and secret:
            cfg["apiKey"] = key
            cfg["secret"] = secret
            if password:
                cfg["password"] = password
        ex = klass(cfg)
        ex.load_markets()
        return ex

    def _sync_balance(self) -> None:
        """Refresh self.balance from the real OKX account (LIVE mode only).

        PAPER mode is intentionally self-contained and never calls this --
        its balance is simulated locally starting from BALANCE. In LIVE mode,
        position sizing (margin_fraction * leverage) must be based on real
        account equity, not the BALANCE env var (which only seeds the paper
        simulator), so this is called once at startup and once per poll cycle.
        On a fetch error, the last known balance is kept and a warning logged
        -- sizing simply uses slightly stale data rather than crashing.
        """
        if self.paper:
            return
        try:
            bal = self.exchange.fetch_balance()
            usdt = bal.get("USDT", {}) if isinstance(bal, dict) else {}
            total = usdt.get("total")
            if total is None:
                total = (bal.get("total") or {}).get("USDT")
            if total is not None and float(total) > 0:
                self.balance = float(total)
                logger.info("Synced live balance from %s: $%.2f", self.exchange_id, self.balance)
            else:
                logger.warning(
                    "fetch_balance returned no positive USDT total; keeping balance=$%.2f",
                    self.balance,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Balance sync failed (%s); keeping last known balance=$%.2f",
                           e, self.balance)

    def _fetch_closed_df(self, symbol: str) -> pd.DataFrame:
        """Fetch OHLCV and drop the still-forming last candle."""
        raw = self.exchange.fetch_ohlcv(symbol, timeframe=self.timeframe, limit=FETCH_LIMIT)
        if len(raw) >= 2:
            raw = raw[:-1]  # exclude the in-progress bar
        return pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

    # ── Order execution ─────────────────────────────────────────────
    def _sl_tp(self, direction: str, entry: float, atr: float) -> tuple[float, float]:
        if direction == "LONG":
            return entry - atr * ATR_STOP_MULT, entry + atr * ATR_TP_MULT
        return entry + atr * ATR_STOP_MULT, entry - atr * ATR_TP_MULT

    def _open_live(self, symbol: str, direction: str, amount: float,
                   sl: float, tp: float) -> None:
        """Market entry + reduce-only SL/TP on the exchange (best-effort)."""
        side = "buy" if direction == "LONG" else "sell"
        close_side = "sell" if direction == "LONG" else "buy"
        base = {"tdMode": self.margin_mode}
        try:
            self.exchange.set_leverage(self.leverage, symbol,
                                       params={"mgnMode": self.margin_mode})
        except Exception as e:  # noqa: BLE001
            logger.debug("set_leverage skipped: %s", e)
        self.exchange.create_order(symbol, "market", side, amount, params=base)
        # Reduce-only protective orders. ccxt maps stopLossPrice/takeProfitPrice
        # to OKX algo orders; params may need tuning for your position mode.
        try:
            self.exchange.create_order(
                symbol, "market", close_side, amount,
                params={**base, "reduceOnly": True, "stopLossPrice": sl},
            )
            self.exchange.create_order(
                symbol, "market", close_side, amount,
                params={**base, "reduceOnly": True, "takeProfitPrice": tp},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("SL/TP order placement failed (%s); position UNPROTECTED", e)

    def _close_live(self, symbol: str, direction: str, amount: float) -> None:
        close_side = "sell" if direction == "LONG" else "buy"
        try:
            self.exchange.cancel_all_orders(symbol)
        except Exception as e:  # noqa: BLE001
            logger.debug("cancel_all_orders: %s", e)
        self.exchange.create_order(
            symbol, "market", close_side, amount,
            params={"tdMode": self.margin_mode, "reduceOnly": True},
        )

    # ── Trade lifecycle ─────────────────────────────────────────────
    def _enter(self, trader: SymbolTrader, direction: str, row: pd.Series) -> None:
        symbol = trader.symbol
        ok, why = self.risk.can_open(symbol, self.strategy_tag)
        if not ok:
            trader.log(f"entry blocked: {why}")
            trader.sm.on_position_closed()  # abandon setup, back to WAITING
            return

        entry = float(row["close"])
        atr = float(row["atr14"])
        sl, tp = self._sl_tp(direction, entry, atr)
        # RiskManager.size_position sizes an unlevered (1x) notional equal to
        # margin_fraction * balance. Leverage multiplies that into the actual
        # notional exposure -- the margin locked stays margin_fraction*balance,
        # but PnL swings (and the amount sent to the exchange) scale with
        # leverage, exactly like a real leveraged futures position.
        margin_amount = self.balance * self.margin_fraction
        notional = margin_amount * self.leverage
        amount = self.risk.size_position(self.balance, entry) * self.leverage
        if amount <= 0:
            trader.sm.on_position_closed()
            return

        if not self.paper:
            try:
                self._open_live(symbol, direction, amount, sl, tp)
            except Exception as e:  # noqa: BLE001
                trader.log(f"LIVE entry failed: {e}")
                self.notifier.notify_order_error(symbol, self.strategy_tag, str(e))
                trader.sm.on_position_closed()
                return

        self.risk.open_position(symbol, direction.lower(), entry, amount,
                                strategy=self.strategy_tag, stop_loss=sl, take_profit=tp)
        trader.position_open = True
        trader.current_trade = {
            "direction": direction, "entry": entry, "sl": sl,
            "tp1": tp, "tp2": tp, "amount": amount, "notional": notional,
            "opened_ts": int(row["timestamp"]), "realized_pnl": 0.0,
            "snapshot": _snapshot(direction, row, row.get("_score", 0), row.get("_comps", {})),
        }
        trader.log(f"ENTER {direction} @ {entry:.4f}  SL={sl:.4f} TP={tp:.4f} amt={amount:.6f}")
        self.notifier.notify_buy(symbol, entry, amount, sl, tp, self.strategy_tag)

    def _exit(self, trader: SymbolTrader, exit_price: float, reason: str) -> None:
        ct = trader.current_trade
        if not ct:
            return
        direction = ct["direction"]
        entry = ct["entry"]
        notional = ct.get("notional", self.balance * self.margin_fraction)
        amount = ct.get("amount", 0.0)

        if not self.paper and reason == "SIGNAL":
            # SL/TP fills close themselves on the exchange; only signal exits
            # need us to send a market close here.
            try:
                self._close_live(trader.symbol, direction, amount)
            except Exception as e:  # noqa: BLE001
                trader.log(f"LIVE close failed: {e}")
                self.notifier.notify_order_error(trader.symbol, self.strategy_tag, str(e))

        if direction == "LONG":
            pnl_pct = (exit_price - entry) / entry
        else:
            pnl_pct = (entry - exit_price) / entry
        pnl = notional * pnl_pct

        self.balance += pnl
        self.pnl_total += pnl
        trader.account_balance = self.balance
        trader.net_pnl += pnl
        trader.trades += 1
        if pnl > 0:
            trader.wins += 1
        else:
            trader.losses += 1

        self.risk.close_position(trader.symbol, self.strategy_tag)
        trader.position_open = False
        trader.log(f"EXIT {direction} @ {exit_price:.4f} [{reason}] pnl={pnl:+.2f} "
                   f"({pnl_pct:+.2%}) bal={self.balance:.2f}")
        stats = {"win_rate": (trader.wins / trader.trades * 100) if trader.trades else 0.0,
                 "trades": trader.trades}
        tp_reason = "take_profit" if reason == "TAKE_PROFIT" else (
            "stop_loss" if reason == "STOP" else reason.lower())
        self.notifier.notify_trade_closed(
            trader.symbol, tp_reason, exit_price, entry, ct.get("sl"), ct.get("tp1"), stats)
        trader.current_trade = {}
        self._update_drawdown()

    # ── Per-bar processing (shared by live loop and --replay) ────────
    def _paper_stop_tp(self, trader: SymbolTrader, row: pd.Series) -> Optional[tuple[float, str]]:
        ct = trader.current_trade
        if not ct:
            return None
        high, low, sl, tp = float(row["high"]), float(row["low"]), ct["sl"], ct["tp1"]
        if ct["direction"] == "LONG":
            if low <= sl:
                return sl, "STOP"
            if high >= tp:
                return tp, "TAKE_PROFIT"
        else:
            if high >= sl:
                return sl, "STOP"
            if low <= tp:
                return tp, "TAKE_PROFIT"
        return None

    def _reconcile_live_close(self, trader: SymbolTrader, row: pd.Series) -> bool:
        """Return True if the exchange shows the position gone (SL/TP filled)."""
        try:
            poss = self.exchange.fetch_positions([trader.symbol])
        except Exception as e:  # noqa: BLE001
            logger.debug("fetch_positions: %s", e)
            return False
        contracts = 0.0
        for p in poss:
            contracts += abs(float(p.get("contracts") or p.get("contractSize") or 0) or 0)
        if contracts > 0:
            return False
        # Position closed externally — infer reason from price vs TP.
        ct = trader.current_trade
        px = float(row["close"])
        tp = ct.get("tp1")
        if ct["direction"] == "LONG":
            reason = "TAKE_PROFIT" if tp and px >= tp else "STOP"
            exit_px = tp if reason == "TAKE_PROFIT" else ct.get("sl", px)
        else:
            reason = "TAKE_PROFIT" if tp and px <= tp else "STOP"
            exit_px = tp if reason == "TAKE_PROFIT" else ct.get("sl", px)
        try:
            self.exchange.cancel_all_orders(trader.symbol)
        except Exception:  # noqa: BLE001
            pass
        self._exit(trader, float(exit_px), reason)
        return True

    def process_bar(self, trader: SymbolTrader, ind: pd.DataFrame, i: int) -> None:
        row = ind.iloc[i]
        trader._bars_seen += 1
        if not TF30MStateMachine.is_warm(row):
            return

        # 1) SL/TP first (always live). On a fill, skip the rest of the bar.
        if trader.position_open:
            if self.paper:
                hit = self._paper_stop_tp(trader, row)
                if hit:
                    exit_px, reason = hit
                    self._exit(trader, exit_px, reason)
                    trader.sm.on_position_closed()
                    return
            else:
                if self._reconcile_live_close(trader, row):
                    trader.sm.on_position_closed()
                    return

        # 2) State machine drives exit / entry decisions.
        decision = trader.sm.step(row)
        if decision.action in (Action.EXIT_LONG, Action.EXIT_SHORT):
            self._exit(trader, float(row["close"]), decision.reason)
        elif decision.action in (Action.ENTER_LONG, Action.ENTER_SHORT):
            # Stash score/components so the entry snapshot records them.
            r = row.copy()
            r["_score"], r["_comps"] = decision.score, decision.components
            direction = "LONG" if decision.action == Action.ENTER_LONG else "SHORT"
            self._enter(trader, direction, r)

    def _update_drawdown(self) -> None:
        self.risk.update_peak(self.balance)
        allowed = self.risk.check_drawdown(self.balance)
        if not allowed and not self._halt_notified:
            self._halt_notified = True
            self.notifier.notify_drawdown_halt(self.balance, self.risk._peak_balance)
        elif allowed:
            self._halt_notified = False

    # ── Live loop ───────────────────────────────────────────────────
    def _poll_symbol(self, trader: SymbolTrader) -> None:
        df = self._fetch_closed_df(trader.symbol)
        if len(df) < MIN_WARMUP_BARS:
            return
        ind = compute_indicators(df)

        # First sighting: sync to latest closed bar without acting on history.
        if trader.last_closed_ts == 0:
            trader.last_closed_ts = int(df["timestamp"].iloc[-1])
            trader.log(f"synced to bar {trader.last_closed_ts} ({len(df)} bars warm)")
            return

        new_idx = [i for i in range(len(df))
                   if int(df["timestamp"].iloc[i]) > trader.last_closed_ts]
        for i in new_idx:
            if self.risk.is_halted and not trader.position_open:
                break
            self.process_bar(trader, ind, i)
            trader.last_closed_ts = int(df["timestamp"].iloc[i])

    def run(self) -> None:
        self.exchange = self._make_exchange()
        self._sync_balance()  # LIVE only; no-op in PAPER
        self.running = True

        # Telegram polling on a background asyncio loop.
        tg_loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, args=(tg_loop,), daemon=True).start()
        self.notifier.start_polling(tg_loop)
        self.notifier.notify_bot_started(self.paper, [self.strategy_tag], self.symbols)

        logger.info("TF30M bot started | %s | %s | symbols=%s | balance=$%.2f",
                    self.exchange_id, "PAPER" if self.paper else "LIVE",
                    self.symbols, self.balance)
        last_status = 0.0
        try:
            while not self._stop_event.is_set():
                self._sync_balance()  # LIVE only; keeps sizing on real equity
                for trader in self.traders.values():
                    try:
                        self._poll_symbol(trader)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[%s] poll error: %s", trader.symbol, e)
                # Periodic /stats push every 5 minutes.
                if time.time() - last_status > 300:
                    self.notifier.send_periodic_status()
                    last_status = time.time()
                self._stop_event.wait(self.poll_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.notifier.notify_bot_stopped()
            self.notifier.stop_polling()
            logger.info("TF30M bot stopped.")

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()


# ── Offline replay (no network) ─────────────────────────────────────
def replay(csv_path: str, symbol: str, balance: float) -> None:
    """Feed a CSV bar-by-bar through the full pipeline in PAPER mode."""
    os.environ.setdefault("PAPER", "true")
    os.environ["SYMBOLS"] = symbol
    os.environ["BALANCE"] = str(balance)
    bot = TF30MBot()
    trader = bot.traders[symbol]

    df = pd.read_csv(csv_path)
    df.columns = [c.lower() for c in df.columns]
    if "timestamp" not in df.columns:
        df["timestamp"] = range(len(df))
    ind = compute_indicators(df)
    for i in range(len(ind)):
        if bot.risk.is_halted and not trader.position_open:
            break
        bot.process_bar(trader, ind, i)

    perf = trader.get_performance_summary()
    print("=" * 56)
    print(f"Replay complete — {symbol}")
    print(f"Trades      : {trader.trades} ({trader.wins}W / {trader.losses}L)")
    print(f"Win rate    : {perf['win_rate']:.1%}")
    print(f"Net PnL     : {trader.net_pnl:+.2f}")
    print(f"Balance     : {balance:.2f} -> {bot.balance:.2f} "
          f"({(bot.balance / balance - 1) * 100:+.2f}%)")
    print(f"Halted      : {bot.risk.is_halted}")


def main() -> int:
    p = argparse.ArgumentParser(description="TF30M HMA-EMA live/paper trading bot")
    p.add_argument("--replay", help="CSV of 30m OHLCV to replay offline (PAPER)")
    p.add_argument("--symbol", default="BTC/USDT:USDT", help="Symbol for --replay")
    p.add_argument("--balance", type=float, default=10_000.0, help="Replay start balance")
    args = p.parse_args()

    if args.replay:
        replay(args.replay, args.symbol, args.balance)
        return 0

    TF30MBot().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
