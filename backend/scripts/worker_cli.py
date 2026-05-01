#!/usr/bin/env python3
"""
Worker 管理命令行工具

基于 backend/worker API 接口的 CLI 客户端实现，作为 API 文档的扩展，
支持 Worker 的完整生命周期管理，包括创建、启动、停止、状态查看、
配置管理和日志查看等功能。

底层通过 HTTP API 调用与后端交互，确保 CLI 和 API 行为一致。
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urljoin

import typer
from typing_extensions import Annotated

# 尝试导入 requests，如果不可用则提供安装提示
try:
    import requests
except ImportError:
    print("错误: 需要安装 requests 模块")
    print("请运行: pip install requests")
    sys.exit(1)


class OutputFormat(str, Enum):
    """输出格式枚举"""
    TABLE = "table"
    JSON = "json"


class WorkerCLIConfig:
    """CLI 配置"""
    def __init__(self):
        self.base_url = os.getenv("WORKER_API_URL", "http://localhost:8000")
        self.api_prefix = "/api/workers"

    def get_api_url(self, path: str = "") -> str:
        """获取完整 API URL"""
        base = urljoin(self.base_url, self.api_prefix)
        if path:
            return urljoin(base + "/", path)
        return base


# 全局配置
_config = WorkerCLIConfig()


def _make_request(method: str, path: str = "", extract_data: bool = True, **kwargs) -> Any:
    """发送 HTTP 请求
    
    Args:
        method: HTTP 方法
        path: API 路径
        extract_data: 是否从 ApiResponse 中提取 data 字段
        **kwargs: 其他请求参数
    """
    url = _config.get_api_url(path)
    headers = kwargs.pop("headers", {})
    headers.setdefault("Content-Type", "application/json")

    try:
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        response.raise_for_status()
        
        if not response.content:
            return {} if extract_data else None
            
        data = response.json()
        
        # 如果需要提取 data 字段
        if extract_data and isinstance(data, dict):
            # 检查是否是 ApiResponse 格式
            if "code" in data and "data" in data:
                if data.get("code") != 0:
                    message = data.get("message", "未知错误")
                    typer.echo(f"API 错误: {message}", err=True)
                    raise typer.Exit(1)
                return data.get("data")
        
        return data
        
    except requests.exceptions.ConnectionError:
        typer.echo(f"错误: 无法连接到 API 服务器 ({_config.base_url})", err=True)
        typer.echo("请确保后端服务已启动", err=True)
        raise typer.Exit(1)
    except requests.exceptions.HTTPError as e:
        try:
            error_data = e.response.json()
            # 检查是否是 ApiResponse 格式的错误
            if "code" in error_data and "message" in error_data:
                error_msg = error_data.get("message", str(e))
            else:
                error_msg = error_data.get("detail", str(e))
        except:
            error_msg = str(e)
        typer.echo(f"API 错误: {error_msg}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"请求错误: {e}", err=True)
        raise typer.Exit(1)


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


def _print_worker_table(workers: List[Dict[str, Any]], show_header: bool = True):
    """打印 Worker 表格"""
    if show_header:
        typer.echo(f"{'ID':<8} {'名称':<20} {'状态':<12} {'PID':<10} {'运行时长':<15}")
        typer.echo("-" * 70)

    for worker in workers:
        worker_id = str(worker.get("id", "N/A"))[:6]
        name = worker.get("name", "N/A")[:18]
        state = worker.get("status", "unknown")
        pid = str(worker.get("pid")) if worker.get("pid") else "N/A"
        pid = pid[:8]
        started_at = worker.get("started_at")
        uptime = _format_uptime(started_at)

        state_color = _get_state_color(state)

        typer.echo(f"{worker_id:<8} {name:<20} ", nl=False)
        typer.secho(f"{state:<12}", fg=state_color, nl=False)
        typer.echo(f" {pid:<10} {uptime:<15}")


# 创建 Typer 应用
app = typer.Typer(
    name="worker-cli",
    help="Worker 管理命令行工具 - 基于 backend/worker API",
    epilog="""
示例:
  # 创建 Worker
  python worker_cli.py create --name worker_001 --strategy-id 1 --exchange binance --symbol BTCUSDT

  # 启动 Worker
  python worker_cli.py start 1

  # 查看 Worker 状态
  python worker_cli.py status 1

  # 列出所有 Worker
  python worker_cli.py list

  # 停止 Worker
  python worker_cli.py stop 1

