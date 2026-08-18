"""
PluginBase 模块单元测试
"""

from unittest.mock import MagicMock, patch

import pytest


class TestPluginBase:
    """测试 PluginBase 类"""

    @pytest.fixture
    def mock_logger(self):
        """模拟 logger"""
        with patch("plugins.plugin_base.get_plugin_logger") as mock_get_logger:
            yield mock_get_logger.return_value

    def test_initialization(self, mock_logger):
        """测试初始化"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        assert plugin.name == "test-plugin"
        assert plugin.version == "1.0.0"
        assert plugin.load_type == "hot"
        assert plugin.is_active is False
        assert plugin.plugin_manager is None

    def test_register(self, mock_logger):
        """测试注册功能"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        mock_manager = MagicMock()
        plugin.register(mock_manager)
        assert plugin.plugin_manager == mock_manager
        mock_logger.info.assert_called_with("插件 test-plugin 注册成功")

    def test_start(self, mock_logger):
        """测试启动功能"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        plugin.start()
        assert plugin.is_active is True
        mock_logger.info.assert_called_with("插件 test-plugin 启动成功")

    def test_stop(self, mock_logger):
        """测试停止功能"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        plugin.start()  # 先启动
        plugin.stop()
        assert plugin.is_active is False
        mock_logger.info.assert_called_with("插件 test-plugin 停止成功")

    def test_get_info(self, mock_logger):
        """测试获取信息"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        info = plugin.get_info()
        assert info["name"] == "test-plugin"
        assert info["version"] == "1.0.0"
        assert info["load_type"] == "hot"
        assert info["is_active"] is False

        plugin.start()
        info = plugin.get_info()
        assert info["is_active"] is True

    def test_get_metadata(self, mock_logger):
        """测试获取元数据"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        metadata = plugin.get_metadata()
        assert metadata["name"] == "test-plugin"
        assert metadata["version"] == "1.0.0"
        assert metadata["description"] == ""
        assert metadata["author"] == ""
        assert metadata["frontend_assets"] is None
        assert metadata["config_schema"] is None

    def test_get_frontend_assets(self, mock_logger):
        """测试获取前端资源"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        assert plugin.get_frontend_assets() is None

    def test_get_config_schema(self, mock_logger):
        """测试获取配置模式"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        assert plugin.get_config_schema() is None

    def test_on_enable(self, mock_logger):
        """测试 on_enable 回调"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        # 不应该抛出异常
        plugin.on_enable()

    def test_on_disable(self, mock_logger):
        """测试 on_disable 回调"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test-plugin", "1.0.0")
        # 不应该抛出异常
        plugin.on_disable()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
