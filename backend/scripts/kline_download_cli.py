#!/usr/bin/env python3
"""
K线数据下载命令行工具
支持通过命令行方式下载加密货币K线数据并存储到数据库
"""

import sys
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import time

import typer
from typing_extensions import Annotated
from loguru import logger

# 添加后端目录到路径
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# 导入项目内部模块
try:
    from collector.scripts.get_data import GetData
    from collector.services.data_service import DataService
    from collector.schemas.data import DownloadCryptoRequest
    from collector.utils.task_manager import task_manager
    from collector.db.database import init_database_config, SessionLocal
    from collector.db.models import CryptoSpotKline, CryptoFutureKline
    from settings.models import SystemConfigBusiness as SystemConfig
except ImportError as e:
    logger.error(f"导入模块失败: {e}")
    logger.error("请确保在正确的目录下运行此脚本")
    sys.exit(1)

# 创建Typer应用
app = typer.Typer(
    name="kline-download",
    help="K线数据下载命令行工具",
    epilog="""
示例:
  # 下载BTCUSDT的日线数据
  python kline_download_cli.py download -s BTCUSDT -i 1d --start 2024-01-01 --end 2024-12-31

  # 下载多个交易对的多时间周期数据
  python kline_download_cli.py download -s BTCUSDT -s ETHUSDT -i 1h -i 1d --start 2024-01-01 --end 2024-12-31

  # 使用4个线程下载数据
  python kline_download_cli.py download -s BTCUSDT -i 1m --start 2024-01-01 --end 2024-01-31 --max-workers 4

  # 查询任务状态
  python kline_download_cli.py status -t <task_id>

  # 列出支持的货币对
  python kline_download_cli.py list-symbols -e binance
    """
)


def init_db():
    """初始化数据库连接"""
    try:
        init_database_config()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


