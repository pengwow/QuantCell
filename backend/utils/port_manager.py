# -*- coding: utf-8 -*-
"""
端口管理工具模块

提供端口占用检测、可用端口查找、端口信息持久化等功能。

使用示例:
    from utils.port_manager import PortManager

    port_manager = PortManager()
    available_port = port_manager.find_available_port(8000, 8010)
    if available_port:
        port_manager.save_port_info(available_port, "backend")
"""

import socket
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)


@dataclass
class PortInfo:
    """端口信息数据结构"""
    port: int
    pid: int
    started_at: str
    service: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PortInfo":
        return cls(**data)


class PortManager:
    """
    端口管理器

    管理端口占用检测、可用端口查找、端口信息持久化等功能。
    """

    # 默认端口配置
    DEFAULT_BACKEND_PORT = 8000
    DEFAULT_BACKEND_RANGE = (8000, 8010)
    DEFAULT_FRONTEND_PORT = 5173
    DEFAULT_FRONTEND_RANGE = (5173, 5183)

    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化端口管理器

        参数:
            project_root: 项目根目录，默认为当前工作目录
        """
        if project_root is None:
            # 从当前文件位置推断项目根目录
            self.project_root = Path(__file__).resolve().parent.parent.parent
        else:
            self.project_root = Path(project_root)

        self.ports_file = self.project_root / ".quantcell" / "ports.json"
        self._ensure_ports_dir()

    def _ensure_ports_dir(self) -> None:
        """确保端口信息目录存在"""
        ports_dir = self.ports_file.parent
        ports_dir.mkdir(parents=True, exist_ok=True)

    def check_port_available(self, port: int, host: str = "0.0.0.0") -> bool:
        """
        检查端口是否可用

        参数:
            port: 端口号
            host: 主机地址，默认为 0.0.0.0

        返回:
            bool: 端口是否可用
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return True
            except OSError:
                return False

    def find_available_port(
        self, start_port: int, end_port: int, host: str = "0.0.0.0"
    ) -> Optional[int]:
        """
        在指定范围内查找可用端口

        参数:
            start_port: 起始端口
            end_port: 结束端口
            host: 主机地址

        返回:
            Optional[int]: 可用端口号，如果没有可用端口则返回 None
        """
        for port in range(start_port, end_port + 1):
            if self.check_port_available(port, host):
                logger.debug(f"找到可用端口: {port}")
                return port
            else:
                logger.debug(f"端口 {port} 已被占用")
        return None

    def get_default_port_ranges(self) -> Dict[str, Any]:
        """
        获取默认端口范围配置

        返回:
            Dict: 包含前后端默认端口和范围的配置
        """
        return {
            "backend": {
                "default": self.DEFAULT_BACKEND_PORT,
                "range": self.DEFAULT_BACKEND_RANGE,
            },
            "frontend": {
                "default": self.DEFAULT_FRONTEND_PORT,
                "range": self.DEFAULT_FRONTEND_RANGE,
            },
        }

    def load_port_config(self) -> Dict[str, Any]:
        """
        从配置文件加载端口配置

        返回:
            Dict: 端口配置
        """
        config_file = self.project_root / "backend" / "config.toml"
        if not config_file.exists():
            return self.get_default_port_ranges()

        try:
            import tomllib

            with open(config_file, "rb") as f:
                config = tomllib.load(f)

            ports_config = config.get("ports", {})
            return {
                "backend": {
                    "default": ports_config.get(
                        "backend_default", self.DEFAULT_BACKEND_PORT
                    ),
                    "range": (
                        ports_config.get("backend_range_start", self.DEFAULT_BACKEND_RANGE[0]),
                        ports_config.get("backend_range_end", self.DEFAULT_BACKEND_RANGE[1]),
                    ),
                },
                "frontend": {
                    "default": ports_config.get(
                        "frontend_default", self.DEFAULT_FRONTEND_PORT
                    ),
                    "range": (
                        ports_config.get("frontend_range_start", self.DEFAULT_FRONTEND_RANGE[0]),
                        ports_config.get("frontend_range_end", self.DEFAULT_FRONTEND_RANGE[1]),
                    ),
                },
            }
        except Exception as e:
            logger.warning(f"加载端口配置失败: {e}，使用默认配置")
            return self.get_default_port_ranges()

    def save_port_info(self, port: int, service: str) -> None:
        """
        保存端口信息到文件

        参数:
            port: 端口号
            service: 服务名称 (backend/frontend)
        """
        import os

        port_info = PortInfo(
            port=port,
            pid=os.getpid(),
            started_at=datetime.now().isoformat(),
            service=service,
        )

        # 读取现有配置
        ports_data = self._load_ports_file()

        # 更新配置
        ports_data[service] = port_info.to_dict()

        # 保存配置
        self._save_ports_file(ports_data)
        logger.info(f"已保存 {service} 端口信息: {port}")

    def load_port_info(self, service: str) -> Optional[int]:
        """
        从文件加载端口信息

        参数:
            service: 服务名称 (backend/frontend)

        返回:
            Optional[int]: 端口号，如果不存在则返回 None
        """
        ports_data = self._load_ports_file()
        service_info = ports_data.get(service)
        if service_info:
            return service_info.get("port")
        return None

    def get_all_port_info(self) -> Dict[str, Any]:
        """
        获取所有端口信息

        返回:
            Dict: 所有服务的端口信息
        """
        return self._load_ports_file()

    def clear_port_info(self, service: Optional[str] = None) -> None:
        """
        清除端口信息

        参数:
            service: 服务名称，如果为 None 则清除所有
        """
        if service is None:
            if self.ports_file.exists():
                self.ports_file.unlink()
                logger.info("已清除所有端口信息")
        else:
            ports_data = self._load_ports_file()
            if service in ports_data:
                del ports_data[service]
                self._save_ports_file(ports_data)
                logger.info(f"已清除 {service} 端口信息")

    def _load_ports_file(self) -> Dict[str, Any]:
        """加载端口信息文件"""
        if not self.ports_file.exists():
            return {}

        try:
            with open(self.ports_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"读取端口信息文件失败: {e}")
            return {}

    def _save_ports_file(self, data: Dict[str, Any]) -> None:
        """保存端口信息文件"""
        try:
            with open(self.ports_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"保存端口信息文件失败: {e}")

    def find_backend_port(
        self, preferred_port: Optional[int] = None
    ) -> tuple[int, bool]:
        """
        查找后端可用端口

        参数:
            preferred_port: 优先使用的端口

        返回:
            tuple: (端口号, 是否使用了优先端口)
        """
        config = self.load_port_config()
        backend_config = config["backend"]

        # 如果指定了优先端口，先尝试使用
        if preferred_port is not None:
            if self.check_port_available(preferred_port):
                logger.info(f"优先端口 {preferred_port} 可用")
                return preferred_port, True
            else:
                logger.warning(f"优先端口 {preferred_port} 已被占用")

        # 尝试默认端口
        default_port = backend_config["default"]
        if self.check_port_available(default_port):
            logger.info(f"默认端口 {default_port} 可用")
            return default_port, False

        # 在范围内查找可用端口
        range_start, range_end = backend_config["range"]
        logger.info(f"在端口范围 {range_start}-{range_end} 内查找可用端口...")

        available_port = self.find_available_port(range_start, range_end)
        if available_port:
            logger.info(f"找到可用端口: {available_port}")
            return available_port, False

        # 如果没有找到，抛出异常
        raise RuntimeError(
            f"在端口范围 {range_start}-{range_end} 内未找到可用端口，"
            "请关闭占用端口的进程或扩大端口范围"
        )

    def find_frontend_port(
        self, preferred_port: Optional[int] = None
    ) -> tuple[int, bool]:
        """
        查找前端可用端口

        参数:
            preferred_port: 优先使用的端口

        返回:
            tuple: (端口号, 是否使用了优先端口)
        """
        config = self.load_port_config()
        frontend_config = config["frontend"]

        # 如果指定了优先端口，先尝试使用
        if preferred_port is not None:
            if self.check_port_available(preferred_port):
                logger.info(f"优先端口 {preferred_port} 可用")
                return preferred_port, True
            else:
                logger.warning(f"优先端口 {preferred_port} 已被占用")

        # 尝试默认端口
        default_port = frontend_config["default"]
        if self.check_port_available(default_port):
            logger.info(f"默认端口 {default_port} 可用")
            return default_port, False

        # 在范围内查找可用端口
        range_start, range_end = frontend_config["range"]
        logger.info(f"在端口范围 {range_start}-{range_end} 内查找可用端口...")

        available_port = self.find_available_port(range_start, range_end)
        if available_port:
            logger.info(f"找到可用端口: {available_port}")
            return available_port, False

        # 如果没有找到，抛出异常
        raise RuntimeError(
            f"在端口范围 {range_start}-{range_end} 内未找到可用端口，"
            "请关闭占用端口的进程或扩大端口范围"
        )


# 全局端口管理器实例
_port_manager: Optional[PortManager] = None


def get_port_manager() -> PortManager:
    """
    获取全局端口管理器实例

    返回:
        PortManager: 端口管理器实例
    """
    global _port_manager
    if _port_manager is None:
        _port_manager = PortManager()
    return _port_manager
