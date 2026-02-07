# -*- coding: utf-8 -*-
"""
定时任务调度器模块

提供定时任务调度功能
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from services.symbol_sync import symbol_sync_manager


def start_scheduler(
    proxy_enabled: bool = False,
    proxy_url: str = "",
    proxy_username: str = "",
    proxy_password: str = "",
):
    """启动定时任务调度器

    Args:
        proxy_enabled: 是否启用代理
        proxy_url: 代理地址
        proxy_username: 代理用户名
        proxy_password: 代理密码

    Returns:
        BackgroundScheduler: 后台调度器实例
    """
    # 创建后台调度器
    scheduler = BackgroundScheduler()

    # 添加定时任务：每周日凌晨2点执行一次，同步加密货币对
    # 使用同步管理器执行，确保与主动同步的协调
    def scheduled_sync():
        """定时同步任务包装器"""
        # 检查是否正在主动同步
        if symbol_sync_manager.is_syncing:
            logger.info("主动同步正在进行中，跳过本次定时同步")
            return

        # 执行同步
        result = symbol_sync_manager.perform_sync(exchange='binance')
        if result.get("success"):
            logger.info(f"定时同步成功: {result.get('message')}")
        else:
            logger.error(f"定时同步失败: {result.get('message')}")

    scheduler.add_job(
        func=scheduled_sync,
        trigger=CronTrigger(day_of_week=6, hour=2, minute=0),  # 每周日凌晨2点
        id="sync_crypto_symbols",
        name="Sync cryptocurrency symbols",
        replace_existing=True,
    )

    # 启动调度器
    scheduler.start()
    logger.info("定时任务调度器已启动，货币对同步任务将在每周日凌晨2点执行")
    return scheduler
