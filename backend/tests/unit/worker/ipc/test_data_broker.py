"""
Worker DataBroker 模块单元测试

测试 DataBroker 和 DataSubscription 的功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from worker.ipc.data_broker import DataBroker, DataSubscription
from worker.ipc.protocol import Message, MessageType, MessageTopic


class TestDataSubscription:
    """测试 DataSubscription 类"""

    @pytest.fixture
    def subscription(self):
        """创建测试用的 DataSubscription 实例"""
        return DataSubscription(worker_id="worker-001")

    def test_initial_state(self, subscription):
        """测试初始状态"""
        assert subscription.worker_id == "worker-001"
        assert len(subscription.symbols) == 0
        assert "kline" in subscription.data_types

    def test_add_symbols(self, subscription):
        """测试添加交易对"""
        subscription.add_symbols(["BTC/USDT", "ETH/USDT"])
        assert "BTC/USDT" in subscription.symbols
        assert "ETH/USDT" in subscription.symbols
        assert len(subscription.symbols) == 2

    def test_remove_symbols(self, subscription):
        """测试移除交易对"""
        subscription.add_symbols(["BTC/USDT", "ETH/USDT", "XRP/USDT"])
        subscription.remove_symbols(["ETH/USDT"])
        assert "BTC/USDT" in subscription.symbols
        assert "ETH/USDT" not in subscription.symbols
        assert "XRP/USDT" in subscription.symbols

    def test_add_data_types(self, subscription):
        """测试添加数据类型"""
        subscription.add_data_types(["tick", "depth"])
        assert "kline" in subscription.data_types
        assert "tick" in subscription.data_types
        assert "depth" in subscription.data_types

    def test_remove_data_types(self, subscription):
        """测试移除数据类型"""
        subscription.add_data_types(["tick", "depth"])
        subscription.remove_data_types(["tick"])
        assert "tick" not in subscription.data_types
        assert "kline" in subscription.data_types
        assert "depth" in subscription.data_types

    def test_get_topics(self, subscription):
        """测试获取主题列表"""
        subscription.add_symbols(["BTC/USDT", "ETH/USDT"])
        subscription.add_data_types(["kline", "tick"])
        
        topics = subscription.get_topics()
        
        assert len(topics) == 4  # 2 symbols * 2 data types
        assert "market.BTC/USDT.kline" in topics
        assert "market.BTC/USDT.tick" in topics
        assert "market.ETH/USDT.kline" in topics
        assert "market.ETH/USDT.tick" in topics

    def test_get_topics_empty(self, subscription):
        """测试空订阅时的主题列表"""
        topics = subscription.get_topics()
        assert len(topics) == 0


class TestDataBroker:
    """测试 DataBroker 类"""

    @pytest.fixture
    def mock_comm_manager(self):
        """创建模拟的通信管理器"""
        mock = AsyncMock()
        mock.publish_data = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def data_broker(self, mock_comm_manager):
        """创建测试用的 DataBroker 实例"""
        return DataBroker(mock_comm_manager)

    def test_initial_state(self, data_broker, mock_comm_manager):
        """测试初始状态"""
        assert data_broker.comm_manager == mock_comm_manager
        assert len(data_broker._subscriptions) == 0
        assert len(data_broker._topic_routing) == 0
        assert data_broker._messages_published == 0
        assert data_broker._messages_dropped == 0

    def test_subscribe_success(self, data_broker):
        """测试成功的订阅"""
        result = data_broker.subscribe(
            worker_id="worker-001",
            symbols=["BTC/USDT", "ETH/USDT"],
            data_types=["kline", "tick"]
        )
        
        assert result is True
        assert "worker-001" in data_broker._subscriptions
        assert "market.BTC/USDT.kline" in data_broker._topic_routing
        assert "worker-001" in data_broker._topic_routing["market.BTC/USDT.kline"]

    def test_subscribe_add_to_existing(self, data_broker):
        """测试向现有订阅添加"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        data_broker.subscribe("worker-001", ["ETH/USDT"], ["tick"])
        
        subscription = data_broker._subscriptions["worker-001"]
        assert "BTC/USDT" in subscription.symbols
        assert "ETH/USDT" in subscription.symbols
        assert "kline" in subscription.data_types
        assert "tick" in subscription.data_types

    def test_subscribe_multiple_workers(self, data_broker):
        """测试多个 Worker 订阅同一主题"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        data_broker.subscribe("worker-002", ["BTC/USDT"], ["kline"])
        
        subscribers = data_broker._topic_routing["market.BTC/USDT.kline"]
        assert "worker-001" in subscribers
        assert "worker-002" in subscribers

    def test_unsubscribe_partial(self, data_broker):
        """测试部分取消订阅"""
        data_broker.subscribe("worker-001", ["BTC/USDT", "ETH/USDT"], ["kline", "tick"])
        result = data_broker.unsubscribe("worker-001", symbols=["BTC/USDT"])
        
        assert result is True
        subscription = data_broker._subscriptions["worker-001"]
        assert "BTC/USDT" not in subscription.symbols
        assert "ETH/USDT" in subscription.symbols

    def test_unsubscribe_all(self, data_broker):
        """测试取消所有订阅"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        result = data_broker.unsubscribe_all("worker-001")
        
        assert result is True
        assert "worker-001" not in data_broker._subscriptions
        assert "worker-001" not in data_broker._topic_routing.get("market.BTC/USDT.kline", set())

    def test_unsubscribe_nonexistent_worker(self, data_broker):
        """测试取消不存在的 Worker 订阅"""
        result = data_broker.unsubscribe("nonexistent")
        assert result is True  # 应该返回 True，因为没有错误

    @pytest.mark.asyncio
    async def test_publish_success(self, data_broker, mock_comm_manager):
        """测试成功的数据发布"""
        result = await data_broker.publish(
            symbol="BTC/USDT",
            data_type="kline",
            data={"close": 50000},
            source="binance"
        )
        
        assert result is True
        assert data_broker._messages_published == 1
        mock_comm_manager.publish_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_failure(self, data_broker, mock_comm_manager):
        """测试发布失败"""
        mock_comm_manager.publish_data = AsyncMock(return_value=False)
        
        result = await data_broker.publish("BTC/USDT", "kline", {})
        
        assert result is False
        assert data_broker._messages_dropped == 1

    @pytest.mark.asyncio
    async def test_publish_batch(self, data_broker, mock_comm_manager):
        """测试批量发布"""
        messages = [
            Message.create_market_data("BTC/USDT", "kline", {"close": 50000}),
            Message.create_market_data("ETH/USDT", "kline", {"close": 3000}),
        ]
        
        count = await data_broker.publish_batch(messages)
        
        assert count == 2
        assert data_broker._messages_published == 2

    def test_get_subscribers(self, data_broker):
        """测试获取订阅者"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        data_broker.subscribe("worker-002", ["BTC/USDT"], ["kline"])
        
        subscribers = data_broker.get_subscribers("BTC/USDT", "kline")
        
        assert "worker-001" in subscribers
        assert "worker-002" in subscribers

    def test_get_subscribers_empty(self, data_broker):
        """测试获取空订阅者"""
        subscribers = data_broker.get_subscribers("BTC/USDT", "kline")
        assert len(subscribers) == 0

    def test_get_subscription(self, data_broker):
        """测试获取订阅信息"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        
        subscription = data_broker.get_subscription("worker-001")
        
        assert subscription is not None
        assert subscription.worker_id == "worker-001"
        assert "BTC/USDT" in subscription.symbols

    def test_get_subscription_nonexistent(self, data_broker):
        """测试获取不存在的订阅"""
        subscription = data_broker.get_subscription("nonexistent")
        assert subscription is None

    def test_get_topic_stats(self, data_broker):
        """测试获取主题统计"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        data_broker.subscribe("worker-002", ["BTC/USDT"], ["kline"])
        data_broker.subscribe("worker-003", ["ETH/USDT"], ["kline"])
        
        stats = data_broker.get_topic_stats()
        
        assert stats["market.BTC/USDT.kline"] == 2
        assert stats["market.ETH/USDT.kline"] == 1

    def test_get_stats(self, data_broker):
        """测试获取统计信息"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        
        stats = data_broker.get_stats()
        
        assert stats["subscriptions_count"] == 1
        assert stats["topics_count"] == 1
        assert "topic_stats" in stats

    def test_is_subscribed(self, data_broker):
        """测试检查是否已订阅"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        
        assert data_broker.is_subscribed("worker-001", "BTC/USDT", "kline") is True
        assert data_broker.is_subscribed("worker-001", "ETH/USDT", "kline") is False
        assert data_broker.is_subscribed("worker-002", "BTC/USDT", "kline") is False

    def test_get_worker_symbols(self, data_broker):
        """测试获取 Worker 订阅的交易对"""
        data_broker.subscribe("worker-001", ["BTC/USDT", "ETH/USDT"], ["kline"])
        
        symbols = data_broker.get_worker_symbols("worker-001")
        
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols

    def test_get_symbol_workers(self, data_broker):
        """测试获取订阅交易对的所有 Worker"""
        data_broker.subscribe("worker-001", ["BTC/USDT"], ["kline"])
        data_broker.subscribe("worker-002", ["BTC/USDT"], ["kline"])
        
        workers = data_broker.get_symbol_workers("BTC/USDT", "kline")
        
        assert "worker-001" in workers
        assert "worker-002" in workers

    def test_register_preprocessor(self, data_broker):
        """测试注册预处理器"""
        def preprocessor(msg):
            return msg
        
        data_broker.register_preprocessor(preprocessor)
        assert preprocessor in data_broker._data_preprocessors

    def test_unregister_preprocessor(self, data_broker):
        """测试注销预处理器"""
        def preprocessor(msg):
            return msg
        
        data_broker.register_preprocessor(preprocessor)
        data_broker.unregister_preprocessor(preprocessor)
        assert preprocessor not in data_broker._data_preprocessors

    @pytest.mark.asyncio
    async def test_process_message_with_preprocessors(self, data_broker):
        """测试带预处理器的消息处理"""
        def add_field(msg):
            msg.payload["processed"] = True
            return msg
        
        def remove_symbol(msg):
            if "symbol" in msg.payload:
                del msg.payload["symbol"]
            return msg
        
        data_broker.register_preprocessor(add_field)
        data_broker.register_preprocessor(remove_symbol)
        
        msg = Message.create_market_data("BTC/USDT", "kline", {"close": 50000})
        result = await data_broker._process_message(msg)
        
        assert result.payload["processed"] is True
        assert "symbol" not in result.payload

    @pytest.mark.asyncio
    async def test_process_message_preprocessor_returns_none(self, data_broker):
        """测试预处理器返回 None"""
        def filter_msg(msg):
            return None
        
        data_broker.register_preprocessor(filter_msg)
        
        msg = Message.create_market_data("BTC/USDT", "kline", {})
        result = await data_broker._process_message(msg)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_process_message_preprocessor_exception(self, data_broker):
        """测试预处理器异常"""
        def bad_preprocessor(msg):
            raise ValueError("Preprocessor error")
        
        data_broker.register_preprocessor(bad_preprocessor)
        
        msg = Message.create_market_data("BTC/USDT", "kline", {})
        result = await data_broker._process_message(msg)
        
        assert result is None
