"""Agent Token 签发/查询/撤销与认证（P2-06）。

明文 token 格式 `qctk_<40 hex>`，只在签发响应中出现一次；库存 sha256 摘要。
过期/已撤销令牌认证一律 401。用量口径：每次认证成功 use_count +1 并刷新 last_used_at
（ponytail: 直接每请求 UPDATE 一行，本地 SQLite 足够；高频外部调用再换缓存计数）。
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from config.capabilities import Capability, require_capability
from utils.db_session import get_db_session
from utils.logger import LogType, get_logger
from utils.rbac import Permission, require_permission

from .models import AgentToken

router = APIRouter(
    prefix="/api/v1/agent/tokens",
    tags=["agent-tokens"],
    # 签发属于写操作，默认组级别只读，逐端点再挂 AI_WRITE
    dependencies=[Depends(require_capability(Capability.AGENT_GATEWAY))],
)

TOKEN_PREFIX = "qctk_"

logger = get_logger(__name__, LogType.APPLICATION)


# ---------- service ----------


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    """DB 列为 UTC naive（SQLite func.now() 即 UTC），代码侧统一对齐。"""
    return datetime.now(UTC).replace(tzinfo=None)


def authenticate_agent_token(raw: str) -> AgentToken | None:
    """认证 raw token：摘要查表 + 撤销/过期判定，命中即累计一次用量。

    无法与 JWT 语义混用，非 qctk_ 前缀调用方不应进入本函数。
    """
    # 函数内 import：SessionLocal 初始无 bind，init_database_config 时才绑定 engine。
    # 顶层 import 拿到的是引用快照；运行期读模块属性 + 检测 bind，未初始化时正确返回 None
    from collector.db.database import SessionLocal

    if SessionLocal is None or SessionLocal.kw.get("bind") is None:
        return None
    with SessionLocal() as db:
        row = db.scalar(select(AgentToken).where(AgentToken.token_hash == hash_token(raw)))
        if row is None or row.revoked_at is not None:
            return None
        if row.expires_at is not None and row.expires_at < _utc_now():
            return None
        row.use_count += 1
        row.last_used_at = _utc_now()
        db.commit()
        db.refresh(row)
        return row


# ---------- 路由 ----------


class TokenIssueRequest(BaseModel):
    """签发请求"""

    name: str = Field(min_length=1, max_length=100, description="令牌名称，便于识别用途")
    scope: str = Field(default="read", pattern="^(read|write)$", description="read=只读工具，write=允许副作用工具")
    expires_days: int | None = Field(default=None, ge=1, le=3650, description="有效期天数，缺省永不过期")


class TokenIssueResponse(BaseModel):
    """签发响应：token 明文仅本次返回"""

    token: str
    id: int
    name: str
    scope: str
    expires_at: datetime | None


@router.post(
    "",
    summary="签发 Agent Token",
    description="生成新令牌，明文仅在响应中返回一次；expires_days 缺省表示永不过期。",
    dependencies=[Depends(require_permission(Permission.AI_WRITE))],
)
def issue_token_api(req: TokenIssueRequest) -> TokenIssueResponse:
    raw = TOKEN_PREFIX + secrets.token_hex(20)
    expires_at = _utc_now() + timedelta(days=req.expires_days) if req.expires_days else None
    with get_db_session() as db:
        row = AgentToken(
            name=req.name,
            token_hash=hash_token(raw),
            scope=req.scope,
            expires_at=expires_at,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info(f"签发 Agent Token: id={row.id} name={row.name} scope={row.scope}")
        return TokenIssueResponse(
            token=raw,
            id=row.id,
            name=row.name,
            scope=row.scope,
            expires_at=row.expires_at,
        )


@router.get(
    "",
    summary="Agent Token 列表",
    description="列出全部令牌及用量（不含摘要与明文），已撤销令牌保留供审计追溯。",
    dependencies=[Depends(require_permission(Permission.AI_READ))],
)
def list_tokens_api() -> list[dict]:
    with get_db_session() as db:
        rows = db.scalars(select(AgentToken).order_by(AgentToken.id)).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "scope": r.scope,
                "expires_at": r.expires_at,
                "last_used_at": r.last_used_at,
                "use_count": r.use_count,
                "revoked": r.revoked_at is not None,
                "created_at": r.created_at,
            }
            for r in rows
        ]


@router.delete(
    "/{token_id}",
    summary="撤销 Agent Token",
    description="软撤销（记 revoked_at），历史记录保留。幂等：重复撤销返回成功。",
    dependencies=[Depends(require_permission(Permission.AI_WRITE))],
)
def revoke_token_api(token_id: int) -> dict:
    with get_db_session() as db:
        row = db.get(AgentToken, token_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"令牌不存在: id={token_id}")
        if row.revoked_at is None:
            row.revoked_at = _utc_now()
            db.commit()
            logger.info(f"撤销 Agent Token: id={token_id} name={row.name}")
    return {"id": token_id, "revoked": True}
