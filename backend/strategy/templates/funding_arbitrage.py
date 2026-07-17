"""资金费率套利策略 — 现货做多 + 合约做空吃 funding。

ponytail: axon_quant 0.4.0 无 funding rate API, 单标的简化版
         on_bar 接收 bar 含 'funding_rate' 字段（由 BacktestLoop 注入）
         funding_rate > min_funding → 做空（模拟合约空）+ 不做多
         funding_rate < -min_funding → 做多（模拟合约多）+ 不做空
         单边行为：仅产生 reduce_long/reduce_short 调整净仓位
"""
from __future__ import annotations

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from axon_bridge import Action


class FundingArbitrage(BaseStrategy):
    """资金费率套利（单标的简化版）。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._current_side: str = "flat"  # "long" | "short" | "flat"

    def on_start(self, ctx: StrategyContext) -> None:
        self._current_side = "flat"

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        min_funding = float(self.config.params.get("min_funding", 0.0001))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name
        funding_rate = float(bar.get("funding_rate", 0.0))

        # funding > 0（多头付空头）→ 做空吃费率
        if funding_rate > min_funding:
            self._current_side = "short"
            return Action(action_type="sell", confidence=0.6, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        # funding < 0（空头付多头）→ 做多吃费率
        if funding_rate < -min_funding:
            self._current_side = "long"
            return Action(action_type="buy", confidence=0.6, target_position=limit,
                          model_id=model_id, inference_time_us=0)

        # funding 接近 0 → 减仓
        if self._current_side != "flat":
            self._current_side = "flat"
            if self._current_side == "long":
                return Action(action_type="reduce_long", confidence=0.5, target_position=0.0,
                              model_id=model_id, inference_time_us=0)
            return Action(action_type="reduce_short", confidence=0.5, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        return Action(action_type="hold", confidence=0.0, target_position=0.0,
                      model_id=model_id, inference_time_us=0)
