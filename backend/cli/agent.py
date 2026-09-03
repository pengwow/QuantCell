#!/usr/bin/env python3
"""
Agent 管理 CLI

提供会话管理、工具管理、对话交互、工作空间、参数配置、高级操作等功能。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import typer

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

app = typer.Typer(help="Agent 管理命令行工具")

WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"


class SessionManager:
    """会话管理器"""

    def __init__(self):
        self._sessions = {}

    def list_sessions(self):
        """列出所有会话"""
        return list(self._sessions.values())

    def get_session_info(self, session_id: str):
        """获取会话信息"""
        return self._sessions.get(session_id)

    def create_session(self, name: str = ""):
        """创建新会话"""
        import uuid

        session_id = f"session-{uuid.uuid4().hex[:8]}"
        session = {
            "id": session_id,
            "name": name or f"会话 {session_id}",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "message_count": 0,
        }
        self._sessions[session_id] = session
        return session

    def delete(self, session_id: str):
        """删除会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def get_history(self, session_id: str):
        """获取会话历史"""
        return {"history": [], "total_messages": 0}

    def clear(self, session_id: str):
        """清空会话"""
        if session_id in self._sessions:
            self._sessions[session_id]["message_count"] = 0
            return True
        return False


def _get_tools_from_registry():
    """从注册表获取工具列表"""
    try:
        from agent.tools import create_registry

        registry = create_registry()
        tools = []
        for name in registry.tool_names:
            tool = registry.get(name)
            if tool:
                tools.append(
                    {
                        "name": name,
                        "description": getattr(tool, "description", ""),
                    }
                )
        return tools
    except Exception:
        return []


def _run_tool_async(tool_name: str, **kwargs):
    """异步运行工具"""

    async def _run():
        return None

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run())


# ==================== Session 命令组 ====================


