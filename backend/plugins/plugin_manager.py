import importlib.util
import json
import os
import re
import shutil
import sys
from typing import Dict, List, Optional

from fastapi import FastAPI

from utils.logger import get_logger, LogType
from .plugin_base import PluginBase
from .plugin_store import PluginStore
from .plugin_loader import HotPluginLoader, RestartPluginLoader, unload_plugin
from .event_bus import EventBus
from .plugin_installer import PluginInstaller

try:
    from .plugin_security import validate_permissions
except ImportError:
    def validate_permissions(permissions: list) -> tuple:
        return True, ""

logger = get_logger(__name__, LogType.APPLICATION)

SYSTEM_VERSION = "1.0.0"


def _parse_version(version_str: str) -> tuple:
    parts = version_str.strip().split(".")
    return tuple(int(p) for p in parts)


class PluginManager:

    def __init__(self, app: Optional[FastAPI] = None, plugin_dir: Optional[str] = None):
        self._app = app
        self.plugin_dir = plugin_dir or os.path.dirname(os.path.abspath(__file__))
        self.plugins: Dict[str, PluginBase] = {}
        self.plugin_configs: Dict[str, dict] = {}
        self._loaded_modules: Dict[str, object] = {}
        self._hot_loader = HotPluginLoader()
        self._restart_loader = RestartPluginLoader()
        self._event_bus = EventBus()
        self._store = PluginStore

    def scan_plugins(self) -> List[str]:
        if not os.path.exists(self.plugin_dir):
            logger.warning(f"插件目录不存在: {self.plugin_dir}")
            return []

        existing_names = set()
        all_db_plugins = self._store.get_all_plugins()
        for p in all_db_plugins:
            existing_names.add(p["name"])

        discovered = []
        for item in os.listdir(self.plugin_dir):
            item_path = os.path.join(self.plugin_dir, item)
            if not os.path.isdir(item_path):
                continue
            manifest_path = os.path.join(item_path, "manifest.json")
            if not os.path.exists(manifest_path):
                continue
            if item not in existing_names:
                discovered.append(item)

        logger.info(f"扫描到 {len(discovered)} 个新插件: {discovered}")
        return discovered

    def load_all_plugins(self):
        all_plugins = self._store.get_all_plugins()
        logger.info(f"从数据库读取到 {len(all_plugins)} 个插件")

        for plugin_info in all_plugins:
            name = plugin_info["name"]
            status = plugin_info.get("status", "installed")
            if status == "disabled":
                logger.info(f"插件 {name} 已禁用，跳过加载")
                continue

            install_path = plugin_info.get("install_path")
            plugin_dir_path = install_path or os.path.join(self.plugin_dir, name)
            if not os.path.isdir(plugin_dir_path):
                logger.error(f"插件 {name} 目录不存在: {plugin_dir_path}")
                self._store.update_status(name, "error", f"插件目录不存在: {plugin_dir_path}")
                continue

            plugin = self.load_plugin(name)
            if plugin is None:
                self._store.update_status(name, "error", "加载失败")

    def load_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        plugin_info = self._store.get_plugin(plugin_name)
        if plugin_info is None:
            plugin_dir_path = os.path.join(self.plugin_dir, plugin_name)
            if not os.path.isdir(plugin_dir_path):
                logger.error(f"插件 {plugin_name} 不存在")
                return None
        else:
            install_path = plugin_info.get("install_path")
            plugin_dir_path = install_path or os.path.join(self.plugin_dir, plugin_name)

        load_type = "hot"
        if plugin_info:
            load_type = plugin_info.get("load_type", "hot")

        if self._app is not None:
            loader = self._hot_loader if load_type == "hot" else self._restart_loader
            plugin = loader.load_plugin(plugin_dir_path, self._app)
        else:
            plugin = self._load_plugin_without_app(plugin_dir_path, load_type)

        if plugin is None:
            logger.error(f"加载插件 {plugin_name} 失败")
            return None

        plugin.plugin_manager = self
        self.plugins[plugin_name] = plugin
        self._loaded_modules[plugin_name] = sys.modules.get(f"plugins.hot.{plugin_name}") or sys.modules.get(f"plugins.restart.{plugin_name}")

        if plugin_info:
            self._store.update_status(plugin_name, "enabled")

        self._event_bus.publish("plugin.loaded", {"name": plugin_name})
        logger.info(f"插件 {plugin_name} 加载成功")
        return plugin

    def _ensure_plugin_namespace(self, load_type: str, plugin_dir: str):
        """确保 plugins.hot / plugins.restart 命名空间包存在，并将插件目录加入 __path__ 以支持相对导入"""
        import types
        if "plugins" not in sys.modules:
            plugins_pkg = types.ModuleType("plugins")
            plugins_pkg.__path__ = []
            sys.modules["plugins"] = plugins_pkg
        ns_name = f"plugins.{load_type}"
        if ns_name not in sys.modules:
            ns_pkg = types.ModuleType(ns_name)
            ns_pkg.__path__ = []
            sys.modules[ns_name] = ns_pkg
        ns_pkg = sys.modules[ns_name]
        if plugin_dir not in ns_pkg.__path__:
            ns_pkg.__path__.append(plugin_dir)

    def _load_plugin_without_app(self, plugin_dir: str, load_type: str) -> Optional[PluginBase]:
        manifest_path = os.path.join(plugin_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            logger.error(f"manifest.json 不存在: {manifest_path}")
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            main_file = manifest.get("main", "main.py")
            plugin_name = manifest.get("name", os.path.basename(plugin_dir))
            module_path = os.path.join(plugin_dir, main_file)

            if not os.path.exists(module_path):
                logger.error(f"入口文件不存在: {module_path}")
                return None

            self._ensure_plugin_namespace(load_type, plugin_dir)

            module_name = f"plugins.{load_type}.{plugin_name}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.error(f"无法创建模块规格: {module_path}")
                return None

            plugin_module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = plugin_module
            spec.loader.exec_module(plugin_module)

            if not hasattr(plugin_module, "register_plugin"):
                logger.error(f"插件入口文件缺少 register_plugin 函数: {module_path}")
                return None

            plugin = plugin_module.register_plugin()

            if not isinstance(plugin, PluginBase):
                logger.error(f"register_plugin 返回值不是 PluginBase 实例: {type(plugin)}")
                return None

            plugin.load_type = load_type
            plugin.register(self)
            plugin.start()

            return plugin
        except Exception as e:
            logger.error(f"加载插件失败: {plugin_dir}, {e}")
            return None

    def unload_plugin(self, plugin_name: str) -> bool:
        if plugin_name not in self.plugins:
            logger.warning(f"插件 {plugin_name} 未加载")
            return False

        if self._app is not None:
            result = unload_plugin(plugin_name, self._app, self.plugins, self._loaded_modules)
        else:
            plugin = self.plugins.get(plugin_name)
            if plugin:
                try:
                    plugin.stop()
                except Exception:
                    pass
            self.plugins.pop(plugin_name, None)
            self._loaded_modules.pop(plugin_name, None)
            result = True

        if result:
            self._store.update_status(plugin_name, "installed")
            self._event_bus.publish("plugin.unloaded", {"name": plugin_name})
        return result

    def _validate_manifest(self, manifest: dict) -> tuple:
        name = manifest.get("name")
        if not name:
            return False, "manifest 缺少 name 字段"
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, f"插件名称格式不合法: {name}，仅允许字母、数字、下划线、连字符"

        version = manifest.get("version")
        if not version:
            return False, "manifest 缺少 version 字段"

        main = manifest.get("main", "main.py")
        if not main:
            return False, "manifest 缺少 main 字段"

        return True, ""

    def _check_version_compatibility(self, manifest: dict) -> bool:
        min_version = manifest.get("min_system_version")
        if not min_version:
            return True
        try:
            return _parse_version(SYSTEM_VERSION) >= _parse_version(min_version)
        except (ValueError, TypeError):
            logger.warning(f"版本号解析失败: min_system_version={min_version}")
            return False

    def install_plugin(self, plugin_dir_path: str, manifest: dict, source_type: str = "manual") -> bool:
        valid, msg = self._validate_manifest(manifest)
        if not valid:
            logger.error(f"manifest 校验失败: {msg}")
            return False

        if not self._check_version_compatibility(manifest):
            min_ver = manifest.get("min_system_version")
            logger.error(f"插件要求系统最低版本 {min_ver}，当前系统版本 {SYSTEM_VERSION}")
            return False

        permissions = manifest.get("permissions", [])
        perm_valid, perm_msg = validate_permissions(permissions)
        if not perm_valid:
            logger.error(f"权限校验失败: {perm_msg}")
            return False

        name = manifest["name"]
        metadata = {
            "name": name,
            "version": manifest.get("version", "0.0.0"),
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "load_type": manifest.get("load_type", "hot"),
            "status": "installed",
            "install_source": source_type,
            "install_path": plugin_dir_path,
            "permissions": permissions,
            "config_schema": manifest.get("config_schema"),
            "frontend_entry": manifest.get("frontend_entry"),
        }

        saved = self._store.save_plugin(metadata)
        if not saved:
            logger.error(f"保存插件元数据失败: {name}")
            return False

        self._event_bus.publish("plugin.installed", {"name": name})

        load_type = manifest.get("load_type", "hot")
        if load_type == "hot":
            plugin = self.load_plugin(name)
            if plugin is None:
                self._store.update_status(name, "error", "安装后自动加载失败")
                logger.warning(f"插件 {name} 安装成功但加载失败，状态已标记为 error")
                return True

        logger.info(f"插件 {name} 安装成功")
        return True

    def uninstall_plugin(self, plugin_name: str) -> bool:
        if plugin_name in self.plugins:
            if not self.unload_plugin(plugin_name):
                logger.error(f"卸载插件 {plugin_name} 失败，取消卸载操作")
                return False

        plugin_info = self._store.get_plugin(plugin_name)
        install_path = None
        if plugin_info:
            install_path = plugin_info.get("install_path") or os.path.join(self.plugin_dir, plugin_name)

        deleted = self._store.delete_plugin(plugin_name)
        if deleted:
            if install_path and os.path.isdir(install_path):
                try:
                    shutil.rmtree(install_path)
                    logger.info(f"插件目录已删除: {install_path}")
                except OSError as e:
                    logger.warning(f"删除插件目录失败: {install_path}, 错误: {e}")
            self._event_bus.publish("plugin.uninstalled", {"name": plugin_name})
            logger.info(f"插件 {plugin_name} 已卸载")
        return deleted

    def enable_plugin(self, plugin_name: str) -> bool:
        plugin_info = self._store.get_plugin(plugin_name)
        if not plugin_info:
            logger.error(f"插件 {plugin_name} 不存在")
            return False

        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.on_enable()
            self._store.update_status(plugin_name, "enabled")
            logger.info(f"插件 {plugin_name} 已启用")
            return True

        plugin = self.load_plugin(plugin_name)
        if plugin is None:
            return False

        plugin.on_enable()
        self._store.update_status(plugin_name, "enabled")
        logger.info(f"插件 {plugin_name} 已启用")
        return True

    def disable_plugin(self, plugin_name: str) -> bool:
        plugin_info = self._store.get_plugin(plugin_name)
        if not plugin_info:
            logger.error(f"插件 {plugin_name} 不存在")
            return False

        if plugin_name in self.plugins:
            plugin = self.plugins[plugin_name]
            plugin.on_disable()
            self.unload_plugin(plugin_name)

        self._store.update_status(plugin_name, "disabled")
        logger.info(f"插件 {plugin_name} 已禁用")
        return True

    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        return self.plugins.get(plugin_name)

    def get_all_plugins_info(self) -> List[dict]:
        return self._store.get_all_plugins()

    def stop_all_plugins(self):
        plugin_names = list(self.plugins.keys())
        for name in reversed(plugin_names):
            plugin = self.plugins.get(name)
            if plugin is None:
                continue
            try:
                plugin.stop()
                logger.info(f"插件 {name} 已停止")
            except Exception as e:
                logger.error(f"停止插件 {name} 失败: {e}")

    def register_plugins(self, app: Optional[FastAPI] = None):
        target_app = app or self._app
        if target_app is None:
            logger.error("未提供 FastAPI 实例，无法注册路由")
            return

        self._app = target_app

        for name, plugin in self.plugins.items():
            try:
                router = getattr(plugin, "router", None)
                if router is not None:
                    target_app.include_router(router)
            except Exception as e:
                logger.error(f"注册插件路由 {name} 失败: {e}")

    def register_plugin_config(self, plugin_name: str, config: dict):
        self.plugin_configs[plugin_name] = config

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def install_from_zip(self, zip_file_path: str) -> tuple[bool, str]:
        installer = PluginInstaller(self.plugin_dir, self)
        return installer.install_from_zip(zip_file_path)

    def install_from_zip_bytes(self, zip_bytes: bytes, filename: str = "plugin.zip") -> tuple[bool, str]:
        installer = PluginInstaller(self.plugin_dir, self)
        return installer.install_from_zip_bytes(zip_bytes, filename)

    def install_from_git(self, git_url: str, branch: Optional[str] = None) -> tuple[bool, str]:
        installer = PluginInstaller(self.plugin_dir, self)
        return installer.install_from_git(git_url, branch)
