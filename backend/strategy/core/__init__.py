"""策略核心 — 统一导出 axon_quant 类型"""

from axon_bridge import (
    Action,
    ActionType,
    BacktestEngine,
    Observation,
    RunResult,
)
from axon_bridge.rl import TradingEnv


class StrategyBase:
    """Legacy 策略基类，兼容旧版策略接口"""

    def on_bar(self, bar: dict) -> Action:
        raise NotImplementedError

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass


__all__ = [
    "Action",
    "ActionType",
    "BacktestEngine",
    "Observation",
    "RunResult",
    "StrategyBase",
    "TradingEnv",
]
