"""RL Backtest Strategy — wraps an RL model as an axon_quant strategy for backtesting."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import numpy as np

from backtest.strategies.strategy_adapter import StrategyAdapter, StrategyConfig
from strategy.core import Bar, OrderSide

logger = logging.getLogger(__name__)


class RLBacktestStrategy(StrategyAdapter):
    """Run a trained RL model inside axon_quant's event-driven backtest engine.

    On each bar:
      1. Build observation from bar features + current position
      2. Call RLWorker.predict(observation)
      3. Execute buy/sell/hold via axon_quant order system
    """

    def __init__(self, config: StrategyConfig, model_path: str, trade_quantity: float = 0.01):
        super().__init__(config)
        from worker.rl_worker import RLWorker
        self._worker = RLWorker(model_path)
        self._trade_quantity = Decimal(str(trade_quantity))
        self._returns: list[float] = []
        self._last_close: float | None = None
        self._position_side: str = "flat"  # flat / long / short

    def _on_bar_impl(self, bar: Bar) -> None:
        close = float(bar.close)

        ret = 0.0
        if self._last_close is not None and self._last_close > 0:
            ret = (close - self._last_close) / self._last_close
        self._returns.append(ret)
        self._last_close = close

        vol = np.std(self._returns[-50:]) if len(self._returns) > 1 else 0.0
        pos = 0.0
        if self._position_side == "long":
            pos = 1.0
        elif self._position_side == "short":
            pos = -1.0

        obs = np.array([pos, ret, vol], dtype=np.float32)
        result = self._worker.predict(obs)
        side = result["side"]

        inst_id = bar.instrument_id

        if side == "buy" and self._position_side != "long":
            if self._position_side == "short":
                self.close_position(inst_id)
            self.buy(inst_id, self._trade_quantity)
            self._position_side = "long"
            logger.debug(f"[RL] BUY @ {close:.2f}, ret={ret:.4f}")

        elif side == "sell" and self._position_side != "short":
            if self._position_side == "long":
                self.close_position(inst_id)
            self.sell(inst_id, self._trade_quantity)
            self._position_side = "short"
            logger.debug(f"[RL] SELL @ {close:.2f}, ret={ret:.4f}")
