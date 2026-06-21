# -*- coding: utf-8 -*-
"""axond 包导入测试"""
import pytest


class TestAxondImports:
    def test_import_types(self):
        from axond import types
        assert hasattr(types, "OrderSide")
        assert hasattr(types, "OrderType")
        assert hasattr(types, "TimeInForce")
        assert hasattr(types, "PositionSide")
        assert hasattr(types, "InstrumentId")
        assert hasattr(types, "Bar")
        assert hasattr(types, "QuoteTick")
        assert hasattr(types, "TradeTick")
        assert hasattr(types, "Position")
        assert hasattr(types, "AccountBalance")

    def test_import_data_converter(self):
        from axond import data_converter
        assert hasattr(data_converter, "dataframe_to_events")
        assert hasattr(data_converter, "strategy_signals_to_events")
        assert hasattr(data_converter, "axon_result_to_dict")
