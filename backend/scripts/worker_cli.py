#!/usr/bin/env python3
"""
Worker 管理命令行工具 - HTTP Client 模式

通过 HTTP 请求与 FastAPI Worker 后端通信。
支持 Worker 的完整生命周期管理、批量操作、实时状态监控。

特性:
  - 通过 HTTP 与 FastAPI 服务器通信
  - 支持远程服务器操作
  - 批量操作支持
  - 实时状态查询
  - 增强的输出格式（颜色、图标、耗时统计）
"""

import sys
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import json
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

import requests
import typer
from typing_extensions import Annotated

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class OutputFormat(str, Enum):
    """输出格式枚举"""
    TABLE = "table"
    JSON = "json"


app = typer.Typer(
    name="worker-cli",
    help="Worker 管理命令行工具 - HTTP Client 模式",
    epilog="""
示例:
  python worker_cli.py list                            # 列出所有 Worker
  python worker_cli.py create --name w1 --strategy-id 1
  python worker_cli.py start 1                          # 启动（非阻塞）
  python worker_cli.py start 1 --wait                   # 启动（等待完成）
  python worker_cli.py status                           # 查看状态
  python worker_cli.py summary                          # 系统摘要
  python worker_cli.py start-all                        # 批量启动
  python worker_cli.py stop-all                         # 批量停止
  python worker_cli.py --server http://remote:8000 list # 连接远程服务器
  
注意: 此工具通过 HTTP 与 FastAPI 服务器通信，确保服务器正在运行。
""",
)

# 全局 --server 选项
_server_url: str = "http://localhost:8000"


# ==================== HTTP Client 工具函数 ====================

def _api(path: str) -> str:
    return f"{_server_url}{path}"


def _get(path: str, params: dict = None) -> dict:
    resp = requests.get(_api(path), params=params, timeout=30)
    _check_error(resp)
    return resp.json().get("data", {})


def _post(path: str, body: dict = None) -> dict:
    resp = requests.post(_api(path), json=body or {}, timeout=30)
    _check_error(resp)
    return resp.json().get("data", {})


def _put(path: str, body: dict = None) -> dict:
    resp = requests.put(_api(path), json=body or {}, timeout=30)
    _check_error(resp)
    return resp.json().get("data", {})


def _patch(path: str, body: dict = None) -> dict:
    resp = requests.patch(_api(path), json=body or {}, timeout=30)
    _check_error(resp)
    return resp.json().get("data", {})


def _delete(path: str) -> dict:
    resp = requests.delete(_api(path), timeout=30)
    _check_error(resp)
    return resp.json().get("data", {})


