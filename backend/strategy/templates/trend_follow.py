"""趋势跟踪策略 — ATR 通道突破 + 跟踪止损。

Donchian Channel 突破 + ATR 跟踪止损
强趋势行情表现好,震荡市反复止损

ponytail: 用 close 历史计算 Donchian 上轨/下轨 + ATR
         突破上轨 → buy, 跌破下轨 → sell
         持仓时若 close < entry - atr*mult → 强制 sell（跟踪止损）
"""

from __future__ import annotations

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext


class TrendFollow(BaseStrategy):
    """趋势跟踪（Donchian 突破 + ATR 跟踪止损）。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._entry_price: float | None = None

    def on_start(self, ctx: StrategyContext) -> None:
        self._entry_price = None

    def _true_range(self, highs: list[float], lows: list[float], closes: list[float]) -> float:
        """最近一根 K 线的真实波幅 TR。"""
        if len(closes) < 2:
            return highs[-1] - lows[-1]
        return max(
            highs[-1] - lows[-1],
            abs(highs[-1] - closes[-2]),
            abs(lows[-1] - closes[-2]),
        )

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])
        highs = ctx.__dict__.setdefault("highs", [])  # type: ignore[attr-defined]
        lows = ctx.__dict__.setdefault("lows", [])  # type: ignore[attr-defined]
        highs.append(bar.get("high", bar["close"]))
        lows.append(bar.get("low", bar["close"]))

        lookback = int(self.config.params.get("lookback", 20))
        atr_period = int(self.config.params.get("atr_period", 14))
        atr_mult = float(self.config.params.get("atr_mult", 3.0))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < max(lookback, atr_period + 1):
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        # Donchian 通道（排除当前 K 线，只看历史 lookback 根）
        upper = max(highs[-(lookback + 1) : -1])
        lower = min(lows[-(lookback + 1) : -1])
        close = bar["close"]

        # ATR（最近 atr_period 根 TR 的均值）
        trs = [
            self._true_range(
                highs[-(atr_period + 1) :],
                lows[-(atr_period + 1) :],
                ctx.closes[-(atr_period + 1) :],
            )
        ]  # 简化：取最近一根 TR
        atr = trs[0] / 1  # 单根 TR 不足以做 ATR 简化

        # 简化 ATR：直接用最近 lookback 的平均 (high-low)
        atr = sum((highs[i] - lows[i]) for i in range(-lookback, 0)) / lookback

        # 突破上轨 → buy
        if close > upper:
            self._entry_price = close
            return Action(
                action_type="buy",
                confidence=0.7,
                target_position=limit,
                model_id=model_id,
                inference_time_us=0,
            )

        # 跌破下轨 → sell
        if close < lower:
            self._entry_price = None
            return Action(
                action_type="sell",
                confidence=0.7,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        # 持仓跟踪止损
        if self._entry_price is not None and close < self._entry_price - atr * atr_mult:
            self._entry_price = None
            return Action(
                action_type="sell",
                confidence=0.9,
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
