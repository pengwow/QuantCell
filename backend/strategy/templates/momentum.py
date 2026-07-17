"""动量策略 — N 日收益率排序做多 Top 1。

ponytail: 单标的动量 = (close - close_n) / close_n
         强趋势市做多,震荡市不动
         多品种时按动量排序,这里用单标的简化版
"""
from __future__ import annotations

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from axon_bridge import Action


class Momentum(BaseStrategy):
    """单标的动量策略。"""

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        lookback = int(self.config.params.get("lookback", 20))
        threshold = float(self.config.params.get("threshold", 0.05))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < lookback + 1:
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        prev = ctx.closes[-(lookback + 1)]
        cur = bar["close"]
        ret = (cur - prev) / prev

        if ret > threshold:
            return Action(action_type="buy", confidence=min(0.9, ret * 5), target_position=limit,
                          model_id=model_id, inference_time_us=0)
        if ret < -threshold:
            return Action(action_type="sell", confidence=min(0.9, -ret * 5), target_position=0.0,
                          model_id=model_id, inference_time_us=0)
        return Action(action_type="hold", confidence=0.0, target_position=0.0,
                      model_id=model_id, inference_time_us=0)
