# -*- coding: utf-8 -*-
"""
货币对同步服务模块

提供货币对数据同步管理功能，包括：
- 主动同步与定时同步协调
- 数据完整性检查
- 错误重试和告警机制
"""

import asyncio
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from collector.db.database import SessionLocal, init_database_config
from collector.db.models import CryptoSymbol
from collector.services.crypto_symbol_service import sync_crypto_symbols


class SyncStatus(Enum):
    """同步状态枚举"""
    IDLE = "idle"           # 空闲状态
    RUNNING = "running"     # 正在同步
    FAILED = "failed"       # 同步失败
    SUCCESS = "success"     # 同步成功


class SymbolSyncManager:
    """货币对同步管理器

    管理主动同步和定时同步的协调，避免冲突
    """

    def __init__(self):
        self._status = SyncStatus.IDLE
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._max_retries = 3
        self._last_sync_time: Optional[datetime] = None
        self._sync_event = threading.Event()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._proxy_config = {
            "enabled": False,
            "url": "",
            "username": "",
            "password": ""
        }

    @property
    def status(self) -> SyncStatus:
        """获取当前同步状态"""
        with self._lock:
            return self._status

    @property
    def is_syncing(self) -> bool:
        """检查是否正在同步"""
        with self._lock:
            return self._status == SyncStatus.RUNNING

    @property
    def consecutive_failures(self) -> int:
        """获取连续失败次数"""
        with self._lock:
            return self._consecutive_failures

    @property
    def last_sync_time(self) -> Optional[datetime]:
        """获取最后同步时间"""
        with self._lock:
            return self._last_sync_time

    def set_scheduler(self, scheduler: BackgroundScheduler):
        """设置调度器引用"""
        self._scheduler = scheduler

    def set_proxy_config(self, enabled: bool, url: str, username: str, password: str):
        """设置代理配置"""
        self._proxy_config = {
            "enabled": enabled,
            "url": url,
            "username": username,
            "password": password
        }

    def _pause_scheduled_sync(self) -> bool:
        """暂停即将执行的定时同步任务

        Returns:
            bool: 是否成功暂停
        """
        if not self._scheduler:
            return False

        try:
            # 获取同步任务
            job = self._scheduler.get_job("sync_crypto_symbols")
            if job and job.next_run_time:
                # 计算距离下次执行的时间
                time_until_next = (job.next_run_time - datetime.now()).total_seconds()
                # 如果下次执行在5分钟内，暂停该任务
                if time_until_next < 300:
                    logger.info(f"暂停定时同步任务，距离下次执行还有 {time_until_next:.0f} 秒")
                    job.pause()
                    return True
        except Exception as e:
            logger.error(f"暂停定时同步任务失败: {e}")
        return False

    def _resume_scheduled_sync(self):
        """恢复定时同步任务"""
        if not self._scheduler:
            return

        try:
            job = self._scheduler.get_job("sync_crypto_symbols")
            if job:
                job.resume()
                logger.info("恢复定时同步任务")
        except Exception as e:
            logger.error(f"恢复定时同步任务失败: {e}")

    def _send_alert(self, message: str):
        """发送系统告警通知

        Args:
            message: 告警消息内容
        """
        logger.error(f"【系统告警】{message}")
        # TODO: 可以在这里添加更多告警方式，如邮件、Webhook等

    def check_symbols_exist(self) -> bool:
        """检查货币对数据是否存在

        Returns:
            bool: 是否存在有效的货币对数据
        """
        try:
            init_database_config()
            db = SessionLocal()
            try:
                # 检查是否存在任何货币对数据
                count = db.query(CryptoSymbol).filter(
                    CryptoSymbol.is_deleted == False,
                    CryptoSymbol.active == True
                ).count()

                logger.info(f"当前有效货币对数量: {count}")
                return count > 0
            finally:
                db.close()
        except Exception as e:
            logger.error(f"检查货币对数据存在性失败: {e}")
            return False

    def perform_sync(self, exchange: str = 'binance') -> Dict[str, Any]:
        """执行同步操作（带重试机制）

        Args:
            exchange: 交易所名称

        Returns:
            Dict[str, Any]: 同步结果
        """
        with self._lock:
            if self._status == SyncStatus.RUNNING:
                logger.warning("同步任务已在运行中，跳过本次请求")
                return {"success": False, "message": "同步任务已在运行中"}

            self._status = SyncStatus.RUNNING

        # 暂停定时同步任务
        paused = self._pause_scheduled_sync()

        try:
            result = self._do_sync_with_retry(exchange)

            # 更新状态
            with self._lock:
                if result.get("success"):
                    self._status = SyncStatus.SUCCESS
                    self._consecutive_failures = 0
                    self._last_sync_time = datetime.now()
                else:
                    self._status = SyncStatus.FAILED
                    self._consecutive_failures += 1

                    # 检查是否需要触发告警
                    if self._consecutive_failures >= 3:
                        self._send_alert(
                            f"货币对数据同步连续失败 {self._consecutive_failures} 次，"
                            f"最后错误: {result.get('message', '未知错误')}"
                        )

            return result

        finally:
            # 恢复定时同步任务
            if paused:
                self._resume_scheduled_sync()

            # 如果当前不是运行中状态，重置为空闲
            with self._lock:
                if self._status == SyncStatus.RUNNING:
                    self._status = SyncStatus.IDLE

    def _do_sync_with_retry(self, exchange: str) -> Dict[str, Any]:
        """执行同步（带重试）

        Args:
            exchange: 交易所名称

        Returns:
            Dict[str, Any]: 同步结果
        """
        last_error = None

        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(f"开始第 {attempt}/{self._max_retries} 次同步尝试")

                result = sync_crypto_symbols(
                    exchange=exchange,
                    proxy_enabled=self._proxy_config["enabled"],
                    proxy_url=self._proxy_config["url"],
                    proxy_username=self._proxy_config["username"],
                    proxy_password=self._proxy_config["password"],
                )

                if result.get("success"):
                    logger.info(f"同步成功: {result.get('message')}")
                    return result
                else:
                    last_error = result.get("message", "未知错误")
                    logger.warning(f"第 {attempt} 次同步失败: {last_error}")

                    if attempt < self._max_retries:
                        wait_time = attempt * 2  # 指数退避
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)

            except Exception as e:
                last_error = str(e)
                logger.error(f"第 {attempt} 次同步异常: {e}")

                if attempt < self._max_retries:
                    wait_time = attempt * 2
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)

        # 所有重试都失败
        error_msg = f"同步失败，已重试 {self._max_retries} 次，最后错误: {last_error}"
        logger.error(error_msg)
        return {"success": False, "message": error_msg}

    async def async_perform_sync(self, exchange: str = 'binance') -> Dict[str, Any]:
        """异步执行同步操作

        Args:
            exchange: 交易所名称

        Returns:
            Dict[str, Any]: 同步结果
        """
        return await asyncio.to_thread(self.perform_sync, exchange)


# 全局同步管理器实例
symbol_sync_manager = SymbolSyncManager()


def require_symbols_data(func):
    """装饰器：要求货币对数据必须存在

    如果数据不存在，返回友好的错误提示
    """
    async def wrapper(*args, **kwargs):
        if not symbol_sync_manager.check_symbols_exist():
            return {
                "code": 503,
                "message": "货币对数据尚未初始化，请稍后重试",
                "data": None,
                "sync_status": symbol_sync_manager.status.value
            }
        return await func(*args, **kwargs)
    return wrapper
