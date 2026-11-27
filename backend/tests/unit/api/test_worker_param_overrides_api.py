"""/workers/{id}/strategy/param-overrides + 参数通道统一（spec §3.3/§8 D5）"""

import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from utils.db_session import get_db_session
from worker import crud as worker_crud

client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")


@pytest.fixture
def db():
    with get_db_session() as session:
        yield session


@pytest.fixture
def worker_row(db):
    from worker import schemas

    return worker_crud.create_worker(
        db,
        schemas.WorkerCreate(
            name=f"param-ov-{uuid.uuid4().hex[:8]}",
            strategy_name="grid",
            trading_config=schemas.TradingConfig(symbols_config=schemas.SymbolsConfig(symbols=["BTCUSDT", "ETHUSDT"])),
        ),
    )


def test_param_overrides_roundtrip_normalizes_keys(db, worker_row):
    r = client.put(
        f"/api/v1/workers/{worker_row.id}/strategy/param-overrides",
        json={"overrides": {"BTCUSDT": {"lower": 100.0, "empty": None}, "ETHUSDT": {}}},
    )
    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/v1/workers/{worker_row.id}/strategy/param-overrides")
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert data["BTC/USDT"] == {"lower": 100.0, "empty": None}  # 键已规范化；None 原样保留（读取端过滤）


def test_update_worker_does_not_wipe_strategy_params(db, worker_row):
    """D5 存量 bug：PUT /workers/{id} 只提交部分 config，不得清掉已有参数"""
    worker_crud.update_worker_config(db, int(worker_row.id), {"strategy_params": {"levels": 20}})
    from worker import schemas

    worker_crud.update_worker(
        db, int(worker_row.id), schemas.WorkerUpdate(name="renamed", config={"initial_capital": 20000})
    )
    from worker.models import Worker

    row = db.query(Worker).filter(Worker.id == worker_row.id).first()
    config = row.get_config_dict()
    assert config["strategy_params"] == {"levels": 20}  # 合并写，未被整体替换
    assert config["initial_capital"] == 20000


def test_put_parameters_writes_config_strategy_params(db, worker_row):
    """D5：PUT strategy/parameters 落 config.strategy_params（启动链路的事实源）"""
    r = client.put(
        f"/api/v1/workers/{worker_row.id}/strategy/parameters",
        json={"parameters": {"levels": 7}},
    )
    assert r.status_code == 200, r.text
    from worker.models import Worker

    row = db.query(Worker).filter(Worker.id == worker_row.id).first()
    # HTTP 写走路由内另一个 session，本 session 的 identity map 仍缓存创建时的旧对象；
    # expire_all 强制重读 DB，才能验证写入已落库
    db.expire_all()
    assert row.get_config_dict()["strategy_params"] == {"levels": 7}
