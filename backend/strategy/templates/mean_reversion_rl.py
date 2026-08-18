"""均值回归 + RL 仓位管理。

ponytail: axon_quant 0.4.0 无 stable-baselines3 依赖,简化版:
         内嵌 mean_reversion 信号 + 固定 RL 仓位决策（state-based 查表）
         state = (signal: -1/0/1, vol: 0/1/2)
         PPO 决策查表：state -> (target_position, confidence)

生产用法: 训练好的 PPO 模型从 model_registry 加载, 替换 _policy_lookup 为 _policy_model.predict(state)
"""

from __future__ import annotations

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyContext

# 简化 PPO 策略查表（生产版: 从 stable-baselines3 加载）
# state_key = (signal, vol) -> (target_position, confidence)
_POLICY_TABLE: dict[tuple[int, int], tuple[float, float]] = {
    (0, 0): (0.0, 0.0),  # 无信号低波动 → 观望
    (0, 1): (0.0, 0.0),  # 无信号中波动 → 观望
    (0, 2): (0.0, 0.0),  # 无信号高波动 → 观望
    (1, 0): (0.5, 0.6),  # 买入信号低波动 → 轻仓
    (1, 1): (0.8, 0.8),  # 买入信号中波动 → 重仓
    (1, 2): (0.3, 0.5),  # 买入信号高波动 → 轻仓
    (-1, 0): (0.0, 0.5),  # 卖出信号低波动 → 减仓
    (-1, 1): (0.0, 0.8),  # 卖出信号中波动 → 清仓
    (-1, 2): (0.0, 0.9),  # 卖出信号高波动 → 清仓
}


class MeanReversionRL(BaseStrategy):
    """均值回归 + RL 仓位管理（state-based 查表简化版）。"""

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        bb_period = int(self.config.params.get("bb_period", 20))
        std_mult = float(self.config.params.get("std_mult", 2.0))
        model_id = self.config.name

        if len(ctx.closes) < bb_period:
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        recent = ctx.closes[-bb_period:]
        m = sum(recent) / bb_period
        var = sum((p - m) ** 2 for p in recent) / bb_period
        s = var**0.5
        upper = m + std_mult * s
        lower = m - std_mult * s
        close = bar["close"]

        # signal
        if close < lower:
            signal = 1  # 买入信号
        elif close > upper:
            signal = -1  # 卖出信号
        else:
            signal = 0

        # vol regime (0=low, 1=mid, 2=high) by s/m
        vol_ratio = s / m if m > 0 else 0.0
        if vol_ratio < 0.01:
            vol = 0
        elif vol_ratio < 0.03:
            vol = 1
        else:
            vol = 2

        # 查 PPO 策略
        position, confidence = _POLICY_TABLE.get((signal, vol), (0.0, 0.0))

        if position > 0 and signal == 1:
            return Action(
                action_type="buy",
                confidence=confidence,
                target_position=position,
                model_id=model_id,
                inference_time_us=0,
            )
        if position == 0 and signal == -1:
            return Action(
                action_type="sell",
                confidence=confidence,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        return Action(
            action_type="hold",
            confidence=confidence,
            target_position=0.0,
            model_id=model_id,
            inference_time_us=0,
        )
