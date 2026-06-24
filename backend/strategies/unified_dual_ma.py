from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide


class DualMAStrategy(UnifiedStrategy):
    def __init__(self, fast_period: int = 5, slow_period: int = 20):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.closes: list[float] = []
        self.position: float = 0.0

    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        self.closes.append(bar.close)
        if len(self.closes) < self.slow_period:
            return []

        fast_ma = sum(self.closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(self.closes[-self.slow_period:]) / self.slow_period

        orders = []
        if fast_ma > slow_ma and self.position == 0:
            orders.append(Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1, price=bar.close))
            self.position = 0.1
        elif fast_ma < slow_ma and self.position > 0:
            orders.append(Order(symbol=bar.symbol, side=OrderSide.SELL, quantity=0.1, price=bar.close))
            self.position = 0.0

        return orders
