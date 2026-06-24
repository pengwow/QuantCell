import uuid
from .config import EngineConfig
from .strategy_runtime import StrategyRuntime
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
