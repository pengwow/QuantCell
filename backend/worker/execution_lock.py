"""跨 worker / per-symbol 执行锁（P0-03）。

目标：防止两个 worker 对同一交易所账户的同一 symbol 并行交易导致双向
重复下单。锁 = order_lease 表中 lease_key = f"{symbol}:{account_id}" 的
唯一行；持有 = 行内 owner_worker_id 是自己且心跳新鲜；过期 = expires_at
< now，他人可条件 UPDATE 换主——kill -9 之类拿不到 release 的死亡靠
TTL 自愈，不依赖 sweep。

接口约定对齐 factor/job_lease.py：所有函数可选传 db，传入时用调用方
会话（同事务），不传自开短会话并**显式 commit**（get_db_session 不会
自动提交）。原子性：acquire 依赖 lease_key 唯一约束 + 条件 UPDATE 的
行数判定，不做「先 SELECT 再 INSERT」的竞态窗口。
"""

import time
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.db_session import get_db_session
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

EXEC_LEASE_TTL_S = 30.0  # 持锁超时未续期即视为持有方死亡，可被他人换主
EXEC_HEARTBEAT_S = 5.0  # 续期最小间隔参考值；实际接线按 live tick 10s 节拍续期（< TTL 即安全）

# acquire 两步：无行 INSERT（唯一约束拦并发），有行走条件 UPDATE 换主/
# 本 worker 复读，绝不改写他主且新鲜的锁。
# acquired_at 是 DateTime 列，用 SQL 标准 CURRENT_TIMESTAMP 生成（SQLite 存
# 文本、方言无关）；:now 是 time.time() 浮点，只给 heartbeat_at/expires_at
# 这两个 REAL 心跳列——浮点直写 DateTime 列读回时 fromisoformat 会炸
_ACQUIRE_INSERT = text(
    "INSERT INTO order_lease (lease_key, owner_worker_id, acquired_at, heartbeat_at, expires_at) "
    "VALUES (:k, :w, CURRENT_TIMESTAMP, :now, :exp) ON CONFLICT (lease_key) DO NOTHING"
)
_ACQUIRE_TAKEOVER = text(
    "UPDATE order_lease SET owner_worker_id = :w, acquired_at = CURRENT_TIMESTAMP, "
    "heartbeat_at = :now, expires_at = :exp "
    "WHERE lease_key = :k AND (expires_at < :now OR owner_worker_id = :w)"
)
_HEARTBEAT_SQL = text(
    "UPDATE order_lease SET heartbeat_at = :now, expires_at = :exp WHERE lease_key = :k AND owner_worker_id = :w"
)
_RELEASE_SQL = text("DELETE FROM order_lease WHERE lease_key = :k AND owner_worker_id = :w")
_SWEEP_SQL = text("DELETE FROM order_lease WHERE expires_at < :now")


def lease_key(symbol: str, account_id: str) -> str:
    """锁键：symbol 用 DB 口径（如 BTC/USDT），account_id 用 API key 指纹前 8 位"""
    return f"{symbol}:{account_id}"


def _run[T](fn: Callable[[Session], T], db: Session | None) -> T:
    """传 db 则同调用方事务执行；否则自开短会话并显式提交（get_db_session 不自动 commit）"""
    if db is not None:
        return fn(db)
    with get_db_session() as session:
        result = fn(session)
        session.commit()
        return result


def acquire(symbol: str, account_id: str, worker_id: int, *, db: Session | None = None) -> bool:
    """获取锁（幂等）：已持有返回 True；他主且新鲜返回 False；过期行换主返回 True"""

    def _acquire(session: Session) -> bool:
        now = time.time()
        inserted = session.execute(
            _ACQUIRE_INSERT,
            {"k": lease_key(symbol, account_id), "w": worker_id, "now": now, "exp": now + EXEC_LEASE_TTL_S},
        )
        if inserted.rowcount == 1:
            return True
        # 行已存在：过期换主 / 本 worker 复读（兼做续期）；他主且新鲜不动
        updated = session.execute(
            _ACQUIRE_TAKEOVER,
            {"k": lease_key(symbol, account_id), "w": worker_id, "now": now, "exp": now + EXEC_LEASE_TTL_S},
        )
        return updated.rowcount > 0

    return _run(_acquire, db)


def heartbeat(symbol: str, account_id: str, worker_id: int, *, db: Session | None = None) -> bool:
    """续期：仅 owner 本人可续，返回是否命中（False = 已失锁，调用方应停止交易）"""

    def _heartbeat(session: Session) -> bool:
        now = time.time()
        updated = session.execute(
            _HEARTBEAT_SQL,
            {
                "k": lease_key(symbol, account_id),
                "w": worker_id,
                "now": now,
                "exp": now + EXEC_LEASE_TTL_S,
            },
        )
        return updated.rowcount > 0

    return _run(_heartbeat, db)


def release(symbol: str, account_id: str, worker_id: int, *, db: Session | None = None) -> bool:
    """释放锁：仅 owner 本人可删；非持锁方调用无副作用返回 False"""

    def _release(session: Session) -> bool:
        deleted = session.execute(_RELEASE_SQL, {"k": lease_key(symbol, account_id), "w": worker_id})
        return deleted.rowcount > 0

    return _run(_release, db)


def sweep_expired(*, db: Session | None = None) -> int:
    """清理过期锁行（崩溃残留垃圾）；换主不依赖本函数，调用方可低频顺手执行"""
    return _run(lambda session: session.execute(_SWEEP_SQL, {"now": time.time()}).rowcount, db)
