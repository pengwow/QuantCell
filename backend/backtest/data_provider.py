"""
回测数据提供者模块

从本地Parquet文件加载回测所需的K线数据，支持单品种和多品种批量加载。
支持通过数据适配器加载多种数据类型（K线/Tick/衍生/盘口）。
为回测引擎提供统一的数据接口，替代原有的数据库查询和下载器逻辑。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from utils import get_source_data_dir
from utils.logger import LogType, get_logger
from utils.timestamp_utils import convert_to_datetime

if TYPE_CHECKING:
    from pathlib import Path

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class DataDownloadResult:
    """数据下载/加载结果"""

    symbol: str
    timeframe: str
    success: bool = True
    failure_type: str | None = None  # "no_data", "file_not_found", "parse_error"
    failure_reason: str | None = None
    data: pd.DataFrame | None = None
    warnings: list[str] = field(default_factory=list)
    is_incomplete: bool = False
    coverage_percent: float = 100.0


@dataclass
class AdapterLoadResult:
    """适配器加载结果（包含特征数据）"""

    data: pd.DataFrame
    features: pd.DataFrame | None = None
    metadata: dict = field(default_factory=dict)
    data_type: str = "kline"


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

    def __init__(self, base_dir: Path | None = None):
        """
        初始化数据提供者

        Args:
            base_dir: 数据根目录，默认使用 data_cli 的标准路径
        """
        if base_dir is None:
            base_dir = get_source_data_dir()

        self.base_dir = base_dir
        logger.info(f"[BacktestDataProvider] 初始化完成，数据目录: {base_dir}")

    def load_klines(
        self,
        symbol: str,
        interval: str,
        candle_type: str = "spot",
        start: str | None = None,
        end: str | None = None,
        normalize_columns: bool = True,
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
            from cli.data import _find_parquet_file, filter_by_date_range
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

            logger.info(f"[BacktestDataProvider] 加载成功: {symbol} {interval}, 共{len(df)}条记录")

            return df

        except Exception as e:
            logger.error(f"[BacktestDataProvider] 加载失败: {e}")
            raise

    def load_multiple(
        self,
        symbols: list[str],
        timeframes: list[str],
        candle_type: str = "spot",
        time_range: str | None = None,
        auto_download: bool = False,
        show_progress: bool = False,
    ) -> tuple[dict[str, pd.DataFrame], list[DataDownloadResult]]:
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
        logger.info(f"[BacktestDataProvider] 批量加载开始: {len(symbols)}个品种 x {len(timeframes)}个周期")

        data_dict: dict[str, pd.DataFrame] = {}
        download_results: list[DataDownloadResult] = []

        # 解析时间范围
        start_time = None
        end_time = None
        if time_range:
            try:
                from utils.validation import parse_time_range

                start_dt, end_dt = parse_time_range(time_range)
                start_time = start_dt.strftime("%Y-%m-%d")
                end_time = end_dt.strftime("%Y-%m-%d")
            except Exception as e:
                logger.warning(f"解析时间范围失败: {e}, 将不加时间筛选")

        total_tasks = len(symbols) * len(timeframes)
        current_task = 0

        for symbol in symbols:
            for timeframe in timeframes:
                current_task += 1

                if show_progress:
                    pass

                result = DataDownloadResult(symbol=symbol, timeframe=timeframe)

                try:
                    key = f"{symbol}_{timeframe}"
                    df = self.load_klines(
                        symbol=symbol,
                        interval=timeframe,
                        candle_type=candle_type,
                        start=start_time,
                        end=end_time,
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

            # 🔍 增强错误信息：显示详细的失败原因
            if fail_count > 0:
                for result in download_results:
                    if not result.success and hasattr(result, "warnings") and result.warnings:
                        for _warn in result.warnings:
                            pass

        logger.info(f"[BacktestDataProvider] 批量加载完成: 成功{len(data_dict)}/{total_tasks}个")

        return data_dict, download_results

    def load_data(
        self,
        symbol: str,
        interval: str,
        data_type: str = "kline",
        market: str = "spot",
        start: str | None = None,
        end: str | None = None,
    ) -> AdapterLoadResult:
        """通过数据适配器加载单品种数据。

        Args:
            symbol: 交易对符号
            interval: 时间周期
            data_type: 数据类型 (kline/aggTrades/fundingRate/bookDepth 等)
            market: 市场类型 (spot/um/cm)
            start: 开始时间
            end: 结束时间

        Returns:
            AdapterLoadResult: 包含数据、特征和元数据
        """
        from backtest.data_adapters import DataAdapterFactory, LoadConfig

        config = LoadConfig(
            symbol=symbol,
            data_type=data_type,
            market=market,
            interval=interval,
            start=start,
            end=end,
        )

        adapter = DataAdapterFactory.create(data_type)
        result = adapter.load(config)

        logger.info(f"[BacktestDataProvider] 适配器加载成功: {symbol} {data_type} {market}, {len(result.data)} 行")

        return AdapterLoadResult(
            data=result.data,
            features=result.features,
            metadata=result.metadata,
            data_type=data_type,
        )

    def load_multiple_data(
        self,
        symbols: list[str],
        timeframes: list[str],
        data_type: str = "kline",
        market: str = "spot",
        time_range: str | None = None,
        show_progress: bool = False,
    ) -> tuple[dict[str, AdapterLoadResult], list[DataDownloadResult]]:
        """通过数据适配器批量加载多品种数据。

        Args:
            symbols: 交易对列表
            timeframes: 时间周期列表
            data_type: 数据类型
            market: 市场类型
            time_range: 时间范围 (YYYYMMDD-YYYYMMDD)
            show_progress: 是否显示进度

        Returns:
            (数据字典, 加载结果列表)
        """
        from utils.validation import parse_time_range

        start_time = None
        end_time = None
        if time_range:
            try:
                start_dt, end_dt = parse_time_range(time_range)
                start_time = start_dt.strftime("%Y-%m-%d")
                end_time = end_dt.strftime("%Y-%m-%d")
            except Exception as e:
                logger.warning(f"解析时间范围失败: {e}")

        data_dict: dict[str, AdapterLoadResult] = {}
        download_results: list[DataDownloadResult] = []
        len(symbols) * len(timeframes)
        current_task = 0

        for symbol in symbols:
            for timeframe in timeframes:
                current_task += 1
                if show_progress:
                    pass

                result = DataDownloadResult(symbol=symbol, timeframe=timeframe)
                try:
                    key = f"{symbol}_{timeframe}"
                    load_result = self.load_data(
                        symbol=symbol,
                        interval=timeframe,
                        data_type=data_type,
                        market=market,
                        start=start_time,
                        end=end_time,
                    )
                    if load_result.data.empty:
                        result.success = False
                        result.failure_type = "no_data"
                        result.failure_reason = "数据文件为空"
                    else:
                        data_dict[key] = load_result
                        result.data = load_result.data
                except FileNotFoundError as e:
                    result.success = False
                    result.failure_type = "file_not_found"
                    result.failure_reason = str(e)
                except Exception as e:
                    result.success = False
                    result.failure_type = "parse_error"
                    result.failure_reason = str(e)
                    logger.exception(f"加载失败: {symbol} {timeframe}")

                download_results.append(result)

        if show_progress:
            sum(1 for r in download_results if r.success)

        return data_dict, download_results

    def list_available_symbols(self, candle_type="spot") -> list[dict]:
        """
        列出所有可用的交易对

        Args:
            candle_type: 市场类型 (spot/future)

        Returns:
            List[Dict]: [{symbol: str, intervals: [str]}, ...]
        """
        try:
            from cli.data import scan_parquet_files

            files = scan_parquet_files(candle_type=candle_type)

            symbols_dict: dict[str, dict] = {}
            for f in files:
                sym = f["symbol"]
                if sym not in symbols_dict:
                    symbols_dict[sym] = {"symbol": sym, "intervals": []}
                if f["interval"] not in symbols_dict[sym]["intervals"]:
                    symbols_dict[sym]["intervals"].append(f["interval"])

            return list(symbols_dict.values())

        except Exception as e:
            logger.error(f"[BacktestDataProvider] 列出可用品种失败: {e}")
            return []

    def get_available_intervals(self, symbol: str, candle_type: str = "spot") -> list[str]:
        """
        获取指定交易对的可用时间周期

        Args:
            symbol: 交易对符号
            candle_type: 市场类型

        Returns:
            List[str]: 如 ['1m', '5m', '15m', '1h', '4h', '1d']
        """
        try:
            from cli.data import scan_parquet_files

            files = scan_parquet_files(symbol=symbol, candle_type=candle_type)
            return sorted(set(f["interval"] for f in files))

        except Exception as e:
            logger.error(f"[BacktestDataProvider] 获取可用周期失败: {e}")
            return []

    def load_funding_rate(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        market: str = "um",
    ) -> pd.DataFrame:
        """
        加载永续合约资金费率数据

        数据源路径: data/source/fundingRate/{market}/{symbol}/{symbol}-fundingRate-*.parquet
        原始列: symbol / timestamp(毫秒) / fundingRate / markPrice / rateType

        Args:
            symbol: 交易对符号（如 BTCUSDT）
            start: 开始时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
            end: 结束时间
            market: 市场类型 ("um" U本位 / "cm" 币本位)

        Returns:
            pd.DataFrame: 资金费率数据，索引为 DatetimeIndex，
                          包含 funding_rate / mark_price 列（按时间升序）
        """
        from utils.parquet_utils import load_from_parquet

        normalized_symbol = symbol.upper().replace("/", "")
        funding_dir = self.base_dir / "fundingRate" / market / normalized_symbol

        if not funding_dir.exists():
            logger.warning(f"[BacktestDataProvider] 资金费率目录不存在: {funding_dir}")
            return pd.DataFrame()

        # 合并该品种下所有资金费率分片文件
        files = sorted(funding_dir.glob(f"{normalized_symbol}-fundingRate-*.parquet"))
        if not files:
            logger.warning(f"[BacktestDataProvider] 未找到资金费率文件: {funding_dir}")
            return pd.DataFrame()

        frames = []
        for f in files:
            try:
                frames.append(load_from_parquet(f))
            except Exception as e:
                logger.warning(f"[BacktestDataProvider] 资金费率文件加载失败 {f.name}: {e}")

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)

        # 时间戳为毫秒，转换为 datetime 索引
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").sort_index()

        # 时间范围筛选
        if start or end:
            from cli.data import filter_by_date_range

            df = filter_by_date_range(df, start, end)

        # 标准化列名
        df = df.rename(columns={"fundingRate": "funding_rate", "markPrice": "mark_price"})
        keep_cols = [c for c in ("funding_rate", "mark_price", "rateType") if c in df.columns]
        df = df[keep_cols]

        for col in ("funding_rate", "mark_price"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.info(f"[BacktestDataProvider] 资金费率加载成功: {normalized_symbol}, 共{len(df)}条记录")
        return df

    def _normalize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化DataFrame格式

        处理内容：
        1. 列名统一为小写（event_engine 要求）
        2. 时间戳处理：设置datetime索引（自动检测精度）
        3. 数据类型确保：价格列为float64

        Args:
            df: 原始DataFrame

        Returns:
            pd.DataFrame: 标准化后的DataFrame
        """
        df = df.copy()

        # 统一列名为小写（event_engine 使用小写列名）
        df.columns = [col.lower() for col in df.columns]

        # 设置时间索引（使用统一的工具函数自动检测时间戳精度）
        if "timestamp" in df.columns:
            if not isinstance(df.index, pd.DatetimeIndex):
                df.set_index("timestamp", inplace=True)
            df.index = convert_to_datetime(df.index)
        elif "date" in df.columns:
            if not isinstance(df.index, pd.DatetimeIndex):
                df.set_index("date", inplace=True)
            df.index = convert_to_datetime(df.index)

        # 确保价格列为float64
        price_columns = ["open", "high", "low", "close", "volume"]
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col].astype("float64")

        return df
