"""标的池并入自选组后的成分快照与成分解析自检（承接原 tests/unit/universe 的语义）。

覆盖三条非平凡路径：
1. 成分增删后快照必须是"变更后的完整成分"（依赖 flush 先落库的顺序正确性）；
2. resolve_symbols 的 None（池不存在→404）/ 空列表（空池→400）语义；
3. 池删除级联清理快照。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db import database as db_module
from collector.db.database import _import_all_models
from collector.db.models import DataPoolAsset, DataPoolBusiness, DataPoolSnapshot, TimezoneAwareBase

# 跨 app 模块的外键（workers.strategy_id → strategies）要求所有 ORM 先注册，
# 否则内存库 create_all 会因 FK 无法解析而抛错（与 indicators 测试同模式的坑）
_import_all_models()


@pytest.fixture()
def pool_db(monkeypatch):
    """函数级内存库：每个用例一张干净库（与 indicators 测试同模式）。

    替换全局 SessionLocal 指向内存库，engine 置哨兵让 init_database_config 短路。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TimezoneAwareBase.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(db_module, "SessionLocal", factory)
    monkeypatch.setattr(db_module, "engine", object(), raising=False)
    yield factory
    engine.dispose()


def _create_pool(name: str = "测试组") -> int:
    pool_id = DataPoolBusiness.create(name=name, type="crypto")
    assert pool_id is not None
    return pool_id


class TestDataPoolSnapshot:
    def test_add_assets_writes_snapshot_with_full_composition(self, pool_db):
        pool_id = _create_pool()
        assert DataPoolBusiness.add_assets(pool_id, ["BTCUSDT", "ETHUSDT"], "crypto")

        with pool_db() as db:
            snaps = db.query(DataPoolSnapshot).order_by(DataPoolSnapshot.id).all()
            assert len(snaps) == 1
            assert snaps[0].pool_id == pool_id

    def test_remove_appends_second_snapshot(self, pool_db):
        pool_id = _create_pool()
        assert DataPoolBusiness.add_assets(pool_id, ["BTCUSDT", "ETHUSDT"], "crypto")
        assert DataPoolBusiness.remove_assets(pool_id, ["ETHUSDT"])

        with pool_db() as db:
            assert db.query(DataPoolSnapshot).count() == 2

        # 快照 JSON 内容语义直接走 list_snapshots 校验
        history = DataPoolBusiness.list_snapshots(pool_id)
        assert history[0]["symbols"] == ["BTCUSDT"]  # 最新快照：移除后剩余
        assert history[-1]["symbols"] == ["BTCUSDT", "ETHUSDT"]  # 最早快照：初始成分

    def test_delete_cascades_snapshots(self, pool_db):
        pool_id = _create_pool()
        DataPoolBusiness.add_assets(pool_id, ["BTCUSDT"], "crypto")
        assert DataPoolBusiness.delete(pool_id)

        with pool_db() as db:
            assert db.query(DataPoolSnapshot).filter_by(pool_id=pool_id).count() == 0

    def test_resolve_symbols_semantics(self, pool_db):
        pool_id = _create_pool()
        assert DataPoolBusiness.resolve_symbols(9999) is None  # 池不存在
        assert DataPoolBusiness.resolve_symbols(pool_id) == []  # 空池

        DataPoolBusiness.add_assets(pool_id, ["BTCUSDT", "ETHUSDT"], "crypto")
        assert DataPoolBusiness.resolve_symbols(pool_id) == ["BTCUSDT", "ETHUSDT"]

    def test_list_snapshots_missing_pool_returns_empty(self, pool_db):
        assert DataPoolBusiness.list_snapshots(9999) == []

    def test_assets_table_still_consistent(self, pool_db):
        """快照是旁路记录，不应影响 DataPoolAsset 主数据。"""
        pool_id = _create_pool()
        DataPoolBusiness.add_assets(pool_id, ["BTCUSDT"], "crypto")
        with pool_db() as db:
            assets = db.query(DataPoolAsset).filter_by(pool_id=pool_id).all()
            assert [(a.asset_id, a.asset_type) for a in assets] == [("BTCUSDT", "crypto")]