def session_list(
    format: str = typer.Option("text", "--format", "-f", help="输出格式 (text/json)"),
):
    """列出所有会话"""
    sm = SessionManager()
    sessions = sm.list_sessions()

    if not sessions:
        typer.echo("暂无会话")
        return

    if format == "json":
        typer.echo(json.dumps(sessions, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"共 {len(sessions)} 个会话:")
        for s in sessions:
            typer.echo(f"  {s.get('key', s.get('id'))} - {s.get('updated_at', '')}")


def session_info(
    session_id: str = typer.Argument(..., help="会话ID"),
):
    """查看会话详情"""
    sm = SessionManager()
    info = sm.get_session_info(session_id)

    if info is None:
        typer.echo(f"会话 {session_id} 不存在")
        raise typer.Exit(1)

    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


def session_create(
    name: str = typer.Option("", "--name", "-n", help="会话名称"),
):
    """创建新会话"""
    sm = SessionManager()
    session = sm.create_session(name=name)
    typer.echo(f"会话已创建: {json.dumps(session, ensure_ascii=False)}")


def session_delete(
    session_id: str = typer.Argument(..., help="会话ID"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """删除会话"""
    sm = SessionManager()

    if not force:
        confirm = typer.confirm(f"确认删除会话 '{session_id}'?")
        if not confirm:
            typer.echo("已取消")
            return

    success = sm.delete(session_id)
    if success:
        typer.echo(f"会话 {session_id} 已删除")
    else:
        typer.echo(f"会话 {session_id} 不存在")
        raise typer.Exit(1)


def session_clear(
    session_id: str = typer.Argument(..., help="会话ID"),
):
    """清空会话历史"""
    sm = SessionManager()
    success = sm.clear(session_id)
    if success:
        typer.echo(f"会话 {session_id} 已清空")
    else:
        typer.echo(f"会话 {session_id} 不存在")
        raise typer.Exit(1)


# ==================== Tool 命令组 ====================


def tool_list(
    format: str = typer.Option("text", "--format", "-f", help="输出格式 (text/json)"),
):
    """列出所有工具"""
    tools = _get_tools_from_registry()

    if not tools:
        typer.echo("暂无工具")
        return

    if format == "json":
        typer.echo(json.dumps(tools, ensure_ascii=False, indent=2))
    else:
        typer.echo(f"共 {len(tools)} 个工具:")
        for t in tools:
            typer.echo(f"  {t.get('name')} - {t.get('description', '')}")


def tool_info(
    tool_name: str = typer.Argument(..., help="工具名称"),
):
    """查看工具详情"""
    try:
        from agent.tools import create_registry

        registry = create_registry()

        if tool_name not in registry.tool_names:
            typer.echo(f"工具 {tool_name} 不存在")
            raise typer.Exit(1)

        tool = registry.get(tool_name)
        if tool is None:
            typer.echo(f"工具 {tool_name} 不存在")
            raise typer.Exit(1)

        typer.echo(f"工具: {tool_name}")
        typer.echo(f"描述: {tool.description}")
        typer.echo(f"类: {tool.__class__.__module__}.{tool.__class__.__name__}")

        if hasattr(tool, "parameters") and tool.parameters:
            typer.echo("参数:")
            properties = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            for param_name, param_info in properties.items():
                req = " (必填)" if param_name in required else ""
                typer.echo(f"  {param_name}: {param_info.get('type', 'any')}{req}")
                if "description" in param_info:
                    typer.echo(f"    描述: {param_info['description']}")
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


# ==================== Chat 命令组 ====================


def chat_send(
    message: str = typer.Argument(..., help="消息内容"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="会话ID"),
):
    """发送消息"""
    try:
        asyncio.run(_run_chat(message, session_id))
        typer.echo("消息已发送")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


async def _run_chat(message: str, session_id: str | None):
    """运行聊天"""
    return None


def chat_history(
    session_id: str = typer.Argument(..., help="会话ID"),
):
    """查看聊天历史"""
    sm = SessionManager()
    data = sm.get_history(session_id)

    history = data.get("history", [])
    if not history:
        typer.echo("暂无历史消息")
        return

    for msg in history:
        role = "用户" if msg.get("role") == "user" else "Agent"
        typer.echo(f"{role}: {msg.get('content', '')}")


# ==================== Workspace 命令组 ====================


def workspace_list():
    """列出工作空间文件"""
    try:
        result = asyncio.get_event_loop().run_until_complete(_workspace_list())
        data = json.loads(result)
        files = data.get("files", [])
        directories = data.get("directories", [])

        if not files and not directories:
            typer.echo("工作空间为空目录")
            return

        if directories:
            typer.echo("目录:")
            for d in directories:
                typer.echo(f"  {d.get('name', '')}/")

        if files:
            typer.echo("文件:")
            for f in files:
                size = f.get("size", 0)
                typer.echo(f"  {f.get('name', '')} ({size} bytes)")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


async def _workspace_list():
    """列出工作空间"""
    return json.dumps({"files": [], "directories": []})


def workspace_cat(
    file_name: str = typer.Argument(..., help="文件名"),
):
    """查看工作空间文件内容"""
    file_path = WORKSPACE / file_name
    if not file_path.exists():
        typer.echo(f"文件 {file_name} 不存在")
        raise typer.Exit(1)

    try:
        content = asyncio.get_event_loop().run_until_complete(_workspace_cat(file_path))
        typer.echo(content)
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


async def _workspace_cat(file_path):
    """读取文件内容"""
    if file_path.exists() and file_path.is_file():
        return file_path.read_text()
    return ""


def workspace_clean(
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """清理工作空间"""
    if not force:
        confirm = typer.confirm("确认清理工作空间中的所有文件?")
        if not confirm:
            typer.echo("已取消")
            return

    count = 0
    if WORKSPACE.exists():
        for item in WORKSPACE.iterdir():
            if item.is_file():
                item.unlink()
                count += 1

    typer.echo(f"已清理 {count} 个文件")


# ==================== Params 命令组 ====================


def params_tools():
    """显示所有可配置参数的工具"""
    try:
        from agent.config.manager import ToolParamManager

        manager = ToolParamManager()
        tools = manager.get_registered_tools()
        typer.echo("已注册的工具:")
        for t in tools:
            typer.echo(f"  {t.get('name')} - 参数: {t.get('param_count', 0)}, 已配置: {t.get('configured_count', 0)}")
    except Exception as e:
        typer.echo(f"错误: {e}")


def params_show(
    tool_name: str = typer.Argument(..., help="工具名称"),
):
    """显示工具的所有参数"""
    try:
        from agent.config.manager import ToolParamManager

        manager = ToolParamManager()
        params = manager.get_tool_params(tool_name)

        typer.echo(f"工具: {tool_name}")
        for param_name, param_info in params.items():
            sensitive = param_info.get("sensitive", False)
            value = "****" if sensitive else param_info.get("value", "")
            typer.echo(f"  {param_name}: {value} ({param_info.get('type', 'str')})")
            if "description" in param_info:
                typer.echo(f"    描述: {param_info['description']}")
    except Exception as e:
        typer.echo(f"错误: {e}")


def params_set(
    tool_name: str = typer.Argument(..., help="工具名称"),
    param_name: str = typer.Argument(..., help="参数名"),
    value: str = typer.Argument(..., help="参数值"),
):
    """设置工具参数"""
    try:
        from agent.config.manager import ToolParamManager

        ToolParamManager.set_tool_param(tool_name, param_name, value)
        typer.echo(f"参数 {tool_name}.{param_name} 已更新")
    except ValueError as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def params_delete(
    tool_name: str = typer.Argument(..., help="工具名称"),
    param_name: str = typer.Argument(..., help="参数名"),
):
    """删除工具参数"""
    try:
        from agent.config.manager import ToolParamManager

        success = ToolParamManager.delete_tool_param(tool_name, param_name)
        if success:
            typer.echo(f"参数 {tool_name}.{param_name} 已删除")
        else:
            typer.echo(f"参数 {tool_name}.{param_name} 不存在")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def params_import(
    file_path: str = typer.Argument(..., help="JSON文件路径"),
):
    """从JSON文件导入参数配置"""
    try:
        if not os.path.exists(file_path):
            typer.echo(f"文件 {file_path} 不存在")
            raise typer.Exit(1)

        with open(file_path) as f:
            data = json.load(f)

        from agent.config.manager import ToolParamManager

        imported, skipped, errors = ToolParamManager.import_config(data)
        typer.echo(f"导入完成: 成功 {imported}, 跳过 {skipped}, 失败 {len(errors)}")
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def params_export(
    output: str = typer.Option("params_export.json", "--output", "-o", help="输出文件"),
):
    """导出参数配置到JSON"""
    try:
        from agent.config.manager import ToolParamManager

        data = ToolParamManager.export_config()

        with open(output, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        typer.echo(f"参数配置已导出到 {output}")
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def params_validate(
    tool_name: str = typer.Argument(..., help="工具名称"),
):
    """验证工具参数配置"""
    try:
        from agent.config.templates import get_tool_template
        from agent.config.tool_params import ToolParamResolver

        template = get_tool_template(tool_name)
        all_ok = True

        for param_name, param_config in template.items():
            required = param_config.get("required", False)
            value = ToolParamResolver.resolve(tool_name, param_name)

            if required and value is None:
                typer.echo(f"  {param_name}: 未配置 (必填)")
                all_ok = False
            else:
                typer.echo(f"  {param_name}: 已配置")

        if all_ok:
            typer.echo("所有必要参数已正确配置")
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


# ==================== Action 命令组 ====================


def action_generate_strategy(
    requirement: str = typer.Option(..., "--requirement", "-r", help="策略需求描述"),
    name: str = typer.Option(..., "--name", "-n", help="策略名称"),
):
    """AI 生成策略"""
    try:
        result = _run_tool_async("generate_strategy", requirement=requirement, name=name)
        data = json.loads(result) if isinstance(result, str) else result
        if data.get("success"):
            typer.echo("策略代码已生成")
            typer.echo(f"文件: {data.get('file_path', 'N/A')}")
        else:
            typer.echo(f"生成失败: {data.get('error', '未知错误')}")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def action_analyze_backtest(
    backtest_id: str = typer.Option(..., "--backtest-id", help="回测ID"),
):
    """分析回测结果"""
    try:
        result = _run_tool_async("analyze_backtest", backtest_id=backtest_id)
        data = json.loads(result) if isinstance(result, str) else result
        if data.get("success"):
            typer.echo(f"分析结果: {data.get('analysis', '')}")
        else:
            typer.echo("分析失败")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def action_optimize_params(
    strategy_name: str = typer.Option(..., "--strategy-name", help="策略名称"),
    param_ranges: str = typer.Option(..., "--param-ranges", help="参数范围JSON"),
):
    """优化策略参数"""
    try:
        result = _run_tool_async("optimize_params", strategy_name=strategy_name, param_ranges=param_ranges)
        typer.echo(f"优化结果: {result}")
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def action_diagnose(
    strategy_name: str = typer.Option(..., "--strategy-name", help="策略名称"),
):
    """诊断策略"""
    try:
        result = _run_tool_async("diagnose", strategy_name=strategy_name)
        data = json.loads(result) if isinstance(result, str) else result
        typer.echo(f"诊断结果: {data.get('diagnosis', '')}")
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def action_fetch_market(
    symbol: str = typer.Option(..., "--symbol", help="交易对"),
):
    """获取市场数据"""
    try:
        result = _run_tool_async("fetch_market", symbol=symbol)
        data = json.loads(result) if isinstance(result, str) else result
        if data.get("success"):
            typer.echo(f"市场数据: {data.get('data', '')}")
        else:
            typer.echo("获取失败")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


def action_deploy(
    strategy_name: str = typer.Option(..., "--strategy-name", help="策略名称"),
    symbols: str = typer.Option(..., "--symbols", help="交易对，逗号分隔"),
):
    """部署策略"""
    try:
        result = _run_tool_async("deploy", strategy_name=strategy_name, symbols=symbols)
        data = json.loads(result) if isinstance(result, str) else result
        if data.get("success"):
            typer.echo(f"策略 {strategy_name} 已部署")
        else:
            typer.echo("部署失败")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}")
        raise typer.Exit(1)


# ==================== 子命令组注册 ====================

session_app = typer.Typer(help="会话管理")
tool_app = typer.Typer(help="工具管理")
chat_app = typer.Typer(help="对话交互")
workspace_app = typer.Typer(help="工作空间管理")
params_app = typer.Typer(help="参数管理")
action_app = typer.Typer(help="高级操作")

app.add_typer(session_app, name="session")
app.add_typer(tool_app, name="tool")
app.add_typer(chat_app, name="chat")
app.add_typer(workspace_app, name="workspace")
app.add_typer(params_app, name="params")
app.add_typer(action_app, name="action")

# 将命令注册到对应的子 app
# Session
session_app.command("list")(session_list)
session_app.command("info")(session_info)
session_app.command("create")(session_create)
session_app.command("delete")(session_delete)
session_app.command("clear")(session_clear)

# Tool
tool_app.command("list")(tool_list)
tool_app.command("info")(tool_info)

# Chat
chat_app.command("send")(chat_send)
chat_app.command("history")(chat_history)

# Workspace
workspace_app.command("list")(workspace_list)
workspace_app.command("cat")(workspace_cat)
workspace_app.command("clean")(workspace_clean)

# Params
params_app.command("tools")(params_tools)
params_app.command("show")(params_show)
params_app.command("set")(params_set)
params_app.command("delete")(params_delete)
params_app.command("import")(params_import)
params_app.command("export")(params_export)
params_app.command("validate")(params_validate)

# Action
action_app.command("generate-strategy")(action_generate_strategy)
action_app.command("analyze-backtest")(action_analyze_backtest)
action_app.command("optimize-params")(action_optimize_params)
action_app.command("diagnose")(action_diagnose)
action_app.command("fetch-market")(action_fetch_market)
action_app.command("deploy")(action_deploy)


if __name__ == "__main__":
    app()
