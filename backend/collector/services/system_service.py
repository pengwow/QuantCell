# 系统服务类，处理系统相关的业务逻辑

import platform
import time
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

import psutil
from loguru import logger

# 导入WebSocket连接管理器
from websocket.manager import manager


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
                "timestamp": datetime.now().isoformat()
            }
    
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
