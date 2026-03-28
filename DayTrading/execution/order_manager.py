"""
order_manager.py — submits and manages orders via the Alpaca Trading API.

submit() calculates position size, places a limit entry order,
and immediately places a stop-loss bracket.
"""

import logging
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, cfg):
        self._cfg = cfg
        self.client = TradingClient(
            cfg.alpaca.api_key,
            cfg.alpaca.secret_key,
            paper=cfg.alpaca.paper,
        )

    def _account_equity(self) -> Optional[float]:
        try:
            return float(self.client.get_account().equity)
        except Exception as e:
            logger.error("Could not fetch account equity: %s", e)
            return None

    def _position_size(self, entry: float, stop: float, equity: float) -> float:
        """
        Risk-based position sizing.
        Risk per trade = equity * max_position_pct
        Shares = risk_amount / (entry - stop)
        """
        risk_amount = equity * self._cfg.risk.max_position_pct
        risk_per_share = abs(entry - stop)
        if risk_per_share == 0:
            return 0
        return round(risk_amount / risk_per_share, 2)

    def submit(self, signal: dict, db) -> Optional[int]:
        """
        Place a bracket order for the given signal.

        Returns the trade DB row ID, or None if submission failed.
        """
        ticker = signal["ticker"]
        direction = signal["direction"]
        close = signal["close"]

        # Determine entry, stop, and target prices
        if direction == "long":
            entry  = round(close * 1.001, 2)          # slight premium above current
            stop   = signal.get("breakout_bar_low") or round(close * 0.99, 2)
            risk   = entry - stop
            target = round(entry + (risk * self._cfg.risk.reward_risk_ratio), 2)
            side   = OrderSide.BUY
        else:
            entry  = round(close * 0.999, 2)
            stop   = signal.get("local_high") or round(close * 1.01, 2)
            risk   = stop - entry
            target = round(entry - (risk * self._cfg.risk.reward_risk_ratio), 2)
            side   = OrderSide.SELL

        if risk <= 0:
            logger.warning("%s: invalid risk calculation (entry=%.2f stop=%.2f)", ticker, entry, stop)
            return None

        equity = self._account_equity()
        if equity is None:
            return None

        qty = self._position_size(entry, stop, equity)
        if qty <= 0:
            logger.warning("%s: position size calculated as 0 — skip", ticker)
            return None

        logger.info(
            "Submitting %s %s | entry=%.2f stop=%.2f target=%.2f qty=%.2f strength=%s",
            direction.upper(), ticker, entry, stop, target, qty, signal.get("signal_strength"),
        )

        try:
            order = self.client.submit_order(
                LimitOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=entry,
                    order_class=OrderClass.BRACKET,
                    stop_loss={"stop_price": stop},
                    take_profit={"limit_price": target},
                )
            )
            logger.info("Order submitted: %s", order.id)
            trade_id = db.open_trade(ticker, direction, entry, stop, target, qty)
            return trade_id

        except Exception as e:
            logger.error("Order submission failed for %s: %s", ticker, e)
            return None

    def cancel_all_open(self):
        """Cancel all open day orders — called at end of trading session."""
        try:
            self.client.cancel_orders()
            logger.info("All open orders cancelled")
        except Exception as e:
            logger.error("Failed to cancel open orders: %s", e)
