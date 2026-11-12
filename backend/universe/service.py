"""标的池 service（P2-03）：池 CRUD、成分增删（历史留痕 + 变更快照）、成分解析。

异常统一抛 UniverseError 子类，routes 层据此映射 HTTP 状态码；后端时间列统一存
naive UTC DateTime（与既有 DateTime + func.now() 模式一致）。
resolve_universe_symbols 同时供 backtest / factor 的 universe_id 入参解析复用。
"""

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from universe.models import Universe, UniverseMembership, UniverseSnapshot
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


class UniverseError(Exception):
    """标的池业务错误基类，message 可直接作为用户可见错误信息。"""


class UniverseNotFoundError(UniverseError):
    """池不存在（routes 映射 404）。"""


class DuplicateUniverseError(UniverseError):
    """池名称重复或成分越权归属（routes 映射 409）。"""


def _normalize_symbols(symbols: list[str]) -> list[str]:
    """标的归一化：去空白、大写、按首次出现顺序去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in symbols:
        symbol = (raw or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def _utcnow_naive() -> datetime:
    """naive UTC 时间戳，与 DateTime 列（func.now()）口径一致。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _active_symbol_list(db: Session, universe_id: int) -> list[str]:
    """当前在池成分（included_until 为 NULL），按入池顺序。"""
    rows = (
        db.query(UniverseMembership.symbol)
        .filter(
            UniverseMembership.universe_id == universe_id,
            UniverseMembership.included_until.is_(None),
        )
        .order_by(UniverseMembership.included_from, UniverseMembership.id)
        .all()
    )
    return [symbol for (symbol,) in rows]


def _take_snapshot(db: Session, universe_id: int, symbols: list[str]) -> None:
    """成分变更后写入快照（变更后的完整成分）。"""
    db.add(UniverseSnapshot(universe_id=universe_id, symbols=json.dumps(symbols)))


def _require_universe(db: Session, universe_id: int) -> Universe:
    """按 id 取池，不存在抛 UniverseNotFoundError。"""
    universe = db.get(Universe, universe_id)
    if universe is None:
        raise UniverseNotFoundError(f"标的池不存在: {universe_id}")
    return universe


def _universe_dict(universe: Universe, members: list[str]) -> dict:
    return {
        "id": universe.id,
        "name": universe.name,
        "description": universe.description,
        "owner_id": universe.owner_id,
        "members": members,
        "member_count": len(members),
        "created_at": universe.created_at.isoformat() if universe.created_at else None,
    }


