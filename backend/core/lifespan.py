# -*- coding: utf-8 -*-
"""
应用生命周期管理模块

管理FastAPI应用的启动和关闭生命周期
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from collector.db import init_db
from utils.logger import get_logger, LogType

# 获取生命周期管理模块日志器
logger = get_logger(__name__, LogType.SYSTEM)
from collector.utils.task_manager import task_manager
from collector.utils.scheduled_task_manager import scheduled_task_manager
from collector.services.system_service import SystemService
from utils.config_manager import load_system_configs
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

    # 从配置中提取代理信息
    # 首先查找启用的默认交易所
    default_exchange = None
    for key, value in app.state.configs.items():
        if key.endswith(".is_default") and value in ("1", "true", "True", True):
            exchange_id = key.replace(".is_default", "").replace("exchange.", "")
            is_enabled_key = f"exchange.{exchange_id}.is_enabled"
            is_enabled = app.state.configs.get(is_enabled_key) in ("1", "true", "True", True)
            if is_enabled:
                default_exchange = exchange_id
                logger.info(f"找到默认启用的交易所: {exchange_id}")
                break
    
    # 如果没有找到默认交易所，使用 binance 作为后备
    if not default_exchange:
        default_exchange = "binance"
        logger.info("未找到默认启用的交易所，使用 binance 作为默认")
    
    # 读取该交易所的代理配置
    proxy_enabled = app.state.configs.get(f"exchange.{default_exchange}.proxy_enabled", "0")
    proxy_url = app.state.configs.get(f"exchange.{default_exchange}.proxy_url", "")
    proxy_username = app.state.configs.get(f"exchange.{default_exchange}.proxy_username", "")
    proxy_password = app.state.configs.get(f"exchange.{default_exchange}.proxy_password", "")
    
    # 如果带前缀的配置不存在，尝试读取旧格式（向后兼容）
    if not proxy_enabled or proxy_enabled == "0":
        proxy_enabled = app.state.configs.get("proxy_enabled", "0")
    if not proxy_url:
        proxy_url = app.state.configs.get("proxy_url", "")
    if not proxy_username:
        proxy_username = app.state.configs.get("proxy_username", "")
    if not proxy_password:
        proxy_password = app.state.configs.get("proxy_password", "")
    
    logger.info(f"交易所 {default_exchange} 代理配置: enabled={proxy_enabled}, url={proxy_url}")

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

    # 将同步管理器保存到应用状态
    app.state.symbol_sync_manager = symbol_sync_manager

    # 延迟执行货币对数据同步，避免阻塞启动流程
    async def delayed_symbol_sync():
        """延迟同步货币对数据，确保系统配置已完全加载"""
        try:
            # 延迟30秒，等待系统完全启动
            await asyncio.sleep(30)
            logger.info("开始延迟同步货币对数据...")

            if not symbol_sync_manager.check_symbols_exist():
                logger.warning("未检测到有效的货币对数据，触发主动同步...")
                sync_result = await symbol_sync_manager.async_perform_sync(exchange='binance')
                if sync_result.get("success"):
                    logger.info(f"货币对数据同步成功: {sync_result.get('message')}")
                else:
                    logger.error(f"货币对数据同步失败: {sync_result.get('message')}")
            else:
                logger.info("货币对数据检查通过，无需同步")
        except Exception as e:
            logger.error(f"延迟同步货币对数据时发生错误: {e}")

    # 启动后台任务执行同步，不阻塞主流程
    symbol_sync_task = asyncio.create_task(delayed_symbol_sync())
    app.state.symbol_sync_task = symbol_sync_task
    logger.info("货币对数据同步将在30秒后异步执行")

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
            """将K线数据推送到WebSocket（优化版：直接推送到队列，避免事件循环开销）"""
            try:
                if data.get('data_type') == 'kline':
                    # 构建K线消息 - 保持原始数据格式
                    kline_message = {
                        "type": "kline",
                        "id": f"kline_{int(time.time() * 1000)}",
                        "timestamp": int(time.time() * 1000),
                        "data": data  # 保持原始数据结构
                    }

                    # 直接推送到消息队列，避免创建asyncio任务的开销
                    if manager.message_queue:
                        # 使用非阻塞方式放入队列
                        try:
                            manager.message_queue.put_nowait({
                                "type": "kline",
                                "topic": "kline",
                                **kline_message
                            })
                        except asyncio.QueueFull:
                            logger.warning("[KlinePush] 消息队列已满，丢弃消息")
                    else:
                        # 队列未初始化时，回退到asyncio.create_task
                        asyncio.create_task(
                            manager.broadcast(kline_message, topic="kline")
                        )
            except Exception as e:
                logger.error(f"[KlinePush] WebSocket K线数据推送失败: {e}")

        # 注册消费者
        realtime_engine.register_consumer("kline", websocket_kline_consumer)
        logger.info("已注册WebSocket K线数据推送消费者")

        # 注册K线持久化消费者（新增）
        from realtime.kline_persistence import kline_persistence_consumer
        realtime_engine.register_consumer("kline", kline_persistence_consumer.process_kline)
        logger.info("已注册K线持久化消费者")

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

    # ========== 应用关闭阶段（必须保证执行完毕） ==========
    # 使用 try/finally + CancelledError 保护，确保 Ctrl+C 时关键资源也能清理
    logger.info("========== 应用开始关闭 ==========")

    # 步骤 1: 停止所有 Worker 进程（最高优先级，防止孤儿进程）
    try:
        from worker.api.routes import shutdown_worker_manager
        await asyncio.wait_for(shutdown_worker_manager(), timeout=60.0)
        logger.info("所有 Worker 进程已停止")
    except asyncio.CancelledError:
        logger.warning("停止 Worker 进程时被中断（CancelledError），尝试快速终止...")
        try:
            from worker.api.routes import _worker_manager
            if _worker_manager is not None:
                for wid, w in list(_worker_manager._workers.items()):
                    if w.is_alive():
                        w.terminate()
                _worker_manager._workers.clear()
                logger.info("Worker 进程已强制终止")
        except Exception as e2:
            logger.error(f"强制终止 Worker 失败: {e2}")
        raise
    except Exception as e:
        logger.error(f"停止 Worker 进程失败: {e}")

    # 步骤 2: 停止 WorkerService（清理 ZMQ 通信资源）
    try:
        from worker.service import worker_service
        await asyncio.wait_for(worker_service.shutdown(), timeout=10.0)
        logger.info("WorkerService 已停止")
    except asyncio.CancelledError:
        logger.warning("WorkerService 停止被中断")
        raise
    except Exception as e:
        logger.error(f"停止 WorkerService 失败: {e}")

    # 步骤 3: 停止实时引擎
    if realtime_engine:
        try:
            await realtime_engine.stop()
            logger.info("实时引擎已停止")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"停止实时引擎失败: {e}")

    # 步骤 4: 停止系统状态推送服务
    try:
        if hasattr(app.state, "system_service"):
            await app.state.system_service.stop_system_status_push()
            logger.info("系统状态推送服务已停止")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"停止系统状态推送服务失败: {e}")

    # 步骤 5: 停止 WebSocket 连接管理器
    try:
        await manager.stop()
        logger.info("WebSocket连接管理器已停止")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"停止 WebSocket 连接管理器失败: {e}")

    # 步骤 6: 取消后台任务
    try:
        if hasattr(app.state, "symbol_sync_task") and not app.state.symbol_sync_task.done():
            app.state.symbol_sync_task.cancel()
            logger.info("已取消货币对同步任务")
    except Exception as e:
        logger.error(f"取消货币对同步任务失败: {e}")

    # 步骤 7: 关闭调度器和插件
    try:
        await asyncio.to_thread(traditional_scheduler.shutdown)
        await asyncio.to_thread(scheduled_task_manager.shutdown)
        await asyncio.to_thread(plugin_manager.stop_all_plugins)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"关闭调度器或插件失败: {e}")

    logger.info("========== 应用关闭完成 ==========")


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
