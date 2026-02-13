"""
实时监控器测试

测试RealtimeMonitor的统计和监控功能
"""

import pytest
import time
from unittest.mock import Mock, patch

from realtime.monitor import RealtimeMonitor


class TestRealtimeMonitor:
    """测试实时监控器核心功能"""

    def test_initialization(self, realtime_monitor):
        """测试初始化"""
        assert realtime_monitor.interval == 1
        assert realtime_monitor.running is False
        assert realtime_monitor.start_time == 0
        assert realtime_monitor.stats['total_messages'] == 0

    def test_start(self, realtime_monitor):
        """测试启动监控器"""
        result = realtime_monitor.start()
        assert result is True
        assert realtime_monitor.running is True
        assert realtime_monitor.start_time > 0

    def test_start_already_running(self, realtime_monitor):
        """测试启动已在运行的监控器"""
        realtime_monitor.start()
        result = realtime_monitor.start()
        assert result is False

    def test_stop(self, realtime_monitor):
        """测试停止监控器"""
        realtime_monitor.start()
        result = realtime_monitor.stop()
        assert result is True
        assert realtime_monitor.running is False

    def test_stop_not_running(self, realtime_monitor):
        """测试停止未运行的监控器"""
        result = realtime_monitor.stop()
        assert result is False

    def test_reset_stats(self, realtime_monitor):
        """测试重置统计信息"""
        # 先添加一些统计数据
        realtime_monitor.record_message('kline', True, 0.1)
        realtime_monitor.record_connection(True)

        # 重置
        realtime_monitor.reset_stats()

        assert realtime_monitor.stats['total_messages'] == 0
        assert realtime_monitor.stats['total_connections'] == 0
        assert realtime_monitor.stats['processing_times'] == []

    def test_record_connection_success(self, realtime_monitor):
        """测试记录成功连接"""
        realtime_monitor.record_connection(True)
        assert realtime_monitor.stats['total_connections'] == 1
        assert realtime_monitor.stats['successful_connections'] == 1
        assert realtime_monitor.stats['failed_connections'] == 0

    def test_record_connection_failure(self, realtime_monitor):
        """测试记录失败连接"""
        realtime_monitor.record_connection(False)
        assert realtime_monitor.stats['total_connections'] == 1
        assert realtime_monitor.stats['successful_connections'] == 0
        assert realtime_monitor.stats['failed_connections'] == 1

    def test_record_message_success(self, realtime_monitor):
        """测试记录成功消息"""
        realtime_monitor.record_message('kline', True, 0.1)
        assert realtime_monitor.stats['total_messages'] == 1
        assert realtime_monitor.stats['processed_messages'] == 1
        assert realtime_monitor.stats['failed_messages'] == 0

    def test_record_message_failure(self, realtime_monitor):
        """测试记录失败消息"""
        realtime_monitor.record_message('kline', False)
        assert realtime_monitor.stats['total_messages'] == 1
        assert realtime_monitor.stats['processed_messages'] == 0
        assert realtime_monitor.stats['failed_messages'] == 1

    def test_record_message_data_type_stats(self, realtime_monitor):
        """测试记录消息的数据类型统计"""
        realtime_monitor.record_message('kline', True, 0.1)
        realtime_monitor.record_message('kline', False)
        realtime_monitor.record_message('depth', True, 0.05)

        kline_stats = realtime_monitor.stats['data_type_stats']['kline']
        assert kline_stats['total'] == 2
        assert kline_stats['successful'] == 1
        assert kline_stats['failed'] == 1

        depth_stats = realtime_monitor.stats['data_type_stats']['depth']
        assert depth_stats['total'] == 1
        assert depth_stats['successful'] == 1

    def test_record_message_processing_time(self, realtime_monitor):
        """测试记录消息处理时间"""
        realtime_monitor.record_message('kline', True, 0.1)
        realtime_monitor.record_message('kline', True, 0.2)

        assert len(realtime_monitor.stats['processing_times']) == 2
        # 使用近似相等比较浮点数
        assert abs(realtime_monitor.stats['average_processing_time'] - 0.15) < 0.001
        assert abs(realtime_monitor.stats['max_processing_time'] - 0.2) < 0.001
        assert abs(realtime_monitor.stats['min_processing_time'] - 0.1) < 0.001

    def test_get_stats_basic(self, realtime_monitor):
        """测试获取基本统计信息"""
        realtime_monitor.start()
        time.sleep(0.1)  # 等待一段时间

        stats = realtime_monitor.get_stats()

        assert 'uptime' in stats
        assert 'monitor_interval' in stats
        assert 'connections' in stats
        assert 'messages' in stats
        assert stats['uptime'] > 0

    def test_get_stats_connection_success_rate(self, realtime_monitor):
        """测试获取连接成功率"""
        realtime_monitor.record_connection(True)
        realtime_monitor.record_connection(True)
        realtime_monitor.record_connection(False)

        stats = realtime_monitor.get_stats()
        assert abs(stats['connections']['success_rate'] - 2 / 3) < 0.001

    def test_get_stats_message_success_rate(self, realtime_monitor):
        """测试获取消息成功率"""
        realtime_monitor.record_message('kline', True, 0.1)
        realtime_monitor.record_message('kline', True, 0.1)
        realtime_monitor.record_message('kline', False)

        stats = realtime_monitor.get_stats()
        assert abs(stats['messages']['success_rate'] - 2 / 3) < 0.001

    def test_get_stats_performance(self, realtime_monitor):
        """测试获取性能统计"""
        realtime_monitor.record_message('kline', True, 0.1)

        stats = realtime_monitor.get_stats()
        assert 'performance' in stats
        assert stats['performance']['average_processing_time'] == 100  # 转换为毫秒
        assert stats['performance']['max_processing_time'] == 100
        assert stats['performance']['min_processing_time'] == 100

    def test_get_alert_connection_low_success_rate(self, realtime_monitor):
        """测试连接成功率过低告警"""
        # 模拟大量失败连接
        for _ in range(11):
            realtime_monitor.record_connection(False)

        alert = realtime_monitor.get_alert()
        assert alert is not None
        # 检查告警级别和消息内容
        assert alert['level'] == 'warning'
        # 消息中应该包含成功率相关信息
        assert '成功率' in alert['message'] or 'success_rate' in alert['message'].lower()

    def test_get_alert_message_low_success_rate(self, realtime_monitor):
        """测试消息处理成功率过低告警"""
        # 模拟大量失败消息
        for _ in range(101):
            realtime_monitor.record_message('kline', False)

        alert = realtime_monitor.get_alert()
        assert alert is not None
        assert alert['level'] == 'warning'
        # 消息中应该包含成功率相关信息
        assert '成功率' in alert['message'] or 'success_rate' in alert['message'].lower()

    def test_get_alert_high_processing_time(self, realtime_monitor):
        """测试处理时间过长告警"""
        # 模拟处理时间过长（超过100毫秒）
        realtime_monitor.record_message('kline', True, 0.15)

        alert = realtime_monitor.get_alert()
        assert alert is not None
        assert alert['level'] == 'warning'
        # 消息中应该包含处理时间相关信息
        assert '处理时间' in alert['message'] or 'processing_time' in alert['message'].lower() or '时间' in alert['message']

    def test_get_alert_no_alert(self, realtime_monitor):
        """测试无告警情况"""
        # 正常情况，不应触发告警
        realtime_monitor.record_connection(True)
        realtime_monitor.record_message('kline', True, 0.05)

        alert = realtime_monitor.get_alert()
        assert alert is None


