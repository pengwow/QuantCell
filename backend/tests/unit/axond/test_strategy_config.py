# -*- coding: utf-8 -*-
"""axond.strategy_config 策略配置测试"""
import pytest
from decimal import Decimal


class TestStrategyConfig:
    def test_creation(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        config = StrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
        )
        assert len(config.instrument_ids) == 1
        assert len(config.bar_types) == 1

    def test_instrument_id_property(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        iid = InstrumentId("BTCUSDT", "BINANCE")
        config = StrategyConfig(instrument_ids=[iid], bar_types=["1-HOUR"])
        assert config.instrument_id == iid

    def test_bar_type_property(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        config = StrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
        )
        assert config.bar_type == "1-HOUR"

    def test_is_multi_symbol_single(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        config = StrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
        )
        assert config.is_multi_symbol is False

    def test_is_multi_symbol_multi(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        config = StrategyConfig(
            instrument_ids=[
                InstrumentId("BTCUSDT", "BINANCE"),
                InstrumentId("ETHUSDT", "BINANCE"),
            ],
            bar_types=["1-HOUR", "1-HOUR"],
        )
        assert config.is_multi_symbol is True

    def test_validation_empty_instrument_ids(self):
        from axond.strategy_config import StrategyConfig
        with pytest.raises(ValueError, match="不能为空"):
            StrategyConfig(instrument_ids=[], bar_types=["1-HOUR"])

    def test_validation_empty_bar_types(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        with pytest.raises(ValueError, match="不能为空"):
            StrategyConfig(instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")], bar_types=[])

    def test_validation_length_mismatch(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        with pytest.raises(ValueError, match="长度必须相同"):
            StrategyConfig(
                instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
                bar_types=["1-HOUR", "1-MINUTE"],
            )

    def test_custom_fields(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        config = StrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
            trade_size=Decimal("0.5"),
            log_level="DEBUG",
        )
        assert config.trade_size == Decimal("0.5")
        assert config.log_level == "DEBUG"

    def test_default_values(self):
        from axond.strategy_config import StrategyConfig
        from axond.types import InstrumentId
        config = StrategyConfig(
            instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
            bar_types=["1-HOUR"],
        )
        assert config.trade_size == Decimal("1.0")
        assert config.log_level == "INFO"
