"""均值回归策略 — 布林带 + RSI 反转。

价格跌破下轨 + RSI < 30 → 买入
价格突破上轨 + RSI > 70 → 卖出
震荡市表现好,趋势市反复接飞刀

ponytail: 用 close 历史计算布林带 (20, 2) + RSI (14)
         上轨 = mean + 2*std, 下轨 = mean - 2*std
         RSI 简化：gain/loss 平均
"""

from __future__ import annotations

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyContext


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _rsi(closes: list[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-diff)
    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class MeanReversion(BaseStrategy):
    """均值回归（布林带 + RSI 反转）。"""

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        bb_period = int(self.config.params.get("bb_period", 20))
        rsi_period = int(self.config.params.get("rsi_period", 14))
        rsi_oversold = float(self.config.params.get("rsi_oversold", 30))
        rsi_overbought = float(self.config.params.get("rsi_overbought", 70))
        std_mult = float(self.config.params.get("std_mult", 2.0))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < max(bb_period, rsi_period + 1):
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        recent = ctx.closes[-bb_period:]
        m, s = _mean(recent), _std(recent)
        upper = m + std_mult * s
        lower = m - std_mult * s
        close = bar["close"]
        rsi = _rsi(ctx.closes, rsi_period)

        # 价格破下轨 + RSI 超卖 → 买入反转
        if close < lower and rsi < rsi_oversold:
            return Action(
                action_type="buy",
                confidence=0.7,
                target_position=limit,
                model_id=model_id,
                inference_time_us=0,
            )
        # 价格破上轨 + RSI 超买 → 卖出反转
        if close > upper and rsi > rsi_overbought:
            return Action(
                action_type="sell",
                confidence=0.7,
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
