"""
插件模块单元测试
"""

import json
import sys
from unittest.mock import MagicMock

import pytest


# Mock plugin_store completely to avoid pytz and sqlalchemy
class MockPluginStore:
    @staticmethod
    def get_all_plugins():
        return []

    @staticmethod
    def get_plugin(name):
        return None

    @staticmethod
    def save_plugin(metadata):
        return True

    @staticmethod
    def update_status(name, status, error_message=None):
        return True

    @staticmethod
    def delete_plugin(name):
        return True


@pytest.fixture(scope="module", autouse=True)
def _isolate_plugin_deps():
    """注入隔离桩，模块测试结束后手动恢复原模块。

    此前是模块级裸写 sys.modules["utils.logger"/"collector"/"fastapi"] = MagicMock，
    全量测试时这些顶层包被永久 Mock 化，导致后续集成测试出现
    "collector.db is not a package"、"isinstance() arg 2 must be a type"
    等连锁错误。
    注：monkeypatch 为 function 级 fixture，无法被 module 级请求，
    故这里用 saved/orig 字典手动恢复。
    """
    mock_logger = MagicMock()
    injected: dict[str, MagicMock] = {}

    utils_logger = MagicMock()
    utils_logger.get_logger = MagicMock(return_value=mock_logger)
    utils_logger.get_plugin_logger = MagicMock(return_value=mock_logger)
    utils_logger.LogType = MagicMock()
    injected["utils.logger"] = utils_logger

    collector = MagicMock()
    collector_db = MagicMock()
    collector_db.database = MagicMock()
    collector_db.models = MagicMock()
    collector.db = collector_db
    injected["collector"] = collector
    injected["collector.db"] = collector_db
    injected["collector.db.database"] = collector_db.database
    injected["collector.db.models"] = collector_db.models

    fastapi_mod = MagicMock()
    fastapi_mod.FastAPI = MagicMock()
    injected["fastapi"] = fastapi_mod

    injected["plugins.event_bus"] = MagicMock()
    injected["plugins.plugin_loader"] = MagicMock()
    injected["plugins.plugin_installer"] = MagicMock()
    plugin_store_stub = MagicMock()
    plugin_store_stub.PluginStore = MockPluginStore
    injected["plugins.plugin_store"] = plugin_store_stub

    saved: dict[str, object | None] = {}
    for name, stub in injected.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = stub
    yield
    for name, orig in saved.items():
        if orig is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = orig


class TestPluginBase:
    """测试 PluginBase 类"""

    def test_initialization(self):
        """测试初始化"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test_plugin", "1.0.0")

        assert plugin.name == "test_plugin"
        assert plugin.version == "1.0.0"
        assert plugin.load_type == "hot"
        assert plugin.is_active is False
        assert plugin.plugin_manager is None

    def test_get_info(self):
        """测试 get_info 方法"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test_plugin", "1.0.0")

        info = plugin.get_info()
        assert info["name"] == "test_plugin"
        assert info["version"] == "1.0.0"
        assert info["load_type"] == "hot"
        assert info["is_active"] is False

    def test_start_stop(self):
        """测试 start 和 stop 方法"""
        from plugins.plugin_base import PluginBase

        plugin = PluginBase("test_plugin", "1.0.0")

        plugin.start()
        assert plugin.is_active is True

        plugin.stop()
        assert plugin.is_active is False


class TestPluginManager:
    """测试 PluginManager 类"""

    def test_parse_version(self):
        """测试 _parse_version 函数"""
        from plugins.plugin_manager import _parse_version

        assert _parse_version("1.0.0") == (1, 0, 0)
        assert _parse_version("2.5.10") == (2, 5, 10)
        with pytest.raises(ValueError):
            _parse_version("invalid")

    def test_validate_manifest(self):
        """测试 _validate_manifest 方法"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager()

        # 测试正常的 manifest
        valid_manifest = {"name": "test_plugin", "version": "1.0.0"}
        valid, msg = pm._validate_manifest(valid_manifest)
        assert valid is True
        assert msg == ""

        # 测试缺少 name
        invalid_manifest = {"version": "1.0.0"}
        valid, msg = pm._validate_manifest(invalid_manifest)
        assert valid is False
        assert "缺少 name 字段" in msg

        # 测试非法 name 格式
        invalid_manifest = {"name": "test plugin", "version": "1.0.0"}
        valid, msg = pm._validate_manifest(invalid_manifest)
        assert valid is False
        assert "格式不合法" in msg

        # 测试缺少 version
        invalid_manifest = {"name": "test_plugin"}
        valid, msg = pm._validate_manifest(invalid_manifest)
        assert valid is False
        assert "缺少 version 字段" in msg

    def test_check_version_compatibility(self):
        """测试 _check_version_compatibility 方法"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager()

        # 无最低版本要求
        manifest = {}
        assert pm._check_version_compatibility(manifest) is True

        # 当前版本 >= 最低版本
        manifest = {"min_system_version": "0.9.0"}
        assert pm._check_version_compatibility(manifest) is True

        # 当前版本 < 最低版本
        manifest = {"min_system_version": "2.0.0"}
        assert pm._check_version_compatibility(manifest) is False

        # 无效版本号
        manifest = {"min_system_version": "invalid"}
        assert pm._check_version_compatibility(manifest) is False

    def test_scan_plugins_empty_dir(self, tmp_path):
        """测试扫描空插件目录"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager(plugin_dir=str(tmp_path))

        discovered = pm.scan_plugins()
        assert discovered == []

    def test_scan_plugins_new_plugin(self, tmp_path):
        """测试扫描新插件"""
        from plugins.plugin_manager import PluginManager

        # 创建插件目录和 manifest
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        manifest = {"name": "test_plugin", "version": "1.0.0"}
        (plugin_dir / "manifest.json").write_text(json.dumps(manifest))

        pm = PluginManager(plugin_dir=str(tmp_path))

        discovered = pm.scan_plugins()
        assert "test_plugin" in discovered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
