"""services 层各 axon_quant 包装器的单测。

覆盖 OMS / Compliance / Explain / Data 四个服务的：
- AXON_AVAILABLE 门控（可用构造 Mock 引擎、不可用抛 RuntimeError）
- 内部对 _OrderManager/_ComplianceModule/_DataService 的委托
- 各 Proxy 在 axon 不可用时的降级默认值
- Proxy 构造失败时自动降级（Compliance / Data）

所有第三方 IO 均通过 monkeypatch 替换为伪实现，不发起任何真实调用。
"""

from unittest import mock

import pytest

from services import compliance_service as compliance_mod
from services import data_service as data_mod
from services import explain_service as explain_mod
from services import oms_service as oms_mod
from services.compliance_service import ComplianceServiceProxy, ComplianceServiceWrapper
from services.data_service import DataServiceProxy, DataServiceWrapper
from services.explain_service import ExplainServiceWrapper
from services.oms_service import OMSService, OMSServiceProxy


# --------------------------------------------------------------------------- #
# 通用伪枚举，用于验证模块内 _Side/_OrderType/_TradeStatus/_Frequency 的取值
# --------------------------------------------------------------------------- #
class _FakeSide:
    BUY = "BUY"
    SELL = "SELL"


class _FakeOrderType:
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class _FakeTradeSide:
    BUY = "BUY"
    SELL = "SELL"


