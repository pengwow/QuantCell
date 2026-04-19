#!/usr/bin/env python3
"""
Agent 管理命令行工具

支持 Agent 会话管理、工具查询、对话交互等功能。
提供 HTTP API 和直接模块调用两种模式。

使用示例:
    # 列出所有会话
    python scripts/agent_cli.py session list

    # 创建新会话
    python scripts/agent_cli.py session create --name "测试会话"

    # 发送消息
    python scripts/agent_cli.py chat send "Hello" --session default

    # 交互式对话
    python scripts/agent_cli.py chat interactive

    # 列出所有工具
    python scripts/agent_cli.py tool list

    # 查看工作空间文件
    python scripts/agent_cli.py workspace list

环境变量:
    AGENT_API_URL: Agent API 地址，默认 http://localhost:8000
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin
from datetime import datetime

import typer
from typing_extensions import Annotated

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 创建主应用
app = typer.Typer(
    name="agent",
    help="Agent 管理命令行工具",
    add_completion=False,
)

# 创建子命令分组
session_app = typer.Typer(help="会话管理")
tool_app = typer.Typer(help="工具管理")
chat_app = typer.Typer(help="对话交互")
workspace_app = typer.Typer(help="工作空间管理")

app.add_typer(session_app, name="session")
app.add_typer(tool_app, name="tool")
app.add_typer(chat_app, name="chat")
app.add_typer(workspace_app, name="workspace")


class AgentCLIConfig:
    """CLI 配置"""

    def __init__(self):
        self.base_url = os.getenv("AGENT_API_URL", "http://localhost:8000")
        self.api_prefix = "/api/agent"
        self.workspace = Path(__file__).parent.parent / "agent_workspace"

    def get_api_url(self, path: str = "") -> str:
        """获取完整 API URL"""
        base = urljoin(self.base_url, self.api_prefix)
        if path:
            return urljoin(base + "/", path)
        return base


_config = AgentCLIConfig()


# 辅助函数
def _make_request(
    method: str,
    path: str,
    json_data: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    发送 HTTP 请求到 Agent API

    Args:
        method: HTTP 方法 (GET, POST, DELETE 等)
        path: API 路径
        json_data: JSON 请求体
        params: URL 参数

    Returns:
        API 响应数据

    Raises:
        typer.Exit: 请求失败时退出程序
    """
    try:
        import requests
    except ImportError:
        logger.error("请先安装 requests: pip install requests")
        raise typer.Exit(1)

    url = _config.get_api_url(path)
    logger.debug(f"{method} {url}")

    try:
        # 根据路径设置不同的超时时间
        # chat 接口可能需要较长时间（涉及工具调用）
        timeout = 120 if path == "chat" else 30
        
        response = requests.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        logger.error(f"无法连接到 Agent API: {_config.base_url}")
        logger.error("请确保后端服务已启动: uvicorn main:app --host 0.0.0.0 --port 8000")
        raise typer.Exit(1)
    except requests.exceptions.Timeout:
        logger.error("请求超时，请稍后重试")
        raise typer.Exit(1)
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_data = e.response.json()
            error_detail = error_data.get("detail", str(error_data))
        except:
            error_detail = str(e)
        logger.error(f"API 错误: {error_detail}")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"请求失败: {e}")
        raise typer.Exit(1)


