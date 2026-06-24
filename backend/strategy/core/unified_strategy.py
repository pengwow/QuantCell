from abc import ABC, abstractmethod
from .bar import Bar
from .order import Order


class StrategyContext:
    def __init__(self):
        self._positions: dict[str, float] = {}

    def get_position(self, symbol: str) -> float:
        return self._positions.get(symbol, 0.0)


class UnifiedStrategy(ABC):

    def on_start(self, ctx: StrategyContext) -> None:
        pass

    @abstractmethod
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        ...

    def on_stop(self, ctx: StrategyContext) -> None:
        pass
