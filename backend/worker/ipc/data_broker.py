"""
数据代理模块

管理数据订阅和分发，使用 ZeroMQ PUB/SUB 模式实现高效数据分发
"""

from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field
from loguru import logger

from .protocol import Message, MessageType, MessageTopic
from .comm_manager import CommManager


@dataclass
class DataSubscription:
    """
    数据订阅信息

    记录 Worker 对特定交易对和数据类型的订阅
    """
    worker_id: str
    symbols: Set[str] = field(default_factory=set)
    data_types: Set[str] = field(default_factory=lambda: {"kline"})

    def add_symbols(self, symbols: List[str]):
        """添加交易对"""
        self.symbols.update(symbols)

    def remove_symbols(self, symbols: List[str]):
        """移除交易对"""
        for symbol in symbols:
            self.symbols.discard(symbol)

    def add_data_types(self, data_types: List[str]):
        """添加数据类型"""
        self.data_types.update(data_types)

    def remove_data_types(self, data_types: List[str]):
        """移除数据类型"""
        for data_type in data_types:
            self.data_types.discard(data_type)

    def get_topics(self) -> List[str]:
        """获取所有订阅主题"""
        topics = []
        for symbol in self.symbols:
            for data_type in self.data_types:
                topics.append(MessageTopic.market_data(symbol, data_type))
        return topics


