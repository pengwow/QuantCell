"""资金费率套利策略 — 现货+合约真双边套利 (2026-07-17 升级)。

ponytail:
- 升级前: 单边简化版, funding > 0 直接 sell (没现货对冲, 不是真套利)
- 升级后: 3 状态机 (FLAT / LONG_FUNDING / SHORT_FUNDING) + 持续时间计数器 (抗噪)
- funding 现金流: 2026-07-19 完全下沉到 axon_quant 引擎 (RunResult.total_funding_pnl),
  策略层不再调 ctx.settle_funding() (已 no-op, 保留以兼容旧代码)
- 现货腿传递: 策略 set ctx.spot_target_position, baseline 读
- 现货做空门控: spot_margin_enabled=False 时自动降级为单边
"""

from __future__ import annotations

from enum import Enum

from axon_bridge import Action
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext


class FundingState(Enum):
    """funding 套利状态机。"""

    FLAT = "flat"
    LONG_FUNDING = "long_funding"  # perp=short, spot=long
    SHORT_FUNDING = "short_funding"  # perp=long, spot=short (需 spot_margin)


class FundingArbitrage(BaseStrategy):
    """资金费率套利（真双边版）。"""

    # 默认参数
    _DEFAULTS = {
        "entry_threshold": 0.0003,
        "exit_threshold": 0.0001,
        "min_hold_bars": 8,
        "target_position_pct": 0.1,
        "spot_leg_enabled": True,
        "spot_margin_enabled": False,
        "log_state_transitions": True,
    }

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._state: FundingState = FundingState.FLAT
        self._hold_counter: int = 0
        self._current_side: str = "flat"  # 兼容老属性(供外部日志读)

    def _param(self, key: str):
        """读 params 字段, 缺省用 _DEFAULTS。"""
        if key in self.config.params:
            return self.config.params[key]
        return self._DEFAULTS[key]

    def on_start(self, ctx: StrategyContext) -> None:
        self._state = FundingState.FLAT
        self._hold_counter = 0
        self._current_side = "flat"

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        # 兼容未调 on_start 的场景（测试/单 bar 模式）
        if self._ctx is None:
            self._ctx = ctx
        funding_rate = float(bar.get("funding_rate", 0.0))

        # 状态机更新: 算 (perp_target, spot_target, new_state)
        # funding 现金流由 axon_quant 引擎通过 push_funding / with_funding_schedule
        # 计算并累加到 RunResult.total_funding_pnl, 策略层不再调 settle_funding
        prev_state = self._state
        perp_target, spot_target, new_state = self._compute_targets(funding_rate)

        if new_state != prev_state and self._param("log_state_transitions"):
            ctx.orders.append(
                {
                    "type": "log",
                    "msg": f"state: {prev_state.value} -> {new_state.value} (funding={funding_rate:.6f})",
                }
            )
        self._state = new_state
        self._current_side = {
            FundingState.FLAT: "flat",
            FundingState.LONG_FUNDING: "short",
            FundingState.SHORT_FUNDING: "long",
        }[new_state]

        # 3) 写 ctx.spot_target_position (baseline 读)
        ctx.spot_target_position = spot_target

        return Action(
            action_type=self._action_type_for(new_state),
            confidence=0.6,
            target_position=perp_target,
            model_id=self.config.name,
            inference_time_us=0,
        )

    def _compute_targets(self, funding: float) -> tuple[float, float, FundingState]:
        """状态机核心: 决定 (perp_ratio, spot_ratio, new_state)。

        返回 ratio 语义(占 equity 比例,如 -0.1 = 做空 10% equity)
        与 StrategyConfig.position_limit 默认值 0.1 一致,便于 baseline
        统一转换 qty = ratio * equity / close。
        """
        entry = float(self._param("entry_threshold"))
        exit_ = float(self._param("exit_threshold"))
        min_bars = int(self._param("min_hold_bars"))
        pct = float(self._param("target_position_pct"))
        spot_leg = bool(self._param("spot_leg_enabled"))
        spot_margin = bool(self._param("spot_margin_enabled"))

        # 已持仓状态的退场 / 维持
        if self._state == FundingState.LONG_FUNDING:
            # 强反转: funding 反号 + 持续 min_bars
            if funding <= -entry:
                self._hold_counter += 1
                if self._hold_counter >= min_bars:
                    return self._short_funding_targets(pct, spot_leg, spot_margin)
                return self._long_funding_targets(pct, spot_leg)  # 维持
            # 弱退场
            if funding < exit_:
                self._hold_counter = 0
                return 0.0, 0.0, FundingState.FLAT
            # 维持
            self._hold_counter = 0
            return self._long_funding_targets(pct, spot_leg)

        if self._state == FundingState.SHORT_FUNDING:
            if funding >= +entry:
                self._hold_counter += 1
                if self._hold_counter >= min_bars:
                    return self._long_funding_targets(pct, spot_leg)
                return self._short_funding_targets(pct, spot_leg, spot_margin)
            if funding > -exit_:
                self._hold_counter = 0
                return 0.0, 0.0, FundingState.FLAT
            self._hold_counter = 0
            return self._short_funding_targets(pct, spot_leg, spot_margin)

        # FLAT 状态入场
        if funding >= +entry:
            self._hold_counter += 1
            if self._hold_counter >= min_bars:
                return self._long_funding_targets(pct, spot_leg)
            return 0.0, 0.0, FundingState.FLAT
        if funding <= -entry:
            self._hold_counter += 1
            if self._hold_counter >= min_bars:
                return self._short_funding_targets(pct, spot_leg, spot_margin)
            return 0.0, 0.0, FundingState.FLAT
        # funding 接近 0: 重置计数器
        self._hold_counter = 0
        return 0.0, 0.0, FundingState.FLAT

    def _long_funding_targets(self, pct, spot_leg):
        # 返回 ratio: 做空 perp 收 funding (负 perp ratio)
        if spot_leg:
            return -pct, +pct, FundingState.LONG_FUNDING
        return -pct, 0.0, FundingState.LONG_FUNDING

    def _short_funding_targets(self, pct, spot_leg, spot_margin):
        # 返回 ratio: 做多 perp 付 funding (正 perp ratio)
        if spot_leg and spot_margin:
            return +pct, -pct, FundingState.SHORT_FUNDING
        # spot_margin=False: spot 降级为 0
        return +pct, 0.0, FundingState.SHORT_FUNDING

    def _action_type_for(self, state: FundingState) -> str:
        """Action.action_type 字符串（兼容 axon_quant 枚举）。"""
        return {
            FundingState.FLAT: "hold",
            FundingState.LONG_FUNDING: "sell",  # 做空 perp
            FundingState.SHORT_FUNDING: "buy",  # 做多 perp
        }[state]
