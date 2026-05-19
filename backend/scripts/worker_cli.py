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
  python worker_cli.py --server http://remote:8000 list # 连接远程服务器

注意: 此工具通过 HTTP 与 FastAPI 服务器通信，确保服务器正在运行。
""",
    add_completion=False,
)

# 全局 --server 选项
_server_url: str = "http://localhost:8000"
_local_mode: bool = False


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


# ==================== 本地数据库查询辅助函数 ====================

def _get_local_db():
    from collector.db.database import SessionLocal
    db = SessionLocal()
    return db


def _local_trades(worker_id, symbol=None, side=None, order_type=None, pnl_status=None, start_time=None, end_time=None, skip=0, limit=50):
    db = _get_local_db()
    try:
        from worker.crud import get_worker_trades_paginated
        result, total = get_worker_trades_paginated(db, worker_id, symbol, side, order_type, pnl_status, start_time, end_time, skip, limit)
        return [r.to_dict() for r in result], total
    finally:
        db.close()


def _local_orders(worker_id, status=None, symbol=None, side=None, order_type=None, start_time=None, end_time=None, skip=0, limit=50):
    db = _get_local_db()
    try:
        from worker.crud import get_worker_orders_paginated
        result, total = get_worker_orders_paginated(db, worker_id, status, symbol, side, order_type, start_time, end_time, skip, limit)
        return [r.to_dict() for r in result], total
    finally:
        db.close()


def _local_positions(worker_id, status="OPEN", symbol=None, side=None):
    db = _get_local_db()
    try:
        from worker.crud import get_worker_positions_filtered
        result = get_worker_positions_filtered(db, worker_id, status, symbol, side)
        return [r.to_dict() for r in result]
    finally:
        db.close()


def _local_trading_summary(worker_id):
    db = _get_local_db()
    try:
        from worker.crud import get_trading_summary
        return get_trading_summary(db, worker_id)
    finally:
        db.close()


def _local_pnl_distribution(worker_id):
    db = _get_local_db()
    try:
        from worker.crud import get_pnl_distribution
        return get_pnl_distribution(db, worker_id)
    finally:
        db.close()


def _local_trade_history(worker_id, days=30):
    db = _get_local_db()
    try:
        from worker.crud import get_trade_history_chart
        return get_trade_history_chart(db, worker_id, days)
    finally:
        db.close()


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


# ==================== 批量操作命令 ====================

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

    支持 --local 模式直接查询本地数据库获取完整交易统计。

    示例:
      python worker_cli.py stats              # 查看全局统计
      python worker_cli.py stats 1            # 查看指定 Worker 统计
      python worker_cli.py stats 1 --local    # 本地数据库直连模式
    """
    try:
        if worker_id:
            if _local_mode:
                summary = _local_trading_summary(worker_id)
                if summary:
                    _display_trading_summary(worker_id, summary)
                else:
                    typer.echo(f"Worker {worker_id} 暂无交易统计数据")
                return

            try:
                summary = _get(f"/api/workers/{worker_id}/stats/trading-summary")
                if summary:
                    _display_trading_summary(worker_id, summary)
                    return
            except Exception:
                pass

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


