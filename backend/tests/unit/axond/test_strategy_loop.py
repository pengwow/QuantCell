# -*- coding: utf-8 -*-
"""实盘策略主循环测试"""
import pytest
import time
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


class TestStrategyLoop:
    def test_creation(self):
        from axond.strategy_loop import StrategyLoop
        mock_adapter = MagicMock()
        mock_strategy = MagicMock()
        loop = StrategyLoop(adapter=mock_adapter, strategy=mock_strategy, symbol="BTCUSDT")
        assert loop.symbol == "BTCUSDT"
        assert loop.is_running is False

    def test_start_calls_on_start(self):
        from axond.strategy_loop import StrategyLoop
        mock_adapter = MagicMock()
        mock_strategy = MagicMock()
        loop = StrategyLoop(adapter=mock_adapter, strategy=mock_strategy, symbol="BTCUSDT")
        loop.start()
        mock_strategy.on_start.assert_called_once()
        assert loop.is_running is True
        loop.stop()

    def test_stop_calls_on_stop(self):
        from axond.strategy_loop import StrategyLoop
        mock_adapter = MagicMock()
        mock_strategy = MagicMock()
        loop = StrategyLoop(adapter=mock_adapter, strategy=mock_strategy, symbol="BTCUSDT")
        loop.start()
        loop.stop()
        mock_strategy.on_stop.assert_called_once()
        assert loop.is_running is False
        mock_adapter.disconnect.assert_called_once()

    def test_start_connects_adapter(self):
        from axond.strategy_loop import StrategyLoop
        mock_adapter = MagicMock()
        mock_strategy = MagicMock()
        loop = StrategyLoop(adapter=mock_adapter, strategy=mock_strategy, symbol="BTCUSDT")
        loop.start()
        mock_adapter.connect.assert_called_once()
        loop.stop()

    def test_start_subscribes(self):
        from axond.strategy_loop import StrategyLoop
        mock_adapter = MagicMock()
        mock_strategy = MagicMock()
        loop = StrategyLoop(adapter=mock_adapter, strategy=mock_strategy, symbol="BTCUSDT")
        loop.start()
        mock_adapter.subscribe.assert_called_once()
        loop.stop()

    def test_is_running_reflects_state(self):
        from axond.strategy_loop import StrategyLoop
        mock_adapter = MagicMock()
        mock_strategy = MagicMock()
        loop = StrategyLoop(adapter=mock_adapter, strategy=mock_strategy, symbol="BTCUSDT")
        assert loop.is_running is False
        loop.start()
        assert loop.is_running is True
        loop.stop()
        assert loop.is_running is False
