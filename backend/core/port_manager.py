# -*- coding: utf-8 -*-
"""
统一端口管理器模块

提供端口分配、检测、持久化等功能，支持：
- 自动端口分配和冲突检测
- 配置文件持久化存储
- 僵尸进程检测与清理
- 线程安全的并发访问
- 环境变量配置覆盖

使用示例：
    from core.port_manager import port_manager

    # 获取 FastAPI 服务端口
    fastapi_port = port_manager.get_port("fastapi")

    # 获取 ZMQ 数据通道端口
    zmq_data_port = port_manager.get_port("zmq_data")

    # 获取所有端口配置
    all_ports = port_manager.get_all_ports()
"""

import os
import socket
import signal
import json
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict, field
from threading import Lock
from enum import Enum

from utils.logger import get_logger, LogType


class PortAllocationError(Exception):
    """端口分配异常

    当端口分配失败时抛出此异常，包括：
    - 所有端口都被占用
    - 权限不足
    - 配置文件读写错误
    """

    def __init__(self, message: str, service_name: str = "", port: int = 0):
        self.service_name = service_name
        self.port = port
        super().__init__(message)


@dataclass
class PortConfig:
    """端口配置数据结构"""

    port: int
    pid: Optional[int] = None
    start_time: Optional[str] = None
    last_used: Optional[str] = None
    status: str = "allocated"

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


PORT_RANGES: Dict[str, Dict[str, any]] = {
    "fastapi": {"default": 8000, "range": (8000, 8010)},
    "zmq_data": {"default": 5555, "range": (5550, 5560)},
    "zmq_control": {"default": 5556, "range": (5560, 5570)},
    "zmq_status": {"default": 5557, "range": (5570, 5580)},
    "zmq_broadcast": {"default": 5558, "range": (5580, 5590)},
}


