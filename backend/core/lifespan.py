# -*- coding: utf-8 -*-
"""
应用生命周期管理模块

管理FastAPI应用的启动和关闭生命周期
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from collector.db import init_db
from collector.utils.task_manager import task_manager
from collector.utils.scheduled_task_manager import scheduled_task_manager
from collector.services.system_service import SystemService
from config_manager import load_system_configs
from plugins import init_plugin_system
from realtime.engine import RealtimeEngine
from realtime.routes import setup_routes
from websocket.manager import manager
from utils.secret_key_manager import initialize_secret_key

from services.symbol_sync import symbol_sync_manager
from core.scheduler import start_scheduler


# 全局实时引擎实例
realtime_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    Args:
        app: FastAPI应用实例

    Yields:
        None: 无返回值
    """
    global realtime_engine

    # 首先初始化JWT安全密钥（在其他组件之前）
    logger.info("正在初始化JWT安全密钥...")
    jwt_secret_key = await asyncio.to_thread(initialize_secret_key)
    app.state.jwt_secret_key = jwt_secret_key
    logger.info("JWT安全密钥初始化完成")

    # 启动时异步初始化数据库
    await asyncio.to_thread(init_database)

    # 异步加载系统配置到应用上下文
    app.state.configs = await asyncio.to_thread(load_system_configs)
    logger.info(f"系统配置: {app.state.configs}")

    # 从配置中提取代理信息
    proxy_enabled = app.state.configs.get("proxy_enabled", "0")
    proxy_url = app.state.configs.get("proxy_url", "")
    proxy_username = app.state.configs.get("proxy_username", "")
    proxy_password = app.state.configs.get("proxy_password", "")
    logger.info(f"代理配置: enabled={proxy_enabled}, url={proxy_url}")

    # 转换proxy_enabled为布尔值
    proxy_enabled_bool = str(proxy_enabled).strip().lower() in ["1", "true", "yes"]

    # 配置同步管理器的代理设置
    symbol_sync_manager.set_proxy_config(
        enabled=proxy_enabled_bool,
        url=proxy_url if proxy_url is not None else "",
        username=proxy_username if proxy_username is not None else "",
        password=proxy_password if proxy_password is not None else ""
    )

    # 异步启动传统定时任务，传递代理配置
    traditional_scheduler = await asyncio.to_thread(
        start_scheduler,
        proxy_enabled=proxy_enabled_bool,
        proxy_url=proxy_url if proxy_url is not None else "",
        proxy_username=proxy_username if proxy_username is not None else "",
        proxy_password=proxy_password if proxy_password is not None else "",
    )

    # 将调度器设置到同步管理器
    symbol_sync_manager.set_scheduler(traditional_scheduler)

    # 检查货币对数据是否存在，如果不存在则触发主动同步
    logger.info("检查货币对数据完整性...")
    if not symbol_sync_manager.check_symbols_exist():
        logger.warning("未检测到有效的货币对数据，触发主动同步...")
        sync_result = await symbol_sync_manager.async_perform_sync(exchange='binance')
        if sync_result.get("success"):
            logger.info(f"主动同步成功: {sync_result.get('message')}")
        else:
            logger.error(f"主动同步失败: {sync_result.get('message')}")
            # 同步失败但不阻塞启动，让定时同步稍后重试
    else:
        logger.info("货币对数据检查通过")

    # 将同步管理器保存到应用状态
    app.state.symbol_sync_manager = symbol_sync_manager

    # 异步启动新的定时任务管理器
    await asyncio.to_thread(scheduled_task_manager.start)

    # 初始化插件系统
    plugin_manager, plugin_api = await asyncio.to_thread(init_plugin_system)
    # 加载所有插件
    await asyncio.to_thread(plugin_manager.load_all_plugins)

    # 注册插件路由
    plugin_manager.register_plugins(app)

    # 将插件管理器保存到应用状态，供后续使用
    app.state.plugin_manager = plugin_manager
    app.state.plugin_api = plugin_api

    # 初始化实时引擎
    try:
        logger.info("正在初始化实时引擎")
        realtime_engine = RealtimeEngine()
        app.state.realtime_engine = realtime_engine
        # 将实时引擎实例传递给路由模块

        logger.info("准备调用setup_routes函数")
        setup_routes(realtime_engine)
        logger.info("setup_routes函数调用成功")

        # 注册WebSocket数据推送消费者
        def websocket_kline_consumer(data: dict):
            """将K线数据推送到WebSocket"""
            try:
                if data.get('data_type') == 'kline':
                    # 构建K线消息 - 保持原始数据格式
                    kline_message = {
                        "type": "kline",
                        "id": f"kline_{int(time.time() * 1000)}",
                        "timestamp": int(time.time() * 1000),
                        "data": data  # 保持原始数据结构
                    }
                    # 广播到所有订阅了kline主题的客户端
                    asyncio.create_task(
                        manager.broadcast(kline_message, topic="kline")
                    )
            except Exception as e:
                logger.error(f"WebSocket K线数据推送失败: {e}")

        # 注册消费者
        realtime_engine.register_consumer("kline", websocket_kline_consumer)
        logger.info("已注册WebSocket K线数据推送消费者")

        logger.info("实时引擎初始化成功")
    except Exception as e:
        logger.error(f"实时引擎初始化失败: {e}")
        logger.exception(e)
        realtime_engine = None

    # 启动WebSocket连接管理器
    try:
        await manager.start()
        app.state.websocket_manager = manager
        logger.info("WebSocket连接管理器启动成功")

        # 启动系统状态推送服务
        system_service = SystemService()
        await system_service.start_system_status_push()
        app.state.system_service = system_service
        logger.info("系统状态推送服务启动成功")
    except Exception as e:
        logger.error(f"WebSocket连接管理器或系统信息推送服务启动失败: {e}")

    yield

    # 停止实时引擎
    if realtime_engine:
        logger.info("正在停止实时引擎")
        await realtime_engine.stop()

    # 停止系统状态推送服务
    try:
        if hasattr(app.state, "system_service"):
            await app.state.system_service.stop_system_status_push()
            logger.info("系统状态推送服务已停止")
    except Exception as e:
        logger.error(f"停止系统状态推送服务失败: {e}")

    # 停止WebSocket连接管理器
    try:
        await manager.stop()
        logger.info("WebSocket连接管理器已停止")
    except Exception as e:
        logger.error(f"停止WebSocket连接管理器失败: {e}")

    # 异步关闭传统调度器，确保清理完成后再退出
    await asyncio.to_thread(traditional_scheduler.shutdown)
    # 异步关闭新的定时任务管理器
    await asyncio.to_thread(scheduled_task_manager.shutdown)
    # 停止所有插件
    await asyncio.to_thread(plugin_manager.stop_all_plugins)


def init_database():
    """初始化数据库

    Returns:
        None: 无返回值
    """
    init_db()

    # 初始化任务管理器，确保数据库表已创建
    task_manager.init()

    # 初始化定时任务管理器，确保数据库表已创建
    logger.info("初始化定时任务管理器")
