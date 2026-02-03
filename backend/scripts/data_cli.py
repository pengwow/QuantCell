#!/usr/bin/env python3
"""
数据管理命令行工具
支持K线数据下载、任务管理和本地数据查询
"""

import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import time

import typer
from typing_extensions import Annotated
from loguru import logger
from sqlalchemy import func
import pandas as pd

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
    from collector.db.models import CryptoSpotKline, CryptoFutureKline, CryptoSymbol
    from settings.models import SystemConfigBusiness as SystemConfig
except ImportError as e:
    logger.error(f"导入模块失败: {e}")
    logger.error("请确保在正确的目录下运行此脚本")
    sys.exit(1)


# 创建导入导出子命令
export_app = typer.Typer(help="导出数据到文件")
import_app = typer.Typer(help="从文件导入数据到数据库")


def init_db():
    """初始化数据库连接"""
    try:
        init_database_config()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


# ========== 导出子命令 ==========

@export_app.command("csv")
def export_csv(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对，如BTCUSDT")],
    interval: Annotated[str, typer.Option("--interval", "-i", help="时间周期，如1m, 5m, 1h, 1d")],
    output: Annotated[str, typer.Option("--output", "-o", help="输出文件路径")],
    data_source: Annotated[Optional[str], typer.Option("--data-source", "-d", help="数据源(如binance, okx)")] = None,
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    start: Annotated[Optional[str], typer.Option("--start", help="开始时间(格式: YYYYMMDD)")] = None,
    end: Annotated[Optional[str], typer.Option("--end", help="结束时间(格式: YYYYMMDD)")] = None,
):
    """
    导出K线数据到CSV格式文件
    
    示例:
      # 导出BTCUSDT的1小时数据
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc_1h.csv
      
      # 导出指定时间范围的数据
      python data_cli.py export csv -s BTCUSDT -i 1d --start 20240101 --end 20241231 -o btc_2024.csv
    """
    try:
        init_db()
        
        db = SessionLocal()
        try:
            # 选择数据表
            if candle_type.lower() == "spot":
                KlineModel = CryptoSpotKline
            elif candle_type.lower() == "future":
                KlineModel = CryptoFutureKline
            else:
                typer.echo(f"错误: 不支持的蜡烛图类型: {candle_type}", err=True)
                raise typer.Exit(1)
            
            # 构建查询
            query = db.query(KlineModel).filter(
                KlineModel.symbol == symbol.upper(),
                KlineModel.interval == interval
            )
            
            # 筛选数据源
            if data_source:
                query = query.filter(KlineModel.data_source == data_source.lower())
            
            # 筛选时间范围
            if start:
                try:
                    start_ts = int(datetime.strptime(start, "%Y%m%d").timestamp() * 1000)
                    query = query.filter(KlineModel.timestamp >= str(start_ts))
                except ValueError:
                    typer.echo("错误: 开始时间格式不正确，请使用 YYYYMMDD 格式", err=True)
                    raise typer.Exit(1)
            
            if end:
                try:
                    end_ts = int(datetime.strptime(end, "%Y%m%d").timestamp() * 1000)
                    query = query.filter(KlineModel.timestamp <= str(end_ts))
                except ValueError:
                    typer.echo("错误: 结束时间格式不正确，请使用 YYYYMMDD 格式", err=True)
                    raise typer.Exit(1)
            
            # 按时间戳排序
            query = query.order_by(KlineModel.timestamp)
            
            # 执行查询
            records = query.all()
            
            if not records:
                typer.echo(f"未找到符合条件的数据")
                return
            
            # 转换为DataFrame
            data = []
            for record in records:
                data.append({
                    'symbol': record.symbol,
                    'interval': record.interval,
                    'timestamp': record.timestamp,
                    'open': record.open,
                    'high': record.high,
                    'low': record.low,
                    'close': record.close,
                    'volume': record.volume,
                    'data_source': record.data_source,
                })
            
            df = pd.DataFrame(data)
            
            # 保存到CSV
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
            
            typer.echo(f"✓ 成功导出 {len(df)} 条数据到 {output_path}")
            typer.echo(f"  交易对: {symbol}")
            typer.echo(f"  时间周期: {interval}")
            typer.echo(f"  数据源: {data_source or '全部'}")
            if start or end:
                typer.echo(f"  时间范围: {start or '无限制'} ~ {end or '无限制'}")
                
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"导出数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 导入子命令 ==========

