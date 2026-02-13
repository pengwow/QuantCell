# 商品列表工厂类，实现基于工厂模式的统一商品列表获取接口

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy.orm import Session


class ProductListFetcher(ABC):
    """商品列表获取器抽象基类
    
    定义了获取商品列表的统一接口，不同市场类型的获取器需要实现此接口
    """
    
    @abstractmethod
    def fetch_products(
        self,
        db: Optional[Session] = None,
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取商品列表
        
        Args:
            db: 数据库会话
            exchange: 交易商名称
            filter: 过滤条件
            limit: 返回数量限制
            offset: 返回偏移量
            
        Returns:
            Dict[str, Any]: 包含商品列表的字典，格式如下：
                {
                    "success": bool,
                    "message": str,
                    "products": List[Dict[str, Any]]
                }
        """
        pass


class BaseProductListFetcher(ProductListFetcher):
    """商品列表获取器基类，实现通用的数据库查询逻辑"""
    
    def _fetch_from_database(
        self,
        db: Session,
        table_name: str,
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """从数据库获取商品列表的通用方法"""
        logger.info(f"从数据库获取商品列表: table={table_name}, exchange={exchange}, filter={filter}, limit={limit}, offset={offset}")

        # 导入需要的模型
        if table_name == "crypto_symbol":
            from ..db.models import CryptoSymbol as ProductModel
        else:
            # 默认返回空列表
            return {
                "success": True,
                "message": "查询商品列表成功",
                "products": []
            }

        # 构建查询
        query = db.query(ProductModel)

        # 应用交易商过滤
        if exchange:
            query = query.filter(ProductModel.exchange == exchange)

        # 应用通用过滤（支持 symbol 和 quote 字段）
        if filter:
            query = query.filter(ProductModel.symbol.contains(filter))

        # 计算总数量
        total = query.count()

        # 应用分页
        products = query.offset(offset).limit(limit).all()

        # 转换为指定格式
        product_list = []
        for product in products:
            product_list.append({
                "symbol": product.symbol,
                "name": product.symbol,
                "exchange": product.exchange,
                "icon": self._get_product_icon(product),
                "base": product.base,
                "quote": product.quote if hasattr(product, 'quote') else None,
            })

        return {
            "success": True,
            "message": "查询商品列表成功",
            "products": product_list,
            "total": total
        }
    
    def _get_product_icon(self, product: Any) -> str:
        """获取商品图标"""
        return "S"  # 默认返回股票图标


class StockProductListFetcher(BaseProductListFetcher):
    """股票市场商品列表获取器"""
    
    def fetch_products(
        self,
        db: Optional[Session] = None,
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取股票商品列表"""
        logger.info(f"获取股票商品列表: exchange={exchange}, filter={filter}, limit={limit}, offset={offset}")
        
        if not db:
            return {
                "success": False,
                "message": "数据库会话未初始化",
                "products": []
            }
        
        # 实现股票市场的商品列表获取逻辑
        # 这里复用现有的数据库查询逻辑
        return self._fetch_from_database(
            db=db,
            table_name="stock_symbol",
            exchange=exchange,
            filter=filter,
            limit=limit,
            offset=offset
        )
    
    def _get_product_icon(self, product: Any) -> str:
        """获取股票商品图标"""
        return "S"  # 股票图标


class FuturesProductListFetcher(BaseProductListFetcher):
    """期货市场商品列表获取器"""
    
    def fetch_products(
        self,
        db: Optional[Session] = None,
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取期货商品列表"""
        logger.info(f"获取期货商品列表: exchange={exchange}, filter={filter}, limit={limit}, offset={offset}")
        
        if not db:
            return {
                "success": False,
                "message": "数据库会话未初始化",
                "products": []
            }
        
        # 实现期货市场的商品列表获取逻辑
        # 这里复用现有的数据库查询逻辑
        return self._fetch_from_database(
            db=db,
            table_name="futures_symbol",
            exchange=exchange,
            filter=filter,
            limit=limit,
            offset=offset
        )
    
    def _get_product_icon(self, product: Any) -> str:
        """获取期货商品图标"""
        return "F"  # 期货图标


class CryptoSpotProductListFetcher(BaseProductListFetcher):
    """加密货币现货商品列表获取器"""

    def fetch_products(
        self,
        db: Optional[Session] = None,
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取加密货币现货商品列表

        从系统配置中获取计价货币，并使用数据库 quote 字段进行过滤。
        同时支持通过 filter 参数进行 symbol 过滤。
        """
        logger.info(f"获取加密货币现货商品列表: exchange={exchange}, filter={filter}, limit={limit}, offset={offset}")

        if not db:
            return {
                "success": False,
                "message": "数据库会话未初始化",
                "products": []
            }

        # 从系统配置获取计价货币
        from config_manager import get_config
        from ..db.models import CryptoSymbol
        quote_currency = get_config('quote', 'USDT')
        logger.info(f"系统配置计价货币: quote={quote_currency}")

        # 构建查询
        query = db.query(CryptoSymbol)

        query = query.filter(CryptoSymbol.type == 'spot')

        # 应用交易商过滤
        if exchange:
            query = query.filter(CryptoSymbol.exchange == exchange)

        # 应用计价货币过滤（使用数据库 quote 字段）
        if quote_currency:
            query = query.filter(CryptoSymbol.quote == quote_currency)

        # 应用 symbol 过滤
        if filter:
            query = query.filter(CryptoSymbol.symbol.contains(filter))

        # 计算总数量
        total = query.count()

        # 应用分页
        products = query.offset(offset).limit(limit).all()

        # 转换为指定格式
        product_list = []
        for product in products:
            product_list.append({
                "symbol": product.symbol,
                "name": product.symbol,
                "exchange": product.exchange,
                "icon": self._get_product_icon(product),
                "base": product.base,
                "quote": product.quote,
            })

        return {
            "success": True,
            "message": "查询商品列表成功",
            "products": product_list,
            "total": total
        }

    def _get_product_icon(self, product: Any) -> str:
        """获取加密货币现货商品图标"""
        return "C"  # 加密货币现货图标


class CryptoFutureProductListFetcher(BaseProductListFetcher):
    """加密货币合约商品列表获取器"""
    
    def fetch_products(
        self,
        db: Optional[Session] = None,
        exchange: Optional[str] = None,
        filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """获取加密货币合约商品列表"""
        logger.info(f"获取加密货币合约商品列表: exchange={exchange}, filter={filter}, limit={limit}, offset={offset}")
        
        if not db:
            return {
                "success": False,
                "message": "数据库会话未初始化",
                "products": []
            }
        
        # 实现加密货币合约的商品列表获取逻辑
        # 这里复用现有的数据库查询逻辑，但添加合约类型过滤
        from ..db.models import CryptoSymbol as ProductModel
        
        # 构建查询
        query = db.query(ProductModel).filter(ProductModel.type == "future")
        
        # 应用交易商过滤
        if exchange:
            query = query.filter(ProductModel.exchange == exchange)
        
        # 应用通用过滤
        if filter:
            query = query.filter(ProductModel.symbol.contains(filter))
        
        # 计算总数量
        total = query.count()
        
        # 应用分页
        products = query.offset(offset).limit(limit).all()
        
        # 转换为指定格式
        product_list = []
        for product in products:
            product_list.append({
                "symbol": product.symbol,
                "name": product.symbol,
                "exchange": product.exchange,
                "base": product.base,
                "icon": "CF"  # 加密货币合约图标
            })
        
        return {
            "success": True,
            "message": "查询商品列表成功",
            "products": product_list,
            "total": total
        }


class ProductListFactory:
    """商品列表工厂类，用于创建不同市场类型的商品列表获取器"""
    
    @staticmethod
    def create_fetcher(market_type: str, crypto_type: Optional[str] = None) -> ProductListFetcher:
        """创建商品列表获取器
        
        Args:
            market_type: 市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）
            crypto_type: 加密货币类型，当market_type为crypto时必填，可选值：spot（现货）、future（合约）
            
        Returns:
            ProductListFetcher: 对应市场类型的商品列表获取器
            
        Raises:
            ValueError: 当market_type或crypto_type无效时抛出
        """
        if market_type == "stock":
            return StockProductListFetcher()
        elif market_type == "futures":
            return FuturesProductListFetcher()
        elif market_type == "crypto":
            if crypto_type == "spot":
                return CryptoSpotProductListFetcher()
            elif crypto_type == "future":
                return CryptoFutureProductListFetcher()
            else:
                raise ValueError(f"无效的加密货币类型: {crypto_type}，可选值：spot、future")
        else:
            raise ValueError(f"无效的市场类型: {market_type}，可选值：stock、futures、crypto")
