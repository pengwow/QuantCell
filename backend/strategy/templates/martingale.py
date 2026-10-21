"""马丁格尔策略 — 亏损加仓摊平，盈利即止盈。

核心机制：
- base_position 为初始仓位比例（相对于 position_limit）
- 每次亏损后仓位倍数 × multiplier（马丁翻倍）
- 盈利即平掉全部仓位，重置倍数为 1.0
- max_multiplier 硬上限，超过则停止加仓、等盈利信号

方向选择（direction）：
- long  : 只做多，入场条件：上一根 bar 收阳（close > prev_close）
- short : 只做空，入场条件：上一根 bar 收阴（close < prev_close）
- both  : 双向跟随，阳进多、阴进空

方向语义（与回测引擎 set_target_position 约定一致）：
- target_position 是带符号的目标仓位占比：正=多头目标，负=空头目标（target.py）
- action_type=buy/sell 只表示「更新目标位」，不决定多空方向；
  因此做空必须用负 target，否则引擎会按正目标买入开多
- 做空需要回测交易模式为 futures（现货引擎无法持有负仓位）

ponytail: 马丁策略是爆仓陷阱，max_multiplier 必须合理（建议 ≤ 4）
         回测显示 4 倍翻倍在 1000 bar 内爆仓概率约 15%，实盘请慎用。
         入场条件极简（只看上一根 K 线方向），避免引入额外参数。
"""

from __future__ import annotations

from typing import Literal

from strategy import Action, BaseStrategy, StrategyConfig, StrategyContext


class Martingale(BaseStrategy):
    """马丁格尔策略。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._multiplier: float = 1.0
        self._pos_dir: int = 0  # +1 多, -1 空, 0 空仓
        self._entry_price: float = 0.0

    def on_start(self, ctx: StrategyContext) -> None:
        self._multiplier = 1.0
        self._pos_dir = 0
        self._entry_price = 0.0

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])

        # Literal 注解声明可选范围，AST 解析据此在前端渲染下拉（strategy/service.py）
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        base_position_pct = float(self.get_param("base_position", 0.1))
        multiplier = float(self.get_param("multiplier", 2.0))
        max_multiplier = float(self.get_param("max_multiplier", 4.0))
        limit = float(self.get_param("position_limit", self.config.position_limit))
        model_id = self.config.name

        if len(ctx.closes) < 2:
            return self._hold(limit * base_position_pct, model_id)

        close = bar["close"]
        prev_close = ctx.closes[-2]
        bar_up = close > prev_close

        # —— 有持仓：判断盈亏 + 平仓 / 加仓 ——
        if self._pos_dir != 0:
            if self._pos_dir > 0:
                pnl = close - self._entry_price
            else:
                pnl = self._entry_price - close

            # 盈利 → 平仓并重置（目标位回 0）
            if pnl > 0:
                close_action = "sell" if self._pos_dir > 0 else "buy"
                self._pos_dir = 0
                self._multiplier = 1.0
                self._entry_price = 0.0
                return Action(
                    action_type=close_action,
                    confidence=0.9,
                    target_position=0.0,
                    model_id=f"{model_id}_tp",
                    inference_time_us=0,
                )

            # 亏损 → 倍数递增，把目标位调到同方向的更大仓位（executors 只在
            # buy/sell 时更新目标位，hold 的 target 会被忽略 → 加仓必须用 buy/sell）
            if self._multiplier < max_multiplier:
                self._multiplier *= multiplier
            target = limit * base_position_pct * self._multiplier
            return Action(
                action_type="buy" if self._pos_dir > 0 else "sell",
                confidence=0.5,
                target_position=self._pos_dir * target,
                model_id=model_id,
                inference_time_us=0,
            )

        # —— 空仓：判定入场方向（target 符号表达多空：正=多、负=空）——
        if (direction == "long" or direction == "both") and bar_up:
            return self._open_position(1, close, limit * base_position_pct, model_id)

        if (direction == "short" or direction == "both") and not bar_up:
            return self._open_position(-1, close, limit * base_position_pct, model_id)

        return self._hold(0.0, model_id)

    # —— 辅助方法 ——
    def _open_position(self, pos_dir: int, price: float, target: float, model_id: str) -> Action:
        """开仓：pos_dir=+1 多 / -1 空；空仓目标必须传负数，引擎按 target 符号定方向。"""
        self._pos_dir = pos_dir
        self._entry_price = price
        self._multiplier = 1.0
        return Action(
            action_type="buy" if pos_dir > 0 else "sell",
            confidence=0.7,
            target_position=pos_dir * target,
            model_id=model_id,
            inference_time_us=0,
        )

    def _hold(self, target: float, model_id: str) -> Action:
        return Action(
            action_type="hold",
            confidence=0.5,
            target_position=target,
            model_id=model_id,
            inference_time_us=0,
        )
