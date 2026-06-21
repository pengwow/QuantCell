# -*- coding: utf-8 -*-
"""axond.types 类型定义测试"""
import pytest
from datetime import datetime, timezone


class TestEnums:
    def test_order_side_values(self):
        from axond.types import OrderSide
        assert OrderSide.BUY.value == "Buy"
        assert OrderSide.SELL.value == "Sell"

    def test_order_type_values(self):
        from axond.types import OrderType
        assert OrderType.MARKET.value == "Market"
        assert OrderType.LIMIT.value == "Limit"
        assert OrderType.STOP_LOSS.value == "StopLoss"
        assert OrderType.STOP_LIMIT.value == "StopLimit"

    def test_time_in_force_values(self):
        from axond.types import TimeInForce
        assert TimeInForce.GTC.value == "GTC"
        assert TimeInForce.IOC.value == "IOC"
        assert TimeInForce.FOK.value == "FOK"

    def test_position_side_values(self):
        from axond.types import PositionSide
        assert PositionSide.LONG.value == "Long"
        assert PositionSide.SHORT.value == "Short"
        assert PositionSide.FLAT.value == "Flat"


class TestInstrumentId:
    def test_creation(self):
        from axond.types import InstrumentId
        iid = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        assert iid.symbol == "BTCUSDT"
        assert iid.venue == "BINANCE"

    def test_str(self):
        from axond.types import InstrumentId
        iid = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        assert str(iid) == "BTCUSDT.BINANCE"

    def test_equality_and_hash(self):
        from axond.types import InstrumentId
        a = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        b = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        c = InstrumentId(symbol="ETHUSDT", venue="BINANCE")
        assert a == b
        assert a != c
        assert hash(a) == hash(b)
        d = {a: "btc"}
        assert d[b] == "btc"


class TestBar:
    def test_creation(self):
        from axond.types import Bar, InstrumentId
        iid = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        bar = Bar(
            instrument_id=iid,
            bar_type="1-HOUR",
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0,
            volume=1000.0,
            timestamp=ts,
            ts_event=1735689600000000000,
        )
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 99.0
        assert bar.close == 103.0
        assert bar.volume == 1000.0
        assert bar.instrument_id == iid
        assert bar.bar_type == "1-HOUR"
        assert bar.timestamp == ts
        assert bar.ts_event == 1735689600000000000


class TestQuoteTick:
    def test_creation(self):
        from axond.types import QuoteTick, InstrumentId
        iid = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tick = QuoteTick(
            instrument_id=iid,
            bid=100.0,
            ask=100.5,
            bid_size=10.0,
            ask_size=5.0,
            timestamp=ts,
            ts_event=1735689600000000000,
        )
        assert tick.bid == 100.0
        assert tick.ask == 100.5
        assert tick.bid_size == 10.0
        assert tick.ask_size == 5.0


class TestTradeTick:
    def test_creation(self):
        from axond.types import TradeTick, InstrumentId, OrderSide
        iid = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tick = TradeTick(
            instrument_id=iid,
            price=100.0,
            quantity=1.5,
            aggressor_side=OrderSide.BUY,
            trade_id="T001",
            timestamp=ts,
            ts_event=1735689600000000000,
        )
        assert tick.price == 100.0
        assert tick.quantity == 1.5
        assert tick.aggressor_side == OrderSide.BUY
        assert tick.trade_id == "T001"


class TestPosition:
    def test_creation(self):
        from axond.types import Position, InstrumentId, PositionSide
        from decimal import Decimal
        iid = InstrumentId(symbol="BTCUSDT", venue="BINANCE")
        pos = Position(
            instrument_id=iid,
            side=PositionSide.LONG,
            quantity=Decimal("0.5"),
            avg_price=50000.0,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
        )
        assert pos.side == PositionSide.LONG
        assert pos.quantity == Decimal("0.5")
        assert pos.avg_price == 50000.0
        assert pos.unrealized_pnl == 100.0


class TestAccountBalance:
    def test_creation(self):
        from axond.types import AccountBalance
        from decimal import Decimal
        bal = AccountBalance(
            currency="USDT",
            total=Decimal("100000"),
            available=Decimal("90000"),
            locked=Decimal("10000"),
        )
        assert bal.currency == "USDT"
        assert bal.total == Decimal("100000")
        assert bal.available == Decimal("90000")
        assert bal.locked == Decimal("10000")

    def test_default_locked(self):
        from axond.types import AccountBalance
        from decimal import Decimal
        bal = AccountBalance(
            currency="USDT",
            total=Decimal("100000"),
            available=Decimal("100000"),
        )
        assert bal.locked == Decimal("0")
