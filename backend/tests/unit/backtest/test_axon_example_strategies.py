# -*- coding: utf-8 -*-
"""axon 示例策略测试"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone


class TestAxonDualMAStrategy:
    def test_strategy_creation(self):
        from strategies.axon_dual_ma import DualEMACrossover, DualEMACrossoverConfig
        from axond.types import InstrumentId

        config = DualEMACrossoverConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
            fast_period=5,
            slow_period=10,
            trade_size=Decimal("0.1"),
        )
        strategy = DualEMACrossover(config)
        assert strategy.config.fast_period == 5
        assert strategy.config.slow_period == 10
        assert strategy.position_held is False

    def test_strategy_on_bar(self):
        from strategies.axon_dual_ma import DualEMACrossover, DualEMACrossoverConfig
        from axond.types import Bar, InstrumentId

        config = DualEMACrossoverConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
            fast_period=3,
            slow_period=5,
            trade_size=Decimal("0.1"),
        )
        strategy = DualEMACrossover(config)
        strategy.on_start()

        # 生成测试数据
        prices = [100, 102, 104, 106, 108, 110, 108, 106, 104, 102]
        for i, price in enumerate(prices):
            bar = Bar(
                instrument_id=InstrumentId("BTCUSDT", "BINANCE"),
                bar_type="1-HOUR",
                open=float(price),
                high=float(price + 2),
                low=float(price - 2),
                close=float(price),
                volume=1000.0,
                timestamp=datetime(2026, 1, 1, i, tzinfo=timezone.utc),
                ts_event=int(datetime(2026, 1, 1, i, tzinfo=timezone.utc).timestamp() * 1e9),
            )
            strategy.on_bar(bar)

        # 验证策略处理了K线
        assert strategy.bars_processed == 10

    def test_strategy_config_validation(self):
        from strategies.axon_dual_ma import DualEMACrossover, DualEMACrossoverConfig
        from axond.types import InstrumentId

        # 快线周期必须小于慢线周期
        config = DualEMACrossoverConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
            fast_period=20,
            slow_period=10,
        )
        with pytest.raises(ValueError, match="快线周期"):
            DualEMACrossover(config)
