"""截面多因子策略 — 多品种动量 + 价值 + 波动率打分排序。

ponytail: axon_quant 0.4.0 单标的 BacktestEngine,简化版：
         on_bar 接收 bar 含 'cross_sectional' 字段, dict[symbol] -> 因子字典
         每个因子 [-1, 1] 标准化后加权
         top1 品种 → buy (假定策略被多 symbol 调度时,仅对 top1 出 Action)
         单 symbol 调度时: 退化为单 symbol 动量

实际生产用法: BacktestLoop 对 N 个 symbol 调度,每个 symbol 独立喂 bar
本模板假设 BacktestLoop 会把 cross_sectional 排名结果注入 bar
"""

from __future__ import annotations

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyContext


class CrossSectional(BaseStrategy):
    """截面多因子（动量 + 反转 + 波动率）简化版。"""

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        lookback = int(self.config.params.get("lookback", 20))
        top_k = int(self.config.params.get("top_k", 1))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < lookback + 1:
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        # 1. 动量因子 = (close - close_n) / close_n
        momentum = (bar["close"] - ctx.closes[-(lookback + 1)]) / ctx.closes[-(lookback + 1)]

        # 2. 反转因子 = -momentum（动量极强时反向看跌反转）
        reversal = -momentum * 0.3

        # 3. 波动率因子 = 倒数（低波动率高分）
        recent = ctx.closes[-lookback:]
        mean = sum(recent) / lookback
        variance = sum((p - mean) ** 2 for p in recent) / lookback
        vol = variance**0.5
        vol_factor = 1.0 / (1.0 + vol / mean) if mean > 0 else 0.0

        # 综合分数
        score = 0.5 * momentum + 0.2 * reversal + 0.3 * vol_factor

        # 排名: cross_sectional 字段是 BacktestLoop 注入的排名（1=top, 0=其他）
        # 简化:score > 阈值 + 排名 top_k 视为可买
        rank = int(bar.get("cross_sectional_rank", 0))
        threshold = float(self.config.params.get("threshold", 0.05))

        if rank > 0 and rank <= top_k and score > threshold:
            return Action(
                action_type="buy",
                confidence=min(0.9, score),
                target_position=limit,
                model_id=model_id,
                inference_time_us=0,
            )

        if score < -threshold:
            return Action(
                action_type="sell",
                confidence=min(0.9, -score),
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        return Action(
            action_type="hold",
            confidence=0.0,
            target_position=0.0,
            model_id=model_id,
            inference_time_us=0,
        )
