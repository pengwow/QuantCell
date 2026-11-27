"""马丁格尔策略 — 分层加仓摊平，篮子止盈（2026-11 计划型语义，spec §2.1）。

核心机制（与 strategies/martingale.py 创建版一致）：
- 层价位/仓位/止盈价全部来自 strategy.price_plan.martingale_plan
  （唯一公式权威，禁止复制）：价格每下跌一层间距触发一层加仓；
- 首根 bar 按其 close 固化整套计划（worker 启动链路与 preview 同传
  最新收盘，口径一致），启动后改参数不影响运行中 worker；
- 篮子止盈后整套重置，下一根 bar 重新固化新一轮；
- direction/base_position/multiplier/max_multiplier/position_limit
  含义不变；spacing_pct / spacing_multiplier / layer_count /
  take_profit_pct 为价格计划配置项（分层节奏与止盈幅度）。

方向与引擎约定（与 target.py 后端一致）：
- target_position 为带符号的目标仓位占比：正=多头目标、负=空头目标，
  引擎按符号定方向；action_type 只表达「开/平方向」，hold 表示保持；
- short 向为镜像：层触发价 = 2×entry − 层价（上涨 = 层距时加仓）；
  篮子止盈价按已触发层的实际篮子均价动态计算（均价 × (1±tp%)），
  plan 的 tp 层仅作「全层触发后」的预览参考。
- 做空需要回测交易模式为 futures（现货引擎无法持有负仓位）。

注：self.get_param(...) 调用是创建表单参数（variables）的 AST 提取源，
direction 渲染为下拉（Literal 注解绑定），spacing/layer/take_profit
系价格计划完整配置项，缺省值与公式库对齐。
"""

from __future__ import annotations

from typing import Literal

from strategy import Action, BaseStrategy, StrategyConfig, StrategyContext
from strategy.price_plan import martingale_plan


