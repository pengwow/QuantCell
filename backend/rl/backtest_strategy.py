# -*- coding: utf-8 -*-
"""RL Backtest Strategy — 将 RL 模型包装为 axon_quant 策略用于回测"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from axon_bridge import Action
from backtest.backtest_loop import RuleStrategy

logger = logging.getLogger(__name__)


class RLBacktestStrategy(RuleStrategy):
    """在 axon_quant 事件驱动回测引擎中运行训练好的 RL 模型

    每根 bar:
      1. 从 bar 特征 + 当前持仓构建观测
      2. 调用 RL 模型预测
      3. 返回 Action (Buy/Sell/Hold)
    """

    def __init__(self, model_path: str, trade_quantity: float = 0.01):
        from stable_baselines3 import PPO

        self._model = PPO.load(model_path)
        self._trade_quantity = trade_quantity
        self._returns: list[float] = []
        self._last_close: float | None = None
        self._position_side: str = "flat"

    def on_bar(self, bar: dict) -> Action:
        close = bar["close"]

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
        action_logits, _ = self._model.predict(obs, deterministic=True)

        action_type = "hold"
        confidence = 0.5
        target = 0.0

        if action_logits == 0 and self._position_side != "long":
            action_type = "buy"
            confidence = 0.8
            target = self._trade_quantity
            self._position_side = "long"
        elif action_logits == 1 and self._position_side != "short":
            action_type = "sell"
            confidence = 0.8
            target = self._trade_quantity
            self._position_side = "short"

        return Action(
            action_type=action_type,
            confidence=confidence,
            target_position=target,
            model_id="rl_ppo",
            inference_time_us=0,
        )
