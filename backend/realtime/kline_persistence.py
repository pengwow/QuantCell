"""
K线数据持久化模块

当收到完结的K线数据(is_final=True)时，自动保存到数据库
"""

import queue
import threading
from typing import Any

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from collector.db.database import SessionLocal
from collector.db.models import CryptoSpotKline, decimal_or_zero


class KlinePersistenceConsumer:
    """K线数据持久化消费者

    消费者回调跑在引擎数据泵的同步链上，任何 DB I/O 都会阻塞整条实时链路
    （此前同步写库把每条消息的处理耗时拖到 0.16s，depth/aggTrade 被整体饿慢），
    因此这里只做 O(1) 入队，实际写库由独立后台线程串行执行。
    """

    def __init__(self, queue_size: int = 2000):
        """初始化持久化消费者并启动后台写库线程"""
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_size)
        self._dropped = 0
        self._worker = threading.Thread(target=self._run, daemon=True, name="kline-persistence")
        self._worker.start()
        logger.info("KlinePersistenceConsumer initialized (background writer started)")

    def process_kline(self, data: dict[str, Any]) -> bool:
        """
        接收K线数据：过滤出完结K线并入队，不做任何 DB I/O

        Args:
            data: K线数据，包含k字段

        Returns:
            bool: 是否成功入队
        """
        try:
            kline = data.get("k", {})
            if not kline:
                return False
            # 只处理完结的K线
            if not kline.get("x", False):
                return False
            self._queue.put_nowait(kline)
            return True
        except queue.Full:
            # ponytail: 写库线程积压时丢弃新完结K线（上限即放弃），写库本身幂等（写前查重），
            # 历史缺口由 K 线 REST 补数路径兜底；代价是极端积压下丢最后一根收盘K线
            self._dropped += 1
            if self._dropped % 50 == 1:
                logger.warning(f"[KlinePersistence] 写库队列已满，累计丢弃 {self._dropped} 条完结K线")
            return False

    def _run(self) -> None:
        """后台写库线程：串行消费队列，写库失败只记日志不入队重试"""
        while True:
            kline = self._queue.get()
            try:
                self._save_to_database(kline)
            except Exception as e:  # pragma: no cover - 兜底防线程崩溃
                logger.error(f"[KlinePersistence] 后台写库线程异常: {e}")

    def _save_to_database(self, kline: dict[str, Any]) -> bool:
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
            symbol = kline.get("s", "")
            interval = kline.get("i", "")
            timestamp = kline.get("t", 0)
            open_price = float(kline.get("o", 0))
            high_price = float(kline.get("h", 0))
            low_price = float(kline.get("l", 0))
            close_price = float(kline.get("c", 0))
            volume = float(kline.get("v", 0))
            float(kline.get("q", 0))

            if not symbol or not interval or not timestamp:
                logger.warning(
                    f"[KlinePersistence] K线数据缺少必要字段: symbol={symbol}, interval={interval}, timestamp={timestamp}"
                )
                return False

            # 转换symbol格式 BTCUSDT -> BTC/USDT
            # ponytail: 按常见计价资产后缀拆分，未匹配则保留原样；新增计价资产时在此补充
            base_symbol = symbol
            for quote in ("USDT", "USDC", "BUSD", "FDUSD", "BTC", "ETH", "BNB"):
                if symbol.endswith(quote) and len(symbol) > len(quote):
                    base_symbol = f"{symbol[: -len(quote)]}/{quote}"
                    break

            unique_key = f"{base_symbol}_{interval}_{timestamp}"

            # 创建数据库会话
            db = SessionLocal()

            # 检查是否已存在相同记录（走 unique_kline 唯一索引；
            # 旧实现按 symbol/interval/timestamp 三列过滤，命中不了索引）
            existing = db.query(CryptoSpotKline).filter(CryptoSpotKline.unique_kline == unique_key).first()

            if existing:
                # 更新现有记录
                existing.open = str(open_price)
                existing.high = str(high_price)
                existing.low = str(low_price)
                existing.close = str(close_price)
                existing.volume = decimal_or_zero(volume)
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
                    volume=decimal_or_zero(volume),
                    unique_kline=unique_key,
                    data_source="binance_websocket",
                )
                db.add(kline_record)
                logger.info(
                    f"[KlinePersistence] 保存新K线数据: {symbol}@{interval}, timestamp={timestamp}, close={close_price}"
                )

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
