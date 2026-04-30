#!/usr/bin/env python3
"""
数据管理命令行工具
支持K线数据下载、任务管理和本地数据查询
支持数据导出到 CSV 和 Parquet 格式（Parquet 提供更高的压缩率和查询性能）
"""

import sys
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import time

# 添加后端目录到路径（必须在导入项目模块之前）
backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import typer
from typing_extensions import Annotated
from utils.logger import get_logger, LogType
from utils.timestamp_utils import (
    to_nanoseconds, normalize_to_nanoseconds, format_nanoseconds,
    nanoseconds_to_milliseconds, detect_precision, datetime_to_nanoseconds,
    from_nanoseconds
)
from utils.parquet_utils import save_to_parquet, get_parquet_info, load_from_parquet

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from sqlalchemy import func
import pandas as pd

# 尝试导入 dateutil，如果不存在则使用 timedelta 替代
try:
    from dateutil.relativedelta import relativedelta
    HAS_RELATIVEDELTA = True
except ImportError:
    HAS_RELATIVEDELTA = False
    logger.warning("python-dateutil 未安装，使用 timedelta 替代月份计算")

# 导入项目内部模块
try:
    from collector.scripts.get_data import GetData
    from collector.services.data_service import DataService
    from collector.schemas.data import DownloadCryptoRequest
    from collector.utils.task_manager import task_manager
    from collector.db.database import init_database_config, SessionLocal
    from collector.db.models import CryptoSpotKline, CryptoFutureKline, CryptoSymbol
    from settings.models import SystemConfigBusiness as SystemConfig
    # 可选导入回测CLI核心模块（用于 list_symbols 等功能）
    try:
        from backtest.cli_core import get_symbols_from_data_pool
        _cli_core_available = True
    except ImportError:
        get_symbols_from_data_pool = None
        _cli_core_available = False
        logger.warning("backtest.cli_core 模块不可用，部分功能可能受限")
except ImportError as e:
    logger.error(f"导入模块失败: {e}")
    logger.error(f"当前 sys.path: {sys.path}")
    logger.error(f"backend_path: {backend_path}")
    logger.error("请确保在正确的目录下运行此脚本")
    import traceback
    traceback.print_exc()
    sys.exit(1)


# 创建导入导出子命令
export_app = typer.Typer(help="导出数据到文件（支持 CSV 和 Parquet 格式，Parquet 提供更高压缩率和性能）")
import_app = typer.Typer(help="从文件导入数据到数据库")


def init_db():
    """初始化数据库连接"""
    try:
        init_database_config()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise


def _get_all_available_symbols() -> List[str]:
    """
    获取所有可用货币对

    从数据库中查询所有已注册的货币对符号

    Returns:
        List[str]: 货币对列表
    """
    try:
        db = SessionLocal()
        # 从 CryptoSymbol 表中获取所有符号
        symbols = db.query(CryptoSymbol.symbol).distinct().all()
        symbol_list = [s[0] for s in symbols if s[0]]
        logger.debug(f"从数据库获取到 {len(symbol_list)} 个货币对")
        return symbol_list
    except Exception as e:
        logger.error(f"获取货币对列表失败: {e}")
        return []
    finally:
        db.close()


def _get_default_date_range(end_date: Optional[datetime] = None) -> tuple[str, str]:
    """
    获取默认日期范围

    当用户未指定时间范围时，提供默认的开始和结束时间：
    - 结束时间：如果未指定，使用当前时间
    - 开始时间：结束时间往前推1个月

    Args:
        end_date: 指定的结束日期，如果为None则使用当前时间

    Returns:
        tuple: (start_date_str, end_date_str) 格式为 YYYYMMDD
    """
    # 确定结束时间
    if end_date is None:
        end_date = datetime.now()

    # 计算开始时间（1个月前）
    if HAS_RELATIVEDELTA:
        start_date = end_date - relativedelta(months=1)
    else:
        # 使用 timedelta 近似计算（30天）
        start_date = end_date - timedelta(days=30)

    # 格式化为 YYYYMMDD
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    logger.debug(f"默认日期范围: {start_str} 至 {end_str}")
    return start_str, end_str


