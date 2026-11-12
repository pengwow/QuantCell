"""Agent 模块数据模型（P2-06）：Agent Token 与工具调用审计表。

存放于独立模块以便加入 collector.db 的模型导入清单（与 universe.models 同模式）。
"""

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from collector.db.database import Base


class AgentToken(Base):
    """代理访问令牌：供外部 Agent（MCP 等调用方）以 token 而非用户 JWT 访问。

    仅存 token 的 sha256 摘要，明文只在签发响应中出现一次。
    expires_at / last_used_at / created_at 均为 UTC naive（与 SQLite func.now() 口径一致）。
    """

    __tablename__ = "agent_tokens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    # sha256(raw_token) 的十六进制摘要，64 字符
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    # read：仅调用只读工具；write：允许执行有副作用的工具
    scope = Column(String(20), nullable=False, default="read", index=True)
    # NULL 表示永不过期
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    use_count = Column(Integer, nullable=False, default=0)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AgentToolAudit(Base):
    """Agent 工具调用审计：工具名、参数摘要/脱敏原文、结果状态、调用方身份。

    args_hash 用于等幂比对（sha256(canonical json)），args_redacted 存脱敏后 JSON
    以便问题排查不落明文密钥。
    """

    __tablename__ = "agent_tool_audit"

    id = Column(Integer, primary_key=True, index=True)
    tool = Column(String(100), nullable=False, index=True)
    args_hash = Column(String(64), nullable=True)
    args_redacted = Column(Text, nullable=True)
    result_status = Column(String(20), nullable=False, default="success", index=True)
    # 调用方：JWT 用户 sub 或 agent_token 名称
    user = Column(String(100), nullable=True)
    # 令牌来源标识："jwt" 或 "#<token_id>"
    token = Column(String(50), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
