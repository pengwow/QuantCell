"""LiveTradeSync 最小自检：ccxt 符号推导 + trade 字段映射（纯逻辑，无网络/DB）。"""

from datetime import datetime

from worker.live_trade_sync import LiveTradeSync


def _make_sync() -> LiveTradeSync:
    # 构造不联网：ccxt 实例纯对象装配（credentials 为假值，不发起请求）
    return LiveTradeSync(worker_id=7, api_key="k", api_secret="s", symbol="BTC/USDT")


def test_ccxt_symbol_suffix_and_since():
    s = _make_sync()
    assert s._ccxt_symbol == "BTC/USDT:USDT"
    assert s._since > 0
    # DB symbol 口径与 LiveTradeRecorder（instrument_id）一致
    assert s.symbol == "BTC/USDT"


def test_to_trade_data_mapping():
    s = _make_sync()
    trade = {
        "id": "373270969",
        "side": "buy",
        "amount": 0.5,
        "price": 60000.0,
        "timestamp": 1750000000000,
        "fee": {"cost": 0.03, "currency": "USDT"},
        "info": {"realizedPnl": "12.5"},
    }
    d = s._to_trade_data(trade)
    assert d["worker_id"] == 7
    assert d["trade_id"] == "373270969"
    assert d["symbol"] == "BTC/USDT"
    assert d["side"] == "buy"
    assert d["order_type"] == "MARKET"
    assert d["quantity"] == 0.5
    assert d["price"] == 60000.0
    assert d["amount"] == 30000.0
    assert d["fee"] == 0.03
    assert d["fee_currency"] == "USDT"
    assert d["realized_pnl"] == 12.5
    assert d["realized_pnl_pct"] is None
    assert d["entry_time"] == datetime.fromtimestamp(1750000000)
    assert d["exit_time"] is None


def test_to_trade_data_missing_fields():
    s = _make_sync()
    d = s._to_trade_data({"id": "1"})
    assert d["order_type"] == "MARKET"
    assert d["fee"] == 0.0
    assert d["fee_currency"] == "USDT"
    assert d["realized_pnl"] is None
    assert d["entry_time"] is None


def test_to_trade_data_bad_realized_pnl():
    s = _make_sync()
    d = s._to_trade_data({"id": "2", "info": {"realizedPnl": "abc"}})
    assert d["realized_pnl"] is None
