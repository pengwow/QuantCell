"""FactorCatalogService 同步/状态机/快照 服务层测试。"""

import json

import numpy as np
import pandas as pd
import pytest

from factor.catalog_service import (
    LIFECYCLE_STATUSES,
    CatalogError,
    FactorCatalogService,
)
from factor.factor_store import FactorStore
from factor.models import FactorCatalog, FactorSnapshot
from factor.service import FactorService


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


class _KlineProvider:
    """与 factor analyze 单测同款合成 K 线 provider（含 columns 关键字）。"""

    def __init__(self, n=200):
        self.n = n

    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        rng = np.random.default_rng(abs(hash(symbol)) % 1000)
        close = 100 + np.cumsum(rng.normal(0, 1, self.n))
        ts = pd.date_range("2026-01-01", periods=self.n, freq="1h")
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": rng.uniform(100, 1000, self.n),
                "quote_volume": close * rng.uniform(100, 1000, self.n),
                "timestamp": ts.astype("int64"),
            }
        )


def _svc_with_analyze(db_session, dirs):
    return FactorCatalogService(
        factor_service=FactorService(),
        snapshots_dir=dirs["snapshots"],
        trash_dir=dirs["trash"],
        backend_dir=dirs["backend"],
    )


def test_save_snapshot_recomputes_and_persists(db_session, dirs):
    svc = _svc_with_analyze(db_session, dirs)
    params = {
        "factor_name": "momentum_5d",
        "instruments": ["BTCUSDT"],
        "interval": "1h",
        "candle_type": "spot",
        "start_time": None,
        "end_time": None,
        "method": "spearman",
        "n_groups": 5,
        "window": 20,
        "forward": 1,
    }
    summary = svc.save_snapshot(db_session, params, provider=_KlineProvider())
    snap = db_session.query(FactorSnapshot).filter_by(factor_name="momentum_5d").one()
    assert snap.id == summary["id"]
    assert snap.bar_count > 0
    assert snap.snapshot_file.endswith(".parquet")

    pq = dirs["backend"] / snap.snapshot_file
    assert pq.exists()
    out = pd.read_parquet(pq)
    assert {"timestamp", "factor", "forward_return", "symbol"} <= set(out.columns)
    assert len(out) == snap.bar_count

    cat = db_session.query(FactorCatalog).filter_by(name="momentum_5d").one()
    assert cat.is_builtin is True  # 内置因子也可收藏
    lm = json.loads(cat.last_metrics)
    assert {"snapshot_id", "ic_mean", "ic_ir", "long_short_return"} <= set(lm)
    assert lm["snapshot_id"] == snap.id


def test_list_and_delete_snapshot(db_session, dirs):
    svc = _svc_with_analyze(db_session, dirs)
    params = {
        "factor_name": "momentum_5d",
        "instruments": ["BTCUSDT"],
        "interval": "1h",
        "candle_type": "spot",
        "start_time": None,
        "end_time": None,
        "method": "spearman",
        "n_groups": 5,
        "window": 20,
        "forward": 1,
    }
    s1 = svc.save_snapshot(db_session, params, provider=_KlineProvider())
    pq1 = dirs["backend"] / db_session.query(FactorSnapshot).get(s1["id"]).snapshot_file
    assert pq1.exists()

    items = svc.list_snapshots(db_session, "momentum_5d")
    assert len(items) == 1 and items[0]["id"] == s1["id"]
    # 列表项只摘核心指标 + ic_series_len，不含 ic.series 大数组
    assert "ic_series_len" in items[0]

    svc.delete_snapshot(db_session, s1["id"])
    assert db_session.query(FactorSnapshot).get(s1["id"]) is None
    assert not pq1.exists()
    assert list(dirs["trash"].rglob("*.parquet"))


def test_delete_latest_snapshot_clears_last_metrics(db_session, dirs):
    svc = _svc_with_analyze(db_session, dirs)
    params = {
        "factor_name": "momentum_5d",
        "instruments": ["BTCUSDT"],
        "interval": "1h",
        "candle_type": "spot",
        "start_time": None,
        "end_time": None,
        "method": "spearman",
        "n_groups": 5,
        "window": 20,
        "forward": 1,
    }
    s = svc.save_snapshot(db_session, params, provider=_KlineProvider())
    svc.delete_snapshot(db_session, s["id"])
    cat = db_session.query(FactorCatalog).filter_by(name="momentum_5d").one()
    assert cat.last_metrics is None and cat.last_snapshot_at is None
