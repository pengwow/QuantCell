# 数据分发器
import threading
from typing import TYPE_CHECKING, Any

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class DataDistributor:
    """数据分发器，负责将处理后的数据分发给不同的消费者"""

    def __init__(self):
        """初始化数据分发器"""
        self.consumers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._lock = threading.Lock()

    def register_consumer(self, data_type: str, consumer: Callable[[dict[str, Any]], None]) -> bool:
        with self._lock:
            if data_type not in self.consumers:
                self.consumers[data_type] = []
            self.consumers[data_type].append(consumer)
        logger.info(f"成功注册消费者，数据类型: {data_type}")
        return True

    def unregister_consumer(self, data_type: str, consumer: Callable[[dict[str, Any]], None]) -> bool:
        with self._lock:
            if data_type not in self.consumers:
                logger.warning(f"数据类型不存在: {data_type}")
                return False
            if consumer not in self.consumers[data_type]:
                logger.warning(f"消费者不存在: {consumer}")
                return False
            self.consumers[data_type].remove(consumer)
        logger.info(f"成功注销消费者，数据类型: {data_type}")
        return True

    def distribute(self, data: dict[str, Any]) -> bool:
        """分发数据给对应的消费者（快照模式，锁外回调）"""
        try:
            data_type = data.get("data_type", "")
            if not data_type:
                logger.warning("[KlinePush] 数据缺少类型字段")
                return False

            # ponytail: 锁内快照，锁外回调，避免慢回调阻塞注册
            with self._lock:
                targets = list(self.consumers.get(data_type, []))
                wildcards = list(self.consumers.get("*", []))

            for consumer in targets + wildcards:
                try:
                    consumer(data)
                except Exception as e:
                    logger.error(f"[KlinePush] 消费者执行失败: {e}")

            return True

        except Exception as e:
            logger.error(f"[KlinePush] 数据分发失败: {e}")
            return False

    def broadcast(self, data: dict[str, Any]) -> bool:
        """广播数据给所有消费者（快照模式）"""
        try:
            with self._lock:
                all_consumers = [c for clist in self.consumers.values() for c in clist]

            for consumer in all_consumers:
                try:
                    consumer(data)
                except Exception as e:
                    logger.error(f"消费者执行失败: {e}")
            return True

        except Exception as e:
            logger.error(f"数据广播失败: {e}")
            return False

    def get_consumer_count(self, data_type: str | None = None) -> int:
        with self._lock:
            if data_type:
                return len(self.consumers.get(data_type, []))
            return sum(len(clist) for clist in self.consumers.values())

    def clear_consumers(self, data_type: str | None = None) -> bool:
        try:
            with self._lock:
                if data_type:
                    self.consumers.pop(data_type, None)
                else:
                    self.consumers.clear()
            logger.info(f"成功清除消费者，数据类型: {data_type}")
            return True
        except Exception as e:
            logger.error(f"清除消费者失败: {e}")
            return False
