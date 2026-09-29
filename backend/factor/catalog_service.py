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

from sqlalchemy.orm import Session

from factor.models import FactorCatalog, FactorSnapshot
from utils.logger import LogType, get_logger

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
