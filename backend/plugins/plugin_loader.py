import importlib
import importlib.util
import json
import os
import sys
import traceback
import types

from fastapi import APIRouter, FastAPI

from utils.logger import LogType, get_logger

from .plugin_base import PluginBase

logger = get_logger(__name__, LogType.APPLICATION)


def _ensure_plugin_namespace(load_type: str, plugin_dir: str = ""):
    """确保 plugins.hot / plugins.restart 命名空间包存在，并将插件目录加入 __path__ 以支持相对导入"""
    if "plugins" not in sys.modules:
        plugins_pkg = types.ModuleType("plugins")
        plugins_pkg.__path__ = []
        sys.modules["plugins"] = plugins_pkg
    ns_name = f"plugins.{load_type}"
    if ns_name not in sys.modules:
        ns_pkg = types.ModuleType(ns_name)
        ns_pkg.__path__ = []
        sys.modules[ns_name] = ns_pkg
    if plugin_dir:
        ns_pkg = sys.modules[ns_name]
        if plugin_dir not in ns_pkg.__path__:
            ns_pkg.__path__.append(plugin_dir)


class HotPluginLoader:
    def __init__(self):
        self._registered_routes: dict[str, list] = {}

    def load_plugin(self, plugin_dir: str, app: FastAPI) -> PluginBase | None:
        try:
            manifest_path = os.path.join(plugin_dir, "manifest.json")
            if not os.path.exists(manifest_path):
                logger.error(f"manifest.json 不存在: {manifest_path}")
                return None

            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            main_file = manifest.get("main", "plugin.py")
            plugin_name = manifest.get("name", os.path.basename(plugin_dir))
            module_path = os.path.join(plugin_dir, main_file)

            if not os.path.exists(module_path):
                logger.error(f"入口文件不存在: {module_path}")
                return None

            _ensure_plugin_namespace("hot", plugin_dir)

            module_name = f"plugins.hot.{plugin_name}"
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

            plugin.load_type = "hot"
            plugin.register(getattr(plugin, "plugin_manager", None))
            plugin.start()

            if hasattr(plugin, "router") and isinstance(plugin.router, APIRouter):
                app.include_router(plugin.router)
                self._registered_routes[plugin_name] = [plugin.router]

            logger.info(f"热加载插件成功: {plugin_name} v{plugin.version}")
            return plugin

        except Exception:
            logger.error(f"热加载插件失败: {plugin_dir}\n{traceback.format_exc()}")
            return None


class RestartPluginLoader:
    def __init__(self):
        self._registered_routes: dict[str, list] = {}

    def load_plugin(self, plugin_dir: str, app: FastAPI) -> PluginBase | None:
        try:
            manifest_path = os.path.join(plugin_dir, "manifest.json")
            if not os.path.exists(manifest_path):
                logger.warning(f"manifest.json 不存在: {manifest_path}")
                return None

            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            main_file = manifest.get("main", "plugin.py")
            plugin_name = manifest.get("name", os.path.basename(plugin_dir))
            module_path = os.path.join(plugin_dir, main_file)

            if not os.path.exists(module_path):
                logger.warning(f"入口文件不存在: {module_path}")
                return None

            _ensure_plugin_namespace("restart", plugin_dir)

            module_name = f"plugins.restart.{plugin_name}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.warning(f"无法创建模块规格: {module_path}")
                return None

            plugin_module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = plugin_module
            spec.loader.exec_module(plugin_module)

            if not hasattr(plugin_module, "register_plugin"):
                logger.warning(f"插件入口文件缺少 register_plugin 函数: {module_path}")
                return None

            plugin = plugin_module.register_plugin()

            if not isinstance(plugin, PluginBase):
                logger.warning(f"register_plugin 返回值不是 PluginBase 实例: {type(plugin)}")
                return None

            plugin.load_type = "restart"
            plugin.register(getattr(plugin, "plugin_manager", None))
            plugin.start()

            if hasattr(plugin, "router") and isinstance(plugin.router, APIRouter):
                app.include_router(plugin.router)
                self._registered_routes[plugin_name] = [plugin.router]

            logger.info(f"重启加载插件成功: {plugin_name} v{plugin.version}")
            return plugin

        except Exception:
            logger.warning(f"重启加载插件失败（已跳过）: {plugin_dir}\n{traceback.format_exc()}")
            return None


def unload_plugin(
    plugin_name: str,
    app: FastAPI,
    loaded_plugins: dict[str, PluginBase],
    loaded_modules: dict[str, object],
) -> bool:
    plugin = loaded_plugins.get(plugin_name)
    if plugin is None:
        logger.warning(f"插件未加载，无法卸载: {plugin_name}")
        return False

    try:
        plugin.stop()
    except Exception:
        logger.error(f"停止插件失败: {plugin_name}\n{traceback.format_exc()}")

    try:
        plugin_router = getattr(plugin, "router", None)
        if plugin_router is not None:
            prefix = getattr(plugin_router, "prefix", "") or ""
            # include_router 会将子路由展开到 app.routes 中，
            # 通过路由前缀匹配并原地移除，不能直接赋值 app.routes（FastAPI 的 routes 无 setter）
            routes_to_remove = []
            for route in app.routes:
                route_path = getattr(route, "path", "")
                if prefix and route_path.startswith(prefix):
                    routes_to_remove.append(route)
            for route in routes_to_remove:
                app.routes.remove(route)
            if routes_to_remove:
                logger.info(f"已移除 {len(routes_to_remove)} 条插件路由: {prefix}")
    except Exception:
        logger.error(f"移除插件路由失败: {plugin_name}\n{traceback.format_exc()}")

    loaded_plugins.pop(plugin_name, None)
    loaded_modules.pop(plugin_name, None)

    modules_to_remove = [
        key for key in sys.modules if key == f"plugins.hot.{plugin_name}" or key == f"plugins.restart.{plugin_name}"
    ]
    for key in modules_to_remove:
        sys.modules.pop(key, None)

    logger.info(f"插件卸载成功: {plugin_name}")
    return True
