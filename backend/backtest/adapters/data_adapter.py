"""数据适配器 — 将外部数据源转换为 axon_quant 格式"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# 常用交易对配置
COMMON_PAIRS = {
    "BTCUSDT": {"base": "BTC", "quote": "USDT"},
    "ETHUSDT": {"base": "ETH", "quote": "USDT"},
    "BNBUSDT": {"base": "BNB", "quote": "USDT"},
    "SOLUSDT": {"base": "SOL", "quote": "USDT"},
}


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """标准化 DataFrame 列名为大写 OHLCV"""
    result = df.copy()
    col_map = {}
    for col in result.columns:
        lower = col.lower()
        if lower in ("open", "high", "low", "close", "volume"):
            col_map[col] = lower.capitalize()
    result = result.rename(columns=col_map)
    return result


def dataframe_to_bars(df: pd.DataFrame, symbol: str = "BTCUSDT") -> list[dict]:
    """将 DataFrame 转换为 bar dict 列表"""
    df = normalize_dataframe(df)
    bars = []
    for idx, row in df.iterrows():
        ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)
        bars.append(
            {
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": float(row.get("Volume", 0)),
                "symbol": symbol,
                "timestamp_ns": ts,
            }
        )
    return bars
