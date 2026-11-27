"""马丁格尔策略 — 分层加仓摊平，篮子止盈（2026-11 语义改造，spec §2.1）。

变更（语义变更，非兼容）：
- 旧语义「每根亏损 bar 倍数翻倍」（无价位概念）→ 新语义
  「价格每下跌一层间距触发一层加仓」；层价位/仓位/止盈价全部来自
  strategy.price_plan.martingale_plan（唯一公式权威，禁止复制）；
- on_start 预置为空，首根 bar 按其 close 固化整套计划到 self._plan
  （worker 启动链路与 preview 同传最新收盘，口径一致），启动后改参数
  不影响运行中 worker；篮子止盈后整套重置，下一根 bar 重新固化新一轮；
- direction/base_position/multiplier/max_multiplier/position_limit 含义不变；
  新增 spacing_pct / spacing_multiplier / layer_count / take_profit_pct
  （旧参数在 martingale_plan 内回落默认值，不迁移）。

方向与引擎约定（与 strategy.templates.martingale 对 target.py 后端一致）：
- target_position 为带符号的目标仓位占比：正=多头目标、负=空头目标，
  引擎按符号定方向；action_type 只表达「开/平方向」，hold 表示保持；
- short 向为镜像：层触发价 = 2×entry − 层价（上涨 = 层距时加仓），
  篮子止盈触发价 = 2×篮子均价 − tp 价（下跳同幅止盈）。
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
        self._tp_trigger: float = 0.0  # 篮子止盈触发价（已按方向镜像；0=无 tp 层）
        self._layer_hit: int = 0  # 已触发到的层号（0=仅建仓层）
        self._pos_dir: int = 0  # +1 多, -1 空, 0 空仓
        self._entry_price: float = 0.0

    @classmethod
    def price_plan(cls, params: dict, ref_price: float):
        # 公式权威在 strategy.price_plan；预览与固化都走这里
        return martingale_plan(params, ref_price)

    def _fused_params(self) -> dict:
        # position_limit 是 StrategyConfig 顶层字段，固化前合入 params
        # （martingale_plan 从 params 读，口径与旧 on_bar 的 limit 读取一致）
        params = dict(self.config.params)
        if params.get("position_limit") is None:
            params["position_limit"] = self.config.position_limit
        return params

    def on_start(self, ctx: StrategyContext | None = None) -> None:
        # 首根 bar 用其 close 固化（worker 启动链路此时还没有可靠参考价）
        self._plan = None
        self._buy_levels = []
        self._trigger_prices = []
        self._tp_trigger = 0.0
        self._layer_hit = 0
        self._pos_dir = 0
        self._entry_price = 0.0

    def _fix_plan(self, close: float) -> None:
        """按参考价固化整套计划并做方向镜像预处理。

        经 self.price_plan 类方法调用（而非直接调模块函数）：
        保持「固化=预览=worker 页」同源，篡改 price_plan 可污染固化结果
        （same-source 契约测试以此守护）。
        """
        self._plan = self.price_plan(self._fused_params(), close)
        buys = [lv for lv in self._plan.levels if lv.action == "buy"]
        self._buy_levels = buys
        direction: Literal["long", "short", "both"] = self.get_param("direction", "long")
        if direction == "short":
            self._trigger_prices = [2.0 * close - lv.price for lv in buys]
        else:
            self._trigger_prices = [lv.price for lv in buys]
        tp = next((lv for lv in self._plan.levels if lv.action == "tp"), None)
        if tp is None:
            self._tp_trigger = 0.0  # 计划无篮子止盈层（如参数非法/空计划）
        elif direction == "short":
            avg = self._plan.summary.extra.get("basket_avg", close)
            self._tp_trigger = 2.0 * avg - tp.price
        else:
            self._tp_trigger = tp.price
        self._layer_hit = 0

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        close = bar["close"]
        model_id = self.config.name

        if self._plan is None:
            # 首根 bar：按本根 close 固化计划并立即开建仓层
            self._fix_plan(close)
            return self._open(bar)

        # —— 篮子止盈：触及 tp 触发价平掉全部仓位并整套重置 ——
        if self._tp_trigger > 0.0 and (
            (self._pos_dir > 0 and close >= self._tp_trigger) or (self._pos_dir < 0 and close <= self._tp_trigger)
        ):
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
        """开建仓层。方向判定沿用旧版入场语义：
        - long  → 只做多
        - short → 只做空
        - both  → 由入场 bar 阴阳决定（阳进多、阴进空；open 缺失视为
          平开 → 沿用旧「非阳 → short」的兜底方向）
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