环境变量:
  WORKER_API_URL - API 服务器地址 (默认: http://localhost:8000)
    """
)


# ========== Worker 创建/删除命令 ==========

@app.command()
def create(
    name: Annotated[str, typer.Option("--name", "-n", help="Worker 名称")],
    strategy_id: Annotated[int, typer.Option("--strategy-id", "-s", help="策略ID(使用 'strategies' 命令查看可用策略)")],
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    symbol: Annotated[str, typer.Option("--symbol", help="交易对")] = "BTCUSDT",
    timeframe: Annotated[str, typer.Option("--timeframe", "-t", help="时间周期")] = "1h",
    market_type: Annotated[str, typer.Option("--market-type", help="市场类型(spot/future)")] = "spot",
    trading_mode: Annotated[str, typer.Option("--trading-mode", help="交易模式(paper/live)")] = "paper",
    cpu_limit: Annotated[int, typer.Option("--cpu-limit", help="CPU核心数限制")] = 1,
    memory_limit: Annotated[int, typer.Option("--memory-limit", help="内存限制(MB)")] = 512,
    description: Annotated[Optional[str], typer.Option("--description", "-d", help="Worker 描述")] = None,
):
    """
    创建新 Worker

    示例:
      python worker_cli.py create --name worker_001 --strategy-id 1 --exchange binance --symbol BTCUSDT
    """
    try:
        worker_data = {
            "name": name,
            "description": description,
            "strategy_id": strategy_id,
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "market_type": market_type,
            "trading_mode": trading_mode,
            "cpu_limit": cpu_limit,
            "memory_limit": memory_limit,
        }

        result = _make_request("POST", json=worker_data)

        typer.echo(f"✓ Worker 创建成功")
        typer.echo(f"  ID: {result.get('id')}")
        typer.echo(f"  名称: {result.get('name')}")
        typer.echo(f"  策略ID: {result.get('strategy_id')}")
        typer.echo(f"  交易所: {result.get('exchange')}")
        typer.echo(f"  交易对: {result.get('symbol')}")
        typer.echo(f"  时间周期: {result.get('timeframe')}")
        typer.echo(f"  市场类型: {result.get('market_type')}")
        typer.echo(f"  交易模式: {result.get('trading_mode')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def delete(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="确认删除，不提示")] = False,
):
    """
    删除 Worker

    示例:
      python worker_cli.py delete 1
      python worker_cli.py delete 1 --yes
    """
    try:
        # 先获取 Worker 信息
        worker = _make_request("GET", str(worker_id))

        # 确认删除
        if not yes:
            if not typer.confirm(f"确定要删除 Worker {worker_id} ({worker.get('name')}) 吗?"):
                typer.echo("已取消")
                raise typer.Exit(0)

        # 删除 Worker
        _make_request("DELETE", str(worker_id))
        typer.echo(f"✓ Worker {worker_id} 已删除")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== Worker 生命周期命令 ==========

@app.command()
def start(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    启动指定 Worker

    示例:
      python worker_cli.py start 1
    """
    try:
        # 先检查 Worker 当前状态
        try:
            worker = _make_request("GET", str(worker_id))
            current_status = worker.get('status', 'unknown')

            if current_status == 'running':
                typer.secho(f"⚠ Worker {worker_id} 已经在运行中", fg=typer.colors.YELLOW)
                typer.echo(f"  Worker ID: {worker_id}")
                typer.echo(f"  状态: {current_status}")
                typer.echo(f"  PID: {worker.get('pid')}")
                return
        except Exception:
            # 如果获取状态失败，继续尝试启动
            pass

        result = _make_request("POST", f"{worker_id}/lifecycle/start")

        typer.secho(f"✓ Worker {worker_id} 启动成功", fg=typer.colors.GREEN)
        typer.echo(f"  Worker ID: {result.get('worker_id')}")
        typer.echo(f"  状态: {result.get('status')}")
        typer.echo(f"  PID: {result.get('pid')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def stop(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="强制停止")] = False,
):
    """
    停止指定 Worker

    示例:
      python worker_cli.py stop 1
      python worker_cli.py stop 1 --force
    """
    try:
        result = _make_request("POST", f"{worker_id}/lifecycle/stop")

        typer.echo(f"✓ Worker {worker_id} 已停止")
        typer.echo(f"  状态: {result.get('status')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def restart(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    重启指定 Worker

    示例:
      python worker_cli.py restart 1
    """
    try:
        result = _make_request("POST", f"{worker_id}/lifecycle/restart")

        typer.echo(f"✓ Worker {worker_id} 重启中")
        typer.echo(f"  任务ID: {result.get('task_id')}")
        typer.echo(f"  状态: {result.get('status')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def pause(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    暂停指定 Worker

    示例:
      python worker_cli.py pause 1
    """
    try:
        result = _make_request("POST", f"{worker_id}/lifecycle/pause")

        typer.echo(f"✓ Worker {worker_id} 已暂停")
        typer.echo(f"  状态: {result.get('status')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def resume(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
):
    """
    恢复指定 Worker

    示例:
      python worker_cli.py resume 1
    """
    try:
        result = _make_request("POST", f"{worker_id}/lifecycle/resume")

        typer.echo(f"✓ Worker {worker_id} 已恢复")
        typer.echo(f"  状态: {result.get('status')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("batch")
def batch_operation(
    operation: Annotated[str, typer.Option("--operation", "-o", help="操作: start/stop/restart")],
    worker_ids: Annotated[List[int], typer.Option("--worker-ids", "-w", help="Worker ID 列表")],
):
    """
    批量操作 Worker

    示例:
      python worker_cli.py batch --operation start --worker-ids 1 --worker-ids 2 --worker-ids 3
    """
    try:
        data = {
            "worker_ids": worker_ids,
            "operation": operation
        }

        result = _make_request("POST", "batch", json=data)

        typer.echo(f"批量操作完成:")
        typer.echo(f"  成功: {len(result.get('success', []))} 个")
        typer.echo(f"  失败: {len(result.get('failed', {}))} 个")
        typer.echo(f"  总计: {result.get('total', 0)} 个")

        if result.get('failed'):
            typer.echo(f"\n失败的 Worker:")
            for wid, error in result['failed'].items():
                typer.echo(f"  - Worker {wid}: {error}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== Worker 状态查看命令 ==========

@app.command()
def status(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则查看所有")] = None,
    watch: Annotated[bool, typer.Option("--watch", "-w", help="持续监控")] = False,
    interval: Annotated[int, typer.Option("--interval", "-i", help="监控间隔(秒)")] = 5,
):
    """
    查看 Worker 状态

    示例:
      python worker_cli.py status              # 查看所有 Worker 状态
      python worker_cli.py status 1            # 查看指定 Worker 状态
      python worker_cli.py status --watch      # 持续监控
    """
    try:
        if watch:
            # 持续监控模式
            typer.echo(f"开始监控 Worker 状态，按 Ctrl+C 停止...\n")
            try:
                while True:
                    os.system('clear' if os.name == 'posix' else 'cls')
                    typer.echo(f"QuantCell Worker 监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    _show_status(worker_id)
                    import time
                    time.sleep(interval)
            except KeyboardInterrupt:
                typer.echo("\n监控已停止")
        else:
            # 单次显示
            _show_status(worker_id)

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


def _show_status(worker_id: Optional[int] = None):
    """显示 Worker 状态"""
    if worker_id:
        # 显示单个 Worker 状态
        worker = _make_request("GET", str(worker_id))

        # 从 trading_config 解析交易配置
        trading_config = worker.get('trading_config', '{}')
        if isinstance(trading_config, str):
            try:
                import json
                trading_config = json.loads(trading_config)
            except:
                trading_config = {}

        symbols_config = trading_config.get('symbols_config', {})
        symbols = symbols_config.get('symbols', [])
        # 显示交易对，多个用逗号分隔
        symbols_str = ', '.join(symbols) if symbols else 'N/A'

        typer.echo(f"Worker ID: {worker.get('id')}")
        typer.echo(f"名称: {worker.get('name')}")
        typer.echo(f"状态: ", nl=False)
        typer.secho(f"{worker.get('status')}", fg=_get_state_color(worker.get('status', '')))
        typer.echo(f"策略ID: {worker.get('strategy_id')}")
        typer.echo(f"交易所: {trading_config.get('exchange', 'N/A')}")
        typer.echo(f"交易对: {symbols_str}")
        typer.echo(f"时间周期: {trading_config.get('timeframe', 'N/A')}")
        typer.echo(f"市场类型: {trading_config.get('market_type', 'N/A')}")
        typer.echo(f"交易模式: {trading_config.get('trading_mode', 'N/A')}")
        typer.echo(f"PID: {worker.get('pid') or 'N/A'}")
        typer.echo(f"运行时长: {_format_uptime(worker.get('started_at'))}")

        # 获取实时状态
        try:
            realtime = _make_request("GET", f"{worker_id}/lifecycle/status")
            typer.echo(f"\n实时状态:")
            typer.echo(f"  是否健康: {realtime.get('is_healthy', False)}")
            typer.echo(f"  最后心跳: {realtime.get('last_heartbeat', 'N/A')}")
        except:
            pass
    else:
        # 显示所有 Worker 状态
        result = _make_request("GET")
        workers = result.get("items", [])
        total = result.get("total", 0)

        if not workers:
            typer.echo("没有 Worker")
            return

        typer.echo(f"\n总计: {total} 个 Worker\n")
        _print_worker_table(workers)


@app.command()
def list_workers(
    status: Annotated[Optional[str], typer.Option("--status", "-s", help="按状态筛选")] = None,
    strategy_id: Annotated[Optional[int], typer.Option("--strategy-id", help="按策略ID筛选")] = None,
    page: Annotated[int, typer.Option("--page", "-p", help="页码")] = 1,
    page_size: Annotated[int, typer.Option("--page-size", help="每页数量")] = 20,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    列出所有 Worker

    示例:
      python worker_cli.py list_workers
      python worker_cli.py list_workers --status running
      python worker_cli.py list_workers --format json
    """
    try:
        params = {
            "skip": (page - 1) * page_size,
            "limit": page_size
        }
        if status:
            params["status"] = status
        if strategy_id:
            params["strategy_id"] = strategy_id

        result = _make_request("GET", params=params)
        workers = result.get("items", [])
        total = result.get("total", 0)

        if not workers:
            typer.echo("没有 Worker")
            return

        if format == OutputFormat.JSON:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            typer.echo(f"\n总计: {total} 个 Worker (第 {page} 页，每页 {page_size} 个)\n")
            _print_worker_table(workers)

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def stats(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则查看全局统计")] = None,
):
    """
    查看 Worker 统计信息

    示例:
      python worker_cli.py stats              # 查看全局统计
      python worker_cli.py stats 1            # 查看指定 Worker 统计
    """
    try:
        if worker_id:
            # 查看单个 Worker 统计
            worker = _make_request("GET", str(worker_id))

            typer.echo(f"Worker {worker_id} 统计信息:")
            typer.echo(f"{'='*50}")
            typer.echo(f"名称: {worker.get('name')}")
            typer.echo(f"状态: {worker.get('status')}")
            typer.echo(f"运行时长: {_format_uptime(worker.get('started_at'))}")

            # 获取实时指标
            try:
                metrics = _make_request("GET", f"{worker_id}/monitoring/metrics")
                typer.echo(f"\n性能指标:")
                typer.echo(f"  CPU使用率: {metrics.get('cpu_usage', 0):.1f}%")
                typer.echo(f"  内存使用率: {metrics.get('memory_usage', 0):.1f}%")
                typer.echo(f"  已用内存: {metrics.get('memory_used_mb', 0):.1f} MB")
                typer.echo(f"  活跃任务: {metrics.get('active_tasks', 0)}")
            except:
                pass

        else:
            # 查看全局统计
            result = _make_request("GET")
            workers = result.get("items", [])

            running_count = sum(1 for w in workers if w.get("status") == "running")
            stopped_count = sum(1 for w in workers if w.get("status") == "stopped")
            error_count = sum(1 for w in workers if w.get("status") == "error")

            typer.echo("全局统计信息:")
            typer.echo(f"{'='*50}")
            typer.echo(f"总 Worker 数: {len(workers)}")
            typer.echo(f"运行中: {running_count}")
            typer.echo(f"已停止: {stopped_count}")
            typer.echo(f"错误: {error_count}")

            if running_count > 0:
                typer.echo(f"\n运行中的 Worker:")
                for w in workers:
                    if w.get("status") == "running":
                        pid = w.get('pid')
                        pid_str = f", PID: {pid}" if pid else ""
                        typer.echo(f"  - {w.get('name')} (ID: {w.get('id')}{pid_str}, 运行时长: {_format_uptime(w.get('started_at'))})")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 配置管理命令 ==========

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
        strategy_api_prefix = "/api/strategy/list"
        url = urljoin(_config.base_url, strategy_api_prefix)
        response = requests.get(url, timeout=10)

        if response.ok:
            result = response.json()
            strategies_data = []

            # 处理不同的响应格式
            if isinstance(result, dict) and "data" in result:
                strategies_data = result.get("data", [])
                # 如果 data 是字典，尝试提取列表
                if isinstance(strategies_data, dict):
                    strategies_data = strategies_data.get("strategies", strategies_data.get("items", []))
            elif isinstance(result, list):
                strategies_data = result

            # 确保是列表类型
            if not isinstance(strategies_data, list):
                strategies_data = []

            # 查找匹配的策略
            for strategy in strategies_data:
                if isinstance(strategy, dict) and strategy.get("id") == strategy_id:
                    return strategy.get("name", f"策略#{strategy_id}")

    except Exception as e:
        typer.echo(f"获取策略名称失败: {e}", err=True)

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
    # 优先从 trading_config.symbols_config.symbols 获取
    trading_config = worker_data.get("trading_config", {})
    if isinstance(trading_config, str):
        try:
            trading_config = json.loads(trading_config)
        except (json.JSONDecodeError, TypeError):
            trading_config = {}

    symbols_config = trading_config.get("symbols_config", {})
    symbols = symbols_config.get("symbols", [])

    # 如果是列表且非空，格式化显示
    if isinstance(symbols, list) and symbols:
        return ", ".join(symbols)

    # 兼容旧字段 symbol（单个字符串）
    symbol = worker_data.get("symbol")
    if symbol:
        return str(symbol)

    return "N/A"



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
        worker = _make_request("GET", str(worker_id))

        if set:
            # 修改配置
            try:
                key, value = set.split("=", 1)
                key = key.strip()
                value = value.strip()

                # 尝试解析 JSON 值
                try:
                    parsed_value = json.loads(value)
                except json.JSONDecodeError:
                    parsed_value = value

                # 更新配置
                update_data = {"config": {key: parsed_value}}
                _make_request("PUT", str(worker_id), json=update_data)
                typer.echo(f"✓ 配置已更新: {key} = {parsed_value}")

            except ValueError:
                typer.echo("错误: 配置项格式错误，请使用 key=value 格式", err=True)
                raise typer.Exit(1)

        else:
            # 显示配置
            # 获取策略名称
            strategy_id = worker.get('strategy_id')
            strategy_name = _get_strategy_name(strategy_id) if strategy_id else "N/A"

            # 格式化交易对显示
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
            typer.echo(f"CPU限制: {worker.get('cpu_limit')} 核")
            typer.echo(f"内存限制: {worker.get('memory_limit')} MB")
            typer.echo(f"配置: {json.dumps(worker.get('config', {}), indent=2)}")
            typer.echo(f"创建时间: {worker.get('created_at')}")
            typer.echo(f"更新时间: {worker.get('updated_at')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


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
        # 构建更新数据
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
            typer.echo("错误: 没有指定要更新的字段", err=True)
            raise typer.Exit(1)

        result = _make_request("PUT", str(worker_id), json=update_data)

        typer.echo(f"✓ Worker {worker_id} 更新成功")
        typer.echo(f"  名称: {result.get('name')}")
        typer.echo(f"  交易对: {result.get('symbol')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 日志命令 ==========

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
        # 显示日志文件路径
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

        # 显示日志统计信息
        if stats:
            stats_result = _make_request("GET", f"{worker_id}/monitoring/logs/stats")
            typer.echo(f"\nWorker {worker_id} 日志统计:")
            typer.echo(f"{'='*50}")
            typer.echo(f"总文件数: {len(stats_result.get('files', []))}")
            typer.echo(f"总大小: {stats_result.get('total_size_human', '0 B')}")
            typer.echo(f"总行数: {stats_result.get('total_lines', 0)}")
            for fi in stats_result.get('files', []):
                typer.echo(f"  - {Path(fi['path']).name}: {fi['size_human']} ({fi['lines']} 行)")
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

            params = {"confirm": True}
            if before_days:
                params["before_days"] = before_days

            result = _make_request("DELETE", f"{worker_id}/monitoring/logs", params=params)
            deleted_count = result.get("deleted_count", 0)
            typer.echo(f"✓ 已清理 {deleted_count} 个日志文件")
            return

        # 查看日志模式
        # 默认 tail 模式：offset 未指定时，先获取总数再计算偏移量，始终显示最后 N 条
        actual_offset = offset
        if offset is None:
            count_params = {"limit": 1, "offset": 0}
            if level:
                count_params["level"] = level
            if keyword:
                count_params["keyword"] = keyword
            if start_time:
                count_params["start_time"] = start_time
            if end_time:
                count_params["end_time"] = end_time
            count_result = _make_request("GET", f"{worker_id}/monitoring/logs", params=count_params)
            if isinstance(count_result, dict) and "items" in count_result:
                total_for_calc = count_result.get("total", 0)
            else:
                total_for_calc = len(count_result) if isinstance(count_result, list) else 0
            actual_offset = max(0, total_for_calc - lines)

        params = {
            "limit": lines,
            "offset": actual_offset,
        }
        if level:
            params["level"] = level
        if keyword:
            params["keyword"] = keyword
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        result = _make_request("GET", f"{worker_id}/monitoring/logs", params=params)

        # 适配新的分页响应格式（文件存储方案）
        if isinstance(result, dict) and "items" in result:
            logs = result.get("items", [])
            total = result.get("total", 0)
        else:
            # 兼容旧格式（直接返回列表）
            logs = result if isinstance(result, list) else []
            total = len(logs)

        if not logs:
            typer.echo("暂无日志")
            return

        typer.echo(f"显示 {len(logs)} / {total} 条日志:\n")
        for log in logs:
            timestamp = log.get("timestamp", "N/A")
            if timestamp != "N/A":
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
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

            source = log.get("source", "")
            source_str = f"[{source}] " if source else ""

            typer.echo(f"[{timestamp}] ", nl=False)
            typer.secho(f"{log_level:<8}", fg=level_color, nl=False)
            typer.echo(f" {source_str}{log.get('message', '')}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 系统管理命令 ==========

@app.command()
def monitor(
    interval: Annotated[int, typer.Option("--interval", "-i", help="刷新间隔(秒)")] = 5,
):
    """
    监控所有 Worker 状态

    示例:
      python worker_cli.py monitor
      python worker_cli.py monitor --interval 10
    """
    try:
        typer.echo(f"开始监控 Worker，刷新间隔: {interval}秒，按 Ctrl+C 停止...\n")

        try:
            while True:
                os.system('clear' if os.name == 'posix' else 'cls')
                typer.echo(f"QuantCell Worker 监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

                result = _make_request("GET")
                workers = result.get("items", [])
                total = result.get("total", 0)
                running_count = sum(1 for w in workers if w.get("status") == "running")

                # 显示概览
                typer.echo(f"总 Worker 数: {total} | 运行中: {running_count} | 已停止: {total - running_count}")
                typer.echo("-" * 80)

                if workers:
                    typer.echo(f"{'ID':<8} {'名称':<20} {'状态':<12} {'PID':<10} {'运行时长':<15}")
                    typer.echo("-" * 80)

                    for worker in workers:
                        worker_id = str(worker.get("id", "N/A"))
                        name = worker.get("name", "N/A")[:18]
                        state = worker.get("status", "unknown")
                        pid = str(worker.get("pid")) if worker.get("pid") else "N/A"
                        uptime = _format_uptime(worker.get("started_at"))

                        state_color = _get_state_color(state)

                        typer.echo(f"{worker_id:<8} {name:<20} ", nl=False)
                        typer.secho(f"{state:<12}", fg=state_color, nl=False)
                        typer.echo(f" {pid:<10} {uptime:<15}")
                else:
                    typer.echo("没有 Worker")

                import time
                time.sleep(interval)

        except KeyboardInterrupt:
            typer.echo("\n监控已停止")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def health(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则检查所有")] = None,
):
    """
    健康检查

    示例:
      python worker_cli.py health              # 检查所有 Worker
      python worker_cli.py health 1            # 检查指定 Worker
    """
    try:
        if worker_id:
            # 检查单个 Worker
            health = _make_request("GET", f"{worker_id}/lifecycle/health")

            typer.echo(f"Worker {worker_id} 健康检查:")
            typer.echo(f"{'='*50}")
            typer.echo(f"状态: {health.get('status', 'unknown')}")
            typer.echo(f"是否健康: {health.get('is_healthy', False)}")

            checks = health.get('checks', {})
            if checks:
                typer.echo(f"\n检查项:")
                for check_name, check_result in checks.items():
                    status = "✓" if check_result else "✗"
                    color = typer.colors.GREEN if check_result else typer.colors.RED
                    typer.secho(f"  {status} {check_name}", fg=color)

        else:
            # 检查所有 Worker
            result = _make_request("GET")
            workers = result.get("items", [])

            healthy_count = 0
            unhealthy_count = 0
            issues = []

            for worker in workers:
                if worker.get("status") == "running":
                    try:
                        health = _make_request("GET", f"{worker.get('id')}/lifecycle/health")
                        if health.get('is_healthy', False):
                            healthy_count += 1
                        else:
                            unhealthy_count += 1
                            issues.append(f"Worker {worker.get('id')} ({worker.get('name')}): 不健康")
                    except Exception as e:
                        unhealthy_count += 1
                        issues.append(f"Worker {worker.get('id')} ({worker.get('name')}): 检查失败 - {e}")

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

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


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
        data = {
            "new_name": new_name,
            "copy_config": copy_config,
            "copy_parameters": copy_parameters
        }

        result = _make_request("POST", f"{worker_id}/clone", json=data)

        typer.echo(f"✓ Worker 克隆成功")
        typer.echo(f"  新 Worker ID: {result.get('id')}")
        typer.echo(f"  新 Worker 名称: {result.get('name')}")
        typer.echo(f"  源 Worker ID: {worker_id}")
        typer.echo(f"  复制配置: {copy_config}")
        typer.echo(f"  复制参数: {copy_parameters}")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def strategies(
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="输出格式")] = OutputFormat.TABLE,
):
    """
    列出所有可用的策略

    查询策略列表，用于创建 Worker 时选择策略 ID。

    示例:
      python worker_cli.py strategies
      python worker_cli.py strategies --format json
    """
    try:
        # 策略 API 端点
        strategy_api_prefix = "/api/strategy/list"
        url = urljoin(_config.base_url, strategy_api_prefix)

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.ConnectionError:
            typer.echo(f"错误: 无法连接到 API 服务器 ({_config.base_url})", err=True)
            raise typer.Exit(1)
        except requests.exceptions.HTTPError as e:
            typer.echo(f"API 错误: {e}", err=True)
            raise typer.Exit(1)

        # 提取策略列表
        # 处理 ApiResponse 格式
        if isinstance(result, dict) and "code" in result and "data" in result:
            if result.get("code") != 0:
                typer.echo(f"API 错误: {result.get('message', '未知错误')}", err=True)
                raise typer.Exit(1)
            strategies_data = result.get("data")
        else:
            strategies_data = result
        
        # 检查是否是列表类型（使用 __iter__ 避免 list 类型被覆盖的问题）
        if not hasattr(strategies_data, '__iter__') or isinstance(strategies_data, str):
            strategies_data = []
        elif isinstance(strategies_data, dict):
            # 尝试从 data.strategies 获取（策略API格式）
            if "strategies" in strategies_data:
                strategies_data = strategies_data["strategies"]
            # 尝试从 data.items 获取（通用格式）
            elif "items" in strategies_data:
                strategies_data = strategies_data["items"]
            else:
                strategies_data = []

        if not strategies_data:
            typer.echo("没有可用的策略")
            raise typer.Exit(0)

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
                # 只取描述的第一行
                description = description.split('\n')[0]

                typer.echo(f"{strategy_id:<8} {name:<25} {file_name:<20} {description:<30}")

            typer.echo("\n提示: 使用策略ID创建 Worker")
            typer.echo("  例如: python worker_cli.py create --name worker_001 --strategy-id 1")

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def diagnose(
    worker_id: Annotated[Optional[int], typer.Argument(help="Worker ID，不指定则诊断系统")] = None,
):
    """
    诊断 Worker 系统状态

    分析 Worker 启动后状态未变化的可能原因，帮助排查问题。

    示例:
      python worker_cli.py diagnose           # 诊断系统整体状态
      python worker_cli.py diagnose 3         # 诊断指定 Worker
    """
    try:
        typer.echo("=" * 60)
        typer.echo("Worker 系统诊断报告")
        typer.echo("=" * 60)

        # 1. 检查 API 连接和幽灵 Worker
        typer.echo("\n[1/6] 检查 API 连接...")
        try:
            result = _make_request("GET")
            typer.secho("  ✓ API 连接正常", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"  ✗ API 连接失败: {e}", fg=typer.colors.RED)
            raise typer.Exit(1)

        # 检查幽灵 Worker 进程
        typer.echo("\n[2/6] 检查幽灵 Worker 进程...")
        try:
            import subprocess
            ps_result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True
            )

            ghost_workers = []
            for line in ps_result.stdout.split("\n"):
                if "quantcell-worker" in line and "grep" not in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        # 提取 worker_id 从进程标题
                        for part in parts:
                            if part.startswith("quantcell-worker:"):
                                try:
                                    ghost_worker_id = part.split(":")[1]
                                    ghost_workers.append({
                                        "pid": pid,
                                        "worker_id": ghost_worker_id,
                                        "cmd": " ".join(parts[10:]) if len(parts) > 10 else ""
                                    })
                                except:
                                    pass
                                break

            if ghost_workers:
                typer.secho(f"  ⚠ 发现 {len(ghost_workers)} 个 Worker 进程", fg=typer.colors.YELLOW)
                for ghost in ghost_workers:
                    typer.echo(f"    - Worker {ghost['worker_id']}: PID={ghost['pid']}")

                # 检查数据库中的 Worker 状态
                workers = result.get("items", [])
                db_worker_ids = {str(w.get("id")) for w in workers}
                ghost_ids = {g["worker_id"] for g in ghost_workers}

                orphaned = ghost_ids - db_worker_ids
                if orphaned:
                    typer.secho(f"\n  ⚠ 发现 {len(orphaned)} 个幽灵 Worker (数据库中不存在):", fg=typer.colors.RED)
                    for ghost in ghost_workers:
                        if ghost["worker_id"] in orphaned:
                            typer.echo(f"    - Worker {ghost['worker_id']}: PID={ghost['pid']} (数据库中不存在)")
                    typer.echo("\n  建议操作:")
                    typer.echo("    运行以下命令终止幽灵进程:")
                    for ghost in ghost_workers:
                        if ghost["worker_id"] in orphaned:
                            typer.echo(f"      kill -9 {ghost['pid']}")
                else:
                    typer.secho("  ✓ 所有 Worker 进程都在数据库中有记录", fg=typer.colors.GREEN)
            else:
                typer.secho("  ✓ 没有发现 Worker 进程", fg=typer.colors.GREEN)

        except Exception as e:
            typer.secho(f"  ⚠ 检查 Worker 进程失败: {e}", fg=typer.colors.YELLOW)

        # 3. 检查 Worker 基本信息
        if worker_id:
            typer.echo(f"\n[3/6] 检查 Worker {worker_id} 基本信息...")
            try:
                worker = _make_request("GET", str(worker_id))
                typer.secho(f"  ✓ Worker 存在", fg=typer.colors.GREEN)
                typer.echo(f"    - 名称: {worker.get('name')}")
                typer.echo(f"    - 当前状态: {worker.get('status')}")
                typer.echo(f"    - PID: {worker.get('pid') or 'N/A'}")
                typer.echo(f"    - 策略ID: {worker.get('strategy_id')}")
            except Exception as e:
                typer.secho(f"  ✗ 获取 Worker 信息失败: {e}", fg=typer.colors.RED)
                return

            # 4. 检查生命周期状态
            typer.echo(f"\n[4/6] 检查 Worker {worker_id} 生命周期状态...")
            try:
                lifecycle = _make_request("GET", f"{worker_id}/lifecycle/status")
                typer.secho("  ✓ 生命周期接口正常", fg=typer.colors.GREEN)
                typer.echo(f"    - 是否健康: {lifecycle.get('is_healthy', False)}")
                typer.echo(f"    - 最后心跳: {lifecycle.get('last_heartbeat', 'N/A')}")
            except Exception as e:
                typer.secho(f"  ✗ 生命周期接口调用失败: {e}", fg=typer.colors.RED)
                typer.echo("    提示: Worker 可能未真正启动或通信组件未初始化")

            # 5. 检查性能指标
            typer.echo(f"\n[5/6] 检查 Worker {worker_id} 性能指标...")
            try:
                metrics = _make_request("GET", f"{worker_id}/monitoring/metrics")
                typer.secho("  ✓ 性能指标接口正常", fg=typer.colors.GREEN)

                # 检查是否是模拟数据
                is_mock = metrics.get('timestamp') is None or (
                    metrics.get('cpu_usage') == 15.5 and
                    metrics.get('memory_usage') == 45.2
                )
                if is_mock:
                    typer.secho("  ⚠ 警告: 性能指标可能是模拟数据", fg=typer.colors.YELLOW)
                    typer.echo("    原因: CommManager (ZeroMQ) 可能未正确初始化")
                    typer.echo("    建议: 检查后端服务日志，确认通信组件配置")
                else:
                    typer.echo(f"    - CPU使用率: {metrics.get('cpu_usage', 0):.1f}%")
                    typer.echo(f"    - 内存使用率: {metrics.get('memory_usage', 0):.1f}%")
            except Exception as e:
                typer.secho(f"  ✗ 性能指标接口调用失败: {e}", fg=typer.colors.RED)

            # 6. 检查日志
            typer.echo(f"\n[6/6] 检查 Worker {worker_id} 日志...")
            try:
                result = _make_request("GET", f"{worker_id}/monitoring/logs", params={"limit": 5})
                # 适配新的分页响应格式（文件存储方案）
                if isinstance(result, dict) and "items" in result:
                    logs = result.get("items", [])
                else:
                    logs = result if isinstance(result, list) else []
                if logs and len(logs) > 0:
                    typer.secho(f"  ✓ 发现 {len(logs)} 条日志", fg=typer.colors.GREEN)
                else:
                    typer.secho("  ⚠ 暂无日志", fg=typer.colors.YELLOW)
                    typer.echo("    原因: Worker 进程可能未真正运行或日志文件不存在")
            except Exception as e:
                typer.secho(f"  ✗ 日志接口调用失败: {e}", fg=typer.colors.RED)

            # 诊断总结
            typer.echo("\n" + "=" * 60)
            typer.echo("诊断总结")
            typer.echo("=" * 60)

            current_status = worker.get('status')
            if current_status == 'stopped':
                typer.secho("\n问题: Worker 启动后状态仍为 stopped", fg=typer.colors.YELLOW)
                typer.echo("\n可能原因:")
                typer.echo("  1. Worker 启动是异步操作，需要等待一段时间")
                typer.echo("  2. CommManager (ZeroMQ通信组件) 未正确初始化")
                typer.echo("  3. Worker 进程启动失败（检查后端日志）")
                typer.echo("  4. 状态更新机制未正常工作")
                typer.echo("\n建议操作:")
                typer.echo("  1. 等待 10-30 秒后再次检查状态")
                typer.echo("  2. 查看后端服务日志确认错误信息")
                typer.echo("  3. 检查 ZeroMQ 端口是否被占用")
                typer.echo("  4. 确认策略文件是否存在且可执行")
            elif current_status == 'running':
                typer.secho("\n✓ Worker 状态正常 (running)", fg=typer.colors.GREEN)
            else:
                typer.echo(f"\nWorker 当前状态: {current_status}")

        else:
            # 系统级诊断
            workers = result.get("items", [])
            typer.echo(f"\n[3/6] 系统概览")
            typer.echo(f"  - 总 Worker 数: {len(workers)}")

            running = sum(1 for w in workers if w.get('status') == 'running')
            stopped = sum(1 for w in workers if w.get('status') == 'stopped')
            error = sum(1 for w in workers if w.get('status') == 'error')
            typer.echo(f"  - 运行中: {running}")
            typer.echo(f"  - 已停止: {stopped}")
            typer.echo(f"  - 错误: {error}")

            typer.echo("\n[4/6] 检查系统健康状态...")
            try:
                # 尝试获取第一个 Worker 的指标来检查系统状态
                if workers:
                    test_worker = workers[0]
                    metrics = _make_request("GET", f"{test_worker.get('id')}/monitoring/metrics")
                    # 检查是否是模拟数据
                    if metrics.get('cpu_usage') == 15.5 and metrics.get('memory_usage') == 45.2:
                        typer.secho("  ⚠ 系统可能运行在模拟/测试模式", fg=typer.colors.YELLOW)
                        typer.echo("    原因: CommManager 未初始化，返回模拟数据")
                    else:
                        typer.secho("  ✓ 系统运行正常", fg=typer.colors.GREEN)
            except Exception as e:
                typer.secho(f"  ✗ 系统检查失败: {e}", fg=typer.colors.RED)

            typer.echo("\n[5/6] 检查 ZMQ 端口...")
            try:
                import subprocess
                ports = [5555, 5556, 5557, 5558]
                occupied_by_others = []

                for port in ports:
                    port_check = subprocess.run(
                        ["lsof", "-i", f":{port}"],
                        capture_output=True,
                        text=True
                    )
                    if port_check.returncode == 0 and port_check.stdout.strip():
                        # 检查占用端口的进程是否是 Worker 进程
                        lines = port_check.stdout.strip().split("\n")[1:]  # 跳过标题行
                        for line in lines:
                            if line and "quantcell-worker" not in line and "Python" not in line:
                                # 被非 Worker 进程占用
                                occupied_by_others.append(port)
                                break

                if occupied_by_others:
                    typer.secho(f"  ⚠ 发现 {len(occupied_by_others)} 个 ZMQ 端口被其他进程占用: {occupied_by_others}", fg=typer.colors.YELLOW)
                    typer.echo("    建议: 终止占用端口的进程或更换端口配置")
                else:
                    if running > 0:
                        typer.secho(f"  ✓ ZMQ 端口正常占用（{running} 个 Worker 正在运行）", fg=typer.colors.GREEN)
                    else:
                        typer.secho("  ✓ ZMQ 端口空闲", fg=typer.colors.GREEN)
            except Exception as e:
                typer.secho(f"  ⚠ 检查 ZMQ 端口失败: {e}", fg=typer.colors.YELLOW)

            typer.echo("\n[6/6] 诊断建议...")
            if running == 0 and len(workers) > 0:
                typer.secho("  ⚠ 有 Worker 但未运行", fg=typer.colors.YELLOW)
                typer.echo("    建议: 尝试启动 Worker")
                typer.echo(f"      python worker_cli.py start {workers[0].get('id')}")
            elif running > 0:
                typer.secho(f"  ✓ 有 {running} 个 Worker 正在运行", fg=typer.colors.GREEN)

            typer.echo("\n" + "=" * 60)
            typer.echo("建议: 如需诊断具体 Worker，请指定 Worker ID")
            typer.echo("  例如: python worker_cli.py diagnose 3")
            typer.echo("=" * 60)

    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def tail(
    worker_id: Annotated[int, typer.Argument(help="Worker ID")],
    lines: Annotated[int, typer.Option("--lines", "-n", help="初始显示行数")] = 20,
    level: Annotated[Optional[str], typer.Option("--level", "-l", help="日志级别筛选")] = None,
):
    """
    实时跟踪 Worker 日志（类似 tail -f）

    通过 WebSocket 连接实时接收日志更新。
    按 Ctrl+C 停止监控。

    示例:
      python worker_cli.py tail 1                    # 实时跟踪
      python worker_cli.py tail 1 --lines 50         # 显示前50行再跟踪
      python worker_cli.py tail 1 --level ERROR      # 只跟踪错误日志
    """
    try:
        import websocket

        ws_url = f"ws://localhost:8000/api/workers/{worker_id}/monitoring/logs/stream"

        typer.echo(f"🔍 开始实时跟踪 Worker {worker_id} 日志...")
        typer.echo("按 Ctrl+C 停止监控\n")

        # 显示历史日志
        if lines > 0:
            params = {"limit": lines}
            if level:
                params["level"] = level

            result = _make_request("GET", f"{worker_id}/monitoring/logs", params=params)
            history = result.get("items", []) if isinstance(result, dict) else (result or [])

            for log in history:
                _print_log_entry(log)

            if history:
                typer.echo("--- 以上为历史日志，以下是实时更新 ---\n")

        # WebSocket 实时接收
        def on_message(ws, message):
            import json as _json
            data = _json.loads(message)
            msg_type = data.get("type")

            if msg_type == "log":
                log = data.get("data", {})
                if not level or log.get("level") == level.upper():
                    _print_log_entry(log)
            elif msg_type == "error":
                typer.secho(f"❌ 错误: {data.get('message')}", fg=typer.colors.RED)

        def on_error(ws, error):
            typer.secho(f"⚠ WebSocket 错误: {error}", fg=typer.colors.RED)

        def on_close(ws, close_status_code, close_msg):
            typer.echo("\n✓ 连接已关闭")

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        try:
            ws.run_forever()
        except KeyboardInterrupt:
            ws.close()
            typer.echo("\n✓ 监控已停止")

    except ImportError:
        typer.echo("❌ 需要安装 websocket-client:", err=True)
        typer.echo("   pip install websocket-client", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ 错误: {e}", err=True)
        raise typer.Exit(1)


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


if __name__ == "__main__":
    app()
