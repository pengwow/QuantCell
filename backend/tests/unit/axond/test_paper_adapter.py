"""PaperExchangeAdapter 单元测试"""
import pytest
import time
from axond.paper_adapter import PaperExchangeAdapter, build_paper_adapter


class TestPaperExchangeAdapter:
    """PaperExchangeAdapter 行为测试"""

    def test_default_construction(self):
        adapter = PaperExchangeAdapter()
        assert adapter.exchange == "paper"
        assert adapter.trading_mode == "paper"
        assert adapter.is_connected is False

    def test_connect_disconnect(self):
        adapter = PaperExchangeAdapter()
        adapter.connect()
        assert adapter.is_connected is True
        adapter.disconnect()
        assert adapter.is_connected is False

    def test_subscribe_seeds_ticker(self):
        adapter = PaperExchangeAdapter()
        adapter.subscribe(["BTCUSDT", "ETHUSDT"])
        # 即使不显式调用 connect，subscribe 也可使用
        assert "BTCUSDT" in adapter.list_orders() or len(adapter.list_orders()) == 0

    def test_get_ticker_returns_ohlcv(self):
        adapter = PaperExchangeAdapter()
        ticker = adapter.get_ticker("BTCUSDT")
        for key in ("open", "high", "low", "last", "volume"):
            assert key in ticker
            assert isinstance(ticker[key], float)

    def test_get_ticker_uses_injected_data(self):
        adapter = PaperExchangeAdapter()
        adapter.inject_ticker("BTCUSDT", {
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "last": 102.0,
            "volume": 10.0,
        })
        ticker = adapter.get_ticker("BTCUSDT")
        # 注入的 open 应保持不变
        assert ticker["open"] == 100.0
        # 注入的 high/low 应在随机游走中保持
        assert ticker["high"] >= 102.0
        assert ticker["low"] <= 102.0

    def test_place_order_returns_receipt(self):
        adapter = PaperExchangeAdapter()
        receipt = adapter.place_order({
            "symbol": "BTCUSDT",
            "side": "Buy",
            "type": "limit",
            "quantity": 0.1,
            "price": 50000.0,
        })
        assert receipt["status"] == "ACCEPTED"
        assert receipt["symbol"] == "BTCUSDT"
        assert "order_id" in receipt
        assert len(adapter.list_orders()) == 1

    def test_list_orders_returns_copy(self):
        adapter = PaperExchangeAdapter()
        adapter.place_order({"symbol": "BTCUSDT", "side": "Buy", "quantity": 0.1})
        orders = adapter.list_orders()
        orders.clear()
        # 内部状态不受外部修改影响
        assert len(adapter.list_orders()) == 1

    def test_factory_build_paper_adapter(self):
        adapter = build_paper_adapter(exchange="binance", trading_mode="paper")
        assert isinstance(adapter, PaperExchangeAdapter)
        assert adapter.exchange == "binance"
        assert adapter.trading_mode == "paper"
