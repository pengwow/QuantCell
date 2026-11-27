"""网格策略 — 等距挂单网格（计划型，2026-11 语义改造，spec §3.1）。

在 [lower, upper] 价格区间内等距放 levels+1 条档位线，
价格跌一档买一档,涨一档卖一档（低吸高抛）
震荡市表现好,趋势市反复被套

计划型语义（与 strategies/grid.py 创建版一致）：
- 首根 bar close 固化整套价格计划到 self._plan（公式唯一权威 =
  strategy.price_plan.grid_plan，预览 API 与运行固化共用同一实现），
  此后 bar-by-bar 只做穿档触发，启动后改参数不影响运行中 worker；
- 出界一律 hold（旧自适应区间扩展已移除），区间外空转风险由
  plan warnings 预警；
- price_plan 类方法使本策略在策略详情 / worker 页具备「价格计划」
  预览能力（AST 探测 has_price_plan，见 strategy/service.py）。

注：self.get_param(...) 调用是创建策略表单参数（variables）的 AST
提取源，价格计划区间/档位参数必须显式声明在此才会出现在表单中。
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
        # 模板版刻意逐参 get_param 显式读取（而非吞 config.params）：
        # AST 据此提取创建表单 variables，价格计划四件套在创建时即可配置；
        # 运行时语义与 get_param 缺省兜底一致（params 显式 None 视同缺省）
        return {
            "lower": float(self.get_param("lower", 60000.0)),
            "upper": float(self.get_param("upper", 70000.0)),
            "levels": int(self.get_param("levels", 20)),
            "position_limit": float(self.get_param("position_limit", self.config.position_limit)),
        }

    def on_start(self, ctx: StrategyContext | None = None) -> None:
        self._position_grid_idx = 0
        # 首根 bar close 固化（worker 启动链路与 preview 同传最新收盘，口径一致）
        self._plan = None
        self._prices = []

    def _idx_of(self, close: float) -> int:
        # 当前价落在第几条档位线：等距线下二分等价于旧 int((close-lower)/step) 截断
        idx = bisect_right(self._prices, close) - 1
        return max(0, min(len(self._prices) - 1, idx))

    def on_bar(self, bar: dict, ctx: StrategyContext | None = None) -> Action:
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
