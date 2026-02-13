"""
实时配置管理测试

测试RealtimeConfig的配置加载、获取、设置和验证功能
"""

import pytest
from realtime.config import RealtimeConfig


class TestRealtimeConfig:
    """测试实时配置管理核心功能"""

    def test_initialization(self, realtime_config):
        """测试初始化"""
        assert realtime_config.config is not None
        assert 'realtime_enabled' in realtime_config.config
        assert 'data_mode' in realtime_config.config
        assert 'default_exchange' in realtime_config.config

    def test_default_config_values(self, realtime_config):
        """测试默认配置值"""
        assert realtime_config.config['realtime_enabled'] is False
        assert realtime_config.config['data_mode'] == 'cache'
        assert realtime_config.config['default_exchange'] == 'binance'
        assert realtime_config.config['monitor_interval'] == 30

    def test_load_config_success(self, realtime_config):
        """测试成功加载配置"""
        new_config = {
            'realtime_enabled': True,
            'data_mode': 'realtime',
            'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        }
        result = realtime_config.load_config(new_config)

        assert result is True
        assert realtime_config.config['realtime_enabled'] is True
        assert realtime_config.config['data_mode'] == 'realtime'
        assert realtime_config.config['symbols'] == ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

    def test_load_config_failure(self, realtime_config):
        """测试加载配置失败"""
        # 传入无效的配置类型
        result = realtime_config.load_config(None)
        assert result is False

    def test_get_config_all(self, realtime_config):
        """测试获取所有配置"""
        config = realtime_config.get_config()
        assert isinstance(config, dict)
        assert 'realtime_enabled' in config
        assert 'data_mode' in config

    def test_get_config_specific_key(self, realtime_config):
        """测试获取特定配置项"""
        value = realtime_config.get_config('data_mode')
        assert value == 'cache'

    def test_get_config_with_default(self, realtime_config):
        """测试获取配置时使用默认值"""
        value = realtime_config.get_config('non_existent_key', 'default_value')
        assert value == 'default_value'

    def test_set_config_success(self, realtime_config):
        """测试成功设置配置"""
        result = realtime_config.set_config('custom_key', 'custom_value')
        assert result is True
        assert realtime_config.config['custom_key'] == 'custom_value'

    def test_set_config_failure(self, realtime_config):
        """测试设置配置失败"""
        # 尝试设置一个不可哈希的键（会引发异常）
        result = realtime_config.set_config([], 'value')
        assert result is False

    def test_reset_config(self, realtime_config):
        """测试重置配置"""
        # 先修改配置
        realtime_config.set_config('realtime_enabled', True)
        realtime_config.set_config('custom_key', 'custom_value')

        # 重置
        result = realtime_config.reset_config()
        assert result is True

        # 验证配置已重置
        assert realtime_config.config['realtime_enabled'] is False
        assert 'custom_key' not in realtime_config.config

    def test_validate_config_valid(self, realtime_config):
        """测试验证有效配置"""
        result = realtime_config.validate_config()
        assert result is True

    def test_validate_config_invalid_data_mode(self, realtime_config):
        """测试验证无效的数据模式"""
        realtime_config.set_config('data_mode', 'invalid_mode')
        result = realtime_config.validate_config()
        assert result is False

    def test_validate_config_invalid_exchange(self, realtime_config):
        """测试验证无效的交易所"""
        realtime_config.set_config('default_exchange', 'invalid_exchange')
        result = realtime_config.validate_config()
        assert result is False

    def test_validate_config_invalid_realtime_enabled(self, realtime_config):
        """测试验证无效的实时引擎开关"""
        realtime_config.set_config('realtime_enabled', 'not_a_boolean')
        result = realtime_config.validate_config()
        assert result is False

    def test_validate_config_invalid_symbols(self, realtime_config):
        """测试验证无效的符号列表"""
        realtime_config.set_config('symbols', 'not_a_list')
        result = realtime_config.validate_config()
        assert result is False

    def test_validate_config_invalid_data_types(self, realtime_config):
        """测试验证无效的数据类型列表"""
        realtime_config.set_config('data_types', 'not_a_list')
        result = realtime_config.validate_config()
        assert result is False

    def test_validate_config_invalid_intervals(self, realtime_config):
        """测试验证无效的时间间隔列表"""
        realtime_config.set_config('intervals', 'not_a_list')
        result = realtime_config.validate_config()
        assert result is False


class TestRealtimeConfigEdgeCases:
    """测试边界条件和异常场景"""

    def test_load_config_empty_dict(self, realtime_config):
        """测试加载空配置字典"""
        result = realtime_config.load_config({})
        assert result is True
        # 配置应该保持不变
        assert realtime_config.config['realtime_enabled'] is False

    def test_get_config_none_key(self, realtime_config):
        """测试使用None作为键获取配置"""
        config = realtime_config.get_config(None)
        assert isinstance(config, dict)
        assert 'realtime_enabled' in config

    def test_config_isolation(self, realtime_config):
        """测试配置隔离性"""
        # 获取配置
        config1 = realtime_config.get_config()
        # 修改返回的配置
        config1['new_key'] = 'new_value'
        # 验证原始配置未被修改
        assert 'new_key' not in realtime_config.config

    def test_default_config_not_modified(self, realtime_config):
        """测试默认配置未被修改"""
        original_default = realtime_config.default_config.copy()

        # 修改当前配置
        realtime_config.set_config('realtime_enabled', True)

        # 验证默认配置未被修改
        assert realtime_config.default_config == original_default

    def test_symbols_list_content(self, realtime_config):
        """测试符号列表内容"""
        symbols = realtime_config.get_config('symbols')
        assert isinstance(symbols, list)
        assert 'BTCUSDT' in symbols
        assert 'ETHUSDT' in symbols

    def test_data_types_list_content(self, realtime_config):
        """测试数据类型列表内容"""
        data_types = realtime_config.get_config('data_types')
        assert isinstance(data_types, list)
        assert 'kline' in data_types

    def test_intervals_list_content(self, realtime_config):
        """测试时间间隔列表内容"""
        intervals = realtime_config.get_config('intervals')
        assert isinstance(intervals, list)
        assert '1m' in intervals
        assert '5m' in intervals
