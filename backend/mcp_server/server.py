"""MCP Server 装配（P2-04）：mcp 2.x 低级 Server + stdio 传输，代理 ToolRegistry。

不用 MCPServer 高级 API：其按函数签名推导 inputSchema，无法复用 agent Tool 已有的
JSON Schema 与风险分级；低级 Server 的 (ctx, params) 处理器恰好贴合"代理既有工具面"。
核心调用逻辑抽为 handle_list_tools / handle_call_tool 纯函数，build_server 只做闭包
装配——单测直接打纯函数即可，无需起进程。
"""

import os
import sys
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from agent.core.audit import agent_caller
from agent.tools import create_registry
from agent.tools.registry import ToolRegistry
from mcp_server.security import redact_secrets_text
from mcp_server.tool_contract import (
    CONFIRM_FIELD,
    build_mcp_tool,
    select_mcp_tools,
    write_has_confirmation,
)
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)


# registry 约定的失败形态：参数/执行类错误以"错误"开头；异常包装含"时出错"；
# 被拦截的操作描述含"需要人工确认"。按这些特征标 isError，让 MCP 客户端可感知失败
# 而不是当成功文本渲染
def _is_error_result(text: str) -> bool:
    return text.startswith("错误") or "时出错" in text or "需要人工确认" in text


def handle_list_tools(registry: ToolRegistry, include_write: bool) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[build_mcp_tool(t) for t in select_mcp_tools(registry, include_write)])


async def handle_call_tool(
    registry: ToolRegistry, include_write: bool, name: str, arguments: dict[str, Any] | None
) -> types.CallToolResult:
    """单次工具调用的 MCP 层处理：存在性 → 风险护栏 → 代理执行 → 脱敏出站。"""

    def _error(text: str) -> types.CallToolResult:
        # 记录日志便于运维排查，正文原样给客户端
        logger.warning(f"[MCP] 工具调用被拒: name={name} reason={text}")
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=True)

    tool = registry.get(name)
    if tool is None:
        return _error(f"错误: 工具 '{name}' 不存在，请核对 tools/list 返回的工具清单。")

    # MCP 层第一道护栏（registry 内还有第二道，防未来 registry 放开白名单时这里漏防）：
    if tool.risk_level == "dangerous":
        return _error(f"错误: 工具 '{name}' 属危险操作，MCP 通道不提供此类工具。")
    if tool.risk_level == "write":
        # 暴露开关与调用双重校验：未开启时即使盲调工具名也不可执行（纵深防御）
        if not include_write:
            return _error(f"错误: 工具 '{name}' 为写操作，本实例未开启 QUANTCELL_MCP_ENABLE_WRITE，不能通过 MCP 调用。")
        if not write_has_confirmation(arguments):
            return _error(
                f"错误: 工具 '{name}' 会产生写副作用，需要二次确认：请在 arguments 中加入 {CONFIRM_FIELD}=true 后重试。"
            )

    # confirm 只是 MCP 客户端与本层的握手标记，不属于工具本身的参数，执行前剥掉
    clean_args = dict(arguments or {})
    clean_args.pop(CONFIRM_FIELD, None)

    try:
        result = await registry.execute(name, clean_args)
    except Exception as e:  # 理论上 registry 已兜底，这里防 handler 层意外直接炸断会话
        logger.error(f"[MCP] 工具 {name} 执行抛出未捕获异常: {e}")
        return _error(f"执行 {name} 时出错: {e}")

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=redact_secrets_text(result))],
        is_error=_is_error_result(result),
    )


def build_server(registry: ToolRegistry, include_write: bool = False) -> Server:
    """构建 MCP Server：list/call 处理器闭包共享同一份 registry 实例。"""

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return handle_list_tools(registry, include_write)

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        return await handle_call_tool(registry, include_write, params.name, params.arguments)

    return Server("quantcell", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def serve(registry: ToolRegistry | None = None) -> None:
    """stdio 入口：Agent Token 认证 → 注入调用方上下文 → 装配 → 起 stdio 传输。"""
    # 函数内 import：agent.tokens 顶层链路会拉 fastapi 等 API 侧依赖，stdio 场景
    # 延迟到启动期；未携带合法令牌时在读到 DB 前即快速失败
    from agent.tokens import TOKEN_PREFIX, authenticate_agent_token

    raw_token = os.environ.get("QUANTCELL_MCP_TOKEN", "")
    if not raw_token.startswith(TOKEN_PREFIX):
        logger.error("QUANTCELL_MCP_TOKEN 未设置或缺少 qctk_ 前缀，MCP Server 拒绝启动")
        sys.exit(2)
    token = authenticate_agent_token(raw_token)
    if token is None:
        logger.error("QUANTCELL_MCP_TOKEN 认证失败（无效/已撤销/已过期），MCP Server 拒绝启动")
        sys.exit(2)

    # 与 P2-06 审计链路一致：registry 拦截判定与审计落库的 user/token/scope 来源
    agent_caller.set((token.name, f"#{token.id}", token.scope))

    enable_write = os.environ.get("QUANTCELL_MCP_ENABLE_WRITE", "") == "1"
    if registry is None:
        registry = create_registry()

    server = build_server(registry, include_write=enable_write)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
