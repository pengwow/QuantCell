"""
数据分发器测试

测试DataDistributor的消费者注册和数据分发功能
"""

import pytest
from unittest.mock import Mock

from realtime.data_distributor import DataDistributor


class TestDataDistributor:
    """测试数据分发器核心功能"""

    def test_initialization(self, data_distributor):
        """测试初始化"""
        assert data_distributor.consumers == {}

    def test_register_consumer_new_type(self, data_distributor):
        """测试注册新类型的消费者"""
        consumer = Mock()
        result = data_distributor.register_consumer('kline', consumer)

        assert result is True
        assert 'kline' in data_distributor.consumers
        assert consumer in data_distributor.consumers['kline']

    def test_register_consumer_existing_type(self, data_distributor):
        """测试向已有类型注册消费者"""
        consumer1 = Mock()
        consumer2 = Mock()

        data_distributor.register_consumer('kline', consumer1)
        result = data_distributor.register_consumer('kline', consumer2)

        assert result is True
        assert len(data_distributor.consumers['kline']) == 2

    def test_unregister_consumer_success(self, data_distributor):
        """测试成功注销消费者"""
        consumer = Mock()
        data_distributor.register_consumer('kline', consumer)

        result = data_distributor.unregister_consumer('kline', consumer)
        assert result is True
        assert consumer not in data_distributor.consumers['kline']

    def test_unregister_consumer_not_exists(self, data_distributor):
        """测试注销不存在的消费者"""
        consumer = Mock()
        result = data_distributor.unregister_consumer('kline', consumer)
        assert result is False

    def test_unregister_consumer_type_not_exists(self, data_distributor):
        """测试注销不存在类型的消费者"""
        consumer = Mock()
        result = data_distributor.unregister_consumer('nonexistent', consumer)
        assert result is False

    def test_distribute_success(self, data_distributor):
        """测试成功分发数据"""
        consumer = Mock()
        data_distributor.register_consumer('kline', consumer)

        data = {'data_type': 'kline', 'symbol': 'BTCUSDT', 'price': 50000}
        result = data_distributor.distribute(data)

        assert result is True
        consumer.assert_called_once_with(data)

    def test_distribute_no_type(self, data_distributor):
        """测试分发缺少类型的数据"""
        data = {'symbol': 'BTCUSDT'}
        result = data_distributor.distribute(data)
        assert result is False

    def test_distribute_no_consumers(self, data_distributor):
        """测试分发给无消费者的数据类型"""
        data = {'data_type': 'kline', 'symbol': 'BTCUSDT'}
        result = data_distributor.distribute(data)
        assert result is True  # 应该成功，只是没有消费者

    def test_distribute_to_wildcard(self, data_distributor):
        """测试分发数据给通配符消费者"""
        consumer = Mock()
        data_distributor.register_consumer('*', consumer)

        data = {'data_type': 'kline', 'symbol': 'BTCUSDT'}
        result = data_distributor.distribute(data)

        assert result is True
        consumer.assert_called_once_with(data)

    def test_broadcast_success(self, data_distributor):
        """测试成功广播数据"""
        consumer1 = Mock()
        consumer2 = Mock()
        data_distributor.register_consumer('kline', consumer1)
        data_distributor.register_consumer('depth', consumer2)

        data = {'data_type': 'kline', 'symbol': 'BTCUSDT'}
        result = data_distributor.broadcast(data)

        assert result is True
        consumer1.assert_called_once_with(data)
        consumer2.assert_called_once_with(data)

    def test_get_consumer_count_specific_type(self, data_distributor):
        """测试获取特定类型的消费者数量"""
        consumer1 = Mock()
        consumer2 = Mock()
        data_distributor.register_consumer('kline', consumer1)
        data_distributor.register_consumer('kline', consumer2)

        count = data_distributor.get_consumer_count('kline')
        assert count == 2

    def test_get_consumer_count_all(self, data_distributor):
        """测试获取所有消费者数量"""
        consumer1 = Mock()
        consumer2 = Mock()
        data_distributor.register_consumer('kline', consumer1)
        data_distributor.register_consumer('depth', consumer2)

        count = data_distributor.get_consumer_count()
        assert count == 2

    def test_clear_consumers_specific_type(self, data_distributor):
        """测试清除特定类型的消费者"""
        consumer = Mock()
        data_distributor.register_consumer('kline', consumer)

        result = data_distributor.clear_consumers('kline')
        assert result is True
        assert 'kline' not in data_distributor.consumers

    def test_clear_consumers_all(self, data_distributor):
        """测试清除所有消费者"""
        consumer1 = Mock()
        consumer2 = Mock()
        data_distributor.register_consumer('kline', consumer1)
        data_distributor.register_consumer('depth', consumer2)

        result = data_distributor.clear_consumers()
        assert result is True
        assert data_distributor.consumers == {}


class TestDataDistributorEdgeCases:
    """测试边界条件和异常场景"""

    def test_distribute_consumer_exception(self, data_distributor):
        """测试消费者抛出异常时的分发"""
        consumer = Mock(side_effect=Exception("Consumer error"))
        data_distributor.register_consumer('kline', consumer)

        data = {'data_type': 'kline', 'symbol': 'BTCUSDT'}
        result = data_distributor.distribute(data)

        # 应该成功，即使消费者抛出异常
        assert result is True
        consumer.assert_called_once()

    def test_broadcast_consumer_exception(self, data_distributor):
        """测试广播时消费者抛出异常"""
        consumer1 = Mock(side_effect=Exception("Error 1"))
        consumer2 = Mock()
        data_distributor.register_consumer('kline', consumer1)
        data_distributor.register_consumer('kline', consumer2)

        data = {'data_type': 'kline', 'symbol': 'BTCUSDT'}
        result = data_distributor.broadcast(data)

        # 应该成功，即使一个消费者抛出异常
        assert result is True
        consumer1.assert_called_once()
        consumer2.assert_called_once()

    def test_register_none_consumer(self, data_distributor):
        """测试注册None作为消费者"""
        result = data_distributor.register_consumer('kline', None)
        assert result is True
        assert None in data_distributor.consumers['kline']

    def test_multiple_data_types(self, data_distributor):
        """测试多种数据类型"""
        kline_consumer = Mock()
        depth_consumer = Mock()

        data_distributor.register_consumer('kline', kline_consumer)
        data_distributor.register_consumer('depth', depth_consumer)

        # 分发K线数据
        kline_data = {'data_type': 'kline', 'symbol': 'BTCUSDT'}
        data_distributor.distribute(kline_data)
        kline_consumer.assert_called_once_with(kline_data)
        depth_consumer.assert_not_called()

        # 分发深度数据
        depth_data = {'data_type': 'depth', 'symbol': 'BTCUSDT'}
        data_distributor.distribute(depth_data)
        depth_consumer.assert_called_once_with(depth_data)

    def test_consumer_called_with_correct_data(self, data_distributor):
        """测试消费者被调用时接收正确的数据"""
        consumer = Mock()
        data_distributor.register_consumer('kline', consumer)

        data = {
            'data_type': 'kline',
            'symbol': 'BTCUSDT',
            'open': 50000,
            'close': 50100
        }
        data_distributor.distribute(data)

        # 验证消费者被调用时接收到的数据
        call_args = consumer.call_args[0][0]
        assert call_args['data_type'] == 'kline'
        assert call_args['symbol'] == 'BTCUSDT'
        assert call_args['open'] == 50000
