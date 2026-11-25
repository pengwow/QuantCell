"""Agent 工具调用审计（P2-06）。

- record_tool_call：工具执行后落库（agent_tool_audit），失败仅记日志不阻断工具执行；
- redact_secrets：递归脱敏参数/结果中疑似密钥的键值；
- agent_caller：请求级调用方上下文（由认证层 set，registry/审计读取）。
"""

import hashlib
import json
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

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


# ---------- 查询侧（/audit 审计 Tab） ----------

# limit 上限：超出按此截断而非报错（前端传大值不会 422）
MAX_LIMIT = 500


def parse_time_bound(value: str | None, *, name: str = "time") -> datetime | None:
    """解析时间边界：ISO8601（可带 Z/偏移）或 epoch 秒/毫秒，统一为 UTC naive。

    库列 created_at 为 UTC naive（SQLite func.now()），比较前必须对齐口径；
    无时区的 ISO 串按 UTC 解释。
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        num = float(raw)
    except ValueError:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"{name} 需为 ISO8601 或 epoch 秒/毫秒: {value!r}") from exc
        return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt
    # ponytail: 按量级区分秒/毫秒（>=1e11 视为毫秒；1e11 秒≈5138 年，正常时间戳达不到）
    ts = num / 1000 if abs(num) >= 1e11 else num
    try:
        return datetime.fromtimestamp(ts, UTC).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{name} 超出可解析范围: {value!r}") from exc


def query_tool_calls(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    tool: str | None = None,
    result_status: str | None = None,
    user: str | None = None,
    token: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """分页查询工具调用审计（agent_tool_audit），created_at 倒序。

    tool 为前缀匹配（传完整工具名即精确）。args_redacted 落库时已脱敏，原样返回。
    返回 (满足条件的总数, 当前页记录)；数据库未初始化时返回 (0, [])。
    """
    # 函数内 import：SessionLocal 初始无 bind，运行期读模块属性（测试替换通道同 record_tool_call）
    from collector.db.database import SessionLocal

    if SessionLocal is None or SessionLocal.kw.get("bind") is None:
        return 0, []

    from agent.models import AgentToolAudit

    conds = []
    if start is not None:
        conds.append(AgentToolAudit.created_at >= start)
    if end is not None:
        conds.append(AgentToolAudit.created_at <= end)
    if tool:
        conds.append(AgentToolAudit.tool.startswith(tool, autoescape=True))
    if result_status:
        conds.append(AgentToolAudit.result_status == result_status)
    if user:
        conds.append(AgentToolAudit.user == user)
    if token:
        conds.append(AgentToolAudit.token == token)

    limit = max(1, min(limit, MAX_LIMIT))
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(AgentToolAudit).where(*conds)) or 0
        rows = db.scalars(
            select(AgentToolAudit)
            .where(*conds)
            # ponytail: SQLite func.now() 只到秒，同秒内用 id 兜底保证翻页稳定
            .order_by(AgentToolAudit.created_at.desc(), AgentToolAudit.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        # 会话内取值成 dict：避免回传 detached ORM 实例后的懒加载
        def _iso_utc(v):
            """库存 UTC naive（SQLite func.now()）→ 带 Z 的 ISO 串。

            前端 formatTimestamp 按 ISO 解析并本地化；无 Z 会被当本地时间
            显示差 8 小时（AuditTab 历史缺陷）。
            """
            if v is None:
                return None
            if isinstance(v, datetime):
                # DATETIME 列此处为 naive UTC；若未来换有时区后端可直接透传
                return v.isoformat() + ("" if v.tzinfo else "Z")
            s = str(v)
            return s if s.endswith(("Z", "+00:00")) else f"{s}Z"

        items = [
            {
                "id": r.id,
                "tool": r.tool,
                "args_hash": r.args_hash,
                "args_redacted": r.args_redacted,
                "result_status": r.result_status,
                "user": r.user,
                "token": r.token,
                "duration_ms": r.duration_ms,
                "created_at": _iso_utc(r.created_at),
            }
            for r in rows
        ]
    return total, items
