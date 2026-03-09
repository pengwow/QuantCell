"""市场数据服务模块

基于工厂模式的市场数据获取服务，支持多交易所和代理配置
"""
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from collector.db.database import get_db
from collector.db.models import MarketData
from settings.models import SystemConfigBusiness as SystemConfig
from .market_data_factory import market_data_fetcher_factory


class MarketDataService:
    """市场数据服务类

    负责从多交易所获取市场数据并缓存到数据库
    支持从系统配置读取代理和交易所信息
    """

    def __init__(self):
        """初始化市场数据服务"""
        self.cache_ttl = timedelta(minutes=5)  # 缓存5分钟

    async def get_market_data(self, symbols: List[str],
                              exchange: str = "binance",
                              force_refresh: bool = False) -> List[Dict]:
        """获取市场数据

        优先从交易所官方接口获取，失败时回退到数据库缓存

        Args:
            symbols: 货币对列表
            exchange: 交易所名称
            force_refresh: 强制刷新（仍优先从官方接口获取）

        Returns:
            List[Dict]: 市场数据列表

        Raises:
            Exception: 当无法从交易所获取数据且数据库中没有缓存时
        """
        if not symbols:
            return []

        result = []
        failed_symbols = []

        # 优先从交易所官方接口获取数据
        try:
            # 使用工厂获取对应交易所的获取器
            fetcher = market_data_fetcher_factory.get_fetcher(exchange)
            if not fetcher:
                raise Exception(f"不支持的交易所或未启用: {exchange}")

            logger.info(f"从{exchange}官方接口获取市场数据: {len(symbols)}个货币对")
            fresh_data = await fetcher.fetch_market_data(symbols)
            
            # 记录成功获取的数据
            fetched_symbols = {item.get("symbol") for item in fresh_data if item.get("symbol")}
            result.extend(fresh_data)
            
            # 找出获取失败的货币对
            failed_symbols = [s for s in symbols if s not in fetched_symbols]
            if failed_symbols:
                logger.warning(f"以下货币对从官方接口获取失败: {failed_symbols}")
                
        except Exception as e:
            logger.error(f"从交易所官方接口获取市场数据失败: {e}")
            failed_symbols = symbols  # 全部失败

        # 对于获取失败的货币对，尝试从数据库缓存获取
        if failed_symbols:
            logger.info(f"从数据库缓存获取失败的货币对: {len(failed_symbols)}个")
            db_data = await self._get_market_data_from_db(failed_symbols, exchange)
            
            # 添加数据库中的有效数据
            if db_data["valid"]:
                logger.info(f"从数据库缓存获取到{len(db_data['valid'])}条数据")
                result.extend(db_data["valid"])
            
            # 记录数据库中也没有的货币对
            if db_data["expired"]:
                logger.warning(f"以下货币对在数据库中也不存在或已过期: {db_data['expired']}")

        # 如果没有任何数据，抛出异常
        if not result:
            raise Exception(f"无法从交易所官方接口或数据库缓存获取市场数据")

        return result

    async def _get_market_data_from_db(self, symbols: List[str],
                                       exchange: str) -> Dict:
        """从数据库获取市场数据，返回有效和过期的"""
        db = next(get_db())
        try:
            valid_data = []
            expired_symbols = []

            for symbol in symbols:
                record = db.query(MarketData).filter(
                    MarketData.symbol == symbol,
                    MarketData.exchange == exchange
                ).first()

                if record:
                    # 检查是否过期
                    if (record.last_update and
                        datetime.utcnow() - record.last_update < self.cache_ttl):
                        valid_data.append({
                            "symbol": record.symbol,
                            "price": float(record.price) if record.price else None,
                            "price_change_24h": float(record.price_change_24h) if record.price_change_24h else None,
                            "price_change_percent_24h": float(record.price_change_percent_24h) if record.price_change_percent_24h else None,
                            "volume_24h": float(record.volume_24h) if record.volume_24h else None,
                            "high_24h": float(record.high_24h) if record.high_24h else None,
                            "low_24h": float(record.low_24h) if record.low_24h else None,
                            "last_update": record.last_update.isoformat() if record.last_update else None
                        })
                    else:
                        expired_symbols.append(symbol)
                else:
                    expired_symbols.append(symbol)

            return {"valid": valid_data, "expired": expired_symbols}
        finally:
            db.close()

    async def sync_all_market_data(self, exchange: str = "binance") -> int:
        """同步所有货币对的市场数据

        Args:
            exchange: 交易所名称

        Returns:
            int: 同步的数据条数
        """
        try:
            # 使用工厂获取对应交易所的获取器
            fetcher = market_data_fetcher_factory.get_fetcher(exchange)
            if not fetcher:
                raise Exception(f"不支持的交易所或未启用: {exchange}")

            logger.info(f"开始同步{exchange}所有货币对的市场数据")
            all_data = await fetcher.fetch_all_tickers()
            logger.info(f"成功同步{len(all_data)}条市场数据")
            return len(all_data)

        except Exception as e:
            logger.error(f"同步所有市场数据失败: {e}")
            raise

    def clear_fetcher_cache(self):
        """清除获取器缓存"""
        market_data_fetcher_factory.clear_cache()


# 全局服务实例
market_data_service = MarketDataService()