class TestRealtimeMonitorEdgeCases:
    """测试边界条件和异常场景"""

    def test_record_message_zero_processing_time(self, realtime_monitor):
        """测试记录零处理时间"""
        realtime_monitor.record_message('kline', True, 0)
        assert realtime_monitor.stats['total_messages'] == 1
        # 零处理时间不应被添加到处理时间列表
        assert len(realtime_monitor.stats['processing_times']) == 0

    def test_get_stats_zero_division(self, realtime_monitor):
        """测试获取统计信息时的零除处理"""
        stats = realtime_monitor.get_stats()
        assert stats['connections']['success_rate'] == 0
        assert stats['messages']['success_rate'] == 0

    def test_min_processing_time_initial(self, realtime_monitor):
        """测试初始最小处理时间"""
        assert realtime_monitor.stats['min_processing_time'] == float('inf')

        stats = realtime_monitor.get_stats()
        # 当没有处理时间记录时，最小处理时间应为0
        assert stats['performance']['min_processing_time'] == 0

    def test_monitor_not_running(self, realtime_monitor):
        """测试监控器未运行时的monitor调用"""
        # 不应抛出异常
        realtime_monitor.monitor()

    @patch('time.time')
    def test_monitor_interval(self, mock_time, realtime_monitor):
        """测试监控间隔"""
        mock_time.return_value = 1000
        realtime_monitor.start()

        # 第一次调用（应该输出报告）
        mock_time.return_value = 1031  # 超过30秒间隔
        with patch.object(realtime_monitor, '_output_monitor_report') as mock_output:
            realtime_monitor.monitor()
            mock_output.assert_called_once()

    def test_record_consumer_event(self, realtime_monitor):
        """测试记录消费者事件"""
        realtime_monitor.record_consumer_event('consumer1', 'kline', True)
        realtime_monitor.record_consumer_event('consumer1', 'kline', False)
        realtime_monitor.record_consumer_event('consumer1', 'depth', True)

        consumer_stats = realtime_monitor.stats['consumer_stats']['consumer1']
        assert consumer_stats['total'] == 3
        assert consumer_stats['successful'] == 2
        assert consumer_stats['failed'] == 1
        assert 'kline' in consumer_stats['data_types']
        assert 'depth' in consumer_stats['data_types']
