# -*- coding: utf-8 -*-
"""
应用生命周期管理模块

管理FastAPI应用的启动和关闭生命周期
"""

import asyncio
import os
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
from plugins import PluginManager
from plugins.event_bus import event_bus
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

    # 自动扫描并初始化策略到数据库
    await asyncio.to_thread(_init_strategies)

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

    plugin_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "installed_plugins"
    )
    os.makedirs(plugin_dir, exist_ok=True)
    plugin_manager = await asyncio.to_thread(PluginManager, app=app, plugin_dir=plugin_dir)
    await asyncio.to_thread(plugin_manager.load_all_plugins)
    plugin_manager.register_plugins(app)
    app.state.plugin_manager = plugin_manager
    app.state.plugin_api = plugin_manager
    app.state.event_bus = event_bus

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

    # 初始化 TradingEngine（paper 模式默认配置）
    try:
        from engine.trading_engine import get_trading_engine
        from engine.config import EngineConfig
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        app.state.trading_engine = engine
        logger.info(f"TradingEngine 初始化完成: {engine.engine_status()}")
    except Exception as e:
        logger.error(f"TradingEngine 初始化失败: {e}")

    # 初始化 Worker System（全局单例，统一管理所有 Worker）
    _worker_system_available = False
    try:
        from worker.axon_worker_system import worker_system
        _worker_system_available = True
        logger.info("正在初始化 Worker System...")
        try:
            await worker_system.initialize()
            summary = worker_system.get_summary()
            state = worker_system.get_system_state()
            logger.info(
                f"✓ Worker System 初始化完成 | "
                f"axon_quant: 已连接 | "
                f"Worker 总数: {summary['total_workers']} | "
                f"状态分布: {summary['status_breakdown']}"
            )
        except Exception as init_err:
            logger.error(f"Worker System 初始化失败: {init_err}")
            logger.warning(
                "Worker 相关功能将不可用，但其他 API 正常工作。"
                "可后续通过 CLI 手动初始化 (worker_cli.py init)"
            )
    except ImportError as import_err:
        logger.warning(f"Worker System 模块导入失败（可能缺少依赖）: {import_err}")
        logger.warning("Worker 功能将被禁用，不影响其他功能运行")
    except Exception as import_err:
        logger.error(f"Worker System 导入时发生意外错误: {import_err}")

    yield

    # ========== 应用关闭阶段（必须保证执行完毕） ==========
    # 独立事件循环设计：每个 TradingNode 使用独立 asyncio 循环（非 uvicorn 主循环）
    # uvicorn 的 SIGINT 处理器始终有效，shutdown 流程正常触发
    import time as _time, threading as _th, os as _os

    _shutdown_start = _time.monotonic()

    # 2秒强制退出定时器（兜底：即使事件循环/线程卡死，也能快速退出）
    def _force_exit_timer():
        _th.Event().wait(2.0)
        _elapsed = _time.monotonic() - _shutdown_start
        import logging as _log
        _log.getLogger(__name__).warning(
            f"[FORCE EXIT] 2秒强制退出定时器触发 (已等待 {_elapsed:.2f}s)"
        )
        _os._exit(0)

    _force_thread = _th.Thread(target=_force_exit_timer, daemon=True, name="force-exit-timer")
    _force_thread.start()

    logger.info("========== 应用开始关闭 ==========")

    # 步骤 1: 关闭 Worker System 全局单例（统一管理：停止进程 + 清理状态 + 关闭Manager后台任务）
    if _worker_system_available:
        try:
            from worker.axon_worker_system import worker_system
            logger.info("正在关闭 Worker System...")
            try:
                worker_system.shutdown()
                logger.info("✓ Worker System 已优雅关闭")
            except Exception as ws_err:
                logger.error(f"Worker System 关闭失败: {ws_err}")
        except ImportError:
            logger.debug("Worker System 模块不可用，跳过关闭")
        except asyncio.CancelledError:
            logger.warning("Worker System 关闭被中断")
            raise
        except Exception as e:
            logger.error(f"关闭 Worker System 时发生意外错误: {e}")

    # 步骤 3: 停止实时引擎（带超时保护）
    if realtime_engine:
        try:
            await asyncio.wait_for(realtime_engine.stop(), timeout=1.0)
            logger.info("实时引擎已停止")
        except asyncio.TimeoutError:
            logger.warning("实时引擎停止超时（>1s），强制跳过")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"停止实时引擎失败: {e}")

    # 步骤 4: 停止系统状态推送服务（带超时保护）
    try:
        if hasattr(app.state, "system_service"):
            await asyncio.wait_for(
                app.state.system_service.stop_system_status_push(),
                timeout=1.0
            )
            logger.info("系统状态推送服务已停止")
    except asyncio.TimeoutError:
        logger.warning("系统状态推送服务停止超时（>1s），强制跳过")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"停止系统状态推送服务失败: {e}")

    # 步骤 4.5: 停止 TradingEngine 中所有运行的策略
    try:
        if hasattr(app.state, "trading_engine"):
            engine = app.state.trading_engine
            for rt in list(engine._strategies.values()):
                if rt.status == "running" and rt.loop:
                    try:
                        engine.stop_strategy(rt.strategy_id)
                    except Exception as stop_err:
                        logger.error(f"停止策略 {rt.strategy_id} 失败: {stop_err}")
            logger.info("TradingEngine 所有策略已停止")
    except Exception as e:
        logger.error(f"TradingEngine 关闭失败: {e}")

    # 步骤 5: 停止 WebSocket 连接管理器（带超时保护）
    try:
        await asyncio.wait_for(manager.stop(), timeout=1.0)
        logger.info("WebSocket连接管理器已停止")
    except asyncio.TimeoutError:
        logger.warning("WebSocket连接管理器停止超时（>1s），强制跳过")
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

    # 步骤 7: 关闭调度器和插件（带超时保护，使用线程池执行器）
    try:
        # 使用 asyncio.to_thread 配合 wait_for 实现超时控制
        async def _shutdown_schedulers():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, traditional_scheduler.shutdown)
            await loop.run_in_executor(None, scheduled_task_manager.shutdown)
            await loop.run_in_executor(None, plugin_manager.stop_all_plugins)
            await loop.run_in_executor(None, event_bus.clear)

        await asyncio.wait_for(_shutdown_schedulers(), timeout=1.5)
        logger.info("调度器和插件已全部关闭")
    except asyncio.TimeoutError:
        logger.warning("调度器或插件关闭超时（>1.5s），强制跳过")
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