@import_app.command("csv")
def import_csv(
    input_file: Annotated[str, typer.Argument(help="CSV文件路径")],
    interval: Annotated[str, typer.Option("--interval", "-i", help="时间周期，如1m, 5m, 1h, 1d")],
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    batch_size: Annotated[int, typer.Option("--batch-size", "-b", help="批量插入大小")] = 500,
    skip_validation: Annotated[bool, typer.Option("--skip-validation", help="跳过数据验证")] = False,
):
    """
    从CSV格式文件导入K线数据到数据库
    
    导入的数据将标记数据源为 "import"
    
    示例:
      # 导入CSV文件
      python data_cli.py import csv data.csv -i 1h
      
      # 导入合约数据
      python data_cli.py import csv data.csv -i 1h --candle-type future
      
      # 使用更大的批次导入
      python data_cli.py import csv data.csv -i 1h --batch-size 1000
    """
    try:
        init_db()
        
        # 检查文件是否存在
        input_path = Path(input_file)
        if not input_path.exists():
            typer.echo(f"错误: 文件不存在: {input_file}", err=True)
            raise typer.Exit(1)
        
        # 读取CSV文件
        try:
            df = pd.read_csv(input_file)
        except Exception as e:
            typer.echo(f"错误: 读取CSV文件失败: {e}", err=True)
            raise typer.Exit(1)
        
        if df.empty:
            typer.echo("错误: CSV文件为空", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"读取到 {len(df)} 行数据")
        
        # 验证必需列
        required_columns = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            typer.echo(f"错误: CSV文件缺少必需列: {', '.join(missing_columns)}", err=True)
            raise typer.Exit(1)
        
        # 数据验证
        if not skip_validation:
            typer.echo("正在验证数据...")
            invalid_rows = []
            for idx, row in df.iterrows():
                # 检查空值
                if pd.isna(row[required_columns]).any():
                    invalid_rows.append(idx)
                    continue
                
                # 检查数值列是否为有效数字
                numeric_columns = ['open', 'high', 'low', 'close', 'volume']
                for col in numeric_columns:
                    try:
                        float(row[col])
                    except (ValueError, TypeError):
                        invalid_rows.append(idx)
                        break
            
            if invalid_rows:
                typer.echo(f"警告: 发现 {len(invalid_rows)} 行无效数据，将跳过这些行")
                df = df.drop(index=invalid_rows).reset_index(drop=True)
        
        if df.empty:
            typer.echo("错误: 没有有效的数据可以导入", err=True)
            raise typer.Exit(1)
        
        # 准备数据
        kline_list = []
        for _, row in df.iterrows():
            # 处理timestamp，确保为整数字符串
            try:
                timestamp = int(float(row['timestamp']))
            except (ValueError, TypeError):
                logger.warning(f"无效的timestamp值: {row['timestamp']}，跳过该行")
                continue
            
            symbol = str(row['symbol']).upper()
            # 使用命令行传入的interval参数，data_source固定为"import"
            interval_value = interval
            data_source_value = "import"
            
            # 生成unique_kline
            unique_kline = f"{symbol}_{interval_value}_{timestamp}"
            
            kline_list.append({
                'symbol': symbol,
                'interval': interval_value,
                'timestamp': str(timestamp),
                'open': str(row['open']),
                'high': str(row['high']),
                'low': str(row['low']),
                'close': str(row['close']),
                'volume': str(row['volume']),
                'unique_kline': unique_kline,
                'data_source': data_source_value,
            })
        
        if not kline_list:
            typer.echo("错误: 没有有效的数据可以导入", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"准备导入 {len(kline_list)} 条数据...")
        
        # 导入数据库
        db = SessionLocal()
        try:
            # 选择数据表
            if candle_type.lower() == "spot":
                KlineModel = CryptoSpotKline
            elif candle_type.lower() == "future":
                KlineModel = CryptoFutureKline
            else:
                typer.echo(f"错误: 不支持的蜡烛图类型: {candle_type}", err=True)
                raise typer.Exit(1)
            
            from collector.db.database import db_type
            
            inserted_count = 0
            updated_count = 0
            
            if db_type == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                
                # 分批处理
                total_records = len(kline_list)
                for i in range(0, total_records, batch_size):
                    batch = kline_list[i:i+batch_size]
                    
                    # 检查已存在的记录
                    existing = db.query(KlineModel.unique_kline).filter(
                        KlineModel.unique_kline.in_([k['unique_kline'] for k in batch])
                    ).all()
                    existing_set = {uk[0] for uk in existing}
                    
                    # 分离新记录和更新记录
                    new_records = [k for k in batch if k['unique_kline'] not in existing_set]
                    update_records = [k for k in batch if k['unique_kline'] in existing_set]
                    
                    # 插入新记录
                    if new_records:
                        stmt = sqlite_insert(KlineModel).values(new_records)
                        db.execute(stmt)
                        inserted_count += len(new_records)
                    
                    # 更新已有记录
                    for record in update_records:
                        db.query(KlineModel).filter(
                            KlineModel.unique_kline == record['unique_kline']
                        ).update({
                            'open': record['open'],
                            'high': record['high'],
                            'low': record['low'],
                            'close': record['close'],
                            'volume': record['volume'],
                            'data_source': record['data_source'],
                            'updated_at': func.now()
                        })
                        updated_count += 1
                    
                    # 每批次提交
                    db.commit()
                    
                    if (i + len(batch)) % 1000 == 0 or (i + len(batch)) >= total_records:
                        typer.echo(f"  已处理 {i + len(batch)}/{total_records} 条记录")
                
            elif db_type == "duckdb":
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                
                # 分批处理
                total_records = len(kline_list)
                for i in range(0, total_records, batch_size):
                    batch = kline_list[i:i+batch_size]
                    
                    stmt = pg_insert(KlineModel).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['unique_kline'],
                        set_={
                            'open': stmt.excluded.open,
                            'high': stmt.excluded.high,
                            'low': stmt.excluded.low,
                            'close': stmt.excluded.close,
                            'volume': stmt.excluded.volume,
                            'data_source': stmt.excluded.data_source,
                            'updated_at': func.now()
                        }
                    )
                    db.execute(stmt)
                    db.commit()
                    
                    inserted_count += len(batch)
                    
                    if (i + len(batch)) % 1000 == 0 or (i + len(batch)) >= total_records:
                        typer.echo(f"  已处理 {i + len(batch)}/{total_records} 条记录")
            else:
                raise ValueError(f"不支持的数据库类型: {db_type}")
            
            typer.echo(f"✓ 导入完成!")
            typer.echo(f"  插入: {inserted_count} 条")
            typer.echo(f"  更新: {updated_count} 条")
            typer.echo(f"  总计: {inserted_count + updated_count} 条")
            
        except Exception as e:
            db.rollback()
            logger.exception(f"导入数据时发生错误: {e}")
            typer.echo(f"错误: 导入失败，已回滚事务: {e}", err=True)
            raise typer.Exit(1)
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"导入数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 主应用 ==========