class Martingale(BaseStrategy):
    """马丁格尔策略（分层执行）。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._plan = None
        self._buy_levels: list = []  # 计划的建仓/加仓层（PricePlanLevel 列表）
        self._trigger_prices: list[float] = []  # 按方向镜像后的层触发价
        self._layer_hit: int = 0  # 已触发到的层号（0=仅建仓层）
        self._pos_dir: int = 0  # +1 多, -1 空, 0 空仓
        self._entry_price: float = 0.0

    @classmethod
    def price_plan(cls, params: dict, ref_price: float):
        # 公式权威在 strategy.price_plan；预览与固化都走这里
        return martingale_plan(params, ref_price)

    def _fused_params(self) -> dict:
        # 模板版刻意逐参 get_param 显式读取（而非吞 config.params）：
        # AST 据此提取创建表单 variables，价格计划配置项创建时即可配置；
        # 缺省值与 martingale_plan 公式库严格对齐；direction 不入公式
        # （只影响执行端镜像），在 _fix_plan/_open 读取
        return {
            "base_position": float(self.get_param("base_position", 0.1)),
            "multiplier": float(self.get_param("multiplier", 2.0)),
            "max_multiplier": float(self.get_param("max_multiplier", 4.0)),
            # position_limit 是 StrategyConfig 顶层字段，固化前合入 params
            "position_limit": float(self.get_param("position_limit", self.config.position_limit)),
            "spacing_pct": float(self.get_param("spacing_pct", 2.0)),
            "spacing_multiplier": float(self.get_param("spacing_multiplier", 1.5)),
            "layer_count": int(self.get_param("layer_count", 5)),
            "take_profit_pct": float(self.get_param("take_profit_pct", 1.0)),
        }

    def on_start(self, ctx: StrategyContext | None = None) -> None:
        # 首根 bar 用其 close 固化（worker 启动链路此时还没有可靠参考价）
        self._plan = None
        self._buy_levels = []
        self._trigger_prices = []
        self._layer_hit = 0
        self._pos_dir = 0
        self._entry_price = 0.0

    def _fix_plan(self, close: float) -> None:
        """按参考价固化整套计划并做方向镜像预处理。

        经 self.price_plan 类方法调用（而非直接调模块函数）：
        保持「固化=预览=worker 页」同源，篡改 price_plan 可污染固化结果
        （same-source 契约测试以此守护）。

        plan 的 tp 层只供预览展示（全层触发后的篮子止盈参考价）；
        运行端止盈按已触发层的实际篮子均价动态计算（见 _basket），
        不消费 tp 层——「未摊平先止盈」的误触发由此杜绝。
        """
        self._plan = self.price_plan(self._fused_params(), close)
        buys = [lv for lv in self._plan.levels if lv.action == "buy"]
        self._buy_levels = buys
        # Literal 注解声明可选范围，AST 解析据此在前端渲染下拉（strategy/service.py）
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        if direction == "short":
            self._trigger_prices = [2.0 * close - lv.price for lv in buys]
        else:
            self._trigger_prices = [lv.price for lv in buys]
        self._layer_hit = 0

    def _basket(self) -> tuple[float, float]:
        """已触发层构成的篮子（加权均价, 总仓）。空仓返回 (0, 0)。

        近似口径：假设引擎按各层触发价精确成交（long=层价, short=镜像
        触发价），权重 = |target_position|；实际回测/live 按 bar close
        撮合存在基差，tp 触发点随之有小偏差（ponytail：升格路径 = 由
        ExecutionSink 回传真实篮子均价替换本近似）。
        """
        if self._pos_dir == 0 or not self._buy_levels:
            return 0.0, 0.0
        n = self._layer_hit + 1
        marks = self._trigger_prices[:n] if self._pos_dir < 0 else [lv.price for lv in self._buy_levels[:n]]
        sizes = [abs(lv.target_position) for lv in self._buy_levels[:n]]
        q = sum(sizes)
        if q <= 0.0:
            return 0.0, 0.0
        return sum(m * s for m, s in zip(marks, sizes, strict=True)) / q, q

    def on_bar(self, bar: dict, ctx: StrategyContext | None = None) -> Action:
        close = bar["close"]
        model_id = self.config.name

        if self._plan is None:
            # 首根 bar：按本根 close 固化计划并立即开建仓层
            self._fix_plan(close)
            return self._open(bar)

        # —— 篮子止盈：按已触发层的实际篮子均价动态触发，平仓后整套重置。
        # 2026-11-27 修复：旧实现用计划全层均价（含未触发层）固定触发价，
        # 该价低于建仓价，导致建仓后小幅回调即在亏损位「止盈」离场，
        # 策略退化为每 bar 开平循环。
        if self._pos_dir != 0:
            take_profit_pct = float(self.get_param("take_profit_pct", 1.0))
            if take_profit_pct > 0.0:
                avg, _q = self._basket()
                if avg > 0.0:
                    tp_price = (
                        avg * (1.0 - take_profit_pct / 100.0)
                        if self._pos_dir < 0
                        else avg * (1.0 + take_profit_pct / 100.0)
                    )
                    if (self._pos_dir > 0 and close >= tp_price) or (self._pos_dir < 0 and close <= tp_price):
                        close_action = "sell" if self._pos_dir > 0 else "buy"
                        self.on_start(None)
                        return Action(
                            action_type=close_action,
                            confidence=0.9,
                            target_position=0.0,
                            model_id=f"{model_id}_tp",
                            inference_time_us=0,
                        )

        # —— 加仓层逐层触发（long 向下 / short 向上；镜像触发价已预处理）——
        if self._pos_dir > 0:
            while (
                self._layer_hit + 1 < len(self._trigger_prices) and close <= self._trigger_prices[self._layer_hit + 1]
            ):
                self._layer_hit += 1
        elif self._pos_dir < 0:
            while (
                self._layer_hit + 1 < len(self._trigger_prices) and close >= self._trigger_prices[self._layer_hit + 1]
            ):
                self._layer_hit += 1

        target = self._buy_levels[self._layer_hit].target_position if self._buy_levels else 0.0
        # hold 只回报当前层目标仓位；符号携带方向（引擎按符号定多空）
        return Action(
            action_type="hold",
            confidence=0.5,
            target_position=self._pos_dir * target,
            model_id=model_id,
            inference_time_us=0,
        )

    def _open(self, bar: dict) -> Action:
        """开建仓层。方向判定入场语义：
        - long  → 只做多
        - short → 只做空
        - both  → 由入场 bar 阴阳决定（阳进多、阴进空；open 缺失视为
          平开 → 沿用「非阳 → short」的兜底方向）
        （建仓层在固化当根立即开盘，旧「上一根收阳/收阴才入场」的
        前置等待在新固化协议下不再适用——spec §2.1 层 0 即建仓。）
        """
        close = bar["close"]
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        if direction == "short":
            self._pos_dir = -1
        elif direction == "both":
            up = close > bar.get("open", close)
            self._pos_dir = 1 if up else -1
        else:
            self._pos_dir = 1
        self._entry_price = close
        entry_target = self._pos_dir * self._buy_levels[0].target_position if self._buy_levels else 0.0
        return Action(
            action_type="buy" if self._pos_dir > 0 else "sell",
            confidence=0.7,
            target_position=entry_target,
            model_id=self.config.name,
            inference_time_us=0,
        )