def _query_kline_data_from_db(
    symbol: str,
    interval: str,
    candle_type: str = "spot",
    data_source: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
    columns: Optional[List[str]] = None,
    sort_desc: bool = False,
) -> pd.DataFrame:
    """
    从数据库查询 K线 数据（共享查询逻辑，供 CSV 和 Parquet 导出使用）

    Args:
        symbol: 交易对符号
        interval: 时间周期
        candle_type: 蜡烛图类型 (spot/future)
        data_source: 数据源过滤
        start: 开始时间 (YYYYMMDD)
        end: 结束时间 (YYYYMMDD)
        limit: 记录数限制
        columns: 指定返回的列（逗号分隔的字符串）
        sort_desc: 是否倒序排列

    Returns:
        pd.DataFrame: 查询结果

    Raises:
        ValueError: 参数无效时抛出
        Exception: 数据库查询失败时抛出
    """
    db = SessionLocal()
    try:
        # 选择数据表
        if candle_type.lower() == "spot":
            KlineModel = CryptoSpotKline
        elif candle_type.lower() in ["future", "futures"]:
            KlineModel = CryptoFutureKline
        else:
            raise ValueError(f"不支持的蜡烛图类型: {candle_type}")

        # 构建查询
        query = db.query(KlineModel).filter(
            KlineModel.symbol == symbol.upper(),
            KlineModel.interval == interval
        )

        # 筛选数据源
        if data_source:
            query = query.filter(KlineModel.data_source == data_source.lower())

        # 筛选时间范围 (统一使用纳秒级时间戳)
        if start:
            try:
                # 转换为纳秒级时间戳
                start_dt = datetime.strptime(start, "%Y%m%d")
                start_ts_ns = datetime_to_nanoseconds(start_dt)
                query = query.filter(KlineModel.timestamp >= str(start_ts_ns))
            except ValueError:
                raise ValueError(f"开始时间格式不正确: {start}，请使用 YYYYMMDD 格式")

        if end:
            try:
                # 转换为纳秒级时间戳，并设置为当天23:59:59
                end_dt = datetime.strptime(end, "%Y%m%d").replace(hour=23, minute=59, second=59)
                end_ts_ns = datetime_to_nanoseconds(end_dt)
                query = query.filter(KlineModel.timestamp <= str(end_ts_ns))
            except ValueError:
                raise ValueError(f"结束时间格式不正确: {end}，请使用 YYYYMMDD 格式")

        # 按时间戳排序
        if sort_desc:
            query = query.order_by(KlineModel.timestamp.desc())
        else:
            query = query.order_by(KlineModel.timestamp)

        # 限制记录数量
        if limit and limit > 0:
            query = query.limit(limit)

        # 执行查询
        records = query.all()

        if not records:
            return pd.DataFrame()

        # 定义所有可用列
        all_columns = {
            'symbol': lambda r: r.symbol,
            'interval': lambda r: r.interval,
            'timestamp': lambda r: r.timestamp,
            'open': lambda r: r.open,
            'high': lambda r: r.high,
            'low': lambda r: r.low,
            'close': lambda r: r.close,
            'volume': lambda r: r.volume,
            'data_source': lambda r: r.data_source,
        }

        # 解析用户指定的列
        if columns:
            selected_columns = [col.strip() for col in columns]
            # 验证列名
            invalid_cols = [col for col in selected_columns if col not in all_columns]
            if invalid_cols:
                raise ValueError(f"无效的列名: {', '.join(invalid_cols)}\n可用列: {', '.join(all_columns.keys())}")
        else:
            selected_columns = list(all_columns.keys())

        # 转换为DataFrame
        data = []
        for record in records:
            row = {}
            for col in selected_columns:
                value = all_columns[col](record)
                row[col] = value
            data.append(row)

        df = pd.DataFrame(data)
        return df

    finally:
        db.close()