def _display_trading_summary(worker_id: int, summary: dict):
    typer.echo(f"\nWorker {worker_id} 交易汇总统计")
    typer.echo(f"{'='*50}")
    typer.secho(f"数据来源: {'本地数据库' if _local_mode else 'HTTP API'}", fg=typer.colors.GREEN)

    total_trades = summary.get('total_trades', 0)
    win_rate = summary.get('win_rate', 0)
    total_pnl = summary.get('total_pnl', 0)
    profit_factor = summary.get('profit_factor', 0)

    typer.echo(f"\n核心指标:")
    typer.echo(f"  总交易次数: {total_trades}        ", nl=False)
    typer.secho(f"胜率: {win_rate:.1f}%", fg=typer.colors.GREEN)
    typer.echo(f"  总盈亏:     ", nl=False)
    pnl_color = typer.colors.GREEN if float(total_pnl) >= 0 else typer.colors.RED
    typer.secho(f"{total_pnl:.2f}", fg=pnl_color, nl=False)
    typer.echo(f"           ", nl=False)
    typer.secho(f"盈亏比: {profit_factor:.2f}", fg=typer.colors.CYAN)

    winning_trades = summary.get('winning_trades', 0)
    losing_trades = summary.get('losing_trades', 0)
    total_profit = summary.get('total_profit', 0)
    total_loss = summary.get('total_loss', 0)
    largest_profit = summary.get('largest_profit', 0)
    largest_loss = summary.get('largest_loss', 0)
    average_profit = summary.get('average_profit', 0)
    average_loss = summary.get('average_loss', 0)

    typer.echo(f"\n盈亏详情:")
    typer.secho(f"  盈利次数: {winning_trades}", fg=typer.colors.GREEN, nl=False)
    typer.echo(f"        ", nl=False)
    typer.secho(f"亏损次数: {losing_trades}", fg=typer.colors.RED)
    typer.secho(f"  总盈利:   {total_profit:.2f}", fg=typer.colors.GREEN, nl=False)
    typer.echo(f"         ", nl=False)
    typer.secho(f"总亏损: {total_loss:.2f}", fg=typer.colors.RED)
    typer.secho(f"  最大盈利: {largest_profit:.2f}", fg=typer.colors.GREEN, nl=False)
    typer.echo(f"       ", nl=False)
    typer.secho(f"最大亏损: {largest_loss:.2f}", fg=typer.colors.RED)
    typer.secho(f"  平均盈利: {average_profit:.2f}", fg=typer.colors.GREEN, nl=False)
    typer.echo(f"       ", nl=False)
    typer.secho(f"平均亏损: {average_loss:.2f}", fg=typer.colors.RED)

    total_volume = summary.get('total_volume', 0)
    total_fees = summary.get('total_fees', 0)
    trading_days = summary.get('trading_days', 0)
    daily_average_trades = summary.get('daily_average_trades', 0)

    typer.echo(f"\n交易量统计:")
    typer.echo(f"  总成交量: {total_volume:.2f}         ", nl=False)
    typer.echo(f"总手续费: {total_fees:.2f}")
    typer.echo(f"  交易天数: {trading_days}            ", nl=False)
    typer.echo(f"日均交易: {daily_average_trades:.1f}")


# ==================== 配置管理命令 ====================

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
            log_dir = script_dir.parent / "logs" / "worker"
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
                timestamp = log.get("timestamp", "N/A")
                if timestamp != "N/A":
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        dt_local = dt.astimezone()
                        timestamp = dt_local.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass
                typer.echo(f"[{timestamp}] ", nl=False)
                typer.secho("RAW     ", fg=typer.colors.WHITE, nl=False)
                typer.echo(f" {log.get('message', '')}")
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


# ==================== 数据查询命令 ====================

