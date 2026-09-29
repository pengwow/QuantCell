"""factor_catalog / factor_snapshots 表结构测试（内存 SQLite）。"""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

# factor 包 __init__ 链式导入会注册 worker.models（Worker.relationship("Strategy") 为字符串引用），
# 必须同时注册 strategy.models，否则实例化映射对象触发全局 mapper 配置时会失败
import strategy.models
from collector.db.database import Base
from factor.models import FactorCatalog, FactorSnapshot


def _engine():
    eng = create_engine("sqlite:///:memory:")
    # 只注册本模块两表，避免内存库要求其它业务表全部存在
    Base.metadata.create_all(eng, tables=[FactorCatalog.__table__, FactorSnapshot.__table__])
    return eng


def test_tables_created_with_expected_columns():
    eng = _engine()
    cols = {c["name"] for c in inspect(eng).get_columns("factor_catalog")}
    assert {
        "id",
        "name",
        "label",
        "category",
        "expression",
        "is_builtin",
        "supported",
        "lifecycle_status",
        "last_metrics",
        "last_snapshot_at",
        "created_at",
        "updated_at",
    } <= cols
    snap_cols = {c["name"] for c in inspect(eng).get_columns("factor_snapshots")}
    assert {
        "id",
        "factor_name",
        "params_json",
        "metrics_json",
        "bar_count",
        "snapshot_file",
        "created_at",
    } <= snap_cols


def test_default_lifecycle_status_and_unique_name():
    import pytest
    from sqlalchemy.exc import IntegrityError

    eng = _engine()
    Session = sessionmaker(bind=eng)
    with Session() as s:
        s.add(FactorCatalog(name="mom_x", is_builtin=False, supported=True))
        s.commit()
        row = s.query(FactorCatalog).filter_by(name="mom_x").one()
        assert row.lifecycle_status == "DISCOVERED"
        assert row.is_builtin is False
        s.add(FactorCatalog(name="mom_x", is_builtin=False))
        with pytest.raises(IntegrityError):
            s.commit()


def test_snapshot_belongs_to_factor_name():
    eng = _engine()
    Session = sessionmaker(bind=eng)
    with Session() as s:
        s.add(FactorSnapshot(factor_name="mom_x", params_json="{}", metrics_json="{}", bar_count=10))
        s.commit()
        assert s.query(FactorSnapshot).filter_by(factor_name="mom_x").one().bar_count == 10
