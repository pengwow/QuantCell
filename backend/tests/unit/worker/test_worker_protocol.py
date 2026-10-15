"""Worker 协议测试：旧扁平字段被拒绝 + trading_config 建读往返。

旧协议（exchange/symbols/symbol/timeframe/market_type/trading_mode）会写进没有
对应列的 ORM，造成静默失效；extra="forbid" 让这些字段在请求边界直接 422。
"""

import json

import pytest
from pydantic import ValidationError

from worker import crud, schemas

# WorkerCreate 曾声明过的旧扁平字段
CREATE_FLAT_FIELDS = ["exchange", "symbols", "symbol", "timeframe", "market_type", "trading_mode"]
# WorkerUpdate 曾声明过的旧扁平字段
UPDATE_FLAT_FIELDS = ["exchange", "symbols", "timeframe", "trading_mode"]

TRADING_CONFIG = {
    "exchange": "okx",
    "symbols_config": {"type": "symbols", "symbols": ["ETHUSDT"]},
    "timeframe": "4h",
    "market_type": "futures",
    "trading_mode": "live",
}


@pytest.mark.parametrize("field", CREATE_FLAT_FIELDS)
def test_worker_create_rejects_flat_field(field):
    """WorkerCreate 收到旧扁平字段必须抛 ValidationError（extra=forbid）。"""
    with pytest.raises(ValidationError):
        schemas.WorkerCreate(name="proto-worker", **{field: "x"})


@pytest.mark.parametrize("field", UPDATE_FLAT_FIELDS)
def test_worker_update_rejects_flat_field(field):
    """WorkerUpdate 收到旧扁平字段必须抛 ValidationError（extra=forbid）。"""
    with pytest.raises(ValidationError):
        schemas.WorkerUpdate(**{field: "x"})


def test_worker_create_accepts_trading_config():
    """新协议：trading_config 正常解析。"""
    payload = schemas.WorkerCreate(name="proto-worker", trading_config=TRADING_CONFIG)
    assert payload.trading_config.exchange == "okx"
    assert payload.trading_config.symbols_config.symbols == ["ETHUSDT"]


def test_create_then_read_trading_config_roundtrip(db_session):
    """create_worker 落库后，trading_config 内容与入参一致。"""
    payload = schemas.WorkerCreate(name="proto-roundtrip", trading_config=TRADING_CONFIG)
    worker = crud.create_worker(db_session, payload)
    assert worker.id is not None

    stored = json.loads(worker.trading_config)
    assert stored["exchange"] == "okx"
    assert stored["symbols_config"]["symbols"] == ["ETHUSDT"]
    assert stored["timeframe"] == "4h"
    assert stored["market_type"] == "futures"
    assert stored["trading_mode"] == "live"


def test_worker_create_requires_trading_config():
    """trading_config 必填：缺省应直接 422，而不是静默落库空配置。"""
    with pytest.raises(ValidationError):
        schemas.WorkerCreate(name="no-config")


def test_update_explicit_null_trading_config_is_ignored(db_session):
    """显式传 trading_config=None 视为「不修改」，不得把列置为 NULL。"""
    payload = schemas.WorkerCreate(name="proto-null", trading_config=TRADING_CONFIG)
    worker = crud.create_worker(db_session, payload)
    before = worker.trading_config

    crud.update_worker(db_session, worker.id, schemas.WorkerUpdate(trading_config=None, name="renamed"))
    db_session.refresh(worker)

    assert worker.trading_config == before
    assert worker.name == "renamed"