def list_universes() -> list[dict]:
    """全部标的池及当前成分数（不展开成分列表，列表页用）。"""
    with get_db_session() as db:
        rows = db.query(Universe).order_by(Universe.id.desc()).all()
        active_rows = db.query(UniverseMembership.universe_id).filter(UniverseMembership.included_until.is_(None)).all()
        counts: dict[int, int] = {}
        for (uid,) in active_rows:
            counts[uid] = counts.get(uid, 0) + 1
        return [
            {
                "id": u.id,
                "name": u.name,
                "description": u.description,
                "member_count": counts.get(u.id, 0),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ]


def create_universe(
    name: str,
    description: str | None = None,
    symbols: list[str] | None = None,
    owner_id: int | None = None,
) -> dict:
    """创建标的池：初始成分入池并写入基线快照；名称重复抛 DuplicateUniverseError。"""
    members = _normalize_symbols(symbols or [])
    with get_db_session() as db:
        if db.query(Universe.id).filter(Universe.name == name).first() is not None:
            raise DuplicateUniverseError(f"标的池名称已存在: {name}")
        universe = Universe(name=name, description=description, owner_id=owner_id)
        db.add(universe)
        db.flush()  # 取自增 id 供成员/快照外键使用
        now = _utcnow_naive()
        for symbol in members:
            db.add(UniverseMembership(universe_id=universe.id, symbol=symbol, included_from=now))
        _take_snapshot(db, universe.id, members)  # 建池即有基线快照，便于按时间回看
        db.commit()
        logger.info(f"创建标的池 {universe.id}({name})，初始成分 {len(members)} 个")
        return _universe_dict(universe, members)


def get_universe(universe_id: int) -> dict:
    """池详情（含当前成分列表）。"""
    with get_db_session() as db:
        universe = _require_universe(db, universe_id)
        return _universe_dict(universe, _active_symbol_list(db, universe_id))


def resolve_universe_symbols(universe_id: int) -> list[str]:
    """解析池内当前成分，供 backtest / factor 的 universe_id 入参解析复用；空池返回空列表由调用方报错。"""
    with get_db_session() as db:
        _require_universe(db, universe_id)
        members = _active_symbol_list(db, universe_id)
        logger.info(f"标的池 {universe_id} 解析出 {len(members)} 个标的")
        return members


def update_universe(universe_id: int, name: str | None = None, description: str | None = None) -> dict:
    """更新池名称/描述；改名撞名抛 DuplicateUniverseError。"""
    with get_db_session() as db:
        universe = _require_universe(db, universe_id)
        if name is not None and name != universe.name:
            clash = db.query(Universe.id).filter(Universe.name == name, Universe.id != universe_id).first()
            if clash is not None:
                raise DuplicateUniverseError(f"标的池名称已存在: {name}")
            universe.name = name
        if description is not None:
            universe.description = description
        db.commit()
        logger.info(f"更新标的池 {universe_id}")
        return _universe_dict(universe, _active_symbol_list(db, universe_id))


def delete_universe(universe_id: int) -> None:
    """删除池并级联清理成分历史与快照。"""
    with get_db_session() as db:
        _require_universe(db, universe_id)
        # sqlite 默认不启用外键级联，显式按池清子表
        db.query(UniverseMembership).filter(UniverseMembership.universe_id == universe_id).delete()
        db.query(UniverseSnapshot).filter(UniverseSnapshot.universe_id == universe_id).delete()
        db.query(Universe).filter(Universe.id == universe_id).delete()
        db.commit()
        logger.info(f"删除标的池 {universe_id}（含成分历史与快照）")


def add_members(universe_id: int, symbols: list[str]) -> dict:
    """加入成分：池内已有的活跃成员跳过（同池同标的唯一活跃归属），有新增则写快照。"""
    wanted = _normalize_symbols(symbols)
    with get_db_session() as db:
        _require_universe(db, universe_id)
        existing = set(_active_symbol_list(db, universe_id))
        new_symbols = [s for s in wanted if s not in existing]
        if new_symbols:
            now = _utcnow_naive()
            for symbol in new_symbols:
                db.add(UniverseMembership(universe_id=universe_id, symbol=symbol, included_from=now))
            # 先 flush 让新成员可被 _active_symbol_list 查到，再按入池顺序读回写快照
            db.flush()
            members = _active_symbol_list(db, universe_id)
            _take_snapshot(db, universe_id, members)
            db.commit()
            logger.info(f"标的池 {universe_id} 新增 {len(new_symbols)} 个成分: {new_symbols}")
        else:
            members = _active_symbol_list(db, universe_id)
            db.commit()
        return {"added": len(new_symbols), "members": members}


def remove_members(universe_id: int, symbols: list[str]) -> dict:
    """移出成分：置 included_until 留历史，有实际移出则写快照。"""
    wanted = _normalize_symbols(symbols)
    with get_db_session() as db:
        _require_universe(db, universe_id)
        active_rows = (
            db.query(UniverseMembership)
            .filter(
                UniverseMembership.universe_id == universe_id,
                UniverseMembership.included_until.is_(None),
                UniverseMembership.symbol.in_(wanted),
            )
            .all()
        )
        now = _utcnow_naive()
        for row in active_rows:
            row.included_until = now
        if active_rows:
            members = _active_symbol_list(db, universe_id)
            _take_snapshot(db, universe_id, members)
            db.commit()
            logger.info(f"标的池 {universe_id} 移出 {len(active_rows)} 个成分")
        else:
            members = _active_symbol_list(db, universe_id)
            db.commit()
        return {"removed": len(active_rows), "members": members}


def list_snapshots(universe_id: int) -> list[dict]:
    """快照历史（按创建时间倒序），供按时间回看成分。"""
    with get_db_session() as db:
        _require_universe(db, universe_id)
        rows = (
            db.query(UniverseSnapshot)
            .filter(UniverseSnapshot.universe_id == universe_id)
            .order_by(UniverseSnapshot.id.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "universe_id": r.universe_id,
                "symbols": json.loads(r.symbols),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
