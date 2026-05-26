from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)
from typing import Any, Dict, Optional


class PluginBase:
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self.load_type: str = "hot"
        self.logger = logger.bind(plugin=self.name)
        self.plugin_manager = None
        self.is_active = False

    def register(self, plugin_manager: Any) -> None:
        self.plugin_manager = plugin_manager
        self.logger.info(f"插件 {self.name} 注册成功")

    def start(self) -> None:
        self.is_active = True
        self.logger.info(f"插件 {self.name} 启动成功")

    def stop(self) -> None:
        self.is_active = False
        self.logger.info(f"插件 {self.name} 停止成功")

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def get_frontend_assets(self) -> Optional[dict]:
        return None

    def get_config_schema(self) -> Optional[dict]:
        return None

    def get_info(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "load_type": self.load_type,
            "is_active": self.is_active
        }

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": "",
            "author": "",
            "load_type": self.load_type,
            "frontend_assets": self.get_frontend_assets(),
            "config_schema": self.get_config_schema()
        }
