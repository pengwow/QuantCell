"""因子存储迁移：JSON 文件 → SQLite factor_catalog 表。

一次性脚本，执行：
    cd backend && .venv/bin/python -m factor.migrate_json_to_db

做的事：
1. ALTER TABLE factor_catalog 补 kind/description/code/code_hash/provenance/method/train_window/constituents 列
2. FACTOR_META 31 个内置因子灌入 DB（kind=builtin，已存在则跳过）
3. custom_factors.json → kind=expression
4. code_factors.json → kind=code
5. composite_factors.json → kind=composite
6. 三个 JSON 文件 mv 到 data/factor/_trash_migrated/ （不直接 rm）

幂等：已迁移的数据不会重复插入（按 name 去重）。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from factor.engine import FACTOR_META
from factor.models import FactorCatalog
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

FACTOR_DIR = Path(__file__).resolve().parent.parent / "data" / "factor"
JSON_FILES = {
    "custom": FACTOR_DIR / "custom_factors.json",
    "code": FACTOR_DIR / "code_factors.json",
    "composite": FACTOR_DIR / "composite_factors.json",
}
TRASH_DIR = FACTOR_DIR / "_trash_migrated"


def _add_columns_if_missing(db) -> None:
    """用原生 SQL 补列（SQLite ALTER TABLE 不支持 IF NOT EXISTS，用 inspect 兜底）。"""
    existing = {row[1] for row in db.execute(text("PRAGMA table_info(factor_catalog)")).fetchall()}
    new_cols = [
        ("kind", "VARCHAR(20)"),
        ("description", "TEXT"),
        ("code", "TEXT"),
        ("code_hash", "VARCHAR(64)"),
        ("provenance", "TEXT"),
        ("method", "VARCHAR(50)"),
        ("train_window", "TEXT"),
        ("constituents", "TEXT"),
    ]
    for col, col_type in new_cols:
        if col not in existing:
            db.execute(text(f"ALTER TABLE factor_catalog ADD COLUMN {col} {col_type}"))
            logger.info(f"  + 列 {col}")
    db.commit()


def _migrate_builtins(db) -> int:
    """FACTOR_META 种子灌入。"""
    existing = {r.name for r in db.query(FactorCatalog).all()}
    created = 0
    for name, meta in FACTOR_META.items():
        if name in existing:
            continue
        db.add(
            FactorCatalog(
                name=name,
                kind="builtin",
                label=meta["label"],
                description=meta.get("expression") or None,
                category=meta.get("category"),
                expression=meta.get("expression") or None,
                is_builtin=True,
                supported=meta.get("supported", True),
                lifecycle_status="DISCOVERED",
            )
        )
        created += 1
    db.commit()
    return created


def _migrate_custom(db) -> int:
    """custom_factors.json → kind=expression。"""
    path = JSON_FILES["custom"]
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = {r.name for r in db.query(FactorCatalog).filter_by(kind="expression").all()}
    created = 0
    for name, entry in data.items():
        if name in existing:
            continue
        if isinstance(entry, str):
            entry = {"expression": entry, "label": name, "description": ""}
        db.add(
            FactorCatalog(
                name=name,
                kind="expression",
                label=entry.get("label") or entry.get("description") or name,
                description=entry.get("description") or None,
                expression=entry.get("expression"),
                category="custom",
                is_builtin=False,
                supported=True,
                lifecycle_status="DISCOVERED",
            )
        )
        created += 1
    db.commit()
    return created


def _migrate_code(db) -> int:
    """code_factors.json → kind=code。已存在的行（无论 kind）跳过。"""
    path = JSON_FILES["code"]
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = {r.name for r in db.query(FactorCatalog).all()}
    created = 0
    for name, entry in data.items():
        if name in existing:
            continue
        db.add(
            FactorCatalog(
                name=name,
                kind="code",
                label=entry.get("label") or entry.get("description") or name,
                description=entry.get("description") or None,
                code=entry.get("code"),
                code_hash=entry.get("code_hash"),
                provenance=json.dumps(entry.get("provenance") or {}, ensure_ascii=False),
                category=entry.get("category") or "llm_code",
                is_builtin=False,
                supported=True,
                lifecycle_status="DISCOVERED",
            )
        )
        created += 1
    db.commit()
    return created


def _migrate_composite(db) -> int:
    """composite_factors.json → kind=composite。"""
    path = JSON_FILES["composite"]
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = {r.name for r in db.query(FactorCatalog).filter_by(kind="composite").all()}
    created = 0
    for name, entry in data.items():
        if name in existing:
            continue
        db.add(
            FactorCatalog(
                name=name,
                kind="composite",
                label=entry.get("label") or entry.get("description") or name,
                description=entry.get("description") or None,
                method=entry.get("method"),
                train_window=json.dumps(entry.get("train_window") or {}, ensure_ascii=False),
                constituents=json.dumps(entry.get("constituents") or [], ensure_ascii=False),
                provenance=json.dumps(entry.get("provenance") or {}, ensure_ascii=False),
                category="llm_composite",
                is_builtin=False,
                supported=True,
                lifecycle_status="DISCOVERED",
            )
        )
        created += 1
    db.commit()
    return created


def _archive_json_files() -> None:
    """迁移成功后把 JSON 文件 mv 到 _trash_migrated，不直接 rm。"""
    if not any(p.exists() for p in JSON_FILES.values()):
        return
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for path in JSON_FILES.values():
        if path.exists():
            dest = TRASH_DIR / f"{path.stem}_{stamp}{path.suffix}"
            shutil.move(str(path), str(dest))
            logger.info(f"  归档 {path.name} → {dest.relative_to(FACTOR_DIR)}")


def main() -> None:
    logger.info("开始因子存储迁移：JSON → factor_catalog")
    with get_db_session() as db:
        _add_columns_if_missing(db)
        n_builtin = _migrate_builtins(db)
        n_custom = _migrate_custom(db)
        n_code = _migrate_code(db)
        n_composite = _migrate_composite(db)
    _archive_json_files()
    total = n_builtin + n_custom + n_code + n_composite
    logger.info(
        f"迁移完成：新建 {total} 条（builtin={n_builtin}, expression={n_custom}, "
        f"code={n_code}, composite={n_composite}），JSON 已归档到 {TRASH_DIR.name}/"
    )
    print(f"✓ 迁移完成：新建 {total} 条因子")
    print(f"  内置 {n_builtin} / 表达式 {n_custom} / 代码 {n_code} / 合成 {n_composite}")
    print(f"  JSON 文件已归档到 {TRASH_DIR}")


if __name__ == "__main__":
    main()