class PortManager:
    """
    统一端口管理器（单例模式）

    提供端口的统一管理功能，包括：
    - 端口分配与回收
    - 端口可用性检测
    - 配置文件持久化
    - 僵尸进程清理
    - 并发安全访问

    Attributes:
        _instance: 单例实例
        _lock: 线程锁
        config_path: 配置文件路径
        allocated_ports: 已分配的端口映射
        use_static_ports: 是否使用静态端口
    """

    _instance: Optional["PortManager"] = None
    _lock: Lock = Lock()
    _init_lock: Lock = Lock()

    def __new__(cls) -> "PortManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        self._initialized = True
        self.logger = get_logger(__name__, LogType.APPLICATION)

        self.use_static_ports = os.environ.get("USE_STATIC_PORTS", "").lower() == "true"
        custom_config_path = os.environ.get("PORT_CONFIG_PATH")

        backend_path = Path(__file__).resolve().parent.parent
        default_config_path = backend_path / "data" / "port_config.json"
        self.config_path = Path(custom_config_path) if custom_config_path else default_config_path

        self.allocated_ports: Dict[str, PortConfig] = {}
        self._port_lock = Lock()

        self.logger.info(
            f"初始化端口管理器 | 配置路径: {self.config_path} | 静态模式: {self.use_static_ports}"
        )

        if not self.use_static_ports:
            self.load_config()
        else:
            self.logger.info("使用静态端口模式，跳过配置加载")
            self._initialize_static_ports()

    def _initialize_static_ports(self) -> None:
        """初始化静态端口配置"""
        for service_name, config in PORT_RANGES.items():
            self.allocated_ports[service_name] = PortConfig(
                port=config["default"],
                pid=os.getpid(),
                start_time=datetime.utcnow().isoformat(),
                status="static",
            )
        self.logger.info(f"已初始化 {len(self.allocated_ports)} 个静态端口配置")

    def set_preferred_port(self, service_name: str, preferred_port: int) -> None:
        """
        设置指定服务的首选端口号

        在调用 get_port() 之前调用此方法可以指定优先使用的端口。
        如果首选端口不可用，将自动在范围内查找其他可用端口。

        Args:
            service_name: 服务名称（如 fastapi、zmq_data 等）
            preferred_port: 首选端口号

        Raises:
            ValueError: 当服务名称无效或端口号超出范围时抛出
        """
        if service_name not in PORT_RANGES:
            error_msg = f"未知的服务名称: {service_name}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        config = PORT_RANGES[service_name]
        start_port, end_port = config["range"]

        if not (start_port <= preferred_port < end_port):
            error_msg = (
                f"端口号 {preferred_port} 超出服务 {service_name} 的有效范围 "
                f"({start_port}-{end_port - 1})"
            )
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # 保存首选端口到临时配置，供 _allocate_port 使用
        if not hasattr(self, '_preferred_ports'):
            self._preferred_ports = {}
        self._preferred_ports[service_name] = preferred_port

        self.logger.info(
            f"已设置首选端口 | 服务: {service_name} | 端口: {preferred_port}"
        )

    def get_port(self, service_name: str) -> int:
        """
        获取指定服务的端口号

        如果服务已分配端口则直接返回，否则自动分配新端口。

        Args:
            service_name: 服务名称（如 fastapi、zmq_data 等）

        Returns:
            int: 分配的端口号

        Raises:
            PortAllocationError: 当端口分配失败时抛出
        """
        with self._port_lock:
            if service_name in self.allocated_ports:
                port_config = self.allocated_ports[service_name]
                port_config.last_used = datetime.utcnow().isoformat()
                self.logger.debug(f"返回已分配端口 | 服务: {service_name} | 端口: {port_config.port}")
                return port_config.port

            if service_name not in PORT_RANGES:
                error_msg = f"未知的服务名称: {service_name}"
                self.logger.error(error_msg)
                raise PortAllocationError(error_msg, service_name=service_name)

            try:
                port = self._allocate_port(service_name)
                return port
            except Exception as e:
                error_msg = f"端口分配失败 | 服务: {service_name} | 错误: {str(e)}"
                self.logger.error(error_msg)
                raise PortAllocationError(error_msg, service_name=service_name) from e

    def _allocate_port(self, service_name: str) -> int:
        """
        分配指定服务的端口

        如果通过 set_preferred_port() 设置了首选端口，则优先尝试使用该端口。
        否则从默认端口开始检测可用性，如果被占用则在范围内递增查找。
        找到可用端口后保存到配置并返回。

        Args:
            service_name: 服务名称

        Returns:
            int: 可用的端口号

        Raises:
            PortAllocationError: 当所有端口都不可用时抛出
        """
        config = PORT_RANGES[service_name]
        default_port = config["default"]
        port_range = config["range"]

        self.logger.debug(f"开始分配端口 | 服务: {service_name} | 默认: {default_port} | 范围: {port_range}")

        start_port, end_port = port_range

        # 检查是否有首选端口
        preferred_port = getattr(self, '_preferred_ports', {}).get(service_name)

        # 构建要尝试的端口列表：首选端口 -> 默认端口 -> 其他端口
        ports_to_try = []
        if preferred_port is not None and preferred_port != default_port:
            ports_to_try.append(preferred_port)
        if default_port not in ports_to_try:
            ports_to_try.append(default_port)

        # 添加范围内的其他端口
        for port in range(start_port, end_port):
            if port not in ports_to_try:
                ports_to_try.append(port)

        for port in ports_to_try:
            if not self._is_port_available(port):
                self.logger.debug(f"端口已被占用 | 端口: {port}")
                continue

            cleaned = self.detect_and_cleanup_zombie_process(port)
            if not cleaned and not self._is_port_available(port):
                self.logger.debug(f"端口仍被占用（非僵尸进程）| 端口: {port}")
                continue

            self.allocated_ports[service_name] = PortConfig(
                port=port,
                pid=os.getpid(),
                start_time=datetime.utcnow().isoformat(),
                last_used=datetime.utcnow().isoformat(),
                status="active",
            )

            self.save_config()

            log_msg = (
                f"端口分配成功 | 服务: {service_name} | 端口: {port}"
                f"| {'使用首选端口' if port == preferred_port else '使用默认端口' if port == default_port else '已切换到备用端口'}"
            )
            self.logger.info(log_msg)

            return port

        error_msg = (
            f"所有端口都不可用 | 服务: {service_name}"
            f" | 范围: {start_port}-{end_port - 1}"
        )
        self.logger.error(error_msg)
        raise PortAllocationError(error_msg, service_name=service_name)

    def _is_port_available(self, port: int) -> bool:
        """
        检测端口是否可用

        通过尝试绑定 socket 来检测端口是否被占用。
        支持TCP和UDP两种协议类型。

        Args:
            port: 要检测的端口号

        Returns:
            bool: True 表示端口可用，False 表示被占用
        """
        for sock_type in [socket.SOCK_STREAM, socket.SOCK_DGRAM]:
            try:
                with socket.socket(socket.AF_INET, sock_type) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(("0.0.0.0", port))
                    return True
            except OSError as e:
                if e.errno == 98 or e.errno == 48 or e.errno == 10048:
                    return False
                continue

        return False

    def detect_and_cleanup_zombie_process(self, port: int) -> bool:
        """
        检测并清理占用指定端口的僵尸进程

        检测逻辑：
        1. 查找占用端口的进程 PID
        2. 判断是否是自身进程的僵尸实例
        3. 如果是僵尸进程则尝试终止

        Args:
            port: 要检测的端口号

        Returns:
            bool: 是否成功清理了僵尸进程
        """
        try:
            import subprocess

            current_pid = os.getpid()

            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0 or not result.stdout.strip():
                self.logger.debug(f"端口未被占用 | 端口: {port}")
                return True

            pids = [int(pid.strip()) for pid in result.stdout.strip().split("\n") if pid.strip()]

            cleaned = False
            for pid in pids:
                if self._is_zombie_process(pid, current_pid):
                    self.logger.warning(
                        f"发现僵尸进程 | 端口: {port} | PID: {pid} | 正在清理..."
                    )
                    if self._terminate_process(pid):
                        cleaned = True
                        self.logger.info(f"成功终止僵尸进程 | PID: {pid}")

            return cleaned

        except FileNotFoundError:
            self.logger.debug("lsof 命令不可用，跳过僵尸进程检测")
            return False
        except subprocess.TimeoutExpired:
            self.logger.warning(f"僵尸进程检测超时 | 端口: {port}")
            return False
        except Exception as e:
            self.logger.error(f"僵尸进程检测异常 | 端口: {port} | 错误: {str(e)}")
            return False

    def _is_zombie_process(self, pid: int, current_pid: int) -> bool:
        """
        判断指定进程是否是僵尸进程

        通过比较进程名和命令行参数来判断是否是同一应用的残留进程。

        Args:
            pid: 进程ID
            current_pid: 当前进程ID

        Returns:
            bool: 是否为僵尸进程
        """
        try:
            import subprocess

            proc_info = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command=", "-no-headers"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if proc_info.returncode != 0:
                return False

            command = proc_info.stdout.strip().lower()

            zombie_indicators = ["quantcell", "uvicorn", "main:app", "python"]
            return any(indicator in command for indicator in zombie_indicators) and pid != current_pid

        except Exception:
            return False

    def _terminate_process(self, pid: int) -> bool:
        """
        终止指定进程

        先发送 SIGTERM 信号，如果进程未退出则发送 SIGKILL 强制终止。

        Args:
            pid: 进程ID

        Returns:
            bool: 是否成功终止进程
        """
        import time

        try:
            os.kill(pid, signal.SIGTERM)

            for _ in range(10):
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return True

            self.logger.warning(f"SIGTERM 未生效，发送 SIGKILL | PID: {pid}")
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)

            try:
                os.kill(pid, 0)
                return False
            except ProcessLookupError:
                return True

        except ProcessLookupError:
            return True
        except PermissionError:
            self.logger.error(f"权限不足，无法终止进程 | PID: {pid}")
            return False
        except Exception as e:
            self.logger.error(f"终止进程失败 | PID: {pid} | 错误: {str(e)}")
            return False

    def save_config(self) -> None:
        """
        保存当前端口配置到文件

        使用原子写入方式：先写入临时文件，再重命名到目标路径，
        确保配置文件不会因为程序崩溃而损坏。

        Raises:
            IOError: 当文件写入失败时抛出
        """
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            config_data = {
                "version": "1.0",
                "updated_at": datetime.utcnow().isoformat(),
                "services": {
                    name: port_config.to_dict()
                    for name, port_config in self.allocated_ports.items()
                },
            }

            fd, temp_path = tempfile.mkstemp(
                dir=self.config_path.parent,
                prefix=".port_config_",
                suffix=".tmp",
            )

            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                os.replace(temp_path, str(self.config_path))

                self.logger.debug(f"配置已保存 | 文件: {self.config_path}")
            except Exception as e:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise e

        except Exception as e:
            error_msg = f"保存配置失败 | 路径: {self.config_path} | 错误: {str(e)}"
            self.logger.error(error_msg)
            raise IOError(error_msg) from e

    def load_config(self) -> Dict:
        """
        从文件加载端口配置

        加载并验证配置文件的格式有效性。
        文件不存在或损坏时返回空字典。

        Returns:
            Dict: 加载的配置字典
        """
        if not self.config_path.exists():
            self.logger.info("配置文件不存在，将使用默认配置")
            return {}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            if not self._validate_config(config_data):
                self.logger.warning("配置文件格式无效，将使用默认配置")
                return {}

            services = config_data.get("services", {})
            for service_name, port_info in services.items():
                if service_name in PORT_RANGES:
                    self.allocated_ports[service_name] = PortConfig(**port_info)

            self.logger.info(
                f"配置加载成功 | 文件: {self.config_path}"
                f" | 服务数: {len(self.allocated_ports)}"
            )

            return config_data

        except json.JSONDecodeError as e:
            self.logger.error(f"配置文件JSON解析失败 | 错误: {str(e)}")
            return {}
        except Exception as e:
            self.logger.error(f"加载配置失败 | 错误: {str(e)}")
            return {}

    def _validate_config(self, config_data: Dict) -> bool:
        """
        验证配置数据格式有效性

        Args:
            config_data: 配置字典

        Returns:
            bool: 是否有效
        """
        required_keys = {"version", "services"}
        if not all(key in config_data for key in required_keys):
            return False

        services = config_data.get("services", {})
        if not isinstance(services, dict):
            return False

        for service_name, port_info in services.items():
            if not isinstance(port_info, dict):
                return False
            if "port" not in port_info or not isinstance(port_info["port"], int):
                return False

        return True

    def get_all_ports(self) -> Dict[str, int]:
        """
        获取所有服务的端口配置

        返回服务名称到端口号的映射字典。

        Returns:
            Dict[str, int]: 端口配置字典
        """
        with self._port_lock:
            ports = {
                name: port_config.port
                for name, port_config in self.allocated_ports.items()
            }

            self.logger.debug(f"获取所有端口配置 | 数量: {len(ports)}")
            return ports

    def release_port(self, service_name: str) -> bool:
        """
        释放指定服务的端口

        Args:
            service_name: 服务名称

        Returns:
            bool: 是否成功释放
        """
        with self._port_lock:
            if service_name not in self.allocated_ports:
                self.logger.warning(f"服务未分配端口 | 服务: {service_name}")
                return False

            del self.allocated_ports[service_name]
            self.save_config()

            self.logger.info(f"端口已释放 | 服务: {service_name}")
            return True

    def reload_config(self) -> None:
        """
        重新加载配置文件

        清空当前配置并从文件重新加载。
        """
        with self._port_lock:
            self.allocated_ports.clear()
            self.load_config()
            self.logger.info("配置已重新加载")


port_manager = PortManager()
