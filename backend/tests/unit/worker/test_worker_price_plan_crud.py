"""固化计划存取单测（spec §3：v2 按标的多份存储 + v1 单份兼容）。

只测 crud 口径，存储实现细节（config 键位）通过 roundtrip 断言契约。
"""

import uuid

import pytest

from utils.db_session import get_db_session
from worker import crud

PLAN_BTC = {
    "levels": [{"index": 0, "price": 100.0, "action": "buy", "target_position": 0.1, "label": "入场"}],
    "summary": {"price_min": 100.0, "price_max": 100.0, "entry_price": 100.0, "extra": {}},
    "warnings": [],
}
PLAN_ETH = {
    "levels": [{"index": 1, "price": 2000.0, "action": "buy", "target_position": 0.2, "label": "入场"}],
    "summary": {"price_min": 2000.0, "price_max": 2000.0, "entry_price": 2000.0, "extra": {}},
    "warnings": [],
}


def _fixed_entry(symbol: str, plan: dict, ref_price: float) -> dict:
    """模拟启动链路入口（strategy_manager）组装的固化条目。"""
    return {"symbol": symbol, "state": "fixed", "ref_price": ref_price, "plan": plan, "fixed_at": "2026-11-27T00:00:00"}


@pytest.fixture
def db():
    """与 crud 自持会话同源的会话（DB_FILE 临时库），保证读写在同一个库发生"""
    with get_db_session() as session:
        yield session


@pytest.fixture
def worker_row(db):
    from worker import schemas

    return crud.create_worker(
        db,
        schemas.WorkerCreate(
            name=f"price-plan-{uuid.uuid4().hex[:8]}",
            strategy_name="grid",
            trading_config=schemas.TradingConfig(symbols_config=schemas.SymbolsConfig(symbols=["BTCUSDT", "ETHUSDT"])),
        ),
    )


def _stored_price_plan(worker_id) -> dict:
    """直达 DB 读 config['price_plan'] 原始结构（roundtrip 契约断言用）。

    自持新会话：save 用自持会话提交，fixture 会话已开启的事务快照读不到外部提交。
    """
    from worker.models import Worker

    with get_db_session() as session:
        worker = session.query(Worker).filter(Worker.id == int(worker_id)).first()
        return worker.get_config_dict().get("price_plan") or {}


def test_roundtrip_v2_structure_and_order(db, worker_row):
    """多标的写入 → config 读回 v2 结构；plans 键顺序 = 写入顺序（存取不重排）"""
    crud.save_worker_price_plans(
        str(worker_row.id),
        {"BTCUSDT": _fixed_entry("BTCUSDT", PLAN_BTC, 100.0), "ETHUSDT": _fixed_entry("ETHUSDT", PLAN_ETH, 2000.0)},
    )
    stored = _stored_price_plan(worker_row.id)
    assert stored["version"] == 2
    assert list(stored["plans"].keys()) == ["BTCUSDT", "ETHUSDT"]
    assert stored["plans"]["BTCUSDT"]["plan"]["summary"]["entry_price"] == 100.0

    entry, symbols_states = crud.get_worker_price_plan(str(worker_row.id))
    assert [s["symbol"] for s in symbols_states] == ["BTCUSDT", "ETHUSDT"]
    assert entry["state"] == "fixed" and entry["symbol"] == "BTCUSDT"  # 缺省取第一个


def test_v2_query_specific_symbol(db, worker_row):
    """v2 指定 symbol：返回该标的的固化 entry"""
    crud.save_worker_price_plans(
        str(worker_row.id),
        {"BTCUSDT": _fixed_entry("BTCUSDT", PLAN_BTC, 100.0), "ETHUSDT": _fixed_entry("ETHUSDT", PLAN_ETH, 2000.0)},
    )
    entry, _ = crud.get_worker_price_plan(str(worker_row.id), "ETHUSDT")
    assert entry["symbol"] == "ETHUSDT"
    assert entry["ref_price"] == 2000.0
    assert entry["plan"]["summary"]["entry_price"] == 2000.0


def test_v2_unfixed_symbol_returns_pending(db, worker_row):
    """v2 未固化标的：返回 pending 占位且无 plan"""
    crud.save_worker_price_plans(str(worker_row.id), {"BTCUSDT": _fixed_entry("BTCUSDT", PLAN_BTC, 100.0)})
    entry, symbols_states = crud.get_worker_price_plan(str(worker_row.id), "LTCUSDT")
    assert entry == {"symbol": "LTCUSDT", "state": "pending"}
    assert entry.get("plan") is None
    # LTCUSDT 未在 plans 里，不进 symbols_states
    assert [s["symbol"] for s in symbols_states] == ["BTCUSDT"]


def test_v1_legacy_structure_compat(db, worker_row):
    """v1 单份旧结构：缺省读取返回该份（补 symbol），其他标的 pending"""
    legacy = {"state": "fixed", "ref_price": 100.0, "plan": PLAN_BTC, "fixed_at": "2026-11-26T00:00:00"}
    crud.update_worker_config(db, int(worker_row.id), {"price_plan": legacy})

    entry, symbols_states = crud.get_worker_price_plan(str(worker_row.id))
    assert entry["state"] == "fixed" and entry["ref_price"] == 100.0
    assert entry["symbol"] == "BTCUSDT"  # 首标的由 worker 标的列表推导补齐
    assert symbols_states == [{"symbol": "BTCUSDT", "state": "fixed"}]

    other, _ = crud.get_worker_price_plan(str(worker_row.id), "LTCUSDT")
    assert other == {"symbol": "LTCUSDT", "state": "pending"}


def test_save_none_value_writes_pending_placeholder(db, worker_row):
    """plans 值为 None → 写 pending 占位（而非漏写，详情页 chips 需要完整标的表）"""
    crud.save_worker_price_plans(
        str(worker_row.id), {"BTCUSDT": _fixed_entry("BTCUSDT", PLAN_BTC, 100.0), "ETHUSDT": None}
    )
    stored = _stored_price_plan(worker_row.id)
    assert stored["plans"]["ETHUSDT"] == {"symbol": "ETHUSDT", "state": "pending"}

    entry, symbols_states = crud.get_worker_price_plan(str(worker_row.id), "ETHUSDT")
    assert entry["state"] == "pending" and "plan" not in entry
    assert [s["state"] for s in symbols_states] == ["fixed", "pending"]


def test_old_single_symbol_saver_removed():
    """旧单份写入函数必须删除：防止新旧两套写入结构并存互相覆写"""
    assert not hasattr(crud, "save_worker_price_plan")
    assert not hasattr(crud, "_price_plan_entry")


def test_missing_worker_or_never_fixed(db):
    """worker 不存在 / 从未固化 → (None, [])"""
    assert crud.get_worker_price_plan("no-such-worker") == (None, [])

    from worker import schemas

    fresh = crud.create_worker(
        db,
        schemas.WorkerCreate(
            name=f"price-plan-fresh-{uuid.uuid4().hex[:8]}",
            strategy_name="grid",
            trading_config=schemas.TradingConfig(symbols_config=schemas.SymbolsConfig(symbols=["BTCUSDT"])),
        ),
    )
    assert crud.get_worker_price_plan(str(fresh.id)) == (None, [])
