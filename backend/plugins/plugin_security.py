from enum import Enum
from typing import Any, Callable, List, Tuple, Optional
from utils.logger import get_logger, LogType


class PluginPermission(str, Enum):
    DATABASE_READ = "database:read"
    DATABASE_WRITE = "database:write"
    API_INTERNAL = "api:internal"
    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    NETWORK_OUTBOUND = "network:outbound"


SYSTEM_ROUTE_PREFIXES = [
    "/api/config",
    "/api/system",
    "/api/auth",
    "/api/workers",
    "/api/logs",
    "/api/notifications",
    "/api/system-ports",
    "/ws",
]


def validate_permissions(permissions: list[str]) -> Tuple[bool, str]:
    if not permissions:
        return (True, "")
    
    valid_values = {p.value for p in PluginPermission}
    for perm in permissions:
        if perm not in valid_values:
            return (False, f"不支持的权限: {perm}")
    
    return (True, "")


def check_system_route_conflict(router_prefix: str) -> Tuple[bool, str]:
    if not router_prefix:
        return (True, "")
    
    for prefix in SYSTEM_ROUTE_PREFIXES:
        if router_prefix.startswith(prefix):
            return (False, f"路由前缀 {router_prefix} 与系统核心路由冲突")
    
    return (True, "")


class PluginSandbox:
    def __init__(self, plugin_name: str, logger):
        self.plugin_name = plugin_name
        self.logger = logger

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.logger.error(f"插件 {self.plugin_name} 执行异常: {e}", exception=e)
            return None

    def execute_safe(self, func: Callable, *args, **kwargs) -> Tuple[bool, Any]:
        try:
            result = func(*args, **kwargs)
            return (True, result)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.logger.error(f"插件 {self.plugin_name} 执行异常: {error_msg}", exception=e)
            return (False, error_msg)
