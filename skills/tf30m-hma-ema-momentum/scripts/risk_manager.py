"""Risk management: position sizing, stop-loss, and max drawdown guard."""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Position:
    symbol: str
    side: str          # 'long' | 'short'
    entry_price: float
    amount: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: int = field(default_factory=lambda: int(time.time()))

    @property
    def pnl_pct(self) -> float:
        return 0.0  # filled by bot at runtime


class RiskManager:
    """
    Controls maximum risk per trade, total drawdown, and position limits.
    All limits are configurable; sensible defaults apply.
    """

    def __init__(self,
                 max_risk_per_trade_pct: float = 0.02,   # 2% of balance per trade
                 stop_loss_pct: float = 0.03,            # 3% stop-loss
                 take_profit_pct: float = 0.06,          # 6% take-profit (2:1 RR)
                 max_open_positions: int = 5,
                 max_drawdown_pct: float = 0.15,         # halt if 15% drawdown
                 ):
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_open_positions = max_open_positions
        self.max_drawdown_pct = max_drawdown_pct
        self._positions: dict[str, Position] = {}
        self._peak_balance: float = 0.0
        self._halted: bool = False

    def update_peak(self, balance: float):
        if balance > self._peak_balance:
            self._peak_balance = balance

    def check_drawdown(self, current_balance: float) -> bool:
        """Returns True if within drawdown limit (trading allowed).

        Auto-resets the halt once balance recovers to within half the drawdown threshold,
        preventing the bot from staying halted indefinitely after a recovery.
        """
        if self._peak_balance <= 0 or current_balance <= 0:
            return True  # no meaningful data yet — allow trading
        drawdown = (self._peak_balance - current_balance) / self._peak_balance
        if drawdown >= self.max_drawdown_pct:
            self._halted = True
            return False
        if self._halted and drawdown < self.max_drawdown_pct * 0.5:
            self._halted = False  # balance recovered sufficiently
        return not self._halted

    def size_position(self, balance: float, price: float) -> float:
        """Calculate position size: spend risk_pct% of balance per trade."""
        if price <= 0:
            return 0
        risk_amount = balance * self.max_risk_per_trade_pct
        return round(risk_amount / price, 6)

    def compute_stops(self, side: str, entry_price: float) -> tuple[float, float]:
        """Returns (stop_loss_price, take_profit_price). Accepts 'buy'/'long' or 'sell'/'short'."""
        if side in ("buy", "long"):
            sl = entry_price * (1 - self.stop_loss_pct)
            tp = entry_price * (1 + self.take_profit_pct)
        else:
            sl = entry_price * (1 + self.stop_loss_pct)
            tp = entry_price * (1 - self.take_profit_pct)
        return round(sl, 6), round(tp, 6)

    def can_open(self, symbol: str, strategy: str = "") -> tuple[bool, str]:
        if self._halted:
            return False, "Trading halted: max drawdown reached"
        key = f"{symbol}||{strategy}"
        if key in self._positions:
            return False, f"{strategy} already has open position for {symbol}"
        sym_count = sum(1 for k in self._positions if k.startswith(f"{symbol}||"))
        if sym_count >= 2:
            return False, f"Max 2 positions per symbol for {symbol}"
        if len(self._positions) >= self.max_open_positions:
            return False, f"Max open positions ({self.max_open_positions}) reached"
        return True, "ok"

    def open_position(self, symbol: str, side: str, entry_price: float, amount: float,
                      strategy: str = "", stop_loss: float = None, take_profit: float = None) -> Position:
        if stop_loss is None or take_profit is None:
            sl_default, tp_default = self.compute_stops(side, entry_price)
            stop_loss  = stop_loss  or sl_default
            take_profit = take_profit or tp_default
        pos = Position(symbol=symbol, side=side, entry_price=entry_price, amount=amount,
                       stop_loss=stop_loss, take_profit=take_profit)
        self._positions[f"{symbol}||{strategy}"] = pos
        return pos

    def close_position(self, symbol: str, strategy: str = "") -> Optional[Position]:
        key = f"{symbol}||{strategy}"
        if key in self._positions:
            return self._positions.pop(key)
        # Fallback: close any position for symbol if no strategy given
        for k in list(self._positions):
            if k.startswith(f"{symbol}||"):
                return self._positions.pop(k)
        return None

    def check_stops(self, symbol: str, price: float, strategy: str = "") -> Optional[str]:
        """Returns 'stop_loss', 'take_profit', or None."""
        pos = self._positions.get(f"{symbol}||{strategy}")
        if not pos:
            return None
        if pos.side == "long":
            if pos.stop_loss and price <= pos.stop_loss:
                return "stop_loss"
            if pos.take_profit and price >= pos.take_profit:
                return "take_profit"
        else:
            if pos.stop_loss and price >= pos.stop_loss:
                return "stop_loss"
            if pos.take_profit and price <= pos.take_profit:
                return "take_profit"
        return None

    def get_positions(self) -> list[dict]:
        result = []
        for key, p in self._positions.items():
            strategy = key.split("||")[1] if "||" in key else ""
            result.append({
                "symbol": p.symbol,
                "strategy": strategy,
                "side": p.side,
                "entry": p.entry_price,
                "amount": p.amount,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
            })
        return result

    @property
    def is_halted(self) -> bool:
        return self._halted
