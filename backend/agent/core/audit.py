"""Agent 工具调用审计（P2-06）。

- record_tool_call：工具执行后落库（agent_tool_audit），失败仅记日志不阻断工具执行；
- redact_secrets：递归脱敏参数/结果中疑似密钥的键值；
- agent_caller：请求级调用方上下文（由认证层 set，registry/审计读取）。
"""

import hashlib
import json
from contextvars import ContextVar
from typing import Any

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# (user, token_src, scope)：token_src 为 "jwt" 或 "#<id>"；scope 为 "read"/"write"/"full"
agent_caller: ContextVar[tuple[str, str, str] | None] = ContextVar("agent_caller", default=None)

# 键名包含这些片段即视为敏感（宁可多脱敏）
_SECRET_KEY_PARTS = ("api_key", "apikey", "secret", "token", "password", "passwd", "authorization")

_REDACTED = "***"
# ponytail: 递归脱敏的深度上限，参数对象不该比这更深；真有需要再改成显式遍历
_MAX_DEPTH = 8
# 密钥不应完整落库
_MAX_ARGS_JSON_LENGTH = 4000


def redact_secrets(value: Any, _depth: int = 0) -> Any:
    """递归脱敏：dict 中键名命中敏感片段的值替换为 ***，其余结构原样复制。"""
    if _depth >= _MAX_DEPTH:
        return _REDACTED
    if isinstance(value, dict):
        return {
            k: (_REDACTED if any(p in str(k).lower() for p in _SECRET_KEY_PARTS) else redact_secrets(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(v, _depth + 1) for v in value]
    return value


def args_digest(params: Any) -> str:
    """参数规范化摘要：sha256(排序键 JSON)。参数不可序列化时退化为空摘要。"""
    try:
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError, ValueError:
        return ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_tool_call(tool: str, params: Any, result_status: str, duration_ms: int | None = None) -> None:
    """审计一条工具调用。数据库未初始化（单测/极早期调用）时降级为仅日志。"""
    caller = agent_caller.get()
    user, token_src, _scope = caller or (None, None, None)
    try:
        args_json = json.dumps(redact_secrets(params), ensure_ascii=False, default=str)[:_MAX_ARGS_JSON_LENGTH]
    except TypeError, ValueError:
        args_json = None

    payload = {
        "tool": tool,
        "args_hash": args_digest(params) or None,
        "args_redacted": args_json,
        "result_status": result_status,
        "user": user or None,
        "token": token_src,
        "duration_ms": duration_ms,
    }
    try:
        # 函数内 import：SessionLocal 初始无 bind，运行期读模块属性 + 检测 bind，
        # 未初始化（单测替换模块属性为测试替身的通道）时降级为仅日志
        from collector.db.database import SessionLocal

        if SessionLocal is None or SessionLocal.kw.get("bind") is None:
            logger.debug(f"审计跳过（数据库未初始化）: tool={tool} status={result_status}")
            return
        from agent.models import AgentToolAudit

        with SessionLocal() as db:
            db.add(AgentToolAudit(**payload))
            db.commit()
    except Exception as e:
        logger.warning(f"工具审计落库失败: tool={tool} err={e}")
