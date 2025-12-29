# K线数据工厂类，实现基于工厂模式的统一数据获取接口

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from ..db.models import Kline


class KlineDataFetcher(ABC):
    """K线数据获取器抽象基类
    
    定义了获取K线数据的统一接口，不同市场类型的获取器需要实现此接口
    """
    
    @abstractmethod
    def fetch_kline_data(
        self,
        db: Session,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 5000
    ) -> Dict[str, Any]:
        """获取K线数据
        
        Args:
            db: 数据库会话
            symbol: 交易商标识
            interval: 时间周期
            start_time: 开始时间，格式YYYY-MM-DD HH:MM:SS
            end_time: 结束时间，格式YYYY-MM-DD HH:MM:SS
            limit: 返回数据条数，默认5000条
            
        Returns:
            Dict[str, Any]: 包含K线数据的字典，格式如下：
                {
                    "success": bool,
                    "message": str,
                    "kline_data": List[Dict[str, Any]]
                }
        """
        pass


class BaseKlineFetcher(KlineDataFetcher):
    """K线数据获取器基类，实现通用的数据库查询逻辑"""
    
    def _fetch_from_database(
        self,
        db: Session,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 5000
    ) -> Dict[str, Any]:
        """从数据库获取K线数据的通用方法"""
        # 构建查询
        query = db.query(Kline).filter(
            Kline.symbol == symbol,
            Kline.interval == interval
        )
        
        # 处理时间过滤
        if start_time:
            try:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                query = query.filter(Kline.date >= start_dt)
            except ValueError:
                logger.warning(f"无效的开始时间格式: {start_time}，忽略该过滤条件")
        
        if end_time:
            try:
                end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                query = query.filter(Kline.date <= end_dt)
            except ValueError:
                logger.warning(f"无效的结束时间格式: {end_time}，忽略该过滤条件")
        
        # 按时间降序排序并限制数量
        query = query.order_by(Kline.date.desc()).limit(limit)
        
        # 执行查询
        klines = query.all()
        
        # 转换为指定格式
        kline_data = []
        for kline in klines:
            # 转换时间为毫秒级时间戳
            timestamp = int(kline.date.timestamp() * 1000)
            
            kline_data.append({
                "timestamp": timestamp,
                "open": float(kline.open),
                "close": float(kline.close),
                "high": float(kline.high),
                "low": float(kline.low),
                "volume": float(kline.volume),
                "turnover": 0.0  # 成交额字段，当前版本返回0
            })
        
        # 按时间升序返回
        kline_data.reverse()
        
        return {
            "success": True,
            "message": "查询K线数据成功",
            "kline_data": kline_data
        }


class StockKlineFetcher(BaseKlineFetcher):
    """股票市场K线数据获取器"""
    
    def fetch_kline_data(
        self,
        db: Session,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 5000
    ) -> Dict[str, Any]:
        """获取股票K线数据"""
        logger.info(f"获取股票K线数据: symbol={symbol}, interval={interval}, limit={limit}")
        
        # 实现股票市场的K线数据获取逻辑
        # 这里复用现有的数据库查询逻辑
        return self._fetch_from_database(db, symbol, interval, start_time, end_time, limit)


class FuturesKlineFetcher(BaseKlineFetcher):
    """期货市场K线数据获取器"""
    
    def fetch_kline_data(
        self,
        db: Session,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 5000
    ) -> Dict[str, Any]:
        """获取期货K线数据"""
        logger.info(f"获取期货K线数据: symbol={symbol}, interval={interval}, limit={limit}")
        
        # 实现期货市场的K线数据获取逻辑
        # 这里复用现有的数据库查询逻辑
        return self._fetch_from_database(db, symbol, interval, start_time, end_time, limit)


class CryptoSpotKlineFetcher(BaseKlineFetcher):
    """加密货币现货K线数据获取器"""
    
    def fetch_kline_data(
        self,
        db: Session,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 5000
    ) -> Dict[str, Any]:
        """获取加密货币现货K线数据"""
        # 格式化symbol，移除斜杠等分隔符，转换为数据库存储格式（如BTC/USDT -> BTCUSDT）
        formatted_symbol = symbol.replace('/', '')
        logger.info(f"获取加密货币现货K线数据: symbol={symbol}, formatted_symbol={formatted_symbol}, interval={interval}, limit={limit}")
        
        # 实现加密货币现货的K线数据获取逻辑
        # 这里复用现有的数据库查询逻辑
        return self._fetch_from_database(db, formatted_symbol, interval, start_time, end_time, limit)


class CryptoFutureKlineFetcher(BaseKlineFetcher):
    """加密货币合约K线数据获取器"""
    
    def fetch_kline_data(
        self,
        db: Session,
        symbol: str,
        interval: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = 5000
    ) -> Dict[str, Any]:
        """获取加密货币合约K线数据"""
        # 格式化symbol，移除斜杠等分隔符，转换为数据库存储格式（如BTC/USDT -> BTCUSDT）
        formatted_symbol = symbol.replace('/', '')
        logger.info(f"获取加密货币合约K线数据: symbol={symbol}, formatted_symbol={formatted_symbol}, interval={interval}, limit={limit}")
        
        # 实现加密货币合约的K线数据获取逻辑
        # 这里复用现有的数据库查询逻辑
        return self._fetch_from_database(db, formatted_symbol, interval, start_time, end_time, limit)


class KlineDataFactory:
    """K线数据工厂类，用于创建不同市场类型的K线数据获取器"""
    
    @staticmethod
    def create_fetcher(market_type: str, crypto_type: Optional[str] = None) -> KlineDataFetcher:
        """创建K线数据获取器
        
        Args:
            market_type: 市场类型，可选值：stock（股票）、futures（期货）、crypto（加密货币）
            crypto_type: 加密货币类型，当market_type为crypto时必填，可选值：spot（现货）、future（合约）
            
        Returns:
            KlineDataFetcher: 对应市场类型的K线数据获取器
            
        Raises:
            ValueError: 当market_type或crypto_type无效时抛出
        """
        if market_type == "stock":
            return StockKlineFetcher()
        elif market_type == "futures":
            return FuturesKlineFetcher()
        elif market_type == "crypto":
            if crypto_type == "spot":
                return CryptoSpotKlineFetcher()
            elif crypto_type == "future":
                return CryptoFutureKlineFetcher()
            else:
                raise ValueError(f"无效的加密货币类型: {crypto_type}，可选值：spot、future")
        else:
            raise ValueError(f"无效的市场类型: {market_type}，可选值：stock、futures、crypto")
