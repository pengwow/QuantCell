# K线数据工厂类，实现基于工厂模式的统一数据获取接口

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from ..db.models import CryptoSpotKline, CryptoFutureKline, StockKline


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
    
    def __init__(self):
        self.kline_model = None
    
    def _save_to_database(
        self,
        db: Session,
        symbol: str,
        interval: str,
        kline_data: List[Dict[str, Any]]
    ) -> bool:
        """将K线数据保存到数据库，存在则更新

        Args:
            db: 数据库会话
            symbol: 交易商标识，如BTCUSDT
            interval: 时间周期，如1m, 5m, 1h, 1d
            kline_data: K线数据列表，每条数据包含timestamp, open, close, high, low, volume, turnover字段

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 记录保存K线数据的尝试
            logger.info(f"尝试保存{len(kline_data)}条K线数据到数据库: symbol={symbol}, interval={interval}, model={self.kline_model.__tablename__ if self.kline_model else 'None'}")

            if not self.kline_model:
                logger.error(f"保存K线数据到数据库失败: 未设置kline_model")
                return False

            inserted_count = 0
            updated_count = 0

            for kline in kline_data:
                # 转换timestamp为字符串，保持毫秒级
                timestamp_str = str(kline.get("timestamp"))

                # 生成unique_kline字段
                unique_kline = f"{symbol}_{interval}_{timestamp_str}"

                # 检查是否已存在
                existing = db.query(self.kline_model).filter(
                    self.kline_model.unique_kline == unique_kline
                ).first()

                if existing:
                    # 更新现有记录
                    existing.open = str(kline.get("open"))
                    existing.high = str(kline.get("high"))
                    existing.low = str(kline.get("low"))
                    existing.close = str(kline.get("close"))
                    existing.volume = str(kline.get("volume"))
                    existing.data_source = 'ccxt_binance'
                    updated_count += 1
                else:
                    # 创建新记录
                    kline_instance = self.kline_model(
                        symbol=symbol,
                        interval=interval,
                        timestamp=timestamp_str,
                        open=str(kline.get("open")),
                        high=str(kline.get("high")),
                        low=str(kline.get("low")),
                        close=str(kline.get("close")),
                        volume=str(kline.get("volume")),
                        unique_kline=unique_kline,
                        data_source='ccxt_binance'
                    )
                    db.add(kline_instance)
                    inserted_count += 1

            # 提交事务
            db.commit()

            logger.info(f"成功保存{len(kline_data)}条K线数据到数据库: symbol={symbol}, interval={interval}, 插入={inserted_count}, 更新={updated_count}")
            return True
        except Exception as e:
            logger.error(f"保存K线数据到数据库失败: symbol={symbol}, interval={interval}, error={e}")
            logger.exception(e)
            # 回滚事务
            db.rollback()
            return False
            # 回滚事务
            db.rollback()
            return False
    
    def _fetch_from_ccxt(
        self,
        symbol: str,
        interval: str,
        limit: Optional[int] = 5000,
        proxy_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """从ccxt获取K线数据的通用方法
        
        Args:
            symbol: 交易商标识，如BTC/USDT
            interval: 时间周期，如1m, 5m, 1h, 1d
            limit: 返回数据条数，默认5000条
            proxy_config: 代理配置，包含enabled, url, username, password等字段
            
        Returns:
            List[Dict[str, Any]]: 包含K线数据的列表
        """
        import ccxt
        from datetime import datetime
        
        # 初始化ccxt交易所客户端（默认使用binance）
        exchange = ccxt.binance()
        
        # 配置代理
        if proxy_config and proxy_config.get("enabled", False):
            proxy_url = proxy_config.get("url")
            proxy_username = proxy_config.get("username")
            proxy_password = proxy_config.get("password")
            
            if proxy_url:
                from urllib.parse import urlparse
                parsed_url = urlparse(proxy_url)
                
                if parsed_url.scheme in ['socks5', 'socks4', 'socks4a']:
                    # SOCKS代理使用proxy属性
                    exchange.proxy = proxy_url
                else:
                    # HTTP/HTTPS代理使用proxies字典
                    exchange.proxies = {
                        "http": proxy_url,
                        "https": proxy_url
                    }
                
                # 如果有用户名和密码，添加到代理配置中
                if proxy_username and proxy_password:
                    exchange.proxy_auth = (proxy_username, proxy_password)
        
        # 调用ccxt的fetchOHLCV方法获取K线数据
        # ccxt返回的OHLCV数据格式：[[timestamp, open, high, low, close, volume], ...]
        try:
            ohlcv_data = exchange.fetchOHLCV(
                symbol=symbol,
                timeframe=interval,
                limit=limit
            )
            
            # 转换为指定格式
            kline_data = []
            for ohlcv in ohlcv_data:
                timestamp = ohlcv[0]
                kline_data.append({
                    "timestamp": timestamp,
                    "open": float(ohlcv[1]),
                    "close": float(ohlcv[4]),
                    "high": float(ohlcv[2]),
                    "low": float(ohlcv[3]),
                    "volume": float(ohlcv[5]),
                    "turnover": 0.0  # 成交额字段，当前版本返回0
                })
            
            return kline_data
        except Exception as e:
            logger.error(f"从ccxt获取K线数据失败: symbol={symbol}, interval={interval}, error={e}")
            return []
    
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
        if not self.kline_model:
            logger.error("未设置K线模型，无法从数据库获取数据")
            return {
                "success": False,
                "message": "未设置K线模型",
                "kline_data": []
            }
        
        # 构建查询
        query = db.query(self.kline_model).filter(
            self.kline_model.symbol == symbol,
            self.kline_model.interval == interval
        )
        
        # 处理时间过滤
        if start_time:
            try:
                start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
                query = query.filter(self.kline_model.timestamp >= start_dt)
            except ValueError:
                logger.warning(f"无效的开始时间格式: {start_time}，忽略该过滤条件")
        
        if end_time:
            try:
                end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                query = query.filter(self.kline_model.timestamp <= end_dt)
            except ValueError:
                logger.warning(f"无效的结束时间格式: {end_time}，忽略该过滤条件")
        
        # 按时间降序排序并限制数量
        query = query.order_by(self.kline_model.timestamp.desc()).limit(limit)
        
        # 执行查询
        klines = query.all()
        
        # 转换为指定格式
        kline_data = []
        for kline in klines:
            # 转换时间戳为整数
            timestamp = int(kline.timestamp)
            
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
    
    def __init__(self):
        super().__init__()
        self.kline_model = StockKline
    
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
    
    def __init__(self):
        super().__init__()
        self.kline_model = CryptoFutureKline
    
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

    def __init__(self):
        super().__init__()
        self.kline_model = CryptoSpotKline

    def _is_data_expired(self, latest_timestamp: int, interval: str) -> tuple[bool, str]:
        """
        检查数据是否过期

        Args:
            latest_timestamp: 最新数据的时间戳（毫秒）
            interval: K线周期

        Returns:
            tuple[bool, str]: (是否过期, 原因)
        """
        from datetime import datetime

        now = int(datetime.utcnow().timestamp() * 1000)

        # 计算K线周期对应的毫秒数
        interval_ms = self._get_interval_ms(interval)

        # 判断标准1：超过1根K线周期
        if now - latest_timestamp > interval_ms:
            return True, f"数据超过1根K线周期，最新数据时间: {latest_timestamp}, 当前时间: {now}, 差值: {now - latest_timestamp}ms"

        # 判断标准2：超过1天
        one_day_ms = 24 * 60 * 60 * 1000
        if now - latest_timestamp > one_day_ms:
            return True, f"数据超过1天，最新数据时间: {latest_timestamp}, 当前时间: {now}"

        return False, "数据新鲜"

    def _get_interval_ms(self, interval: str) -> int:
        """获取K线周期对应的毫秒数"""
        interval_map = {
            '1m': 60 * 1000,
            '3m': 3 * 60 * 1000,
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '2h': 2 * 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '6h': 6 * 60 * 60 * 1000,
            '8h': 8 * 60 * 60 * 1000,
            '12h': 12 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000,
            '3d': 3 * 24 * 60 * 60 * 1000,
            '1w': 7 * 24 * 60 * 60 * 1000,
        }
        return interval_map.get(interval.lower(), 60 * 1000)  # 默认1分钟

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
        interval = interval.lower()
        # 首先从数据库获取K线数据
        result = self._fetch_from_database(db, formatted_symbol, interval, start_time, end_time, limit)

        # 检查数据时效性
        data_expired = False
        if result['kline_data']:
            latest_timestamp = result['kline_data'][-1]['timestamp']  # 最后一条是最新的
            is_expired, reason = self._is_data_expired(latest_timestamp, interval)
            if is_expired:
                logger.warning(f"[KlineData] 数据已过期: {reason}")
                data_expired = True
            else:
                logger.info(f"[KlineData] 数据新鲜，最新时间戳: {latest_timestamp}")

        # 如果数据库数据为空或已过期，从ccxt获取
        if not result['kline_data'] or data_expired:
            if not result['kline_data']:
                logger.warning(f"数据库中未找到K线数据，尝试从ccxt获取: symbol={symbol}, interval={interval}")
            else:
                logger.warning(f"数据库数据已过期，尝试从ccxt获取最新数据: symbol={symbol}, interval={interval}")

            # 获取系统配置中的代理信息
            from config_manager import load_system_configs
            configs = load_system_configs()
            proxy_config = {
                "enabled": configs.get("proxy_enabled", False),
                "url": configs.get("proxy_url", None),
                "username": configs.get("proxy_username", None),
                "password": configs.get("proxy_password", None)
            }

            # 从ccxt获取K线数据
            ccxt_data = self._fetch_from_ccxt(symbol, interval, limit, proxy_config)

            if ccxt_data:
                result['kline_data'] = ccxt_data
                result['message'] = "从ccxt获取K线数据成功"

                # 将从ccxt获取的K线数据保存到数据库
                self._save_to_database(db, formatted_symbol, interval, ccxt_data)
            else:
                if not result['kline_data']:
                    result['message'] = "数据库和ccxt均未找到K线数据"
                else:
                    result['message'] = "数据库数据已过期，从ccxt获取数据失败，返回旧数据"

        return result


class CryptoFutureKlineFetcher(BaseKlineFetcher):
    """加密货币合约K线数据获取器"""
    
    def __init__(self):
        super().__init__()
        self.kline_model = CryptoFutureKline
    
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
        interval = interval.lower()
        # 首先从数据库获取K线数据
        result = self._fetch_from_database(db, formatted_symbol, interval, start_time, end_time, limit)
        
        # 检查数据库返回的K线数据是否为空
        if not result['kline_data']:
            logger.warning(f"数据库中未找到K线数据，尝试从ccxt获取: symbol={symbol}, interval={interval}")
            
            # 获取系统配置中的代理信息
            from config_manager import load_system_configs
            configs = load_system_configs()
            proxy_config = {
                "enabled": configs.get("proxy_enabled", False),
                "url": configs.get("proxy_url", None),
                "username": configs.get("proxy_username", None),
                "password": configs.get("proxy_password", None)
            }
            
            # 从ccxt获取K线数据
            ccxt_data = self._fetch_from_ccxt(symbol, interval, limit, proxy_config)
            
            if ccxt_data:
                result['kline_data'] = ccxt_data
                result['message'] = "从ccxt获取K线数据成功"
                
                # 将从ccxt获取的K线数据保存到数据库
                self._save_to_database(db, formatted_symbol, interval, ccxt_data)
            else:
                result['message'] = "数据库和ccxt均未找到K线数据"
        
        return result


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
