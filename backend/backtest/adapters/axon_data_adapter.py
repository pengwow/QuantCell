# -*- coding: utf-8 -*-
"""axon 数据适配器

替代原 backtest/adapters/data_adapter.py 中的 axon_quant 数据类型依赖。
使用 pandas 原生加载，转换为 axon 事件格式。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


class AxonDataAdapter:
    """axon 数据适配器。

    从 CSV/Parquet 加载 OHLCV 数据，转换为 DataFrame。
    不依赖 axon_quant。
    """

    def load_bars_from_csv(self, path: str) -> pd.DataFrame:
        """从 CSV 加载 OHLCV 数据。

        Args:
            path: CSV 文件路径。

        Returns:
            标准化的 OHLCV DataFrame。
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"CSV 文件不存在: {path}")

        df = pd.read_csv(path)
        return self._standardize_dataframe(df)

    def load_bars_from_parquet(self, path: str) -> pd.DataFrame:
        """从 Parquet 加载 OHLCV 数据。

        Args:
            path: Parquet 文件路径。

        Returns:
            标准化的 OHLCV DataFrame。
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Parquet 文件不存在: {path}")

        df = pd.read_parquet(path)
        return self._standardize_dataframe(df)

    def load_multiple(
        self,
        symbols: List[str],
        data_dir: str,
        file_pattern: str = "{symbol}_1h.csv",
    ) -> Dict[str, pd.DataFrame]:
        """加载多个品种的数据。

        Args:
            symbols: 品种列表。
            data_dir: 数据目录。
            file_pattern: 文件名模式，{symbol} 会被替换为品种名。

        Returns:
            品种到 DataFrame 的映射。
        """
        data = {}
        for symbol in symbols:
            filename = file_pattern.format(symbol=symbol)
            filepath = os.path.join(data_dir, filename)
            if os.path.exists(filepath):
                if filepath.endswith(".parquet"):
                    data[symbol] = self.load_bars_from_parquet(filepath)
                else:
                    data[symbol] = self.load_bars_from_csv(filepath)
        return data

    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFrame 列名和索引。

        Args:
            df: 原始 DataFrame。

        Returns:
            标准化后的 DataFrame。
        """
        # 列名标准化为小写
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ("open", "high", "low", "close", "volume", "timestamp"):
                col_map[col] = col_lower
        df = df.rename(columns=col_map)

        # 如果有 timestamp 列，设为索引
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.set_index("timestamp")

        # 确保索引是 DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)

        # 确保必要列存在
        required = ["open", "high", "low", "close"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"缺少必要列: {col}")

        # 转换为 float64
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

        return df
