# -*- coding: utf-8 -*-
"""
Parquet 文件读写工具函数

提供 K线 数据的 Parquet 格式存储功能，包括：
- DataFrame 到 Parquet 的保存
- 从 Parquet 加载数据
- CSV 到 Parquet 的格式转换
- Parquet 文件元信息查询
"""

import os

import pandas as pd
from pathlib import Path
from typing import Optional, List
from utils.logger import get_logger, LogType


logger = get_logger(__name__, LogType.APPLICATION)


def save_to_parquet(
    df: pd.DataFrame,
    file_path: Path,
    compression: str = 'snappy'
) -> bool:
    """
    将 DataFrame 保存为 Parquet 格式

    Args:
        df: K线数据 DataFrame
        file_path: 目标文件路径（.parquet 后缀）
        compression: 压缩算法，可选 'snappy', 'gzip', 'zstd'

    Returns:
        bool: 是否保存成功
    """
    try:
        if df is None or df.empty:
            logger.warning(f"数据为空，跳过保存: {file_path}")
            return False
        
        # 确保数据类型正确
        df = _optimize_dtypes(df.copy())

        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入临时文件，再原子性重命名（防止写入中断导致文件损坏）
        temp_path = file_path.with_suffix('.tmp')
        df.to_parquet(
            temp_path,
            engine='pyarrow',
            compression=compression,
            index=False
        )
        
        # 原子性重命名
        if file_path.exists():
            file_path.unlink()
        temp_path.rename(file_path)

        logger.info(f"成功保存 Parquet 文件: {file_path} ({len(df)} 行)")
        return True

    except Exception as e:
        logger.error(f"保存 Parquet 文件失败: {e}")
        # 清理临时文件
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        return False


def load_from_parquet(
    file_path: Path,
    columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    从 Parquet 文件加载数据

    Args:
        file_path: Parquet 文件路径
        columns: 可选，指定加载的列（提升性能）

    Returns:
        pd.DataFrame: K线数据
    """
    if not file_path.exists():
        logger.warning(f"Parquet 文件不存在: {file_path}")
        return pd.DataFrame()

    try:
        df = pd.read_parquet(
            file_path,
            engine='pyarrow',
            columns=columns
        )
        logger.debug(f"成功加载 Parquet 文件: {file_path} ({len(df)} 行)")
        return df

    except Exception as e:
        logger.error(f"读取 Parquet 文件失败: {e}")
        return pd.DataFrame()


def append_to_parquet(
    df: pd.DataFrame,
    file_path: Path,
    compression: str = 'snappy'
) -> bool:
    """
    追加数据到 Parquet 文件（读取-合并-重写策略）

    由于 Parquet 不支持直接追加，采用以下策略：
    1. 如果文件不存在，直接创建新文件
    2. 如果文件已存在，读取现有数据 → 合并 → 去重 → 重写

    Args:
        df: 要追加的 DataFrame
        file_path: 目标文件路径
        compression: 压缩算法

    Returns:
        bool: 是否成功
    """
    try:
        if df is None or df.empty:
            logger.warning("数据为空，跳过追加")
            return False

        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.exists():
            # 读取现有数据
            existing_df = load_from_parquet(file_path)
            
            if not existing_df.empty:
                # 合并数据
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                
                # 按时间戳去重（保留最新的）
                if 'timestamp' in combined_df.columns:
                    combined_df = combined_df.drop_duplicates(
                        subset=['timestamp'], 
                        keep='last'
                    ).sort_values('timestamp').reset_index(drop=True)
                
                logger.info(f"追加数据: {len(df)} 行 (合并后共 {len(combined_df)} 行)")
                return save_to_parquet(combined_df, file_path, compression)
        
        # 文件不存在或为空，直接保存
        return save_to_parquet(df, file_path, compression)

    except Exception as e:
        logger.error(f"追加数据到 Parquet 失败: {e}")
        return False


def _optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    优化 DataFrame 的数据类型，减少存储空间

    Args:
        df: 原始 DataFrame

    Returns:
        pd.DataFrame: 优化后的 DataFrame
    """
    # 确保数值列使用合适的数据类型
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 确保 timestamp 是整数
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce').astype('int64')
    
    # 确保 symbol 和 interval 是字符串类型
    string_cols = ['symbol', 'interval']
    for col in string_cols:
        if col in df.columns:
            df[col] = df[col].astype('string')

    return df


def convert_csv_to_parquet(csv_path: Path, parquet_path: Path = None) -> bool:
    """
    将 CSV 文件转换为 Parquet 格式（用于历史数据迁移）

    Args:
        csv_path: CSV 文件路径
        parquet_path: 输出 Parquet 路径，默认与 CSV 同名

    Returns:
        bool: 是否转换成功
    """
    if not csv_path.exists():
        logger.error(f"CSV 文件不存在: {csv_path}")
        return False
    
    if parquet_path is None:
        parquet_path = csv_path.with_suffix('.parquet')

    try:
        logger.info(f"开始转换 CSV → Parquet: {csv_path}")
        df = pd.read_csv(csv_path)
        success = save_to_parquet(df, parquet_path)
        
        if success:
            logger.info(f"转换成功: {parquet_path}")
        else:
            logger.error(f"转换失败: {csv_path}")
        
        return success

    except Exception as e:
        logger.error(f"CSV 转 Parquet 失败: {csv_path}, 错误: {e}")
        return False


def batch_convert_csv_to_parquet(
    directory: Path,
    pattern: str = "*.csv",
    delete_original: bool = False
) -> dict:
    """
    批量将目录下的 CSV 文件转换为 Parquet 格式

    Args:
        directory: 要转换的目录
        pattern: 文件匹配模式，默认 *.csv
        delete_original: 是否删除原始 CSV 文件

    Returns:
        dict: 转换统计信息 {
            'total': 总文件数,
            'success': 成功数,
            'failed': 失败数,
            'files': 转换结果列表
        }
    """
    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'files': []
    }

    csv_files = list(directory.glob(pattern))
    stats['total'] = len(csv_files)

    logger.info(f"开始批量转换: {directory}, 共 {stats['total']} 个 CSV 文件")

    for csv_file in csv_files:
        parquet_file = csv_file.with_suffix('.parquet')
        success = convert_csv_to_parquet(csv_file, parquet_file)

        result = {
            'csv': str(csv_file),
            'parquet': str(parquet_file),
            'success': success
        }
        stats['files'].append(result)

        if success:
            stats['success'] += 1
            
            # 可选：删除原始 CSV 文件
            if delete_original:
                csv_file.unlink()
                logger.info(f"已删除原始 CSV: {csv_file}")
        else:
            stats['failed'] += 1

    logger.info(f"批量转换完成: 成功 {stats['success']}/{stats['total']}, 失败 {stats['failed']}")
    return stats


