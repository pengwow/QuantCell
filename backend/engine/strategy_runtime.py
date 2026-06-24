from dataclasses import dataclass
from strategy.core.unified_strategy import UnifiedStrategy


@dataclass
class StrategyRuntime:
    strategy_id: str
    strategy: UnifiedStrategy
    symbols: list[str]
    status: str = "stopped"
