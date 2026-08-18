from .api import PluginAPI
from .event_bus import EventBus, event_bus
from .plugin_base import PluginBase
from .plugin_manager import PluginManager
from .plugin_security import (
    PluginPermission,
    PluginSandbox,
    check_system_route_conflict,
    validate_permissions,
)
from .plugin_store import PluginStore

__all__ = [
    "EventBus",
    "PluginAPI",
    "PluginBase",
    "PluginManager",
    "PluginPermission",
    "PluginSandbox",
    "PluginStore",
    "check_system_route_conflict",
    "event_bus",
    "validate_permissions",
]

global_plugin_manager = None
global_plugin_api = None


def init_plugin_system(app=None):
    global global_plugin_manager, global_plugin_api
    global_plugin_manager = PluginManager(app=app)
    global_plugin_api = PluginAPI(global_plugin_manager)
    return global_plugin_manager, global_plugin_api
