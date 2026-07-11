"""Telegram notifier and command handler for the trading bot."""
import asyncio
import logging
import time
from typing import Callable, Optional

import aiohttp

logger = logging.getLogger("telegram_notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
_BOT_START_TIME = time.time()


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str,
                 min_confidence: float = 0.5):
        self.token = token.strip()
        self.chat_id = str(chat_id).strip()
        self.min_confidence = min_confidence
        self._enabled = bool(token and chat_id)
        self._last_update_id = 0
        self._polling_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Wired by run_bot.py after construction
        self.bot: object = None          # TradingBot reference (legacy/non-adaptive)
        self.bots_dict: dict = {}        # symbol → AdaptiveTradingBot (adaptive mode)
        self.stop_bot_fn: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Polling control
    # ------------------------------------------------------------------

    def start_polling(self, loop: asyncio.AbstractEventLoop):
        if not self._enabled or self._polling_task:
            return
        self._loop = loop
        self._polling_task = loop.create_task(self._poll_loop())
        logger.info("Telegram polling started (chat_id=%s)", self.chat_id)

    def stop_polling(self):
        if self._polling_task:
            self._polling_task.cancel()

    # ------------------------------------------------------------------
    # Notification methods
    # ------------------------------------------------------------------

    def send(self, text: str):
        """Fire-and-forget send."""
        if not self._enabled:
            return
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._send(text), loop)
        else:
            try:
                cur = asyncio.get_event_loop()
                if cur.is_running():
                    cur.create_task(self._send(text))
                else:
                    cur.run_until_complete(self._send(text))
            except Exception:
                pass

    def send_photo(self, photo_path: str, caption: str = "",
                   parse_mode: str = "", delete_after: bool = True):
        """Fire-and-forget photo send (chart alerts). Falls back to a plain
        text message when the photo upload fails, so an alert is never lost
        to a rendering/upload problem. delete_after removes the temp PNG
        once the upload attempt finishes."""
        if not self._enabled:
            return
        coro = self._send_photo(photo_path, caption, parse_mode, delete_after)
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            try:
                cur = asyncio.get_event_loop()
                if cur.is_running():
                    cur.create_task(coro)
                else:
                    cur.run_until_complete(coro)
            except Exception:
                pass

    # Alias for backward compatibility
    def notify(self, text: str):
        self.send(text)

    def notify_buy(self, symbol: str, price: float, amount: float,
                   sl: float, tp: float, strategy: str):
        mode = "PAPER" if (self.bot and getattr(self.bot, "_paper", False)) else "LIVE"
        self.send(
            f"BUY {symbol} [{strategy}] {mode}\n"
            f"Price: {price:,.4f}  Amount: {amount:.6f}\n"
            f"SL: {sl:,.4f}  TP: {tp:,.4f}"
        )

    def notify_close(self, symbol: str, entry: float, exit_price: float,
                     pnl_pct: float, reason: str):
        sign = "+" if pnl_pct >= 0 else ""
        label = "Take-Profit" if reason == "take_profit" else "Stop-Loss"
        self.send(
            f"{label} hit: {symbol}\n"
            f"Entry: {entry:,.4f}  Exit: {exit_price:,.4f}\n"
            f"PnL: {sign}{pnl_pct:.2f}%"
        )

    def notify_error(self, symbol: str, error: str):
        self.send(f"Order error: {symbol}\n{str(error)[:200]}")

    # Keep older method names used by the old bot (no-op or map to new ones)
    def notify_signal(self, signal_dict: dict):
        sig_type = signal_dict.get("type", "hold")
        if sig_type == "hold":
            return
        conf = signal_dict.get("confidence") or 0
        if conf < self.min_confidence:
            return
        sym = signal_dict.get("symbol", "")
        strat = signal_dict.get("strategy", "")
        price = signal_dict.get("price", 0)
        reason = signal_dict.get("reason", "")
        meta = signal_dict.get("metadata", {})
        sl = meta.get("stop_loss")
        tp = meta.get("take_profit")
        arrow = "BUY" if sig_type == "buy" else "SELL"
        sl_tp = f"\nSL: {sl:,.4f}  TP: {tp:,.4f}" if sl and tp else ""
        self.send(
            f"{arrow} {sym} [{strat}]  conf={conf*100:.0f}%\n"
            f"@ {price:,.4f}  {reason}{sl_tp}"
        )

    def notify_order(self, symbol: str, side: str, amount: float,
                     price: float, strategy: str, paper: bool):
        mode = "PAPER" if paper else "LIVE"
        self.send(
            f"Order filled [{mode}] {side.upper()} {symbol}\n"
            f"Amount: {amount:.6f} @ {price:,.4f}  [{strategy}]"
        )

    def notify_trade_closed(self, symbol: str, reason: str, exit_price: float,
                            entry: float, sl, tp, stats: dict):
        won = reason == "take_profit"
        label = "Take-Profit" if won else "Stop-Loss"
        risk = abs(entry - sl) if sl else abs(entry - exit_price) or 1.0
        pnl_r = abs(exit_price - entry) / risk if won else -1.0
        sign = "+" if pnl_r >= 0 else ""
        wr = stats.get("win_rate", 0) or 0
        total = stats.get("trades", 0)
        self.send(
            f"{label} hit: {symbol}\n"
            f"Entry: {entry:,.4f}  Exit: {exit_price:,.4f}\n"
            f"Result: {sign}{pnl_r:.1f}R  |  WR: {wr:.1f}% ({total} trades)"
        )

    def notify_order_error(self, symbol: str, strategy: str, error: str):
        self.send(f"Order error [{strategy}]: {symbol}\n{str(error)[:200]}")

    def notify_bot_started(self, paper: bool, strategies: list, symbols: list):
        mode = "Paper" if paper else "Live"
        self.send(
            f"Bot started [{mode}]\n"
            f"Symbols: {', '.join(symbols)}\n"
            f"Strategies: {', '.join(strategies)}"
        )

    def notify_bot_stopped(self):
        self.send("Bot stopped.")

    def notify_drawdown_halt(self, balance: float, peak: float):
        dd = (peak - balance) / peak * 100 if peak else 0.0
        self.send(
            f"MAX DRAWDOWN REACHED - Trading halted\n"
            f"Balance: ${balance:,.2f} (peak ${peak:,.2f})\n"
            f"Drawdown: {dd:.1f}%"
        )

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    async def _cmd_stats(self):
        """Per-symbol adaptive bot stats + balance + open positions + totals."""
        bots = self.bots_dict
        if not bots:
            if self.bot:
                state = self.bot.get_state() if hasattr(self.bot, "get_state") else {}
                await self._send(
                    f"Bot Stats\n"
                    f"Balance: ${state.get('balance', 0):,.2f}\n"
                    f"PnL: ${state.get('pnl_total', 0):+,.2f}\n"
                    f"Positions: {len(state.get('positions', []))}"
                )
            else:
                await self._send("No bots connected.")
            return

        lines = ["📊 Adaptive Bot Stats\n"]
        total_pnl    = 0.0
        total_trades = 0
        total_wins   = 0
        total_losses = 0
        balance      = 0.0
        open_lines   = []

        for sym, (bot, _) in bots.items():
            try:
                st = bot.get_status()
                perf = bot.get_performance_summary() if hasattr(bot, "get_performance_summary") else {}
                n = st.get("total_trades", 0)
                wr = perf.get("win_rate", 0) * 100 if n > 0 else 0.0
                pnl = perf.get("net_pnl", 0.0)
                total_pnl    += pnl
                total_trades += n
                total_wins   += perf.get("wins", 0)
                total_losses += perf.get("losses", 0)
                balance = st.get("account_balance", balance)

                regime = st.get("market_state", "?")
                pos = "IN_POS" if st.get("position_open") else st.get("state", "?")
                warmup = st.get("warmup_remaining_m", 0)
                warmup_str = f" | WARMUP {warmup}m" if warmup > 0 else ""
                lines.append(
                    f"{sym}: {pos} | {regime} | "
                    f"{n}T {wr:.0f}%WR ${pnl:+.0f}{warmup_str}"
                )

                if st.get("position_open"):
                    t = getattr(bot, "current_trade", {}) or {}
                    direction = t.get("direction", "?")
                    entry     = t.get("entry", 0.0)
                    sl        = t.get("sl", 0.0)
                    tp1       = t.get("tp1", 0.0)
                    tp2       = t.get("tp2", 0.0)
                    open_lines.append(
                        f"{sym} {direction} entry={entry:,.4f} "
                        f"SL={sl:,.4f} TP1={tp1:,.4f} TP2={tp2:,.4f}"
                    )
            except Exception as e:
                lines.append(f"{sym}: error ({e})")

        lines.append(f"\n💰 Balance: ${balance:,.2f}")
        if open_lines:
            lines.append("\n📌 Open Positions:\n" + "\n".join(open_lines))
        else:
            lines.append("\n📌 No open positions")
        lines.append(
            f"\n📈 Total: {total_trades} trades | "
            f"{total_wins}W/{total_losses}L | Net PnL: ${total_pnl:+,.2f}"
        )
        await self._send("\n".join(lines))

    async def _cmd_log(self, n: int = 15):
        """Last N log lines from all adaptive bots."""
        bots = self.bots_dict
        if not bots:
            await self._send("No adaptive bots connected.")
            return

        all_lines = []
        for sym, (bot, _) in bots.items():
            try:
                st = bot.get_status()
                recent = st.get("recent_log", [])
                for entry in recent:
                    all_lines.append(f"[{sym.split('/')[0]}] {entry}")
            except Exception:
                pass

        if not all_lines:
            await self._send("No log entries yet.")
            return

        tail = all_lines[-n:]
        text = "Recent Log\n" + "\n".join(tail)
        # Telegram message limit ~4096 chars
        if len(text) > 3800:
            text = text[-3800:]
        await self._send(text)

    def send_periodic_status(self):
        """Fire-and-forget periodic status — call from run_bot every 5m."""
        if not self._enabled:
            return
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._cmd_stats(), loop)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _send(self, text: str) -> bool:
        url = TELEGRAM_API.format(token=self.token, method="sendMessage")
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status != 200:
                        body = await r.text()
                        logger.warning("Telegram send failed %s: %s", r.status, body[:200])
                        return False
                    return True
        except Exception as e:
            logger.warning("Telegram send error: %s", e)
            return False

    async def _send_photo(self, photo_path: str, caption: str,
                          parse_mode: str, delete_after: bool) -> bool:
        """Upload a photo via sendPhoto (multipart). Telegram caps captions
        at 1024 chars — truncate rather than fail. On any failure, fall back
        to sending the caption as a plain text message."""
        url = TELEGRAM_API.format(token=self.token, method="sendPhoto")
        ok = False
        try:
            with open(photo_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("chat_id", self.chat_id)
                form.add_field("photo", f, filename="chart.png",
                               content_type="image/png")
                if caption:
                    form.add_field("caption", caption[:1024])
                if parse_mode:
                    form.add_field("parse_mode", parse_mode)
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url, data=form, timeout=aiohttp.ClientTimeout(total=30)
                    ) as r:
                        if r.status != 200:
                            body = await r.text()
                            logger.warning("Telegram sendPhoto failed %s: %s",
                                           r.status, body[:200])
                        else:
                            ok = True
        except Exception as e:
            logger.warning("Telegram sendPhoto error: %s", e)
        finally:
            if delete_after:
                try:
                    import os as _os
                    _os.remove(photo_path)
                except OSError:
                    pass
        if not ok and caption:
            # Markdown entities in the caption may not be valid plain text —
            # send as-is (sendMessage without parse_mode renders raw text).
            await self._send(caption)
        return ok

    async def _get_updates(self) -> list:
        url = TELEGRAM_API.format(token=self.token, method="getUpdates")
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 20,
            "allowed_updates": ["message"],
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    if r.status != 200:
                        return []
                    data = await r.json()
                    return data.get("result", [])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Telegram getUpdates error: %s", e)
            return []

    async def _drain_old_updates(self):
        """Discard stale updates so old commands don't fire on restart."""
        url = TELEGRAM_API.format(token=self.token, method="getUpdates")
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    params = {
                        "offset": self._last_update_id + 1,
                        "timeout": 0,
                        "limit": 100,
                        "allowed_updates": ["message"],
                    }
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                    ) as r:
                        if r.status != 200:
                            break
                        data = await r.json()
                        updates = data.get("result", [])
                        if not updates:
                            break
                        self._last_update_id = max(u["update_id"] for u in updates)
        except Exception as e:
            logger.debug("Telegram drain error: %s", e)

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self):
        logger.info("Telegram command polling started")
        await self._drain_old_updates()
        while True:
            try:
                updates = await self._get_updates()
                for update in updates:
                    self._last_update_id = max(self._last_update_id, update["update_id"])
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip()
                    chat = str(msg.get("chat", {}).get("id", ""))
                    if chat != self.chat_id:
                        continue
                    # Ignore stale commands from before this process started
                    msg_time = msg.get("date", 0)
                    if msg_time < _BOT_START_TIME - 5:
                        continue
                    if text:
                        await self._handle_command(text)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Poll loop error: %s", e)
                await asyncio.sleep(5)

    async def _handle_command(self, text: str):
        parts = text.split()
        cmd = parts[0].lower().lstrip("/").split("@")[0]

        if cmd == "help":
            await self._send(
                "Trading Bot Commands\n\n"
                "/stats - per-symbol P&L, WR, regime, balance\n"
                "/log [N] - last N log lines (default 15)\n"
                "/status - running status, positions, balance\n"
                "/positions - open positions with PnL estimate\n"
                "/stop - stop the bot\n"
                "/help - show this message"
            )

        elif cmd in ("stats", "stat"):
            await self._cmd_stats()

        elif cmd == "log":
            n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15
            await self._cmd_log(n)

        elif cmd == "status":
            if not self.bot:
                await self._send("Bot not connected.")
                return
            state = self.bot.get_state()
            running = state.get("running", False)
            paper = state.get("paper", True)
            balance = state.get("balance", 0)
            pnl = state.get("pnl_total", 0)
            positions = len(state.get("positions", []))
            mode = "Paper" if paper else "Live"
            status = "Running" if running else "Stopped"
            sign = "+" if pnl >= 0 else ""
            await self._send(
                f"Bot Status\n"
                f"Status: {status} | {mode}\n"
                f"Balance: ${balance:,.2f}\n"
                f"PnL: {sign}${pnl:,.2f}\n"
                f"Open positions: {positions}"
            )

        elif cmd == "positions":
            if self.bots_dict:
                lines = ["📌 Open Positions\n"]
                found = False
                for sym, (bot, _) in self.bots_dict.items():
                    if not getattr(bot, "position_open", False):
                        continue
                    found = True
                    t = getattr(bot, "current_trade", {}) or {}
                    lines.append(
                        f"{sym} {t.get('direction', '?')} "
                        f"entry={t.get('entry', 0):,.4f} "
                        f"SL={t.get('sl', 0):,.4f} "
                        f"TP1={t.get('tp1', 0):,.4f} TP2={t.get('tp2', 0):,.4f}\n"
                        f"  realized_pnl={t.get('realized_pnl', 0):+,.2f}"
                    )
                if not found:
                    await self._send("No open positions.")
                    return
                await self._send("\n".join(lines))
                return

            if not self.bot:
                await self._send("Bot not connected.")
                return
            state = self.bot.get_state()
            positions = state.get("positions", [])
            if not positions:
                await self._send("No open positions.")
                return
            lines = ["Open Positions\n"]
            for p in positions:
                entry = p.get("entry", 0)
                sl = p.get("stop_loss")
                tp = p.get("take_profit")
                sl_str = f"{sl:,.4f}" if sl else "-"
                tp_str = f"{tp:,.4f}" if tp else "-"
                lines.append(
                    f"{p['symbol']} {p.get('side', 'long')} [{p.get('strategy', '')}]\n"
                    f"  Entry: {entry:,.4f}  SL: {sl_str}  TP: {tp_str}"
                )
            await self._send("\n".join(lines))

        elif cmd == "buy":
            if not self.bot:
                await self._send("Bot not connected.")
                return
            sym = parts[1].upper() if len(parts) > 1 else "BTC/USDT"
            if "/" not in sym:
                sym += "/USDT"
            await self._send(f"Sending manual BUY for {sym}...")
            try:
                result = await self.bot.manual_buy(sym)
                await self._send(result)
            except Exception as e:
                await self._send(f"Error: {e}")

        elif cmd == "stop":
            await self._send("Stopping bot...")
            if self.stop_bot_fn:
                self.stop_bot_fn()
            elif self.bot:
                asyncio.create_task(self.bot.stop())

        else:
            await self._send(f"Unknown command: {text}\nType /help for commands.")
