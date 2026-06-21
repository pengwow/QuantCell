# -*- coding: utf-8 -*-
"""AxonStrategy 策略基类测试"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock


@pytest.fixture
def config():
    from axond.types import InstrumentId
    from axond.strategy_config import StrategyConfig
    return StrategyConfig(
        instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
        bar_types=["1-HOUR"],
        trade_size=Decimal("0.1"),
    )


@pytest.fixture
def bar():
    from axond.types import Bar, InstrumentId
    from datetime import datetime, timezone
    return Bar(
        instrument_id=InstrumentId("BTCUSDT", "BINANCE"),
        bar_type="1-HOUR",
        open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ts_event=1735689600000000000,
    )


class TestAxonStrategy:
    def test_creation(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        assert strategy.config == config
        assert strategy.bars_processed == 0
        assert strategy.start_time is None

    def test_on_start(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        strategy.on_start()
        assert strategy.start_time is not None
        assert strategy.bars_processed == 0

    def test_on_bar_increments_count(self, config, bar):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        strategy.on_start()
        strategy.on_bar(bar)
        assert strategy.bars_processed == 1
        strategy.on_bar(bar)
        assert strategy.bars_processed == 2

    def test_on_stop(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        strategy.on_start()
        strategy.on_stop()
        assert strategy.end_time is not None

    def test_buy_creates_order(self, config):
        from axond.axon_strategy import AxonStrategy
        from axond.types import OrderType
        strategy = AxonStrategy(config)
        strategy.on_start()
        order = strategy.buy("BTCUSDT", 0.1, 50000.0)
        assert order["side"] == "Buy"
        assert order["symbol"] == "BTCUSDT"
        assert order["quantity"] == 0.1
        assert order["price"] == 50000.0
        assert order["type"] == "limit"
        assert len(strategy._orders) == 1

    def test_buy_market_order(self, config):
        from axond.axon_strategy import AxonStrategy
        from axond.types import OrderType
        strategy = AxonStrategy(config)
        strategy.on_start()
        order = strategy.buy("BTCUSDT", 0.1, order_type=OrderType.MARKET)
        assert order["type"] == "market"

    def test_sell_creates_order(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        strategy.on_start()
        order = strategy.sell("BTCUSDT", 0.2, 51000.0)
        assert order["side"] == "Sell"
        assert order["quantity"] == 0.2
        assert len(strategy._orders) == 1

    def test_buy_pushes_to_engine(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        strategy.on_start()
        mock_engine = MagicMock()
        strategy._engine = mock_engine
        strategy.buy("BTCUSDT", 0.1, 50000.0)
        mock_engine.submit_order.assert_called_once()

    def test_get_position_returns_none_when_empty(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        assert strategy.get_position("BTCUSDT") is None

    def test_get_position_size_returns_zero_when_empty(self, config):
        from axond.axon_strategy import AxonStrategy
        strategy = AxonStrategy(config)
        assert strategy.get_position_size("BTCUSDT") == 0.0

    def test_close_position(self, config):
        from axond.axon_strategy import AxonStrategy
        from axond.types import Position, InstrumentId, PositionSide
        strategy = AxonStrategy(config)
        strategy.on_start()
        iid = InstrumentId("BTCUSDT", "BINANCE")
        strategy._positions["BTCUSDT"] = Position(
            instrument_id=iid, side=PositionSide.LONG,
            quantity=Decimal("0.1"), avg_price=50000.0,
        )
        order = strategy.close_position("BTCUSDT")
        assert order["side"] == "Sell"
        assert order["quantity"] == 0.1


class TestAxonStrategySubclass:
    def test_subclass_on_bar(self, config, bar):
        from axond.axon_strategy import AxonStrategy

        class MyStrategy(AxonStrategy):
            def on_bar(self, bar):
                super().on_bar(bar)
                if self.bars_processed == 1:
                    self.buy(bar.instrument_id.symbol, self.config.trade_size, bar.close)

        strategy = MyStrategy(config)
        strategy.on_start()
        strategy.on_bar(bar)
        assert strategy.bars_processed == 1
        assert len(strategy._orders) == 1
        assert strategy._orders[0]["side"] == "Buy"
