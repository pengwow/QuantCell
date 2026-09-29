"""FactorCatalogService 同步/状态机/快照 服务层测试。"""

import json

import pytest

from factor.catalog_service import (
    LIFECYCLE_STATUSES,
    CatalogError,
    FactorCatalogService,
)
from factor.factor_store import FactorStore
from factor.models import FactorCatalog, FactorSnapshot


class _Detail:
    def __init__(self, name, label, category, expression, builtin, supported):
        self.name, self.label, self.category = name, label, category
        self.expression, self.builtin, self.supported = expression, builtin, supported


class FakeFactorService:
    """只实现档案服务需要的 get_factor_details / store。"""

    def __init__(self, details):
        self._details = details

    def get_factor_details(self):
        return [vars(d) for d in self._details]


def _details():
    return [
        _Detail("close", "收盘价", "price", "close", True, True),
        _Detail("momentum_5d", "动量(5)", "momentum", "close / Ref(close, 5) - 1", True, True),
        _Detail("pe", "市盈率", "fundamental", "", True, False),
    ]


def _svc(db_session, dirs, details=None):
    return FactorCatalogService(
        factor_service=FakeFactorService(details or _details()),
        snapshots_dir=dirs["snapshots"],
        trash_dir=dirs["trash"],
        backend_dir=dirs["backend"],
    )


def test_sync_builtins_idempotent_and_preserves_lifecycle(db_session, dirs):
    svc = _svc(db_session, dirs)
    created = svc.sync_builtins(db_session)
    assert created == 3
    assert svc.sync_builtins(db_session) == 0
    assert db_session.query(FactorCatalog).filter_by(name="close").one().is_builtin is True

    # 用户把 close 推到 LIVE，再次同步不能冲掉（直接改列模拟用户状态）
    db_session.query(FactorCatalog).filter_by(name="close").update({"lifecycle_status": "LIVE"})
    db_session.commit()
    svc.sync_builtins(db_session)
    assert db_session.query(FactorCatalog).filter_by(name="close").one().lifecycle_status == "LIVE"


def test_upsert_custom_catalog(db_session, dirs):
    svc = _svc(db_session, dirs)
    svc.upsert_custom(
        db_session,
        {
            "name": "my_mom",
            "label": "my_mom",
            "category": "custom",
            "expression": "close-open",
            "builtin": False,
            "supported": True,
        },
    )
    row = db_session.query(FactorCatalog).filter_by(name="my_mom").one()
    assert row.is_builtin is False and row.lifecycle_status == "DISCOVERED"


def test_delete_factor_removes_catalog_snapshots_and_archives_parquet(db_session, dirs):
    svc = _svc(db_session, dirs)
    svc.upsert_custom(
        db_session,
        {
            "name": "my_mom",
            "label": "my_mom",
            "category": "custom",
            "expression": "close",
            "builtin": False,
            "supported": True,
        },
    )
    # 手工造一条快照 + parquet 文件
    snap_dir = dirs["snapshots"] / "my_mom"
    snap_dir.mkdir(parents=True)
    pq = snap_dir / "snapshot_1.parquet"
    pq.write_bytes(b"fake-parquet")
    db_session.add(
        FactorSnapshot(
            factor_name="my_mom",
            params_json="{}",
            metrics_json="{}",
            bar_count=1,
            snapshot_file=str(pq.relative_to(dirs["backend"])),
        )
    )
    db_session.commit()

    svc.on_factor_deleted(db_session, "my_mom")
    assert db_session.query(FactorCatalog).filter_by(name="my_mom").first() is None
    assert db_session.query(FactorSnapshot).filter_by(factor_name="my_mom").count() == 0
    assert not pq.exists()
    moved = list(dirs["trash"].rglob("snapshot_1.parquet"))
    assert len(moved) == 1


def test_lifecycle_constants():
    assert LIFECYCLE_STATUSES == {
        "DISCOVERED",
        "INSPECTED",
        "PAPER_TRADING",
        "LIVE",
        "RETIRED",
    }


def _custom_row(db_session, name="my_mom", status="DISCOVERED"):
    r = FactorCatalog(name=name, is_builtin=False, supported=True, lifecycle_status=status)
    db_session.add(r)
    db_session.commit()
    return r


def test_lifecycle_valid_transitions(db_session, dirs):
    svc = _svc(db_session, dirs)
    _custom_row(db_session)
    assert svc.transition(db_session, "my_mom", "INSPECTED").lifecycle_status == "INSPECTED"
    assert svc.transition(db_session, "my_mom", "PAPER_TRADING").lifecycle_status == "PAPER_TRADING"
    assert svc.transition(db_session, "my_mom", "LIVE").lifecycle_status == "LIVE"
    assert svc.transition(db_session, "my_mom", "PAPER_TRADING").lifecycle_status == "PAPER_TRADING"


def test_lifecycle_retire_from_any_state_is_terminal(db_session, dirs):
    svc = _svc(db_session, dirs)
    _custom_row(db_session, name="r1", status="INSPECTED")
    assert svc.transition(db_session, "r1", "RETIRED").lifecycle_status == "RETIRED"
    with pytest.raises(CatalogError) as ei:
        svc.transition(db_session, "r1", "DISCOVERED")
    assert ei.value.kind == "bad_request"


def test_lifecycle_rejects_skip(db_session, dirs):
    svc = _svc(db_session, dirs)
    _custom_row(db_session)
    with pytest.raises(CatalogError):
        svc.transition(db_session, "my_mom", "LIVE")  # DISCOVERED 不能直达 LIVE


def test_lifecycle_unknown_factor_and_bad_status(db_session, dirs):
    svc = _svc(db_session, dirs)
    with pytest.raises(CatalogError) as e:
        svc.transition(db_session, "ghost", "INSPECTED")
    assert e.value.kind == "not_found"
    _custom_row(db_session, name="x1")
    with pytest.raises(CatalogError) as e2:
        svc.transition(db_session, "x1", "NOPE")
    assert e2.value.kind == "bad_request"


def test_lifecycle_builtin_forbidden(db_session, dirs):
    svc = _svc(db_session, dirs)
    svc.sync_builtins(db_session)
    with pytest.raises(CatalogError) as e:
        svc.transition(db_session, "close", "INSPECTED")
    assert e.value.kind == "forbidden"
