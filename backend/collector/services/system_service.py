# 系统服务类，处理系统相关的业务逻辑

import platform
import time
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

import psutil
from loguru import logger

# 导入WebSocket连接管理器
from websocket.manager import manager


class ExchangeStatus(Enum):
    """交易所连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class ExchangeConnectionInfo:
    """交易所连接信息"""
    exchange_name: str
    status: ExchangeStatus
    last_connected_at: Optional[datetime] = None
    last_disconnected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    reconnect_count: int = 0
    latency_ms: Optional[float] = None
    message_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "exchange_name": self.exchange_name,
            "status": self.status.value,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "last_disconnected_at": self.last_disconnected_at.isoformat() if self.last_disconnected_at else None,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "reconnect_count": self.reconnect_count,
            "latency_ms": self.latency_ms,
            "message_count": self.message_count,
        }


class ExchangeConnectionMonitor:
    """交易所连接状态监测器"""
    
    def __init__(self):
        """初始化监测器"""
        self._connections: Dict[str, ExchangeConnectionInfo] = {}
        self._lock = asyncio.Lock()
    
    async def register_exchange(self, exchange_name: str) -> ExchangeConnectionInfo:
        """注册交易所"""
        async with self._lock:
            if exchange_name not in self._connections:
                self._connections[exchange_name] = ExchangeConnectionInfo(
                    exchange_name=exchange_name,
                    status=ExchangeStatus.DISCONNECTED
                )
            return self._connections[exchange_name]
    
    async def update_status(
        self,
        exchange_name: str,
        status: ExchangeStatus,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None
    ):
        """更新连接状态"""
        async with self._lock:
            if exchange_name not in self._connections:
                await self.register_exchange(exchange_name)
            
            info = self._connections[exchange_name]
            old_status = info.status
            info.status = status
            
            # 更新时间戳
            if status == ExchangeStatus.CONNECTED:
                info.last_connected_at = datetime.now()
                # 清除错误信息
                if old_status != ExchangeStatus.CONNECTED:
                    info.last_error = None
            elif status == ExchangeStatus.DISCONNECTED:
                info.last_disconnected_at = datetime.now()
            elif status == ExchangeStatus.ERROR and error:
                info.last_error = error
                info.last_error_at = datetime.now()
            elif status == ExchangeStatus.RECONNECTING:
                info.reconnect_count += 1
            
            # 更新延迟
            if latency_ms is not None:
                info.latency_ms = latency_ms
    
    async def increment_message_count(self, exchange_name: str):
        """增加消息计数"""
        async with self._lock:
            if exchange_name in self._connections:
                self._connections[exchange_name].message_count += 1
    
    def get_connection_info(self, exchange_name: str) -> Optional[ExchangeConnectionInfo]:
        """获取连接信息"""
        return self._connections.get(exchange_name)
    
    def get_all_connections(self) -> List[ExchangeConnectionInfo]:
        """获取所有连接信息"""
        return list(self._connections.values())
    
    def get_connections_summary(self) -> Dict[str, Any]:
        """获取连接摘要"""
        total = len(self._connections)
        connected = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.CONNECTED)
        disconnected = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.DISCONNECTED)
        error = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.ERROR)
        reconnecting = sum(1 for c in self._connections.values() if c.status == ExchangeStatus.RECONNECTING)
        
        return {
            "total": total,
            "connected": connected,
            "disconnected": disconnected,
            "error": error,
            "reconnecting": reconnecting,
            "healthy": connected == total and total > 0,
        }


class SystemService:
    """系统服务类，处理系统相关的业务逻辑"""
    
    def __init__(self):
        """初始化系统服务"""
        # 应用启动时间
        self.start_time = time.time()
        # 系统信息推送定时器
        self.push_timer: Optional[asyncio.Task] = None
        # 推送间隔（秒）
        self.push_interval: int = 5
        # 交易所连接监测器
        self.exchange_monitor = ExchangeConnectionMonitor()
        # 交易所状态推送定时器
        self.exchange_push_timer: Optional[asyncio.Task] = None
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息
        
        Returns:
            Dict[str, Any]: 包含系统信息的数据
        """
        try:
            # logger.info("开始获取系统信息")
            
            # 获取版本信息
            version_info = {
                "system_version": "1.0.0",  # 系统版本，可从配置文件或环境变量获取
                "python_version": platform.python_version(),
                "build_date": "2025-11-30"  # 构建日期，可从环境变量或配置文件获取
            }
            
            # 计算运行时间
            uptime_seconds = time.time() - self.start_time
            days = int(uptime_seconds // (24 * 3600))
            hours = int((uptime_seconds % (24 * 3600)) // 3600)
            uptime_str = f"{days} 天 {hours} 小时"
            
            # 获取运行状态
            running_status = {
                "uptime": uptime_str,
                "status": "running",
                "status_color": "green",
                "last_check": datetime.now()
            }
            
            # 获取资源使用情况
            # CPU使用率
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_used = round(memory.used / (1024 ** 3), 2)
            memory_total = round(memory.total / (1024 ** 3), 2)
            memory_str = f"{memory_used}GB / {memory_total}GB"
            
            # 磁盘空间使用情况
            disk = psutil.disk_usage('/')
            disk_used = round(disk.used / (1024 ** 3), 2)
            disk_total = round(disk.total / (1024 ** 3), 2)
            disk_str = f"{disk_used}GB / {disk_total}GB"
            
            resource_usage = {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_str,
                "disk_space": disk_str
            }
            
            # 构建响应数据
            system_info = {
                "version": version_info,
                "running_status": running_status,
                "resource_usage": resource_usage
            }
            
            # logger.info("成功获取系统信息")
            
            return {
                "success": True,
                "message": "获取系统信息成功",
                "system_info": system_info
            }
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            return {
                "success": False,
                "message": "获取系统信息失败",
                "error": str(e)
            }
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态
        
        Returns:
            Dict[str, Any]: 包含系统状态的数据
        """
        try:
            # 获取CPU使用率
            cpu_usage = psutil.cpu_percent(interval=0.1)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_used = round(memory.used / (1024 ** 3), 2)
            memory_total = round(memory.total / (1024 ** 3), 2)
            memory_str = f"{memory_used}GB / {memory_total}GB"
            memory_percent = memory.percent
            
            # 磁盘空间使用情况
            disk = psutil.disk_usage('/')
            disk_used = round(disk.used / (1024 ** 3), 2)
            disk_total = round(disk.total / (1024 ** 3), 2)
            disk_str = f"{disk_used}GB / {disk_total}GB"
            disk_percent = disk.percent
            
            system_status = {
                "cpu_usage": cpu_usage,
                "cpu_usage_percent": cpu_usage,
                "memory_usage": memory_str,
                "memory_usage_percent": memory_percent,
                "disk_space": disk_str,
                "disk_space_percent": disk_percent,
                "timestamp": datetime.now().isoformat()
            }
            
            # 添加交易所连接状态
            system_status["exchange_connections"] = self.get_exchange_connections_status()
            
            return system_status
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}")
            return {
                "cpu_usage": 0,
                "cpu_usage_percent": 0,
                "memory_usage": "0GB / 0GB",
                "memory_usage_percent": 0,
                "disk_space": "0GB / 0GB",
                "disk_space_percent": 0,
                "timestamp": datetime.now().isoformat(),
                "exchange_connections": self.get_exchange_connections_status()
            }
    
    def get_exchange_connections_status(self) -> Dict[str, Any]:
        """获取交易所连接状态
        
        Returns:
            Dict[str, Any]: 交易所连接状态信息
        """
        try:
            # 获取所有连接信息
            connections = self.exchange_monitor.get_all_connections()
            summary = self.exchange_monitor.get_connections_summary()
            
            # 构建详细连接信息
            connections_detail = []
            for conn in connections:
                conn_dict = conn.to_dict()
                # 添加状态颜色（用于前端展示）
                status_colors = {
                    "connected": "green",
                    "disconnected": "gray",
                    "connecting": "yellow",
                    "error": "red",
                    "reconnecting": "orange",
                }
                conn_dict["status_color"] = status_colors.get(conn.status.value, "gray")
                connections_detail.append(conn_dict)
            
            return {
                "summary": summary,
                "connections": connections_detail,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"获取交易所连接状态失败: {e}")
            return {
                "summary": {
                    "total": 0,
                    "connected": 0,
                    "disconnected": 0,
                    "error": 0,
                    "reconnecting": 0,
                    "healthy": False,
                },
                "connections": [],
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }
    
    async def update_exchange_status(
        self,
        exchange_name: str,
        status: str,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None
    ):
        """更新交易所连接状态
        
        Args:
            exchange_name: 交易所名称
            status: 连接状态 (disconnected, connecting, connected, error, reconnecting)
            error: 错误信息（可选）
            latency_ms: 延迟毫秒数（可选）
        """
        try:
            # 转换状态字符串为枚举
            status_enum = ExchangeStatus(status)
            await self.exchange_monitor.update_status(
                exchange_name=exchange_name,
                status=status_enum,
                error=error,
                latency_ms=latency_ms
            )
            logger.debug(f"交易所 {exchange_name} 状态更新为 {status}")
        except Exception as e:
            logger.error(f"更新交易所状态失败: {e}")
    
    async def register_exchange(self, exchange_name: str):
        """注册交易所到监测系统
        
        Args:
            exchange_name: 交易所名称
        """
        try:
            await self.exchange_monitor.register_exchange(exchange_name)
            logger.info(f"交易所 {exchange_name} 已注册到监测系统")
        except Exception as e:
            logger.error(f"注册交易所失败: {e}")
    
    async def start_system_status_push(self):
        """启动系统状态推送"""
        if not self.push_timer or self.push_timer.done():
            self.push_timer = asyncio.create_task(self._push_system_status_loop())
            logger.info("系统状态推送服务已启动")
    
    async def stop_system_status_push(self):
        """停止系统状态推送"""
        if self.push_timer and not self.push_timer.done():
            self.push_timer.cancel()
            try:
                await self.push_timer
            except asyncio.CancelledError:
                pass
            logger.info("系统状态推送服务已停止")
    
    async def start_exchange_status_push(self):
        """启动交易所状态推送"""
        if not self.exchange_push_timer or self.exchange_push_timer.done():
            self.exchange_push_timer = asyncio.create_task(self._push_exchange_status_loop())
            logger.info("交易所状态推送服务已启动")
    
    async def stop_exchange_status_push(self):
        """停止交易所状态推送"""
        if self.exchange_push_timer and not self.exchange_push_timer.done():
            self.exchange_push_timer.cancel()
            try:
                await self.exchange_push_timer
            except asyncio.CancelledError:
                pass
            logger.info("交易所状态推送服务已停止")
    
    async def _push_exchange_status_loop(self):
        """交易所状态推送循环"""
        while True:
            try:
                await self.push_exchange_status()
                await asyncio.sleep(self.push_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"交易所状态推送失败: {e}")
                await asyncio.sleep(self.push_interval)
    
    async def push_exchange_status(self):
        """推送交易所状态到前端"""
        try:
            # 获取交易所连接状态
            exchange_status = self.get_exchange_connections_status()
            
            # 构建交易所状态消息
            message = {
                "type": "exchange_status",
                "id": f"exchange_status_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": exchange_status
            }
            
            # 通过WebSocket广播交易所状态
            await manager.broadcast(message, topic="exchange:status")
            
            logger.debug("交易所状态推送成功")
        except Exception as e:
            logger.error(f"推送交易所状态失败: {e}")
    
    async def _push_system_status_loop(self):
        """系统状态推送循环"""
        while True:
            try:
                await self.push_system_status()
                await asyncio.sleep(self.push_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"系统状态推送失败: {e}")
                await asyncio.sleep(self.push_interval)
    
    async def push_system_status(self):
        """推送系统状态到前端"""
        try:
            # 获取系统状态
            system_status = self.get_system_status()
            
            # 构建系统状态消息
            message = {
                "type": "system_status",
                "id": f"system_status_{int(time.time() * 1000)}",
                "timestamp": int(time.time() * 1000),
                "data": system_status
            }
            
            # 通过WebSocket广播系统状态
            await manager.broadcast(message, topic="system:status")
            
            # logger.debug("系统状态推送成功")
        except Exception as e:
            logger.error(f"推送系统状态失败: {e}")
