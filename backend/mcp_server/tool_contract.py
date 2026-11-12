"""MCP 工具契约（P2-04）：agent 工具风险分级 → MCP ToolAnnotations 映射，
只读白名单筛选与数量上限。

跟随 ToolRegistry 的实际工具面走：registry 新增/调整工具时 MCP 侧自动跟随，
无需维护第二份白名单（方案定位"代理既有服务，不新建能力"）。
"""

from typing import Any

from mcp.types import Tool as McpTool
from mcp.types import ToolAnnotations

from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# MCP Server 单实例暴露的工具数量上限（方案验收条目），超出截断并告警
MAX_MCP_TOOLS = 30

# write 工具二次确认的参数名：调用方必须在 arguments 中显式带 confirm=true
CONFIRM_FIELD = "confirm"


def mcp_tool_annotations(risk_level: str) -> ToolAnnotations:
    """风险分级 → MCP 注解 hints。read 天然幂等；write 不幂等也无破坏性；
    destructive 只标 dangerous（MCP 永不暴露，仅保持映射完备）。"""
    return ToolAnnotations(
        read_only_hint=(risk_level == "read"),
        destructive_hint=(risk_level == "dangerous"),
        # ponytail: read 一律视为幂等——QuantCell 工具面 read 即无副作用，重复执行结果不变
        idempotent_hint=(risk_level == "read"),
    )


def select_mcp_tools(registry: ToolRegistry, include_write: bool = False) -> list[Tool]:
    """MCP 可暴露工具筛选：read 必留；write 仅在 include_write 时纳入；dangerous
    一律剔除（即使 registry 处于信任模式——MCP 是外部入口，面要更严）。"""
    allowed_risks = ("read", "write") if include_write else ("read",)
    tools = [
        tool
        for name in registry.tool_names
        if (tool := registry.get(name)) is not None and tool.risk_level in allowed_risks
    ]
    if len(tools) > MAX_MCP_TOOLS:
        logger.warning(f"MCP 工具数 {len(tools)} 超过上限 {MAX_MCP_TOOLS}，已截断")
        tools = tools[:MAX_MCP_TOOLS]
    return tools


def build_mcp_tool(tool: Tool) -> McpTool:
    """agent Tool → MCP Tool 定义。inputSchema 直接复用工具自身的 JSON Schema，
    保证与 Chat completion / registry 侧参数校验一致。"""
    return McpTool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.parameters,
        annotations=mcp_tool_annotations(tool.risk_level),
    )


def write_has_confirmation(arguments: dict[str, Any] | None) -> bool:
    """write 工具调用是否已带显式二次确认标记。"""
    return bool(arguments) and arguments.get(CONFIRM_FIELD) is True
