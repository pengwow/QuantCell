from .plugin_base import PluginBase
from .plugin_manager import PluginManager
from .api import PluginAPI

# 导出核心组件
__all__ = [
    "PluginBase",
    "PluginManager",
    "PluginAPI"
]

# 全局插件管理器实例
global_plugin_manager = None

# 全局插件API实例
global_plugin_api = None

def init_plugin_system():
    """初始化插件系统"""
    global global_plugin_manager, global_plugin_api
    global_plugin_manager = PluginManager()
    global_plugin_api = PluginAPI(global_plugin_manager)
    return global_plugin_manager, global_plugin_api
