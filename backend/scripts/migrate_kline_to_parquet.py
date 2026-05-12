#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库K线数据迁移脚本

将SQLite数据库中的K线数据导出为Parquet文件格式。
支持dry-run模式（仅显示统计）和批量处理。

使用示例:
    # 显示统计信息
    python scripts/migrate_kline_to_parquet.py --dry-run
    
    # 执行迁移
    python scripts/migrate_kline_to_parquet.py --batch-size 10000
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import typer
from typer import Option, echo, secho
from utils.logger import get_logger, LogType
from utils.kline_file_manager import KlineFileManager

logger = get_logger(__name__, LogType.APPLICATION)

app = typer.Typer(
    name="migrate-kline-to-parquet",
    help="将数据库中的K线数据迁移到Parquet文件系统",
    no_args_is_help=True,
)


def show_database_stats(db_url: str):
    """显示数据库中K线数据的统计信息"""
    from sqlalchemy import create_engine, text
    
    engine = create_engine(db_url)
    
    secho("\n" + "=" * 60, bold=True, fg=typer.colors.CYAN)
    secho("📊 数据库K线数据统计", bold=True, fg=typer.colors.WHITE)
    secho("=" * 60, bold=True, fg=typer.colors.CYAN)
    
    tables = [
        ('crypto_spot_klines', '现货'),
        ('crypto_future_klines', '合约'),
    ]
    
    total_records = 0
    
    with engine.connect() as conn:
        for table_name, description in tables:
            try:
                count_query = text(f"SELECT COUNT(*) FROM {table_name}")
                result = conn.execute(count_query)
                count = result.scalar()
                
                if count > 0:
                    total_records += count
                    
                    # 获取时间范围
                    range_query = text(f"""
                        SELECT 
                            MIN(timestamp) as min_ts,
                            MAX(timestamp) as max_ts
                        FROM {table_name}
                    """)
                    range_result = conn.execute(range_query).fetchone()
                    min_ts = range_result[0]
                    max_ts = range_result[1]
                    
                    # 获取品种数量
                    symbol_query = text(f"SELECT COUNT(DISTINCT symbol) FROM {table_name}")
                    symbol_count = conn.execute(symbol_query).scalar()
                    
                    echo(f"\n  📁 {description}表: {table_name}", fg=typer.colors.YELLOW)
                    echo(f"     记录数: {count:,}", fg=typer.colors.GREEN)
                    echo(f"     品种数: {symbol_count:,}", fg=typer.colors.BLUE)
                    if min_ts and max_ts:
                        echo(f"     时间范围: {min_ts} ~ {max_ts}", fg=typer.colors.MAGENTA)
                else:
                    echo(f"\n  📁 {description}表: {table_name} (空)", fg=typer.colors.GRAY)
                    
            except Exception as e:
                echo(f"\n  ❌ 查询 {table_name} 失败: {e}", fg=typer.colors.RED)
    
    secho("\n" + "-" * 60, fg=typer.colors.CYAN)
    secho(f"📈 总计记录数: {total_records:,}", bold=True, fg=typer.colors.WHITE if total_records > 0 else typer.colors.RED)


