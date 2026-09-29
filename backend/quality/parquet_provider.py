# 复用 utils 中的工具函数（避免代码重复）
from typing import TYPE_CHECKING

from utils import _normalize_symbol, filter_by_date_range, get_source_data_dir
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

    def _klines_dir(self, candle_type: str):
        """返回指定市场的 K 线根目录。

        与采集器（exchange/*/downloader）落盘布局保持一致：
        {base_dir}/crypto/{spot|future}/klines
        """
        return self.base_dir / "crypto" / candle_type / "klines"

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
        norm_symbol = _normalize_symbol(symbol)
        parquet_path = self._klines_dir(candle_type) / interval / f"{norm_symbol}.parquet"

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
        root = self._klines_dir(candle_type)
        if not root.exists():
            return []

        # 仅扫描指定周期，否则遍历全部周期子目录
        if interval is not None:
            interval_dirs = [root / interval]
        else:
            interval_dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)

        symbols_dict: dict[str, dict] = {}
        for interval_dir in interval_dirs:
            if not interval_dir.is_dir():
                continue
            interval_name = interval_dir.name
            # 文件名即交易对（如 BTCUSDT.parquet）
            for data_file in interval_dir.glob("*.parquet"):
                entry = symbols_dict.setdefault(data_file.stem, {"symbol": data_file.stem, "intervals": []})
                if interval_name not in entry["intervals"]:
                    entry["intervals"].append(interval_name)

        for entry in symbols_dict.values():
            entry["intervals"].sort()

        return [symbols_dict[name] for name in sorted(symbols_dict)]

    def get_available_intervals(self, symbol: str, candle_type: str = "spot") -> list[str]:
        """
        获取指定交易对的可用时间周期

        Args:
            symbol: 交易对符号（如 BTCUSDT）
            candle_type: 市场类型 (spot/future)

        Returns:
            List[str]: 如 ['1m', '5m', '15m', '1h', '4h', '1d']
        """
        norm_symbol = _normalize_symbol(symbol)
        root = self._klines_dir(candle_type)
        if not root.exists():
            return []

        # 周期目录下存在该交易对的 parquet，即视为该周期可用
        return sorted(
            interval_dir.name
            for interval_dir in root.iterdir()
            if interval_dir.is_dir() and (interval_dir / f"{norm_symbol}.parquet").exists()
        )

    # DataProvider 抽象接口实现
    def list_symbols(self, candle_type: str = "spot") -> list:
        """列出可用的交易对（DataProvider 接口实现）"""
        result = self.list_available_symbols(candle_type=candle_type)
        return [item["symbol"] for item in result]

    def list_intervals(self, symbol: str, candle_type: str = "spot") -> list:
        """列出指定交易对可用的K线周期（DataProvider 接口实现）"""
        return self.get_available_intervals(symbol=symbol, candle_type=candle_type)
