"""P2-03 标的池验收：CRUD、成分历史留痕、快照、backtest/factor 标的来源二选一。

沿用 worker 对账测试的会话替身模式：tmp_path 文件库 + monkeypatch 服务层
get_db_session，验证真实 SQL 行为（去重、留痕、级联清理）。
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import universe.service as svc
from backtest.schemas import BacktestConfig
from factor.schemas import FactorCalculateBase
from universe.models import Universe, UniverseMembership, UniverseSnapshot
from universe.schemas import UniverseUpdateRequest
from universe.service import DuplicateUniverseError, UniverseNotFoundError


class _Ctx:
    """get_db_session 上下文替身：共享同一个 session，异常时回滚。"""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        if exc is not None:
            self.session.rollback()
        return False


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    from collector.db.database import Base, _import_all_models

    # workers 等表带跨模块 FK，create_all 前必须注册全部模型
    _import_all_models()
    engine = create_engine(f"sqlite:///{tmp_path}/universe.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(svc, "get_db_session", lambda: _Ctx(session))
    yield session
    session.close()


def test_create_with_members_and_baseline_snapshot(db_session):
    """建池：成分归一化去重入池 + 基线快照 + 列表计数。"""
    u = svc.create_universe("主流币", symbols=[" btc/usdt ", "ETHUSDT", " btc/usdt ", "ethusdt"], owner_id=7)
    assert u["members"] == ["BTC/USDT", "ETHUSDT"]
    assert u["member_count"] == 2 and u["owner_id"] == 7

    detail = svc.get_universe(u["id"])
    assert detail["name"] == "主流币" and detail["members"] == ["BTC/USDT", "ETHUSDT"]

    rows = svc.list_universes()
    assert len(rows) == 1 and rows[0]["member_count"] == 2

    snapshots = svc.list_snapshots(u["id"])
    assert len(snapshots) == 1
    assert snapshots[0]["symbols"] == ["BTC/USDT", "ETHUSDT"]


def test_create_duplicate_name(db_session):
    svc.create_universe("趋势币")
    with pytest.raises(DuplicateUniverseError):
        svc.create_universe("趋势币")


def test_empty_pool_resolve_returns_empty(db_session):
    """空池可建（成分后续再补），resolve 返回空列表由调用方决定如何报错。"""
    u = svc.create_universe("空池")
    assert svc.resolve_universe_symbols(u["id"]) == []
    assert svc.get_universe(u["id"])["member_count"] == 0


def test_add_members_dedup_and_snapshot(db_session):
    u = svc.create_universe("池", symbols=["ETHUSDT"])
    out = svc.add_members(u["id"], ["ETHUSDT", "BTCUSDT", " btcusdt "])
    assert out["added"] == 1
    assert out["members"] == ["ETHUSDT", "BTCUSDT"]  # 新增按入池顺序追加

    snapshots = svc.list_snapshots(u["id"])
    assert len(snapshots) == 2  # 基线 + 变更
    assert snapshots[0]["symbols"] == ["ETHUSDT", "BTCUSDT"]  # 倒序，最新在前


def test_remove_members_keeps_history(db_session):
    u = svc.create_universe("池", symbols=["BTCUSDT", "ETHUSDT", "XRPUSDT"])
    out = svc.remove_members(u["id"], ["BTCUSDT"])
    assert out["removed"] == 1 and out["members"] == ["ETHUSDT", "XRPUSDT"]

    # 留痕：membership 记录仍在，included_until 被置位
    rows = db_session.query(UniverseMembership).filter_by(universe_id=u["id"]).all()
    assert len(rows) == 3
    assert {r.symbol for r in rows if r.included_until is None} == {"ETHUSDT", "XRPUSDT"}

    assert svc.resolve_universe_symbols(u["id"]) == ["ETHUSDT", "XRPUSDT"]
    assert svc.list_snapshots(u["id"])[0]["symbols"] == ["ETHUSDT", "XRPUSDT"]

    # 再移出非成员：removed=0，且不追加快照
    out2 = svc.remove_members(u["id"], ["SOLUSDT"])
    assert out2["removed"] == 0 and len(svc.list_snapshots(u["id"])) == 2


def test_resolve_not_found(db_session):
    with pytest.raises(UniverseNotFoundError):
        svc.resolve_universe_symbols(999)
    with pytest.raises(UniverseNotFoundError):
        svc.get_universe(999)


def test_update_universe(db_session):
    u1 = svc.create_universe("A", description="desc")
    u2 = svc.create_universe("B")

    out = svc.update_universe(u1["id"], name="A2", description="新描述")
    assert out["name"] == "A2" and out["description"] == "新描述"

    # 改名撞名 → 409
    with pytest.raises(DuplicateUniverseError):
        svc.update_universe(u2["id"], name="A2")

    # 更新请求至少一项（schema 层）
    with pytest.raises(ValidationError):
        UniverseUpdateRequest()


def test_delete_universe_cascades(db_session):
    u = svc.create_universe("短命池", symbols=["BTCUSDT"])
    svc.add_members(u["id"], ["ETHUSDT"])
    svc.delete_universe(u["id"])

    assert db_session.query(Universe).count() == 0
    assert db_session.query(UniverseMembership).count() == 0
    assert db_session.query(UniverseSnapshot).count() == 0
    with pytest.raises(UniverseNotFoundError):
        svc.get_universe(u["id"])


def test_backtest_config_symbols_or_universe():
    """BacktestConfig：symbols 与 universe_id 二选一（schema 入口把关）。"""
    base = dict(start_time="2024-01-01", end_time="2024-02-01")

    both = {**base, "symbols": ["BTCUSDT"], "universe_id": 1}
    with pytest.raises(ValidationError):
        BacktestConfig(**both)

    neither = {**base}
    with pytest.raises(ValidationError):
        BacktestConfig(**neither)

    assert BacktestConfig(**{**base, "symbols": ["BTCUSDT"]}).universe_id is None
    assert BacktestConfig(**{**base, "universe_id": 3}).symbols == []


def test_factor_calculate_base_symbols_or_universe():
    """FactorCalculateBase：instruments 与 universe_id 二选一。"""
    with pytest.raises(ValidationError):
        FactorCalculateBase(instruments=["BTCUSDT"], universe_id=1)
    with pytest.raises(ValidationError):
        FactorCalculateBase()

    assert FactorCalculateBase(instruments=["BTCUSDT"]).universe_id is None
    assert FactorCalculateBase(universe_id=2).instruments == []
