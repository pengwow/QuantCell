"""双均线交叉策略 — 趋势跟随。

快线从下方穿越慢线时买入（金叉）
快线从上方穿越慢线时卖出（死叉）

ponytail: 用 ctx.closes 维护价格历史,首次穿越不立即下单（避免噪音）
         fast=10/slow=30 是 BTC 1h K 线的常用参数
"""
from __future__ import annotations

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from axon_bridge import Action


class DualMA(BaseStrategy):
    """双均线交叉策略。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._prev_fast_above_slow: bool | None = None
        self._current_position: float = 0.0

    def on_start(self, ctx: StrategyContext) -> None:
        self._prev_fast_above_slow = None
        self._current_position = 0.0

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        fast = int(self.config.params.get("fast", 10))
        slow = int(self.config.params.get("slow", 30))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < slow:
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        fast_ma = sum(ctx.closes[-fast:]) / fast
        slow_ma = sum(ctx.closes[-slow:]) / slow
        fast_above_slow = fast_ma > slow_ma

        # 首次计算仅记录状态
        if self._prev_fast_above_slow is None:
            self._prev_fast_above_slow = fast_above_slow
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        # 金叉 → 买入
        if not self._prev_fast_above_slow and fast_above_slow:
            self._prev_fast_above_slow = fast_above_slow
            self._current_position = limit
            return Action(action_type="buy", confidence=0.8, target_position=limit,
                          model_id=model_id, inference_time_us=0)

        # 死叉 → 卖出
        if self._prev_fast_above_slow and not fast_above_slow:
            self._prev_fast_above_slow = fast_above_slow
            self._current_position = 0.0
            return Action(action_type="sell", confidence=0.8, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        # 状态不变 → 维持当前仓位
        self._prev_fast_above_slow = fast_above_slow
        return Action(action_type="hold", confidence=0.5, target_position=self._current_position,
                      model_id=model_id, inference_time_us=0)
