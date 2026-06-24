import uuid

import pandas as pd

from .config import EngineConfig
from .strategy_runtime import StrategyRuntime
from backtest.backtest_loop import BacktestLoop, BacktestResult
from strategy.core.unified_strategy import UnifiedStrategy


class TradingEngine:
    def __init__(self, config: EngineConfig):
        self._config = config
        self._strategies: dict[str, StrategyRuntime] = {}

    def register_strategy(self, strategy: UnifiedStrategy, symbols: list[str]) -> str:
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid, strategy=strategy, symbols=symbols
        )
        return sid

    def list_strategies(self) -> list[dict]:
        return [{"id": s.strategy_id, "status": s.status, "symbols": s.symbols}
                for s in self._strategies.values()]

    def run_backtest(self, strategy: UnifiedStrategy, data: pd.DataFrame, symbol: str = "BTCUSDT") -> BacktestResult:
        loop = BacktestLoop(initial_cash=100_000.0)
        return loop.run(strategy, data, symbol)
