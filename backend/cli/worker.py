#!/usr/bin/env python3
"""
Worker 管理 CLI

提供 Worker 的增删改查、启停、状态监控、日志查看、交易记录查询等功能。
直接调用 WorkerCoreService，无需启动 FastAPI 服务。
"""

import sys

import typer

backend_path = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# 确保 worker 模块完整初始化（trading_system 等单例注册）
from worker import crud
from worker.core_service import (
    WorkerAlreadyRunningError,
    WorkerCoreService,
    WorkerNotFoundError,
    WorkerOperationError,
)
from worker.trading_system import trading_system

app = typer.Typer(help="Worker 管理命令行工具")

# 单例服务实例
_service = WorkerCoreService()


def _to_int(value: str, name: str = "ID") -> int:
    """将字符串 ID 转为 int，失败则报错退出"""
    try:
        return int(value)
    except ValueError, TypeError:
        typer.echo(f"错误: {name} 必须是整数, 收到: {value}")
        raise typer.Exit(1)


@app.command("summary")
def worker_summary():
    """系统摘要 - 显示所有Worker的汇总信息"""
    try:
        total = _service.get_worker_count()
        if total == 0:
            typer.echo("暂无 Worker")
            return

        running = _service.get_worker_count("running")
        stopped = _service.get_worker_count("stopped")
        error = _service.get_worker_count("error")
        typer.echo(f"Worker 总数: {total}")
        typer.echo(f"  running: {running}")
        typer.echo(f"  stopped: {stopped}")
        typer.echo(f"  error: {error}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("create")
def worker_create(
    name: str = typer.Option(..., "--name", help="Worker名称"),
    strategy_id: str = typer.Option(..., "--strategy-id", help="策略ID"),
    exchange: str = typer.Option("binance", "--exchange", help="交易所"),
    symbol: str = typer.Option("", "--symbol", help="交易对"),
):
    """创建新 Worker"""
    try:
        data = {"name": name, "strategy_id": strategy_id, "exchange": exchange}
        if symbol:
            data["symbol"] = symbol
        result = _service.create_worker(data)
        typer.echo(f"Worker '{result.get('name', name)}' 已创建 (ID: {result.get('id')})")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("delete")
def worker_delete(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除 Worker"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        worker = _service.get_worker(wid)
    except WorkerNotFoundError:
        typer.echo(f"Worker {wid} 不存在")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"确认删除 Worker '{worker.get('name', wid)}'?")
        if not confirm:
            typer.echo("已取消")
            return

    try:
        _service.delete_worker(wid)
        typer.echo(f"Worker {wid} 已删除")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("start")
def worker_start(worker_id: str = typer.Argument(..., help="Worker ID")):
    """启动 Worker (独立进程)"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        # 先检查状态
        status_info = _service.get_worker_status(wid)
        if status_info.get("is_running"):
            typer.echo(f"Worker {wid} 正在运行中")
            return

        result = _service.start_worker(wid)
        pid = result.get("pid", "?")
        typer.echo(f"Worker {wid} 已启动 (PID: {pid}, 状态: {result.get('status')})")
    except WorkerAlreadyRunningError:
        typer.echo(f"Worker {wid} 已在运行中")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("stop")
def worker_stop(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    force: bool = typer.Option(False, "--force", help="强制停止"),
):
    """停止 Worker"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        result = _service.stop_worker(wid)
        typer.echo(f"Worker {wid} 已停止 (状态: {result.get('status')})")
    except RuntimeError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("restart")
def worker_restart(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """重启 Worker"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        result = _service.restart_worker(wid)
        typer.echo(f"Worker {wid} 重启完成 (状态: {result.get('status')})")
    except RuntimeError as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("status")
def worker_status(
    worker_id: str | None = typer.Argument(None, help="Worker ID (不填则显示所有)"),
):
    """查看 Worker 状态"""
    try:
        if worker_id:
            wid = _to_int(worker_id, "Worker ID")
            worker = _service.get_worker(wid)
            status_info = _service.get_worker_status(wid)
            _print_worker(worker, status_info)
        else:
            result = _service.list_workers(page_size=100)
            workers = result.get("items", [])
            if not workers:
                typer.echo("暂无 Worker")
                return
            for w in workers:
                _print_worker(w)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


def _print_worker(worker: dict, status_info: dict | None = None):
    """打印单个 Worker 信息"""
    parts = [
        f"ID: {worker.get('id')}",
        f"名称: {worker.get('name')}",
        f"状态: {worker.get('status', 'N/A')}",
        f"策略: {worker.get('strategy_id', 'N/A')}",
    ]
    if status_info:
        parts.append(f"运行时: {status_info.get('runtime_status', 'N/A')}")
        parts.append(f"运行中: {status_info.get('is_running', False)}")
    typer.echo(", ".join(parts))


@app.command("list-workers")
def worker_list(
    status: str | None = typer.Option(None, "--status", help="按状态筛选"),
):
    """列出所有 Worker"""
    try:
        result = _service.list_workers(status=status, page_size=100)
        workers = result.get("items", [])
        if not workers:
            typer.echo("没有 Worker")
            return
        for w in workers:
            typer.echo(
                f"ID: {w.get('id')}, "
                f"名称: {w.get('name')}, "
                f"状态: {w.get('status', 'N/A')}, "
                f"策略: {w.get('strategy_id', 'N/A')}"
            )
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("stats")
def worker_stats(
    worker_id: str | None = typer.Argument(None, help="Worker ID (不填则显示全局统计)"),
):
    """查看统计信息"""
    try:
        if worker_id:
            wid = _to_int(worker_id, "Worker ID")
            data = _service.get_worker_stats(wid)
            typer.echo(f"Worker {wid} 统计:")
            typer.echo(f"  交易数: {data.get('trades_count', 0)}")
            typer.echo(f"  订单数: {data.get('orders_count', 0)}")
            typer.echo(f"  状态: {data.get('status', 'N/A')}")
        else:
            data = _service.get_worker_stats()
            typer.echo("全局统计信息")
            typer.echo(f"  Worker 总数: {data.get('total_workers', 0)}")
            typer.echo(f"  运行中: {data.get('running', 0)}")
            typer.echo(f"  已停止: {data.get('stopped', 0)}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("logs")
def worker_logs(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    lines: int = typer.Option(50, "--lines", "-l", help="显示行数"),
    clear: bool = typer.Option(False, "--clear", help="清理日志"),
    show_path: bool = typer.Option(False, "--show-path", help="显示日志路径"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """查看 Worker 日志"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        if show_path:
            typer.echo(f"日志目录: ./logs/workers/{wid}/")
            return

        if clear:
            if not yes:
                confirm = typer.confirm("确认清理所有日志?")
                if not confirm:
                    typer.echo("已取消")
                    return
            result = _service.clear_worker_logs(wid, before_days=None, confirm=True)
            typer.echo(f"已清理 {result.get('deleted_count', 0)} 条日志")
            return

        data = _service.get_worker_logs(wid, limit=lines)
        items = data.get("items", [])
        if not items:
            typer.echo("暂无日志")
            return
        for item in items:
            typer.echo(f"[{item.get('timestamp', '')}] [{item.get('level', 'INFO')}] {item.get('message', '')}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("trades")
def worker_trades(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    symbol: str | None = typer.Option(None, "--symbol", help="按交易对筛选"),
    side: str | None = typer.Option(None, "--side", help="按方向筛选 (buy/sell)"),
):
    """查看成交记录"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        data = _service.get_worker_trades(wid, symbol=symbol, side=side, page_size=100)
        items = data.get("items", [])
        if not items:
            typer.echo("暂无成交记录")
            return
        for t in items:
            typer.echo(
                f"ID: {t.get('id')}, "
                f"交易对: {t.get('symbol')}, "
                f"方向: {t.get('side')}, "
                f"价格: {t.get('price')}, "
                f"数量: {t.get('quantity')}"
            )
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("positions")
def worker_positions(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看当前持仓"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        worker = _service.get_worker(wid)
        # 持仓信息在 worker 的 runtime 中，通过 status 获取
        status_info = _service.get_worker_status(wid)
        typer.echo(
            f"Worker {wid} ({worker.get('name')}) 当前状态: {status_info.get('runtime_status', worker.get('status'))}"
        )
        if status_info.get("is_running"):
            typer.echo("Worker 运行中，请通过 API 或 WebSocket 查询实时持仓")
        else:
            typer.echo("Worker 未运行，无活跃持仓")
    except WorkerNotFoundError:
        typer.echo(f"Worker {wid} 不存在")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("orders")
def worker_orders(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    status: str | None = typer.Option(None, "--status", help="按状态筛选"),
):
    """查看订单记录"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        data = _service.get_worker_orders(wid, status=status)
        items = data.get("items", [])
        if not items:
            typer.echo("暂无订单")
            return
        for o in items:
            typer.echo(
                f"ID: {o.get('id')}, "
                f"交易对: {o.get('symbol')}, "
                f"方向: {o.get('side')}, "
                f"类型: {o.get('event_type', o.get('type', 'N/A'))}, "
                f"价格: {o.get('price')}, "
                f"数量: {o.get('quantity')}"
            )
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("trading-stats")
def worker_trading_stats(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看交易统计"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        data = _service.get_worker_stats(wid)
        typer.echo(f"Worker {wid} 交易统计:")
        typer.echo(f"  总交易数: {data.get('trades_count', 0)}")
        typer.echo(f"  订单数: {data.get('orders_count', 0)}")
        typer.echo(f"  状态: {data.get('status', 'N/A')}")
    except WorkerNotFoundError:
        typer.echo(f"Worker {wid} 不存在")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("pnl-distribution")
def worker_pnl_distribution(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看盈亏分布"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        data = _service.get_worker_performance(wid, days=30)
        if not data:
            typer.echo("暂无盈亏分布数据")
            return

        typer.echo(f"Worker {wid} 盈亏分布 (近30天):")
        total_pnl = sum(p.get("pnl", 0) for p in data)
        total_trades = sum(p.get("trades", 0) for p in data)
        typer.echo(f"  总盈亏: {total_pnl:.2f}")
        typer.echo(f"  总交易数: {total_trades}")

        # 按日期展示
        for p in data[:10]:  # 最多显示10天
            typer.echo(f"  {p.get('date', 'N/A')}: PnL={p.get('pnl', 0):.2f}, 交易数={p.get('trades', 0)}")
        if len(data) > 10:
            typer.echo(f"  ... 还有 {len(data) - 10} 天数据")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("trade-history")
def worker_trade_history(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看交易历史"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        data = _service.get_worker_performance(wid, days=30)
        if not data:
            typer.echo("暂无交易历史数据")
            return
        typer.echo(f"Worker {wid} 交易历史 (近30天):")
        for d in data:
            typer.echo(f"  {d.get('date')}: PnL={d.get('pnl', 0):.2f}, 交易数={d.get('trades', 0)}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("kill")
def worker_kill(worker_id: str = typer.Argument(..., help="Worker ID")):
    """强制终止 Worker 进程"""
    wid = _to_int(worker_id, "Worker ID")
    try:
        from worker.orchestrator import WorkerOrchestrator

        orch = WorkerOrchestrator.get_instance()
        if orch.kill_worker_process(wid):
            typer.echo(f"Worker {wid} 已强制终止")
        else:
            typer.echo(f"Worker {wid} 未连接")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("discover")
def worker_discover():
    """手动触发 Worker 自发现"""
    try:
        from worker.orchestrator import WorkerOrchestrator

        orch = WorkerOrchestrator.get_instance()
        orch.ensure_transport()
        typer.echo("正在扫描 Worker...")
        # 发送 ping 到所有 DB 中的 running Worker
        # 注: crud 中函数是 get_workers（返回 (workers, total) 元组），不是 list_workers
        with _service.get_db() as db:
            workers, _ = crud.get_workers(db, status="running")
        for w in workers:
            response = orch.send_command_and_wait(w.id, "ping", timeout=3.0)
            if response:
                orch._register_worker(w.id)
                typer.echo(f"  Worker {w.id} ({w.name}) 已发现")
            else:
                typer.echo(f"  Worker {w.id} ({w.name}) 无响应")
        connected = orch.list_connected_workers()
        typer.echo(f"\n已连接: {len(connected)} 个 Worker")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("health")
def worker_health():
    """健康检查报告"""
    try:
        from worker.orchestrator import WorkerOrchestrator

        orch = WorkerOrchestrator.get_instance()
        orch.ensure_transport()
        summary = orch.check_health()
        typer.echo("=== Worker 健康检查 ===")
        typer.echo(f"总数: {summary['total']}")
        typer.echo(f"已连接: {summary['connected']}")
        typer.echo(f"已断开: {summary['disconnected']}")
        if summary["disconnected_ids"]:
            typer.echo(f"断开的 Worker: {summary['disconnected_ids']}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
