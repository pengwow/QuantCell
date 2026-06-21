# -*- coding: utf-8 -*-
"""axond.data_converter 数据转换器测试"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone


class TestDataframeToEvents:
    def test_basic_conversion(self):
        from axond.data_converter import dataframe_to_events
        df = pd.DataFrame({
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [103.0, 104.0],
            "volume": [1000.0, 2000.0],
        }, index=pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True))
        events = dataframe_to_events(df, "BTCUSDT")
        assert len(events) == 2
        assert events[0]["type"] == "market_data"
        assert events[0]["symbol"] == "BTCUSDT"
        assert events[0]["open"] == 100.0
        assert events[0]["high"] == 105.0
        assert events[0]["low"] == 99.0
        assert events[0]["close"] == 103.0
        assert events[0]["volume"] == 1000.0
        assert "timestamp_ns" in events[0]

    def test_empty_dataframe(self):
        from axond.data_converter import dataframe_to_events
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        events = dataframe_to_events(df, "BTCUSDT")
        assert events == []

    def test_case_insensitive_columns(self):
        from axond.data_converter import dataframe_to_events
        df = pd.DataFrame({
            "Open": [100.0],
            "High": [105.0],
            "Low": [99.0],
            "Close": [103.0],
            "Volume": [1000.0],
        }, index=pd.to_datetime(["2026-01-01"], utc=True))
        events = dataframe_to_events(df, "BTCUSDT")
        assert len(events) == 1
        assert events[0]["open"] == 100.0

    def test_timestamp_ns_is_int(self):
        from axond.data_converter import dataframe_to_events
        df = pd.DataFrame({
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [103.0],
            "volume": [1000.0],
        }, index=pd.to_datetime(["2026-01-01"], utc=True))
        events = dataframe_to_events(df, "BTCUSDT")
        assert isinstance(events[0]["timestamp_ns"], int)
        assert events[0]["timestamp_ns"] > 0


class TestStrategySignalsToEvents:
    def test_buy_signal(self):
        from axond.data_converter import strategy_signals_to_events
        signals = [{"action": "buy", "timestamp_ns": 1000, "price": 50000.0, "quantity": 0.1}]
        events = strategy_signals_to_events(signals, "BTCUSDT", start_id=1)
        assert len(events) == 1
        assert events[0]["type"] == "order_submitted"
        assert events[0]["order"]["side"] == "Buy"
        assert events[0]["order"]["symbol"] == "BTCUSDT"
        assert events[0]["order"]["price"] == 50000.0
        assert events[0]["order"]["quantity"] == 0.1

    def test_sell_signal(self):
        from axond.data_converter import strategy_signals_to_events
        signals = [{"action": "sell", "timestamp_ns": 2000, "price": 51000.0, "quantity": 0.2}]
        events = strategy_signals_to_events(signals, "BTCUSDT", start_id=5)
        assert len(events) == 1
        assert events[0]["order"]["side"] == "Sell"
        assert events[0]["order"]["id"] == 5

    def test_increasing_order_ids(self):
        from axond.data_converter import strategy_signals_to_events
        signals = [
            {"action": "buy", "timestamp_ns": 1000, "price": 50000.0, "quantity": 0.1},
            {"action": "sell", "timestamp_ns": 2000, "price": 51000.0, "quantity": 0.2},
            {"action": "buy", "timestamp_ns": 3000, "price": 50500.0, "quantity": 0.3},
        ]
        events = strategy_signals_to_events(signals, "BTCUSDT", start_id=10)
        assert events[0]["order"]["id"] == 10
        assert events[1]["order"]["id"] == 11
        assert events[2]["order"]["id"] == 12


class TestAxonResultToDict:
    def test_conversion(self):
        from axond.data_converter import axon_result_to_dict
        from types import SimpleNamespace
        result = SimpleNamespace(
            final_nav=110000.0,
            total_pnl=10000.0,
            max_drawdown=5000.0,
            orders_accepted=10,
            orders_rejected=1,
            fills=8,
        )
        d = axon_result_to_dict(result)
        assert d["final_nav"] == 110000.0
        assert d["total_pnl"] == 10000.0
        assert d["max_drawdown"] == 5000.0
        assert d["orders_accepted"] == 10
        assert d["orders_rejected"] == 1
        assert d["fills"] == 8