def migrate_from_database(
    db_url: str,
    batch_size: int,
    dry_run: bool = False
):
    """
    从数据库迁移K线数据到Parquet文件
    
    Args:
        db_url: 数据库连接URL
        batch_size: 每批处理的记录数
        dry_run: 是否只显示统计信息
    """
    from sqlalchemy import create_engine, text
    
    engine = create_engine(db_url)
    manager = KlineFileManager()
    
    tables_to_migrate = [
        ('crypto_spot_klines', 'spot'),
        ('crypto_future_klines', 'future'),
    ]
    
    total_migrated = 0
    start_time = datetime.now()
    
    for table_name, market_type in tables_to_migrate:
        secho(f"\n{'='*60}", bold=True, fg=typer.colors.CYAN)
        secho(f"🚀 开始迁移表: {table_name} → {market_type}", bold=True)
        secho(f"{'='*60}", bold=True, fg=typer.colors.CYAN)
        
        try:
            with engine.connect() as conn:
                # 检查表是否存在
                check_query = text(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                )
                exists = conn.execute(check_query).fetchone()
                
                if not exists:
                    secho(f"\n  ⚠️  表 {table_name} 不存在，跳过", fg=typer.colors.YELLOW)
                    continue
                
                # 获取总记录数
                count_query = text(f"SELECT COUNT(*) FROM {table_name}")
                total_rows = conn.execute(count_query).scalar()
                
                if total_rows == 0:
                    secho(f"\n  ⚠️  表 {table_name} 为空，跳过", fg=typer.colors.YELLOW)
                    continue
                
                secho(f"\n  📊 总记录数: {total_rows:,}", fg=typer.colors.GREEN)
                
                if dry_run:
                    secho(f"\n  🔍 [DRY-RUN] 仅显示统计，不实际迁移", fg=typer.colors.YELLOW)
                    continue
                
                # 分批读取并保存
                offset = 0
                batch_num = 0
                errors = 0
                
                while offset < total_rows:
                    query = text(f"""
                        SELECT symbol, interval, timestamp, open, high, low, close, volume 
                        FROM {table_name}
                        ORDER BY timestamp
                        LIMIT :limit OFFSET :offset
                    """)
                    
                    df = pd.read_sql_query(
                        query,
                        conn,
                        params={'limit': batch_size, 'offset': offset}
                    )
                    
                    if df.empty:
                        break
                    
                    # 数据类型转换
                    try:
                        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                        
                        # 清理无效数据
                        df = df.dropna(subset=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        
                        # 转换为毫秒时间戳（如果存储的是微秒）
                        if df['timestamp'].max() > 1e15:  # 大于微秒阈值
                            df['timestamp'] = (df['timestamp'] / 1000).astype('int64')
                        
                        # 数值列转换
                        for col in ['open', 'high', 'low', 'close', 'volume']:
                            df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        df = df.dropna()
                        
                        if not df.empty:
                            # 按品种和周期分组保存
                            for (symbol, interval), group in df.groupby(['symbol', 'interval']):
                                saved = manager.save_klines(
                                    df=group,
                                    symbol=symbol,
                                    interval=interval,
                                    market_type=market_type
                                )
                                
                                if saved:
                                    if batch_num % 10 == 0 or len(group) > 1000:
                                        echo(
                                            f"  ✅ 批次{batch_num}: {symbol} {interval} "
                                            f"- {len(group):,} 条",
                                            fg=typer.colors.GREEN
                                        )
                    except Exception as e:
                        errors += 1
                        logger.error(f"批次{batch_num}处理失败: {e}")
                        if errors <= 3:
                            logger.exception(e)
                    
                    offset += batch_size
                    batch_num += 1
                    total_migrated += len(df)
                    
                    # 进度显示
                    progress = min(offset / total_rows * 100, 100)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    
                    if batch_num % 20 == 0 or offset >= total_rows:
                        echo(
                            f"\n  📈 进度: {progress:.1f}% "
                            f"({offset:,}/{total_rows:,}) | "
                            f"耗时: {elapsed:.1f}s | "
                            f"错误: {errors}",
                            fg=typer.colors.CYAN
                        )
                
                # 迁移完成统计
                elapsed = (datetime.now() - start_time).total_seconds()
                speed = total_migrated / elapsed if elapsed > 0 else 0
                
                secho(f"\n{'─'*60}", fg=typer.colors.CYAN)
                secho(f"✅ 表 {table_name} 迁移完成!", bold=True, fg=typer.colors.GREEN)
                secho(f"   成功: {total_migrated:,} 条", fg=typer.colors.GREEN)
                secho(f"   错误: {errors} 次", fg=typer.colors.RED if errors > 0 else typer.colors.GREEN)
                secho(f"   耗时: {elapsed:.2f}s", fg=typer.colors.BLUE)
                secho(f"   速度: {speed:,.0f} 条/秒", fg=typer.colors.MAGENTA)
                
        except Exception as e:
            secho(f"\n❌ 表 {table_name} 迁移失败: {e}", fg=typer.colors.RED)
            logger.error(f"迁移失败: {e}")
            logger.exception(e)
            continue
    
    # 最终统计
    if not dry_run and total_migrated > 0:
        secho(f"\n{'='*60}", bold=True, fg=typer.colors.WHITE)
        secho("🎉 迁移完成！", bold=True, fg=typer.colors.GREEN)
        secho(f"{'='*60}", bold=True, fg=typer.colors.WHITE)
        
        stats = manager.get_storage_stats()
        
        secho(f"\n📦 Parquet文件存储统计:", bold=True, fg=typer.colors.YELLOW)
        secho(f"   基础目录: {stats['base_dir']}", fg=typer.colors.BLUE)
        secho(f"   总文件数: {stats['total_files']:,}", fg=typer.colors.GREEN)
        secho(f"   总大小: {stats['total_size_mb']} MB", fg=typer.colors.MAGENTA)
        
        secho(f"\n🎯 可用品种:", bold=True, fg=typer.colors.YELLOW)
        for symbol in list(stats['symbols'].keys())[:10]:
            info = stats['symbols'][symbol]
            secho(f"   • {symbol}: {info['total_files']} 文件, {info['total_size_mb']:.2f} MB")
        
        if len(stats['symbols']) > 10:
            secho(f"   ... 还有 {len(stats['symbols']) - 10} 个品种", fg=typer.colors.GRAY)


@app.command()
def main(
    db_url: str = Option("sqlite:///./quantcell.db", "--db-url", help="数据库连接URL"),
    batch_size: int = Option(10000, "--batch-size", "-b", help="每批处理记录数"),
    dry_run: bool = Option(False, "--dry-run", "-n", help="只显示统计信息，不实际迁移"),
):
    """
    迁移K线数据从数据库到Parquet文件
    """
    if dry_run:
        show_database_stats(db_url)
        secho("\n💡 提示: 移除 --dry-run 参数以执行实际迁移", fg=typer.colors.YELLOW)
        return
    
    secho("\n🚀 开始K线数据迁移...", bold=True, fg=typer.colors.GREEN)
    migrate_from_database(db_url, batch_size, dry_run=False)
    secho("\n✨ 完成！请验证Parquet文件是否正确生成。", bold=True, fg=typer.colors.GREEN)


if __name__ == '__main__':
    app()
