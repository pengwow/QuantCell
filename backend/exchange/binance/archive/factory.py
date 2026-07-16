"""7 种归档数据 × 3 个市场的工厂装配。"""
from __future__ import annotations

from exchange.binance.archive.base import BaseBinanceArchiveDownloader
from exchange.binance.archive.kinds import ArchiveKind, MarketType


class BinanceArchiveFactory:
    """根据 (kind, market) 组合返回对应 fetcher 实例。

    设计要点：
    - 7 种数据种类各对应一个 fetcher 类；同一个 kind 在 3 个 market 下复用同一类（market 作为
      构造参数透传，影响 save_dir / URL 前缀，不影响 fetcher 类行为）。
    - 注册表以 (kind, market) 为 key 共 21 项，方便校验 "每个组合都能实例化"。
    - 接受 ArchiveKind enum 或其 value 字符串；未知 kind 抛 ValueError。
    """

    # 完整注册表（21 项）：(kind, market) → fetcher 类
    _REGISTRY: dict[tuple[ArchiveKind, MarketType], type[BaseBinanceArchiveDownloader]] = {}

    # kind → fetcher 类的紧凑表达（用于构建 _REGISTRY）
    _KIND_TO_FETCHER: dict[ArchiveKind, type[BaseBinanceArchiveDownloader]] = {}

    @classmethod
    def _build_registry(cls) -> None:
        if cls._REGISTRY:
            return
        # 延迟 import 避免循环：fetchers 包内部还会被上层其他模块使用
        from exchange.binance.archive.fetchers import (
            AggTradesFetcher,
            BookDepthFetcher,
            BookTickerFetcher,
            IndexPriceKlinesFetcher,
            MarkPriceKlinesFetcher,
            PremiumIndexKlinesFetcher,
            TradesFetcher,
        )

        cls._KIND_TO_FETCHER = {
            ArchiveKind.AGG_TRADES: AggTradesFetcher,
            ArchiveKind.TRADES: TradesFetcher,
            ArchiveKind.BOOK_DEPTH: BookDepthFetcher,
            ArchiveKind.BOOK_TICKER: BookTickerFetcher,
            ArchiveKind.MARK_KLINES: MarkPriceKlinesFetcher,
            ArchiveKind.INDEX_KLINES: IndexPriceKlinesFetcher,
            ArchiveKind.PREMIUM_KLINES: PremiumIndexKlinesFetcher,
        }
        # 7 × 3 = 21 项；market 不影响类选择，但保持显式映射便于诊断
        cls._REGISTRY = {
            (kind, market): fetcher_cls
            for kind, fetcher_cls in cls._KIND_TO_FETCHER.items()
            for market in MarketType
        }

    @classmethod
    def create(
        cls,
        kind: ArchiveKind | str,
        market: MarketType,
        base_dir: str,
        symbol: str,
        interval: str | None = None,
        proxy: str | None = None,
    ) -> BaseBinanceArchiveDownloader:
        """根据 (kind, market) 实例化 fetcher。

        Args:
            kind: ArchiveKind enum 或其 value 字符串（'aggTrades' 等）。
            market: MarketType 枚举（spot / um / cm）。
            base_dir: 本地数据存储根目录。
            symbol: 交易对符号（如 'BTCUSDT'）。
            interval: K 线间隔（仅 K 线类 fetcher 生效）。
            proxy: HTTP 代理地址。

        Returns:
            已注入 (market, base_dir, symbol, interval, proxy) 的 fetcher 实例。

        Raises:
            ValueError: kind 不是合法 ArchiveKind。
        """
        cls._build_registry()

        if isinstance(kind, str):
            try:
                kind = ArchiveKind(kind)
            except ValueError as exc:
                raise ValueError(f"Unknown ArchiveKind: {kind!r}") from exc

        fetcher_cls = cls._REGISTRY.get((kind, market))
        if fetcher_cls is None:
            # 走到这里说明 _build_registry 出错或 kind 拼写异常
            raise ValueError(f"No fetcher registered for kind={kind!r}, market={market!r}")
        return fetcher_cls(
            market=market,
            base_dir=base_dir,
            symbol=symbol,
            interval=interval,
            proxy=proxy,
        )
