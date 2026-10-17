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
    result = runner.run(bars=[...], state_by_symbol={})
"""

from __future__ import annotations

from axon_quant import Action

from strategy.base import BaseStrategy, StrategyContext


class RustStrategyAdapter:
    """BaseStrategy → Rust BacktestRunner 适配器。

    维护 StrategyContext 状态，把 on_bar(bar, ctx) 适配为 decide(bar) -> dict。
    """

    def __init__(self, strategy: BaseStrategy):
        self._strategy = strategy
        symbol = getattr(strategy.config, "symbol", "BTCUSDT")
        self._ctx = StrategyContext(symbol=symbol)
        self._strategy.on_start(self._ctx)

    @property
    def name(self) -> str:
        return self._strategy.config.name

    @property
    def symbol(self) -> str:
        return getattr(self._strategy.config, "symbol", "BTCUSDT")

    def decide(self, bar: dict) -> dict:
        """Rust 调用入口：bar dict → 决策 dict。"""
        action: Action = self._strategy.on_bar(bar, self._ctx)
        return {
            "action_type": action.action_type,
            "confidence": action.confidence,
            "target_position": action.target_position,
        }
