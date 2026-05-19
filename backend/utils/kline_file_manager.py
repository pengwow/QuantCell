# -*- coding: utf-8 -*-
"""
K线数据文件管理器

提供统一的K线数据文件管理功能：
- 按品种、周期、市场类型组织Parquet文件
- 支持保存、加载、追加、查询操作
- 自动处理文件路径和数据格式转换
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import fcntl  # 文件锁
from utils.logger import get_logger, LogType
from utils.parquet_utils import save_to_parquet, load_from_parquet, append_to_parquet

logger = get_logger(__name__, LogType.APPLICATION)


class KlineFileManager:
    """
    K线数据文件管理器
    
    管理K线数据的Parquet文件存储，支持现货和合约两种市场类型。
    数据按照以下目录结构组织：
    
    base_dir (data/source)
    ├── crypto/
    │   ├── spot/
    │   │   └── klines/
    │   │       └── {symbol}/
    │   │           └── {interval}/
    │   │               └── {YYYY-MM}.parquet
    │   └── future/
    │       └── klines/
    ├── stock/  (预留)
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        初始化文件管理器
        
        Args:
            base_dir: 基础目录路径，默认为 backend/data/source
        """
        if base_dir is None:
            self.base_dir = Path(__file__).parent.parent / 'data' / 'source'
        else:
            self.base_dir = Path(base_dir)
        
        logger.info(f"[KlineFileManager] 初始化完成，基础目录: {self.base_dir}")
    
    def _get_file_path(
        self,
        symbol: str,
        interval: str,
        date_str: str,
        market_type: str = 'spot'
    ) -> Path:
        """
        获取Parquet文件的完整路径
        
        Args:
            symbol: 交易对符号 (如 "BTCUSDT")
            interval: 时间周期 (如 "1h", "15m")
            date_str: 日期字符串 (如 "2024-01")
            market_type: 市场类型 ("spot" 或 "future")
            
        Returns:
            Path: 文件完整路径
        """
        return (
            self.base_dir
            / 'crypto'
            / market_type
            / 'klines'
            / symbol
            / interval
            / f"{date_str}.parquet"
        )
    
    def _extract_date_from_timestamp(self, timestamp: int) -> str:
        """
        从时间戳提取年月字符串
        自动检测时间戳单位（纳秒/毫秒/秒）

        Args:
            timestamp: 时间戳（支持纳秒、毫秒、秒）

        Returns:
            str: 格式化的日期字符串 (YYYY-MM)
        """
        # 自动检测时间戳单位
        if timestamp > 1e15:  # 纳秒 (19位，如 1764547200000000000)
            ts_seconds = timestamp / 1_000_000_000
        elif timestamp > 1e12:  # 毫秒 (13位，如 1764547200000)
            ts_seconds = timestamp / 1000
        else:  # 秒 (10位，如 1764547200)
            ts_seconds = timestamp

        dt = datetime.fromtimestamp(ts_seconds)
        return dt.strftime('%Y-%m')
    
    def _ensure_dataframe_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        确保DataFrame格式符合规范
        
        Args:
            df: 输入的DataFrame
            
        Returns:
            pd.DataFrame: 格式化后的DataFrame
        """
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"DataFrame缺少必需列: {required_cols}")
        
        # 确保数值列类型正确
        for col in required_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 处理时间戳
        if 'timestamp' not in df.columns and 'datetime' in df.columns:
            df['timestamp'] = pd.to_datetime(df['datetime']).astype('int64') // 10**6
        
        return df
    
    def save_klines(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> bool:
        """
        保存K线数据到Parquet文件
        
        自动根据数据的时间范围分割成月度文件。
        
        Args:
            df: K线数据DataFrame
            symbol: 交易对符号
            interval: 时间周期
            market_type: 市场类型
            
        Returns:
            bool: 是否保存成功
        """
        try:
            if df is None or df.empty:
                logger.warning("[KlineFileManager] 数据为空，跳过保存")
                return False
            
            # 格式化数据
            df = self._ensure_dataframe_format(df.copy())
            
            # 按月份分组保存
            if 'timestamp' in df.columns:
                df['_month'] = df['timestamp'].apply(self._extract_date_from_timestamp)
                
                success_count = 0
                for month, group in df.groupby('_month'):
                    file_path = self._get_file_path(symbol, interval, month, market_type)
                    
                    # 使用文件锁确保并发安全
                    lock_path = file_path.parent / '.lock'
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(lock_path, 'w') as lock_file:
                        try:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                            
                            group_to_save = group.drop(columns=['_month'])
                            if save_to_parquet(group_to_save, file_path):
                                success_count += 1
                                logger.debug(f"[KlineFileManager] 已保存: {file_path.name} ({len(group)}条)")
                        finally:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                
                logger.info(
                    f"[KlineFileManager] 保存成功: {symbol} {interval}, "
                    f"共{len(df)}条数据, 分{success_count}个文件"
                )
                return success_count > 0
            
            else:
                # 无时间戳，保存到默认文件
                file_path = self._get_file_path(symbol, interval, 'unknown', market_type)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                return save_to_parquet(df, file_path)
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 保存失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def load_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        market_type: str = 'spot'
    ) -> pd.DataFrame:
        """
        加载K线数据
        
        支持按时间范围过滤，自动加载相关月份的文件。
        
        Args:
            symbol: 交易对符号
            interval: 时间周期
            start_time: 开始时间 (ISO格式或毫秒时间戳)
            end_time: 结束时间
            market_type: 市场类型
            
        Returns:
            pd.DataFrame: K线数据
        """
        try:
            data_dir = self.base_dir / 'crypto' / market_type / 'klines' / symbol / interval
            
            if not data_dir.exists():
                logger.warning(f"[KlineFileManager] 目录不存在: {data_dir}")
                return pd.DataFrame()
            
            # 获取所有Parquet文件并排序
            parquet_files = sorted(data_dir.glob('*.parquet'))
            
            if not parquet_files:
                logger.warning(f"[KlineFileManager] 未找到数据文件: {data_dir}")
                return pd.DataFrame()
            
            # 如果有时间范围限制，筛选相关文件
            if start_time or end_time:
                filtered_files = []
                
                # 解析开始时间的月份
                start_month = None
                if start_time:
                    if isinstance(start_time, str) and len(start_time) >= 7:
                        start_month = start_time[:7]
                
                # 解析结束时间的月份
                end_month = None
                if end_time:
                    if isinstance(end_time, str) and len(end_time) >= 7:
                        end_month = end_time[:7]
                
                for pf in parquet_files:
                    file_month = pf.stem  # YYYY-MM
                    
                    if start_month and file_month < start_month:
                        continue
                    if end_month and file_month > end_month:
                        continue
                    
                    filtered_files.append(pf)
                
                parquet_files = filtered_files
            
            # 加载数据
            dfs = []
            for pf in parquet_files:
                try:
                    df = load_from_parquet(pf)
                    if not df.empty:
                        dfs.append(df)
                except Exception as e:
                    logger.warning(f"[KlineFileManager] 加载文件失败 {pf}: {e}")
                    continue
            
            if not dfs:
                return pd.DataFrame()
            
            # 合并所有数据
            combined_df = pd.concat(dfs, ignore_index=True)
            
            # 按时间排序并去重
            if 'timestamp' in combined_df.columns:
                combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
                
                # 按时间戳去重（保留最后一条）
                combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='last')
                
                # 应用时间范围过滤
                if start_time:
                    if isinstance(start_time, str) and ('T' in start_time or '-' in start_time):
                        try:
                            start_ts = int(datetime.fromisoformat(start_time).timestamp() * 1000)
                        except (ValueError, AttributeError):
                            start_ts = int(float(start_time))
                    else:
                        start_ts = int(float(start_time))
                    combined_df = combined_df[combined_df['timestamp'] >= start_ts]
                
                if end_time:
                    if isinstance(end_time, str) and ('T' in end_time or '-' in end_time):
                        try:
                            end_ts = int(datetime.fromisoformat(end_time).timestamp() * 1000)
                        except (ValueError, AttributeError):
                            end_ts = int(float(end_time))
                    else:
                        end_ts = int(float(end_time))
                    combined_df = combined_df[combined_df['timestamp'] <= end_ts]
            
            logger.info(
                f"[KlineFileManager] 加载成功: {symbol} {interval}, "
                f"共{len(combined_df)}条数据"
            )
            
            return combined_df
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 加载失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return pd.DataFrame()
    
    def append_klines(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> bool:
        """
        追加K线数据到现有文件
        
        Args:
            df: 要追加的数据
            symbol: 交易对符号
            interval: 时间周期
            market_type: 市场类型
            
        Returns:
            bool: 是否成功
        """
        try:
            if df is None or df.empty:
                logger.warning("[KlineFileManager] 追加数据为空")
                return False
            
            df = self._ensure_dataframe_format(df.copy())
            
            # 按月份分别追加
            if 'timestamp' in df.columns:
                df['_month'] = df['timestamp'].apply(self._extract_date_from_timestamp)
                
                for month, group in df.groupby('_month'):
                    file_path = self._get_file_path(symbol, interval, month, market_type)
                    
                    # 确保目录存在
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    group_to_save = group.drop(columns=['_month'])
                    
                    if append_to_parquet(group_to_save, file_path):
                        logger.info(f"[KlineFileManager] 追加成功: {file_path.name} ({len(group)}条)")
            
            return True
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 追加失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def get_available_symbols(self, market_type: str = 'spot') -> List[str]:
        """
        获取可用的交易对列表
        
        Args:
            market_type: 市场类型
            
        Returns:
            List[str]: 交易对符号列表
        """
        market_dir = self.base_dir / 'crypto' / market_type / 'klines'
        
        if not market_dir.exists():
            return []
        
        symbols = []
        for symbol_dir in market_dir.iterdir():
            if symbol_dir.is_dir() and any(symbol_dir.glob('*/*.parquet')):
                symbols.append(symbol_dir.name)
        
        return sorted(symbols)
    
    def get_available_intervals(self, symbol: str, market_type: str = 'spot') -> List[str]:
        """
        获取指定交易对的可用周期列表
        
        Args:
            symbol: 交易对符号
            market_type: 市场类型
            
        Returns:
            List[str]: 周期列表
        """
        symbol_dir = self.base_dir / 'crypto' / market_type / 'klines' / symbol
        
        if not symbol_dir.exists():
            return []
        
        intervals = []
        for interval_dir in symbol_dir.iterdir():
            if interval_dir.is_dir() and list(interval_dir.glob('*.parquet')):
                intervals.append(interval_dir.name)
        
        return sorted(intervals)
    
    def get_date_range(
        self,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> tuple:
        """
        获取数据的日期范围
        
        Args:
            symbol: 交易对符号
            interval: 周期
            market_type: 市场类型
            
        Returns:
            tuple: (最早日期, 最晚日期) 或 None
        """
        data_dir = self.base_dir / 'crypto' / market_type / 'klines' / symbol / interval

        if not data_dir.exists():
            return None
        
        files = sorted(data_dir.glob('*.parquet'))
        
        if not files:
            return None
        
        earliest = files[0].stem  # YYYY-MM
        latest = files[-1].stem
        
        return (earliest, latest)
    
    def delete_klines(
        self,
        symbol: str,
        interval: str,
        market_type: str = 'spot'
    ) -> bool:
        """
        删除指定交易对的K线数据
        
        Args:
            symbol: 交易对符号
            interval: 周期
            market_type: 市场类型
            
        Returns:
            bool: 是否成功
        """
        try:
            target_dir = self.base_dir / 'crypto' / market_type / 'klines' / symbol / interval
            
            if not target_dir.exists():
                logger.warning(f"[KlineFileManager] 目录不存在: {target_dir}")
                return False
            
            import shutil
            shutil.rmtree(target_dir)
            
            logger.info(f"[KlineFileManager] 已删除: {target_dir}")
            return True
            
        except Exception as e:
            logger.error(f"[KlineFileManager] 删除失败: {e}")
            return False
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            dict: 统计信息
        """
        stats = {
            'total_files': 0,
            'total_size_mb': 0.0,
            'symbols': {},
            'base_dir': str(self.base_dir),
            'exists': self.base_dir.exists()
        }
        
        if not self.base_dir.exists():
            return stats
        
        for market_type in ['spot', 'future']:
            market_dir = self.base_dir / 'crypto' / market_type / 'klines'
            
            if not market_dir.exists():
                continue
            
            for symbol_dir in market_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                
                symbol_stats = {
                    'intervals': {},
                    'total_size_mb': 0.0,
                    'total_files': 0
                }
                
                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue
                    
                    files = list(interval_dir.glob('*.parquet'))
                    interval_stats = {
                        'file_count': len(files),
                        'size_mb': sum(f.stat().st_size for f in files) / (1024 * 1024),
                        'date_range': None
                    }
                    
                    if files:
                        dates = sorted([f.stem for f in files])
                        interval_stats['date_range'] = (dates[0], dates[-1])
                    
                    symbol_stats['intervals'][interval_dir.name] = interval_stats
                    symbol_stats['total_size_mb'] += interval_stats['size_mb']
                    symbol_stats['total_files'] += interval_stats['file_count']
                
                stats['symbols'][symbol_dir.name] = symbol_stats
                stats['total_files'] += symbol_stats['total_files']
                stats['total_size_mb'] += symbol_stats['total_size_mb']
        
        stats['total_size_mb'] = round(stats['total_size_mb'], 2)
        
        return stats


# 全局单例实例
_kline_manager_instance = None

def get_kline_file_manager() -> KlineFileManager:
    """获取全局KlineFileManager实例"""
    global _kline_manager_instance
    if _kline_manager_instance is None:
        _kline_manager_instance = KlineFileManager()
    return _kline_manager_instance