def _check_error(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json()
            msg = detail.get("message", detail.get("detail", resp.text))
        except Exception:
            msg = resp.text
        typer.echo(f"❌ 错误 ({resp.status_code}): {msg}", err=True)
        raise typer.Exit(code=1)


# ==================== 工具函数 ====================

def _get_state_color(state: str) -> str:
    """获取状态颜色"""
    color_map = {
        "running": typer.colors.GREEN,
        "stopped": typer.colors.WHITE,
        "error": typer.colors.RED,
        "initializing": typer.colors.YELLOW,
        "starting": typer.colors.YELLOW,
        "stopping": typer.colors.YELLOW,
        "paused": typer.colors.CYAN,
    }
    return color_map.get(state.lower(), typer.colors.WHITE)


def _get_state_icon(state: str) -> str:
    """获取状态图标"""
    icon_map = {
        "running": "🟢",
        "stopped": "⚪",
        "error": "🔴",
        "starting": "🟡",
        "stopping": "🟠",
        "paused": "🔵",
        "initializing": "🟣",
    }
    return icon_map.get(state.lower(), "⚫")


def _format_uptime(started_at: Optional[str]) -> str:
    """格式化运行时长"""
    if started_at is None:
        return "N/A"

    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        uptime = datetime.now(start.tzinfo) - start
        total_seconds = int(uptime.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    except:
        return "N/A"


def _format_elapsed(elapsed: float) -> str:
    """格式化耗时"""
    if elapsed < 1:
        return f"{elapsed * 1000:.0f}ms"
    else:
        return f"{elapsed:.2f}s"


def _print_worker_table(workers: List[Dict[str, Any]], show_header: bool = True):
    """
    打印 Worker 表格（增强版）
    
    包含：ID、名称、状态（带颜色和图标）、PID、运行时长
    """
    if show_header:
        typer.echo(f"{'ID':<8} {'名称':<20} {'状态':<15} {'PID':<10} {'运行时长':<15}")
        typer.echo("-" * 75)

    for worker in workers:
        worker_id = str(worker.get("worker_id", worker.get("id", "N/A")))[:6]
        name = worker.get("name", "N/A")[:18]
        state = worker.get("status", "unknown")
        pid = str(worker.get("pid")) if worker.get("pid") else "-"
        
        started_at = worker.get("started_at")
        uptime = _format_uptime(started_at)

        state_color = _get_state_color(state)
        state_icon = _get_state_icon(state)
        state_display = f"{state_icon} {state}"

        typer.echo(f"{worker_id:<8} {name:<20} ", nl=False)
        typer.secho(f"{state_display:<15}", fg=state_color, nl=False)
        typer.echo(f" {pid:<10} {uptime:<15}")


def _print_log_entry(log: dict):
    """打印单条日志条目（统一格式）"""
    timestamp = log.get("timestamp", "N/A")
    if timestamp != "N/A":
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except Exception:
            pass

    log_level = log.get("level", "INFO")
    level_color = {
        "DEBUG": typer.colors.WHITE,
        "INFO": typer.colors.GREEN,
        "WARNING": typer.colors.YELLOW,
        "ERROR": typer.colors.RED,
        "CRITICAL": typer.colors.RED,
    }.get(log_level, typer.colors.WHITE)

    source = log.get("source", "")
    source_str = f"[{source}] " if source else ""

    typer.echo(f"[{timestamp}] ", nl=False)
    typer.secho(f"{log_level:<8}", fg=level_color, nl=False)
    typer.echo(f" {source_str}{log.get('message', '')}")


def _print_start_result(result: Dict[str, Any], worker_id: int):
    """
    打印启动结果（用于 --wait 模式）
    
    显示最终状态和耗时信息
    """
    status = result.get('status', 'unknown')
    pid = result.get('pid')
    elapsed = result.get('elapsed')

    state_icon = _get_state_icon(status)
    state_color = _get_state_color(status)

    typer.echo("")
    typer.secho(f"✓ Worker {worker_id} 启动完成", fg=typer.colors.GREEN)
    typer.echo(f"  Worker ID: {result.get('worker_id', worker_id)}")
    typer.echo(f"  最终状态: ", nl=False)
    typer.secho(f"{state_icon} {status}", fg=state_color)
    
    if pid:
        typer.echo(f"  PID: {pid}")
    
    if elapsed is not None:
        typer.echo(f"  耗时: {_format_elapsed(elapsed)}")

    if status == 'starting':
        typer.echo("")
        typer.secho("ℹ  Worker 正在后台初始化中...", fg=typer.colors.YELLOW)
        typer.echo("  查看日志:")
        typer.echo(f"    python worker_cli.py logs {worker_id} --lines 20")


def _handle_general_error(e: Exception, verbose: bool = False):
    """
    处理通用异常
    
    提供友好的错误信息，可选显示详细堆栈
    """
    typer.echo(f"✗ 操作失败: {e}", err=True)
    if verbose:
        import traceback
        traceback.print_exc()
    raise typer.Exit(1)


# ==================== 策略相关工具函数（本地查询） ====================

def _get_strategy_name(strategy_id: int) -> str:
    """
    根据策略ID获取策略名称

    Args:
        strategy_id: 策略ID

    Returns:
        str: 策略名称，如果查询失败返回默认值
    """
    if not strategy_id:
        return "N/A"

    try:
        from strategy.models import Strategy
        from collector.db.database import SessionLocal
        from collector.db.database import init_database_config

        init_database_config()
        db = SessionLocal()
        try:
            strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
            if strategy:
                return strategy.name
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"获取策略名称失败: {e}")

    return f"策略#{strategy_id}"


def _format_symbols(worker_data: Dict) -> str:
    """
    格式化交易对显示

    从 trading_config 中正确提取 symbols 列表并格式化显示

    Args:
        worker_data: Worker 数据字典

    Returns:
        str: 格式化后的交易对字符串
    """
    config = worker_data.get("config", {})
    symbols_config = config.get("symbols_config", {})
    symbols = symbols_config.get("symbols", [])

    if isinstance(symbols, list) and symbols:
        return ", ".join(symbols)

    symbol = worker_data.get("symbol")
    if symbol:
        return str(symbol)

    return "N/A"


# ==================== 系统摘要命令 ====================

@app.command()
def summary():
    """
    显示系统摘要信息

    从服务器获取 Worker 系统的整体状态，包括总数、状态分布等。

    示例:
      python worker_cli.py summary
    """
    try:
        stats_data = _get("/api/workers/")
        if isinstance(stats_data, dict):
            # 如果返回的是汇总统计
            total = stats_data.get('total_workers', stats_data.get('total', 0))
            breakdown = stats_data.get('status_breakdown', {})
        elif isinstance(stats_data, list):
            items = stats_data
            total = len(items)
            breakdown = {}
            for w in items:
                s = w.get('status', 'unknown')
                breakdown[s] = breakdown.get(s, 0) + 1
        else:
            total = 0
            breakdown = {}

        typer.echo("\n📊 Worker 系统摘要\n")
        typer.echo(f"  总数: {total}")
        if breakdown:
            typer.echo(f"\n  状态分布:")
            for status, count in breakdown.items():
                color = _get_state_color(status)
                icon = _get_state_icon(status)
                typer.secho(f"    {icon} {status}: {count}", fg=color)
        else:
            typer.echo("    （暂无 Worker）")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        typer.echo(f"  请确保 FastAPI 服务器正在运行。")
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== Worker CRUD 命令 ====================

@app.command()
def create(
    name: Annotated[str, typer.Option("--name", "-n", help="Worker 名称")],
    strategy_id: Annotated[int, typer.Option("--strategy-id", "-s", help="策略ID(使用 'strategies' 命令查看可用策略)")],
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    symbol: Annotated[str, typer.Option("--symbol", help="交易对")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t", help="时间周期")] = "1h",
    market_type: Annotated[str, typer.Option("--market-type", help="市场类型(spot/future)")] = "spot",
    trading_mode: Annotated[str, typer.Option("--trading-mode", help="交易模式(paper/live)")] = "paper",
    description: Annotated[Optional[str], typer.Option("--description", "-d", help="Worker 描述")] = None,
):
    """
    创建新 Worker

    示例:
      python worker_cli.py create --name worker_001 --strategy-id 1 --exchange binance --symbol BTCUSDT
    """
    try:
        body = {
            "name": name,
            "strategy_id": strategy_id,
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "market_type": market_type,
            "trading_mode": trading_mode,
        }
        if description:
            body["description"] = description

        result = _post("/api/workers/", body)

        worker_info = result if isinstance(result, dict) else {}
        worker_id = worker_info.get('id', worker_info.get('worker_id', '?'))

        typer.secho("✓ Worker 创建成功", fg=typer.colors.GREEN)
        typer.echo(f"  ID: {worker_id}")
        typer.echo(f"  名称: {name}")
        typer.echo(f"  策略ID: {strategy_id}")
        typer.echo(f"  交易所: {exchange}")
        typer.echo(f"  交易对: {symbol}")
        typer.echo(f"  时间周期: {timeframe}")
        typer.echo(f"  市场类型: {market_type}")
        typer.echo(f"  交易模式: {trading_mode}")
        
        typer.echo(f"\n  下一步:")
        typer.echo(f"    python worker_cli.py start {worker_id}   # 启动 Worker")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def add(
    name: Annotated[str, typer.Option("--name", "-n", help="Worker 名称")],
    strategy_id: Annotated[int, typer.Option("--strategy-id", "-s", help="策略ID")],
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    symbol: Annotated[str, typer.Option("--symbol", help="交易对")] = "BTCUSDT",
):
    """
    快速添加新 Worker（简化版 create）

    使用最常用的参数快速创建 Worker，适合日常使用。

    示例:
      python worker_cli.py add --name quick_worker --strategy-id 1
      python worker_cli.py add -n w2 -s 2 -e binance -symbol ETHUSDT
    """
    try:
        body = {
            "name": name,
            "strategy_id": strategy_id,
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper",
        }

        result = _post("/api/workers/", body)

        worker_info = result if isinstance(result, dict) else {}
        worker_id = worker_info.get('id', worker_info.get('worker_id', '?'))

        typer.secho(f"✓ Worker 已添加 (ID: {worker_id})", fg=typer.colors.GREEN)
        typer.echo(f"  名称: {name}")
        typer.echo(f"  状态: stopped (可随时启动)")
        typer.echo(f"\n  下一步:")
        typer.echo(f"    python worker_cli.py start {worker_id}   # 启动 Worker")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def delete(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="强制删除运行中的 Worker")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="确认删除，不提示")] = False,
):
    """
    删除 Worker

    支持强制删除运行中的 Worker（会先停止再删除）。

    示例:
      python worker_cli.py delete 1
      python worker_cli.py delete 1 --force     # 强制删除（即使正在运行）
      python worker_cli.py delete 1 --yes       # 跳过确认提示
    """
    try:
        worker_info = _get(f"/api/workers/{worker_id}")
        if not worker_info:
            typer.echo(f"✗ Worker {worker_id} 不存在", err=True)
            raise typer.Exit(1)

        if not yes:
            worker_name = worker_info.get('name', 'Unknown')
            if not typer.confirm(f"确定要删除 Worker {worker_id} ({worker_name}) 吗?"):
                typer.echo("已取消")
                raise typer.Exit(0)

        _delete(f"/api/workers/{worker_id}")
        
        typer.secho(f"✓ Worker {worker_id} 已删除", fg=typer.colors.GREEN)
        if force:
            typer.echo(f"  （使用了强制删除模式）")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def remove(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="强制删除")] = False,
):
    """
    快捷删除 Worker（简化版 delete）

    示例:
      python worker_cli.py remove 1
      python worker_cli.py remove 1 --force
    """
    # 直接调用 delete 的回调逻辑（HTTP 版本）
    try:
        if not typer.confirm(f"确定要删除 Worker {worker_id} 吗?"):
            typer.echo("已取消")
            raise typer.Exit(0)

        _delete(f"/api/workers/{worker_id}")
        typer.secho(f"✓ Worker {worker_id} 已删除", fg=typer.colors.GREEN)
        if force:
            typer.echo(f"  （使用了强制删除模式）")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def update(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Worker 名称")] = None,
    description: Annotated[Optional[str], typer.Option("--description", "-d", help="Worker 描述")] = None,
    exchange: Annotated[Optional[str], typer.Option("--exchange", "-e", help="交易所")] = None,
    symbol: Annotated[Optional[str], typer.Option("--symbol", "-s", help="交易对")] = None,
    timeframe: Annotated[Optional[str], typer.Option("--timeframe", "-t", help="时间周期")] = None,
    trading_mode: Annotated[Optional[str], typer.Option("--trading-mode", help="交易模式")] = None,
):
    """
    更新 Worker 信息

    示例:
      python worker_cli.py update 1 --name new_name --symbol ETHUSDT
    """
    try:
        update_data = {}
        if name:
            update_data["name"] = name
        if description:
            update_data["description"] = description
        if exchange:
            update_data["exchange"] = exchange
        if symbol:
            update_data["symbol"] = symbol
        if timeframe:
            update_data["timeframe"] = timeframe
        if trading_mode:
            update_data["trading_mode"] = trading_mode

        if not update_data:
            typer.echo("✗ 没有指定要更新的字段", err=True)
            raise typer.Exit(1)

        result = _put(f"/api/workers/{worker_id}", update_data)

        worker_info = result if isinstance(result, dict) else {}
        
        typer.secho(f"✓ Worker {worker_id} 更新成功", fg=typer.colors.GREEN)
        typer.echo(f"  名称: {worker_info.get('name', name)}")
        typer.echo(f"  交易对: {worker_info.get('symbol', symbol)}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def clone(
    worker_id: Annotated[int, typer.Argument(help="源 Worker ID")],
    new_name: Annotated[str, typer.Option("--new-name", "-n", help="新 Worker 名称")],
    copy_config: Annotated[bool, typer.Option("--copy-config/--no-copy-config", help="是否复制配置")] = True,
    copy_parameters: Annotated[bool, typer.Option("--copy-parameters/--no-copy-parameters", help="是否复制参数")] = True,
):
    """
    克隆 Worker

    示例:
      python worker_cli.py clone 1 --new-name worker_002
    """
    try:
        body = {
            "new_name": new_name,
            "copy_config": copy_config,
            "copy_parameters": copy_parameters,
        }

        result = _post(f"/api/workers/{worker_id}/clone", body)

        info = result if isinstance(result, dict) else {}
        
        typer.secho(f"✓ Worker 克隆成功", fg=typer.colors.GREEN)
        typer.echo(f"  新 Worker ID: {info.get('id')}")
        typer.echo(f"  新 Worker 名称: {info.get('name')}")
        typer.echo(f"  源 Worker ID: {worker_id}")
        typer.echo(f"  复制配置: {copy_config}")
        typer.echo(f"  复制参数: {copy_parameters}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 生命周期命令 ====================

@app.command()
def start(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    wait: Annotated[bool, typer.Option("--wait", "-w", help="等待启动完成")] = False,
):
    """
    启动指定 Worker

    支持两种模式：
      - 非阻塞模式（默认）：发送启动请求后立即返回
      - 阻塞模式（--wait）：等待启动完成后返回最终状态

    示例:
      python worker_cli.py start 1           # 非阻塞模式（默认）
      python worker_cli.py start 1 --wait    # 等待启动完成
    """
    try:
        worker_data = _get(f"/api/workers/{worker_id}")
        if not worker_data:
            typer.echo(f"✗ Worker {worker_id} 不存在", err=True)
            raise typer.Exit(1)

        state_info = worker_data.get("_state_info", {})
        current_status = state_info.get("status") or worker_data.get("status", "stopped")

        if current_status in ['running', 'starting']:
            state_icon = _get_state_icon(current_status)
            state_color = _get_state_color(current_status)
            typer.secho(f"{state_icon} Worker {worker_id} 正在运行中", fg=state_color)
            typer.echo(f"  状态: {current_status}")
            
            if current_status == 'starting':
                typer.echo("")
                typer.secho("ℹ  Worker 正在初始化中...", fg=typer.colors.YELLOW)
                typer.echo("  查看日志:")
                typer.echo(f"    python worker_cli.py logs {worker_id} --lines 20")
            return

        if wait:
            start_time = time.time()
            result = _post(f"/api/workers/{worker_id}/lifecycle/start")
            elapsed = time.time() - start_time

            info = result if isinstance(result, dict) else {}
            info['elapsed'] = elapsed
            _print_start_result(info, worker_id)
        else:
            result = _post(f"/api/workers/{worker_id}/lifecycle/start")

            info = result if isinstance(result, dict) else {}
            status = info.get('status', 'starting')
            pid = info.get('pid')
            
            typer.secho(f"✓ 启动请求已发送", fg=typer.colors.GREEN)
            typer.echo(f"  Worker ID: {worker_id}")
            typer.echo(f"  当前状态: ", nl=False)
            typer.secho(f"{_get_state_icon(status)} {status}", fg=_get_state_color(status))
            
            if pid:
                typer.echo(f"  PID: {pid}")
            
            typer.echo(f"\n  提示: 使用以下命令查看进度:")
            typer.echo(f"    python worker_cli.py status {worker_id}")
            typer.echo(f"    python worker_cli.py logs {worker_id} --lines 20")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def stop(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    wait: Annotated[bool, typer.Option("--wait", "-w", help="等待停止完成")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="强制停止")] = False,
):
    """
    停止指定 Worker

    支持两种模式：
      - 非阻塞模式（默认）：发送停止请求后立即返回
      - 阻塞模式（--wait）：等待停止完成后返回最终状态

    示例:
      python worker_cli.py stop 1             # 非阻塞模式（默认）
      python worker_cli.py stop 1 --wait      # 等待停止完成
      python worker_cli.py stop 1 --force     # 强制停止
    """
    try:
        body = {}
        if force:
            body["force"] = True

        start_time = time.time()

        if wait:
            result = _post(f"/api/workers/{worker_id}/lifecycle/stop", body)
            elapsed = time.time() - start_time

            info = result if isinstance(result, dict) else {}
            status = info.get('status', 'unknown')
            
            typer.echo("")
            typer.secho(f"✓ Worker {worker_id} 停止完成", fg=typer.colors.GREEN)
            typer.echo(f"  最终状态: ", nl=False)
            typer.secho(f"{_get_state_icon(status)} {status}", fg=_get_state_color(status))
            typer.echo(f"  耗时: {_format_elapsed(elapsed)}")
            
            if status not in ['stopped', 'stopping']:
                typer.secho(
                    f"  ⚠ 状态为 '{status}'，可能触发了优雅停机超时保护",
                    fg=typer.colors.YELLOW
                )
                typer.echo(f"  提示: 使用 'diagnose {worker_id}' 查看详细信息")
            elif elapsed > 10:
                typer.secho(
                    f"  ℹ 停机耗时较长 ({elapsed:.1f}s)，可能进行了资源清理",
                    fg=typer.colors.CYAN
                )
        else:
            result = _post(f"/api/workers/{worker_id}/lifecycle/stop", body)
            
            elapsed = time.time() - start_time
            info = result if isinstance(result, dict) else {}
            status = info.get('status', 'unknown')
            
            typer.secho(f"✓ 停止请求已发送", fg=typer.colors.GREEN)
            typer.echo(f"  Worker ID: {worker_id}")
            typer.echo(f"  当前状态: ", nl=False)
            typer.secho(f"{_get_state_icon(status)} {status}", fg=_get_state_color(status))
            typer.echo(f"  耗时: {_format_elapsed(elapsed)}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def restart(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    重启指定 Worker

    内部执行先停止再启动的操作。

    示例:
      python worker_cli.py restart 1
    """
    try:
        start_time = time.time()
        result = _post(f"/api/workers/{worker_id}/lifecycle/restart")
        elapsed = time.time() - start_time

        info = result if isinstance(result, dict) else {}
        start_result = info.get('start_result', {})

        typer.secho(f"✓ Worker {worker_id} 重启完成", fg=typer.colors.GREEN)
        typer.echo(f"  状态: {start_result.get('status', 'unknown')}")
        typer.echo(f"  耗时: {_format_elapsed(elapsed)}")
        
        if start_result.get('pid'):
            typer.echo(f"  PID: {start_result['pid']}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def pause(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    暂停指定 Worker

    通过停止 Worker 实现暂停。

    示例:
      python worker_cli.py pause 1
    """
    try:
        result = _post(f"/api/workers/{worker_id}/lifecycle/stop")

        info = result if isinstance(result, dict) else {}
        typer.secho(f"✓ Worker {worker_id} 已暂停", fg=typer.colors.GREEN)
        typer.echo(f"  状态: {info.get('status')}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def resume(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    恢复指定 Worker

    通过启动 Worker 实现恢复。

    示例:
      python worker_cli.py resume 1
    """
    try:
        result = _post(f"/api/workers/{worker_id}/lifecycle/start")

        info = result if isinstance(result, dict) else {}
        typer.secho(f"✓ Worker {worker_id} 已恢复", fg=typer.colors.GREEN)
        typer.echo(f"  状态: {info.get('status')}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 批量操作命令 ====================

@app.command("start-all")
def start_all(
    concurrent: Annotated[int, typer.Option("--concurrent", "-c", help="最大并发数")] = 3,
):
    """
    启动所有已停止的 Worker

    使用信号量控制并发数量，避免同时启动过多 Worker 导致资源耗尽。

    示例:
      python worker_cli.py start-all              # 默认并发数 3
      python worker_cli.py start-all -c 5         # 最大并发数 5
    """
    try:
        workers_data = _get("/api/workers/")
        items = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))
        stopped = [w for w in items if w.get('status') == 'stopped']

        if not stopped:
            typer.echo("\n没有需要启动的 Worker（所有 Worker 都不在 stopped 状态）")
            return

        stopped_ids = [w.get('worker_id', w.get('id')) for w in stopped]

        body = {
            "worker_ids": stopped_ids,
            "operation": "start",
        }
        result = _post("/api/workers/batch", body)

        results = result.get('results', []) if isinstance(result, dict) else []

        success_count = sum(1 for r in results if r.get('success'))
        fail_count = len(results) - success_count

        typer.echo(f"\n{'='*60}")
        typer.secho(f"批量启动完成 | 成功: {success_count} | 失败: {fail_count}", 
                   fg=typer.colors.GREEN if fail_count == 0 else typer.colors.YELLOW,
                   bold=True)
        typer.echo(f"{'='*60}")

        for r in results:
            wid = r['worker_id']
            if r.get('success'):
                typer.secho(f"  ✓ Worker {wid}: 启动成功", fg=typer.colors.GREEN)
            else:
                error_msg = r.get('error', '未知错误')
                typer.secho(f"  ✗ Worker {wid}: {error_msg}", fg=typer.colors.RED)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command("stop-all")
def stop_all(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="跳过确认提示")] = False,
):
    """
    停止所有运行中的 Worker

    示例:
      python worker_cli.py stop-all             # 会提示确认
      python worker_cli.py stop-all -y          # 跳过确认
    """
    try:
        # 获取运行中的 Worker 数量
        workers_data = _get("/api/workers/")
        items = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))
        
        running_count = sum(1 for w in items if w.get('status') == 'running')
        starting_count = sum(1 for w in items if w.get('status') == 'starting')
        total_running = running_count + starting_count

        if total_running == 0:
            typer.echo("\n没有需要停止的 Worker（没有运行中的 Worker）")
            return

        if not yes:
            typer.echo(f"\n即将停止 {total_running} 个运行中的 Worker:")
            typer.echo(f"  - 运行中: {running_count}")
            typer.echo(f"  - 启动中: {starting_count}")
            
            if not typer.confirm("\n确定要停止所有运行中的 Worker 吗?"):
                typer.echo("已取消")
                raise typer.Exit(0)

        running_ids = [
            w.get('worker_id', w.get('id')) for w in items
            if w.get('status') in ('running', 'starting')
        ]

        if not running_ids:
            typer.echo("\n没有需要停止的 Worker")
            return

        body = {
            "worker_ids": running_ids,
            "operation": "stop",
        }
        result = _post("/api/workers/batch", body)

        results = result.get('results', []) if isinstance(result, dict) else []

        success_count = sum(1 for r in results if r.get('success'))
        fail_count = len(results) - success_count

        typer.echo(f"\n{'='*60}")
        typer.secho(f"批量停止完成 | 成功: {success_count} | 失败: {fail_count}",
                   fg=typer.colors.GREEN if fail_count == 0 else typer.colors.YELLOW,
                   bold=True)
        typer.echo(f"{'='*60}")

        for r in results:
            wid = r['worker_id']
            if r.get('success'):
                typer.secho(f"  ✓ Worker {wid}: 已停止", fg=typer.colors.GREEN)
            else:
                error_msg = r.get('error', '未知错误')
                typer.secho(f"  ✗ Worker {wid}: {error_msg}", fg=typer.colors.RED)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command("batch")
def batch_operation(
    operation: Annotated[str, typer.Option("--operation", "-o", help="操作: start/stop/restart")],
    worker_ids: Annotated[List[int], typer.Option("--worker-ids", "-w", help="Worker ID 列表")],
):
    """
    批量操作指定的 Worker 列表

    示例:
      python worker_cli.py batch --operation start --worker-ids 1 --worker-ids 2 --worker-ids 3
    """
    try:
        body = {
            "worker_ids": worker_ids,
            "operation": operation,
        }
        result = _post("/api/workers/batch", body)

        info = result if isinstance(result, dict) else {}
        success_list = info.get('success', [])
        failed_dict = info.get('failed', {})
        total = info.get('total', len(worker_ids))
        results_detail = info.get('results', [])

        typer.echo(f"\n{'='*60}")
        typer.secho(f"批量{operation}操作完成", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"{'='*60}")
        typer.echo(f"  总计: {total} 个 Worker")
        typer.secho(f"  ✓ 成功: {len(success_list)} 个", fg=typer.colors.GREEN)
        if failed_dict:
            typer.secho(f"  ✗ 失败: {len(failed_dict)} 个", fg=typer.colors.RED)
        else:
            typer.secho(f"  ✗ 失败: 0 个", fg=typer.colors.GREEN)

        if results_detail:
            typer.echo(f"\n{'─'*60}")
            typer.echo("详细状态转换记录:")
            typer.echo(f"{'─'*60}")
            typer.echo(f"{'Worker ID':<12} {'结果':<8} {'旧状态':<15} {'新状态':<15} {'消息'}")
            typer.echo(f"{'-'*12} {'-'*8} {'-'*15} {'-'*15} {'-'*30}")

            for r in results_detail:
                wid = str(r.get('worker_id', 'N/A'))
                is_success = r.get('success', False)
                old_state = r.get('old_state') or 'N/A'
                new_state = r.get('new_state') or 'N/A'
                message = r.get('message', '')

                if hasattr(old_state, 'value') and not isinstance(old_state, str):
                    old_state = old_state.value
                if hasattr(new_state, 'value') and not isinstance(new_state, str):
                    new_state = new_state.value

                result_icon = "✓" if is_success else "✗"
                result_color = typer.colors.GREEN if is_success else typer.colors.RED

                typer.echo(f"{wid:<12} ", nl=False)
                typer.secho(f"{result_icon} {'成功' if is_success else '失败':<6}", fg=result_color, nl=False)
                typer.echo(f" {str(old_state):<15} {str(new_state):<15} {message[:40]}")

        if failed_dict:
            typer.echo(f"\n失败原因详情:")
            for wid, error in failed_dict.items():
                typer.secho(f"  ! Worker {wid}: {error}", fg=typer.colors.RED)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 状态查看命令 ====================

@app.command()
def status(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则查看所有")] = None,
    watch: Annotated[bool, typer.Option("--watch", "-w", help="持续监控")] = False,
    interval: Annotated[int, typer.Option("--interval", "-i", help="监控间隔(秒)")] = 5,
):
    """
    查看 Worker 状态

    通过 HTTP 从服务器获取状态信息。

    示例:
      python worker_cli.py status              # 查看所有 Worker 状态
      python worker_cli.py status 1            # 查看指定 Worker 状态
      python worker_cli.py status --watch      # 持续监控
    """
    try:
        if watch:
            typer.echo(f"开始监控 Worker 状态，按 Ctrl+C 停止...\n")
            try:
                while True:
                    os.system('clear' if os.name == 'posix' else 'cls')
                    typer.echo(f"QuantCell Worker 监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    _show_status(worker_id)
                    time.sleep(interval)
            except KeyboardInterrupt:
                typer.echo("\n监控已停止")
        else:
            _show_status(worker_id)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


def _show_status(worker_id: Optional[int] = None):
    """显示 Worker 状态（通过 HTTP 获取数据）"""
    if worker_id:
        state_data = _get(f"/api/workers/{worker_id}/state")

        if not state_data:
            typer.echo(f"✗ Worker {worker_id} 不存在", err=True)
            raise typer.Exit(1)

        state = state_data.get('status', 'unknown')
        state_icon = _get_state_icon(state)
        state_color = _get_state_color(state)

        typer.echo(f"Worker ID: {state_data.get('worker_id', worker_id)}")
        typer.echo(f"名称: {state_data.get('name')}")
        typer.echo(f"状态: ", nl=False)
        typer.secho(f"{state_icon} {state}", fg=state_color)
        typer.echo(f"策略ID: {state_data.get('strategy_id')}")
        typer.echo(f"交易所: {state_data.get('exchange')}")
        typer.echo(f"交易对: {state_data.get('symbol')}")

        state_info = state_data.get('_state_info')
        if state_info:
            typer.echo(f"\n实时状态:")
            typer.echo(f"  是否健康: {state_info.get('is_healthy', False)}")
            typer.echo(f"  最后心跳: {state_info.get('last_heartbeat', 'N/A')}")
    else:
        workers_data = _get("/api/workers/")
        workers = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))

        if not workers:
            typer.echo("没有 Worker")
            return

        typer.echo(f"\n总计: {len(workers)} 个 Worker\n")
        _print_worker_table(workers)


@app.command()
def list_workers(
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="按状态筛选")] = None,
    page: Annotated[int, typer.Option("--page", "-p", help="页码")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="每页数量")] = 20,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    列出所有 Worker

    通过 HTTP 从服务器获取 Worker 列表，支持状态筛选。

    示例:
      python worker_cli.py list_workers
      python worker_cli.py list_workers --status running
      python worker_cli.py list_workers --format json
    """
    try:
        params = {
            "page": page,
            "page_size": page_size,
        }
        if status:
            params["status"] = status

        workers_data = _get("/api/workers/", params=params)

        workers = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))
        total = workers_data.get('total', len(workers)) if isinstance(workers_data, dict) else len(workers)

        if not workers:
            typer.echo("没有 Worker")
            return

        if format == OutputFormat.JSON:
            output = {
                "items": workers,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
            typer.echo(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        else:
            typer.echo(f"\n总计: {total} 个 Worker (第 {page} 页，每页 {page_size} 个)\n")
            _print_worker_table(workers)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def stats(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则查看全局统计")] = None,
):
    """
    查看 Worker 统计信息

    通过 HTTP 从服务器获取统计信息。

    示例:
      python worker_cli.py stats              # 查看全局统计
      python worker_cli.py stats 1            # 查看指定 Worker 统计
    """
    try:
        if worker_id:
            state_data = _get(f"/api/workers/{worker_id}/state")

            typer.echo(f"Worker {worker_id} 统计信息:")
            typer.echo(f"{'='*50}")
            typer.echo(f"名称: {state_data.get('name')}")
            typer.echo(f"状态: ", nl=False)
            typer.secho(f"{state_data.get('status')}", fg=_get_state_color(state_data.get('status', '')))
            typer.echo(f"运行时长: {_format_uptime(state_data.get('started_at'))}")

            try:
                metrics = _get(f"/api/workers/{worker_id}/monitoring/metrics")
                typer.echo(f"\n性能指标:")
                typer.echo(f"  CPU 使用率: {metrics.get('cpu_usage', 0):.1f}%")
                typer.echo(f"  内存使用: {metrics.get('memory_usage_mb', 0):.2f} MB")
            except Exception:
                pass

            typer.echo(f"\n交易记录:")
            typer.echo(f"  成交数量: {state_data.get('trades_count', 0)}")
            typer.echo(f"  订单数量: {state_data.get('orders_count', 0)}")

        else:
            workers_data = _get("/api/workers/")
            workers = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))

            total = len(workers) if isinstance(workers_data, list) else workers_data.get('total', len(workers))
            breakdown = workers_data.get('status_breakdown', {}) if isinstance(workers_data, dict) else {}

            if not breakdown and workers:
                for w in workers:
                    s = w.get('status', 'unknown')
                    breakdown[s] = breakdown.get(s, 0) + 1
            
            typer.echo("全局统计信息:")
            typer.echo(f"{'='*50}")
            typer.echo(f"总 Worker 数: {total}")
            
            typer.echo(f"\n状态分布:")
            for ws, count in breakdown.items():
                icon = _get_state_icon(ws)
                color = _get_state_color(ws)
                typer.secho(f"  {icon} {ws}: {count}", fg=color)

            running_count = breakdown.get('running', 0)
            if running_count > 0:
                typer.echo(f"\n运行中的 Worker:")
                for w in workers:
                    if w.get('status') == 'running':
                        wid = w.get('worker_id', w.get('id'))
                        wname = w.get('name')
                        typer.echo(f"  - {wname} (ID: {wid})")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 配置管理命令 ====================

