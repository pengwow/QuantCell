"""P2-06 Agent Token 认证单测：签发/用量/过期/撤销/风险分级拦截。"""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta

import pytest

from agent.core.audit import agent_caller
from agent.models import AgentToken
from agent.tokens import TOKEN_PREFIX, authenticate_agent_token, hash_token


def _make_token(factory, *, scope="read", days=None, revoked=False) -> str:
    """直接造一条 token 记录并返回明文（绕过路由层，聚焦 service 语义）。"""
    raw = TOKEN_PREFIX + secrets.token_hex(20)
    with factory() as db:
        db.add(
            AgentToken(
                name="t1",
                token_hash=hash_token(raw),
                scope=scope,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=days) if days else None,
                revoked_at=datetime.now(UTC).replace(tzinfo=None) if revoked else None,
            )
        )
        db.commit()
    return raw


class TestAuthenticateAgentToken:
    def test_valid_token_passes_and_counts_usage(self, agent_session_factory):
        raw = _make_token(agent_session_factory)
        row = authenticate_agent_token(raw)
        assert row is not None
        assert row.use_count == 1
        assert row.last_used_at is not None

    def test_wrong_token_rejected(self, agent_session_factory):
        _make_token(agent_session_factory)
        assert authenticate_agent_token(TOKEN_PREFIX + "b" * 40) is None

    def test_expired_token_rejected(self, agent_session_factory):
        raw = _make_token(agent_session_factory, days=-1)
        assert authenticate_agent_token(raw) is None

    def test_revoked_token_rejected(self, agent_session_factory):
        raw = _make_token(agent_session_factory, revoked=True)
        assert authenticate_agent_token(raw) is None

    def test_expired_token_rejected_401_semantics(self, agent_session_factory):
        """过期令牌必须等效于无效令牌（401 路径的 service 判定来源）。"""
        raw = _make_token(agent_session_factory, days=-1)
        assert authenticate_agent_token(raw) is None


class TestRiskGating:
    def test_exec_tool_marked_dangerous(self):
        from agent.tools.shell import ExecTool

        assert ExecTool.risk_level == "dangerous"
        assert ExecTool.requires_approval is True

    def test_write_file_tool_marked_write(self):
        from agent.tools.filesystem import WriteFileTool

        assert WriteFileTool.risk_level == "write"

    def test_registry_blocks_dangerous_by_default(self, agent_session_factory, tmp_path):
        """dangerous 工具默认拦截（人工确认语义），并留下 blocked_approval 审计。"""
        from agent.tools.registry import ToolRegistry
        from agent.tools.shell import ExecTool

        registry = ToolRegistry()
        registry.register(ExecTool(working_dir=str(tmp_path)))
        result = asyncio.run(registry.execute("exec", {"command": "echo hi"}))
        assert "人工确认" in result

    def test_registry_allows_dangerous_in_trust_mode(self, agent_session_factory, tmp_path):
        from agent.tools.registry import ToolRegistry
        from agent.tools.shell import ExecTool

        registry = ToolRegistry(allow_dangerous=True)
        registry.register(ExecTool(working_dir=str(tmp_path)))
        result = asyncio.run(registry.execute("exec", {"command": f"echo hi > {tmp_path / 'out.txt'}"}))
        # 信任模式下放行，不再有人工确认拦截文案（重定向后 stdout 为空，以行为差异点断言）
        assert "人工确认" not in result

    def test_read_scope_blocks_write_tool(self, agent_session_factory, tmp_path):
        """read scope 的调用方不能执行 write 级工具（blocked_scope）。"""
        from agent.tools.filesystem import WriteFileTool
        from agent.tools.registry import ToolRegistry

        agent_caller.set(("bot", "#1", "read"))
        try:
            registry = ToolRegistry(allow_dangerous=True)
            registry.register(WriteFileTool(workspace=str(tmp_path)))
            target = tmp_path / "x.txt"
            result = asyncio.run(registry.execute("write_file", {"file_path": str(target), "content": "x"}))
            assert "只读权限" in result
            assert not target.exists()
        finally:
            agent_caller.set(None)


class TestAuditPersistence:
    def test_record_tool_call_persists(self, agent_session_factory):
        from agent.core.audit import record_tool_call
        from collector.db import database as db_module

        record_tool_call("get_klines", {"symbol": "BTC/USDT", "api_key": "sk-secret"}, "success", 12)
        # 直接用 ORM 类查询
        from agent.models import AgentToolAudit

        with db_module.SessionLocal() as db:
            row = db.query(AgentToolAudit).order_by(AgentToolAudit.id.desc()).first()
            assert row is not None
            assert row.tool == "get_klines"
            assert row.args_hash
            # 参数已落库且密钥被脱敏
            assert "BTC/USDT" in row.args_redacted
            assert "sk-secret" not in row.args_redacted
            assert "***" in row.args_redacted
