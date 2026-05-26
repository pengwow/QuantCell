from .plugin_base import PluginBase
from .plugin_manager import PluginManager
from .api import PluginAPI
from .event_bus import EventBus, event_bus
from .plugin_store import PluginStore
from .plugin_security import PluginPermission, PluginSandbox, validate_permissions, check_system_route_conflict

__all__ = [
    "PluginBase",
    "PluginManager",
    "PluginAPI",
    "EventBus",
    "event_bus",
    "PluginStore",
    "PluginPermission",
    "PluginSandbox",
    "validate_permissions",
    "check_system_route_conflict",
]

global_plugin_manager = None
global_plugin_api = None

def init_plugin_system(app=None):
    global global_plugin_manager, global_plugin_api
    global_plugin_manager = PluginManager(app=app)
    global_plugin_api = PluginAPI(global_plugin_manager)
    return global_plugin_manager, global_plugin_api
