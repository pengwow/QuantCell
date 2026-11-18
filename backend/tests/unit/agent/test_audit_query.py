"""P2-06 审计查询侧单测：分页、tool/status 过滤、时间边界、空结果、路由包装。

沿用 conftest.py 的 in-memory 库夹具（agent_db_engine 为 session 级，行会跨用例累积），
每个用例先用 audit_factory 清表，保证「无过滤」语义可断言。
"""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from agent.core.audit import parse_time_bound, query_tool_calls
from agent.models import AgentToolAudit


@pytest.fixture
def audit_factory(agent_session_factory):
    """清空审计表，返回 sessionmaker（service 已通过 monkeypatch 打到测试库）。"""
    with agent_session_factory() as db:
        db.query(AgentToolAudit).delete()
        db.commit()
    return agent_session_factory


def _add(
    factory,
    tool: str,
    *,
    status: str = "success",
    created_at: datetime,
    user: str | None = None,
    token: str | None = None,
    duration_ms: int | None = None,
) -> None:
    with factory() as db:
        db.add(
            AgentToolAudit(
                tool=tool,
                args_hash="h" * 64,
                args_redacted='{"symbol": "BTC/USDT", "api_key": "***"}',
                result_status=status,
                user=user,
                token=token,
                duration_ms=duration_ms,
                created_at=created_at,
            )
        )
        db.commit()


def _dt(day: int, hour: int = 0) -> datetime:
    """UTC naive，与库列口径一致。"""
    return datetime(2026, 1, day, hour)


class TestQueryToolCalls:
    def test_pagination_without_filters(self, audit_factory):
        for i in range(5):
            _add(audit_factory, "get_klines", created_at=_dt(1, i))
        total, page1 = query_tool_calls(limit=2, offset=0)
        total2, page2 = query_tool_calls(limit=2, offset=2)
        assert total == 5
        assert total2 == 5
        assert len(page1) == 2
        assert len(page2) == 2
        # created_at desc：第 1 页最新（hour=4,3）
        assert page1[0]["created_at"] == _dt(1, 4)
        assert page1[1]["created_at"] == _dt(1, 3)
        assert page2[0]["created_at"] == _dt(1, 2)
        # 返回字段与 ORM 列一致
        assert set(page1[0]) == {
            "id",
            "tool",
            "args_hash",
            "args_redacted",
            "result_status",
            "user",
            "token",
            "duration_ms",
            "created_at",
        }

    def test_tool_prefix_and_status_filter(self, audit_factory):
        _add(audit_factory, "get_klines", status="success", created_at=_dt(2))
        _add(audit_factory, "get_balance", status="error", created_at=_dt(2))
        _add(audit_factory, "write_file", status="success", created_at=_dt(2))

        total, rows = query_tool_calls(tool="get_")
        assert total == 2
        assert {r["tool"] for r in rows} == {"get_klines", "get_balance"}

        # 前缀 + 状态组合
        total, rows = query_tool_calls(tool="get_", result_status="error")
        assert total == 1
        assert rows[0]["tool"] == "get_balance"

        # 传完整工具名即精确（仍是前缀特例）
        total, rows = query_tool_calls(tool="get_klines")
        assert total == 1
        assert rows[0]["tool"] == "get_klines"

    def test_user_and_token_filter(self, audit_factory):
        _add(audit_factory, "exec", created_at=_dt(3), user="alice", token="jwt")
        _add(audit_factory, "exec", created_at=_dt(3), user="bot", token="#7")

        assert query_tool_calls(user="alice")[0] == 1
        total, rows = query_tool_calls(token="#7")
        assert total == 1
        assert rows[0]["user"] == "bot"

    def test_time_bounds_are_inclusive(self, audit_factory):
        _add(audit_factory, "t", created_at=_dt(10, 0))
        _add(audit_factory, "t", created_at=_dt(10, 12))
        _add(audit_factory, "t", created_at=_dt(11, 0))

        # 左闭右闭：恰好落在边界的行都包含
        total, rows = query_tool_calls(start=_dt(10, 0), end=_dt(10, 12))
        assert total == 2
        assert [r["created_at"] for r in rows] == [_dt(10, 12), _dt(10, 0)]

        # 只给 start
        assert query_tool_calls(start=_dt(10, 12))[0] == 2
        # 只给 end
        assert query_tool_calls(end=_dt(10, 0))[0] == 1
        # 区间外
        assert query_tool_calls(start=_dt(12), end=_dt(13))[0] == 0

    def test_empty_result(self, audit_factory):
        _add(audit_factory, "get_klines", created_at=_dt(5))
        total, rows = query_tool_calls(tool="no_such_tool")
        assert (total, rows) == (0, [])

    def test_limit_clamped_to_max(self, audit_factory):
        # 上限截断而非报错：limit 超界按 _MAX_LIMIT 处理（此处只验证不抛且 <= 上限）
        for i in range(3):
            _add(audit_factory, "t", created_at=_dt(6, i))
        total, rows = query_tool_calls(limit=10_000)
        assert total == 3
        assert len(rows) == 3


class TestParseTimeBound:
    def test_iso_and_epoch_forms_agree(self):
        iso = parse_time_bound("2026-01-10T00:00:00")
        assert iso == _dt(10)
        assert parse_time_bound("2026-01-10T00:00:00Z") == iso
        assert parse_time_bound("2026-01-10T08:00:00+08:00") == iso
        epoch = int(iso.replace(tzinfo=UTC).timestamp())
        assert parse_time_bound(str(epoch)) == iso  # epoch 秒
        assert parse_time_bound(str(epoch * 1000)) == iso  # epoch 毫秒

    def test_none_and_blank(self):
        assert parse_time_bound(None) is None
        assert parse_time_bound("  ") is None

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_time_bound("not-a-time", name="start")


class TestAuditRoute:
    """直接调用路由函数（绕过 FastAPI 默认值注入，参数全部显式传入）。"""

    @staticmethod
    def _call(**overrides):
        from agent.api.routes import list_tool_audit

        params = {
            "start": None,
            "end": None,
            "tool": None,
            "result_status": None,
            "user": None,
            "token": None,
            "limit": 50,
            "offset": 0,
        }
        params.update(overrides)
        return asyncio.run(list_tool_audit(**params))

    def test_route_wraps_pagination(self, audit_factory):
        _add(audit_factory, "get_klines", created_at=_dt(20))
        _add(audit_factory, "exec", created_at=_dt(21), status="error")

        body = self._call(limit=1, offset=0)
        assert body["success"] is True
        assert body["total"] == 2
        assert body["limit"] == 1
        assert body["offset"] == 0
        assert [r["tool"] for r in body["audits"]] == ["exec"]

        # ISO 字符串参数经路由解析后生效
        body = self._call(start="2026-01-20T00:00:00", end="2026-01-20T23:59:59")
        assert body["total"] == 1
        assert body["audits"][0]["tool"] == "get_klines"

    def test_route_rejects_bad_time(self, audit_factory):
        with pytest.raises(HTTPException) as exc:
            self._call(start="2026-13-45")
        assert exc.value.status_code == 400

    def test_route_reports_clamped_limit(self, audit_factory):
        _add(audit_factory, "get_klines", created_at=_dt(22))
        body = self._call(limit=10_000)
        assert body["limit"] == 500

    def test_args_redacted_returned_as_stored(self, audit_factory):
        _add(audit_factory, "get_klines", created_at=_dt(22))
        body = self._call()
        assert "***" in body["audits"][0]["args_redacted"]
        assert "sk-secret" not in body["audits"][0]["args_redacted"]
