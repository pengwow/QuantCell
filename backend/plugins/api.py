from typing import Any

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class PluginAPI:
    """插件API，提供核心功能访问和插件间通信"""

    def __init__(self, plugin_manager: Any):
        self.plugin_manager = plugin_manager
        self.logger = logger.bind(component="plugin_api")
        self._registered_services: dict[str, Any] = {}
        self._event_bus = getattr(plugin_manager, "event_bus", None)

    def register_service(self, name: str, service: Any) -> None:
        """注册服务，供其他插件使用

        Args:
            name: 服务名称
            service: 服务实例
        """
        self._registered_services[name] = service
        self.logger.info(f"服务 {name} 注册成功")

    def get_service(self, name: str) -> Any or None:
        """获取指定服务

        Args:
            name: 服务名称

        Returns:
            服务实例，不存在返回None
        """
        return self._registered_services.get(name)

    def get_plugin(self, plugin_name: str) -> Any or None:
        """获取指定插件实例

        Args:
            plugin_name: 插件名称

        Returns:
            插件实例，不存在返回None
        """
        return self.plugin_manager.get_plugin(plugin_name)

    def get_all_plugins(self) -> list[str]:
        """获取所有插件名称

        Returns:
            插件名称列表
        """
        return list(self.plugin_manager.plugins.keys())

    def send_event(self, event_name: str, data: Any = None) -> None:
        if self._event_bus:
            self._event_bus.publish(event_name, data)
        else:
            self.logger.info(f"发送事件 {event_name}，数据: {data}")

    def subscribe_event(self, event_name: str, callback) -> None:
        if self._event_bus:
            self._event_bus.subscribe(event_name, callback)

    def unsubscribe_event(self, event_name: str, callback) -> None:
        if self._event_bus:
            self._event_bus.unsubscribe(event_name, callback)

    def get_event_bus(self):
        return self._event_bus

    def log(self, message: str, level: str = "info") -> None:
        """记录日志

        Args:
            message: 日志消息
            level: 日志级别
        """
        getattr(self.logger, level)(message)
