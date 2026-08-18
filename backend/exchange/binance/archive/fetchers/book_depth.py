"""bookDepth 部分深度快照下载器（Task 8 完整实现）。

bookDepth zip 内的 CSV **含嵌套 bids/asks 列**（形如
`[[100.0, 1.0], [99.0, 2.0]]` 的二维数组), 1 条 record 对应一个 100ms 切片
的 20-1000 档买卖盘快照。需要在 `transform_df` 中把每条 record 展平成
`(timestamp, symbol, side, level, price, quantity)` 长表, 单日行数 × 20~1000。
"""

from __future__ import annotations

import ast
import io

import pandas as pd
import pyarrow as pa

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind

# 标准 pyarrow schema: 6 列 (spec §3.2 bookDepth)
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
        """bookDepth zip 内的 CSV 含 bids/asks 嵌套数组列.

        用 converters 把字符串解析为 Python 列表, 后续 transform_df 展平.
        """
        return pd.read_csv(
            io.BytesIO(data),
            converters={
                "bids": _parse_nested_list,
                "asks": _parse_nested_list,
            },
        )

    def transform_df(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """把 nested bids + asks 展平为 `(side, level, price, quantity)` 长表.

        1 条 record → N bids + M asks 行; `level` 从 0 开始 (0 = 最优),
        每个 record 内独立计数 (跨 record 不连续).
        """
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
