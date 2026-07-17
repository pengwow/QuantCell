"""CredentialsService — 凭证管理业务编排。

ponytail: 仅 add_account 接受明文,其他接口全部返回 Account(无 secret)
         或 DecryptedCredential(显式解密)
"""
from datetime import datetime
from pathlib import Path
from uuid import UUID

from credentials.account import Account
from credentials.crypto import encrypt_secret, decrypt_secret, get_machine_fingerprint
from credentials.exceptions import AccountNotFoundError
from credentials.store import CredentialsStore


_DEFAULT_DB_PATH = "backend/data/credentials.db"


class CredentialsService:
    """凭证管理 service — 加密入库、列表去 secret、解密取凭证。"""

    def __init__(self, db_path: str | None = None, fingerprint: str | None = None):
        self.db_path = db_path or str(Path(_DEFAULT_DB_PATH))
        self.fingerprint = fingerprint or get_machine_fingerprint()
        self.store = CredentialsStore(self.db_path)

    def add_account(self, name: str, exchange: str, api_key: str, api_secret: str) -> Account:
        """新增账号（加密入库）。

        ponytail: 此方法是唯一接受明文 api_secret 的入口
        """
        cred_id = self.store.create_credential(
            encrypt_secret(api_key),
            encrypt_secret(api_secret),
            self.fingerprint,
        )
        acct_id = self.store.create_account(name, exchange, cred_id)
        return Account(
            id=UUID(acct_id),
            name=name,
            exchange=exchange,
            created_at=datetime.now(),
        )

    def get_credential(self, name: str) -> tuple[str, str]:
        """按账号名取凭证（自动解密），返回 (api_key, api_secret)。"""
        cred = self.store.get_credential_by_account(name)
        return (
            decrypt_secret(cred["api_key_enc"]),
            decrypt_secret(cred["api_secret_enc"]),
        )

    def list_accounts(self) -> list[Account]:
        """列出所有账号（不含 secret）。"""
        rows = self.store.list_accounts()
        return [
            Account(
                id=UUID(r["id"]),
                name=r["name"],
                exchange=r["exchange"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def remove_account(self, name: str) -> None:
        """软删除账号。"""
        self.store.soft_delete_account(name)
