"""SQLite 加密凭证表 CRUD。

ponytail: accounts + credentials 拆表（凭证可独立轮换）
         list_accounts 不返回 secret 字段（仅 id/name/exchange/created_at）
         软删除（deleted_at），保留 30 天可恢复
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from credentials.exceptions import AccountNotFoundError, AccountAlreadyExistsError


_SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    api_key_enc BLOB NOT NULL,
    api_secret_enc BLOB NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rotated_at TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    exchange TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (credential_id) REFERENCES credentials(id)
);

CREATE INDEX IF NOT EXISTS idx_accounts_name_active
    ON accounts(name) WHERE deleted_at IS NULL;
"""


def _now_iso() -> str:
    """ISO 8601 纳秒精度（项目规范：9 位小数，保留尾随零）。

    ponytail: Python 3.14.0 的 datetime.isoformat(timespec='nanoseconds') 实际未实现,
             所以手写格式化。UTC 时区 + 9 位小数,确保 1.0 ns 精度。
    """
    now = datetime.now(timezone.utc)
    # 微秒部分补 0 到 9 位（即纳秒精度，末 3 位为 0）
    micro = now.microsecond * 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{micro:09d}+00:00"


class CredentialsStore:
    """账号 + 凭证持久化（CRUD）。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_credential(
        self, api_key_enc: bytes, api_secret_enc: bytes, fingerprint_hash: str
    ) -> str:
        """新增凭证行，返回 credential_id（UUID4）。"""
        with self._conn() as conn:
            cred_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO credentials (id, api_key_enc, api_secret_enc, fingerprint_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cred_id, api_key_enc, api_secret_enc, fingerprint_hash, _now_iso()),
            )
        return cred_id

    def create_account(self, name: str, exchange: str, credential_id: str) -> str:
        """新增账号行，返回 account_id（UUID4）。

        重复名字（未软删）抛 AccountAlreadyExistsError。
        """
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM accounts WHERE name=? AND deleted_at IS NULL",
                (name,),
            ).fetchone()
            if existing:
                raise AccountAlreadyExistsError(f"账号已存在: {name}")
            acct_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO accounts (id, name, exchange, credential_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (acct_id, name, exchange, credential_id, _now_iso()),
            )
        return acct_id

    def get_account_by_name(self, name: str) -> dict:
        """按名字取账号（不含凭证原文）。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name, exchange, credential_id, created_at "
                "FROM accounts WHERE name=? AND deleted_at IS NULL",
                (name,),
            ).fetchone()
            if not row:
                raise AccountNotFoundError(f"账号不存在: {name}")
            return dict(row)

    def get_credential_by_account(self, name: str) -> dict:
        """按账号名取凭证（含加密字段）。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT c.id, c.api_key_enc, c.api_secret_enc, c.fingerprint_hash, c.created_at "
                "FROM credentials c "
                "JOIN accounts a ON a.credential_id = c.id "
                "WHERE a.name=? AND a.deleted_at IS NULL",
                (name,),
            ).fetchone()
            if not row:
                raise AccountNotFoundError(f"账号或凭证不存在: {name}")
            return dict(row)

    def list_accounts(self) -> list[dict]:
        """列出所有账号（不含 secret 字段）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, exchange, created_at FROM accounts "
                "WHERE deleted_at IS NULL ORDER BY created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def soft_delete_account(self, name: str) -> None:
        """软删除账号（deleted_at 置当前时间）。"""
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE accounts SET deleted_at=? WHERE name=? AND deleted_at IS NULL",
                (_now_iso(), name),
            )
            if result.rowcount == 0:
                raise AccountNotFoundError(f"账号不存在: {name}")