class _FakeComplianceOrderType:
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class _FakeTradeStatus:
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class _FakeTradeRecord:
    """记录构造参数的 TradeRecord 替身。"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeFrequency:
    Tick = "Tick"
    Min1 = "Min1"
    Min5 = "Min5"
    Min15 = "Min15"
    Min30 = "Min30"
    Hour1 = "Hour1"
    Hour4 = "Hour4"
    Day1 = "Day1"
    Week1 = "Week1"
    Month1 = "Month1"


class _FakeDataRequest:
    """记录构造参数的 DataRequest 替身。"""

    last = None

    def __init__(self, symbol, start, end, freq):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.freq = freq
        _FakeDataRequest.last = self


class _CaptureDataService:
    """记录 new().with_cache_capacity() 调用链的 DataService 替身。"""

    def __init__(self):
        self.cache_cap = None

    @classmethod
    def new(cls):
        return cls()

    def with_cache_capacity(self, cap):
        self.cache_cap = cap
        return self


# --------------------------------------------------------------------------- #
# OMS (services/oms_service.py)
# --------------------------------------------------------------------------- #


def _oms_available_context(monkeypatch, manager: mock.MagicMock) -> None:
    """把 oms 模块注入到“可用”路径：AXON_AVAILABLE=True + fake 引擎。"""
    monkeypatch.setattr(oms_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(oms_mod, "_OrderManager", mock.MagicMock(return_value=manager))
    monkeypatch.setattr(oms_mod, "_Side", _FakeSide)
    monkeypatch.setattr(oms_mod, "_OrderType", _FakeOrderType)
    monkeypatch.setattr(oms_mod, "_Order", mock.MagicMock())


def test_oms_init_available_creates_manager(monkeypatch):
    manager = mock.MagicMock()
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    oms_mod._OrderManager.assert_called_once_with()
    assert svc._manager is manager


def test_oms_init_unavailable_raises(monkeypatch):
    monkeypatch.setattr(oms_mod, "AXON_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        OMSService()


def test_oms_submit_order_builds_order_and_returns_id(monkeypatch):
    manager = mock.MagicMock()
    manager.submit.return_value = "oid-1"
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    oid = svc.submit_order({"symbol": "BTCUSDT", "side": "Buy", "type": "limit", "quantity": 0.1, "price": 50000.0})
    assert oid == "oid-1"
    oms_mod._Order.assert_called_once_with(
        symbol="BTCUSDT",
        side=_FakeSide.BUY,
        order_type=_FakeOrderType.LIMIT,
        quantity=0.1,
        price=50000.0,
    )
    manager.submit.assert_called_once_with(oms_mod._Order.return_value)


def test_oms_submit_order_maps_sell_market(monkeypatch):
    manager = mock.MagicMock()
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    svc.submit_order({"symbol": "ETHUSDT", "side": "Sell", "type": "market", "quantity": 2.0, "price": 0.0})
    oms_mod._Order.assert_called_once_with(
        symbol="ETHUSDT",
        side=_FakeSide.SELL,
        order_type=_FakeOrderType.MARKET,
        quantity=2.0,
        price=0.0,
    )


def test_oms_cancel_order_success(monkeypatch):
    manager = mock.MagicMock()
    manager.cancel.return_value = True
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    assert svc.cancel_order("O1") is True
    manager.cancel.assert_called_once_with("O1")


def test_oms_cancel_order_failure(monkeypatch):
    manager = mock.MagicMock()
    manager.cancel.return_value = False
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    assert svc.cancel_order("O1") is False


def test_oms_get_order_status_returns_value(monkeypatch):
    manager = mock.MagicMock()
    manager.get_order_status.return_value = {"order_id": "O1", "status": "Filled"}
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    assert svc.get_order_status("O1") == {"order_id": "O1", "status": "Filled"}
    manager.get_order_status.assert_called_once_with("O1")


def test_oms_get_order_status_swallows_exception_and_logs(monkeypatch):
    manager = mock.MagicMock()
    manager.get_order_status.side_effect = RuntimeError("engine exploded")
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    with mock.patch.object(oms_mod.logger, "error") as mock_err:
        result = svc.get_order_status("O1")
    assert result is None
    mock_err.assert_called_once()


def test_oms_snapshot_and_parts_forward(monkeypatch):
    manager = mock.MagicMock()
    manager.snapshot.return_value = {"orders": []}
    manager.snapshot_balance.return_value = {"USDT": 100.0}
    manager.snapshot_positions.return_value = {"BTCUSDT": 1.0}
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    assert svc.snapshot() == {"orders": []}
    assert svc.snapshot_balance() == {"USDT": 100.0}
    assert svc.snapshot_positions() == {"BTCUSDT": 1.0}


def test_oms_counts_forward(monkeypatch):
    manager = mock.MagicMock()
    manager.active_count.return_value = 3
    manager.history_count.return_value = 9
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    assert svc.active_count() == 3
    assert svc.history_count() == 9


def test_oms_deposit_forward(monkeypatch):
    manager = mock.MagicMock()
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    svc.deposit("USDT", 500.0)
    manager.deposit.assert_called_once_with("USDT", 500.0)


def test_oms_add_fill_forward(monkeypatch):
    manager = mock.MagicMock()
    _oms_available_context(monkeypatch, manager)
    svc = OMSService()
    svc.add_fill("O1", "F1", "BTCUSDT", 90000.0, 0.5, 1.5)
    manager.add_fill.assert_called_once_with("O1", "F1", "BTCUSDT", 90000.0, 0.5, 1.5, None)


def test_oms_proxy_unavailable_defaults(monkeypatch):
    monkeypatch.setattr(oms_mod, "AXON_AVAILABLE", False)
    proxy = OMSServiceProxy()
    assert proxy.available is False
    assert proxy._service is None
    assert proxy.submit_order({"symbol": "BTCUSDT"}) == ""
    assert proxy.cancel_order("O1") is False
    assert proxy.get_order_status("O1") is None
    assert proxy.snapshot() == {}
    assert proxy.snapshot_balance() == {}
    assert proxy.snapshot_positions() == {}
    assert proxy.active_count() == 0
    assert proxy.history_count() == 0
    assert proxy.deposit("USDT", 100.0) is None
    assert proxy.add_fill("O1", "F1", "BTCUSDT", 1.0, 1.0, 0.0) is None


def test_oms_proxy_available_forwards(monkeypatch):
    manager = mock.MagicMock()
    manager.submit.return_value = "oid-ok"
    manager.get_order_status.return_value = {"order_id": "O1", "status": "Filled"}
    _oms_available_context(monkeypatch, manager)
    proxy = OMSServiceProxy()
    assert proxy.available is True
    assert (
        proxy.submit_order({"symbol": "BTCUSDT", "side": "Buy", "type": "limit", "quantity": 0.1, "price": 1.0})
        == "oid-ok"
    )
    manager.cancel.return_value = True
    assert proxy.cancel_order("O1") is True
    assert proxy.get_order_status("O1") == {"order_id": "O1", "status": "Filled"}
    proxy.deposit("USDT", 1.0)
    manager.deposit.assert_called_once_with("USDT", 1.0)


# --------------------------------------------------------------------------- #
# Compliance (services/compliance_service.py)
# --------------------------------------------------------------------------- #


def _compliance_available_context(monkeypatch, module, config_cls):
    """把 compliance 模块注入可用路径，返回 wrapper。"""
    monkeypatch.setattr(compliance_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(compliance_mod, "_ComplianceModule", mock.MagicMock(return_value=module))
    monkeypatch.setattr(compliance_mod, "_ComplianceConfig", config_cls)
    return ComplianceServiceWrapper()


def test_compliance_init_available_creates_module(monkeypatch):
    module = mock.MagicMock()
    config_cls = mock.MagicMock()
    _compliance_available_context(monkeypatch, module, config_cls)
    config_cls.assert_called_once_with()
    compliance_mod._ComplianceModule.assert_called_once_with(config_cls.return_value)


def test_compliance_init_with_custom_config(monkeypatch):
    module = mock.MagicMock()
    config_cls = mock.MagicMock()
    monkeypatch.setattr(compliance_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(compliance_mod, "_ComplianceModule", mock.MagicMock(return_value=module))
    monkeypatch.setattr(compliance_mod, "_ComplianceConfig", config_cls)
    ComplianceServiceWrapper({"max_trade_value": 500000.0})
    config_cls.assert_called_once_with(max_trade_value=500000.0)


def test_compliance_init_unavailable_raises(monkeypatch):
    monkeypatch.setattr(compliance_mod, "AXON_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        ComplianceServiceWrapper()


def test_compliance_create_trade_record_maps_side_order_type(monkeypatch):
    monkeypatch.setattr(compliance_mod, "_TradeSide", _FakeTradeSide)
    monkeypatch.setattr(compliance_mod, "_OrderType", _FakeComplianceOrderType)
    monkeypatch.setattr(compliance_mod, "_TradeStatus", _FakeTradeStatus)
    monkeypatch.setattr(compliance_mod, "_TradeRecord", _FakeTradeRecord)
    svc = _compliance_available_context(monkeypatch, mock.MagicMock(), mock.MagicMock())

    rec = svc.create_trade_record("T1", "BTCUSDT", "Sell", "Market", 50000.0, 0.1)
    assert rec.trade_id == "T1"
    assert rec.symbol == "BTCUSDT"
    assert rec.side == _FakeTradeSide.SELL
    assert rec.order_type == _FakeComplianceOrderType.MARKET
    assert rec.status == _FakeTradeStatus.FILLED
    assert rec.price == 50000.0
    assert rec.quantity == 0.1


def test_compliance_create_trade_record_status_getattr_fallback(monkeypatch):
    monkeypatch.setattr(compliance_mod, "_TradeSide", _FakeTradeSide)
    monkeypatch.setattr(compliance_mod, "_OrderType", _FakeComplianceOrderType)
    monkeypatch.setattr(compliance_mod, "_TradeStatus", _FakeTradeStatus)
    monkeypatch.setattr(compliance_mod, "_TradeRecord", _FakeTradeRecord)
    svc = _compliance_available_context(monkeypatch, mock.MagicMock(), mock.MagicMock())
    rec_cancelled = svc.create_trade_record("T1", "BTCUSDT", "Buy", "Limit", 1.0, 1.0, status="Cancelled")
    assert rec_cancelled.status == _FakeTradeStatus.CANCELLED
    rec_unknown = svc.create_trade_record("T2", "BTCUSDT", "Buy", "Limit", 1.0, 1.0, status="BogusStatus")
    assert rec_unknown.status == _FakeTradeStatus.FILLED


def test_compliance_log_trade_and_get_audit_trail(monkeypatch):
    module = mock.MagicMock()
    module.get_audit_trail.return_value = [{"trade_id": "T1"}]
    svc = _compliance_available_context(monkeypatch, module, mock.MagicMock())
    record = mock.MagicMock(trade_id="T1")
    svc.log_trade(record)
    module.log_trade.assert_called_once_with(record)
    assert svc.get_audit_trail() == [{"trade_id": "T1"}]


def test_compliance_proxy_unavailable_defaults(monkeypatch):
    monkeypatch.setattr(compliance_mod, "AXON_AVAILABLE", False)
    proxy = ComplianceServiceProxy()
    assert proxy.available is False
    assert proxy.create_trade_record("T1", "BTCUSDT", "Buy", "Limit", 1.0, 1.0) is None
    assert proxy.log_trade(object()) is None
    assert proxy.get_audit_trail() == []


def test_compliance_proxy_wrapper_creation_failure_degrades(monkeypatch):
    class _BoomWrapper:
        def __init__(self, config=None):
            raise RuntimeError("engine init failed")

    monkeypatch.setattr(compliance_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(compliance_mod, "ComplianceServiceWrapper", _BoomWrapper)
    with mock.patch.object(compliance_mod.logger, "error") as mock_err:
        proxy = ComplianceServiceProxy()
    assert proxy.available is False
    assert proxy._service is None
    assert proxy.create_trade_record("T1", "BTCUSDT", "Buy", "Limit", 1.0, 1.0) is None
    assert proxy.get_audit_trail() == []
    mock_err.assert_called_once()


def test_compliance_proxy_available_forwards(monkeypatch):
    class _FakeWrapper:
        def __init__(self, config=None):
            self.logged = []

        def create_trade_record(self, *args, **kwargs):
            return "REC-T1"

        def log_trade(self, record):
            self.logged.append(record)

        def get_audit_trail(self):
            return ["audit1"]

    monkeypatch.setattr(compliance_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(compliance_mod, "ComplianceServiceWrapper", _FakeWrapper)
    proxy = ComplianceServiceProxy()
    assert proxy.available is True
    assert proxy.create_trade_record("T1", "BTCUSDT", "Buy", "Limit", 1.0, 1.0) == "REC-T1"
    proxy.log_trade("r1")
    assert proxy._service.logged == ["r1"]
    assert proxy.get_audit_trail() == ["audit1"]


# --------------------------------------------------------------------------- #
# Explain (services/explain_service.py)
# --------------------------------------------------------------------------- #


def test_explain_init_unavailable_raises(monkeypatch):
    monkeypatch.setattr(explain_mod, "AXON_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        ExplainServiceWrapper()


def test_explain_init_available_ok(monkeypatch):
    monkeypatch.setattr(explain_mod, "AXON_AVAILABLE", True)
    assert ExplainServiceWrapper() is not None


def test_explain_prediction_returns_not_implemented(monkeypatch):
    monkeypatch.setattr(explain_mod, "AXON_AVAILABLE", True)
    svc = ExplainServiceWrapper()
    assert svc.explain_prediction(model=None, observation=None) == {"status": "not_implemented"}


# --------------------------------------------------------------------------- #
# Data (services/data_service.py)
# --------------------------------------------------------------------------- #


def test_data_init_default_cache_capacity(monkeypatch):
    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(data_mod, "_DataService", _CaptureDataService)
    svc = DataServiceWrapper()
    assert svc._service.cache_cap == 64


def test_data_init_custom_cache_capacity(monkeypatch):
    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(data_mod, "_DataService", _CaptureDataService)
    svc = DataServiceWrapper(cache_capacity=512)
    assert svc._service.cache_cap == 512


def test_data_init_unavailable_raises(monkeypatch):
    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        DataServiceWrapper()


def test_data_load_maps_frequency_and_returns_dataset(monkeypatch):
    dataset = mock.MagicMock()
    dataset.len = 123
    engine = mock.MagicMock()
    engine.new.return_value = engine
    engine.with_cache_capacity.return_value = engine
    engine.load.return_value = dataset
    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(data_mod, "_DataService", engine)
    monkeypatch.setattr(data_mod, "_Frequency", _FakeFrequency)
    monkeypatch.setattr(data_mod, "_DataRequest", _FakeDataRequest)
    _FakeDataRequest.last = None

    svc = DataServiceWrapper()
    result = svc.load("BTCUSDT", 100, 200, "Min5")
    assert result is dataset
    req = _FakeDataRequest.last
    assert req.symbol == "BTCUSDT"
    assert req.start == 100
    assert req.end == 200
    assert req.freq is _FakeFrequency.Min5


def test_data_load_unknown_frequency_falls_back_hour1(monkeypatch):
    dataset = mock.MagicMock()
    engine = mock.MagicMock()
    engine.new.return_value = engine
    engine.with_cache_capacity.return_value = engine
    engine.load.return_value = dataset
    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(data_mod, "_DataService", engine)
    monkeypatch.setattr(data_mod, "_Frequency", _FakeFrequency)
    monkeypatch.setattr(data_mod, "_DataRequest", _FakeDataRequest)
    _FakeDataRequest.last = None

    svc = DataServiceWrapper()
    svc.load("BTCUSDT", 100, 200, "Y2Y")
    assert _FakeDataRequest.last.freq is _FakeFrequency.Hour1


def test_data_proxy_unavailable_defaults(monkeypatch):
    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", False)
    proxy = DataServiceProxy()
    assert proxy.available is False
    assert proxy.load("BTCUSDT", 0, 1) is None
    assert proxy.stream("src", None) is None
    assert proxy.cache_stats() == {}
    assert proxy.cache_control() is None
    assert proxy.register_mock_source("n", 100, 1, lambda i: 1.0) is None
    assert proxy.register_source(object()) is None


def test_data_proxy_wrapper_creation_failure_degrades(monkeypatch):
    class _BoomWrapper:
        def __init__(self, cache_capacity=64):
            raise RuntimeError("engine init failed")

    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(data_mod, "DataServiceWrapper", _BoomWrapper)
    with mock.patch.object(data_mod.logger, "error") as mock_err:
        proxy = DataServiceProxy()
    assert proxy.available is False
    assert proxy._service is None
    assert proxy.load("BTCUSDT", 100, 200) is None
    assert proxy.cache_stats() == {}
    mock_err.assert_called_once()


def test_data_proxy_available_forwards(monkeypatch):
    class _FakeWrapper:
        def __init__(self, cache_capacity=64):
            self.cache_capacity = cache_capacity
            self.load_calls = []

        def register_mock_source(self, *args, **kwargs):
            pass

        def register_source(self, *args, **kwargs):
            pass

        def load(self, symbol, start, end, frequency="Hour1"):
            self.load_calls.append((symbol, start, end, frequency))
            return "dataset"

        def stream(self, *args, **kwargs):
            return "stream"

        def cache_stats(self):
            return {"hits": 3}

        def cache_control(self):
            return "controller"

    monkeypatch.setattr(data_mod, "AXON_AVAILABLE", True)
    monkeypatch.setattr(data_mod, "DataServiceWrapper", _FakeWrapper)
    proxy = DataServiceProxy(cache_capacity=128)
    assert proxy.available is True
    assert proxy.load("BTCUSDT", 100, 200) == "dataset"
    assert proxy._service.load_calls == [("BTCUSDT", 100, 200, "Hour1")]
    assert proxy.stream("src", None) == "stream"
    assert proxy.cache_stats() == {"hits": 3}
    assert proxy.cache_control() == "controller"
    assert proxy._service.cache_capacity == 128
