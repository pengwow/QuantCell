"""网格策略 — 等距挂单网格（计划型，2026-11 语义改造，spec §3.1）。

在 [lower, upper] 价格区间内等距放 levels+1 条档位线，
价格跌一档买一档,涨一档卖一档（低吸高抛）
震荡市表现好,趋势市反复被套

2026-11 语义变更（非兼容）：
- 首根 bar close 固化整套价格计划到 self._plan（公式唯一权威 =
  strategy.price_plan.grid_plan），此后 bar-by-bar 只做穿档触发，
  启动后改参数不影响运行中 worker；
- 旧自适应区间扩展（upper/lower 镜像 close*1.05/0.95）移除：
  自适应使价格计划启动后漂移，与「预览=实盘同源」矛盾；
  出界一律 hold，区间外挂单的空转风险由 plan warnings 预警。

ponytail: 不真挂单, 仅在 on_bar 触发时按当前价所在档位模拟
         持仓状态用 _position_grid_idx 表示（0..levels，档位线序号）
"""

from __future__ import annotations

from bisect import bisect_right

from strategy import Action, BaseStrategy, StrategyConfig, StrategyContext
from strategy.price_plan import grid_plan


class Grid(BaseStrategy):
    """等距网格策略（计划型执行）。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._position_grid_idx: int = 0
        self._plan = None  # PricePlan，首根 bar 才固化
        self._prices: list[float] = []  # 固化计划的等距档位线价格（levels+1 条）

    @classmethod
    def price_plan(cls, params: dict, ref_price: float):
        # 公式权威在 strategy.price_plan，这里只转发；固化与预览共用同一实现
        return grid_plan(params, ref_price)

    def _fused_params(self) -> dict:
        # 与旧 on_bar 读参口径一致：params 显式 None 视同缺省
        # （lower/upper/levels → 60000/70000/20，position_limit → config 顶层字段）
        params = dict(self.config.params)
        defaults = {
            "lower": 60000.0,
            "upper": 70000.0,
            "levels": 20,
            "position_limit": self.config.position_limit,
        }
        for key, default in defaults.items():
            if params.get(key) is None:
                params[key] = default
        return params

    def on_start(self, ctx: StrategyContext | None = None) -> None:
        self._position_grid_idx = 0
        # 首根 bar close 固化（worker 启动链路与 preview 同传最新收盘，口径一致）
        self._plan = None
        self._prices = []

    def _idx_of(self, close: float) -> int:
        # 当前价落在第几条档位线：等距线下二分等价于旧 int((close-lower)/step) 截断
        idx = bisect_right(self._prices, close) - 1
        return max(0, min(len(self._prices) - 1, idx))

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        model_id = self.config.name
        close = bar["close"]

        if self._plan is None:
            # 首根 bar 固化：经类方法调用（而非直接调模块函数）
            # 保持「固化=预览」同源，monkeypatch 篡改 price_plan 可污染固化结果（契约测试守护）
            self._plan = self.price_plan(self._fused_params(), close)
            self._prices = [lv.price for lv in self._plan.levels]
            if not self._prices:
                # 参数非法（plan warnings 已预警）：无可交易档位，只能 hold
                return Action(
                    action_type="hold",
                    confidence=0.0,
                    target_position=0.0,
                    model_id=model_id,
                    inference_time_us=0,
                )
            # 仅定位不动作：后续 bar 从该档位起判定穿档
            self._position_grid_idx = self._idx_of(close)
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        # 出界一律 hold：自适应扩展已移除；不动 _position_grid_idx，
        # 价格重新进入区间首根 bar 仍按「仍在原档」处理，穿越新档才触发
        if close < self._prices[0] or close > self._prices[-1]:
            return Action(
                action_type="hold",
                confidence=0.0,
                target_position=0.0,
                model_id=model_id,
                inference_time_us=0,
            )

        idx = self._idx_of(close)

        # 穿档触发：target_position 直接取固化计划该档的值（正买负卖）
        if idx < self._position_grid_idx:
            self._position_grid_idx = idx
            return Action(
                action_type="buy",
                confidence=0.5,
                target_position=self._plan.levels[idx].target_position,
                model_id=model_id,
                inference_time_us=0,
            )
        if idx > self._position_grid_idx:
            self._position_grid_idx = idx
            return Action(
                action_type="sell",
                confidence=0.5,
                target_position=self._plan.levels[idx].target_position,
                model_id=model_id,
                inference_time_us=0,
            )

        self._position_grid_idx = idx
        return Action(
            action_type="hold",
            confidence=0.0,
            target_position=0.0,
            model_id=model_id,
            inference_time_us=0,
        )
