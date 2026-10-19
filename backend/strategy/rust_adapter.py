"""Rust BacktestRunner 适配器：把 QuantCell BaseStrategy 桥接到 Rust Strategy trait。

Rust 侧 axon_quant.worker.BacktestRunner 期望策略实现 `decide(bar_dict) -> dict`，
而 QuantCell 的 BaseStrategy 是 `on_bar(bar, ctx) -> Action`。本适配器：
1. 自己维护 StrategyContext（closes/highs/lows 逐 bar 累积）
2. 调用 strategy.on_bar(bar, ctx)
3. 把 Action 转成 Rust 期望的 dict（action_type/confidence/target_position）

用法：
    from strategy.rust_adapter import RustStrategyAdapter
    from axon_quant import worker

    adapter = RustStrategyAdapter(base_strategy)
    runner = worker.BacktestRunner(initial_cash=100000.0)
    runner.add_strategy(adapter)
    result = runner.run(bars=[...], states_by_symbol={})
"""

from __future__ import annotations

from strategy.base import BaseStrategy, StrategyContext
from strategy.target import ratio_to_target_qty


class RustStrategyAdapter:
    """BaseStrategy → Rust BacktestRunner 适配器。

    维护 StrategyContext 状态，把 on_bar(bar, ctx) 适配为 decide(bar) -> dict。

    语义对齐（与 `BacktestLoop` 逐 bar 循环保持一致，保证结果 parity）：
    - Rust `set_target_position` 收**绝对数量**；而策略的 `target_position` 是**权益占比**，
      故在 buy/sell 决策时按 `ratio * equity / price` 换算（复用 `ratio_to_target_qty` 口径）。
    - hold 决策**不改目标位**（与 BacktestLoop "仅 buy/sell 调 set_target_position" 一致），
      否则 Rust 侧会把 hold 当 target=0 平掉仓位。
    - Rust `Instrument::from_symbol` 需要 `BASE/QUOTE` 分隔格式，故 symbol 归一化。
    """

    def __init__(self, strategy: BaseStrategy, initial_cash: float = 100_000.0):
        self._strategy = strategy
        self._initial_cash = initial_cash
        raw_symbol = getattr(strategy.config, "symbol", "BTCUSDT")
        self._symbol = _normalize_symbol(raw_symbol)
        self._ctx = StrategyContext(symbol=raw_symbol)
        self._strategy.on_start(self._ctx)
        # 当前目标持仓数量（绝对量），hold 时保持不变
        self._last_target_qty = 0.0

    @property
    def name(self) -> str:
        return self._strategy.config.name

    @property
    def symbol(self) -> str:
        return self._symbol

    def decide(self, bar: dict) -> dict:
        """Rust 调用入口：bar dict → 决策 dict（target_position 为绝对目标数量）。

        Rust 侧把逐 bar state 放在 `bar["state"]`（非空时），此处映射回
        `BacktestLoop` 的注入口径：`features` → `ctx.features`，
        `cross_sectional_rank` → `bar["cross_sectional_rank"]`。
        """
        state = bar.pop("state", None)
        if isinstance(state, dict):
            feats = state.get("features")
            if isinstance(feats, dict):
                self._ctx.features = {str(k): float(v) for k, v in feats.items()}
            rank = state.get("cross_sectional_rank")
            if rank is not None:
                bar["cross_sectional_rank"] = int(rank)

        action = self._strategy.on_bar(bar, self._ctx)
        action_type = str(action.action_type)

        # 仅 buy/sell 更新目标位；hold 保持上次目标（对齐 BacktestLoop 行为）
        if action_type in ("buy", "sell"):
            ratio = float(getattr(action, "target_position", 0.0) or 0.0)
            price = float(bar["close"])
            self._last_target_qty = ratio_to_target_qty(ratio, self._initial_cash, price) if price > 0 else 0.0

        return {
            "action_type": action_type,
            "confidence": action.confidence,
            "target_position": self._last_target_qty,
        }


def _normalize_symbol(symbol: str) -> str:
    """把 'BTCUSDT' / 'BTC-USDT' 归一化为 Rust 可解析的 'BTC/USDT'。"""
    s = symbol.upper()
    if "/" in s:
        return s
    # 无分隔符：去掉 "-"/"_" 后按已知计价币后缀切分
    s = s.replace("-", "").replace("_", "")
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[: -len(quote)]}/{quote}"
    return s
