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


class TestRestartRequiredPolicy:
    """所有插件统一"重启后生效"策略的测试"""

    @staticmethod
    def _make_recording_store(plugin_info=None):
        """记录 save_plugin / update_status 调用的 store 桩"""

        class RecordingStore:
            saved_metadata = None
            status_updates = []

            @classmethod
            def get_all_plugins(cls):
                return []

            @classmethod
            def get_plugin(cls, name):
                return plugin_info

            @classmethod
            def save_plugin(cls, metadata):
                cls.saved_metadata = metadata
                return True

            @classmethod
            def update_status(cls, name, status, error_message=None):
                cls.status_updates.append((name, status))
                return True

            @classmethod
            def delete_plugin(cls, name):
                return True

        return RecordingStore

    def test_install_marks_pending_restart_ignoring_manifest_load_type(self, tmp_path):
        """安装后统一为 pending_restart + restart，即使 manifest 声明 hot，也不触发运行期加载"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager(plugin_dir=str(tmp_path))
        store = self._make_recording_store()
        pm._store = store
        # 间谍：若安装流程触发加载应立即暴露
        pm.load_plugin = MagicMock(side_effect=AssertionError("安装后不应运行期加载插件"))

        manifest = {
            "name": "demo_plugin",
            "version": "1.0.0",
            "load_type": "hot",  # manifest 即使声明热加载也必须被忽略
        }
        assert pm.install_plugin(str(tmp_path / "demo_plugin"), manifest) is True

        meta = store.saved_metadata
        assert meta["status"] == "pending_restart"
        assert meta["load_type"] == "restart"
        assert pm.plugins == {}
        pm.load_plugin.assert_not_called()

    def test_enable_unloaded_plugin_marks_pending_restart(self, tmp_path):
        """运行期启用未加载插件：只标记 pending_restart，不动态加载"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager(plugin_dir=str(tmp_path))
        store = self._make_recording_store(plugin_info={"name": "demo_plugin", "status": "disabled"})
        pm._store = store
        pm.load_plugin = MagicMock(side_effect=AssertionError("未加载插件不应运行期动态加载"))

        assert pm.enable_plugin("demo_plugin") is True

        assert store.status_updates == [("demo_plugin", "pending_restart")]
        pm.load_plugin.assert_not_called()

    def test_enable_loaded_plugin_takes_effect_immediately(self, tmp_path):
        """启动时已加载的插件启用：直接 on_enable 并标记 enabled（无需重启）"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager(plugin_dir=str(tmp_path))
        store = self._make_recording_store(plugin_info={"name": "demo_plugin", "status": "disabled"})
        pm._store = store

        running_plugin = MagicMock()
        pm.plugins["demo_plugin"] = running_plugin

        assert pm.enable_plugin("demo_plugin") is True

        running_plugin.on_enable.assert_called_once()
        assert store.status_updates == [("demo_plugin", "enabled")]

    def test_enable_nonexistent_plugin_returns_false(self, tmp_path):
        """启用不存在的插件返回 False"""
        from plugins.plugin_manager import PluginManager

        pm = PluginManager(plugin_dir=str(tmp_path))
        pm._store = self._make_recording_store(plugin_info=None)

        assert pm.enable_plugin("ghost") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
