# -*- coding: utf-8 -*-
"""
PluginManager 模块单元测试
"""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


class TestPluginManager:
    """测试 PluginManager 类
    """

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """创建临时目录
        """
        return tmp_path

    @pytest.fixture
    def mock_store(self):
        """模拟 PluginStore
        """
        with patch("plugins.plugin_manager.PluginStore") as mock:
            mock.get_all_plugins.return_value = []
            mock.get_plugin.return_value = None
            mock.save_plugin.return_value = True
            mock.update_status.return_value = True
            mock.delete_plugin.return_value = True
            yield mock

    @pytest.fixture
    def mock_logger(self):
        """模拟 logger
        """
        with patch("plugins.plugin_manager.logger") as mock:
            yield mock

    @pytest.fixture
    def plugin_manager(self, temp_dir, mock_store, mock_logger):
        """创建 PluginManager 实例
        """
        from plugins.plugin_manager import PluginManager
        return PluginManager(plugin_dir=str(temp_dir))

    def test_initialization(self, temp_dir, mock_store, mock_logger):
        """测试初始化
        """
        from plugins.plugin_manager import PluginManager

        pm = PluginManager(plugin_dir=str(temp_dir))
        assert pm.plugin_dir == str(temp_dir)
        assert pm.plugins == {}
        assert pm.plugin_configs == {}

    def test_scan_plugins_no_directory(self, plugin_manager, temp_dir):
        """测试扫描不存在的插件目录
        """
        result = plugin_manager.scan_plugins()
        assert result == []

    def test_scan_plugins_empty_directory(self, plugin_manager, temp_dir, mock_store):
        """测试扫描空插件目录
        """
        plugins_dir = temp_dir
        os.makedirs(plugins_dir, exist_ok=True)
        plugin_manager.plugin_dir = str(plugins_dir)
        mock_store.get_all_plugins.return_value = []

        result = plugin_manager.scan_plugins()
        assert result == []

    def test_scan_plugins_with_plugins(self, plugin_manager, temp_dir, mock_store):
        """测试扫描有插件的目录
        """
        plugins_dir = temp_dir / "plugins"
        os.makedirs(plugins_dir, exist_ok=True)

        # 创建测试插件目录
        test_plugin_dir = plugins_dir / "test-plugin"
        os.makedirs(test_plugin_dir)

        # 创建 manifest.json
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "main": "main.py"
        }
        with open(test_plugin_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        plugin_manager.plugin_dir = str(plugins_dir)
        mock_store.get_all_plugins.return_value = []

        result = plugin_manager.scan_plugins()
        assert "test-plugin" in result

    def test_validate_manifest_valid(self, plugin_manager):
        """测试验证有效的 manifest
        """
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "main": "main.py"
        }
        valid, msg = plugin_manager._validate_manifest(manifest)
        assert valid is True
        assert msg == ""

    def test_validate_manifest_missing_name(self, plugin_manager):
        """测试验证缺少 name 的 manifest
        """
        manifest = {
            "version": "1.0.0",
            "main": "main.py"
        }
        valid, msg = plugin_manager._validate_manifest(manifest)
        assert valid is False
        assert "缺少 name 字段" in msg

    def test_validate_manifest_invalid_name(self, plugin_manager):
        """测试验证名称格式不合法的 manifest
        """
        manifest = {
            "name": "test plugin",  # 包含空格
            "version": "1.0.0",
            "main": "main.py"
        }
        valid, msg = plugin_manager._validate_manifest(manifest)
        assert valid is False
        assert "格式不合法" in msg

    def test_validate_manifest_missing_version(self, plugin_manager):
        """测试验证缺少 version 的 manifest
        """
        manifest = {
            "name": "test-plugin",
            "main": "main.py"
        }
        valid, msg = plugin_manager._validate_manifest(manifest)
        assert valid is False
        assert "缺少 version 字段" in msg

    def test_parse_version(self, plugin_manager):
        """测试解析版本号
        """
        from plugins.plugin_manager import _parse_version

        assert _parse_version("1.0.0") == (1, 0, 0)
        assert _parse_version("2.1.3") == (2, 1, 3)

    def test_check_version_compatibility(self, plugin_manager):
        """测试检查版本兼容性
        """
        from plugins.plugin_manager import SYSTEM_VERSION

        # 没有要求最低版本
        manifest = {"name": "test", "version": "1.0.0", "main": "main.py"}
        assert plugin_manager._check_version_compatibility(manifest) is True

        # 要求低于当前版本
        manifest["min_system_version"] = "0.1.0"
        assert plugin_manager._check_version_compatibility(manifest) is True

        # 要求高于当前版本
        manifest["min_system_version"] = "999.999.999"
        assert plugin_manager._check_version_compatibility(manifest) is False

        # 无效版本格式错误
        manifest["min_system_version"] = "invalid"
        assert plugin_manager._check_version_compatibility(manifest) is False

    def test_get_plugin(self, plugin_manager, temp_dir):
        """测试获取插件
        """
        plugin = plugin_manager.get_plugin("nonexistent")
        assert plugin is None

    def test_get_all_plugins_info(self, plugin_manager, mock_store):
        """测试获取所有插件信息
        """
        mock_plugins = [
            {"name": "plugin1", "version": "1.0.0"},
            {"name": "plugin2", "version": "2.0.0"}
        ]
        mock_store.get_all_plugins.return_value = mock_plugins

        result = plugin_manager.get_all_plugins_info()
        assert result == mock_plugins

    def test_register_plugin_config(self, plugin_manager):
        """测试注册插件配置
        """
        plugin_manager.register_plugin_config("test-plugin", {"key": "value"})
        assert plugin_manager.plugin_configs["test-plugin"] == {"key": "value"}

    def test_event_bus_property(self, plugin_manager):
        """测试 event_bus 属性
        """
        from plugins.event_bus import EventBus
        assert isinstance(plugin_manager.event_bus, EventBus)

    @patch("plugins.plugin_manager.PluginInstaller")
    def test_install_from_zip(self, mock_installer_class, plugin_manager):
        """测试从 zip 安装插件
        """
        mock_installer = mock_installer_class.return_value
        mock_installer.install_from_zip.return_value = (True, "Success")

        result = plugin_manager.install_from_zip("/path/to/plugin.zip")
        assert result == (True, "Success")

    @patch("plugins.plugin_manager.PluginInstaller")
    def test_install_from_zip_bytes(self, mock_installer_class, plugin_manager):
        """测试从 zip 字节安装插件
        """
        mock_installer = mock_installer_class.return_value
        mock_installer.install_from_zip_bytes.return_value = (True, "Success")

        result = plugin_manager.install_from_zip_bytes(b"zip-data")
        assert result == (True, "Success")

    @patch("plugins.plugin_manager.PluginInstaller")
    def test_install_from_git(self, mock_installer_class, plugin_manager):
        """测试从 git 安装插件
        """
        mock_installer = mock_installer_class.return_value
        mock_installer.install_from_git.return_value = (True, "Success")

        result = plugin_manager.install_from_git("https://github.com/test/plugin.git")
        assert result == (True, "Success")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
