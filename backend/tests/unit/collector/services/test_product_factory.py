"""collector.services.product_factory 单元测试。

覆盖工厂创建与各 market fetcher 的数据库查询逻辑：
- ProductListFactory.create_fetcher: 合法/非法市场与加密货币类型
- 各 Fetcher.fetch_products: 无 db 降级 + 有 db 查询（MagicMock 模拟查询链）
- BaseProductListFetcher._fetch_from_database: 仅支持 crypto 表，其余表名返回空列表
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from collector.services.product_factory import (
    BaseProductListFetcher,
    CryptoFutureProductListFetcher,
    CryptoSpotProductListFetcher,
    FuturesProductListFetcher,
    ProductListFactory,
    StockProductListFetcher,
)


class _StubProductFetcher(BaseProductListFetcher):
    """BaseProductListFetcher 是抽象类，需实现 fetch_products 才能实例化。

    测试基类 _fetch_from_database 逻辑时固定走 crypto_symbol 表。
    """

    def fetch_products(self, db=None, exchange=None, filter=None, limit=100, offset=0):
        return self._fetch_from_database(db, "crypto_symbol", exchange, filter, limit, offset)


def make_product(symbol="BTCUSDT", base="BTC", quote="USDT", exchange="binance", type_="spot"):
    p = MagicMock()
    p.symbol = symbol
    p.base = base
    p.quote = quote
    p.exchange = exchange
    p.type = type_
    return p


def make_db_query(rows, total=1):
    """构造可复用的查询链 mock：db.query(...) -> filter() -> offset() -> limit() -> all()

    生产代码会把 query.filter / query.offset / query.limit 的返回值继续当作 query 使用，
    这里统一让它们返回自身，保证 count() 与 all() 能落在同一个 mock 上。
    """
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.count.return_value = total
    query.all.return_value = rows
    return db


# =================== 工厂 ===================


class TestProductListFactory:
    def test_create_stock(self):
        assert isinstance(ProductListFactory.create_fetcher("stock"), StockProductListFetcher)

    def test_create_futures(self):
        assert isinstance(ProductListFactory.create_fetcher("futures"), FuturesProductListFetcher)

    def test_create_crypto_spot(self):
        assert isinstance(ProductListFactory.create_fetcher("crypto", "spot"), CryptoSpotProductListFetcher)

    def test_create_crypto_future(self):
        assert isinstance(ProductListFactory.create_fetcher("crypto", "future"), CryptoFutureProductListFetcher)

    def test_invalid_crypto_type_raises(self):
        with pytest.raises(ValueError, match="无效的加密货币类型"):
            ProductListFactory.create_fetcher("crypto", "bogus")

    def test_invalid_market_type_raises(self):
        with pytest.raises(ValueError, match="无效的市场类型"):
            ProductListFactory.create_fetcher("bogus")

    def test_crypto_without_crypto_type_raises(self):
        with pytest.raises(ValueError, match="无效的加密货币类型"):
            ProductListFactory.create_fetcher("crypto", None)


# =================== _fetch_from_database 通用逻辑 ===================


class TestBaseFetchFromDatabase:
    def test_unknown_table_returns_empty(self):
        db = MagicMock()
        result = _StubProductFetcher()._fetch_from_database(db, table_name="unknown_table")
        assert result == {"success": True, "message": "查询商品列表成功", "products": []}

    def test_crypto_symbol_table_maps_rows(self):
        db = make_db_query([make_product()], total=1)
        result = _StubProductFetcher()._fetch_from_database(db, table_name="crypto_symbol", limit=10, offset=0)
        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["products"]) == 1
        assert result["products"][0]["symbol"] == "BTCUSDT"
        assert result["products"][0]["icon"] == "S"


# =================== Stock / Futures ===================


class TestStockFetcher:
    def test_no_db_returns_failure(self):
        result = StockProductListFetcher().fetch_products(db=None)
        assert result["success"] is False
        assert "数据库会话未初始化" in result["message"]

    def test_fetch_products_with_db_returns_empty(self):
        # 生产代码 _fetch_from_database 目前仅支持 crypto_symbol 表，
        # stock/futures 表名走 else 分支返回空产品列表（无 total 字段）
        db = make_db_query([make_product(symbol="AAPL", base="AAPL")], total=1)
        result = StockProductListFetcher().fetch_products(db=db, exchange="binance", limit=5)
        assert result["success"] is True
        assert result["products"] == []


class TestFuturesFetcher:
    def test_no_db_returns_failure(self):
        assert FuturesProductListFetcher().fetch_products(db=None)["success"] is False

    def test_fetch_products_with_db_returns_empty(self):
        db = make_db_query([make_product(symbol="BTC/USDT-PERP", type_="future")], total=1)
        result = FuturesProductListFetcher().fetch_products(db=db)
        assert result["success"] is True
        assert result["products"] == []


# =================== Crypto Spot ===================


class TestCryptoSpotFetcher:
    def test_no_db_returns_failure(self):
        assert CryptoSpotProductListFetcher().fetch_products(db=None)["success"] is False

    def test_fetch_products_with_quote_filter(self):
        from unittest.mock import patch

        db = make_db_query([make_product(symbol="BTCUSDT")], total=1)
        with patch("config.get_config", return_value="USDT"):
            result = CryptoSpotProductListFetcher().fetch_products(db=db, exchange="binance")
        assert result["total"] == 1
        assert result["products"][0]["icon"] == "C"
        assert result["products"][0]["quote"] == "USDT"


# =================== Crypto Future ===================


class TestCryptoFutureFetcher:
    def test_no_db_returns_failure(self):
        assert CryptoFutureProductListFetcher().fetch_products(db=None)["success"] is False

    def test_fetch_products_with_db(self):
        db = make_db_query([make_product(symbol="BTCUSDT", type_="future")], total=1)
        result = CryptoFutureProductListFetcher().fetch_products(db=db)
        assert result["total"] == 1
        assert result["products"][0]["icon"] == "CF"
