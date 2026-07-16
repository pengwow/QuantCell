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
    from collector.services.data_service import GetData
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

# 创建质量检查子命令
quality_app = typer.Typer(help="数据质量管理命令")


def get_source_data_dir() -> Path:
    """获取源数据根目录: backend/data/source"""
    return Path(__file__).parent.parent / "data" / "source"


def scan_parquet_files(
    base_dir: Optional[Path] = None,
    symbol: Optional[str] = None,
    candle_type: str = "spot",
    interval: Optional[str] = None
) -> List[Dict]:
    """
    扫描 Parquet 文件并返回元数据信息

    Args:
        base_dir: 基础目录（默认为 data/source）
        symbol: 筛选特定交易对（如 BTCUSDT），None 表示全部
        candle_type: 市场类型 ("spot" 或 "future")
        interval: 筛选时间周期（如 15m, 1h），None 表示全部

    Returns:
        List[Dict]: 文件元信息列表，每项包含 path, symbol, interval, rows, size_bytes 等
    """
    if base_dir is None:
        base_dir = get_source_data_dir()

    # 确保 base_dir 是 Path 类型（防止外部传入字符串导致 TypeError）
    if isinstance(base_dir, str):
        base_dir = Path(base_dir)

    market_type = 'spot' if candle_type == "spot" else 'future'
    crypto_kline_dir = base_dir / 'crypto' / market_type / 'klines'

    if not crypto_kline_dir.exists():
        return []

    results = []

    # 遍历时间周期目录
    interval_dirs = [crypto_kline_dir / interval] if interval else sorted(crypto_kline_dir.iterdir()) if crypto_kline_dir.is_dir() else []

    for intv_dir in interval_dirs:
        if not intv_dir.is_dir():
            continue

        intv_name = intv_dir.name

        # 遍历 Parquet 文件
        parquet_files = list(intv_dir.glob("*.parquet"))
        for pfile in parquet_files:
            sym = pfile.stem

            # 按交易对筛选（支持逗号分隔的多交易对）
            if symbol:
                # ✅ 支持多交易对：将输入拆分为列表
                symbol_list = [s.strip().upper() for s in symbol.split(',') if s.strip()]
                if sym not in symbol_list:
                    continue

            try:
                meta = get_parquet_info(pfile)

                # 修正键名映射并提取时间范围
                rows = meta.get("num_rows", 0) or 0
                size_bytes = meta.get("file_size_bytes", 0) or 0

                # 提取时间范围（从 Parquet 元数据或实际数据中获取）
                min_time = None
                max_time = None
                try:
                    import pyarrow.parquet as pq
                    pf = pq.ParquetFile(pfile)
                    if pf.metadata.num_rows > 0:
                        # 使用 PyArrow 读取 timestamp 列的统计信息（性能优化）
                        # 只读取第一行和最后一行的 timestamp 值
                        table = pf.read(columns=['timestamp'])
                        timestamps = table['timestamp'].to_pylist()
                        if timestamps:
                            min_time = min(timestamps)
                            max_time = max(timestamps)
                except Exception as ts_error:
                    logger.debug(f"提取时间范围失败 {pfile.name}: {ts_error}")

                # 计算数据完整度
                completeness_info = calculate_data_completeness(
                    rows=rows,
                    min_time=min_time,
                    max_time=max_time,
                    interval=intv_name
                )

                results.append({
                    "path": pfile,
                    "symbol": sym,
                    "interval": intv_name,
                    "candle_type": candle_type,
                    "rows": rows,
                    "size_bytes": size_bytes,
                    "min_time": min_time,
                    "max_time": max_time,
                    "modified_time": datetime.fromtimestamp(pfile.stat().st_mtime),
                    "completeness": completeness_info,
                })
            except Exception as e:
                logger.warning(f"读取 {pfile} 元信息失败: {e}")

    return results


