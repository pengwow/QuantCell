"""Account / Credential 数据模型。

ponytail: Account 不含 secret（list 友好，仅 id/name/exchange/created_at）
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Account:
    """账号（不含 secret）。"""
    id: UUID
    name: str
    exchange: str
    created_at: datetime


@dataclass
class DecryptedCredential:
    """解密的凭证（仅 CredentialsService.get_credential 返回）。"""
    api_key: str
    api_secret: str
