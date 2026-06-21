# -*- coding: utf-8 -*-
"""axon 结果格式化器测试"""
import pytest


class TestAxonResultFormatter:
    def test_format_single_result(self):
        from axond.result_formatter import format_backtest_result
        result = {
            "final_nav": 110000.0,
            "total_pnl": 10000.0,
            "max_drawdown": 5000.0,
            "orders_accepted": 10,
            "orders_rejected": 1,
            "fills": 8,
        }
        formatted = format_backtest_result(result, symbol="BTCUSDT", timeframe="1h", strategy_name="test")
        assert formatted["symbol"] == "BTCUSDT"
        assert formatted["timeframe"] == "1h"
        assert formatted["strategy_name"] == "test"
        assert formatted["metrics"]["final_nav"] == 110000.0
        assert formatted["metrics"]["total_pnl"] == 10000.0

    def test_format_multi_result(self):
        from axond.result_formatter import format_multi_result
        results = {
            "BTCUSDT": {
                "final_nav": 110000.0, "total_pnl": 10000.0, "max_drawdown": 5000.0,
                "orders_accepted": 5, "orders_rejected": 0, "fills": 5,
            },
            "ETHUSDT": {
                "final_nav": 52000.0, "total_pnl": 2000.0, "max_drawdown": 1000.0,
                "orders_accepted": 3, "orders_rejected": 0, "fills": 3,
            },
        }
        formatted = format_multi_result(results, timeframe="1h", strategy_name="test")
        assert "BTCUSDT" in formatted["per_symbol"]
        assert "ETHUSDT" in formatted["per_symbol"]
        assert formatted["portfolio"]["total_pnl"] == 12000.0
        assert formatted["portfolio"]["final_nav"] == 162000.0

    def test_format_empty_result(self):
        from axond.result_formatter import format_backtest_result
        result = {
            "final_nav": 100000.0, "total_pnl": 0.0, "max_drawdown": 0.0,
            "orders_accepted": 0, "orders_rejected": 0, "fills": 0,
        }
        formatted = format_backtest_result(result, symbol="BTCUSDT", timeframe="1h", strategy_name="test")
        assert formatted["metrics"]["total_pnl"] == 0.0
