# -*- coding: utf-8 -*-
"""
K线数据持久化模块

当收到完结的K线数据(is_final=True)时，自动保存到数据库
"""

from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from collector.db.models import CryptoSpotKline
from collector.db.database import SessionLocal


class KlinePersistenceConsumer:
    """K线数据持久化消费者"""

    def __init__(self):
        """初始化持久化消费者"""
        self.db_session = None
        logger.info("KlinePersistenceConsumer initialized")

    def process_kline(self, data: Dict[str, Any]) -> bool:
        """
        处理K线数据，只保存完结的K线

        Args:
            data: K线数据，包含k字段

        Returns:
            bool: 是否成功保存
        """
        try:
            # 获取K线数据
            kline = data.get('k', {})
            if not kline:
                return False

            # 只处理完结的K线
            is_final = kline.get('x', False)
            if not is_final:
                # K线未完结，跳过
                return False

            # 保存到数据库
            return self._save_to_database(kline)

        except Exception as e:
            logger.error(f"[KlinePersistence] 处理K线数据失败: {e}")
            return False

    def _save_to_database(self, kline: Dict[str, Any]) -> bool:
        """
        保存K线数据到数据库

        Args:
            kline: 币安K线数据格式

        Returns:
            bool: 是否成功保存
        """
        db = None
        try:
            # 提取字段
            symbol = kline.get('s', '')
            interval = kline.get('i', '')
            timestamp = kline.get('t', 0)
            open_price = float(kline.get('o', 0))
            high_price = float(kline.get('h', 0))
            low_price = float(kline.get('l', 0))
            close_price = float(kline.get('c', 0))
            volume = float(kline.get('v', 0))
            quote_volume = float(kline.get('q', 0))

            if not symbol or not interval or not timestamp:
                logger.warning(f"[KlinePersistence] K线数据缺少必要字段: symbol={symbol}, interval={interval}, timestamp={timestamp}")
                return False

            # 转换symbol格式 BTCUSDT -> BTC/USDT
            base_symbol = symbol.replace('USDT', '/USDT').replace('BTC', '/BTC').replace('ETH', '/ETH')
            if '/' not in base_symbol:
                base_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith('USDT') else symbol

            # 创建数据库会话
            db = SessionLocal()

            # 检查是否已存在相同记录
            existing = db.query(CryptoSpotKline).filter(
                CryptoSpotKline.symbol == base_symbol,
                CryptoSpotKline.interval == interval,
                CryptoSpotKline.timestamp == timestamp
            ).first()

            if existing:
                # 更新现有记录
                existing.open = str(open_price)
                existing.high = str(high_price)
                existing.low = str(low_price)
                existing.close = str(close_price)
                existing.volume = str(volume)
                existing.turnover = str(quote_volume)
                logger.debug(f"[KlinePersistence] 更新K线数据: {symbol}@{interval}, timestamp={timestamp}")
            else:
                # 创建新记录
                kline_record = CryptoSpotKline(
                    symbol=base_symbol,
                    interval=interval,
                    timestamp=str(timestamp),
                    open=str(open_price),
                    high=str(high_price),
                    low=str(low_price),
                    close=str(close_price),
                    volume=str(volume),
                    turnover=str(quote_volume),
                    unique_kline=f"{base_symbol}_{interval}_{timestamp}",
                    data_source='binance_websocket'
                )
                db.add(kline_record)
                logger.info(f"[KlinePersistence] 保存新K线数据: {symbol}@{interval}, timestamp={timestamp}, close={close_price}")

            # 提交事务
            db.commit()
            return True

        except Exception as e:
            logger.error(f"[KlinePersistence] 保存K线数据到数据库失败: {e}")
            if db:
                db.rollback()
            return False
        finally:
            if db:
                db.close()


# 全局持久化消费者实例
kline_persistence_consumer = KlinePersistenceConsumer()
