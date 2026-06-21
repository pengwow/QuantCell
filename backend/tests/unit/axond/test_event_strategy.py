# -*- coding: utf-8 -*-
"""事件驱动策略测试"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
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
    return Bar(
        instrument_id=InstrumentId("BTCUSDT", "BINANCE"),
        bar_type="1-HOUR",
        open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ts_event=1735689600000000000,
    )


class TestEventDrivenStrategy:
    def test_creation(self, config):
        from axond.event_strategy import EventDrivenStrategy
        strategy = EventDrivenStrategy(config)
        assert strategy.config == config

    def test_subclass_on_bar_called(self, config, bar):
        from axond.event_strategy import EventDrivenStrategy

        class MyStrategy(EventDrivenStrategy):
            def _on_bar_impl(self, bar):
                self.buy(bar.instrument_id.symbol, 0.1, bar.close)

        strategy = MyStrategy(config)
        strategy.on_start()
        strategy.on_bar(bar)
        assert strategy.bars_processed == 1
        assert len(strategy._orders) == 1

    def test_multi_symbol_config(self):
        from axond.types import InstrumentId
        from axond.strategy_config import StrategyConfig
        from axond.event_strategy import EventDrivenStrategy
        config = StrategyConfig(
            instrument_ids=[
                InstrumentId("BTCUSDT", "BINANCE"),
                InstrumentId("ETHUSDT", "BINANCE"),
            ],
            bar_types=["1-HOUR", "1-HOUR"],
        )
        strategy = EventDrivenStrategy(config)
        assert strategy.config.is_multi_symbol is True

    def test_engine_injection(self, config):
        from axond.event_strategy import EventDrivenStrategy
        strategy = EventDrivenStrategy(config)
        mock_engine = MagicMock()
        strategy._engine = mock_engine
        strategy.buy("BTCUSDT", 0.1, 50000.0)
        mock_engine.submit_order.assert_called_once()
