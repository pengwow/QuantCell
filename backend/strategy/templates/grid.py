"""网格策略 — 等距挂单网格。

在 [lower, upper] 价格区间内,等距放 levels 档挂单
价格跌一档买一档,涨一档卖一档（反向做空回补）
震荡市表现好,趋势市反复被套

ponytail: 不真挂单, 仅在 on_bar 触发时按当前价所在档位模拟
         持仓状态用 _position_grid_idx 表示（-N..N，0 为中枢）
"""
from __future__ import annotations

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from axon_bridge import Action


class Grid(BaseStrategy):
    """等距网格策略。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._position_grid_idx: int = 0

    def on_start(self, ctx: StrategyContext) -> None:
        self._position_grid_idx = 0

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        lower = float(self.config.params.get("lower", 60000.0))
        upper = float(self.config.params.get("upper", 70000.0))
        levels = int(self.config.params.get("levels", 20))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name
        close = bar["close"]

        if upper <= lower or levels <= 0:
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        step = (upper - lower) / levels
        if step <= 0:
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        # 当前价在第几档
        idx = int((close - lower) / step)
        idx = max(0, min(levels, idx))

        # 价格相对中枢位置 → 转换为 target_position (-1..1)
        target = (idx - levels / 2) / (levels / 2) * limit
        # 取反：低吸高抛（价格低 → 加仓，价格高 → 减仓）
        target = -target

        # 跨档位变化 → 触发 action（首次仅初始化，不触发）
        if self._position_grid_idx == 0 and idx == levels // 2:
            self._position_grid_idx = idx
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)
        if idx < self._position_grid_idx:
            self._position_grid_idx = idx
            return Action(action_type="buy", confidence=0.5, target_position=target,
                          model_id=model_id, inference_time_us=0)
        if idx > self._position_grid_idx:
            self._position_grid_idx = idx
            return Action(action_type="sell", confidence=0.5, target_position=target,
                          model_id=model_id, inference_time_us=0)

        self._position_grid_idx = idx
        return Action(action_type="hold", confidence=0.0, target_position=0.0,
                      model_id=model_id, inference_time_us=0)
