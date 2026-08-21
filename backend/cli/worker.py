#!/usr/bin/env python3
"""
Worker 管理 CLI

提供 Worker 的增删改查、启停、状态监控、日志查看、交易记录查询等功能。
"""

import sys

import httpx
import typer

backend_path = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

API_BASE = "http://localhost:8000/api"

app = typer.Typer(help="Worker 管理命令行工具")

# 禁用代理: CLI 仅访问本地 FastAPI 服务,不走系统代理
_HTTP_CLIENT = httpx.Client(trust_env=False)


def _get(url: str):
    """发送 GET 请求"""
    response = _HTTP_CLIENT.get(url)
    response.raise_for_status()
    return response.json()


def _post(url: str, data: dict | None = None):
    """发送 POST 请求"""
    response = _HTTP_CLIENT.post(url, json=data)
    response.raise_for_status()
    return response.json()


def _delete(url: str):
    """发送 DELETE 请求"""
    response = _HTTP_CLIENT.delete(url)
    response.raise_for_status()
    return response.json()


@app.command("summary")
def worker_summary():
    """系统摘要 - 显示所有Worker的汇总信息"""
    try:
        data = _get(f"{API_BASE}/workers/summary")
        if isinstance(data, list) or (isinstance(data, dict) and data.get("total_workers", 0) == 0):
            typer.echo("暂无 Worker")
            return

        total = data.get("total_workers", 0)
        breakdown = data.get("status_breakdown", {})
        typer.echo(f"Worker 总数: {total}")
        for status, count in breakdown.items():
            typer.echo(f"  {status}: {count}")
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
        result = _post(f"{API_BASE}/workers", data)
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
    try:
        worker = _get(f"{API_BASE}/workers/{worker_id}")
        if worker is None:
            typer.echo(f"Worker {worker_id} 不存在")
            raise typer.Exit(1)

        if not yes:
            confirm = typer.confirm(f"确认删除 Worker '{worker.get('name', worker_id)}'?")
            if not confirm:
                typer.echo("已取消")
                return

        _delete(f"{API_BASE}/workers/{worker_id}")
        typer.echo(f"Worker {worker_id} 已删除")
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("start")
def worker_start(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """启动 Worker"""
    try:
        worker = _get(f"{API_BASE}/workers/{worker_id}")
        if worker is None:
            typer.echo(f"Worker {worker_id} 不存在")
            raise typer.Exit(1)

        status = worker.get("_state_info", {}).get("status", "")
        if status == "running":
            typer.echo(f"Worker {worker_id} 正在运行中")
            return

        _post(f"{API_BASE}/workers/{worker_id}/start")
        typer.echo("启动请求已发送")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("stop")
def worker_stop(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    force: bool = typer.Option(False, "--force", help="强制停止"),
):
    """停止 Worker"""
    try:
        data = {"force": force} if force else None
        result = _post(f"{API_BASE}/workers/{worker_id}/stop", data)
        status = result.get("status", "stopped")
        typer.echo(f"Worker {worker_id} 已停止 (状态: {status})")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("restart")
def worker_restart(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """重启 Worker"""
    try:
        result = _post(f"{API_BASE}/workers/{worker_id}/restart")
        start_result = result.get("start_result", {})
        typer.echo(f"Worker {worker_id} 重启完成 (PID: {start_result.get('pid', 'N/A')})")
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
            worker = _get(f"{API_BASE}/workers/{worker_id}")
            if worker is None:
                typer.echo(f"Worker {worker_id} 不存在")
                raise typer.Exit(1)
            _print_worker(worker)
        else:
            workers = _get(f"{API_BASE}/workers")
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


def _print_worker(worker: dict):
    """打印单个 Worker 信息"""
    typer.echo(
        f"ID: {worker.get('id')}, "
        f"名称: {worker.get('name')}, "
        f"状态: {worker.get('status', 'N/A')}, "
        f"策略: {worker.get('strategy_id', 'N/A')}"
    )


@app.command("list-workers")
def worker_list(
    status: str | None = typer.Option(None, "--status", help="按状态筛选"),
):
    """列出所有 Worker"""
    try:
        url = f"{API_BASE}/workers"
        if status:
            url += f"?status={status}"
        workers = _get(url)
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
            data = _get(f"{API_BASE}/workers/{worker_id}/stats")
            if data:
                typer.echo(f"Worker {worker_id} 统计:")
                typer.echo(f"  总交易数: {data.get('total_trades', 0)}")
                typer.echo(f"  胜率: {data.get('win_rate', 0):.1f}%")
                typer.echo(f"  总盈亏: {data.get('total_pnl', 0):.2f}")
                typer.echo(f"  盈亏比: {data.get('profit_factor', 0):.2f}")
        else:
            workers = _get(f"{API_BASE}/workers")
            typer.echo("全局统计信息")
            typer.echo(f"  Worker 总数: {len(workers)}")
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
    try:
        if show_path:
            typer.echo(f"日志文件路径: /var/log/quantcell/workers/{worker_id}/")
            return

        if clear:
            if not yes:
                confirm = typer.confirm("确认清理所有日志?")
                if not confirm:
                    typer.echo("已取消")
                    return
            result = _delete(f"{API_BASE}/workers/{worker_id}/logs")
            typer.echo(f"已清理 {result.get('deleted_count', 0)} 条日志")
            return

        _get(f"{API_BASE}/workers/{worker_id}/logs?limit={lines}")
        data = _get(f"{API_BASE}/workers/{worker_id}/logs?limit={lines}")
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
    try:
        url = f"{API_BASE}/workers/{worker_id}/trades"
        params = []
        if symbol:
            params.append(f"symbol={symbol}")
        if side:
            params.append(f"side={side}")
        if params:
            url += "?" + "&".join(params)
        data = _get(url)
        items = data.get("items", [])
        if not items:
            typer.echo("暂无成交记录")
            return
        for t in items:
            typer.echo(
                f"ID: {t.get('trade_id')}, "
                f"交易对: {t.get('symbol')}, "
                f"方向: {t.get('side')}, "
                f"价格: {t.get('price')}, "
                f"数量: {t.get('quantity')}, "
                f"金额: {t.get('amount')}"
            )
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("positions")
def worker_positions(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看当前持仓"""
    try:
        data = _get(f"{API_BASE}/workers/{worker_id}/positions")
        items = data.get("items", [])
        if not items:
            typer.echo("暂无持仓")
            return
        for p in items:
            typer.echo(
                f"交易对: {p.get('symbol')}, "
                f"方向: {p.get('side')}, "
                f"数量: {p.get('quantity')}, "
                f"均价: {p.get('avg_price')}, "
                f"未实现盈亏: {p.get('unrealized_pnl', 0):.2f}"
            )
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("orders")
def worker_orders(
    worker_id: str = typer.Argument(..., help="Worker ID"),
    status: str | None = typer.Option(None, "--status", help="按状态筛选"),
):
    """查看订单记录"""
    try:
        url = f"{API_BASE}/workers/{worker_id}/orders"
        if status:
            url += f"?status={status}"
        data = _get(url)
        items = data.get("items", [])
        if not items:
            typer.echo("暂无订单")
            return
        for o in items:
            typer.echo(
                f"ID: {o.get('order_id')}, "
                f"交易对: {o.get('symbol')}, "
                f"方向: {o.get('side')}, "
                f"类型: {o.get('event_type')}, "
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
    try:
        data = _get(f"{API_BASE}/workers/{worker_id}/trading-stats")
        if data is None:
            typer.echo("暂无交易统计数据")
            return
        typer.echo(f"Worker {worker_id} 交易统计:")
        typer.echo(f"  总交易数: {data.get('total_trades', 0)}")
        typer.echo(f"  盈利次数: {data.get('winning_trades', 0)}")
        typer.echo(f"  亏损次数: {data.get('losing_trades', 0)}")
        typer.echo(f"  胜率: {data.get('win_rate', 0):.1f}%")
        typer.echo(f"  总盈亏: {data.get('total_pnl', 0):.2f}")
        typer.echo(f"  盈亏比: {data.get('profit_factor', 0):.2f}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("pnl-distribution")
def worker_pnl_distribution(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看盈亏分布"""
    try:
        data = _get(f"{API_BASE}/workers/{worker_id}/pnl-distribution")
        if data is None:
            typer.echo("暂无盈亏分布数据")
            return
        typer.echo(f"Worker {worker_id} 盈亏分布:")
        bins = data.get("bins", [])
        counts = data.get("counts", [])
        if len(bins) == len(counts) + 1:
            for i in range(len(counts)):
                typer.echo(f"  {bins[i]:>10.2f} ~ {bins[i + 1]:>10.2f}: {'#' * counts[i]} ({counts[i]})")
        else:
            for i in range(min(len(bins), len(counts))):
                typer.echo(f"  {bins[i]:>10.2f}: {'#' * counts[i]} ({counts[i]})")
        typer.echo(f"  均值: {data.get('mean', 0):.2f}")
        typer.echo(f"  中位数: {data.get('median', 0):.2f}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command("trade-history")
def worker_trade_history(
    worker_id: str = typer.Argument(..., help="Worker ID"),
):
    """查看交易历史"""
    try:
        data = _get(f"{API_BASE}/workers/{worker_id}/trade-history")
        daily = data.get("daily", [])
        if not daily:
            typer.echo("暂无交易历史数据")
            return
        typer.echo(f"Worker {worker_id} 交易历史:")
        for d in daily:
            typer.echo(f"  {d.get('date')}: PnL={d.get('pnl', 0):.2f}, 交易数={d.get('trades', 0)}")
    except Exception as e:
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
