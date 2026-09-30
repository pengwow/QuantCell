"""因子档案服务：内置同步、自定义钩子、生命周期状态机、分析快照收藏。

档案是表达式/分析的派生数据：
- 表达式真相源在 factor.engine + FactorStore，本服务不参与求值；
- DB 会话由调用方（routes）管理；快照目录与归档目录可注入，便于测试。
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from factor.models import FactorCatalog, FactorSnapshot
from utils.logger import LogType, get_logger
from utils.parquet_utils import save_to_parquet

logger = get_logger(__name__, LogType.APPLICATION)

# 五态生命周期：逐级前进、逐级回退、任意态可退役；RETIRED 为终态
LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "DISCOVERED": {"INSPECTED", "RETIRED"},
    "INSPECTED": {"DISCOVERED", "PAPER_TRADING", "RETIRED"},
    "PAPER_TRADING": {"INSPECTED", "LIVE", "RETIRED"},
    "LIVE": {"PAPER_TRADING", "RETIRED"},
    "RETIRED": set(),
}
LIFECYCLE_STATUSES = set(LIFECYCLE_TRANSITIONS)


class CatalogError(Exception):
    """档案业务错误（路由按 kind 映射 HTTP 状态码）。"""

    def __init__(self, message: str, kind: str = "bad_request"):
        super().__init__(message)
        self.kind = kind  # not_found / forbidden / bad_request


class FactorCatalogService:
    def __init__(
        self,
        factor_service,
        snapshots_dir: Path,
        trash_dir: Path,
        backend_dir: Path,
    ):
        self._factors = factor_service
        self._snapshots_dir = Path(snapshots_dir)
        self._trash_dir = Path(trash_dir)
        self._backend_dir = Path(backend_dir)

    # ---------------- 内置同步 ----------------

    def sync_builtins(self, db: Session) -> int:
        """按因子引擎明细同步档案：新建缺失内置/自定义条目；只刷新元数据列。

        绝不覆盖 lifecycle_status / last_metrics / last_snapshot_at（用户研究状态）。
        返回新建条目数。
        """
        created = 0
        existing = {row.name: row for row in db.query(FactorCatalog).all()}
        for d in self._factors.get_factor_details():
            row = existing.get(d["name"])
            if row is None:
                db.add(
                    FactorCatalog(
                        name=d["name"],
                        label=d.get("label"),
                        category=d.get("category"),
                        expression=d.get("expression") or None,
                        is_builtin=bool(d.get("builtin")),
                        supported=bool(d.get("supported")),
                    )
                )
                created += 1
            else:
                row.label = d.get("label")
                row.category = d.get("category")
                row.expression = d.get("expression") or None
                row.supported = bool(d.get("supported"))
        db.commit()
        return created

    # ---------------- 自定义因子钩子 ----------------

    def upsert_custom(self, db: Session, detail: dict[str, Any]) -> FactorCatalog:
        """自定义因子 add 后建档；已存在则只刷新表达式，不重置生命周期。"""
        row = db.query(FactorCatalog).filter_by(name=detail["name"]).one_or_none()
        if row is None:
            row = FactorCatalog(
                name=detail["name"],
                label=detail.get("label", detail["name"]),
                category=detail.get("category", "custom"),
                expression=detail.get("expression"),
                is_builtin=False,
                supported=bool(detail.get("supported", True)),
                lifecycle_status="DISCOVERED",
            )
            db.add(row)
        else:
            row.expression = detail.get("expression")
        db.commit()
        return row

    def on_factor_deleted(self, db: Session, name: str) -> None:
        """自定义因子删除后：归档全部快照 parquet，删快照行与档案行。"""
        for snap in db.query(FactorSnapshot).filter_by(factor_name=name).all():
            self._archive_snapshot_file(snap.snapshot_file)
            db.delete(snap)
        db.query(FactorCatalog).filter_by(name=name).delete()
        db.commit()

    # ---------------- 生命周期 ----------------

    def transition(self, db: Session, name: str, new_status: str) -> FactorCatalog:
        """校验并执行生命周期流转；非法转换/未知因子/内置操作抛 CatalogError。"""
        if new_status not in LIFECYCLE_STATUSES:
            raise CatalogError(f"未知生命周期状态: {new_status}", "bad_request")
        row = db.query(FactorCatalog).filter_by(name=name).one_or_none()
        if row is None:
            raise CatalogError(f"因子档案不存在: {name}", "not_found")
        if row.is_builtin:
            raise CatalogError(f"内置因子不允许变更生命周期: {name}", "forbidden")
        allowed = LIFECYCLE_TRANSITIONS.get(row.lifecycle_status, set())
        if new_status not in allowed:
            raise CatalogError(
                f"非法状态流转 {row.lifecycle_status} → {new_status}；合法目标: {sorted(allowed) or '无（终态）'}",
                "bad_request",
            )
        row.lifecycle_status = new_status
        db.commit()
        return row

    # ---------------- 分析快照 ----------------

    _SUMMARY_KEYS = (
        "ic_mean",
        "ic_ir",
        "ic_positive_rate",
        "long_short_return",
        "monotonicity_spearman",
        "stability_autocorr",
    )

    def _metrics_summary(self, result: dict[str, Any], snapshot_id: int) -> dict[str, Any]:
        """从 analyze 结果（或其持久化 JSON）摘取档案卡片用的核心指标。"""
        inspection = result.get("inspection") or {}
        return {
            "snapshot_id": snapshot_id,
            "bar_count": result.get("bar_count"),
            "ic_mean": result.get("ic", {}).get("mean"),
            "ic_ir": result.get("ic", {}).get("ir"),
            "ic_positive_rate": result.get("ic", {}).get("positive_rate"),
            "long_short_return": result.get("long_short_return"),
            "monotonicity_spearman": result.get("monotonicity", {}).get("spearman"),
            "stability_autocorr": result.get("stability", {}).get("mean_autocorr"),
            "coverage": inspection.get("coverage"),
            "turnover": inspection.get("turnover"),
            "annualized_ir": (inspection.get("ic_stats") or {}).get("annualized_ir"),
            "nw_t_stat": (inspection.get("ic_stats") or {}).get("nw_t_stat"),
            "created_at": datetime.now(UTC).isoformat(),
        }

    def save_snapshot(self, db: Session, params: dict[str, Any], provider=None) -> dict[str, Any]:
        """按入参服务端重算 analyze，落 parquet 快照并回写档案 last_metrics。"""
        result, frames = self._factors.analyze(
            factor_name=params["factor_name"],
            symbols=params["instruments"],
            interval=params["interval"],
            candle_type=params.get("candle_type", "spot"),
            start=params.get("start_time"),
            end=params.get("end_time"),
            method=params.get("method", "spearman"),
            n_groups=params.get("n_groups", 5),
            window=params.get("window", 20),
            forward=params.get("forward", 1),
            provider=provider,
            return_frames=True,
            horizons=params.get("horizons"),
            cost_bps=params.get("cost_bps", 0.0),
        )

        snap = FactorSnapshot(
            factor_name=params["factor_name"],
            params_json=json.dumps(params, ensure_ascii=False),
            metrics_json=json.dumps(result, ensure_ascii=False, default=str),
            bar_count=int(result.get("bar_count", 0)),
        )
        db.add(snap)
        db.flush()  # 取自增 id 用于文件名

        snap_dir = self._snapshots_dir / params["factor_name"]
        snap_dir.mkdir(parents=True, exist_ok=True)
        file_path = snap_dir / f"snapshot_{snap.id}.parquet"
        # 列顺序固定：timestamp, symbol, factor, forward_return
        out = (
            frames.rename(columns={"f": "factor", "r": "forward_return"})
            .reset_index()
            .rename(columns={"datetime": "timestamp"})[["timestamp", "symbol", "factor", "forward_return"]]
        )
        if not save_to_parquet(out, file_path):
            db.rollback()
            raise CatalogError("快照 parquet 写入失败", "bad_request")

        # 相对 backend 目录的 posix 路径，便于迁移与归档
        snap.snapshot_file = file_path.relative_to(self._backend_dir).as_posix()

        # 档案行不存在时惰性补建：内置/自定义属性以因子服务明细为准（未同步内置时也能正确标记）
        cat = db.query(FactorCatalog).filter_by(name=params["factor_name"]).one_or_none()
        if cat is None:
            detail = next(
                (d for d in self._factors.get_factor_details() if d["name"] == params["factor_name"]),
                None,
            )
            cat = FactorCatalog(
                name=params["factor_name"],
                label=(detail or {}).get("label", params["factor_name"]),
                category=(detail or {}).get("category", "custom"),
                expression=(detail or {}).get("expression") or None,
                is_builtin=bool(detail and detail.get("builtin")),
                supported=bool((detail or {}).get("supported", True)),
                lifecycle_status="DISCOVERED",
            )
            db.add(cat)
        summary = self._metrics_summary(result, snap.id)
        cat.last_metrics = json.dumps(summary, ensure_ascii=False)
        cat.last_snapshot_at = datetime.now(UTC)
        db.commit()
        return {"id": snap.id, **summary}

    def list_snapshots(self, db: Session, factor_name: str, limit: int = 100) -> list[dict[str, Any]]:
        """查询某因子的快照历史（新→旧），只摘核心指标，不含 ic.series 大数组。"""
        rows = (
            db.query(FactorSnapshot)
            .filter_by(factor_name=factor_name)
            .order_by(FactorSnapshot.created_at.desc(), FactorSnapshot.id.desc())
            .limit(limit)
            .all()
        )
        items = []
        for r in rows:
            metrics = json.loads(r.metrics_json)
            items.append(
                {
                    "id": r.id,
                    "factor_name": r.factor_name,
                    "params": json.loads(r.params_json),
                    "bar_count": r.bar_count,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "ic_mean": metrics.get("ic", {}).get("mean"),
                    "ic_ir": metrics.get("ic", {}).get("ir"),
                    "ic_positive_rate": metrics.get("ic", {}).get("positive_rate"),
                    "long_short_return": metrics.get("long_short_return"),
                    "monotonicity_spearman": metrics.get("monotonicity", {}).get("spearman"),
                    "stability_autocorr": metrics.get("stability", {}).get("mean_autocorr"),
                    "coverage": metrics.get("inspection", {}).get("coverage"),
                    "turnover": metrics.get("inspection", {}).get("turnover"),
                    "annualized_ir": (metrics.get("inspection", {}).get("ic_stats") or {}).get("annualized_ir"),
                    "nw_t_stat": (metrics.get("inspection", {}).get("ic_stats") or {}).get("nw_t_stat"),
                    "ic_series_len": len(metrics.get("ic", {}).get("series", [])),
                }
            )
        return items

    def delete_snapshot(self, db: Session, snapshot_id: int) -> None:
        """删除快照并归档 parquet；若删的是档案最近快照，回退到剩余最新摘要或清空。"""
        snap = db.get(FactorSnapshot, snapshot_id)
        if snap is None:
            raise CatalogError(f"快照不存在: {snapshot_id}", "not_found")
        factor_name = snap.factor_name
        was_latest = False
        cat = db.query(FactorCatalog).filter_by(name=factor_name).one_or_none()
        if cat is not None and cat.last_metrics:
            try:
                was_latest = json.loads(cat.last_metrics).get("snapshot_id") == snapshot_id
            except json.JSONDecodeError:
                was_latest = False
        self._archive_snapshot_file(snap.snapshot_file)
        db.delete(snap)
        if cat is not None and was_latest:
            remaining = (
                db.query(FactorSnapshot)
                .filter_by(factor_name=factor_name)
                .order_by(FactorSnapshot.created_at.desc(), FactorSnapshot.id.desc())
                .first()
            )
            if remaining is not None:
                metrics = json.loads(remaining.metrics_json)
                cat.last_metrics = json.dumps(self._metrics_summary(metrics, remaining.id), ensure_ascii=False)
                cat.last_snapshot_at = remaining.created_at
            else:
                cat.last_metrics = None
                cat.last_snapshot_at = None
        db.commit()

    # ---------------- 文件归档 ----------------

    def _archive_snapshot_file(self, rel_or_abs: str | None) -> None:
        if not rel_or_abs:
            return
        path = Path(rel_or_abs)
        if not path.is_absolute():
            path = self._backend_dir / path
        if not path.exists():
            return
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        dest_dir = self._trash_dir / day / path.parent.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest_dir / path.name))
        logger.info(f"因子快照已归档: {path.name} -> {dest_dir}")