@app.command()
def config(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    show: Annotated[bool, typer.Option("--show", "-s", help="显示配置")] = False,
    set: Annotated[Optional[str], typer.Option("--set", help="设置配置项，格式: key=value")] = None,
):
    """
    查看或修改 Worker 配置

    示例:
      python worker_cli.py config 1 --show
      python worker_cli.py config 1 --set symbol=ETHUSDT
    """
    try:
        if set:
            try:
                key, value = set.split("=", 1)
                key = key.strip()
                value = value.strip()

                try:
                    parsed_value = json.loads(value)
                except json.JSONDecodeError:
                    parsed_value = value

                body = {"config": {key: parsed_value}}
                _patch(f"/api/workers/{worker_id}/config", body)
                typer.secho(f"✓ 配置已更新: {key} = {parsed_value}", fg=typer.colors.GREEN)

            except ValueError:
                typer.echo("✗ 配置项格式错误，请使用 key=value 格式", err=True)
                raise typer.Exit(1)

        else:
            worker = _get(f"/api/workers/{worker_id}")

            strategy_id = worker.get('strategy_id')
            strategy_name = _get_strategy_name(strategy_id) if strategy_id else "N/A"
            symbols_str = _format_symbols(worker)

            typer.echo(f"Worker {worker_id} 配置:")
            typer.echo(f"{'='*50}")
            typer.echo(f"ID: {worker.get('id')}")
            typer.echo(f"名称: {worker.get('name')}")
            typer.echo(f"描述: {worker.get('description') or '无'}")
            typer.echo(f"策略ID: {strategy_id}")
            typer.echo(f"策略名称: {strategy_name}")
            typer.echo(f"交易所: {worker.get('exchange')}")
            typer.echo(f"交易对: {symbols_str}")
            typer.echo(f"时间周期: {worker.get('timeframe')}")
            typer.echo(f"市场类型: {worker.get('market_type')}")
            typer.echo(f"交易模式: {worker.get('trading_mode')}")
            typer.echo(f"配置: {json.dumps(worker.get('config', {}), indent=2)}")
            typer.echo(f"创建时间: {worker.get('created_at')}")
            typer.echo(f"更新时间: {worker.get('updated_at')}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def strategies(
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    列出所有可用的策略

    直接从本地数据库查询策略列表，用于创建 Worker 时选择策略 ID。

    示例:
      python worker_cli.py strategies
      python worker_cli.py strategies --format json
    """
    try:
        from strategy.models import Strategy
        from collector.db.database import SessionLocal
        from collector.db.database import init_database_config

        init_database_config()
        db = SessionLocal()
        try:
            strategies_list = db.query(Strategy).all()
        finally:
            db.close()

        if not strategies_list:
            typer.echo("没有可用的策略")
            raise typer.Exit(0)

        strategies_data = [s.to_dict() for s in strategies_list]

        if format == OutputFormat.JSON:
            typer.echo(json.dumps(strategies_data, indent=2, ensure_ascii=False, default=str))
        else:
            typer.echo(f"\n总计: {len(strategies_data)} 个策略\n")
            typer.echo(f"{'ID':<8} {'名称':<25} {'文件':<20} {'描述':<30}")
            typer.echo("-" * 90)

            for strategy in strategies_data:
                strategy_id = str(strategy.get("id", "N/A"))[:6]
                name = strategy.get("name", "N/A")[:23]
                file_name = strategy.get("file_name", "N/A")[:18]
                description = strategy.get("description", "")[:28]
                description = description.split('\n')[0]

                typer.echo(f"{strategy_id:<8} {name:<25} {file_name:<20} {description:<30}")

            typer.echo("\n提示: 使用策略ID创建 Worker")
            typer.echo("  例如: python worker_cli.py create --name worker_001 --strategy-id 1")

    except Exception as e:
        _handle_general_error(e)


# ==================== 日志命令 ====================

@app.command()
def logs(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    level: Annotated[Optional[str], typer.Option("--level", "-l", help="日志级别筛选")] = None,
    lines: Annotated[int, typer.Option("--lines", "-n", help="显示行数")] = 50,
    offset: Annotated[Optional[int], typer.Option("--offset", "-o", help="偏移量（分页，默认尾行模式显示最后N条）")] = None,
    keyword: Annotated[Optional[str], typer.Option("--keyword", "-k", help="关键词搜索")] = None,
    start_time: Annotated[Optional[str], typer.Option("--start", help="开始时间 (ISO 8601)")] = None,
    end_time: Annotated[Optional[str], typer.Option("--end", help="结束时间 (ISO 8601)")] = None,
    clear: Annotated[bool, typer.Option("--clear", "-c", help="清理日志")] = False,
    before_days: Annotated[Optional[int], typer.Option("--before-days", help="清理多少天前的日志")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="确认清理，不提示")] = False,
    show_path: Annotated[bool, typer.Option("--show-path", help="显示日志文件路径")] = False,
    stats: Annotated[bool, typer.Option("--stats", "-s", help="显示日志统计信息")] = False,
):
    """
    查看或清理 Worker 日志

    示例:
      python worker_cli.py logs 1                    # 查看日志
      python worker_cli.py logs 1 --level ERROR --lines 100
      python worker_cli.py logs 1 --keyword timeout     # 搜索关键词
      python worker_cli.py logs 1 --clear            # 清理所有日志
      python worker_cli.py logs 1 --clear --before-days 7  # 清理7天前的日志
      python worker_cli.py logs 1 --show-path         # 显示日志文件路径
      python worker_cli.py logs 1 --stats             # 显示统计信息
    """
    from pathlib import Path

    try:
        # 显示日志文件路径（本地信息）
        if show_path:
            script_dir = Path(__file__).parent
            log_dir = script_dir.parent / "logs"
            log_file = log_dir / f"worker_{worker_id}.log"
            typer.echo(f"日志文件路径: {log_file.absolute()}")
            if log_file.exists():
                size = log_file.stat().st_size
                typer.echo(f"文件大小: {size / 1024:.2f} KB")
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                typer.echo(f"最后修改: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                typer.echo("文件尚未创建（Worker 可能未启动或无日志输出）")
            return

        # 清理日志模式
        if clear:
            if not yes:
                if before_days:
                    confirm_msg = f"确定要清理 Worker {worker_id} {before_days} 天前的日志吗?"
                else:
                    confirm_msg = f"确定要清理 Worker {worker_id} 的所有日志吗?"
                if not typer.confirm(confirm_msg):
                    typer.echo("已取消")
                    raise typer.Exit(0)

            body = {"confirm": True}
            if before_days:
                body["before_days"] = before_days
            result = _delete(f"/api/workers/{worker_id}/monitoring/logs")
            deleted_count = result.get("deleted_count", 0) if isinstance(result, dict) else 0
            typer.secho(f"✓ 已清理 {deleted_count} 个日志文件", fg=typer.colors.GREEN)
            return

        # 查看日志模式
        # 默认 tail 模式：offset 未指定时，先获取总数再计算偏移量
        actual_offset = offset
        if offset is None:
            count_params = {"limit": 1, "offset": 0}
            if level:
                count_params["level"] = level
            if start_time:
                count_params["start_time"] = start_time
            if end_time:
                count_params["end_time"] = end_time
            count_result = _get(f"/api/workers/{worker_id}/monitoring/logs", params=count_params)
            total_for_calc = count_result.get("total", 0) if isinstance(count_result, dict) else 0
            actual_offset = max(0, total_for_calc - lines)

        params = {
            "limit": lines,
            "offset": actual_offset,
        }
        if level:
            params["level"] = level
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        result = _get(f"/api/workers/{worker_id}/monitoring/logs", params=params)

        log_items = result.get("items", []) if isinstance(result, dict) else []
        total = result.get("total", 0) if isinstance(result, dict) else len(log_items)

        if not log_items:
            typer.echo("暂无日志")
            return

        typer.echo(f"显示 {len(log_items)} / {total} 条日志:\n")
        for log in log_items:
            source = log.get("source", "")

            if source == "raw":
                typer.echo(log.get('message', ''))
                continue

            timestamp = log.get("timestamp", "N/A")
            if timestamp != "N/A":
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    dt_local = dt.astimezone()
                    timestamp = dt_local.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass

            log_level = log.get("level", "INFO")
            level_color = {
                "DEBUG": typer.colors.WHITE,
                "INFO": typer.colors.GREEN,
                "WARNING": typer.colors.YELLOW,
                "ERROR": typer.colors.RED,
                "CRITICAL": typer.colors.RED,
            }.get(log_level, typer.colors.WHITE)

            source_str = f"[{source}] " if source else ""

            typer.echo(f"[{timestamp}] ", nl=False)
            typer.secho(f"{log_level:<8}", fg=level_color, nl=False)
            typer.echo(f" {source_str}{log.get('message', '')}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def tail(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    lines: Annotated[int, typer.Option("--lines", "-n", help="初始显示行数")] = 20,
    level: Annotated[Optional[str], typer.Option("--level", "-l", help="日志级别筛选")] = None,
):
    """
    实时跟踪 Worker 日志（简化版）

    通过定时轮询 HTTP 接口实现实时日志跟踪功能。
    按 Ctrl+C 停止监控。

    示例:
      python worker_cli.py tail 1                    # 实时跟踪
      python worker_cli.py tail 1 --lines 50         # 显示前50行再跟踪
      python worker_cli.py tail 1 --level ERROR      # 只跟踪错误日志
    """
    try:
        typer.secho(f"🔍 开始实时跟踪 Worker {worker_id} 日志...", fg=typer.colors.CYAN)
        typer.echo("按 Ctrl+C 停止监控\n")

        # 显示历史日志
        if lines > 0:
            hist_params = {"limit": lines, "offset": 0}
            if level:
                hist_params["level"] = level
            result = _get(f"/api/workers/{worker_id}/monitoring/logs", params=hist_params)
            history = result.get("items", []) if isinstance(result, dict) else []

            for log in history:
                _print_log_entry(log)

            if history:
                typer.echo("--- 以上为历史日志，以下是实时更新 ---\n")

        last_total = 0
        try:
            while True:
                time.sleep(1)

                try:
                    check_params = {"limit": 10, "offset": 0}
                    if level:
                        check_params["level"] = level
                    result = _get(f"/api/workers/{worker_id}/monitoring/logs", params=check_params)
                    total = result.get("total", 0) if isinstance(result, dict) else 0

                    if total > last_total:
                        new_logs_count = total - last_total
                        logs_params = {"limit": new_logs_count, "offset": last_total}
                        if level:
                            logs_params["level"] = level
                        logs_result = _get(f"/api/workers/{worker_id}/monitoring/logs", params=logs_params)
                        new_logs = logs_result.get("items", []) if isinstance(logs_result, dict) else []

                        for log in new_logs:
                            _print_log_entry(log)

                        last_total = total
                except Exception:
                    pass

        except KeyboardInterrupt:
            typer.secho("\n✓ 监控已停止", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ 错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("realtime-logs")
def realtime_logs(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则查看全局")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="最大返回条数")] = 100,
    level: Annotated[Optional[str], typer.Option("--level", "-l", help="日志级别筛选(DEBUG/INFO/WARNING/ERROR)")] = None,
    keyword: Annotated[Optional[str], typer.Option("--keyword", "-k", help="关键词搜索")] = None,
    watch: Annotated[bool, typer.Option("--watch", "-w", help="持续监控模式")] = False,
    interval: Annotated[int, typer.Option("--interval", "-i", help="监控刷新间隔(秒)")] = 2,
):
    """
    查询实时内存日志

    通过 HTTP 从服务器获取最近的日志。

    特点:
      - 支持多维度过滤（级别、关键词）
      - 可选持续监控模式

    示例:
      python worker_cli.py realtime-logs              # 查看全局最近100条日志
      python worker_cli.py realtime-logs 1            # 查看 Worker 1 最近日志
      python worker_cli.py realtime-logs --level ERROR --limit 50
      python worker_cli.py realtime-logs --keyword timeout --watch  # 持续监控含 timeout 的日志
    """
    try:
        if not watch:
            # 单次查询模式
            params = {"limit": limit}
            if level:
                params["level"] = level
            if keyword:
                params["keyword"] = keyword

            path = f"/api/workers/{worker_id}/logs/recent" if worker_id else "/api/workers/logs/recent"
            result = _get(path, params=params)
            logs_list = result.get("items", []) if isinstance(result, dict) else []

            if not logs_list:
                typer.echo("暂无日志（缓冲区为空）")
                return

            worker_filter = f" [Worker {worker_id}]" if worker_id else " [全局]"
            level_filter = f" [{level}]" if level else ""
            keyword_filter = f" 关键词:'{keyword}'" if keyword else ""

            typer.echo(f"实时内存日志查询结果{worker_filter}{level_filter}{keyword_filter}:")
            typer.echo(f"{'='*80}")
            typer.echo(f"共 {len(logs_list)} 条\n")

            for log in logs_list:
                timestamp = log.get('timestamp', 'N/A')
                log_level = log.get('level', 'INFO')
                message = log.get('message', '')
                log_wid = log.get('worker_id', '')

                level_color = {
                    "DEBUG": typer.colors.WHITE,
                    "INFO": typer.colors.GREEN,
                    "WARNING": typer.colors.YELLOW,
                    "ERROR": typer.colors.RED,
                }.get(log_level, typer.colors.WHITE)

                worker_prefix = f"[{log_wid}] " if log_wid else ""

                typer.echo(f"[{timestamp[:19]}] ", nl=False)
                typer.secho(f"{log_level:<8}", fg=level_color, nl=False)
                typer.echo(f" {worker_prefix}{message[:120]}")

        else:
            # 持续监控模式
            worker_suffix = f" (Worker {worker_id})" if worker_id else ""
            typer.secho(
                f"🔍 开始监控实时日志{worker_suffix}...",
                fg=typer.colors.CYAN
            )
            typer.echo("按 Ctrl+C 停止\n")

            last_timestamp = None
            path = f"/api/workers/{worker_id}/logs/recent" if worker_id else "/api/workers/logs/recent"
            try:
                while True:
                    params = {"limit": limit}
                    if level:
                        params["level"] = level
                    if keyword:
                        params["keyword"] = keyword
                    result = _get(path, params=params)
                    logs_list = result.get("items", []) if isinstance(result, dict) else []

                    if logs_list:
                        latest_ts = logs_list[-1].get('timestamp')
                        if latest_ts != last_timestamp:
                            os.system('clear' if os.name == 'posix' else 'cls')
                            latest_ts_display = latest_ts[:19] if latest_ts else 'N/A'
                            typer.echo(
                                f"实时日志监控 - "
                                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                                f"(最新: {latest_ts_display})\n"
                            )

                            for log in logs_list[-20:]:
                                timestamp = log.get('timestamp', 'N/A')
                                log_level = log.get('level', 'INFO')
                                message = log.get('message', '')
                                log_wid = log.get('worker_id', '')

                                level_color = {
                                    "DEBUG": typer.colors.WHITE,
                                    "INFO": typer.colors.GREEN,
                                    "WARNING": typer.colors.YELLOW,
                                    "ERROR": typer.colors.RED,
                                }.get(log_level, typer.colors.WHITE)

                                wid_prefix = f"[{log_wid}] " if log_wid else ""
                                typer.echo(f"[{timestamp[:19]}] ", nl=False)
                                typer.secho(f"{log_level:<8}", fg=level_color, nl=False)
                                typer.echo(f" {wid_prefix}{message[:100]}")

                            last_timestamp = latest_ts
                    else:
                        if last_timestamp is None:
                            typer.echo("等待日志数据...")

                    time.sleep(interval)

            except KeyboardInterrupt:
                typer.secho("\n✓ 监控已停止", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command("log-stats")
def log_stats():
    """
    查看全局日志统计信息

    通过 HTTP 从服务器获取日志统计。

    示例:
      python worker_cli.py log-stats
    """
    try:
        stats_data = _get("/api/workers/logs/stats")

        typer.echo("全局日志统计:")
        typer.echo(f"{'='*50}")
        typer.echo(f"缓冲区容量: {stats_data.get('max_size', 0):,} 条")
        typer.echo(f"当前条目数: {stats_data.get('current_size', 0):,} 条")
        typer.echo(f"使用率: {stats_data.get('utilization_percent', 0)}%")
        typer.echo(f"剩余空间: {stats_data.get('remaining_capacity', 0):,} 条")
        typer.echo(f"\n累计统计:")
        typer.echo(f"  总追加: {stats_data.get('total_appended', 0):,} 条")
        typer.echo(f"  总淘汰: {stats_data.get('total_evicted', 0):,} 条")
        typer.echo(f"\n级别分布:")

        level_counts = stats_data.get("level_counts", {})
        if level_counts:
            total = sum(level_counts.values())
            for lvl, count in sorted(level_counts.items(), key=lambda x: -x[1]):
                percentage = (count / total * 100) if total > 0 else 0
                bar_len = int(percentage / 5)
                bar = "█" * bar_len
                color = {
                    "ERROR": typer.colors.RED,
                    "WARNING": typer.colors.YELLOW,
                    "INFO": typer.colors.GREEN,
                    "DEBUG": typer.colors.WHITE,
                }.get(lvl, typer.colors.WHITE)

                typer.echo(f"  ", nl=False)
                typer.secho(f"{lvl:<8}", fg=color, nl=False)
                typer.echo(f"{count:>6,} ({percentage:5.1f}%) {bar}")

        if stats_data.get('last_timestamp'):
            typer.echo(f"\n最后日志时间: {stats_data['last_timestamp']}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 系统监控命令 ====================

@app.command()
def monitor(
    interval: Annotated[int, typer.Option("--interval", "-i", help="刷新间隔(秒)")] = 5,
):
    """
    监控所有 Worker 状态

    通过 HTTP 轮询服务器获取实时状态。

    示例:
      python worker_cli.py monitor
      python worker_cli.py monitor --interval 10
    """
    try:
        typer.secho(f"开始监控 Worker，刷新间隔: {interval}秒，按 Ctrl+C 停止...\n", 
                   fg=typer.colors.CYAN)

        try:
            while True:
                os.system('clear' if os.name == 'posix' else 'cls')
                typer.echo(f"QuantCell Worker 监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

                workers_data = _get("/api/workers/")
                workers = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))
                
                total = len(workers)
                running_count = sum(1 for w in workers if w.get("status") == "running")

                typer.echo(f"总 Worker 数: {total} | 运行中: {running_count} | 已停止: {total - running_count}")
                typer.echo("-" * 80)

                if workers:
                    _print_worker_table(workers)
                else:
                    typer.echo("没有 Worker")

                time.sleep(interval)

        except KeyboardInterrupt:
            typer.secho("\n监控已停止", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def health(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则检查所有")] = None,
):
    """
    健康检查

    通过 HTTP 获取 Worker 健康状态。

    示例:
      python worker_cli.py health              # 检查所有 Worker
      python worker_cli.py health 1            # 检查指定 Worker
    """
    try:
        if worker_id:
            health_data = _get(f"/api/workers/{worker_id}/lifecycle/health")

            typer.echo(f"Worker {worker_id} 健康检查:")
            typer.echo(f"{'='*50}")
            typer.echo(f"状态: {health_data.get('status', 'unknown')}")
            typer.echo(f"是否健康: ", nl=False)
            is_healthy = health_data.get('is_healthy', False)
            typer.secho(f"{'✓ 是' if is_healthy else '✗ 否'}", 
                       fg=typer.colors.GREEN if is_healthy else typer.colors.RED)

            checks = health_data.get('checks', {})
            if checks:
                typer.echo(f"\n检查项:")
                for check_name, check_result in checks.items():
                    status = "✓" if check_result else "✗"
                    color = typer.colors.GREEN if check_result else typer.colors.RED
                    typer.secho(f"  {status} {check_name}", fg=color)

        else:
            workers_data = _get("/api/workers/")
            workers = workers_data if isinstance(workers_data, list) else workers_data.get('items', workers_data.get('workers', []))

            healthy_count = 0
            unhealthy_count = 0
            issues = []

            for worker in workers:
                wid = worker.get('worker_id', worker.get('id'))
                if worker.get("status") == "running":
                    try:
                        h = _get(f"/api/workers/{wid}/lifecycle/health")
                        if h.get('is_healthy', False):
                            healthy_count += 1
                        else:
                            unhealthy_count += 1
                            wname = worker.get('name', 'Unknown')
                            issues.append(f"Worker {wid} ({wname}): 不健康")
                    except Exception as e:
                        unhealthy_count += 1
                        wname = worker.get('name', 'Unknown')
                        issues.append(f"Worker {wid} ({wname}): 检查失败 - {e}")

            typer.echo("健康检查完成:")
            typer.echo(f"  健康: {healthy_count}")
            typer.echo(f"  异常: {unhealthy_count}")
            typer.echo(f"  总计: {len(workers)}")

            if issues:
                typer.echo(f"\n发现问题 ({len(issues)} 个):")
                for issue in issues:
                    typer.secho(f"  ! {issue}", fg=typer.colors.YELLOW)
            else:
                typer.secho("\n✓ 所有检查通过", fg=typer.colors.GREEN)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def diagnose(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则诊断系统")] = None,
):
    """
    诊断 Worker 系统状态

    通过组合多个 HTTP 接口获取诊断信息。

    示例:
      python worker_cli.py diagnose           # 诊断系统整体状态
      python worker_cli.py diagnose 3         # 诊断指定 Worker
    """
    try:
        if worker_id:
            state_data = _get(f"/api/workers/{worker_id}/state")
            health_data = _get(f"/api/workers/{worker_id}/lifecycle/health")
        else:
            state_data = _get("/api/workers/")
            health_data = {}

        typer.echo("=" * 60)
        typer.echo("Worker 系统诊断报告")
        typer.echo("=" * 60)
        typer.echo(f"诊断时间: {datetime.now().isoformat()}")

        if worker_id:
            typer.echo(f"Worker ID: {worker_id}")
            typer.echo(f"\n[基本信息]")
            typer.secho(f"  ✓ Worker 存在", fg=typer.colors.GREEN)
            typer.echo(f"    - 名称: {state_data.get('name')}")
            typer.echo(f"    - 当前状态: {state_data.get('status')}")
            typer.echo(f"    - PID: {state_data.get('pid') or 'N/A'}")
            typer.echo(f"    - 策略ID: {state_data.get('strategy_id')}")

            typer.echo(f"\n[健康检查]")
            is_healthy = health_data.get('is_healthy', False)
            typer.secho(f"  是否健康: {is_healthy}", fg=typer.colors.GREEN if is_healthy else typer.colors.RED)
            typer.echo(f"  进程存活: {health_data.get('is_alive', False)}")

            issues = health_data.get('issues', [])
            if issues:
                typer.echo(f"  问题:")
                for issue in issues:
                    typer.secho(f"    ! {issue}", fg=typer.colors.YELLOW)

            try:
                metrics = _get(f"/api/workers/{worker_id}/monitoring/metrics")
                typer.echo(f"\n[性能指标]")
                typer.echo(f"  CPU 使用率: {metrics.get('cpu_usage', 0):.1f}%")
                typer.echo(f"  内存使用: {metrics.get('memory_usage_mb', 0):.2f} MB")
            except Exception:
                pass
        else:
            workers = state_data if isinstance(state_data, list) else state_data.get('items', state_data.get('workers', []))
            total = len(workers)
            running = sum(1 for w in workers if w.get('status') == 'running')
            stopped = sum(1 for w in workers if w.get('status') == 'stopped')
            error_count = sum(1 for w in workers if w.get('status') == 'error')

            typer.echo(f"\n[系统概览]")
            typer.echo(f"  - 总 Worker 数: {total}")
            typer.echo(f"  - 运行中: {running}")
            typer.echo(f"  - 已停止: {stopped}")
            typer.echo(f"  - 错误: {error_count}")

            issues_list = [w for w in workers if w.get('status') == 'error']
            if issues_list:
                typer.echo(f"\n⚠ 发现 {len(issues_list)} 个异常 Worker:")
                for w in issues_list:
                    wid = w.get('worker_id', w.get('id'))
                    wname = w.get('name', 'Unknown')
                    typer.secho(f"    - {wname} (ID: {wid})", fg=typer.colors.RED)

        typer.echo("\n" + "=" * 60)
        typer.echo("诊断完成")
        typer.echo("=" * 60)
        typer.echo("如需详细信息，请访问 Web 前端或使用具体命令查看。")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 数据查询命令 ====================

@app.command()
def trades(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    symbol: Annotated[Optional[str], typer.Option("--symbol", "-s", help="交易对筛选（如 BTCUSDT）")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="返回数量")] = 50,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    查询Worker成交记录（通过 HTTP）

    通过 HTTP 从服务器查询 Worker 的成交记录。

    示例:
      python worker_cli.py trades 1                    # 查询最近50条成交记录
      python worker_cli.py trades 1 --symbol BTCUSDT   # 筛选BTCUSDT交易对
      python worker_cli.py trades 1 --limit 20          # 只显示20条
      python worker_cli.py trades 1 --format json       # JSON格式输出
    """
    try:
        params = {
            "page": 1,
            "page_size": limit,
        }
        if symbol:
            params["symbol"] = symbol

        result = _get(f"/api/workers/{worker_id}/monitoring/trades", params=params)

        trades_list = result.get("items", []) if isinstance(result, dict) else []
        total = result.get("total", 0) if isinstance(result, dict) else len(trades_list)

        if not trades_list:
            typer.echo("暂无成交记录")
            return

        if format == OutputFormat.JSON:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            typer.echo(f"\nWorker {worker_id} 成交记录:")
            typer.echo(f"{'='*80}")
            typer.secho(f"数据来源: HTTP API", fg=typer.colors.GREEN)
            typer.echo(f"总计: {total} 条 (显示前 {len(trades_list)} 条)")

            if symbol:
                typer.echo(f"交易对: {symbol}")

            typer.echo(f"\n{'时间':<22} {'交易ID':<25} {'方向':<6} {'类型':<8} {'数量':>10} {'价格':>12} {'金额':>14}")
            typer.echo("-" * 100)

            for trade in trades_list:
                created_at = trade.get('created_at', 'N/A')
                trade_id = str(trade.get('trade_id', 'N/A'))[:23]
                side = trade.get('side', 'N/A')
                order_type = trade.get('order_type', 'N/A')
                quantity = trade.get('quantity', 0)
                price = trade.get('price', 0)
                amount = trade.get('amount', 0)

                side_color = typer.colors.GREEN if side == 'BUY' else typer.colors.RED

                typer.echo(f"{created_at:<22} {trade_id:<25} ", nl=False)
                typer.secho(f"{side:<6}", fg=side_color, nl=False)
                typer.echo(f" {order_type:<8} {quantity:>10.4f} {price:>12.2f} {amount:>14.2f}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def positions(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    查询Worker当前持仓

    通过 HTTP 从服务器获取持仓信息。

    示例:
      python worker_cli.py positions 1
    """
    try:
        result = _get(f"/api/workers/{worker_id}/strategy/positions")

        if result:
            positions_list = result.get("items", result.get("positions", [])) if isinstance(result, dict) else []
            if not positions_list:
                typer.echo(f"Worker {worker_id} 暂无持仓")
                return

            if format == OutputFormat.JSON:
                typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            else:
                typer.echo(f"\nWorker {worker_id} 持仓信息:")
                typer.echo(f"{'='*60}")
                for pos in positions_list:
                    typer.echo(f"  交易对: {pos.get('symbol', 'N/A')}")
                    typer.echo(f"  方向: {pos.get('side', 'N/A')}")
                    typer.echo(f"  数量: {pos.get('quantity', 0)}")
                    typer.echo(f"  均价: {pos.get('avg_price', 0)}")
                    typer.echo(f"  未实现盈亏: {pos.get('unrealized_pnl', 0)}")
                    typer.echo("-" * 40)
        else:
            typer.echo(f"\nWorker {worker_id} 持仓信息:")
            typer.echo(f"{'='*60}")
            typer.secho("暂无持仓数据", fg=typer.colors.YELLOW)

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command()
def orders(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="订单事件类型筛选（如 OrderFilled）")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="返回数量")] = 50,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    查询Worker订单列表（通过 HTTP）

    通过 HTTP 从服务器查询订单记录。

    示例:
      python worker_cli.py orders 1                     # 查询最近订单
      python worker_cli.py orders 1 --limit 20           # 只显示20条
      python worker_cli.py orders 1 --format json        # JSON格式输出
    """
    try:
        params = {"limit": limit}
        if status:
            params["status"] = status

        result = _get(f"/api/workers/{worker_id}/strategy/orders", params=params)

        orders_list = result.get("items", []) if isinstance(result, dict) else []
        total = result.get("total", 0) if isinstance(result, dict) else len(orders_list)

        if not orders_list:
            typer.echo("暂无订单记录")
            return

        if format == OutputFormat.JSON:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            typer.echo(f"\nWorker {worker_id} 订单列表:")
            typer.echo(f"{'='*85}")
            typer.secho(f"数据来源: HTTP API", fg=typer.colors.GREEN)
            typer.echo(f"总计: {total} 条 (显示前 {len(orders_list)} 条)")

            typer.echo(f"\n{'时间':<22} {'订单ID':<25} {'事件类型':<18} {'方向':<6} {'数量':>10} {'价格':>12}")
            typer.echo("-" * 105)

            for order in orders_list:
                created_at = order.get('created_at', 'N/A')
                order_id = str(order.get('order_id', order.get('client_order_id', 'N/A')))[:23]
                event_type = order.get('event_type', 'N/A')[:16]
                side = order.get('side', 'N/A')
                quantity = order.get('quantity', order.get('last_qty', 0))
                price = order.get('price', order.get('last_px', 0))

                event_colors = {
                    "OrderFilled": typer.colors.GREEN,
                    "OrderAccepted": typer.colors.CYAN,
                    "OrderRejected": typer.colors.RED,
                    "OrderCanceled": typer.colors.YELLOW,
                    "OrderExpired": typer.colors.MAGENTA,
                }
                event_color = event_colors.get(event_type, typer.colors.WHITE)

                side_color = typer.colors.GREEN if side == 'BUY' else typer.colors.RED

                typer.echo(f"{created_at:<22} {order_id:<25} ", nl=False)
                typer.secho(f"{event_type:<18}", fg=event_color, nl=False)
                typer.echo(f" ", nl=False)
                typer.secho(f"{side:<6}", fg=side_color, nl=False)
                typer.echo(f" {quantity:>10.4f} {price:>12.2f}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 全局回调 ====================

@app.callback()
def main(
    server: Annotated[str, typer.Option("--server", help="FastAPI 服务器地址")] = "http://localhost:8000",
):
    """Worker 管理命令行工具 - HTTP Client 模式"""
    global _server_url
    _server_url = server.rstrip("/")


if __name__ == "__main__":
    app()