"""bookDepth 部分深度快照下载器。

两种真实格式（实测取证 Binance 归档）:
- spot: CSV 含嵌套 bids/asks 列（形如 `[[100.0, 1.0], [99.0, 2.0]]`），
  1 条 record 对应一个 100ms 切片，transform_df 中展平为
  `(timestamp, symbol, side, level, price, quantity)` 长表。
- um/cm: CSV 为 `timestamp,percentage,depth,notional` 扁平格式，每行是
  一个 (秒级时间, 离中间价百分比, 档位量, 名义额) 快照点；保留原格式
  存 5 列宽表（percentage 有正负，代表离中间价的方向，不臆造 side/price）。
"""

from __future__ import annotations

import ast
import io

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind

# spot 格式标准 pyarrow schema: 6 列 (spec §3.2 bookDepth)
BOOK_DEPTH_SCHEMA = pa.schema(
    [
        pa.field("timestamp", pa.int64()),  # 毫秒
        pa.field("symbol", pa.string()),
        pa.field("side", pa.string()),  # 'bid' / 'ask'
        pa.field("level", pa.int32()),  # 0 = 最优
        pa.field("price", pa.float64()),
        pa.field("quantity", pa.float64()),
    ]
)

# um/cm 扁平快照格式 schema: 5 列（percentage 行自带方向信息，无 price/level）
BOOK_DEPTH_FLAT_SCHEMA = pa.schema(
    [
        pa.field("timestamp", pa.int64()),  # 毫秒
        pa.field("symbol", pa.string()),
        pa.field("percentage", pa.float64()),  # 离中间价百分比, 负=一侧 正=另一侧
        pa.field("depth", pa.float64()),  # 档位量
        pa.field("notional", pa.float64()),  # 名义额
    ]
)


def _parse_nested_list(s: str) -> list:
    """把 CSV 内 bids/asks 字符串 `'[[100.0,1.0],[99.0,2.0]]'` 解析为 Python 列表.

    用 `ast.literal_eval` 而非 `eval`, 避免执行注入代码 (Binance 数据可信但
    仍按边界输入处理).
    """
    return ast.literal_eval(s)


class BookDepthFetcher(BaseBinanceArchiveDownloader):
    """部分深度快照（Book Depth）下载器。

    嵌套 bids/asks 在 transform_df 中展平为长表.
    """

    archive_kind = ArchiveKind.BOOK_DEPTH
    url_subpath = "bookDepth"
    # 列由 transform_df 构造, 不存在 raw → standard 的固定映射
    column_mapping = {}
    parquet_schema = BOOK_DEPTH_SCHEMA

    def _parse_csv_bytes(self, data: bytes) -> pd.DataFrame:
        """按首行 header 分派两种格式。

        um/cm 首行是 `percentage,...` 扁平格式；spot 是嵌套 bids/asks 数组列。
        """
        first_line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
        if first_line.startswith("percentage"):
            return pd.read_csv(io.BytesIO(data))
        return pd.read_csv(
            io.BytesIO(data),
            converters={
                "bids": _parse_nested_list,
                "asks": _parse_nested_list,
            },
        )

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """um/cm 扁平格式直存 5 列宽表；spot 展平为长表。"""
        if "percentage" in raw_df.columns:
            # um/cm: 字符串秒级 UTC 时间 → epoch 毫秒; 注入 symbol 列。
            # 不能用 astype(int64)//1e6 的"纳秒→毫秒"换算：pandas 3 起是
            # unit-aware datetime（秒字符串解析为 datetime64[s]），astype 直接
            # 得到秒 epoch，写死除数会得到错误数量级。epoch 差值对任意单位都正确。
            out = raw_df.assign(symbol=self._symbol)
            ts = pd.to_datetime(out["timestamp"], utc=True)
            out["timestamp"] = (ts - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)
            return out[["timestamp", "symbol", "percentage", "depth", "notional"]].astype(
                {"percentage": "float64", "depth": "float64", "notional": "float64"}
            )

        # spot: nested bids + asks 展平为 (side, level, price, quantity) 长表
        rows: list[dict] = []
        for _, r in raw_df.iterrows():
            ts = r["timestamp"]
            sym = r["symbol"]
            for level, (price, qty) in enumerate(r["bids"]):
                rows.append(
                    {
                        "timestamp": ts,
                        "symbol": sym,
                        "side": "bid",
                        "level": level,
                        "price": float(price),
                        "quantity": float(qty),
                    }
                )
            for level, (price, qty) in enumerate(r["asks"]):
                rows.append(
                    {
                        "timestamp": ts,
                        "symbol": sym,
                        "side": "ask",
                        "level": level,
                        "price": float(price),
                        "quantity": float(qty),
                    }
                )
        out = pd.DataFrame(
            rows,
            columns=["timestamp", "symbol", "side", "level", "price", "quantity"],
        )
        # 强制类型, 避免 pandas 把数字推断为 object, 与 schema 对齐
        return out.assign(
            timestamp=out["timestamp"].astype("int64"),
            level=out["level"].astype("int32"),
            price=out["price"].astype("float64"),
            quantity=out["quantity"].astype("float64"),
        )
