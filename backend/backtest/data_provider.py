"""
回测数据提供者模块

从本地Parquet文件加载回测所需的K线数据，支持单品种和多品种批量加载。
为回测引擎提供统一的数据接口，替代原有的数据库查询和下载器逻辑。
"""

from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from utils.logger import get_logger, LogType
from utils.timestamp_utils import convert_to_datetime


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class DataDownloadResult:
    """数据下载/加载结果"""
    symbol: str
    timeframe: str
    success: bool = True
    failure_type: Optional[str] = None  # "no_data", "file_not_found", "parse_error"
    failure_reason: Optional[str] = None
    data: Optional[pd.DataFrame] = None
    warnings: List[str] = field(default_factory=list)
    is_incomplete: bool = False
    coverage_percent: float = 100.0


class BacktestDataProvider:
    """
    回测专用数据提供者
    
    从本地Parquet文件加载K线数据，支持：
    - 单品种K线数据加载
    - 多品种批量加载
    - 自动列名转换和时间戳处理
    - 数据完整性检查
    
    使用示例：
        provider = BacktestDataProvider()
        
        # 加载单个品种
        df = provider.load_klines("BTCUSDT", "1h")
        
        # 批量加载多品种
        data_dict, results = provider.load_multiple(
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["1h"]
        )
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        初始化数据提供者
        
        Args:
            base_dir: 数据根目录，默认使用 data_cli 的标准路径
        """
        if base_dir is None:
            from cli.data import get_source_data_dir
            base_dir = get_source_data_dir()
        
        self.base_dir = base_dir
        logger.info(f"[BacktestDataProvider] 初始化完成，数据目录: {base_dir}")
    
    def load_klines(
        self,
        symbol: str,
        interval: str,
        candle_type: str = "spot",
        start: Optional[str] = None,
        end: Optional[str] = None,
        normalize_columns: bool = True
    ) -> pd.DataFrame:
        """
        加载单个品种的K线数据
        
        Args:
            symbol: 交易对符号（如 BTCUSDT）
            interval: 时间周期（如 1m, 5m, 15m, 1h, 4h, 1d）
            candle_type: 市场类型 (spot/future)
            start: 开始时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
            end: 结束时间
            normalize_columns: 是否标准化列名为大写
            
        Returns:
            pd.DataFrame: K线数据，包含 Open/High/Low/Close/Volume 等列
            
        Raises:
            FileNotFoundError: 当Parquet文件不存在时
        """
        logger.info(f"[BacktestDataProvider] 开始加载: {symbol} {interval}")
        
        try:
            # 复用 data_cli 的工具函数查找文件
            from scripts.data_cli import _find_parquet_file, filter_by_date_range
            from utils.parquet_utils import load_from_parquet
            
            parquet_path = _find_parquet_file(symbol, interval, candle_type)
            
            if not parquet_path.exists():
                error_msg = f"未找到 {symbol} {interval} 的Parquet文件\n预期路径: {parquet_path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # 加载数据
            df = load_from_parquet(parquet_path)
            
            if df.empty:
                logger.warning(f"[BacktestDataProvider] 文件为空: {parquet_path}")
                return df
            
            # 应用时间范围筛选
            if not df.empty and (start or end):
                df = filter_by_date_range(df, start, end)
            
            # 标准化列名和数据格式
            if normalize_columns and not df.empty:
                df = self._normalize_dataframe(df)
            
            logger.info(
                f"[BacktestDataProvider] 加载成功: {symbol} {interval}, "
                f"共{len(df)}条记录"
            )
            
            return df
            
        except Exception as e:
            logger.error(f"[BacktestDataProvider] 加载失败: {e}")
            raise
    
    def load_multiple(
        self,
        symbols: List[str],
        timeframes: List[str],
        candle_type: str = "spot",
        time_range: Optional[str] = None,
        auto_download: bool = False,
        show_progress: bool = False
    ) -> Tuple[Dict[str, pd.DataFrame], List[DataDownloadResult]]:
        """
        批量加载多个品种的K线数据
        
        Args:
            symbols: 交易对符号列表
            timeframes: 时间周期列表
            candle_type: 市场类型 (spot/future)
            time_range: 时间范围字符串（YYYYMMDD-YYYYMMDD）
            auto_download: 是否自动下载缺失数据（当前版本不支持，保留参数兼容）
            show_progress: 是否显示进度条
            
        Returns:
            Tuple[Dict[str, pd.DataFrame], List[DataDownloadResult]]:
                - 成功加载数据字典: {"BTCUSDT_1h": DataFrame, ...}
                - 所有加载结果列表（包括失败的）
        """
        logger.info(
            f"[BacktestDataProvider] 批量加载开始: "
            f"{len(symbols)}个品种 x {len(timeframes)}个周期"
        )
        
        data_dict: Dict[str, pd.DataFrame] = {}
        download_results: List[DataDownloadResult] = []
        
        # 解析时间范围
        start_time = None
        end_time = None
        if time_range:
            try:
                from utils.validation import parse_time_range
                start_dt, end_dt = parse_time_range(time_range)
                start_time = start_dt.strftime('%Y-%m-%d')
                end_time = end_dt.strftime('%Y-%m-%d')
            except Exception as e:
                logger.warning(f"解析时间范围失败: {e}, 将不加时间筛选")
        
        total_tasks = len(symbols) * len(timeframes)
        current_task = 0
        
        for symbol in symbols:
            for timeframe in timeframes:
                current_task += 1
                
                if show_progress:
                    print(f"\r[{current_task}/{total_tasks}] 正在加载 {symbol} {timeframe}...", end="", flush=True)
                
                result = DataDownloadResult(
                    symbol=symbol,
                    timeframe=timeframe
                )
                
                try:
                    key = f"{symbol}_{timeframe}"
                    df = self.load_klines(
                        symbol=symbol,
                        interval=timeframe,
                        candle_type=candle_type,
                        start=start_time,
                        end=end_time
                    )
                    
                    if df.empty:
                        result.success = False
                        result.failure_type = "no_data"
                        result.failure_reason = "数据文件为空或无匹配记录"
                    else:
                        data_dict[key] = df
                        result.data = df
                        
                except FileNotFoundError as e:
                    result.success = False
                    result.failure_type = "file_not_found"
                    result.failure_reason = str(e)
                    
                    # 如果允许自动下载（当前版本暂不支持）
                    if auto_download:
                        result.warnings.append("自动下载功能将在未来版本支持")
                        
                except Exception as e:
                    result.success = False
                    result.failure_type = "parse_error"
                    result.failure_reason = str(e)
                    logger.exception(f"加载失败: {symbol} {timeframe}")
                
                download_results.append(result)
        
        if show_progress:
            success_count = sum(1 for r in download_results if r.success)
            fail_count = total_tasks - success_count
            print(f"\r[✓] 批量加载完成: {success_count}/{total_tasks} 个任务成功")

            # 🔍 增强错误信息：显示详细的失败原因
            if fail_count > 0:
                print("\n" + "="*60)
                print("⚠️  数据加载失败详情:")
                print("="*60)
                for result in download_results:
                    if not result.success:
                        print(f"  ❌ {result.symbol} {result.timeframe}")
                        print(f"     类型: {result.failure_type}")
                        print(f"     原因: {result.failure_reason}")
                        if hasattr(result, 'warnings') and result.warnings:
                            for warn in result.warnings:
                                print(f"     ⚠️  {warn}")
                print("="*60)
                print("\n💡 可能的原因：")
                print("   1. 本地没有该交易对/周期的数据文件")
                print("   2. 数据文件路径配置不正确")
                print("   3. 时间范围超出数据覆盖范围")
                print("\n🔧 解决方案：")
                print("   运行: uv run python scripts/data_cli.py list")
                print("   查看可用的数据文件列表\n")
        
        logger.info(
            f"[BacktestDataProvider] 批量加载完成: "
            f"成功{len(data_dict)}/{total_tasks}个"
        )
        
        return data_dict, download_results
    
    def list_available_symbols(self, candle_type="spot") -> List[Dict]:
        """
        列出所有可用的交易对
        
        Args:
            candle_type: 市场类型 (spot/future)
            
        Returns:
            List[Dict]: [{symbol: str, intervals: [str]}, ...]
        """
        try:
            from scripts.data_cli import scan_parquet_files
            
            files = scan_parquet_files(candle_type=candle_type)
            
            symbols_dict: Dict[str, Dict] = {}
            for f in files:
                sym = f['symbol']
                if sym not in symbols_dict:
                    symbols_dict[sym] = {'symbol': sym, 'intervals': []}
                if f['interval'] not in symbols_dict[sym]['intervals']:
                    symbols_dict[sym]['intervals'].append(f['interval'])
            
            return list(symbols_dict.values())
            
        except Exception as e:
            logger.error(f"[BacktestDataProvider] 列出可用品种失败: {e}")
            return []
    
    def get_available_intervals(self, symbol: str, candle_type: str = "spot") -> List[str]:
        """
        获取指定交易对的可用时间周期
        
        Args:
            symbol: 交易对符号
            candle_type: 市场类型
            
        Returns:
            List[str]: 如 ['1m', '5m', '15m', '1h', '4h', '1d']
        """
        try:
            from scripts.data_cli import scan_parquet_files
            
            files = scan_parquet_files(symbol=symbol, candle_type=candle_type)
            return sorted(set(f['interval'] for f in files))
            
        except Exception as e:
            logger.error(f"[BacktestDataProvider] 获取可用周期失败: {e}")
            return []

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化DataFrame格式
        
        处理内容：
        1. 列名转换：open→Open, high→High等
        2. 时间戳处理：设置datetime索引（自动检测精度）
        3. 数据类型确保：价格列为float64
        
        Args:
            df: 原始DataFrame
            
        Returns:
            pd.DataFrame: 标准化后的DataFrame
        """
        df = df.copy()
        
        # 列名映射（小写→标准格式）
        column_mapping = {
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        
        # 重命名列
        df.rename(columns=column_mapping, inplace=True)

        # 设置时间索引（使用统一的工具函数自动检测时间戳精度）
        if 'timestamp' in df.columns:
            if not isinstance(df.index, pd.DatetimeIndex):
                df.set_index('timestamp', inplace=True)
            df.index = convert_to_datetime(df.index)
        elif 'date' in df.columns:
            if not isinstance(df.index, pd.DatetimeIndex):
                df.set_index('date', inplace=True)
            df.index = convert_to_datetime(df.index)
        
        # 确保价格列为float64
        price_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col].astype('float64')
        
        return df