class DataBroker:
    """
    数据代理

    管理数据订阅和分发，使用 PUB/SUB 模式实现高效数据分发
    """

    def __init__(self, comm_manager: CommManager):
        """
        初始化数据代理

        Args:
            comm_manager: 通信管理器实例
        """
        self.comm_manager = comm_manager
        self._subscriptions: Dict[str, DataSubscription] = {}
        self._topic_routing: Dict[str, Set[str]] = {}
        self._messages_published = 0
        self._messages_dropped = 0
        self._data_preprocessors: List[Callable[[Message], Optional[Message]]] = []

    def subscribe(
        self,
        worker_id: str,
        symbols: List[str],
        data_types: Optional[List[str]] = None,
    ) -> bool:
        """
        订阅数据

        Args:
            worker_id: Worker ID
            symbols: 交易对列表
            data_types: 数据类型列表，默认为 ["kline"]

        Returns:
            是否订阅成功
        """
        try:
            if data_types is None:
                data_types = ["kline"]

            # 获取或创建订阅
            if worker_id not in self._subscriptions:
                self._subscriptions[worker_id] = DataSubscription(worker_id=worker_id)

            subscription = self._subscriptions[worker_id]
            subscription.add_symbols(symbols)
            subscription.add_data_types(data_types)

            # 更新主题路由
            for topic in subscription.get_topics():
                if topic not in self._topic_routing:
                    self._topic_routing[topic] = set()
                self._topic_routing[topic].add(worker_id)

            logger.info(f"Worker {worker_id} 订阅数据: symbols={symbols}, types={data_types}")
            return True

        except Exception as e:
            logger.error(f"订阅数据失败: {e}")
            return False

    def unsubscribe(
        self,
        worker_id: str,
        symbols: Optional[List[str]] = None,
        data_types: Optional[List[str]] = None,
    ) -> bool:
        """
        取消订阅

        Args:
            worker_id: Worker ID
            symbols: 要取消的交易对列表，None 表示取消所有
            data_types: 要取消的数据类型列表，None 表示取消所有类型

        Returns:
            是否取消成功
        """
        try:
            if worker_id not in self._subscriptions:
                return True

            subscription = self._subscriptions[worker_id]

            if symbols is None:
                # 取消所有订阅
                for topic in subscription.get_topics():
                    if topic in self._topic_routing:
                        self._topic_routing[topic].discard(worker_id)
                subscription.symbols.clear()
            else:
                subscription.remove_symbols(symbols)

            if data_types is not None:
                subscription.remove_data_types(data_types)

            logger.info(f"Worker {worker_id} 取消订阅")
            return True

        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
            return False

    def unsubscribe_all(self, worker_id: str) -> bool:
        """
        取消 Worker 的所有订阅

        Args:
            worker_id: Worker ID

        Returns:
            是否取消成功
        """
        try:
            if worker_id in self._subscriptions:
                subscription = self._subscriptions[worker_id]
                for topic in subscription.get_topics():
                    if topic in self._topic_routing:
                        self._topic_routing[topic].discard(worker_id)
                        if not self._topic_routing[topic]:
                            del self._topic_routing[topic]

                del self._subscriptions[worker_id]

            logger.info(f"Worker {worker_id} 取消所有订阅")
            return True

        except Exception as e:
            logger.error(f"取消所有订阅失败: {e}")
            return False

    async def publish(
        self,
        symbol: str,
        data_type: str,
        data: dict,
        source: Optional[str] = None,
    ) -> bool:
        """
        发布市场数据

        Args:
            symbol: 交易对
            data_type: 数据类型
            data: 数据内容
            source: 数据来源

        Returns:
            是否发布成功
        """
        try:
            topic = MessageTopic.market_data(symbol, data_type)
            message = Message.create_market_data(symbol, data_type, data, source)

            # 应用预处理器
            message = await self._process_message(message)
            if message is None:
                self._messages_dropped += 1
                return False

            # 发布数据
            success = await self.comm_manager.publish_data(topic, message)
            if success:
                self._messages_published += 1

            return success

        except Exception as e:
            logger.error(f"发布数据失败: {e}")
            self._messages_dropped += 1
            return False

    async def publish_batch(self, messages: List[Message]) -> int:
        """
        批量发布数据

        Args:
            messages: 消息列表

        Returns:
            成功发布的消息数量
        """
        count = 0
        for message in messages:
            if message.payload.get("symbol") and message.payload.get("data_type"):
                topic = MessageTopic.market_data(
                    message.payload["symbol"],
                    message.payload["data_type"],
                )
                if await self.comm_manager.publish_data(topic, message):
                    count += 1
        return count

    def get_subscribers(self, symbol: str, data_type: str) -> Set[str]:
        """
        获取订阅者列表

        Args:
            symbol: 交易对
            data_type: 数据类型

        Returns:
            订阅该主题的 Worker ID 集合
        """
        topic = MessageTopic.market_data(symbol, data_type)
        return self._topic_routing.get(topic, set())

    def get_subscription(self, worker_id: str) -> Optional[DataSubscription]:
        """
        获取 Worker 的订阅信息

        Args:
            worker_id: Worker ID

        Returns:
            订阅信息或 None
        """
        return self._subscriptions.get(worker_id)

    def get_topic_stats(self) -> Dict[str, int]:
        """
        获取主题统计

        Returns:
            主题 -> 订阅者数量 的字典
        """
        return {topic: len(subscribers) for topic, subscribers in self._topic_routing.items()}

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "subscriptions_count": len(self._subscriptions),
            "topics_count": len(self._topic_routing),
            "messages_published": self._messages_published,
            "messages_dropped": self._messages_dropped,
            "topic_stats": self.get_topic_stats(),
        }

    def is_subscribed(self, worker_id: str, symbol: str, data_type: str) -> bool:
        """
        检查 Worker 是否订阅了特定主题

        Args:
            worker_id: Worker ID
            symbol: 交易对
            data_type: 数据类型

        Returns:
            是否已订阅
        """
        if worker_id not in self._subscriptions:
            return False

        subscription = self._subscriptions[worker_id]
        return symbol in subscription.symbols and data_type in subscription.data_types

    def get_worker_symbols(self, worker_id: str) -> List[str]:
        """
        获取 Worker 订阅的所有交易对

        Args:
            worker_id: Worker ID

        Returns:
            交易对列表
        """
        if worker_id not in self._subscriptions:
            return []

        return list(self._subscriptions[worker_id].symbols)

    def get_symbol_workers(self, symbol: str, data_type: str = "kline") -> Set[str]:
        """
        获取订阅特定交易对的所有 Worker

        Args:
            symbol: 交易对
            data_type: 数据类型

        Returns:
            Worker ID 集合
        """
        topic = MessageTopic.market_data(symbol, data_type)
        return self._topic_routing.get(topic, set())

    def register_preprocessor(self, preprocessor: Callable[[Message], Optional[Message]]):
        """
        注册数据预处理器

        Args:
            preprocessor: 预处理器函数，接收 Message 返回处理后的 Message 或 None
        """
        self._data_preprocessors.append(preprocessor)

    def unregister_preprocessor(self, preprocessor: Callable[[Message], Optional[Message]]):
        """
        注销数据预处理器

        Args:
            preprocessor: 预处理器函数
        """
        if preprocessor in self._data_preprocessors:
            self._data_preprocessors.remove(preprocessor)

    async def _process_message(self, message: Message) -> Optional[Message]:
        """
        处理消息（应用所有预处理器）

        Args:
            message: 原始消息

        Returns:
            处理后的消息或 None（如果被过滤）
        """
        for preprocessor in self._data_preprocessors:
            try:
                message = preprocessor(message)
                if message is None:
                    return None
            except Exception as e:
                logger.error(f"预处理器错误: {e}")
                return None
        return message