@app.command()
def download(
    symbols: Annotated[List[str], typer.Option("--symbols", "-s", help="交易对列表，可多次指定")] = None,
    interval: Annotated[List[str], typer.Option("--interval", "-i", help="时间周期列表，可多次指定(如: 1m, 5m, 15m, 30m, 1h, 4h, 1d)")] = None,
    start: Annotated[str, typer.Option("--start", help="开始时间(格式: YYYY-MM-DD)")] = None,
    end: Annotated[str, typer.Option("--end", help="结束时间(格式: YYYY-MM-DD)")] = None,
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    max_workers: Annotated[int, typer.Option("--max-workers", "-w", help="最大工作线程数")] = 1,
    mode: Annotated[str, typer.Option("--mode", "-m", help="下载模式(inc: 增量, full: 全量)")] = "inc",
    save_dir: Annotated[Optional[str], typer.Option("--save-dir", help="保存目录(可选，默认从系统配置读取)")] = None,
    to_db: Annotated[bool, typer.Option("--to-db/--no-db", help="是否直接写入数据库")] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="显示详细日志")] = False,
):
    """
    下载K线数据
    
    支持多交易对、多时间周期批量下载，数据将保存到指定目录并可选写入数据库
    """
    if verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    
    # 验证必需参数
    if not symbols:
        typer.echo("错误: 请指定至少一个交易对，使用 -s 或 --symbols 参数", err=True)
        raise typer.Exit(1)
    
    if not interval:
        typer.echo("错误: 请指定至少一个时间周期，使用 -i 或 --interval 参数", err=True)
        raise typer.Exit(1)
    
    if not start or not end:
        typer.echo("错误: 请指定开始时间和结束时间，使用 --start 和 --end 参数", err=True)
        raise typer.Exit(1)
    
    # 验证时间格式
    try:
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        typer.echo("错误: 时间格式不正确，请使用 YYYY-MM-DD 格式", err=True)
        raise typer.Exit(1)
    
    # 验证模式
    if mode not in ["inc", "full"]:
        typer.echo("错误: 模式必须是 'inc'(增量) 或 'full'(全量)", err=True)
        raise typer.Exit(1)
    
    try:
        # 初始化数据库
        init_db()
        
        # 如果没有指定保存目录，从系统配置读取
        if not save_dir:
            save_dir = SystemConfig.get("data_download_dir")
            if save_dir:
                logger.info(f"从系统配置读取到保存目录: {save_dir}")
            else:
                save_dir = "data/download"
                logger.warning(f"未找到系统配置，使用默认保存目录: {save_dir}")
        
        # 创建下载请求
        request = DownloadCryptoRequest(
            symbols=symbols,
            interval=interval,
            start=start,
            end=end,
            exchange=exchange,
            max_workers=max_workers,
            candle_type=candle_type,
            save_dir=save_dir,
            mode=mode
        )
        
        logger.info(f"创建下载任务，参数: {request.model_dump()}")
        
        # 创建数据服务实例
        data_service = DataService()
        
        # 创建下载任务
        result = data_service.create_download_task(request)
        
        if not result["success"]:
            typer.echo(f"创建下载任务失败: {result['message']}", err=True)
            raise typer.Exit(1)
        
        task_id = result["task_id"]
        typer.echo(f"✓ 下载任务已创建")
        typer.echo(f"  任务ID: {task_id}")
        typer.echo(f"  交易对: {', '.join(symbols)}")
        typer.echo(f"  时间周期: {', '.join(interval)}")
        typer.echo(f"  时间范围: {start} ~ {end}")
        typer.echo(f"  交易所: {exchange}")
        typer.echo(f"  蜡烛类型: {candle_type}")
        typer.echo(f"  下载模式: {mode}")
        typer.echo(f"  保存目录: {save_dir}")
        typer.echo("")
        
        # 执行下载
        typer.echo("开始下载数据...")
        
        with typer.progressbar(length=100, label="下载进度") as progress:
            # 定义进度回调
            def progress_callback(current, completed, total, failed, status=None):
                if total > 0:
                    progress_pct = int((completed / total) * 100)
                    progress.update(progress_pct - progress.n)
                    if status:
                        progress.label = f"下载进度 - {status}"
            
            # 执行异步下载
            DataService.async_download_crypto(task_id, request)
        
        # 获取最终任务状态
        task_info = task_manager.get_task(task_id)
        
        if task_info and task_info.get("status") == "completed":
            typer.echo("")
            typer.echo("✓ 下载完成!")
            typer.echo(f"  已完成: {task_info.get('completed', 0)}")
            typer.echo(f"  失败: {task_info.get('failed', 0)}")
            typer.echo(f"  总任务数: {task_info.get('total', 0)}")
        else:
            typer.echo("")
            typer.echo("✗ 下载可能未完成，请使用 status 命令查询任务状态")
        
        typer.echo(f"\n可使用以下命令查询任务状态:")
        typer.echo(f"  python kline_download_cli.py status -t {task_id}")
        
    except Exception as e:
        logger.exception(f"下载数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def status(
    task_id: Annotated[str, typer.Option("--task-id", "-t", help="任务ID")],
    watch: Annotated[bool, typer.Option("--watch", "-w", help="持续监控任务状态")] = False,
    interval: Annotated[int, typer.Option("--interval", help="监控间隔(秒)")] = 5,
):
    """
    查询下载任务状态
    
    可以查询指定任务的当前状态和进度，支持持续监控模式
    """
    try:
        init_db()
        
        if watch:
            typer.echo(f"开始监控任务 {task_id}，按 Ctrl+C 停止...")
            try:
                while True:
                    task_info = task_manager.get_task(task_id)
                    if not task_info:
                        typer.echo(f"任务 {task_id} 不存在", err=True)
                        raise typer.Exit(1)
                    
                    # 获取进度信息
                    progress_info = task_info.get("progress", {})
                    
                    status = task_info.get("status", "unknown")
                    
                    # 从 progress 字典或 task 根级别获取进度信息
                    if progress_info:
                        progress = progress_info.get("percentage", 0)
                        completed = progress_info.get("completed", 0)
                        total = progress_info.get("total", 0)
                        failed = progress_info.get("failed", 0)
                        current = progress_info.get("current", "")
                    else:
                        progress = task_info.get("percentage", 0)
                        completed = task_info.get("completed", 0)
                        total = task_info.get("total", 0)
                        failed = task_info.get("failed", 0)
                        current = task_info.get("current", "")
                    
                    # 清屏并显示状态
                    os.system('clear' if os.name == 'posix' else 'cls')
                    typer.echo(f"任务ID: {task_id}")
                    typer.echo(f"状态: {status}")
                    typer.echo(f"进度: {progress:.1f}% ({completed}/{total})")
                    typer.echo(f"失败: {failed}")
                    typer.echo(f"当前: {current}")
                    typer.echo(f"更新时间: {task_info.get('end_time', 'N/A')}")
                    
                    if status in ["completed", "failed"]:
                        typer.echo(f"\n任务已结束，状态: {status}")
                        break
                    
                    time.sleep(interval)
                    
            except KeyboardInterrupt:
                typer.echo("\n监控已停止")
        else:
            # 单次查询
            task_info = task_manager.get_task(task_id)
            
            if not task_info:
                typer.echo(f"任务 {task_id} 不存在", err=True)
                raise typer.Exit(1)
            
            # 获取进度信息
            progress_info = task_info.get("progress", {})
            
            # 获取参数信息
            params = task_info.get("params", {})
            
            typer.echo(f"任务ID: {task_id}")
            typer.echo(f"状态: {task_info.get('status', 'unknown')}")
            typer.echo(f"类型: {task_info.get('task_type', 'N/A')}")
            typer.echo(f"交易所: {params.get('exchange', 'N/A')}")
            
            # 从 progress 字典或 task 根级别获取进度信息
            if progress_info:
                percentage = progress_info.get("percentage", 0)
                completed = progress_info.get("completed", 0)
                total = progress_info.get("total", 0)
                failed = progress_info.get("failed", 0)
                current = progress_info.get("current", "N/A")
            else:
                percentage = task_info.get("percentage", 0)
                completed = task_info.get("completed", 0)
                total = task_info.get("total", 0)
                failed = task_info.get("failed", 0)
                current = task_info.get("current", "N/A")
            
            typer.echo(f"进度: {percentage:.1f}%")
            typer.echo(f"已完成: {completed} / {total}")
            typer.echo(f"失败: {failed}")
            typer.echo(f"当前处理: {current}")
            typer.echo(f"创建时间: {task_info.get('start_time', 'N/A')}")
            typer.echo(f"更新时间: {task_info.get('end_time', 'N/A')}")
            
            if task_info.get("error_message"):
                typer.echo(f"错误信息: {task_info.get('error_message')}")
                
    except Exception as e:
        logger.exception(f"查询任务状态时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def list_symbols(
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    limit: Annotated[int, typer.Option("--limit", "-l", help="显示数量限制")] = 50,
):
    """
    列出支持的货币对
    
    显示指定交易所支持的货币对列表
    """
    try:
        init_db()
        
        db = SessionLocal()
        try:
            # 从数据库查询货币对
            if exchange.lower() == "binance":
                symbols = db.query(CryptoSpotKline.symbol).distinct().limit(limit).all()
            else:
                typer.echo(f"暂不支持交易所: {exchange}", err=True)
                raise typer.Exit(1)
            
            if not symbols:
                typer.echo(f"未找到交易所 {exchange} 的货币对数据")
                typer.echo("提示: 请先运行数据同步脚本或下载一些数据")
                return
            
            symbol_list = [s[0] for s in symbols]
            
            typer.echo(f"交易所: {exchange}")
            typer.echo(f"货币对数量: {len(symbol_list)}")
            typer.echo("")
            
            # 分页显示
            for i in range(0, len(symbol_list), 5):
                row = symbol_list[i:i+5]
                typer.echo("  ".join(f"{s:12}" for s in row))
                
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"列出货币对时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def list_tasks(
    status_filter: Annotated[Optional[str], typer.Option("--status", "-s", help="状态过滤(pending/running/completed/failed)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="显示数量")] = 10,
):
    """
    列出最近的下载任务
    
    显示最近的K线数据下载任务列表
    """
    try:
        init_db()
        
        # 获取所有任务
        all_tasks_dict = task_manager.get_all_tasks()
        
        if not all_tasks_dict:
            typer.echo("暂无任务")
            return
        
        # 将字典转换为列表
        all_tasks = list(all_tasks_dict.values())
        
        # 过滤任务
        if status_filter:
            all_tasks = [t for t in all_tasks if t.get("status") == status_filter]
        
        # 限制数量
        all_tasks = all_tasks[:limit]
        
        typer.echo(f"{'任务ID':<36} {'类型':<15} {'状态':<10} {'进度':<8} {'交易所':<10}")
        typer.echo("-" * 90)
        
        for task in all_tasks:
            task_id = task.get("task_id", "N/A")[:36]
            task_type = task.get("task_type", "N/A")[:15]
            status = task.get("status", "N/A")[:10]
            
            # 获取进度信息 - 可能在 progress 字典中或直接在 task 中
            progress_info = task.get("progress", {})
            if progress_info:
                percentage = progress_info.get("percentage", 0)
            else:
                percentage = task.get("percentage", 0)
            progress = f"{percentage:.1f}%"
            
            # 获取交易所信息 - 从 params 字典中获取
            params = task.get("params", {})
            exchange = params.get("exchange", "N/A")[:10]
            
            typer.echo(f"{task_id:<36} {task_type:<15} {status:<10} {progress:<8} {exchange:<10}")
            
    except Exception as e:
        logger.exception(f"列出任务时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
