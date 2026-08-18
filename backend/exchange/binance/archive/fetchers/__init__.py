"""7 个 fetcher 子类，由 factory 装配。

每个 fetcher 都继承自 BaseBinanceArchiveDownloader，重写 4 个类属性钩子
(archive_kind / url_subpath / column_mapping / parquet_schema)。
完整业务实现由 Task 5–11 逐个补充。
"""

from exchange.binance.archive.fetchers.agg_trades import AggTradesFetcher
from exchange.binance.archive.fetchers.book_depth import BookDepthFetcher
from exchange.binance.archive.fetchers.book_ticker import BookTickerFetcher
from exchange.binance.archive.fetchers.index_price_klines import IndexPriceKlinesFetcher
from exchange.binance.archive.fetchers.mark_price_klines import MarkPriceKlinesFetcher
from exchange.binance.archive.fetchers.premium_index_klines import (
    PremiumIndexKlinesFetcher,
)
from exchange.binance.archive.fetchers.trades import TradesFetcher

__all__ = [
    "AggTradesFetcher",
    "BookDepthFetcher",
    "BookTickerFetcher",
    "IndexPriceKlinesFetcher",
    "MarkPriceKlinesFetcher",
    "PremiumIndexKlinesFetcher",
    "TradesFetcher",
]
