"""
EventBus 模块单元测试
"""

from unittest.mock import MagicMock

import pytest


class TestEventBus:
    """测试 EventBus 类"""

    @pytest.fixture
    def event_bus(self):
        """创建 EventBus 实例用于测试"""
        from plugins.event_bus import EventBus

        return EventBus()

    def test_initial_state(self, event_bus):
        """测试初始状态"""
        assert len(event_bus._subscribers) == 0
        assert event_bus.get_subscribers("test.event") == []

    def test_subscribe(self, event_bus):
        """测试订阅功能"""
        callback = MagicMock()
        event_bus.subscribe("test.event", callback)

        subscribers = event_bus.get_subscribers("test.event")
        assert len(subscribers) == 1
        assert callback.__name__ in subscribers

    def test_unsubscribe(self, event_bus):
        """测试取消订阅功能"""
        callback = MagicMock()
        event_bus.subscribe("test.event", callback)

        event_bus.unsubscribe("test.event", callback)
        assert len(event_bus.get_subscribers("test.event")) == 0

    def test_unsubscribe_nonexistent(self, event_bus):
        """测试取消不存在的订阅"""
        callback = MagicMock()
        # 不应该抛出异常
        event_bus.unsubscribe("test.event", callback)

    def test_publish(self, event_bus):
        """测试发布事件"""
        callback1 = MagicMock()
        callback2 = MagicMock()

        event_bus.subscribe("test.event", callback1)
        event_bus.subscribe("test.event", callback2)

        event_data = {"key": "value"}
        event_bus.publish("test.event", event_data)

        callback1.assert_called_once_with(event_data)
        callback2.assert_called_once_with(event_data)

    def test_publish_no_subscribers(self, event_bus):
        """测试发布没有订阅者的事件"""
        # 不应该抛出异常
        event_bus.publish("test.event", {"key": "value"})

    def test_publish_with_exception(self, event_bus):
        """测试发布事件时订阅者抛出异常"""
        callback = MagicMock(side_effect=Exception("Test exception"))
        event_bus.subscribe("test.event", callback)

        # 不应该抛出异常
        event_bus.publish("test.event", {"key": "value"})
        callback.assert_called_once()

    def test_multiple_events(self, event_bus):
        """测试多个不同事件"""
        callback1 = MagicMock()
        callback2 = MagicMock()

        event_bus.subscribe("event1", callback1)
        event_bus.subscribe("event2", callback2)

        event_bus.publish("event1", "data1")
        event_bus.publish("event2", "data2")

        callback1.assert_called_once_with("data1")
        callback2.assert_called_once_with("data2")

    def test_clear(self, event_bus):
        """测试清除所有订阅"""
        callback1 = MagicMock()
        callback2 = MagicMock()

        event_bus.subscribe("event1", callback1)
        event_bus.subscribe("event2", callback2)

        event_bus.clear()
        assert len(event_bus._subscribers) == 0

    def test_duplicate_subscription(self, event_bus):
        """测试重复订阅同一个回调"""
        callback = MagicMock()

        event_bus.subscribe("test.event", callback)
        event_bus.subscribe("test.event", callback)

        assert len(event_bus.get_subscribers("test.event")) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