def get_parquet_info(file_path: Path) -> dict:
    """
    获取 Parquet 文件的元信息

    Args:
        file_path: Parquet 文件路径

    Returns:
        dict: 包含行数、列数、大小等信息
    """
    if not file_path.exists():
        return {}

    try:
        # 使用 PyArrow 读取元数据（无需加载全部数据）
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(file_path)

        return {
            'num_rows': pf.metadata.num_rows,
            'num_columns': pf.metadata.num_columns,
            'file_size_bytes': os.path.getsize(file_path),
            'file_size_mb': round(os.path.getsize(file_path) / (1024 * 1024), 2),
            'created_at': pd.Timestamp.fromtimestamp(file_path.stat().st_ctime).isoformat(),
            'modified_at': pd.Timestamp.fromtimestamp(file_path.stat().st_mtime).isoformat(),
            'schema': str(pf.schema_arrow),
            'path': str(file_path)
        }

    except Exception as e:
        logger.error(f"获取 Parquet 文件信息失败: {e}")
        return {}


def load_kline_data_auto(file_path: Path) -> pd.DataFrame:
    """
    智能加载 K线 数据（自动识别 CSV 或 Parquet 格式）

    用于向后兼容，在过渡期同时支持两种格式

    Args:
        file_path: 数据文件路径（可以是 .csv 或 .parquet）

    Returns:
        pd.DataFrame: K线数据
    """
    # 直接匹配后缀
    if file_path.suffix == '.parquet':
        return load_from_parquet(file_path)
    elif file_path.suffix == '.csv':
        logger.warning(f"使用旧版 CSV 格式: {file_path}")
        try:
            return pd.read_csv(file_path)
        except Exception as e:
            logger.error(f"读取 CSV 文件失败: {e}")
            return pd.DataFrame()
    
    # 尝试自动检测格式
    parquet_path = file_path.with_suffix('.parquet')
    if parquet_path.exists():
        return load_from_parquet(parquet_path)

    csv_path = file_path.with_suffix('.csv')
    if csv_path.exists():
        logger.warning(f"使用旧版 CSV 格式: {csv_path}")
        try:
            return pd.read_csv(csv_path)
        except Exception as e:
            logger.error(f"读取 CSV 文件失败: {e}")
            return pd.DataFrame()

    logger.error(f"未找到数据文件: {file_path}")
    return pd.DataFrame()


def list_parquet_files(directory: Path, pattern: str = "*.parquet") -> List[Path]:
    """
    列出目录下所有 Parquet 文件

    Args:
        directory: 目录路径
        pattern: 文件匹配模式

    Returns:
        List[Path]: Parquet 文件列表
    """
    if not directory.exists():
        logger.warning(f"目录不存在: {directory}")
        return []

    return sorted(directory.glob(pattern))


def get_directory_stats(directory: Path) -> dict:
    """
    获取目录下所有 Parquet 文件的统计信息

    Args:
        directory: 目录路径

    Returns:
        dict: 统计信息 {
            'total_files': 文件数,
            'total_rows': 总行数,
            'total_size_mb': 总大小(MB),
            'files': 各文件信息列表
        }
    """
    files = list_parquet_files(directory)
    
    stats = {
        'total_files': len(files),
        'total_rows': 0,
        'total_size_mb': 0.0,
        'files': []
    }

    for file_path in files:
        info = get_parquet_info(file_path)
        if info:
            stats['total_rows'] += info.get('num_rows', 0)
            stats['total_size_mb'] += info.get('file_size_mb', 0)
            stats['files'].append(info)

    # 四舍五入总大小
    stats['total_size_mb'] = round(stats['total_size_mb'], 2)

    return stats