def filter_by_date_range(df: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    """
    按时间范围筛选 DataFrame（自动检测时间戳精度）

    支持多种时间戳精度：
    - 秒级 (s): 10位数字，如 1767830400
    - 毫秒级 (ms): 13位数字，如 1767830400000
    - 微秒级 (us): 16位数字，如 1767830400000000
    - 纳秒级 (ns): 19位数字，如 1767830400000000000

    Args:
        df: 包含 timestamp 或 date 列的 DataFrame
        start: 开始日期字符串 (YYYY-MM-DD)
        end: 结束日期字符串 (YYYY-MM-DD)

    Returns:
        筛选后的 DataFrame
    """
    if df.empty or ('timestamp' not in df.columns and 'date' not in df.columns):
        return df

    ts_col = 'timestamp' if 'timestamp' in df.columns else 'date'
    df[ts_col] = pd.to_numeric(df[ts_col], errors='coerce')
    df = df.dropna(subset=[ts_col])

    if df.empty:
        return df

    # 🔧 自动检测数据中的时间戳精度
    first_ts = int(df[ts_col].iloc[0])
    ts_len = len(str(first_ts))

    logger.debug(f"[filter_by_date_range] 检测到时间戳精度: {ts_len}位")

    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        # 根据数据的时间戳精度转换日期
        if ts_len > 16:  # 纳秒级 (19位)
            start_ts = int(start_dt.timestamp() * 1_000_000_000)
        elif ts_len > 13:  # 微秒级 (16位)
            start_ts = int(start_dt.timestamp() * 1_000_000)
        elif ts_len > 10:  # 毫秒级 (13位)
            start_ts = int(start_dt.timestamp() * 1000)
        else:  # 秒级 (10位)
            start_ts = int(start_dt.timestamp())

        logger.debug(f"[filter_by_date_range] 开始时间: {start} → {start_ts} ({ts_len}位)")
        df = df[df[ts_col] >= start_ts]

    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
        # 根据数据的时间戳精度转换日期
        if ts_len > 16:  # 纳秒级 (19位)
            end_ts = int(end_dt.timestamp() * 1_000_000_000)
        elif ts_len > 13:  # 微秒级 (16位)
            end_ts = int(end_dt.timestamp() * 1_000_000)
        elif ts_len > 10:  # 毫秒级 (13位)
            end_ts = int(end_dt.timestamp() * 1000)
        else:  # 秒级 (10位)
            end_ts = int(end_dt.timestamp())

        logger.debug(f"[filter_by_date_range] 结束时间: {end} → {end_ts} ({ts_len}位)")
        df = df[df[ts_col] < end_ts]

    logger.info(
        f"[filter_by_date_range] 时间筛选完成: "
        f"保留 {len(df)} 条记录 (原始 {len(df) + (len(df[df[ts_col] < start_ts]) if start else 0)} 条)"
    )

    return df


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_time_range(min_time: Any, max_time: Any) -> str:
    """格式化时间范围"""
    if min_time is None and max_time is None:
        return "-"

    try:
        if min_time is not None:
            if isinstance(min_time, (int, float)):
                # 自动检测时间戳精度并转换为 datetime
                # 支持：秒(10位)、毫秒(13位)、微秒(16位)、纳秒(19位)
                ts_int = int(min_time)
                ts_len = len(str(ts_int))

                if ts_len > 16:  # 纳秒级 (19位)
                    dt_min = datetime.fromtimestamp(ts_int / 1_000_000_000).strftime("%Y-%m-%d")
                elif ts_len > 13:  # 微秒级 (16位)
                    dt_min = datetime.fromtimestamp(ts_int / 1_000_000).strftime("%Y-%m-%d")
                elif ts_len > 10:  # 毫秒级 (13位)
                    dt_min = datetime.fromtimestamp(ts_int / 1_000).strftime("%Y-%m-%d")
                else:  # 秒级 (10位)
                    dt_min = datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d")
            else:
                dt_min = str(min_time)[:10]
        else:
            dt_min = "..."

        if max_time is not None:
            if isinstance(max_time, (int, float)):
                ts_int = int(max_time)
                ts_len = len(str(ts_int))

                if ts_len > 16:
                    dt_max = datetime.fromtimestamp(ts_int / 1_000_000_000).strftime("%Y-%m-%d")
                elif ts_len > 13:
                    dt_max = datetime.fromtimestamp(ts_int / 1_000_000).strftime("%Y-%m-%d")
                elif ts_len > 10:
                    dt_max = datetime.fromtimestamp(ts_int / 1_000).strftime("%Y-%m-%d")
                else:
                    dt_max = datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d")
            else:
                dt_max = str(max_time)[:10]
        else:
            dt_max = "..."

        return f"{dt_min} ~ {dt_max}"
    except Exception:
        return "-"


def calculate_data_completeness(
    rows: int,
    min_time: Any,
    max_time: Any,
    interval: str
) -> Dict[str, Any]:
    """
    计算K线数据的完整度

    根据时间周期和时间范围计算理论行数，与实际行数比较得出完整度百分比。

    Args:
        rows: 实际数据行数
        min_time: 最小时间戳（支持多种精度）
        max_time: 最大时间戳（支持多种精度）
        interval: 时间周期（如 15m, 1h, 1d）

    Returns:
        dict: 包含完整度百分比、状态标识、期望行数等信息
            - completeness_pct: float, 完整度百分比 (0-100+)
            - status: str, 状态标识 ('✓', '⚠️', '✗', '-')
            - expected_rows: int, 理论应有多少条数据
            - actual_rows: int, 实际有多少条数据
    """
    if not rows or min_time is None or max_time is None:
        return {
            'completeness_pct': 0,
            'status': '-',
            'expected_rows': 0,
            'actual_rows': 0
        }

    # 时间周期到每天行数的映射
    INTERVAL_MAP = {
        '1m': 1440,   # 24 * 60 = 1440 条/天
        '3m': 480,    # 24 * 20 = 480 条/天
        '5m': 288,    # 24 * 12 = 288 条/天
        '15m': 96,    # 24 * 4 = 96 条/天
        '30m': 48,    # 24 * 2 = 48 条/天
        '1h': 24,     # 24 条/天
        '2h': 12,     # 12 条/天
        '4h': 6,      # 6 条/天
        '6h': 4,      # 4 条/天
        '8h': 3,      # 3 条/天
        '12h': 2,     # 2 条/天
        '1d': 1,      # 1 条/天
        '1w': 0.1429, # 约 0.14 条/天（周K线特殊处理）
    }

    rows_per_day = INTERVAL_MAP.get(interval, 24)

    try:
        # 自动检测时间戳精度并转换
        ts_min = int(min_time)
        ts_max = int(max_time)
        ts_len = len(str(ts_min))

        if ts_len > 16:  # 纳秒级 (19位)
            dt_min = datetime.fromtimestamp(ts_min / 1_000_000_000)
            dt_max = datetime.fromtimestamp(ts_max / 1_000_000_000)
        elif ts_len > 13:  # 微秒级 (16位)
            dt_min = datetime.fromtimestamp(ts_min / 1_000_000)
            dt_max = datetime.fromtimestamp(ts_max / 1_000_000)
        elif ts_len > 10:  # 毫秒级 (13位)
            dt_min = datetime.fromtimestamp(ts_min / 1_000)
            dt_max = datetime.fromtimestamp(ts_max / 1_000)
        else:  # 秒级 (10位)
            dt_min = datetime.fromtimestamp(ts_min)
            dt_max = datetime.fromtimestamp(ts_max)

        # 使用精确的时间跨度计算（修复：避免 .days 截断导致的虚高问题）
        span_seconds = (dt_max - dt_min).total_seconds()

        # 将时间周期转换为秒数（精确计算理论K线数量）
        INTERVAL_SECONDS_MAP = {
            '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
            '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600,
            '8h': 28800, '12h': 43200, '1d': 86400, '1w': 604800
        }
        interval_seconds = INTERVAL_SECONDS_MAP.get(interval, 3600)

        # 计算精确的理论行数
        expected_rows = max(int(span_seconds / interval_seconds), 1)

        if expected_rows == 0:
            return {'completeness_pct': 100.0, 'status': '✓', 'expected_rows': 0, 'actual_rows': rows}

        # 计算完整度百分比
        completeness = (rows / expected_rows) * 100

        # 判定状态
        if completeness >= 95:
            status = '✓'
        elif completeness >= 70:
            status = '⚠️'
        else:
            status = '✗'

        return {
            'completeness_pct': round(completeness, 1),
            'status': status,
            'expected_rows': expected_rows,
            'actual_rows': rows
        }
    except Exception:
        return {'completeness_pct': 0, 'status': '-', 'expected_rows': 0, 'actual_rows': rows}


def format_completeness(completeness_info: Dict) -> str:
    """
    格式化完整度显示字符串

    Args:
        completeness_info: calculate_data_completeness() 返回的字典

    Returns:
        str: 格式化后的字符串，如 "97% ✓" 或 "67% ⚠️"
    """
    pct = completeness_info.get('completeness_pct', 0)
    status = completeness_info.get('status', '-')

    if status == '-':
        return '-'

    return f"{pct:.0f}% {status}"


def _find_parquet_file(symbol: str, interval: str, candle_type: str = "spot") -> Path:
    """
    定位 Parquet 文件路径

    Args:
        symbol: 交易对符号（如 BTCUSDT 或 ETH/USDT）
        interval: 时间周期（如 1h, 15m）
        candle_type: 市场类型 ("spot" 或 "future")

    Returns:
        Path: Parquet 文件的完整路径
    """
    # 标准化货币对名称：移除斜杠（ETH/USDT → ETHUSDT）
    normalized_symbol = symbol.upper().replace("/", "")
    
    base_dir = get_source_data_dir()
    market_type = 'spot' if candle_type == "spot" else 'future'
    return base_dir / 'crypto' / market_type / 'klines' / interval / f"{normalized_symbol}.parquet"


def _init_db_for_task_manager():
    """为 task_manager 初始化数据库（仅在需要任务管理功能时使用）"""
    try:
        init_database_config()
    except Exception as e:
        logger.debug(f"数据库初始化可选，跳过: {e}")


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
    导出K线数据到CSV格式文件（从本地Parquet文件读取）

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
    """
    try:
        # 1. 定位 Parquet 文件
        parquet_path = _find_parquet_file(symbol, interval, candle_type)

        if not parquet_path.exists():
            typer.echo(f"错误: 未找到 {symbol} {interval} 的Parquet文件", err=True)
            typer.echo(f"  预期路径: {parquet_path}", err=True)
            typer.echo("", err=True)
            typer.echo("提示:", err=True)
            typer.echo("  1. 请先使用 download 命令下载数据:", err=True)
            typer.echo(f"     python data_cli.py download -s {symbol} -i {interval}", err=True)
            typer.echo("  2. 或使用 list-local-data 查看可用数据:", err=True)
            typer.echo("     python data_cli.py list-local-data", err=True)
            raise typer.Exit(1)

        # 2. 加载 Parquet 数据
        df = load_from_parquet(parquet_path)

        if df.empty:
            typer.echo(f"警告: Parquet 文件为空 - {parquet_path}")
            return

        logger.info(f"成功加载 Parquet 文件: {parquet_path}, 共 {len(df)} 行")

        # 3. 应用筛选条件
        df = filter_by_date_range(df, start, end)

        # 4. 排序
        if sort_desc:
            ts_col = 'timestamp' if 'timestamp' in df.columns else 'date'
            df = df.sort_values(ts_col, ascending=False)

        # 5. 限制记录数量
        if limit and limit > 0:
            df = df.head(limit)

        # 6. 检查是否还有数据
        if df.empty:
            typer.echo(f"未找到符合条件的数据（请检查时间范围筛选）")
            return

        # 7. 选择列
        if columns:
            selected_columns = [col.strip() for col in columns.split(',')]
            # 验证列名
            missing_cols = [col for col in selected_columns if col not in df.columns]
            if missing_cols:
                typer.echo(f"错误: 无效的列名: {', '.join(missing_cols)}", err=True)
                typer.echo(f"可用列: {', '.join(df.columns)}", err=True)
                raise typer.Exit(1)
            df = df[selected_columns]

        # 8. 处理时间戳字段
        if 'timestamp' in df.columns:
            if format_timestamp:
                def format_ts_readable(ts_value):
                    """将纳秒级时间戳格式化为可读日期"""
                    try:
                        return format_nanoseconds(ts_value, "%Y-%m-%d %H:%M:%S")
                    except:
                        return str(ts_value)

                df['timestamp'] = df['timestamp'].apply(format_ts_readable)
                logger.info("已将时间戳格式化为可读日期")
            elif ts_precision != 'auto':
                from typing import cast
                from utils.timestamp_utils import Precision
                precision = cast(Precision, ts_precision)
                df['timestamp'] = df['timestamp'].apply(lambda x: from_nanoseconds(x, precision))
                logger.info(f"已统一时间戳精度为: {ts_precision}")

        # 9. 验证时间戳精度参数（如果未使用）
        valid_precisions = ['s', 'ms', 'us', 'ns', 'auto']
        if ts_precision not in valid_precisions:
            typer.echo(f"错误: 无效的时间戳精度: {ts_precision}", err=True)
            typer.echo(f"可用选项: {', '.join(valid_precisions)} (s:秒, ms:毫秒, us:微秒, ns:纳秒, auto:自动)", err=True)
            raise typer.Exit(1)

        # 10. 保存到 CSV
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 构建 to_csv 参数
        csv_kwargs = {
            'index': False,
            'header': not no_header,
            'sep': delimiter,
        }

        if compress or str(output).endswith('.gz'):
            if not str(output).endswith('.csv.gz'):
                output_path = output_path.with_suffix('.csv.gz')
            csv_kwargs['compression'] = 'gzip'

        df.to_csv(output_path, **csv_kwargs)

        # 11. 计算文件大小并输出结果
        file_size = output_path.stat().st_size
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.2f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.2f} KB"
        else:
            size_str = f"{file_size} B"

        typer.echo(f"✓ 成功导出 {len(df):,} 条数据到 {output_path}")
        typer.echo(f"  文件大小: {size_str}")
        typer.echo(f"  交易对: {symbol}")
        typer.echo(f"  时间周期: {interval}")
        typer.echo(f"  数据源: 本地Parquet文件")
        if start or end:
            typer.echo(f"  时间范围: {start or '无限制'} ~ {end or '无限制'}")
        if limit:
            typer.echo(f"  限制数量: {limit:,}")
        if columns:
            typer.echo(f"  导出列: {columns}")
        if format_timestamp:
            typer.echo(f"  时间戳格式: 已格式化")
        elif ts_precision != 'auto':
            precision_names = {'s': '秒', 'ms': '毫秒', 'us': '微秒'}
            typer.echo(f"  时间戳精度: {precision_names.get(ts_precision, ts_precision)}")
        if compress:
            typer.echo(f"  压缩: 已启用")

    except typer.Exit:
        raise
    except Exception as e:
        logger.exception(f"导出CSV数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@export_app.command("parquet")
def export_parquet(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对，如BTCUSDT")],
    interval: Annotated[str, typer.Option("--interval", "-i", help="时间周期，如1m, 5m, 1h, 1d")],
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="输出文件路径(.parquet)，默认保存到当前目录")] = None,
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
    导出K线数据到Parquet格式文件（从本地Parquet文件读取并转换）

    Parquet 格式相比 CSV 具有：
    - 更高的压缩率（通常 70-90% 空间节省）
    - 更快的查询速度（特别是列式读取）
    - 类型安全（保持原始数据类型，数值不转为字符串）

    示例:
      # 基本用法 - 导出BTCUSDT的1小时数据
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
    """
    try:
        if verbose:
            logger.remove()
            logger.add(sys.stderr, level="DEBUG")

        # 1. 定位源 Parquet 文件
        source_path = _find_parquet_file(symbol, interval, candle_type)

        if not source_path.exists():
            typer.echo(f"错误: 未找到 {symbol} {interval} 的源Parquet文件", err=True)
            typer.echo(f"  预期路径: {source_path}", err=True)
            typer.echo("", err=True)
            typer.echo("提示:", err=True)
            typer.echo("  1. 请先使用 download 命令下载数据:", err=True)
            typer.echo(f"     python data_cli.py download -s {symbol} -i {interval}", err=True)
            raise typer.Exit(1)

        # 2. 加载源数据
        df = load_from_parquet(source_path)

        if df.empty:
            typer.echo(f"⚠️ 源Parquet文件为空: {source_path}")
            return

        if verbose:
            typer.echo(f"成功加载源文件: {source_path}")
            typer.echo(f"  原始行数: {len(df):,}")

        # 3. 应用筛选条件
        df = filter_by_date_range(df, start, end)

        # 4. 排序
        if sort_desc:
            ts_col = 'timestamp' if 'timestamp' in df.columns else 'date'
            df = df.sort_values(ts_col, ascending=False)

        # 5. 限制记录数量
        if limit and limit > 0:
            df = df.head(limit)

        # 6. 选择列
        if columns:
            selected_columns = [col.strip() for col in columns.split(',')]
            missing_cols = [col for col in selected_columns if col not in df.columns]
            if missing_cols:
                typer.echo(f"错误: 无效的列名: {', '.join(missing_cols)}", err=True)
                typer.echo(f"可用列: {', '.join(df.columns)}", err=True)
                raise typer.Exit(1)
            df = df[selected_columns]

        # 7. 检查是否还有数据
        if df.empty:
            typer.echo(f"⚠️ 未找到符合条件的数据（请检查筛选条件）")
            return

        # 8. 处理时间戳字段
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
            def format_ts_readable(ts_value):
                try:
                    return format_nanoseconds(ts_value, "%Y-%m-%d %H:%M:%S")
                except:
                    return str(ts_value)

            df['timestamp'] = df['timestamp'].apply(format_ts_readable)
            if verbose:
                typer.echo("已将时间戳格式化为可读日期")

        # 9. 验证压缩算法参数
        valid_compressions = ['snappy', 'gzip', 'zstd']
        if compression not in valid_compressions:
            typer.echo(f"错误: 不支持的压缩算法: {compression}", err=True)
            typer.echo(f"可用选项: {', '.join(valid_compressions)}", err=True)
            raise typer.Exit(1)

        # 10. 验证时间戳精度参数
        valid_precisions = ['s', 'ms', 'us', 'ns', 'auto']
        if ts_precision not in valid_precisions:
            typer.echo(f"错误: 无效的时间戳精度: {ts_precision}", err=True)
            typer.echo(f"可用选项: {', '.join(valid_precisions)} (s:秒, ms:毫秒, us:微秒, ns:纳秒, auto:自动)", err=True)
            raise typer.Exit(1)

        # 11. 确定输出路径
        if output:
            output_path = Path(output)
        else:
            # 默认保存到当前目录（标准化货币对名称）
            normalized_symbol = symbol.upper().replace("/", "")
            output_path = Path.cwd() / f"{normalized_symbol}_{interval}.parquet"
            if verbose:
                typer.echo(f"使用默认输出路径: {output_path}")

        # 12. 确保输出目录存在
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            typer.echo(f"❌ 错误: 无写入权限 - {output_path.parent}", err=True)
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"❌ 错误: 无法创建目录 - {e}", err=True)
            raise typer.Exit(1)

        # 13. 保存到目标 Parquet 文件
        success = save_to_parquet(df, output_path, compression=compression)

        if not success:
            typer.echo(f"❌ 错误: 保存 Parquet 文件失败", err=True)
            raise typer.Exit(1)

        # 14. 获取文件信息并输出结果
        file_size = output_path.stat().st_size
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.2f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.2f} KB"
        else:
            size_str = f"{file_size} B"

        typer.echo(f"✓ 成功导出 {len(df):,} 条数据到 {output_path}")
        typer.echo(f"  格式: Parquet (.parquet)")
        typer.echo(f"  压缩算法: {compression}")
        typer.echo(f"  文件大小: {size_str}")
        typer.echo(f"  交易对: {symbol}")
        typer.echo(f"  时间周期: {interval}")
        typer.echo(f"  数据类型: {'合约' if candle_type.lower() in ['future', 'futures'] else '现货'}")
        typer.echo(f"  数据源: 本地Parquet文件")

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

        # 15. 可选：验证导出的文件
        if validate:
            typer.echo("")
            typer.echo("正在验证导出的文件...")
            validation_passed = _validate_parquet_export(output_path, df, verbose=verbose)

            if validation_passed:
                typer.echo(f"✓ 验证通过: 文件完整性检查正常")
            else:
                typer.echo(f"⚠️ 验证未完全通过: 建议检查文件内容", err=True)

        # 16. 显示额外信息（verbose模式）
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
        _init_db_for_task_manager()
        
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
app.add_typer(quality_app, name="quality", help="数据质量管理")


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

    # ✅ 验证时间范围：end 必须大于等于 start
    if start and end:
        try:
            from datetime import datetime as dt
            start_date = dt.strptime(start, "%Y%m%d")
            end_date = dt.strptime(end, "%Y%m%d")
            
            if end_date < start_date:
                typer.echo(f"❌ 错误: 结束时间 ({end}) 不能早于开始时间 ({start})", err=True)
                typer.echo(f"   开始时间: {start} → {start_date.strftime('%Y-%m-%d')}", err=True)
                typer.echo(f"   结束时间: {end}   → {end_date.strftime('%Y-%m-%d')}", err=True)
                typer.echo("", err=True)
                typer.echo(f"💡 请确保 --end 时间 >= --start 时间", err=True)
                raise typer.Exit(1)
            elif end_date == start_date:
                typer.echo(f"⚠️  提示: 开始时间和结束时间相同 ({start})，将下载该天的数据")
        except ValueError as e:
            typer.echo(f"❌ 错误: 时间格式无效 - {e}", err=True)
            typer.echo(f"   请使用 YYYYMMDD 格式，如: 20260101", err=True)
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

    # 1. 处理 symbols 参数（当 symbols 和 pool 都缺失时，从交易所API获取所有可用货币对）
    if not symbols:
        logger.info("未指定交易对，正在从交易所API获取所有可用货币对...")
        try:
            import requests as _requests

            if exchange == "binance":
                if candle_type == 'spot':
                    url = 'https://api.binance.com/api/v3/exchangeInfo'
                elif candle_type == 'future':
                    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
                else:
                    raise ValueError(f"不支持的蜡烛图类型: {candle_type}")

                response = _requests.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()
                symbols = [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']
            else:
                raise ValueError(f"暂不支持自动获取 {exchange} 交易所的交易对列表")

            if symbols:
                logger.info(f"✅ 从交易所API成功获取 {len(symbols)} 个可用交易对")
                typer.echo(f"ℹ️  未指定交易对，将从交易所下载所有 {len(symbols)} 个可用交易对")
            else:
                typer.echo("⚠️  无法从交易所API获取交易对列表", err=True)
                typer.echo("", err=True)
                typer.echo("解决方案:", err=True)
                typer.echo("  1. 使用 -s 参数指定交易对，例如:", err=True)
                typer.echo("     python data_cli.py download -s BTCUSDT -s ETHUSDT", err=True)
                typer.echo("", err=True)
                typer.echo("  2. 检查网络连接和交易所API是否正常", err=True)
                raise typer.Exit(1)

        except Exception as e:
            logger.error(f"从交易所API获取交易对失败: {e}")
            typer.echo(f"❌ 错误: 从交易所获取交易对列表失败 - {e}", err=True)
            typer.echo("", err=True)
            typer.echo("请使用 -s 参数手动指定交易对:", err=True)
            typer.echo("  python data_cli.py download -s BTCUSDT -s ETHUSDT", err=True)
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
        _init_db_for_task_manager()

        # 使用固定下载目录：项目后端根目录的 data/source 目录
        if not save_dir:
            save_dir = str(Path(__file__).parent.parent / "data" / "source")
            logger.info(f"使用固定下载目录: {save_dir}")
        
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

        # 使用线程异步执行下载，主线程轮询进度
        import threading
        download_error: list = [None]  # 用于捕获异常

        def run_download():
            try:
                data_service.async_download_crypto(task_id, request)
            except Exception as e:
                download_error[0] = e
                logger.exception(f"下载过程出错: {e}")

        # 启动下载线程
        download_thread = threading.Thread(target=run_download)
        download_thread.start()

        # 轮询进度并显示进度条（在行尾）
        import time
        import sys

        last_status = ""
        bar_width = 20  # 进度条宽度（字符数）

        while download_thread.is_alive():
            time.sleep(0.5)  # 每0.5秒刷新一次

            task_info = task_manager.get_task(task_id)
            if task_info:
                progress_data = task_info.get('progress', {})
                completed = progress_data.get('completed', 0)
                total = progress_data.get('total', 1)
                status = progress_data.get('status', '')

                if total > 0:
                    progress_pct = min((completed / total) * 100, 100)

                    # 生成进度条
                    filled = int(bar_width * completed / total)
                    bar = '█' * filled + '░' * (bar_width - filled)

                    # 组装完整状态行：状态文字 + 进度条 + 百分比
                    current_status = f"\r  {status} [{bar}] {progress_pct:5.1f}%" if status else f"\r  [{bar}] {progress_pct:5.1f}%"

                    if current_status != last_status:
                        sys.stdout.write(current_status)
                        sys.stdout.flush()
                        last_status = current_status

        print()  # 换行
        
        # 获取最终任务状态
        task_info = task_manager.get_task(task_id)
        
        if task_info and task_info.get("status") == "completed":
            typer.echo("")
            typer.echo("✓ 下载完成!")

            # ✅ 从 progress 子字典获取真实的统计数据（这是正确的数据源）
            progress_data = task_info.get('progress', {})
            actual_completed = progress_data.get('completed', task_info.get('completed', 0))
            actual_failed = progress_data.get('failed', task_info.get('failed', 0))
            actual_total = progress_data.get('total', task_info.get('total', 0))

            # 如果还是0，尝试从参数推断
            if actual_total == 0:
                actual_total = len(interval) * len(symbols) if interval and symbols else 1

            typer.echo(f"  已完成: {actual_completed}")
            typer.echo(f"  失败: {actual_failed}")
            typer.echo(f"  总任务数: {actual_total}")

            # ✅ 只有当 completed=0 且 total>0 时才提示（说明确实没有成功完成任务）
            if actual_completed == 0 and actual_total > 0:
                typer.echo("")
                typer.echo("⚠️  提示: 没有成功下载任何数据，请检查网络或数据源")
        else:
            typer.echo("")
            typer.echo("✗ 下载可能未完成，请使用 status 命令查询任务状态")
        
        typer.echo(f"\n可使用以下命令查询任务状态:")
        typer.echo(f"  python data_cli.py status -t {task_id}")
        typer.echo(f"\n可使用以下命令查询本地数据:")
        typer.echo(f"  python data_cli.py list-local-data -s {','.join(symbols)}")
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
        _init_db_for_task_manager()
        
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
    exchange: Annotated[str, typer.Option("--exchange", "-e", help="交易所（保留参数兼容性）")] = "binance",
    limit: Annotated[int, typer.Option("--limit", "-l", help="显示数量限制")] = 50,
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future/all)")] = "all",
):
    """
    列出支持的货币对（基于本地Parquet文件）

    显示本地Parquet文件中已存在的货币对列表

    示例:
      # 列出所有货币对（默认限制50个）
      python data_cli.py list-symbols

      # 列出前100个货币对
      python data_cli.py list-symbols --limit 100

      # 只列出现货货币对
      python data_cli.py list-symbols --candle-type spot

      # 只列出合约货币对
      python data_cli.py list-symbols --candle-type future
    """
    try:
        # 根据 candle_type 扫描对应的 Parquet 文件
        if candle_type.lower() == "spot":
            files = scan_parquet_files(candle_type="spot")
            type_label = "现货"
        elif candle_type.lower() == "future":
            files = scan_parquet_files(candle_type="future")
            type_label = "合约"
        else:
            # 默认显示所有类型
            spot_files = scan_parquet_files(candle_type="spot")
            future_files = scan_parquet_files(candle_type="future")
            files = spot_files + future_files
            type_label = "全部"

        if not files:
            typer.echo(f"未找到任何本地Parquet数据")
            typer.echo("提示: 请先使用 download 命令下载数据")
            return

        # 提取唯一符号并排序
        symbols = sorted(set(f['symbol'] for f in files))[:limit]

        # 统计信息
        total_unique = len(set(f['symbol'] for f in files))
        spot_count = len(set(f['symbol'] for f in scan_parquet_files(candle_type="spot")))
        future_count = len(set(f['symbol'] for f in scan_parquet_files(candle_type="future")))

        typer.echo(f"交易所: {exchange} (基于本地Parquet文件)")
        typer.echo(f"类型: {type_label}")
        typer.echo(f"货币对总数: {total_unique} (显示前 {len(symbols)} 个)")
        if candle_type.lower() == "all":
            typer.echo(f"  现货: {spot_count} 个 | 合约: {future_count} 个")
        typer.echo("")

        # 分页显示（每行5个）
        for i in range(0, len(symbols), 5):
            row = symbols[i:i+5]
            typer.echo("  ".join(f"{s:12}" for s in row))

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
        _init_db_for_task_manager()
        
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
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    interval: Annotated[Optional[str], typer.Option("--interval", "-i", help="时间周期筛选(可选，如1h, 1d)")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="显示数量限制")] = 50,
    list_intervals: Annotated[bool, typer.Option("--list-intervals", help="列出所有可用的时间周期")] = False,
):
    """
    查看本地K线数据（基于Parquet文件）

    显示已下载到本地的Parquet文件信息，包括交易对、时间周期、数据量和时间范围

    示例:
      # 列出所有可用的数据
      python data_cli.py list-local-data

      # 查看特定交易对的数据
      python data_cli.py list-local-data -s BTCUSDT

      # 筛选特定时间周期
      python data_cli.py list-local-data -i 1h

      # 查看合约数据
      python data_cli.py list-local-data --candle-type future

      # 列出所有可用的时间周期
      python data_cli.py list-local-data --list-intervals
    """
    try:
        # 如果需要列出所有时间周期
        if list_intervals:
            files = scan_parquet_files(candle_type=candle_type)
            if not files:
                typer.echo(f"未找到任何{candle_type} Parquet 数据")
                return

            intervals = sorted(set(f['interval'] for f in files))

            typer.echo(f"\n{'='*60}")
            typer.echo(f"可用的 {candle_type.upper()} 时间周期")
            typer.echo(f"{'='*60}")

            for intv in intervals:
                intv_files = [f for f in files if f['interval'] == intv]
                symbol_count = len(set(f['symbol'] for f in intv_files))
                total_rows = sum(f['rows'] for f in intv_files)
                total_size = sum(f['size_bytes'] for f in intv_files)

                typer.echo(f"  {intv:8} | 交易对: {symbol_count:4} | 文件数: {len(intv_files):4} | 总行数: {total_rows:10,} | 总大小: {format_size(total_size):>10}")

            typer.echo(f"{'='*60}\n")
            return

        # 扫描 Parquet 文件
        files = scan_parquet_files(
            symbol=symbol,
            candle_type=candle_type,
            interval=interval
        )

        if not files:
            if symbol:
                typer.echo(f"未找到交易对 {symbol} 的本地Parquet数据")
            elif interval:
                typer.echo(f"未找到时间周期 {interval} 的本地Parquet数据")
            else:
                typer.echo(f"未找到任何本地{candle_type} Parquet数据")
            typer.echo("提示: 请先使用 download 命令下载数据")
            return

        # 限制显示数量
        display_files = files[:limit]

        # 显示概览信息
        typer.echo(f"\n{'='*100}")
        typer.echo(f"本地 {candle_type.upper()} Parquet 数据概览 | 共 {len(files)} 个文件 (显示前 {len(display_files)} 个)")
        if symbol:
            typer.echo(f"交易对筛选: {symbol}")
        if interval:
            typer.echo(f"时间周期筛选: {interval}")
        typer.echo(f"{'='*100}\n")

        # 表头
        typer.echo(f"{'交易对':<12} {'周期':<6} {'行数':>10} {'大小':>10} {'时间范围':<35} {'完整度':<10} {'修改时间':<20}")
        typer.echo("-" * 110)

        # 显示每个文件的信息
        for f in display_files:
            time_range = format_time_range(f.get('min_time'), f.get('max_time'))
            modified_time = f.get('modified_time', '').strftime("%Y-%m-%d %H:%M") if hasattr(f.get('modified_time', ''), 'strftime') else str(f.get('modified_time', ''))[:19]
            completeness_str = format_completeness(f.get('completeness', {}))

            typer.echo(
                f"{f['symbol']:<12} "
                f"{f['interval']:<6} "
                f"{f['rows']:>10,} "
                f"{format_size(f['size_bytes']):>10} "
                f"{time_range:<35} "
                f"{completeness_str:<10} "
                f"{modified_time:<20}"
            )

        # 统计信息
        typer.echo(f"\n{'='*100}")
        total_rows = sum(f['rows'] for f in files)
        total_size = sum(f['size_bytes'] for f in files)
        unique_symbols = len(set(f['symbol'] for f in files))
        unique_intervals = len(set(f['interval'] for f in files))

        typer.echo(f"总计:")
        typer.echo(f"  文件数: {len(files)}")
        typer.echo(f"  交易对数: {unique_symbols}")
        typer.echo(f"  时间周期数: {unique_intervals}")
        typer.echo(f"  总行数: {total_rows:,}")
        typer.echo(f"  总大小: {format_size(total_size)}")
        typer.echo(f"{'='*100}\n")

    except Exception as e:
        logger.exception(f"查询本地数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def delete_local_data(
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对")],
    interval: Annotated[Optional[str], typer.Option("--interval", "-i", help="时间周期(可选，不指定则删除所有周期)")] = None,
    candle_type: Annotated[str, typer.Option("--candle-type", help="蜡烛图类型(spot/future)")] = "spot",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="确认删除，不提示")] = False,
):
    """
    删除本地K线数据（删除Parquet文件）

    删除指定交易对的本地Parquet文件，支持按时间周期筛选。
    删除的文件会被移动到 .trash/deleted_parquets 目录，可手动恢复。

    示例:
      # 删除 BTCUSDT 的所有周期数据（会提示确认）
      python data_cli.py delete-local-data -s BTCUSDT

      # 删除 BTCUSDT 的1小时数据
      python data_cli.py delete-local-data -s BTCUSDT -i 1h

      # 跳过确认直接删除
      python data_cli.py delete-local-data -s BTCUSDT -i 1h -y

      # 删除合约数据
      python data_cli.py delete-local-data -s BTCUSDT --candle-type future
    """
    import shutil

    try:
        # 查找匹配的 Parquet 文件
        files = scan_parquet_files(
            symbol=symbol,
            candle_type=candle_type,
            interval=interval
        )

        if not files:
            typer.echo(f"未找到 {symbol} 的Parquet文件")
            if interval:
                typer.echo(f"  筛选条件: 时间周期={interval}, 类型={candle_type}")
            else:
                typer.echo(f"  筛选条件: 类型={candle_type}")
            typer.echo("提示: 使用 list-local-data 查看可用数据")
            return

        # 显示待删除文件列表
        total_rows = sum(f['rows'] for f in files)
        total_size = sum(f['size_bytes'] for f in files)

        typer.echo(f"\n找到 {len(files)} 个待删除文件:")
        typer.echo("-" * 80)
        for f in files:
            time_range = format_time_range(f.get('min_time'), f.get('max_time'))
            typer.echo(f"  {f['path']}")
            typer.echo(f"    大小: {format_size(f['size_bytes']):>10} | 行数: {f['rows']:>8,} | 周期: {f['interval']:6} | 时间: {time_range}")
        typer.echo("-" * 80)
        typer.echo(f"总计: {len(files)} 个文件, {total_rows:,} 行数据, {format_size(total_size)}")
        typer.echo("")

        # 确认删除
        if not yes:
            if interval:
                confirm_msg = f"确定要删除 {symbol} 的 {interval} 数据吗？（共 {len(files)} 个文件）"
            else:
                confirm_msg = f"确定要删除 {symbol} 的所有周期数据吗？（共 {len(files)} 个文件）"

            confirm = typer.confirm(confirm_msg)
            if not confirm:
                typer.echo("已取消删除")
                return

        # 创建回收站目录（遵循项目规则：使用 mv 而非 rm）
        trash_dir = Path(".trash/deleted_parquets")
        trash_dir.mkdir(parents=True, exist_ok=True)

        # 执行删除（移动到回收站目录）
        deleted_count = 0
        failed_files = []

        for f in files:
            try:
                file_path = f['path']
                dest_path = trash_dir / f"{file_path.parent.parent.name}_{file_path.parent.name}_{file_path.name}"

                # 如果目标文件已存在，添加时间戳避免冲突
                if dest_path.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dest_path = trash_dir / f"{file_path.parent.parent.name}_{file_path.parent.name}_{timestamp}_{file_path.name}"

                shutil.move(str(file_path), str(dest_path))
                deleted_count += 1
                logger.info(f"已移动到回收站: {file_path} -> {dest_path}")

            except Exception as e:
                logger.error(f"移动文件失败 {f['path']}: {e}")
                failed_files.append((f['path'], str(e)))

        # 输出结果
        typer.echo("")
        if deleted_count > 0:
            typer.echo(f"✓ 成功删除 {deleted_count} 个文件（已移动到回收站目录）")
            typer.echo(f"  回收站路径: {trash_dir.resolve()}")
            typer.echo(f"  如需恢复，请从回收站目录手动移回原位置")

        if failed_files:
            typer.echo("", err=True)
            typer.echo(f"⚠️ {len(failed_files)} 个文件删除失败:", err=True)
            for path, error in failed_files:
                typer.echo(f"  {path}: {error}", err=True)

        typer.echo("")
        typer.echo("统计:")
        typer.echo(f"  成功: {deleted_count} 个文件")
        typer.echo(f"  失败: {len(failed_files)} 个文件")
        typer.echo(f"  释放空间: ~{format_size(total_size)}")

    except Exception as e:
        logger.exception(f"删除本地数据时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 数据质量管理命令 ==========

def _print_quality_report(result: dict, verbose: bool = False):
    """
    格式化输出质量报告

    Args:
        result: 质量检查结果字典
        verbose: 是否显示详细信息
    """
    summary = result.get('summary', {})
    details = result.get('details', {})
    time_range = result.get('time_range', {})

    # 总体评分
    typer.echo(f"\n📈 总体评分:")
    typer.echo(f"   得分: {summary.get('score', 0):.1f}/100")
    typer.echo(f"   等级: {summary.get('grade', '-')}")
    typer.echo(f"   通过: {summary.get('checks_passed', 0)}/{summary.get('checks_total', 0)} 项检查")
    typer.echo(f"   时间范围: {time_range.get('start', '-')} ~ {time_range.get('end', '-')}")
    typer.echo(f"   总记录数: {result.get('total_records', 0):,}")

    # 各项检查详情
    checks = [
        ('integrity', '🔍 完整性检查', details.get('integrity')),
        ('continuity', '📊 连续性检查', details.get('continuity')),
        ('validity', '✅ 有效性检查', details.get('validity')),
        ('uniqueness', '🔄 唯一性检查', details.get('uniqueness'))
    ]

    for key, title, detail in checks:
        if not detail:
            continue

        status = detail.get('status', 'unknown')
        icon = {'pass': '✅', 'fail': '❌', 'warning': '⚠️'}.get(status, '❓')

        typer.echo(f"\n{title} {icon}")

        if key == 'integrity':
            missing = detail.get('missing_values', {})
            if missing:
                typer.echo(f"   缺失值: {missing}")
            cols = detail.get('missing_columns', [])
            if cols:
                typer.echo(f"   缺失列: {cols}")

        elif key == 'continuity':
            coverage = detail.get('coverage_ratio', 0) * 100
            expected = detail.get('expected_records', 0)
            actual = detail.get('actual_records', 0)
            missing = detail.get('missing_records', 0)

            typer.echo(f"   覆盖率: {coverage:.1f}%")
            typer.echo(f"   期望/实际: {expected:,}/{actual:,}")
            if missing > 0:
                typer.echo(f"   缺失记录: {missing:,}")

            if verbose:
                gaps = detail.get('gaps', [])
                if gaps:
                    typer.echo(f"\n   ⚠️ 检测到 {len(gaps)} 个数据缺口:")
                    for gap in gaps[:5]:  # 只显示前5个
                        typer.echo(f"      {gap['start']} ~ {gap['end']} (缺失 {gap['missing_count']} 条)")

        elif key == 'validity':
            issues = detail.get('issues', {})
            issue_details = detail.get('issue_details', [])

            total_issues = sum(issues.values()) if isinstance(issues, dict) else 0
            if total_issues > 0:
                typer.echo(f"   发现 {total_issues} 个问题:")
                for issue in issue_details:
                    typer.echo(f"      • {issue['type']}: {issue.get('count', 0)} 条记录")

        elif key == 'uniqueness':
            dup_count = detail.get('duplicate_count', 0)
            if dup_count > 0:
                typer.echo(f"   重复记录: {dup_count}")
                if verbose:
                    dup_ts = detail.get('duplicate_timestamps', [])[:5]
                    typer.echo(f"   示例时间戳: {dup_ts}")

    typer.echo(f"\n{'='*60}\n")


@quality_app.command("check")
def quality_check(
    symbol: Annotated[str, typer.Option("-s", "--symbol")],
    interval: Annotated[str, typer.Option("-i", "--interval")],
    candle_type: Annotated[str, typer.Option("--candle-type")] = "spot",
    start: Annotated[Optional[str], typer.Option("--start")] = None,
    end: Annotated[Optional[str], typer.Option("--end")] = None,
    verbose: Annotated[bool, typer.Option("-v/--verbose")] = False,
):
    """
    检查K线数据质量

    示例:
      # 检查BTCUSDT的15分钟数据质量
      python data_cli.py quality check -s BTCUSDT -i 15m

      # 详细模式（显示缺口详情）
      python data_cli.py quality check -s ETHUSDT -i 1h -v

      # 检查指定时间范围的数据
      python data_cli.py quality check -s BTCUSDT -i 1d --start 2024-01-01 --end 2024-12-31
    """
    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        typer.echo(f"\n{'='*60}")
        typer.echo(f"📊 K线数据质量检查报告")
        typer.echo(f"{'='*60}")
        typer.echo(f"交易对: {symbol}")
        typer.echo(f"时间周期: {interval}")
        typer.echo(f"市场类型: {candle_type}")
        typer.echo(f"{'='*60}\n")

        result = service.check_quality(symbol, interval, candle_type, start, end)

        if result.get('status') == 'error':
            typer.echo(f"❌ 错误: {result.get('message', '未知错误')}", err=True)
            raise typer.Exit(1)
        elif result.get('status') == 'empty':
            typer.echo(f"⚠️ 提示: {result.get('message', '未找到数据')}")
            return

        _print_quality_report(result, verbose)

    except FileNotFoundError as e:
        typer.echo(f"❌ 错误: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        logger.exception(f"检查数据质量时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@quality_app.command("options")
def quality_options(
    candle_type: Annotated[str, typer.Option("--candle-type")] = "spot",
):
    """
    列出可用的数据选项（交易对和时间周期）

    示例:
      # 列出现货市场的所有选项
      python data_cli.py quality options --candle-type spot

      # 列出合约市场的所有选项
      python data_cli.py quality options --candle-type future
    """
    try:
        from quality.parquet_provider import ParquetDataProvider

        provider = ParquetDataProvider()

        symbols = provider.list_available_symbols(candle_type=candle_type)

        if not symbols:
            typer.echo(f"未找到任何{candle_type} Parquet 数据")
            typer.echo("提示: 请先使用 download 命令下载数据")
            return

        typer.echo(f"\n可用的{candle_type}交易对 (共 {len(symbols)} 个):")
        typer.echo(f"{'='*60}")

        for sym in symbols[:30]:
            intervals = ", ".join(sym['intervals'][:6])
            typer.echo(f"  {sym['symbol']:<12} | 周期: [{intervals}]")

        if len(symbols) > 30:
            typer.echo(f"\n  ... 还有 {len(symbols) - 30} 个交易对未显示")

        typer.echo(f"{'='*60}\n")

    except Exception as e:
        logger.exception(f"列出可用选项时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@quality_app.command("batch")
def quality_batch(
    interval: Annotated[str, typer.Option("-i", "--interval")] = "1h",
    candle_type: Annotated[str, typer.Option("--candle-type")] = "spot",
    limit: Annotated[int, typer.Option("--limit", "-l")] = 50,
):
    """
    批量检查所有交易对的数据质量

    示例:
      # 批量检查所有交易对的1小时数据（默认前50个）
      python data_cli.py quality batch -i 1h

      # 批量检查前20个交易对的15分钟数据
      python data_cli.py quality batch -i 15m --limit 20

      # 批量检查合约数据
      python data_cli.py quality batch -i 4h --candle-type future --limit 10
    """
    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        symbols = provider.list_available_symbols(candle_type=candle_type)[:limit]

        if not symbols:
            typer.echo(f"未找到任何{candle_type} Parquet 数据")
            return

        typer.echo(f"\n{'='*90}")
        typer.echo(f"批量数据质量检查结果 ({len(symbols)} 个交易对)")
        typer.echo(f"{'='*90}")
        typer.echo(
            f"{'交易对':<12} {'周期':<6} {'行数':>10} "
            f"{'覆盖率':>8} {'评分':>6} {'等级':>4} {'状态':<8}"
        )
        typer.echo("-" * 90)

        passed_count = 0
        warning_count = 0
        failed_count = 0

        for sym_info in symbols:
            sym = sym_info['symbol']

            # 只检查有指定周期的
            if interval not in sym_info['intervals']:
                continue

            try:
                result = service.check_quality(sym, interval, candle_type)
                summary = result.get('summary', {})
                continuity = result.get('details', {}).get('continuity', {})

                coverage = continuity.get('coverage_ratio', 0) * 100
                score = summary.get('score', 0)
                grade = summary.get('grade', '-')
                status = summary.get('status', 'unknown')

                status_icon = {'good': '✓', 'warning': '⚠️', 'bad': '✗'}.get(status, '?')

                # 统计各状态数量
                if status == 'good':
                    passed_count += 1
                elif status == 'warning':
                    warning_count += 1
                else:
                    failed_count += 1

                typer.echo(
                    f"{sym:<12} "
                    f"{interval:<6} "
                    f"{result.get('total_records', 0):>10,} "
                    f"{coverage:>7.1f}% "
                    f"{score:>5.1f} "
                    f"{grade:>4} "
                    f"{status_icon:<8}"
                )
            except Exception as e:
                typer.echo(f"{sym:<12} {interval:<6} 错误: {str(e)[:50]}")

        typer.echo(f"\n{'='*90}")
        typer.echo(f"统计: ✅ 通过 {passed_count} | ⚠️ 警告 {warning_count} | ❌ 失败 {failed_count}")
        typer.echo(f"{'='*90}\n")

    except Exception as e:
        logger.exception(f"批量检查时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@quality_app.command("duplicates")
def quality_duplicates(
    symbol: Annotated[str, typer.Option("-s", "--symbol")],
    interval: Annotated[str, typer.Option("-i", "--interval")],
    candle_type: Annotated[str, typer.Option("--candle-type")] = "spot",
    start: Annotated[Optional[str], typer.Option("--start")] = None,
    end: Annotated[Optional[str], typer.Option("--end")] = None,
):
    """
    查看K线数据的重复记录详情

    示例:
      # 查看BTCUSDT的1小时数据的重复记录
      python data_cli.py quality duplicates -s BTCUSDT -i 1h

      # 查看指定时间范围的重复记录
      python data_cli.py quality duplicates -s ETHUSDT -i 15m --start 2024-01-01
    """
    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        df = provider.get_kline_data(symbol, interval, candle_type, start, end)
        result = service.check_uniqueness(df)

        typer.echo(f"\n{'='*60}")
        typer.echo(f"🔄 重复记录检查结果")
        typer.echo(f"{'='*60}")
        typer.echo(f"交易对: {symbol}")
        typer.echo(f"时间周期: {interval}")
        typer.echo(f"总记录数: {len(df):,}")
        typer.echo(f"{'='*60}\n")

        if result['status'] == 'pass':
            typer.echo("✅ 未发现重复记录")
        else:
            typer.echo(f"❌ 发现 {result['duplicate_count']} 条重复记录")
            typer.echo(f"\n示例重复时间戳（前10个）:")
            for ts in result['duplicate_timestamps'][:10]:
                typer.echo(f"  • {ts}")

            typer.echo(f"\n💡 提示: 使用 'quality resolve' 命令处理重复记录")
            typer.echo(f"   python data_cli.py quality resolve -s {symbol} -i {interval} --strategy keep_first")

        typer.echo(f"\n{'='*60}\n")

    except FileNotFoundError as e:
        typer.echo(f"❌ 错误: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        logger.exception(f"查看重复记录时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


@quality_app.command("resolve")
def quality_resolve(
    symbol: Annotated[str, typer.Option("-s", "--symbol")],
    interval: Annotated[str, typer.Option("-i", "--interval")],
    strategy: Annotated[str, typer.Option("--strategy")] = "keep_first",
    candle_type: Annotated[str, typer.Option("--candle-type")] = "spot",
    dry_run: Annotated[bool, typer.Option("--dry-run/-n", help="仅预览不实际执行")] = False,
):
    """
    处理K线重复记录

    策略说明：
      - keep_first: 保留第一条记录（默认）
      - keep_last: 保留最后一条记录
      - keep_max_volume: 保留成交量最大的记录
      - keep_min_volume: 保留成交量最小的记录

    示例:
      # 预览将删除多少条重复记录（不实际执行）
      python data_cli.py quality resolve -s BTCUSDT -i 1h --dry-run

      # 使用保留第一条策略处理重复记录
      python data_cli.py quality resolve -s BTCUSDT -i 1h --strategy keep_first

      # 使用保留最大成交量策略处理重复记录
      python data_cli.py quality resolve -s ETHUSDT -i 15m --strategy keep_max_volume
    """
    try:
        from quality.kline_quality_service import KlineQualityService
        from quality.parquet_provider import ParquetDataProvider

        provider = ParquetDataProvider()
        service = KlineQualityService(provider)

        typer.echo(f"\n{'='*60}")
        typer.echo(f"🔄 处理重复记录")
        typer.echo(f"{'='*60}")
        typer.echo(f"交易对: {symbol}")
        typer.echo(f"时间周期: {interval}")
        typer.echo(f"处理策略: {strategy}")
        typer.echo(f"预览模式: {'是' if dry_run else '否'}")
        typer.echo(f"{'='*60}\n")

        result = service.resolve_duplicates(
            symbol=symbol,
            interval=interval,
            candle_type=candle_type,
            strategy=strategy,
            dry_run=dry_run
        )

        if result['status'] == 'success':
            typer.echo(f"✅ 处理完成!")
            typer.echo(f"   原始记录数: {result.get('original_count', 0):,}")
            typer.echo(f"   剩余记录数: {result.get('remaining_count', 0):,}")
            typer.echo(f"   删除记录数: {result.get('removed_count', 0):,}")

            if not dry_run and 'backup_path' in result:
                typer.echo(f"   备份文件: {result['backup_path']}")
                typer.echo(f"\n💡 如需恢复，可从备份文件还原")
        elif result['status'] == 'preview':
            typer.echo(f"📋 预览结果:")
            typer.echo(f"   原始记录数: {result.get('original_count', 0):,}")
            typer.echo(f"   将保留记录: {result.get('remaining_count', 0):,}")
            typer.echo(f"   将删除记录: {result.get('removed_count', 0):,}")
            typer.echo(f"\n💡 这是预览模式，如需实际执行，请去掉 --dry-run 参数")
        elif result['status'] == 'warning':
            typer.echo(f"⚠️ {result.get('message', '没有操作')}")
        else:
            typer.echo(f"❌ 错误: {result.get('message', '未知错误')}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\n{'='*60}\n")

    except FileNotFoundError as e:
        typer.echo(f"❌ 错误: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        logger.exception(f"处理重复记录时发生错误: {e}")
        typer.echo(f"错误: {e}", err=True)
        raise typer.Exit(1)


# ========== 归档数据 (Binance 历史 tick/K 线) 子命令 ==========

# 创建归档数据子命令
archive_app = typer.Typer(help="Binance 历史归档数据 (7 种 × 3 个市场) 下载与管理")


def _split_symbols(raw: str) -> List[str]:
    """把 'BTCUSDT,ETHUSDT' 拆成 ['BTCUSDT', 'ETHUSDT']."""
    return [s.strip() for s in raw.split(',') if s.strip()]


@archive_app.command("download")
def archive_download(
    kind: Annotated[str, typer.Option("--kind", "-k", help="数据种类: aggTrades/trades/bookDepth/bookTicker/markPriceKlines/indexPriceKlines/premiumIndexKlines")],
    market: Annotated[str, typer.Option("--market", "-m", help="市场: spot/um/cm")],
    symbols: Annotated[str, typer.Option("--symbols", "-s", help="交易对列表, 逗号分隔, 例如 BTCUSDT,ETHUSDT")],
    start: Annotated[str, typer.Option("--start", help="起始日期 YYYY-MM-DD")],
    end: Annotated[str, typer.Option("--end", help="结束日期 YYYY-MM-DD")],
    mode: Annotated[str, typer.Option("--mode", help="下载模式: inc (增量) / full (全量)")] = "inc",
    interval: Annotated[Optional[str], typer.Option("--interval", "-i", help="K 线类需要: 1m/3m/5m/15m/30m/1h/2h/1d")] = None,
):
    """
    创建 Binance 历史归档下载任务 (后台异步执行)。

    示例:
      # 下载 spot/aggTrades
      quantcell data archive download -k aggTrades -m spot -s BTCUSDT,ETHUSDT --start 2024-12-01 --end 2024-12-02

      # 下载 um/markPriceKlines (1h)
      quantcell data archive download -k markPriceKlines -m um -s BTCUSDT --start 2024-12-01 --end 2024-12-02 --interval 1h
    """
    try:
        from collector.config import get_archive_base_dir, get_binance_proxy
        from collector.services.archive_service import ArchiveService
        from exchange.binance.archive.kinds import ArchiveKind, MarketType

        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        typer.echo(f"❌ 错误: {exc}", err=True)
        raise typer.Exit(1)

    symbol_list = _split_symbols(symbols)
    if not symbol_list:
        typer.echo("❌ 错误: --symbols 不能为空", err=True)
        raise typer.Exit(1)

    if mode not in ("inc", "full"):
        typer.echo("❌ 错误: --mode 必须是 inc 或 full", err=True)
        raise typer.Exit(1)

    svc = ArchiveService(
        base_dir=get_archive_base_dir(),
        proxy=get_binance_proxy(),
    )
    try:
        task_id = svc.create_download_task(
            symbols=symbol_list,
            kind=kind_e,
            market=market_e,
            start_date=start,
            end_date=end,
            mode=mode,
            interval=interval,
        )
    except ValueError as exc:
        typer.echo(f"❌ 错误: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"✓ 归档下载任务已创建")
    typer.echo(f"  task_id   : {task_id}")
    typer.echo(f"  kind      : {kind_e.value}")
    typer.echo(f"  market    : {market_e.value}")
    typer.echo(f"  symbols   : {', '.join(symbol_list)}")
    typer.echo(f"  日期范围  : {start} ~ {end}")
    typer.echo(f"  mode      : {mode}")
    if interval:
        typer.echo(f"  interval  : {interval}")
    typer.echo(f"  base_dir  : {svc.base_dir}")
    typer.echo("")
    typer.echo(f"查询进度: quantcell data archive list-tasks")


@archive_app.command("list")
def archive_list(
    kind: Annotated[str, typer.Option("--kind", "-k", help="数据种类: aggTrades/trades/...")],
    market: Annotated[str, typer.Option("--market", "-m", help="市场: spot/um/cm")],
):
    """
    列出 (kind, market) 下已采集到本地的交易对。

    示例:
      quantcell data archive list -k aggTrades -m spot
    """
    try:
        from collector.config import get_archive_base_dir, get_binance_proxy
        from collector.services.archive_service import ArchiveService
        from exchange.binance.archive.kinds import ArchiveKind, MarketType

        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        typer.echo(f"❌ 错误: {exc}", err=True)
        raise typer.Exit(1)

    svc = ArchiveService(
        base_dir=get_archive_base_dir(),
        proxy=get_binance_proxy(),
    )
    symbols = svc.list_symbols(kind_e, market_e)

    typer.echo(f"已采集 {kind_e.value}/{market_e.value}: {len(symbols)} 个交易对")
    typer.echo(f"base_dir: {svc.base_dir}")
    typer.echo("-" * 60)
    if not symbols:
        typer.echo("  (无)")
        return
    # 每行 6 个, 紧凑展示
    for i in range(0, len(symbols), 6):
        typer.echo("  " + "  ".join(f"{s:12}" for s in symbols[i:i + 6]))


@archive_app.command("meta")
def archive_meta(
    kind: Annotated[str, typer.Option("--kind", "-k", help="数据种类")],
    market: Annotated[str, typer.Option("--market", "-m", help="市场")],
    symbol: Annotated[str, typer.Option("--symbol", "-s", help="交易对, 例如 BTCUSDT")],
):
    """
    读取某 (kind, market, symbol) 的 _meta.json。

    示例:
      quantcell data archive meta -k aggTrades -m spot -s BTCUSDT
    """
    try:
        from collector.config import get_archive_base_dir, get_binance_proxy
        from collector.services.archive_service import ArchiveService
        from exchange.binance.archive.kinds import ArchiveKind, MarketType

        kind_e = ArchiveKind(kind)
        market_e = MarketType(market)
    except ValueError as exc:
        typer.echo(f"❌ 错误: {exc}", err=True)
        raise typer.Exit(1)

    svc = ArchiveService(
        base_dir=get_archive_base_dir(),
        proxy=get_binance_proxy(),
    )
    meta = svc.get_meta(kind_e, market_e, symbol)
    typer.echo(f"{kind_e.value}/{market_e.value}/{symbol} 的元数据:")
    typer.echo("-" * 60)
    if not meta:
        typer.echo("  (无 _meta.json)")
        return
    import json as _json
    typer.echo(_json.dumps(meta, ensure_ascii=False, indent=2))


# 注册归档数据子命令
app.add_typer(archive_app, name="archive", help="Binance 历史归档数据 (7 种 × 3 个市场)")


if __name__ == "__main__":
    app()
