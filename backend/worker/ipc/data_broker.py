"""
数据代理模块

管理数据订阅和分发，使用 ZeroMQ PUB/SUB 模式实现高效数据分发
"""

from typing import Dict, Set, List, Optional, Callable
from dataclasses import dataclass, field
from loguru import logger
import asyncio

from .comm_manager import CommManager
from .protocol import Message, MessageType, MessageTopic


@dataclass
class DataSubscription:
    """
    数据订阅信息

    记录 Worker 的数据订阅配置
    """

    worker_id: str
    symbols: Set[str] = field(default_factory=set)
    data_types: Set[str] = field(default_factory=lambda: {"kline"})

    def add_symbols(self, symbols: List[str]):
        """添加交易对"""
        self.symbols.update(symbols)

    def remove_symbols(self, symbols: List[str]):
        """移除交易对"""
        self.symbols.difference_update(symbols)

    def add_data_types(self, data_types: List[str]):
        """添加数据类型"""
        self.data_types.update(data_types)

    def remove_data_types(self, data_types: List[str]):
        """移除数据类型"""
        self.data_types.difference_update(data_types)

    def get_topics(self) -> List[str]:
        """
        获取所有订阅主题

        Returns:
            主题列表
        """
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

        # 订阅管理: worker_id -> DataSubscription
        self._subscriptions: Dict[str, DataSubscription] = {}

        # 主题路由表: topic -> set(worker_ids)
        self._topic_routing: Dict[str, Set[str]] = {}

        # 统计信息
        self._messages_published = 0
        self._messages_dropped = 0

        # 数据处理器（用于预处理数据）
        self._data_preprocessors: List[Callable[[Message], Optional[Message]]] = []

        # 批量处理配置
        self._batch_size = 100
        self._batch_timeout = 0.01  # 10ms
        self._message_buffer: List[Message] = []
        self._buffer_lock = asyncio.Lock()

    def subscribe(
        self,
        worker_id: str,
        symbols: List[str],
        data_types: Optional[List[str]] = None,
    ) -> bool:
        """
        Worker 订阅数据

        Args:
            worker_id: Worker ID
            symbols: 交易对列表
            data_types: 数据类型列表，默认为 ["kline"]

        Returns:
            是否订阅成功
        """
        if data_types is None:
            data_types = ["kline"]

        try:
            # 获取或创建订阅
            if worker_id not in self._subscriptions:
                self._subscriptions[worker_id] = DataSubscription(worker_id=worker_id)

            subscription = self._subscriptions[worker_id]

            # 更新订阅
            subscription.add_symbols(symbols)
            subscription.add_data_types(data_types)

            # 更新路由表
            for symbol in symbols:
                for data_type in data_types:
                    topic = MessageTopic.market_data(symbol, data_type)
                    if topic not in self._topic_routing:
                        self._topic_routing[topic] = set()
                    self._topic_routing[topic].add(worker_id)

            logger.info(
                f"Worker {worker_id} 订阅数据: symbols={symbols}, types={data_types}"
            )
            return True

        except Exception as e:
            logger.error(f"Worker {worker_id} 订阅数据失败: {e}")
            return False

    def unsubscribe(
        self,
        worker_id: str,
        symbols: Optional[List[str]] = None,
        data_types: Optional[List[str]] = None,
    ) -> bool:
        """
        Worker 取消订阅数据

        Args:
            worker_id: Worker ID
            symbols: 交易对列表，None 表示取消所有交易对
            data_types: 数据类型列表，None 表示取消所有数据类型

        Returns:
            是否取消订阅成功
        """
        try:
            if worker_id not in self._subscriptions:
                return True

            subscription = self._subscriptions[worker_id]

            # 确定要取消的交易对和数据类型
            # 如果都没有指定，则取消所有订阅
            if symbols is None and data_types is None:
                symbols_to_remove = list(subscription.symbols)
                types_to_remove = list(subscription.data_types)
            else:
                # 如果指定了 symbols，只移除这些 symbols
                # 如果指定了 data_types，只移除这些 data_types
                symbols_to_remove = symbols if symbols else []
                types_to_remove = data_types if data_types else []

            # 更新订阅
            subscription.remove_symbols(symbols_to_remove)
            subscription.remove_data_types(types_to_remove)

            # 更新路由表
            # 确定需要更新路由的 symbol 和 data_type 组合
            if symbols is not None and data_types is not None:
                # 都指定了，使用指定的组合
                routing_symbols = symbols_to_remove
                routing_types = types_to_remove
            elif symbols is not None:
                # 只指定了 symbols，为所有 data_types 更新路由
                routing_symbols = symbols_to_remove
                routing_types = list(subscription.data_types) + types_to_remove
            elif data_types is not None:
                # 只指定了 data_types，为所有 symbols 更新路由
                routing_symbols = list(subscription.symbols) + symbols_to_remove
                routing_types = types_to_remove
            else:
                # 都没指定，使用所有组合
                routing_symbols = symbols_to_remove
                routing_types = types_to_remove

            for symbol in routing_symbols:
                for data_type in routing_types:
                    topic = MessageTopic.market_data(symbol, data_type)
                    if topic in self._topic_routing:
                        self._topic_routing[topic].discard(worker_id)
                        if not self._topic_routing[topic]:
                            del self._topic_routing[topic]

            # 如果订阅为空，删除订阅记录
            if not subscription.symbols or not subscription.data_types:
                del self._subscriptions[worker_id]

            logger.info(
                f"Worker {worker_id} 取消订阅: symbols={symbols_to_remove}, types={types_to_remove}"
            )
            return True

        except Exception as e:
            logger.error(f"Worker {worker_id} 取消订阅失败: {e}")
            return False

    def unsubscribe_all(self, worker_id: str) -> bool:
        """
        Worker 取消所有订阅

        Args:
            worker_id: Worker ID

        Returns:
            是否取消订阅成功
        """
        return self.unsubscribe(worker_id)

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
            data_type: 数据类型 (kline, tick, depth)
            data: 数据内容
            source: 数据来源

        Returns:
            是否发布成功
        """
        try:
            # 构建消息
            message = Message.create_market_data(symbol, data_type, data, source)

            # 构建主题
            topic = MessageTopic.market_data(symbol, data_type)

            # 通过 ZMQ 发布
            success = await self.comm_manager.publish_data(topic, message)

            if success:
                self._messages_published += 1
            else:
                self._messages_dropped += 1

            return success

        except Exception as e:
            logger.error(f"发布数据失败: {e}")
            self._messages_dropped += 1
            return False

    async def publish_batch(self, messages: List[Message]) -> int:
        """
        批量发布市场数据

        Args:
            messages: 消息列表

        Returns:
            成功发布的消息数量
        """
        success_count = 0
        for message in messages:
            try:
                symbol = message.payload.get("symbol")
                data_type = message.payload.get("data_type")

                if symbol and data_type:
                    topic = MessageTopic.market_data(symbol, data_type)
                    success = await self.comm_manager.publish_data(topic, message)
                    if success:
                        success_count += 1
            except Exception as e:
                logger.error(f"批量发布数据失败: {e}")

        self._messages_published += success_count
        self._messages_dropped += len(messages) - success_count

        return success_count

    def get_subscribers(self, symbol: str, data_type: str = "kline") -> Set[str]:
        """
        获取订阅指定数据的 Worker 列表

        Args:
            symbol: 交易对
            data_type: 数据类型

        Returns:
            Worker ID 集合
        """
        topic = MessageTopic.market_data(symbol, data_type)
        return self._topic_routing.get(topic, set()).copy()

    def get_subscription(self, worker_id: str) -> Optional[DataSubscription]:
        """
        获取 Worker 的订阅信息

        Args:
            worker_id: Worker ID

        Returns:
            订阅信息
        """
        return self._subscriptions.get(worker_id)

    def get_all_subscriptions(self) -> Dict[str, DataSubscription]:
        """
        获取所有订阅信息

        Returns:
            订阅信息字典
        """
        return self._subscriptions.copy()

    def get_topic_stats(self) -> Dict[str, int]:
        """
        获取主题统计信息

        Returns:
            主题 -> 订阅者数量 的字典
        """
        return {topic: len(workers) for topic, workers in self._topic_routing.items()}

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
        处理消息（应用预处理器）

        Args:
            message: 原始消息

        Returns:
            处理后的消息或 None
        """
        current_message = message
        for preprocessor in self._data_preprocessors:
            try:
                current_message = preprocessor(current_message)
                if current_message is None:
                    return None
            except Exception as e:
                logger.error(f"数据预处理器错误: {e}")
                return None
        return current_message

    def is_subscribed(self, worker_id: str, symbol: str, data_type: str = "kline") -> bool:
        """
        检查 Worker 是否订阅了指定数据

        Args:
            worker_id: Worker ID
            symbol: 交易对
            data_type: 数据类型

        Returns:
            是否已订阅
        """
        topic = MessageTopic.market_data(symbol, data_type)
        return worker_id in self._topic_routing.get(topic, set())

    def get_worker_symbols(self, worker_id: str) -> List[str]:
        """
        获取 Worker 订阅的所有交易对

        Args:
            worker_id: Worker ID

        Returns:
            交易对列表
        """
        subscription = self._subscriptions.get(worker_id)
        if subscription:
            return list(subscription.symbols)
        return []

    def get_symbol_workers(self, symbol: str, data_type: str = "kline") -> List[str]:
        """
        获取订阅指定交易对的所有 Worker

        Args:
            symbol: 交易对
            data_type: 数据类型

        Returns:
            Worker ID 列表
        """
        topic = MessageTopic.market_data(symbol, data_type)
        return list(self._topic_routing.get(topic, set()))