def _validate_parquet_export(
    output_path: Path,
    original_df: pd.DataFrame,
    verbose: bool = False
) -> bool:
    """
    验证导出的 Parquet 文件完整性

    检查项：
    1. 文件是否存在且大小 > 0
    2. 能否成功读取
    3. 行数是否一致
    4. 列名是否一致
    5. 数据类型检查

    Args:
        output_path: 导出的文件路径
        original_df: 原始 DataFrame（用于对比）
        verbose: 是否显示详细信息

    Returns:
        bool: 验证是否通过
    """
    validation_passed = True

    # 检查 1: 文件存在性
    if not output_path.exists():
        typer.echo(f"❌ 验证失败: 文件不存在 - {output_path}", err=True)
        return False

    # 检查 2: 文件大小非零
    file_size = output_path.stat().st_size
    if file_size == 0:
        typer.echo(f"❌ 验证失败: 文件大小为零 - {output_path}", err=True)
        return False

    if verbose:
        typer.echo(f"✓ 文件存在且大小正常: {file_size:,} bytes")

    # 检查 3: 可读性检查
    try:
        loaded_df = load_from_parquet(output_path)
        if loaded_df.empty and not original_df.empty:
            typer.echo("❌ 验证失败: 无法读取文件内容或文件为空", err=True)
            return False

        if verbose:
            typer.echo(f"✓ 文件可成功读取")
    except Exception as e:
        typer.echo(f"❌ 验证失败: 读取文件时出错 - {e}", err=True)
        return False

    # 检查 4: 行数一致性
    if len(loaded_df) != len(original_df):
        typer.echo(f"❌ 验证失败: 行数不一致 - 原始 {len(original_df)} 行, 导出 {len(loaded_df)} 行", err=True)
        validation_passed = False
    elif verbose:
        typer.echo(f"✓ 行数一致: {len(loaded_df):,} 行")

    # 检查 5: 列名一致性
    original_cols = set(original_df.columns)
    loaded_cols = set(loaded_df.columns)
    if original_cols != loaded_cols:
        missing = original_cols - loaded_cols
        extra = loaded_cols - original_cols
        typer.echo(f"❌ 验证失败: 列名不一致", err=True)
        if missing:
            typer.echo(f"   缺少列: {', '.join(missing)}", err=True)
        if extra:
            typer.echo(f"   多余列: {', '.join(extra)}", err=True)
        validation_passed = False
    elif verbose:
        typer.echo(f"✓ 列名一致: {', '.join(sorted(loaded_cols))}")

    # 检查 6: 数据类型检查（抽样）
    if validation_passed and not loaded_df.empty:
        type_checks_passed = True

        # 检查 timestamp 是否为整数类型
        if 'timestamp' in loaded_df.columns:
            if not pd.api.types.is_integer_dtype(loaded_df['timestamp']):
                if verbose:
                    typer.echo(f"⚠️ timestamp 类型: {loaded_df['timestamp'].dtype} (建议使用整数类型)")
            elif verbose:
                typer.echo(f"✓ timestamp 类型正确: {loaded_df['timestamp'].dtype}")

        # 检查数值列
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in loaded_df.columns:
                if not pd.api.types.is_numeric_dtype(loaded_df[col]):
                    typer.echo(f"⚠️ {col} 类型: {loaded_df[col].dtype} (建议使用数值类型)")
                    type_checks_passed = False
                elif verbose:
                    typer.echo(f"✓ {col} 类型正确: {loaded_df[col].dtype}")

        if not type_checks_passed:
            validation_passed = False

    return validation_passed


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
    limit: Annotated[Optional[int], typer.Option("--limit", "-l", help="限制导出记录数量")] = None,
    delimiter: Annotated[str, typer.Option("--delimiter", help="CSV分隔符")] = ",",
    no_header: Annotated[bool, typer.Option("--no-header", help="不包含CSV表头")] = False,
    compress: Annotated[bool, typer.Option("--compress", "-z", help="使用gzip压缩输出文件(.csv.gz)")] = False,
    format_timestamp: Annotated[bool, typer.Option("--format-timestamp", "-t", help="将时间戳格式化为可读日期")] = False,
    columns: Annotated[Optional[str], typer.Option("--columns", "-c", help="指定导出的列(逗号分隔，如:timestamp,open,high,low,close,volume)")] = None,
    sort_desc: Annotated[bool, typer.Option("--sort-desc", help="按时间倒序排列")] = False,
    ts_precision: Annotated[str, typer.Option("--ts-precision", help="时间戳精度统一(s:秒, ms:毫秒, us:微秒, ns:纳秒, auto:自动)")] = "auto",
):
    """
    导出K线数据到CSV格式文件

    示例:
      # 导出BTCUSDT的1小时数据
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc_1h.csv

      # 导出指定时间范围的数据
      python data_cli.py export csv -s BTCUSDT -i 1d --start 20240101 --end 20241231 -o btc_2024.csv

      # 导出前1000条记录，并格式化时间戳
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv -l 1000 -t

      # 导出并压缩
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv.gz -z

      # 只导出指定列
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv -c timestamp,open,high,low,close

      # 使用分号分隔符
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv --delimiter ";"

      # 统一时间戳精度为纳秒(默认)
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv --ts-precision ns

      # 统一时间戳精度为微秒
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv --ts-precision us

      # 统一时间戳精度为毫秒
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv --ts-precision ms

      # 统一时间戳精度为秒
      python data_cli.py export csv -s BTCUSDT -i 1h -o btc.csv --ts-precision s
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
            
            # 筛选时间范围 (统一使用纳秒级时间戳)
            if start:
                try:
                    # 转换为纳秒级时间戳
                    start_dt = datetime.strptime(start, "%Y%m%d")
                    start_ts_ns = datetime_to_nanoseconds(start_dt)
                    query = query.filter(KlineModel.timestamp >= str(start_ts_ns))
                except ValueError:
                    typer.echo("错误: 开始时间格式不正确，请使用 YYYYMMDD 格式", err=True)
                    raise typer.Exit(1)

            if end:
                try:
                    # 转换为纳秒级时间戳，并设置为当天23:59:59
                    end_dt = datetime.strptime(end, "%Y%m%d").replace(hour=23, minute=59, second=59)
                    end_ts_ns = datetime_to_nanoseconds(end_dt)
                    query = query.filter(KlineModel.timestamp <= str(end_ts_ns))
                except ValueError:
                    typer.echo("错误: 结束时间格式不正确，请使用 YYYYMMDD 格式", err=True)
                    raise typer.Exit(1)
            
            # 按时间戳排序
            if sort_desc:
                query = query.order_by(KlineModel.timestamp.desc())
            else:
                query = query.order_by(KlineModel.timestamp)

            # 限制记录数量
            if limit and limit > 0:
                query = query.limit(limit)

            # 执行查询
            records = query.all()

            if not records:
                typer.echo(f"未找到符合条件的数据")
                return

            # 定义所有可用列
            all_columns = {
                'symbol': lambda r: r.symbol,
                'interval': lambda r: r.interval,
                'timestamp': lambda r: r.timestamp,
                'open': lambda r: r.open,
                'high': lambda r: r.high,
                'low': lambda r: r.low,
                'close': lambda r: r.close,
                'volume': lambda r: r.volume,
                'data_source': lambda r: r.data_source,
            }

            # 解析用户指定的列
            if columns:
                selected_columns = [col.strip() for col in columns.split(',')]
                # 验证列名
                invalid_cols = [col for col in selected_columns if col not in all_columns]
                if invalid_cols:
                    typer.echo(f"错误: 无效的列名: {', '.join(invalid_cols)}", err=True)
                    typer.echo(f"可用列: {', '.join(all_columns.keys())}", err=True)
                    raise typer.Exit(1)
            else:
                selected_columns = list(all_columns.keys())

            # 时间戳格式化函数（用于可读日期格式）
            def format_ts_readable(ts_str):
                """将纳秒级时间戳格式化为可读日期"""
                try:
                    return format_nanoseconds(ts_str, "%Y-%m-%d %H:%M:%S")
                except:
                    return ts_str

            # 验证时间戳精度参数
            valid_precisions = ['s', 'ms', 'us', 'ns', 'auto']
            if ts_precision not in valid_precisions:
                typer.echo(f"错误: 无效的时间戳精度: {ts_precision}", err=True)
                typer.echo(f"可用选项: {', '.join(valid_precisions)} (s:秒, ms:毫秒, us:微秒, ns:纳秒, auto:自动)", err=True)
                raise typer.Exit(1)

            # 转换为DataFrame
            data = []
            for record in records:
                row = {}
                for col in selected_columns:
                    value = all_columns[col](record)
                    # 处理时间戳字段
                    if col == 'timestamp':
                        if format_timestamp:
                            # 格式化为可读日期
                            value = format_ts_readable(value)
                        elif ts_precision != 'auto':
                            # 统一时间戳精度 (数据库中已是纳秒，按用户指定精度输出)
                            from typing import cast
                            from utils.timestamp_utils import Precision
                            precision = cast(Precision, ts_precision)
                            value = from_nanoseconds(value, precision)
                    row[col] = value
                data.append(row)

            df = pd.DataFrame(data)

            # 保存到CSV
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 构建to_csv参数
            csv_kwargs = {
                'index': False,
                'header': not no_header,
                'sep': delimiter,
            }

            if compress or str(output).endswith('.gz'):
                # 确保文件名以.csv.gz结尾
                if not str(output).endswith('.csv.gz'):
                    output_path = output_path.with_suffix('.csv.gz')
                csv_kwargs['compression'] = 'gzip'

            df.to_csv(output_path, **csv_kwargs)

            # 计算文件大小
            file_size = output_path.stat().st_size
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.2f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.2f} KB"
            else:
                size_str = f"{file_size} B"

            typer.echo(f"✓ 成功导出 {len(df)} 条数据到 {output_path}")
            typer.echo(f"  文件大小: {size_str}")
            typer.echo(f"  交易对: {symbol}")
            typer.echo(f"  时间周期: {interval}")
            typer.echo(f"  数据源: {data_source or '全部'}")
            if start or end:
                typer.echo(f"  时间范围: {start or '无限制'} ~ {end or '无限制'}")
            if limit:
                typer.echo(f"  限制数量: {limit}")
            if columns:
                typer.echo(f"  导出列: {columns}")
            if format_timestamp:
                typer.echo(f"  时间戳格式: 已格式化")
            elif ts_precision != 'auto':
                precision_names = {'s': '秒', 'ms': '毫秒', 'us': '微秒'}
                typer.echo(f"  时间戳精度: {precision_names.get(ts_precision, ts_precision)}")
            if compress:
                typer.echo(f"  压缩: 已启用")
                
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"导出数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@export_app.command("parquet")
def export_parquet(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对，如BTCUSDT")],
    interval: Annotated[str, typer.Option("--interval", "-i", help="时间周期，如1m, 5m, 1h, 1d")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出文件路径(.parquet)，默认保存到 backend/data/{table_name}/ 目录下")] = None,
    data_source: Annotated[Optional[str], typer.Option("--data-source", "-d", help="数据源(如binance, okx)")] = None,
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    start: Annotated[Optional[str], typer.Option("--start", help="开始时间(格式: YYYYMMDD)")] = None,
    end: Annotated[Optional[str], typer.Option("--end", help="结束时间(格式: YYYYMMDD)")] = None,
    limit: Annotated[Optional[int], typer.Option("--limit", "-l", help="限制导出记录数量")] = None,
    columns: Annotated[Optional[str], typer.Option("--columns", "-c", help="指定导出的列(逗号分隔，如:timestamp,open,high,low,close,volume)")] = None,
    sort_desc: Annotated[bool, typer.Option("--sort-desc", help="按时间倒序排列")] = False,
    compression: Annotated[str, typer.Option("--compression", help="压缩算法(snappy/gzip/zstd)，默认snappy")] = "snappy",
    ts_precision: Annotated[str, typer.Option("--ts-precision", help="时间戳精度统一(s:秒, ms:毫秒, us:微秒, ns:纳秒, auto:自动)")] = "auto",
    format_timestamp: Annotated[bool, typer.Option("--format-timestamp", "-t", help="将时间戳格式化为可读日期")] = False,
    validate: Annotated[bool, typer.Option("--validate", help="导出后验证文件完整性")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="显示详细日志")] = False,
):
    """
    导出K线数据到Parquet格式文件

    Parquet 格式相比 CSV 具有：
    - 更高的压缩率（通常 70-90% 空间节省）
    - 更快的查询速度（特别是列式读取）
    - 类型安全（保持原始数据类型，数值不转为字符串）

    默认保存路径: backend/data/{table_name}/{symbol}_{interval}.parquet
      - 现货数据: backend/data/crypto_spot_klines/BTCUSDT_1h.parquet
      - 合约数据: backend/data/crypto_future_klines/BTCUSDT_1h.parquet

    示例:
      # 基本用法 - 导出BTCUSDT的1小时数据（使用默认路径）
      python data_cli.py export parquet -s BTCUSDT -i 1h

      # 指定输出路径
      python data_cli.py export parquet -s BTCUSDT -i 1h -o /tmp/btc.parquet

      # 指定时间范围的数据
      python data_cli.py export parquet -s BTCUSDT -i 1d --start 20240101 --end 20241231

      # 使用 gzip 压缩以获得更高压缩率
      python data_cli.py export parquet -s BTCUSDT -i 1h --compression gzip

      # 只导出价格列（利用列式存储优势，减少文件大小）
      python data_cli.py export parquet -s BTCUSDT -i 1h -c timestamp,open,high,low,close

      # 导出前1000条记录，并格式化时间戳为可读日期
      python data_cli.py export parquet -s BTCUSDT -i 1h -l 1000 -t

      # 导出并验证文件完整性
      python data_cli.py export parquet -s BTCUSDT -i 1h --validate --verbose

      # 使用 zstd 压缩算法（最佳压缩率，适合归档）
      python data_cli.py export parquet -s BTCUSDT -i 1m --start 20240101 --end 20240131 --compression zstd

      # 导出合约数据（默认保存到 crypto_future_klines/ 目录）
      python data_cli.py export parquet -s BTCUSDT -i 1h --candle-type future

      # 统一时间戳精度为毫秒
      python data_cli.py export parquet -s BTCUSDT -i 1h --ts-precision ms

    性能对比 (Parquet vs CSV):
      ┌─────────────────┬──────────┬───────────┬──────────────┐
      │ 指标            │ CSV      │ Parquet   │ 提升         │
      ├─────────────────┼──────────┼───────────┼──────────────┤
      │ 存储空间        │ 100%     │ 10-30%    │ 70-90% 节省  │
      │ 全量加载速度    │ 基准     │ 3-5x 更快 │ 显著提升     │
      │ 单列查询速度    │ 基准     │ 10-25x更快│ 极大提升     │
      │ 类型安全        │ ❌       │ ✅         │ 避免类型错误  │
      │ 压缩支持        │ gzip     │ 多种算法  │ 灵活选择     │
      └─────────────────┴──────────┴───────────┴──────────────┘
    """
    try:
        if verbose:
            logger.remove()
            logger.add(sys.stderr, level="DEBUG")

        # 初始化数据库
        init_db()

        # 生成输出路径（如果未指定）
        if output:
            output_path = Path(output)
        else:
            # 根据表名确定子目录
            if candle_type.lower() in ["future", "futures"]:
                table_name = "crypto_future_klines"
            else:
                table_name = "crypto_spot_klines"

            # 默认保存到 backend/data/{table_name}/ 目录下
            data_dir = backend_path / "data" / table_name
            output_path = data_dir / f"{symbol.upper()}_{interval}.parquet"

            if verbose:
                typer.echo(f"使用默认输出路径: {output_path}")

        # 验证压缩算法参数
        valid_compressions = ['snappy', 'gzip', 'zstd']
        if compression not in valid_compressions:
            typer.echo(f"错误: 不支持的压缩算法: {compression}", err=True)
            typer.echo(f"可用选项: {', '.join(valid_compressions)}", err=True)
            typer.echo("推荐: snappy(平衡速度与压缩率), gzip(高压缩率), zstd(最佳压缩率)", err=True)
            raise typer.Exit(1)

        # 验证时间戳精度参数
        valid_precisions = ['s', 'ms', 'us', 'ns', 'auto']
        if ts_precision not in valid_precisions:
            typer.echo(f"错误: 无效的时间戳精度: {ts_precision}", err=True)
            typer.echo(f"可用选项: {', '.join(valid_precisions)} (s:秒, ms:毫秒, us:微秒, ns:纳秒, auto:自动)", err=True)
            raise typer.Exit(1)

        # 调用共享查询函数获取数据
        try:
            df = _query_kline_data_from_db(
                symbol=symbol,
                interval=interval,
                candle_type=candle_type,
                data_source=data_source,
                start=start,
                end=end,
                limit=limit,
                columns=columns.split(',') if columns else None,
                sort_desc=sort_desc
            )
        except ValueError as e:
            typer.echo(f"错误: {e}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            logger.exception(f"查询数据时发生错误: {e}")
            typer.echo(f"错误: 数据库查询失败 - {e}", err=True)
            raise typer.Exit(1)

        # 检查数据是否为空
        if df.empty:
            typer.echo(f"⚠️ 未找到符合条件的数据")
            typer.echo("提示: 请检查筛选条件或尝试扩大时间范围", err=False)
            return

        # 处理时间戳字段
        if 'timestamp' in df.columns and not format_timestamp:
            if ts_precision != 'auto':
                try:
                    from typing import cast
                    from utils.timestamp_utils import Precision
                    precision = cast(Precision, ts_precision)
                    df['timestamp'] = df['timestamp'].apply(lambda x: from_nanoseconds(x, precision))
                    if verbose:
                        typer.echo(f"已统一时间戳精度为: {ts_precision}")
                except Exception as e:
                    logger.warning(f"时间戳精度转换失败，保持原值: {e}")

        elif 'timestamp' in df.columns and format_timestamp:
            def format_ts_readable(ts_str):
                try:
                    return format_nanoseconds(ts_str, "%Y-%m-%d %H:%M:%S")
                except:
                    return ts_str

            df['timestamp'] = df['timestamp'].apply(format_ts_readable)
            if verbose:
                typer.echo("已将时间戳格式化为可读日期")

        # 确保输出目录存在
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            typer.echo(f"❌ 错误: 无写入权限 - {output_path.parent}", err=True)
            typer.echo("提示: 请检查目录权限或使用其他路径", err=True)
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"❌ 错误: 无法创建目录 - {e}", err=True)
            raise typer.Exit(1)

        # 保存到 Parquet 文件
        success = save_to_parquet(df, output_path, compression=compression)

        if not success:
            typer.echo(f"❌ 错误: 保存 Parquet 文件失败", err=True)
            raise typer.Exit(1)

        # 获取文件信息
        file_size = output_path.stat().st_size
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.2f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.2f} KB"
        else:
            size_str = f"{file_size} B"

        # 输出成功信息
        typer.echo(f"✓ 成功导出 {len(df):,} 条数据到 {output_path}")
        typer.echo(f"  格式: Parquet (.parquet)")
        typer.echo(f"  压缩算法: {compression}")
        typer.echo(f"  文件大小: {size_str}")
        typer.echo(f"  交易对: {symbol}")
        typer.echo(f"  时间周期: {interval}")
        typer.echo(f"  数据类型: {'合约' if candle_type.lower() in ['future', 'futures'] else '现货'}")
        typer.echo(f"  数据源: {data_source or '全部'}")

        if start or end:
            typer.echo(f"  时间范围: {start or '无限制'} ~ {end or '无限制'}")
        if limit:
            typer.echo(f"  限制数量: {limit:,}")
        if columns:
            typer.echo(f"  导出列: {columns}")
        if format_timestamp:
            typer.echo(f"  时间戳格式: 已格式化为可读日期")
        elif ts_precision != 'auto':
            precision_names = {'s': '秒', 'ms': '毫秒', 'us': '微秒', 'ns': '纳秒'}
            typer.echo(f"  时间戳精度: {precision_names.get(ts_precision, ts_precision)}")

        # 可选：验证导出的文件
        if validate:
            typer.echo("")
            typer.echo("正在验证导出的文件...")
            validation_passed = _validate_parquet_export(output_path, df, verbose=verbose)

            if validation_passed:
                typer.echo(f"✓ 验证通过: 文件完整性检查正常")
            else:
                typer.echo(f"⚠️ 验证未完全通过: 建议检查文件内容", err=True)

        # 显示额外信息（verbose模式）
        if verbose:
            typer.echo("")
            typer.echo("详细统计:")
            parquet_info = get_parquet_info(output_path)
            if parquet_info:
                typer.echo(f"  行数: {parquet_info.get('num_rows', 'N/A'):,}")
                typer.echo(f"  列数: {parquet_info.get('num_columns', 'N/A')}")
                typer.echo(f"  Schema: {parquet_info.get('schema', 'N/A')}")

    except typer.Exit:
        raise
    except Exception as e:
        logger.exception(f"导出 Parquet 数据时发生错误: {e}")
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
            # 处理timestamp，统一转换为纳秒级
            try:
                ts_value = str(row['timestamp'])
                # 使用工具函数统一转换为纳秒级
                timestamp_ns = normalize_to_nanoseconds(ts_value, input_precision='auto')
            except (ValueError, TypeError) as e:
                logger.warning(f"无效的timestamp值: {row['timestamp']}，跳过该行，错误: {e}")
                continue

            symbol = str(row['symbol']).upper()
            # 使用命令行传入的interval参数，data_source固定为"import"
            interval_value = interval
            data_source_value = "import"

            # 生成unique_kline (使用纳秒级时间戳)
            unique_kline = f"{symbol}_{interval_value}_{timestamp_ns}"

            kline_list.append({
                'symbol': symbol,
                'interval': interval_value,
                'timestamp': timestamp_ns,  # 统一为纳秒级
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
    help="数据管理命令行工具（支持 CSV 和 Parquet 格式导出）",
    epilog="""
