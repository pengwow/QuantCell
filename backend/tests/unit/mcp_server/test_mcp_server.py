"""P2-04 MCP Server 单测：工具筛选/注解映射/调用护栏/脱敏契约。

handler 逻辑抽成了纯函数（handle_list_tools / handle_call_tool），直接传 fake
registry + fake Tool 测试，不起 stdio 进程。async 用 pytest-asyncio 驱动。
"""

import pytest

from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from mcp_server.security import assert_code_size, redact_secrets, redact_secrets_text
from mcp_server.server import _is_error_result, handle_call_tool, handle_list_tools
from mcp_server.tool_contract import (
    MAX_MCP_TOOLS,
    build_mcp_tool,
    select_mcp_tools,
    write_has_confirmation,
)


class FakeTool(Tool):
    """壳工具：记录调用参数并返回固定结果，不触真实文件/网络。"""

    def __init__(
        self,
        name: str,
        description: str = "fake tool",
        risk_level: str = "read",
        result: str = "ok",
        parameters: dict | None = None,
    ):
        self._name = name
        self._description = description
        self.risk_level = risk_level
        self._result = result
        self._parameters = parameters or {"type": "object", "properties": {}}
        self.calls: list[dict] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self._result


def _registry(*tools: FakeTool, allow_dangerous: bool = False) -> ToolRegistry:
    registry = ToolRegistry(allow_dangerous=allow_dangerous)
    for tool in tools:
        registry.register(tool)
    return registry


# ---------- select_mcp_tools：只读白名单 ----------


def test_select_keeps_read_tools_by_default():
    registry = _registry(FakeTool("a"), FakeTool("b"))
    names = [t.name for t in select_mcp_tools(registry, include_write=False)]
    assert names == ["a", "b"]


def test_select_excludes_write_unless_enabled():
    registry = _registry(FakeTool("r"), FakeTool("w", risk_level="write"))
    assert [t.name for t in select_mcp_tools(registry, include_write=False)] == ["r"]
    assert sorted(t.name for t in select_mcp_tools(registry, include_write=True)) == ["r", "w"]


def test_select_never_exposes_dangerous():
    # registry 信任模式也不放行：MCP 是外部入口，暴露面要比内部 agent 更严
    registry = _registry(FakeTool("d", risk_level="dangerous"), allow_dangerous=True)
    assert select_mcp_tools(registry, include_write=True) == []


def test_select_truncates_to_max():
    registry = _registry(*(FakeTool(f"t{i:02d}") for i in range(MAX_MCP_TOOLS + 5)))
    assert len(select_mcp_tools(registry)) == MAX_MCP_TOOLS


# ---------- ToolAnnotations 映射 ----------


def test_build_mcp_tool_annotations():
    read_schema = build_mcp_tool(FakeTool("r"))
    assert read_schema.input_schema == {"type": "object", "properties": {}}
    assert read_schema.annotations.read_only_hint is True
    assert read_schema.annotations.destructive_hint is False
    assert read_schema.annotations.idempotent_hint is True

    write_schema = build_mcp_tool(FakeTool("w", risk_level="write"))
    assert write_schema.annotations.read_only_hint is False
    assert write_schema.annotations.destructive_hint is False
    assert write_schema.annotations.idempotent_hint is False

    dangerous_schema = build_mcp_tool(FakeTool("d", risk_level="dangerous"))
    assert dangerous_schema.annotations.destructive_hint is True


def test_write_has_confirmation():
    assert write_has_confirmation({"confirm": True}) is True
    assert write_has_confirmation({"confirm": "true"}) is False  # 必须是布尔，不接受字符串
    assert write_has_confirmation({}) is False
    assert write_has_confirmation(None) is False


# ---------- handle_list_tools ----------


def test_handle_list_tools_honors_whitelist():
    registry = _registry(FakeTool("r"), FakeTool("w", risk_level="write"))
    listed_off = handle_list_tools(registry, include_write=False)
    assert [t.name for t in listed_off.tools] == ["r"]

    listed_on = handle_list_tools(registry, include_write=True)
    assert sorted(t.name for t in listed_on.tools) == ["r", "w"]


# ---------- handle_call_tool：护栏与执行 ----------


async def test_call_unknown_tool_is_error():
    result = await handle_call_tool(_registry(FakeTool("r")), False, "nope", {})
    assert result.is_error is True
    assert "不存在" in result.content[0].text


async def test_call_read_tool_success():
    tool = FakeTool("r")
    result = await handle_call_tool(_registry(tool), False, "r", {"x": 1})
    assert result.is_error is False
    assert result.content[0].text == "ok"
    assert tool.calls == [{"x": 1}]


async def test_call_write_tool_requires_confirmation():
    tool = FakeTool("w", risk_level="write")
    registry = _registry(tool)
    denied = await handle_call_tool(registry, True, "w", {"path": "a.txt"})
    assert denied.is_error is True
    assert "二次确认" in denied.content[0].text
    assert tool.calls == []  # 未确认时绝不能真的执行

    allowed = await handle_call_tool(registry, True, "w", {"path": "a.txt", "confirm": True})
    assert allowed.is_error is False
    assert tool.calls == [{"path": "a.txt"}]  # confirm 是握手标记，不透传给工具


@pytest.mark.parametrize("enabled", [False, True], ids=["write_off", "write_on"])
async def test_call_dangerous_tool_always_denied(enabled):
    tool = FakeTool("d", risk_level="dangerous")
    result = await handle_call_tool(_registry(tool, allow_dangerous=True), enabled, "d", {"confirm": True})
    assert tool.calls == []
    assert result.is_error is True


async def test_call_write_tool_denied_when_include_write_off():
    # 未开启暴露开关时 write 工具即使带 confirm 也拒绝（纵深防御，防盲调工具名）
    tool = FakeTool("w", risk_level="write")
    result = await handle_call_tool(_registry(tool), False, "w", {"confirm": True})
    assert result.is_error is True
    assert "QUANTCELL_MCP_ENABLE_WRITE" in result.content[0].text
    assert tool.calls == []


# ---------- 出站脱敏与错误判定 ----------


def test_redact_secrets_structured():
    assert redact_secrets({"api_key": "x", "ok": 1}) == {"api_key": "***", "ok": 1}
    assert redact_secrets({"nested": [{"access_token": "t"}, "plain"]}) == {
        "nested": [{"access_token": "***"}, "plain"]
    }


def test_redact_secrets_text_patterns():
    masked = redact_secrets_text('config: "api_key": "sk-abc123", timeout=30')
    assert "sk-abc123" not in masked
    assert "timeout=30" in masked  # 非密钥键原样保留
    assert "a" * 41 not in redact_secrets_text("token = " + "a" * 41)  # token 赋值形态被打码
    leaked = "my key is qctk_" + "0123abcd" * 5
    assert leaked not in redact_secrets_text(leaked)
    assert redact_secrets_text("no secrets here") == "no secrets here"


def test_assert_code_size_bounds():
    assert assert_code_size("short") is None
    with pytest.raises(ValueError):  # 512 KiB 上限
        assert_code_size("x" * (512 * 1024 + 1))


def test_is_error_result_prefixes():
    assert _is_error_result("错误: boom") is True
    assert _is_error_result("执行 exec 时出错: x") is True
    assert _is_error_result("工具 'w' 被标记为危险操作，需要人工确认后才能执行") is True
    assert _is_error_result("ok result") is False
    assert _is_error_result("执行完成，共 3 条记录") is False  # "执行"并非都是失败
