# 复用 cli/data.py 中的工具函数（避免代码重复）
from typing import TYPE_CHECKING

from cli.data import _find_parquet_file, filter_by_date_range, scan_parquet_files
from utils import get_source_data_dir
from utils.parquet_utils import load_from_parquet

from .data_provider import DataProvider

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd


class ParquetDataProvider(DataProvider):
    """Parquet 文件数据提供者

    从本地 Parquet 文件读取K线数据，支持时间范围筛选。
    文件路径结构：{base_dir}/crypto/{spot|future}/klines/{interval}/{symbol}.parquet
    """

    def __init__(self, base_dir: Path | None = None):
        """
        初始化 Parquet 数据提供者

        Args:
            base_dir: 数据根目录，默认为 backend/data/source
        """
        if base_dir is None:
            base_dir = get_source_data_dir()
        self.base_dir = base_dir

    def get_kline_data(
        self,
        symbol: str,
        interval: str,
        candle_type: str = "spot",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """
        从 Parquet 文件获取K线数据

        Args:
            symbol: 交易对符号（如 BTCUSDT）
            interval: 时间周期（如 1h, 15m）
            candle_type: 市场类型 (spot/future)
            start: 开始时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
            end: 结束时间

        Returns:
            pd.DataFrame: 包含 timestamp, open, high, low, close, volume 的DataFrame

        Raises:
            FileNotFoundError: 当Parquet文件不存在时
        """
        parquet_path = _find_parquet_file(symbol, interval, candle_type)

        if not parquet_path.exists():
            msg = (
                f"未找到 {symbol} {interval} 的Parquet文件\n"
                f"预期路径: {parquet_path}\n"
                f"提示: 请先使用 download 命令下载数据"
            )
            raise FileNotFoundError(msg)

        df = load_from_parquet(parquet_path)

        # 应用时间范围筛选
        if not df.empty and (start or end):
            df = filter_by_date_range(df, start, end)

        return df

    def list_available_symbols(self, candle_type: str = "spot", interval: str | None = None) -> list[dict]:
        """
        扫描并列出所有可用的交易对

        Args:
            candle_type: 市场类型 (spot/future)
            interval: 可选，筛选特定时间周期的交易对

        Returns:
            List[Dict]: [{symbol: str, intervals: List[str]}, ...]
        """
        files = scan_parquet_files(candle_type=candle_type, interval=interval)

        symbols_dict: dict[str, dict] = {}
        for f in files:
            sym = f["symbol"]
            if sym not in symbols_dict:
                symbols_dict[sym] = {"symbol": sym, "intervals": []}
            if f["interval"] not in symbols_dict[sym]["intervals"]:
                symbols_dict[sym]["intervals"].append(f["interval"])

        return list(symbols_dict.values())

    def get_available_intervals(self, symbol: str, candle_type: str = "spot") -> list[str]:
        """
        获取指定交易对的可用时间周期

        Args:
            symbol: 交易对符号（如 BTCUSDT）
            candle_type: 市场类型 (spot/future)

        Returns:
            List[str]: 如 ['1m', '5m', '15m', '1h', '4h', '1d']
        """
        files = scan_parquet_files(symbol=symbol, candle_type=candle_type)
        return sorted(set(f["interval"] for f in files))

    # DataProvider 抽象接口实现
    def list_symbols(self, candle_type: str = "spot") -> list:
        """列出可用的交易对（DataProvider 接口实现）"""
        result = self.list_available_symbols(candle_type=candle_type)
        return [item["symbol"] for item in result]

    def list_intervals(self, symbol: str, candle_type: str = "spot") -> list:
        """列出指定交易对可用的K线周期（DataProvider 接口实现）"""
        return self.get_available_intervals(symbol=symbol, candle_type=candle_type)
