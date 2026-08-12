"""SMA 均线交叉策略 — 支持做多做空 + ATR 止损止盈 + 趋势过滤

规则：
- 趋势过滤：价格在 MA200 以上才做多，以下才做空
- 金叉（快线上穿慢线）→ 做多
- 死叉（快线下穿慢线）→ 做空
- 持仓期间用 ATR 动态止损止盈 + 移动止损

ponytail: ATR 计算用 TR 最大值,移动止损只上移不下移
"""
from __future__ import annotations

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from axon_bridge import Action


class SMACrossover(BaseStrategy):
    """SMA 均线交叉策略 — 支持做多做空"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._position: float = 0.0
        self._entry_price: float = 0.0
        self._stop_loss: float = 0.0
        self._take_profit: float = 0.0
        self._pending_action: str = ""

    def on_start(self, ctx: StrategyContext) -> None:
        self._position = 0.0
        self._entry_price = 0.0
        self._stop_loss = 0.0
        self._take_profit = 0.0
        self._pending_action = ""

    def _calc_atr(self, ctx: StrategyContext) -> float:
        atr_period = int(self.config.params.get("atr_period", 14))
        if len(ctx.highs) < atr_period + 1:
            return 0.0
        trs = []
        for i in range(-atr_period, 0):
            h = ctx.highs[i]
            l = ctx.lows[i]
            prev_c = ctx.closes[i - 1]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
        return sum(trs) / len(trs)

    def _trend_up(self, ctx: StrategyContext) -> bool:
        trend_ma = int(self.config.params.get("trend_ma", 200))
        if len(ctx.closes) < trend_ma:
            return True
        ma = sum(ctx.closes[-trend_ma:]) / trend_ma
        return ctx.closes[-1] > ma

    def _trend_down(self, ctx: StrategyContext) -> bool:
        trend_ma = int(self.config.params.get("trend_ma", 200))
        if len(ctx.closes) < trend_ma:
            return True
        ma = sum(ctx.closes[-trend_ma:]) / trend_ma
        return ctx.closes[-1] < ma

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        close = bar["close"]
        high = bar["high"]
        low = bar["low"]

        ctx.closes.append(close)
        ctx.highs.append(high)
        ctx.lows.append(low)

        fast = int(self.config.params.get("fast", 10))
        slow = int(self.config.params.get("slow", 30))
        atr_sl_mult = float(self.config.params.get("atr_sl_mult", 2.0))
        atr_tp_mult = float(self.config.params.get("atr_tp_mult", 3.0))
        limit = float(self.config.params.get("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < slow:
            return Action(action_type="hold", confidence=0.0, target_position=0.0,
                          model_id=model_id, inference_time_us=0)

        atr = self._calc_atr(ctx)

        # 上一根 bar 有反向开仓待执行
        if self._pending_action:
            act = self._pending_action
            self._pending_action = ""
            if act == "open_long":
                self._position = limit
                self._entry_price = close
                self._stop_loss = close - atr * atr_sl_mult if atr > 0 else close * 0.97
                self._take_profit = close + atr * atr_tp_mult if atr > 0 else close * 1.05
                return Action(action_type="buy", confidence=0.8, target_position=limit,
                              model_id=model_id, inference_time_us=0)
            elif act == "open_short":
                self._position = -limit
                self._entry_price = close
                self._stop_loss = close + atr * atr_sl_mult if atr > 0 else close * 1.03
                self._take_profit = close - atr * atr_tp_mult if atr > 0 else close * 0.95
                return Action(action_type="sell", confidence=0.8, target_position=limit,
                              model_id=model_id, inference_time_us=0)

        # 多头持仓：检查止损止盈
        if self._position > 0:
            if low <= self._stop_loss:
                self._position = 0.0
                return Action(action_type="sell", confidence=1.0, target_position=0.0,
                              model_id=f"{model_id}_sl", inference_time_us=0)
            if high >= self._take_profit:
                self._position = 0.0
                return Action(action_type="sell", confidence=1.0, target_position=0.0,
                              model_id=f"{model_id}_tp", inference_time_us=0)
            if atr > 0:
                new_sl = close - atr * atr_sl_mult
                if new_sl > self._stop_loss:
                    self._stop_loss = new_sl

        # 空头持仓：检查止损止盈
        if self._position < 0:
            if high >= self._stop_loss:
                self._position = 0.0
                return Action(action_type="buy", confidence=1.0, target_position=0.0,
                              model_id=f"{model_id}_sl", inference_time_us=0)
            if low <= self._take_profit:
                self._position = 0.0
                return Action(action_type="buy", confidence=1.0, target_position=0.0,
                              model_id=f"{model_id}_tp", inference_time_us=0)
            if atr > 0:
                new_sl = close + atr * atr_sl_mult
                if new_sl < self._stop_loss:
                    self._stop_loss = new_sl

        # 均线交叉信号
        fast_ma = sum(ctx.closes[-fast:]) / fast
        slow_ma = sum(ctx.closes[-slow:]) / slow

        # 金叉 → 做多
        if fast_ma > slow_ma and self._position <= 0 and self._trend_up(ctx):
            if self._position < 0:
                self._position = 0.0
                self._pending_action = "open_long"
                return Action(action_type="buy", confidence=0.9, target_position=limit,
                              model_id=f"{model_id}_close_short", inference_time_us=0)
            self._position = limit
            self._entry_price = close
            self._stop_loss = close - atr * atr_sl_mult if atr > 0 else close * 0.97
            self._take_profit = close + atr * atr_tp_mult if atr > 0 else close * 1.05
            return Action(action_type="buy", confidence=0.8, target_position=limit,
                          model_id=model_id, inference_time_us=0)

        # 死叉 → 做空
        if fast_ma < slow_ma and self._position >= 0 and self._trend_down(ctx):
            if self._position > 0:
                self._position = 0.0
                self._pending_action = "open_short"
                return Action(action_type="sell", confidence=0.9, target_position=limit,
                              model_id=f"{model_id}_close_long", inference_time_us=0)
            self._position = -limit
            self._entry_price = close
            self._stop_loss = close + atr * atr_sl_mult if atr > 0 else close * 1.03
            self._take_profit = close - atr * atr_tp_mult if atr > 0 else close * 0.95
            return Action(action_type="sell", confidence=0.8, target_position=limit,
                          model_id=model_id, inference_time_us=0)

        return Action(action_type="hold", confidence=0.0, target_position=0.0,
                      model_id=model_id, inference_time_us=0)