def _print_json(data: Any) -> None:
    """以 JSON 格式打印数据"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _print_table(headers: List[str], rows: List[List[str]]) -> None:
    """以表格格式打印数据"""
    if not rows:
        print("(无数据)")
        return

    # 计算每列的最大宽度
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # 打印表头
    header_line = " | ".join(
        h.ljust(col_widths[i]) for i, h in enumerate(headers)
    )
    print(header_line)
    print("-" * len(header_line))

    # 打印数据行
    for row in rows:
        print(" | ".join(
            str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)
        ))


def _format_timestamp(timestamp: str) -> str:
    """格式化时间戳"""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return timestamp


# 会话管理命令
@session_app.command("list", help="列出所有会话")
def session_list(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="输出格式: json 或 table")
    ] = "table",
):
    """列出所有会话"""
    sessions = []
    
    # 尝试通过 API 获取会话列表
    try:
        data = _make_request("GET", "sessions")
        sessions = data.get("sessions", [])
    except Exception as e:
        # 如果 API 失败，尝试直接读取工作空间
        logger.debug(f"API 调用失败: {e}，尝试直接读取工作空间")
        sessions = _get_sessions_from_workspace()

    if not sessions:
        print("暂无会话")
        return

    if format == "json":
        _print_json(sessions)
    else:
        headers = ["ID", "名称", "更新时间"]
        rows = [
            [
                s.get("id", ""),
                s.get("name", "未命名"),
                _format_timestamp(s.get("updatedAt", "")),
            ]
            for s in sessions
        ]
        _print_table(headers, rows)
        print(f"\n共 {len(sessions)} 个会话")


def _get_sessions_from_workspace() -> List[Dict]:
    """从工作空间目录读取会话列表"""
    sessions = []
    workspace = _config.workspace / "sessions"
    if not workspace.exists():
        return sessions

    for session_file in workspace.glob("*.json"):
        try:
            import json
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                sessions.append({
                    "id": data.get("id", session_file.stem),
                    "name": data.get("name", "未命名"),
                    "createdAt": data.get("createdAt", ""),
                    "updatedAt": data.get("updatedAt", ""),
                })
        except Exception as e:
            logger.debug(f"读取会话文件失败 {session_file}: {e}")

    return sorted(sessions, key=lambda x: x.get("updatedAt", ""), reverse=True)


@session_app.command("info", help="查看会话详情")
def session_info(
    session_id: Annotated[str, typer.Argument(help="会话 ID")],
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="输出格式: json 或 table")
    ] = "table",
):
    """查看会话详情"""
    try:
        data = _make_request("GET", f"sessions/{session_id}")
        session = data.get("session", {})
    except:
        logger.error(f"获取会话 {session_id} 失败")
        raise typer.Exit(1)

    if format == "json":
        _print_json(session)
    else:
        print(f"会话 ID: {session.get('id')}")
        print(f"名称: {session.get('name')}")
        print(f"创建时间: {_format_timestamp(session.get('createdAt', ''))}")
        print(f"更新时间: {_format_timestamp(session.get('updatedAt', ''))}")
        print(f"消息数量: {session.get('messageCount', 0)}")


@session_app.command("create", help="创建新会话")
def session_create(
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="会话名称")
    ] = None,
):
    """创建新会话"""
    try:
        data = _make_request("POST", "sessions", json_data={"name": name})
        session = data.get("session", {})
        print(f"会话创建成功: {session.get('id')}")
        print(f"名称: {session.get('name')}")
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        raise typer.Exit(1)


@session_app.command("delete", help="删除会话")
def session_delete(
    session_id: Annotated[str, typer.Argument(help="会话 ID")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="强制删除，不提示确认")
    ] = False,
):
    """删除会话"""
    if not force:
        confirm = typer.confirm(f"确定要删除会话 {session_id} 吗？此操作不可恢复。")
        if not confirm:
            print("已取消")
            raise typer.Exit(0)

    try:
        _make_request("DELETE", f"sessions/{session_id}")
        print(f"会话 {session_id} 已删除")
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise typer.Exit(1)


@session_app.command("clear", help="清空会话历史")
def session_clear(
    session_id: Annotated[str, typer.Argument(help="会话 ID")],
):
    """清空会话历史消息"""
    try:
        _make_request("POST", f"sessions/{session_id}/clear")
        print(f"会话 {session_id} 的历史消息已清空")
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        raise typer.Exit(1)


# 工具管理命令
@tool_app.command("list", help="列出所有可用工具")
def tool_list(
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="输出格式: json 或 table")
    ] = "table",
):
    """列出所有可用工具"""
    try:
        data = _make_request("GET", "tools")
        tools = data.get("tools", [])
    except:
        # 如果 API 失败，尝试直接导入
        logger.debug("API 调用失败，尝试直接导入工具注册表")
        tools = _get_tools_from_registry()

    if not tools:
        print("暂无工具")
        return

    if format == "json":
        _print_json(tools)
    else:
        headers = ["名称", "描述"]
        rows = [
            [
                t.get("name", ""),
                t.get("description", "")[:50] + "..." if len(t.get("description", "")) > 50 else t.get("description", ""),
            ]
            for t in tools
        ]
        _print_table(headers, rows)
        print(f"\n共 {len(tools)} 个工具")


def _get_tools_from_registry() -> List[Dict]:
    """从工具注册表获取工具列表（使用统一的自动发现机制）"""
    try:
        from agent.tools import get_tool_list
        return get_tool_list()
    except Exception as e:
        logger.debug(f"获取工具列表失败: {e}")
        return []


@tool_app.command("info", help="查看工具详情")
def tool_info(
    tool_name: Annotated[str, typer.Argument(help="工具名称")],
):
    """查看工具详情"""
    try:
        from agent.tools import create_registry
        registry = create_registry()
        tool = registry.get(tool_name)

        if not tool:
            logger.error(f"工具 {tool_name} 不存在")
            print(f"错误: 工具 '{tool_name}' 不存在")
            print(f"可用工具: {', '.join(registry.tool_names)}")
            raise typer.Exit(1)

        print(f"工具名称: {tool_name}")
        print(f"描述: {tool.description}")
        print(f"类名: {tool.__class__.__name__}")
        print(f"模块: {tool.__class__.__module__}")
        
        # 显示构造参数信息
        print(f"配置:")
        workspace = getattr(tool, 'workspace', None)
        if workspace:
            print(f"  workspace: {workspace}")
        allowed_dir = getattr(tool, 'allowed_dir', None)
        if allowed_dir:
            is_restricted = allowed_dir != workspace
            restriction = "⚠️ 已限制" if is_restricted else "✅ 允许所有"
            print(f"  allowed_dir: {allowed_dir} ({restriction})")
        
        # 显示执行参数
        print(f"执行参数:")
        if hasattr(tool, 'parameters') and tool.parameters:
            params_schema = tool.parameters
            if isinstance(params_schema, dict):
                props = params_schema.get("properties", {})
                if props:
                    for param_name, param_info in props.items():
                        required = "必填" if param_name in params_schema.get("required", []) else "可选"
                        desc = param_info.get("description", "")
                        param_type = param_info.get("type", "unknown")
                        print(f"  - {param_name} [{param_type}]: {desc} ({required})")
                else:
                    print("  (无属性)")
            else:
                print(f"  {params_schema}")
        else:
            print("  (无参数)")
    except Exception as e:
        logger.error(f"获取工具信息失败: {e}")
        raise typer.Exit(1)


@tool_app.command("run", help="直接执行工具")
def tool_run(
    tool_name: Annotated[str, typer.Argument(help="工具名称")],
    params_str: Annotated[
        Optional[str],
        typer.Option("--params", "-p", help="工具参数 (JSON 格式)"),
    ] = None,
    allow_all: Annotated[
        bool,
        typer.Option("--allow-all", "-a", help="允许访问所有路径（绕过安全限制）"),
    ] = False,
):
    """直接执行指定工具并显示结果"""
    import asyncio
    import json
    from pathlib import Path

    async def _run():
        try:
            from agent.tools import create_registry
            
            # 如果 allow_all，设置 allowed_dir 为根目录
            if allow_all:
                registry = create_registry(allowed_dir=Path("/"))
            else:
                registry = create_registry()
        except Exception as e:
            print(f"错误: 无法初始化工具注册表 - {e}")
            raise typer.Exit(1)

        tool = registry.get(tool_name)
        if not tool:
            print(f"错误: 工具 '{tool_name}' 不存在")
            print(f"可用工具: {', '.join(registry.tool_names)}")
            raise typer.Exit(1)

        # 解析参数
        params = {}
        if params_str:
            try:
                params = json.loads(params_str)
                if not isinstance(params, dict):
                    print("错误: 参数必须是 JSON 对象")
                    raise typer.Exit(1)
            except json.JSONDecodeError as e:
                print(f"错误: JSON 解析失败 - {e}")
                raise typer.Exit(1)

        if allow_all:
            print(f"执行工具: {tool_name} [⚠️ 路径限制已禁用]")
        else:
            print(f"执行工具: {tool_name}")
        print("-" * 50)

        try:
            result = await registry.execute(tool_name, params)

            if isinstance(result, str) and result.startswith("错误"):
                print(f"\n执行失败")
                print(result)
            else:
                print(f"\n执行成功")
                print(result)

        except asyncio.CancelledError:
            print("\n操作已取消")
        except Exception as e:
            logger.error(f"执行工具失败: {e}")
            print(f"\n错误: {e}")
            raise typer.Exit(1)

    asyncio.run(_run())


# 对话交互命令
@chat_app.command("send", help="发送消息给 Agent")
def chat_send(
    message: Annotated[str, typer.Argument(help="消息内容")],
    session: Annotated[
        Optional[str],
        typer.Option("--session", "-s", help="会话 ID")
    ] = None,
):
    """发送消息给 Agent（process_direct 方式）"""
    import asyncio

    session_id = session or "default"

    async def _run():
        # 延迟导入避免循环导入
        try:
            from agent.api.routes import get_agent
            agent = get_agent()
        except Exception as e:
            print(f"错误: 无法初始化 Agent - {e}")
            raise typer.Exit(1)

        print(f"发送消息到会话 {session_id}...")
        print("-" * 50)

        # 进度回调 - 参考 nanobot 的 _cli_progress
        async def on_progress(content: str, *, tool_hint: bool = False):
            prefix = "  ↳ " if tool_hint else "  → "
            print(f"{prefix}{content}")

        try:
            # 使用 process_direct - 专门为 CLI/Cron 设计的接口
            response = await agent.process_direct(
                content=message,
                session_key=session_id,
                on_progress=on_progress,
            )

            print("-" * 50)
            if response:
                print(f"\nAgent 响应:\n{response}")
            else:
                print("\nAgent 无响应")

        except asyncio.CancelledError:
            print("\n操作已取消")
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            print(f"\n错误: {e}")
            raise typer.Exit(1)

    asyncio.run(_run())


@chat_app.command("interactive", help="交互式对话")
def chat_interactive(
    session: Annotated[
        Optional[str],
        typer.Option("--session", "-s", help="会话 ID")
    ] = None,
):
    """进入交互式对话模式（process_direct 方式）"""
    import asyncio
    import signal

    session_id = session or "default"

    async def _run():
        # 延迟导入避免循环导入
        try:
            from agent.api.routes import get_agent
            agent = get_agent()
        except Exception as e:
            print(f"错误: 无法初始化 Agent - {e}")
            raise typer.Exit(1)

        print(f"进入交互式对话模式 (会话: {session_id})")
        print("输入 'exit' 或 'quit' 退出对话，Ctrl+C 中断")
        print("-" * 50)

        # 进度回调 - _cli_progress
        async def on_progress(content: str, *, tool_hint: bool = False):
            prefix = "  ↳ " if tool_hint else "  → "
            print(f"{prefix}{content}")

        # 信号处理 - 优雅退出
        def handle_signal(signum, frame):
            print("\n\n收到中断信号，再见！")
            raise KeyboardInterrupt()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while True:
            try:
                user_input = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "退出"):
                print("再见！")
                break

            try:
                print("-" * 50)
                # 使用 process_direct - 专门为 CLI/Cron 设计的接口
                response = await agent.process_direct(
                    content=user_input,
                    session_key=session_id,
                    on_progress=on_progress,
                )
                print("-" * 50)
                if response:
                    print(f"\nAgent: {response}")
                else:
                    print("\nAgent 无响应")

            except asyncio.CancelledError:
                print("\n操作已取消")
                break
            except KeyboardInterrupt:
                print("\n再见！")
                break
            except Exception as e:
                logger.error(f"请求失败: {e}")
                print(f"错误: {e}，请重试")

    asyncio.run(_run())


@chat_app.command("history", help="查看会话历史")
def chat_history(
    session_id: Annotated[str, typer.Argument(help="会话 ID")],
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="显示消息数量")
    ] = 50,
):
    """查看会话历史消息"""
    try:
        data = _make_request("GET", f"sessions/{session_id}/history", params={"limit": limit})
        history = data.get("history", [])
        total = data.get("total_messages", 0)

        if not history:
            print("暂无历史消息")
            return

        print(f"会话 {session_id} 的历史消息 (显示 {len(history)}/{total}):\n")

        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = _format_timestamp(msg.get("timestamp", ""))

            role_display = {
                "user": "用户",
                "assistant": "Agent",
                "tool": "工具",
            }.get(role, role)

            print(f"[{timestamp}] {role_display}:")
            print(f"{content[:200]}{'...' if len(content) > 200 else ''}")
            print()

    except Exception as e:
        logger.error(f"获取历史消息失败: {e}")
        raise typer.Exit(1)


# 工作空间管理命令
@workspace_app.command("list", help="列出工作空间文件")
def workspace_list(
    path: Annotated[
        Optional[str],
        typer.Option("--path", "-p", help="子目录路径")
    ] = None,
):
    """列出工作空间文件"""
    target_path = _config.workspace
    if path:
        target_path = target_path / path

    if not target_path.exists():
        print(f"路径不存在: {target_path}")
        raise typer.Exit(1)

    try:
        import asyncio
        from agent.tools.filesystem import ListDirTool
        tool = ListDirTool(workspace=_config.workspace)
        
        # 同步执行
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(path=str(target_path))
        )

        if isinstance(result, str) and result.startswith("错误"):
            logger.error(f"列出文件失败: {result}")
            raise typer.Exit(1)

        data = json.loads(result) if isinstance(result, str) else {}
        files = data.get("files", [])
        directories = data.get("directories", [])

        if not files and not directories:
            print("(空目录)")
            return

        print(f"目录: {target_path}\n")

        if directories:
            print("子目录:")
            for d in directories:
                print(f"  [DIR] {d['name']}")
            print()

        if files:
            print("文件:")
            for f in files:
                size = f.get("size", 0)
                size_str = f"{size} B" if size < 1024 else f"{size/1024:.1f} KB"
                print(f"  {f['name']} ({size_str})")

    except Exception as e:
        logger.error(f"列出文件失败: {e}")
        raise typer.Exit(1)


@workspace_app.command("cat", help="查看文件内容")
def workspace_cat(
    file_path: Annotated[str, typer.Argument(help="文件路径")],
):
    """查看工作空间文件内容"""
    target_path = _config.workspace / file_path

    if not target_path.exists():
        logger.error(f"文件不存在: {file_path}")
        raise typer.Exit(1)

    if not target_path.is_file():
        logger.error(f"这不是一个文件: {file_path}")
        raise typer.Exit(1)

    try:
        import asyncio
        from agent.tools.filesystem import ReadFileTool
        tool = ReadFileTool(workspace=_config.workspace)
        
        result = asyncio.get_event_loop().run_until_complete(
            tool.execute(path=str(target_path))
        )

        if isinstance(result, str) and result.startswith("错误"):
            logger.error(f"读取文件失败: {result}")
            raise typer.Exit(1)

        print(result)

    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        raise typer.Exit(1)


@workspace_app.command("clean", help="清理工作空间")
def workspace_clean(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="强制清理，不提示确认")
    ] = False,
):
    """清理工作空间中的临时文件"""
    if not force:
        confirm = typer.confirm(
            "确定要清理工作空间吗？这将删除所有非会话文件。"
        )
        if not confirm:
            print("已取消")
            raise typer.Exit(0)

    try:
        import shutil

        cleaned = 0
        for item in _config.workspace.iterdir():
            # 保留 sessions 目录
            if item.name == "sessions":
                continue

            if item.is_file():
                item.unlink()
                cleaned += 1
            elif item.is_dir():
                shutil.rmtree(item)
                cleaned += 1

        print(f"已清理 {cleaned} 个文件/目录")

    except Exception as e:
        logger.error(f"清理工作空间失败: {e}")
        raise typer.Exit(1)


# ==================== 工具参数管理命令 ====================
params_app = typer.Typer(help="工具参数管理")
app.add_typer(params_app, name="params")


@params_app.command("tools", help="查看所有已注册的工具")
def params_tools():
    """显示所有工具及其参数配置状态"""
    from agent.config.manager import ToolParamManager

    tools = ToolParamManager.get_registered_tools()

    print("\n📋 已注册的工具:")
    print("=" * 60)

    for tool in tools:
        status_icon = "✅" if tool["has_required_params"] else "⚠️"
        print(f"\n{status_icon} {tool['name']}")
        print(f"   参数: {tool['configured_count']}/{tool['param_count']} 已配置")

    print()


@params_app.command("show", help="查看工具参数详情")
def params_show(
    tool_name: Annotated[str, typer.Argument(help="工具名称")],
    show_sensitive: Annotated[
        bool,
        typer.Option("--sensitive", "-s", help="显示敏感参数真实值")
    ] = False
):
    """显示工具的详细参数配置"""
    from agent.config.manager import ToolParamManager

    try:
        params = ToolParamManager.get_tool_params(
            tool_name,
            include_sensitive=show_sensitive
        )

        print(f"\n🔧 工具: {tool_name}")
        print("=" * 60)

        for param_name, info in params.items():
            sensitive_marker = "🔒" if info["sensitive"] else "  "
            source_icon = {
                "database": "💾",
                "environment": "🌍",
                "default": "⚙️"
            }.get(info["source"], "❓")

            print(f"\n{sensitive_marker} {param_name}")
            print(f"   值: {info['value']}")
            print(f"   来源: {source_icon} {info['source']}")
            print(f"   类型: {info['type']}")
            if info['description']:
                print(f"   说明: {info['description']}")

        print()

    except ValueError as e:
        print(f"❌ 错误: {e}")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"获取工具参数失败: {e}")
        print(f"❌ 错误: {e}")
        raise typer.Exit(1)


@params_app.command("set", help="设置工具参数")
def params_set(
    tool_name: Annotated[str, typer.Argument(help="工具名称")],
    param_name: Annotated[str, typer.Argument(help="参数名称")],
    value: Annotated[str, typer.Argument(help="参数值")]
):
    """设置工具参数"""
    from agent.config.manager import ToolParamManager

    try:
        success = ToolParamManager.set_tool_param(tool_name, param_name, value)

        if success:
            print(f"✅ 参数 {tool_name}.{param_name} 已更新")
        else:
            print("❌ 更新失败")
            raise typer.Exit(1)

    except ValueError as e:
        print(f"❌ 错误: {e}")
        raise typer.Exit(1)
    except Exception as e:
        logger.error(f"设置参数失败: {e}")
        print(f"❌ 错误: {e}")
        raise typer.Exit(1)


@params_app.command("delete", help="删除工具参数")
def params_delete(
    tool_name: Annotated[str, typer.Argument(help="工具名称")],
    param_name: Annotated[str, typer.Argument(help="参数名称")]
):
    """删除工具参数（恢复使用默认值或环境变量）"""
    from agent.config.manager import ToolParamManager

    success = ToolParamManager.delete_tool_param(tool_name, param_name)

    if success:
        print(f"✅ 参数 {tool_name}.{param_name} 已删除")
        print("   将使用环境变量或默认值")
    else:
        print("❌ 参数不存在")
        raise typer.Exit(1)


@params_app.command("import", help="从JSON文件导入配置")
def params_import(
    file_path: Annotated[str, typer.Argument(help="JSON文件路径")],
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-o", help="覆盖已有值")
    ] = False
):
    """从JSON文件导入配置"""
    import os.path
    from agent.config.manager import ToolParamManager

    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        raise typer.Exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    imported, skipped, errors = ToolParamManager.import_config(
        config, overwrite=overwrite
    )

    print(f"\n📦 导入完成:")
    print(f"   ✅ 成功: {imported} 个参数")
    print(f"   ⏭️  跳过: {skipped} 个参数")

    if errors:
        print(f"   ❌ 错误: {len(errors)} 个")
        for err in errors[:5]:
            print(f"      - {err}")


@params_app.command("export", help="导出配置到JSON文件")
def params_export(
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="输出文件路径")
    ] = None,
    tool_name: Annotated[
        Optional[str],
        typer.Option("--tool", "-t", help="指定工具名称")
    ] = None
):
    """导出配置到JSON文件（敏感值自动脱敏）"""
    from agent.config.manager import ToolParamManager

    config = ToolParamManager.export_config(tool_name)

    output_path = output or f"tool_params_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"✅ 配置已导出到: {output_path}")
    print("   注意: 敏感参数值已脱敏处理")


@params_app.command("validate", help="验证工具参数配置")
def params_validate(
    tool_name: Annotated[str, typer.Argument(help="工具名称")]
):
    """验证工具的必需参数是否都已配置"""
    from agent.config.templates import get_tool_template
    from agent.config.tool_params import ToolParamResolver

    template = get_tool_template(tool_name)

    if not template:
        print(f"❌ 未知工具: {tool_name}")
        raise typer.Exit(1)

    print(f"\n🔍 验证工具: {tool_name}")
    print("=" * 60)

    all_valid = True
    for param_name, meta in template.items():
        value = ToolParamResolver.resolve(tool_name, param_name)

        if meta.get("required") and not value:
            print(f"❌ {param_name}: 未配置 (必填)")
            all_valid = False
        elif value:
            print(f"✅ {param_name}: 已配置")
        else:
            print(f"⚪ {param_name}: 使用默认值")

    print()
    if all_valid:
        print("✅ 所有必要参数已正确配置")
    else:
        print("⚠️  存在未配置的必要参数，工具可能无法正常工作")


# 主入口
if __name__ == "__main__":
    app()
