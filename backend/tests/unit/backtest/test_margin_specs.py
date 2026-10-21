"""档位数据三级回退（DB → 内置快照 → 默认档位）与杠杆上限校验单测。"""

import pytest

from backtest import margin_specs
from backtest.margin_specs import DEFAULT_BRACKETS, build_margin_specs


def _brackets(mmr: float = 0.004, max_leverage: float = 125.0) -> list[dict]:
    return [
        {
            "notional_floor": 0.0,
            "notional_cap": None,
            "mmr": mmr,
            "cum": 0.0,
            "liquidation_fee_rate": 0.001,
            "max_leverage": max_leverage,
        }
    ]


def _patch_no_source(monkeypatch) -> None:
    """DB 与快照都缺失"""
    monkeypatch.setattr(margin_specs, "_load_from_db", lambda symbol: None)
    monkeypatch.setattr(margin_specs, "_load_from_snapshot", lambda symbol: None)


def test_fallback_to_default_when_no_data(monkeypatch):
    _patch_no_source(monkeypatch)
    specs = build_margin_specs([("BTCUSDT", 20.0, "cross")])
    assert specs["BTC/USDT"]["leverage"] == 20.0
    assert specs["BTC/USDT"]["mode"] == "cross"
    assert specs["BTC/USDT"]["brackets"] == DEFAULT_BRACKETS


def test_leverage_above_symbol_cap_rejected(monkeypatch):
    monkeypatch.setattr(
        margin_specs,
        "_load_from_db",
        lambda symbol: _brackets(mmr=0.01, max_leverage=5.0),
    )
    with pytest.raises(ValueError, match=r"BTCUSDT.*最高 5"):
        build_margin_specs([("BTCUSDT", 20.0, "cross")])


def test_symbol_normalized_to_instrument_key(monkeypatch):
    _patch_no_source(monkeypatch)
    specs = build_margin_specs([("ETHUSDT", 3.0, "isolated")])
    assert "ETH/USDT" in specs
    assert specs["ETH/USDT"]["mode"] == "isolated"


def test_db_takes_precedence_over_snapshot(monkeypatch):
    db_brackets = _brackets(mmr=0.004)
    snapshot_brackets = _brackets(mmr=0.006)
    monkeypatch.setattr(margin_specs, "_load_from_db", lambda symbol: db_brackets)
    monkeypatch.setattr(margin_specs, "_load_from_snapshot", lambda symbol: snapshot_brackets)

    specs = build_margin_specs([("BTCUSDT", 5.0, "cross")])
    assert specs["BTC/USDT"]["brackets"] is db_brackets


def test_snapshot_used_when_db_missing(monkeypatch):
    snapshot_brackets = _brackets(mmr=0.006, max_leverage=75.0)
    monkeypatch.setattr(margin_specs, "_load_from_db", lambda symbol: None)
    monkeypatch.setattr(margin_specs, "_load_from_snapshot", lambda symbol: snapshot_brackets)

    specs = build_margin_specs([("BTCUSDT", 20.0, "cross")])
    assert specs["BTC/USDT"]["brackets"] is snapshot_brackets


def test_load_from_db_is_safe_without_initialized_db(monkeypatch):
    """DB 未初始化（表不存在）时不能把回测带崩，必须安全降级返回 None"""
    import collector.db.database as db_module

    def _raise_not_initialized():
        raise RuntimeError("数据库未初始化")

    monkeypatch.setattr(db_module, "init_database_config", _raise_not_initialized)
    assert margin_specs._load_from_db("BTCUSDT") is None