示例:
  # 下载BTCUSDT的日线数据
  python data_cli.py download -s BTCUSDT -i 1d --start 20240101 --end 20241231

  # 导出数据到CSV（传统格式）
  python data_cli.py export csv -s BTCUSDT -i 1h -o btc_1h.csv

  # 导出数据到Parquet（推荐，更高压缩率和性能）
  python data_cli.py export parquet -s BTCUSDT -i 1h -o btc_1h.parquet

  # 使用高压缩率算法并验证文件
  python data_cli.py export parquet -s BTCUSDT -i 1d --compression zstd --validate -o btc_daily.parquet

  # 从CSV导入数据
  python data_cli.py import csv data.csv

  # 查看本地数据
  python data_cli.py list-local-data

常用参数:
  -s, --symbol:     交易对符号 (如 BTCUSDT)
  -i, --interval:   时间周期 (如 1m, 5m, 15m, 30m, 1h, 4h, 1d)
  --start:          开始时间 (YYYYMMDD 格式)
  --end:            结束时间 (YYYYMMDD 格式)
  -o, --output:     输出文件路径
  --candle-type:    蜡烛图类型 (spot/future)

Parquet vs CSV:
  Parquet 格式提供 70-90% 的存储空间节省和 3-25 倍的查询速度提升，
  特别适合大数据量场景和需要高性能读取的应用。
    """
)

# 添加子命令
app.add_typer(export_app, name="export", help="导出数据到文件")
app.add_typer(import_app, name="import", help="从文件导入数据到数据库")


@app.command()
def download(
    symbols: Annotated[Optional[List[str]], typer.Option("--symbols", "-s", help="交易对列表，可多次指定，不指定则下载全部")] = None,
    pool: Annotated[Optional[str], typer.Option("--pool", help="自选组合名称")] = None,
    interval: Annotated[Optional[List[str]], typer.Option("--interval", "-i", help="时间周期列表，默认1h(如: 1m, 5m, 15m, 30m, 1h, 4h, 1d)")] = None,
    start: Annotated[Optional[str], typer.Option("--start", help="开始时间(YYYYMMDD)，默认1个月前")] = None,
    end: Annotated[Optional[str], typer.Option("--end", help="结束时间(YYYYMMDD)，默认今天")] = None,
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

    支持多交易对、多时间周期批量下载，数据将保存到指定目录并可选写入数据库。
    
    参数默认值逻辑：
    - 当--symbols和--pool均缺失时：自动获取全部可用货币对
    - 当--interval缺失时：默认下载1小时(1h)数据
    - 当--start和--end均缺失时：默认下载最近1个月数据
    - 当仅--start缺失时：从--end往前推1个月作为开始时间
    - 当仅--end缺失时：使用当前时间作为结束时间

    示例:
      # 下载所有货币对的1小时数据（最近1个月）
      python data_cli.py download
      
      # 下载指定货币对的1小时数据（最近1个月）
      python data_cli.py download -s BTCUSDT -s ETHUSDT
      
      # 下载指定时间范围的数据
      python data_cli.py download -s BTCUSDT -i 15m --start 20240101 --end 20241231

      # 使用自选组合
      python data_cli.py download --pool 我的自选组合 -i 15m --start 20240101 --end 20241231
    """
    if verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    # 检查是否同时指定了 symbols 和 pool
    if symbols and pool:
        typer.echo("错误: 不能同时指定 --symbols 和 --pool 参数", err=True)
        raise typer.Exit(1)

    # 处理 pool 参数，从自选组合获取交易对
    if pool:
        logger.info(f"从自选组合 '{pool}' 获取货币对...")
        try:
            symbols = get_symbols_from_data_pool(pool)
            if not symbols:
                typer.echo(f"错误: 自选组合 '{pool}' 中没有货币对", err=True)
                raise typer.Exit(1)
            logger.info(f"成功获取 {len(symbols)} 个货币对: {', '.join(symbols)}")
        except ValueError as e:
            typer.echo(f"错误: {e}", err=True)
            raise typer.Exit(1)

    # ========== 参数默认值处理 ==========
    
    # 1. 处理 symbols 参数（当 symbols 和 pool 都缺失时，获取全部货币对）
    if not symbols:
        logger.info("未指定交易对，正在获取全部可用货币对...")
        try:
            init_db()
            symbols = _get_all_available_symbols()
            if not symbols:
                typer.echo("错误: 数据库中没有可用货币对，请先添加货币对", err=True)
                raise typer.Exit(1)
            logger.info(f"成功获取 {len(symbols)} 个货币对")
        except Exception as e:
            typer.echo(f"错误: 获取货币对列表失败: {e}", err=True)
            raise typer.Exit(1)
    
    # 2. 处理 interval 参数（默认1h）
    if not interval:
        interval = ["1h"]
        logger.info(f"未指定时间周期，使用默认值: {interval[0]}")
    
    # 3. 处理 start 和 end 参数
    if not start and not end:
        # 都缺失：结束时间=今天，开始时间=1个月前
        start, end = _get_default_date_range()
        logger.info(f"未指定时间范围，使用默认值: {start} 至 {end}")
    elif not start and end:
        # 仅start缺失：开始时间=结束时间往前推1个月
        try:
            end_date = datetime.strptime(end, "%Y%m%d")
            start, _ = _get_default_date_range(end_date)
            logger.info(f"未指定开始时间，使用默认值: {start}")
        except ValueError:
            typer.echo(f"错误: 结束时间格式不正确: {end}，请使用 YYYYMMDD 格式", err=True)
            raise typer.Exit(1)
    elif start and not end:
        # 仅end缺失：结束时间=今天
        end = datetime.now().strftime("%Y%m%d")
        logger.info(f"未指定结束时间，使用默认值: {end}")
    
    # 验证时间格式并转换
    assert start is not None and end is not None, "start 和 end 不应该为 None"
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
                    progress.update(progress_pct - progress.n)  # pyright: ignore[reportAttributeAccessIssue]
                    if status:
                        progress.label = f"下载进度 - {status}"
            
            # 执行异步下载
            DataService.async_download_crypto(task_id, request)
        
        # 获取最终任务状态
        task_info = task_manager.get_task(task_id)
        
        if task_info and task_info.get("status") == "completed":
            typer.echo("")
            typer.echo("✓ 下载完成!")
            # 从 progress 子字典中获取统计信息，如果没有则使用默认值
            progress = task_info.get("progress", {})
            # 尝试从多个位置获取统计信息
            completed = progress.get('completed', task_info.get('completed', 0))
            failed = progress.get('failed', task_info.get('failed', 0))
            total = progress.get('total', task_info.get('total', 0))
            typer.echo(f"  已完成: {completed}")
            typer.echo(f"  失败: {failed}")
            typer.echo(f"  总任务数: {total}")
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
                            
                            if stats and stats.count > 0:  # pyright: ignore[reportOperatorIssue]
                                # 格式化时间戳
                                min_time = stats.min_time
                                max_time = stats.max_time

                                # 尝试将时间戳转换为可读格式
                                # 支持多种时间戳格式：秒(10位)、毫秒(13位)、微秒(16位)
                                def format_timestamp(ts_str: str) -> str:
                                    try:
                                        ts = int(ts_str)
                                        # 根据位数判断时间戳精度并转换为秒
                                        if ts > 10**15:  # 微秒级 (16位+)
                                            ts_sec = ts / 1_000_000
                                        elif ts > 10**12:  # 毫秒级 (13-15位)
                                            ts_sec = ts / 1_000
                                        else:  # 秒级 (10位)
                                            ts_sec = ts
                                        return datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")
                                    except:
                                        return str(ts_str)

                                try:
                                    min_dt = format_timestamp(min_time)
                                    max_dt = format_timestamp(max_time)
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