# 创建主Typer应用
app = typer.Typer(
    name="data-cli",
    help="数据管理命令行工具",
    epilog="""
示例:
  # 下载BTCUSDT的日线数据
  python data_cli.py download -s BTCUSDT -i 1d --start 20240101 --end 20241231

  # 导出数据到CSV
  python data_cli.py export csv -s BTCUSDT -i 1h -o btc_1h.csv

  # 从CSV导入数据
  python data_cli.py import csv data.csv

  # 查看本地数据
  python data_cli.py list-local-data
    """
)

# 添加子命令
app.add_typer(export_app, name="export", help="导出数据到文件")
app.add_typer(import_app, name="import", help="从文件导入数据到数据库")


@app.command()
def download(
    symbols: Annotated[List[str], typer.Option("--symbols", "-s", help="交易对列表，可多次指定")] = None,
    interval: Annotated[List[str], typer.Option("--interval", "-i", help="时间周期列表，可多次指定(如: 1m, 5m, 15m, 30m, 1h, 4h, 1d)")] = None,
    start: Annotated[str, typer.Option("--start", help="开始时间(格式: YYYYMMDD，如20240101)")] = None,
    end: Annotated[str, typer.Option("--end", help="结束时间(格式: YYYYMMDD，如20241231)")] = None,
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
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
        # 转换为系统期望的 YYYY-MM-DD 格式
        start_formatted = start_dt.strftime("%Y-%m-%d")
        end_formatted = end_dt.strftime("%Y-%m-%d")
    except ValueError:
        typer.echo("错误: 时间格式不正确，请使用 YYYYMMDD 格式(如20240101)", err=True)
        raise typer.Exit(1)
    
    # 验证模式
    if mode not in ["inc", "full"]:
        typer.echo("错误: 模式必须是 'inc'(增量) 或 'full'(全量)", err=True)
        raise typer.Exit(1)
    
    try:
        # 初始化数据库
        init_db()
        
        # 获取项目根目录（backend目录的父目录）
        project_root = Path(__file__).parent.parent
        
        # 如果没有指定保存目录，从系统配置读取
        if not save_dir:
            save_dir = SystemConfig.get("data_download_dir")
            if save_dir:
                logger.info(f"从系统配置读取到保存目录: {save_dir}")
            else:
                save_dir = "data/download"
                logger.warning(f"未找到系统配置，使用默认保存目录: {save_dir}")
        
        # 将相对路径转换为绝对路径（基于项目根目录）
        save_dir_path = Path(save_dir)
        if not save_dir_path.is_absolute():
            save_dir_path = project_root / save_dir_path
            save_dir = str(save_dir_path)
            logger.info(f"转换为绝对路径: {save_dir}")
        
        # 创建下载请求 - 使用格式化后的日期
        request = DownloadCryptoRequest(
            symbols=symbols,
            interval=interval,
            start=start_formatted,
            end=end_formatted,
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
        typer.echo(f"  python data_cli.py status -t {task_id}")
        typer.echo(f"\n可使用以下命令查询本地数据:")
        typer.echo(f"  python data_cli.py list-local-data -s {', '.join(symbols)}")
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


@app.command()
def list_local_data(
    symbol: Annotated[Optional[str], typer.Option("--symbol", "-s", help="指定交易对(可选)如BTCUSDT")] = None,
    data_source: Annotated[Optional[str], typer.Option("--data-source", "-d", help="数据源(交易所，如binance, okx)")] = None,
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    limit: Annotated[int, typer.Option("--limit", "-l", help="显示交易对数量限制")] = 50,
    list_sources: Annotated[bool, typer.Option("--list-sources", help="列出所有可用的数据源")] = False,
):
    """
    查看本地K线数据
    显示已下载到本地的K线数据信息，包括交易对、时间范围、时间周期和数据量

    示例:
      # 列出所有可用的数据源
      python data_cli.py list-local-data --list-sources

      # 查看binance的数据
      python data_cli.py list-local-data --data-source binance

      # 查看特定交易对的数据
      python data_cli.py list-local-data -s BTCUSDT
    """
    try:
        init_db()
        
        db = SessionLocal()
        try:
            # 选择数据表
            if candle_type.lower() == "spot":
                KlineModel = CryptoSpotKline
            elif candle_type.lower() == "future":
                KlineModel = CryptoFutureKline
            else:
                typer.echo(f"错误: 不支持的蜡烛图类型: {candle_type}", err=True)
                raise typer.Exit(1)
            
            # 如果需要列出所有数据源
            if list_sources:
                sources = db.query(KlineModel.data_source).distinct().all()
                if not sources:
                    typer.echo(f"未找到任何{candle_type}数据源")
                    return
                
                typer.echo(f"\n{'='*60}")
                typer.echo(f"可用的{candle_type.upper()}数据源")
                typer.echo(f"{'='*60}")
                
                for (source,) in sources:
                    # 统计每个数据源的数据量
                    count = db.query(KlineModel).filter(
                        KlineModel.data_source == source
                    ).count()
                    
                    # 统计每个数据源的交易对数量
                    symbol_count = db.query(KlineModel.symbol).filter(
                        KlineModel.data_source == source
                    ).distinct().count()
                    
                    typer.echo(f"  {source:15} | 数据量: {count:10,} | 交易对: {symbol_count:4}")
                
                typer.echo(f"{'='*60}\n")
                return
            
            # 如果没有指定数据源，查询所有数据源的数据
            if data_source:
                # 构建查询 - 使用data_source字段筛选
                query = db.query(KlineModel.symbol).filter(
                    KlineModel.data_source == data_source.lower()
                ).distinct()
                data_source_filter = data_source.lower()
            else:
                # 查询所有数据源的数据
                query = db.query(KlineModel.symbol).distinct()
                data_source_filter = None
            
            # 如果指定了交易对，只查询该交易对
            if symbol:
                query = query.filter(KlineModel.symbol == symbol.upper())
            
            # 限制数量
            symbols = query.limit(limit).all()
            
            if not symbols:
                if symbol:
                    typer.echo(f"未找到交易对 {symbol} 的本地数据")
                else:
                    typer.echo(f"未找到任何本地{candle_type}数据")
                typer.echo("提示: 请先使用 download 命令下载数据")
                return
            
            symbol_list = [s[0] for s in symbols]
            
            # 显示数据源信息
            if data_source:
                source_info = f"数据源: {data_source.upper()}"
            else:
                source_info = "数据源: 全部"
            
            typer.echo(f"\n{'='*80}")
            typer.echo(f"本地{candle_type.upper()}数据概览 | {source_info}")
            typer.echo(f"{'='*80}\n")
            
            # 统计每个交易对的数据
            for sym in symbol_list:
                typer.echo(f"\n交易对: {sym}")
                typer.echo("-" * 80)
                
                # 获取该交易对的所有数据源
                if data_source_filter:
                    data_sources = [data_source_filter]
                else:
                    sources_query = db.query(KlineModel.data_source).filter(
                        KlineModel.symbol == sym
                    ).distinct().all()
                    data_sources = [s[0] for s in sources_query]
                
                for source in data_sources:
                    # 获取该交易对和数据源的所有时间周期
                    intervals = db.query(KlineModel.interval).filter(
                        KlineModel.symbol == sym,
                        KlineModel.data_source == source
                    ).distinct().all()
                    
                    if intervals:
                        typer.echo(f"  [{source.upper()}]")
                        
                        for (interval,) in intervals:
                            # 查询该交易对、数据源和时间周期的统计信息
                            stats = db.query(
                                func.min(KlineModel.timestamp).label("min_time"),
                                func.max(KlineModel.timestamp).label("max_time"),
                                func.count(KlineModel.id).label("count")
                            ).filter(
                                KlineModel.symbol == sym,
                                KlineModel.interval == interval,
                                KlineModel.data_source == source
                            ).first()
                            
                            if stats and stats.count > 0:
                                # 格式化时间戳
                                min_time = stats.min_time
                                max_time = stats.max_time
                                
                                # 尝试将时间戳转换为可读格式
                                try:
                                    min_dt = datetime.fromtimestamp(int(min_time) / 1000).strftime("%Y-%m-%d %H:%M")
                                    max_dt = datetime.fromtimestamp(int(max_time) / 1000).strftime("%Y-%m-%d %H:%M")
                                    time_range = f"{min_dt} ~ {max_dt}"
                                except:
                                    time_range = f"{min_time} ~ {max_time}"
                                
                                typer.echo(f"    {interval:6} | 数据量: {stats.count:8,} | 时间范围: {time_range}")
            
            typer.echo(f"\n{'='*80}")
            typer.echo(f"总计 {len(symbol_list)} 个交易对")
            typer.echo(f"{'='*80}\n")
                
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"查询本地数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def delete_local_data(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")],
    interval: Annotated[Optional[str], typer.Option("--interval", "-i", help="时间周期(可选，不指定则删除所有周期)")] = None,
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所")] = "binance",
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="确认删除，不提示")] = False,
):
    """
    删除本地K线数据
    
    删除指定交易对的本地K线数据，支持按时间周期筛选
    """
    try:
        init_db()
        
        db = SessionLocal()
        try:
            # 选择数据表
            if candle_type.lower() == "spot":
                KlineModel = CryptoSpotKline
            elif candle_type.lower() == "future":
                KlineModel = CryptoFutureKline
            else:
                typer.echo(f"错误: 不支持的蜡烛图类型: {candle_type}", err=True)
                raise typer.Exit(1)
            
            # 构建查询
            query = db.query(KlineModel).filter(KlineModel.symbol == symbol.upper())
            
            if interval:
                query = query.filter(KlineModel.interval == interval)
            
            # 先统计要删除的数据量
            count = query.count()
            
            if count == 0:
                typer.echo(f"未找到要删除的数据")
                return
            
            # 确认删除
            if not yes:
                if interval:
                    confirm = typer.confirm(f"确定要删除 {symbol} {interval} 的 {count} 条数据吗？")
                else:
                    confirm = typer.confirm(f"确定要删除 {symbol} 的所有时间周期的 {count} 条数据吗？")
                
                if not confirm:
                    typer.echo("已取消删除")
                    return
            
            # 执行删除
            query.delete(synchronize_session=False)
            db.commit()
            
            typer.echo(f"✓ 成功删除 {count} 条数据")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"删除本地数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