@app.command()
def trades(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    symbol: Annotated[Optional[str], typer.Option("--symbol", "-s", help="交易对筛选（如 BTCUSDT）")] = None,
    side: Annotated[Optional[str], typer.Option("--side", help="买卖方向: buy/sell")] = None,
    order_type: Annotated[Optional[str], typer.Option("--order-type", help="订单类型: market/limit/stop")] = None,
    pnl_status: Annotated[Optional[str], typer.Option("--pnl-status", help="盈亏状态: profit/loss/flat")] = None,
    start_time: Annotated[Optional[str], typer.Option("--start-time", help="开始时间 (ISO格式)")] = None,
    end_time: Annotated[Optional[str], typer.Option("--end-time", help="结束时间 (ISO格式)")] = None,
    page: Annotated[int, typer.Option("--page", "-p", help="页码")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", "-n", help="每页数量")] = 50,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    查询Worker成交记录

    支持多维度筛选：交易对、方向、订单类型、盈亏状态、时间范围。
    支持 --local 模式直接查询本地数据库。

    示例:
      python worker_cli.py trades 1                          # 查询最近50条成交记录
      python worker_cli.py trades 1 --symbol BTCUSDT         # 筛选BTCUSDT交易对
      python worker_cli.py trades 1 --side buy --pnl-status profit
      python worker_cli.py trades 1 --start-time 2024-01-01 --end-time 2024-01-31
      python worker_cli.py trades 1 --local                  # 本地数据库直连模式
    """
    try:
        if _local_mode:
            skip = (page - 1) * page_size
            trades_list, total = _local_trades(
                worker_id, symbol=symbol, side=side, order_type=order_type,
                pnl_status=pnl_status, start_time=start_time, end_time=end_time,
                skip=skip, limit=page_size
            )
        else:
            params = {
                "page": page,
                "page_size": page_size,
            }
            if symbol:
                params["symbol"] = symbol
            if side:
                params["side"] = side
            if order_type:
                params["order_type"] = order_type
            if pnl_status:
                params["pnl_status"] = pnl_status
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time

            result = _get(f"/api/workers/{worker_id}/monitoring/trades", params=params)

            trades_list = result.get("items", []) if isinstance(result, dict) else []
            total = result.get("total", 0) if isinstance(result, dict) else len(trades_list)

        if not trades_list:
            typer.echo("暂无成交记录")
            return

        if format == OutputFormat.JSON:
            output = {"items": trades_list, "total": total, "page": page, "page_size": page_size}
            typer.echo(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        else:
            data_source = "本地数据库" if _local_mode else "HTTP API"
            typer.echo(f"\nWorker {worker_id} 成交记录:")
            typer.echo(f"{'='*80}")
            typer.secho(f"数据来源: {data_source}", fg=typer.colors.GREEN)
            typer.echo(f"总计: {total} 条 (第 {page} 页，每页 {page_size} 条)")

            if symbol:
                typer.echo(f"交易对: {symbol}")
            if side:
                typer.echo(f"方向: {side}")
            if pnl_status:
                typer.echo(f"盈亏状态: {pnl_status}")

            typer.echo(f"\n{'时间':<22} {'交易ID':<25} {'方向':<6} {'类型':<8} {'数量':>10} {'价格':>12} {'金额':>14}")
            typer.echo("-" * 100)

            for trade in trades_list:
                created_at = trade.get('created_at', 'N/A')
                trade_id = str(trade.get('trade_id', 'N/A'))[:23]
                trade_side = trade.get('side', 'N/A')
                trade_order_type = trade.get('order_type', 'N/A')
                quantity = trade.get('quantity', 0)
                price = trade.get('price', 0)
                amount = trade.get('amount', 0)

                side_upper = trade_side.upper() if isinstance(trade_side, str) else str(trade_side)
                side_color = typer.colors.GREEN if side_upper == 'BUY' else typer.colors.RED

                typer.echo(f"{created_at:<22} {trade_id:<25} ", nl=False)
                typer.secho(f"{side_upper:<6}", fg=side_color, nl=False)
                typer.echo(f" {trade_order_type:<8} {quantity:>10.4f} {price:>12.2f} {amount:>14.2f}")

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
    status: Annotated[str, typer.Option("--status", "-s", help="持仓状态: OPEN/CLOSED")] = "OPEN",
    symbol: Annotated[Optional[str], typer.Option("--symbol", help="交易对筛选")] = None,
    side: Annotated[Optional[str], typer.Option("--side", help="方向: long/short")] = None,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    查询Worker当前持仓

    支持 --local 模式直接查询本地数据库。

    示例:
      python worker_cli.py positions 1
      python worker_cli.py positions 1 --status OPEN --symbol BTCUSDT
      python worker_cli.py positions 1 --local
    """
    try:
        if _local_mode:
            positions_list = _local_positions(worker_id, status=status, symbol=symbol, side=side)
        else:
            result = _get(f"/api/workers/{worker_id}/strategy/positions")
            positions_list = result.get("items", result.get("positions", [])) if isinstance(result, dict) else []

            if symbol and positions_list:
                positions_list = [p for p in positions_list if p.get('symbol') == symbol]
            if side and positions_list:
                positions_list = [p for p in positions_list if p.get('side', '').lower() == side.lower()]

        if not positions_list:
            typer.echo(f"Worker {worker_id} 暂无持仓")
            return

        if format == OutputFormat.JSON:
            typer.echo(json.dumps({"items": positions_list}, indent=2, ensure_ascii=False, default=str))
        else:
            data_source = "本地数据库" if _local_mode else "HTTP API"
            typer.echo(f"\nWorker {worker_id} 持仓信息:")
            typer.echo(f"{'='*70}")
            typer.secho(f"数据来源: {data_source}", fg=typer.colors.GREEN)
            typer.echo(f"持仓数: {len(positions_list)}")
            if symbol:
                typer.echo(f"交易对: {symbol}")
            if side:
                typer.echo(f"方向: {side}")

            total_value = 0.0
            total_unrealized_pnl = 0.0

            typer.echo(f"\n{'交易对':<14} {'方向':<8} {'数量':>12} {'均价':>12} {'未实现盈亏':>14}")
            typer.echo("-" * 65)

            for pos in positions_list:
                pos_symbol = pos.get('symbol', 'N/A')
                pos_side = pos.get('side', 'N/A')
                quantity = pos.get('quantity', 0) or 0
                avg_price = pos.get('avg_price', 0) or 0
                unrealized_pnl = pos.get('unrealized_pnl', 0) or 0

                total_value += float(quantity) * float(avg_price)
                total_unrealized_pnl += float(unrealized_pnl)

                pnl_color = typer.colors.GREEN if float(unrealized_pnl) >= 0 else typer.colors.RED

                typer.echo(f"{pos_symbol:<14} {pos_side:<8} {float(quantity):>12.4f} {float(avg_price):>12.2f} ", nl=False)
                typer.secho(f"{float(unrealized_pnl):>14.2f}", fg=pnl_color)

            typer.echo("-" * 65)
            typer.echo(f"{'汇总':<14} {'':<8} {'':>12} {'':>12} ", nl=False)
            pnl_summary_color = typer.colors.GREEN if total_unrealized_pnl >= 0 else typer.colors.RED
            typer.secho(f"{total_unrealized_pnl:>14.2f}", fg=pnl_summary_color)
            typer.echo(f"  总持仓价值: {total_value:,.2f}")

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
    symbol: Annotated[Optional[str], typer.Option("--symbol", help="交易对筛选")] = None,
    side: Annotated[Optional[str], typer.Option("--side", help="买卖方向: buy/sell")] = None,
    order_type: Annotated[Optional[str], typer.Option("--order-type", help="订单类型")] = None,
    start_time: Annotated[Optional[str], typer.Option("--start-time", help="开始时间 (ISO格式)")] = None,
    end_time: Annotated[Optional[str], typer.Option("--end-time", help="结束时间 (ISO格式)")] = None,
    page: Annotated[int, typer.Option("--page", "-p", help="页码")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", "-n", help="每页数量")] = 50,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    查询Worker订单列表

    支持多维度筛选和 --local 模式直接查询本地数据库。

    示例:
      python worker_cli.py orders 1                          # 查询最近订单
      python worker_cli.py orders 1 --side buy --symbol BTCUSDT
      python worker_cli.py orders 1 --start-time 2024-01-01 --end-time 2024-01-31
      python worker_cli.py orders 1 --local                   # 本地数据库直连
    """
    try:
        if _local_mode:
            skip = (page - 1) * page_size
            orders_list, total = _local_orders(
                worker_id, status=status, symbol=symbol, side=side,
                order_type=order_type, start_time=start_time, end_time=end_time,
                skip=skip, limit=page_size
            )
        else:
            params = {
                "page": page,
                "page_size": page_size,
            }
            if status:
                params["status"] = status
            if symbol:
                params["symbol"] = symbol
            if side:
                params["side"] = side
            if order_type:
                params["order_type"] = order_type
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time

            result = _get(f"/api/workers/{worker_id}/strategy/orders", params=params)

            orders_list = result.get("items", []) if isinstance(result, dict) else []
            total = result.get("total", 0) if isinstance(result, dict) else len(orders_list)

        if not orders_list:
            typer.echo("暂无订单记录")
            return

        if format == OutputFormat.JSON:
            output = {"items": orders_list, "total": total, "page": page, "page_size": page_size}
            typer.echo(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        else:
            data_source = "本地数据库" if _local_mode else "HTTP API"
            typer.echo(f"\nWorker {worker_id} 订单列表:")
            typer.echo(f"{'='*85}")
            typer.secho(f"数据来源: {data_source}", fg=typer.colors.GREEN)
            typer.echo(f"总计: {total} 条 (第 {page} 页，每页 {page_size} 条)")

            typer.echo(f"\n{'时间':<22} {'订单ID':<25} {'事件类型':<18} {'方向':<6} {'数量':>10} {'价格':>12}")
            typer.echo("-" * 105)

            for order in orders_list:
                created_at = order.get('created_at', 'N/A')
                order_id = str(order.get('order_id', order.get('client_order_id', 'N/A')))[:23]
                event_type = order.get('event_type', 'N/A')[:16]
                order_side = order.get('side', 'N/A')
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

                side_color = typer.colors.GREEN if order_side == 'BUY' else typer.colors.RED

                typer.echo(f"{created_at:<22} {order_id:<25} ", nl=False)
                typer.secho(f"{event_type:<18}", fg=event_color, nl=False)
                typer.echo(f" ", nl=False)
                typer.secho(f"{order_side:<6}", fg=side_color, nl=False)
                typer.echo(f" {quantity:>10.4f} {price:>12.2f}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


# ==================== 交易统计命令 ====================

@app.command("trading-stats")
def trading_stats(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """显示Worker交易汇总统计（核心指标卡片）"""
    try:
        if _local_mode:
            summary = _local_trading_summary(worker_id)
        else:
            summary = _get(f"/api/workers/{worker_id}/stats/trading-summary")

        if not summary:
            typer.echo(f"Worker {worker_id} 暂无交易统计数据")
            return

        data_source = "本地数据库" if _local_mode else "HTTP API"

        total_trades = summary.get('total_trades', 0)
        win_rate = summary.get('win_rate', 0)
        total_pnl = summary.get('total_pnl', 0)
        profit_factor = summary.get('profit_factor', 0)

        winning_trades = summary.get('winning_trades', 0)
        losing_trades = summary.get('losing_trades', 0)
        total_profit = summary.get('total_profit', 0)
        total_loss = summary.get('total_loss', 0)
        largest_profit = summary.get('largest_profit', 0)
        largest_loss = summary.get('largest_loss', 0)
        average_profit = summary.get('average_profit', 0)
        average_loss = summary.get('average_loss', 0)

        total_volume = summary.get('total_volume', 0)
        total_fees = summary.get('total_fees', 0)
        trading_days = summary.get('trading_days', 0)
        daily_average_trades = summary.get('daily_average_trades', 0)

        typer.echo(f"\nWorker {worker_id} 交易统计")
        typer.echo(f"{'='*50}")
        typer.secho(f"数据来源: {data_source}", fg=typer.colors.CYAN)

        typer.echo(f"\n核心指标:")
        typer.echo(f"  总交易次数: {total_trades}", nl=False)
        typer.secho(f"        胜率: {win_rate:.1f}%", fg=typer.colors.GREEN)
        typer.echo(f"  总盈亏:     ", nl=False)
        pnl_color = typer.colors.GREEN if float(total_pnl) >= 0 else typer.colors.RED
        typer.secho(f"{total_pnl:.2f}", fg=pnl_color, nl=False)
        typer.secho(f"          盈亏比: {profit_factor:.2f}", fg=typer.colors.CYAN)

        typer.echo(f"\n盈亏详情:")
        typer.secho(f"  盈利次数: {winning_trades}", fg=typer.colors.GREEN, nl=False)
        typer.secho(f"        亏损次数: {losing_trades}", fg=typer.colors.RED)
        typer.secho(f"  总盈利:   {total_profit:.2f}", fg=typer.colors.GREEN, nl=False)
        typer.secho(f"        总亏损: {total_loss:.2f}", fg=typer.colors.RED)
        typer.secho(f"  最大盈利: {largest_profit:.2f}", fg=typer.colors.GREEN, nl=False)
        typer.secho(f"      最大亏损: {largest_loss:.2f}", fg=typer.colors.RED)
        typer.secho(f"  平均盈利: {average_profit:.2f}", fg=typer.colors.GREEN, nl=False)
        typer.secho(f"      平均亏损: {average_loss:.2f}", fg=typer.colors.RED)

        typer.echo(f"\n交易量统计:")
        typer.echo(f"  总成交量: {total_volume:.2f}", nl=False)
        typer.echo(f"         总手续费: {total_fees:.2f}")
        typer.echo(f"  交易天数: {trading_days}", nl=False)
        typer.echo(f"           日均交易: {daily_average_trades:.1f}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command("pnl-distribution")
def pnl_distribution(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """显示Worker盈亏分布"""
    try:
        if _local_mode:
            dist_data = _local_pnl_distribution(worker_id)
        else:
            dist_data = _get(f"/api/workers/{worker_id}/stats/pnl-distribution")

        if not dist_data:
            typer.echo(f"Worker {worker_id} 暂无盈亏分布数据")
            return

        bins = dist_data.get('bins', [])
        counts = dist_data.get('counts', [])

        if not bins or not counts:
            typer.echo("暂无交易数据")
            return

        data_source = "本地数据库" if _local_mode else "HTTP API"

        typer.echo(f"\nWorker {worker_id} 盈亏分布")
        typer.echo(f"{'='*60}")
        typer.secho(f"数据来源: {data_source}", fg=typer.colors.CYAN)

        max_count = max(counts) if counts else 1
        max_bar_len = 40

        typer.echo(f"\n{'区间':>12}  {'笔数':>6}  {'分布'}")
        typer.echo("-" * 70)

        for i, (b, c) in enumerate(zip(bins, counts)):
            bar_len = int(c / max_count * max_bar_len) if max_count > 0 else 0
            bar = "█" * bar_len
            bin_label = f"{b:.2f}" if isinstance(b, float) else str(b)
            color = typer.colors.GREEN if (isinstance(b, (int, float)) and b >= 0) else typer.colors.RED
            typer.echo(f"  {bin_label:>10}  {c:>6}  ", nl=False)
            typer.secho(f"{bar}", fg=color)

        mean_val = dist_data.get('mean', 0)
        median_val = dist_data.get('median', 0)
        std_val = dist_data.get('std', 0)

        typer.echo(f"\n统计参数:")
        typer.echo(f"  均值: {mean_val:.4f}    中位数: {median_val:.4f}    标准差: {std_val:.4f}")

    except typer.Exit:
        raise
    except requests.exceptions.ConnectionError:
        typer.secho(f"✗ 无法连接到服务器 {_server_url}", fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as e:
        _handle_general_error(e)


@app.command("trade-history")
def trade_history(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    days: Annotated[int, typer.Option("--days", "-d", help="查询天数")] = 30,
):
    """显示Worker每日交易历史汇总"""
    try:
        if _local_mode:
            history_data = _local_trade_history(worker_id, days)
        else:
            history_data = _get(f"/api/workers/{worker_id}/stats/trade-history-chart", params={"days": days})

        if not history_data:
            typer.echo(f"Worker {worker_id} 暂无交易历史数据")
            return

        daily_data = history_data.get('daily', history_data.get('items', []))
        if not daily_data:
            typer.echo(f"Worker {worker_id} 最近 {days} 天暂无交易数据")
            return

        data_source = "本地数据库" if _local_mode else "HTTP API"

        typer.echo(f"\nWorker {worker_id} 最近 {days} 天交易历史")
        typer.echo(f"{'='*75}")
        typer.secho(f"数据来源: {data_source}", fg=typer.colors.CYAN)

        typer.echo(f"\n{'日期':<14} {'每日盈亏':>16}  {'累计盈亏':>16}  {'交易次数':>8}")
        typer.echo("-" * 75)

        cumulative_pnl = 0.0
        for entry in daily_data:
            date_str = entry.get('date', entry.get('trade_date', 'N/A'))
            daily_pnl = entry.get('pnl', entry.get('daily_pnl', 0)) or 0
            trade_count = entry.get('trades', entry.get('trade_count', 0)) or 0

            cumulative_pnl += float(daily_pnl)

            pnl_daily_color = typer.colors.GREEN if float(daily_pnl) >= 0 else typer.colors.RED
            pnl_cumul_color = typer.colors.GREEN if cumulative_pnl >= 0 else typer.colors.RED

            typer.echo(f"{date_str:<14} ", nl=False)
            typer.secho(f"{float(daily_pnl):>+14.2f}", fg=pnl_daily_color, nl=False)
            typer.echo(f"  ", nl=False)
            typer.secho(f"{cumulative_pnl:>14.2f}", fg=pnl_cumul_color, nl=False)
            typer.echo(f"  {trade_count:>8}")

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
    local: Annotated[bool, typer.Option("--local", help="直接使用本地SQLite数据库查询")] = False,
):
    """Worker 管理命令行工具 - HTTP Client 模式"""
    global _server_url, _local_mode
    _server_url = server.rstrip("/")
    _local_mode = local


if __name__ == "__main__":
    app()