def _init_strategies():
    """自动扫描策略目录，将新策略初始化到数据库

    在 FastAPI 启动时自动执行：
    1. 扫描 backend/strategies/ 目录下的 .py 文件
    2. 对每个策略文件，检查数据库中是否已存在同名策略
    3. 如果不存在，解析策略文件内容并插入数据库
    4. 输出初始化结果日志
    """
    import json
    from pathlib import Path

    try:
        from strategy.service import StrategyService
        from collector.db.database import SessionLocal, init_database_config
        from strategy.models import Strategy
    except ImportError as e:
        logger.warning(f"策略初始化模块导入失败，跳过策略自动初始化: {e}")
        return

    try:
        strategy_service = StrategyService()
        strategy_dir = strategy_service.strategy_dir

        if not strategy_dir.exists():
            logger.info(f"策略目录不存在: {strategy_dir}，跳过策略初始化")
            return

        strategy_files = [f for f in strategy_dir.glob("*.py") if f.stem != "__init__"]

        if not strategy_files:
            logger.info("策略目录为空，跳过策略初始化")
            return

        init_database_config()
        db = SessionLocal()

        added = 0
        skipped = 0
        failed = 0

        try:
            for file_path in strategy_files:
                existing = db.query(Strategy).filter_by(name=file_path.stem).first()
                if existing:
                    skipped += 1
                    continue

                strategy_info = strategy_service._parse_strategy_file(file_path)
                if not strategy_info:
                    failed += 1
                    logger.warning(f"策略解析失败: {file_path.name}")
                    continue

                params = strategy_info.get("params", [])
                tags = strategy_info.get("tags", [])
                logger.info(f"策略解析结果: name={strategy_info['name']}, params_type={type(params).__name__}, params={params}, tags_type={type(tags).__name__}, tags={tags}")

                if isinstance(params, str):
                    logger.warning(f"策略参数为字符串类型，尝试解析JSON: {params}")
                    import json
                    try:
                        params = json.loads(params) if params else []
                    except json.JSONDecodeError:
                        params = []
                if not isinstance(params, list):
                    params = []

                if isinstance(tags, str):
                    logger.warning(f"策略标签为字符串类型，尝试解析JSON: {tags}")
                    import json
                    try:
                        tags = json.loads(tags) if tags else []
                    except json.JSONDecodeError:
                        tags = []
                if not isinstance(tags, list):
                    tags = []

                new_strategy = Strategy(
                    name=strategy_info["name"],
                    file_name=strategy_info["file_name"],
                    file_path=strategy_info.get("file_path", str(file_path)),
                    code=strategy_info.get("code", ""),
                    description=strategy_info.get("description", ""),
                    version=strategy_info.get("version", "1.0.0"),
                )
                new_strategy.set_parameters_list(params)
                new_strategy.set_tags_list(tags)
                db.add(new_strategy)
                added += 1
                logger.info(f"策略已初始化: {strategy_info['name']}, params_count={len(params)}, tags_count={len(tags)}")

            db.commit()
            logger.info(f"策略初始化完成: 新增 {added} 个, 跳过 {skipped} 个, 失败 {failed} 个")
        except Exception as e:
            db.rollback()
            logger.error(f"策略初始化事务失败: {e}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"策略初始化失败: {e}")
