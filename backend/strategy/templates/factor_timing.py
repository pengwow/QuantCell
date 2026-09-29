"""因子择时策略 — 指定因子值越过阈值时调仓。

因子值由回测框架按 K 线逐 bar 注入 ctx.features（需在回测配置 factor_names 中
选择该因子）。热身期/未选择因子时 ctx 无该特征，策略一律 hold，不产生交易。
"""

from __future__ import annotations

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyContext


class FactorTiming(BaseStrategy):
    """因子阈值择时：v >= buy_threshold 买入到目标仓位；v <= sell_threshold 清仓。"""

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])
        model_id = self.config.name
        factor_name = str(self.config.params.get("factor_name", ""))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))

        def _hold() -> Action:
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        # 无有效因子值（热身期/回测未选择因子）时不交易；
        # 不能用 get_feature(default=0.0)，0.0 可能恰好越过卖出阈值造成误卖
        if not factor_name or not ctx.has_feature(factor_name):
            return _hold()

        value = ctx.get_feature(factor_name)
        buy_threshold = float(self.config.params.get("buy_threshold", 0.0))
        sell_threshold = float(self.config.params.get("sell_threshold", 0.0))

        if value >= buy_threshold:
            return Action(
                action_type="buy",
                confidence=min(0.95, abs(value)),
                target_position=limit,
                model_id=model_id,
                inference_time_us=0,
            )
        if value <= sell_threshold:
            return Action(
                action_type="sell",
                confidence=min(0.95, abs(value)),
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )
        return _hold()
