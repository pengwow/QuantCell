import asyncio
from contextlib import asynccontextmanager
from math import log
from typing import Union

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 配置日志
from loguru import logger

from backtest.routes import router as backtest_router
from collector.routes import router as collector_router
from factor.routes import router as factor_router
from model.routes import router as model_router
from settings.api import router as settings_router
from strategy.routes import router_strategy as strategy_router
from collector.services.system_service import SystemService
from collector.db import init_db
from collector.utils.task_manager import task_manager
from collector.utils.scheduled_task_manager import scheduled_task_manager
from collector.data_loader import data_loader
from collector.db import SystemConfigBusiness as SystemConfig
from collector.db.database import SessionLocal, init_database_config
from collector.db.models import CryptoSymbol
from collector.services.data_service import DataService
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from scripts.sync_crypto_symbols import sync_crypto_symbols
from scripts.update_features import main as update_features_main
from collector.utils.scheduled_task_manager import scheduled_task_manager
from backtest.demo_service import DemoService
from websocket.manager import manager

# 导入系统配置加载函数
from config_manager import load_system_configs

# 导入实时引擎
from realtime.engine import RealtimeEngine
from realtime.routes import setup_routes

# 全局实时引擎实例
realtime_engine = None


# 导入插件系统
from plugins import init_plugin_system, global_plugin_manager

# 导入WebSocket路由
from websocket.routes import router as websocket_router

# 导入国际化配置
from pathlib import Path
import json
from typing import Dict, Any


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


def init_qlib():
    """初始化QLib数据加载器

    Returns:
        None: 无返回值
    """

    logger.info("开始初始化QLib数据加载器")

    # 从系统配置获取qlib_data_dir
    qlib_dir = SystemConfig.get("qlib_data_dir")

    if not qlib_dir:
        qlib_dir = "data/crypto_data"
        logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")

    # 尝试初始化QLib
    try:
        success = data_loader.init_qlib(qlib_dir)
        if success:
            logger.info(f"QLib初始化成功，数据目录: {qlib_dir}")
        else:
            logger.warning(f"QLib初始化失败，数据目录: {qlib_dir}，将在需要时重新尝试")
    except Exception as e:
        logger.error(f"QLib初始化异常: {e}")
        logger.exception(e)


def check_and_sync_crypto_symbols():
    """检查并同步加密货币对数据

    检查数据库中货币对的最后更新时间，如果超过24小时则触发同步
    使用updated_at字段判断，无需新增字段
    """
    logger.info("开始检查加密货币对同步状态")

    try:

        # 初始化数据库配置
        init_database_config()

        db = SessionLocal()
        try:
            # 获取所有交易所
            exchanges = db.query(CryptoSymbol.exchange).distinct().all()
            exchanges = [exchange[0] for exchange in exchanges]

            # 如果没有交易所数据，添加默认交易所
            if not exchanges:
                exchanges = ["binance"]

            # 加载系统配置
            configs = load_system_configs()

            # 检查每个交易所的同步状态
            for exchange in exchanges:
                # 获取该交易所的最后更新时间
                last_sync = (
                    db.query(CryptoSymbol.updated_at)
                    .filter(CryptoSymbol.exchange == exchange)
                    .order_by(CryptoSymbol.updated_at.desc())
                    .first()
                )

                # 检查是否需要同步
                need_sync = False
                if not last_sync:
                    need_sync = True
                    logger.info(f"交易所 {exchange} 没有同步记录，需要同步")
                else:
                    # 计算时间差
                    time_diff = datetime.now() - last_sync[0]
                    if time_diff > timedelta(hours=24):
                        need_sync = True
                        logger.info(f"交易所 {exchange} 数据已超过24小时，需要同步")
                    else:
                        logger.info(
                            f"交易所 {exchange} 数据同步正常，最后同步时间: {last_sync[0]}"
                        )

                # 如果需要同步，调用同步方法
                if need_sync:
                    logger.info(f"开始同步交易所 {exchange} 的货币对数据")
                    data_service = DataService()
                    # 使用空配置，让方法使用默认值
                    result = data_service.fetch_symbols_from_exchange(
                        exchange=exchange, configs=configs
                    )
                    if result["success"]:
                        logger.info(f"交易所 {exchange} 货币对同步成功")
                    else:
                        logger.error(
                            f"交易所 {exchange} 货币对同步失败: {result.get('error')}"
                        )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"检查加密货币对同步状态失败: {e}")
        logger.exception(e)


def start_scheduler(
    proxy_enabled: str = "0",
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
    # 转换proxy_enabled为布尔值
    proxy_enabled_bool = str(proxy_enabled).strip().lower() in ["1", "true", "yes"]

    # 创建后台调度器
    scheduler = BackgroundScheduler()

    # 添加定时任务：每天凌晨1点执行一次
    scheduler.add_job(
        func=update_features_main,
        trigger=CronTrigger(hour=1, minute=0),
        id="update_features",
        name="Update features information",
        replace_existing=True,
    )

    # 添加立即执行一次的任务，用于初始化特征信息
    scheduler.add_job(
        func=update_features_main,
        trigger="date",
        run_date=None,  # 立即执行
        id="update_features_init",
        name="Initialize features information",
        replace_existing=True,
    )

    # 添加定时任务：每周日凌晨2点执行一次，同步加密货币对
    scheduler.add_job(
        func=lambda: sync_crypto_symbols(
            proxy_enabled=proxy_enabled_bool,
            proxy_url=proxy_url,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
        ),
        trigger=CronTrigger(day_of_week=6, hour=2, minute=0),  # 每周日凌晨2点
        id="sync_crypto_symbols",
        name="Sync cryptocurrency symbols",
        replace_existing=True,
    )

    # 注释掉立即执行的加密货币对同步任务，避免启动时连接交易所API失败
    # scheduler.add_job(
    #     func=lambda: sync_crypto_symbols(
    #         proxy_enabled=proxy_enabled,
    #         proxy_url=proxy_url,
    #         proxy_username=proxy_username,
    #         proxy_password=proxy_password
    #     ),
    #     trigger='date',
    #     run_date=None,  # 立即执行
    #     id='sync_crypto_symbols_init',
    #     name='Initialize cryptocurrency symbols',
    #     replace_existing=True
    # )

    # 启动调度器
    scheduler.start()
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    Args:
        app: FastAPI应用实例

    Yields:
        None: 无返回值
    """
    global realtime_engine

    # 启动时异步初始化数据库
    await asyncio.to_thread(init_database)

    # 异步初始化QLib数据加载器
    # await asyncio.to_thread(init_qlib)

    # 异步加载系统配置到应用上下文
    app.state.configs = await asyncio.to_thread(load_system_configs)
    logger.info(f"系统配置: {app.state.configs}")
    # 异步检查并同步加密货币对数据
    await asyncio.to_thread(check_and_sync_crypto_symbols)

    # 从配置中提取代理信息
    proxy_enabled = app.state.configs.get("proxy_enabled", "0")
    proxy_url = app.state.configs.get("proxy_url", "")
    proxy_username = app.state.configs.get("proxy_username", "")
    proxy_password = app.state.configs.get("proxy_password", "")

    logger.info(f"代理配置: enabled={proxy_enabled}, url={proxy_url}")

    # 异步启动传统定时任务，传递代理配置
    traditional_scheduler = await asyncio.to_thread(
        start_scheduler,
        proxy_enabled=proxy_enabled,
        proxy_url=proxy_url,
        proxy_username=proxy_username,
        proxy_password=proxy_password,
    )

    # 异步启动新的定时任务管理器

    await asyncio.to_thread(scheduled_task_manager.start)

    # 异步初始化演示数据
    try:

        demo_service = DemoService()
        await asyncio.to_thread(demo_service.ensure_demo_data)
        logger.info("演示数据初始化完成")
    except Exception as e:
        logger.error(f"演示数据初始化失败: {e}")

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


# 国际化配置
def get_translation_dict():
    """获取翻译字典，直接返回硬编码的翻译内容，避免文件加载问题"""
    return {
        "zh-CN": {"welcome": "欢迎使用量化交易系统", "current_locale": "当前语言"},
        "en-US": {
            "welcome": "Welcome to Quantitative Trading System",
            "current_locale": "Current Language",
        },
    }


# 从请求头中提取语言代码
def extract_lang(accept_language: str) -> str:
    """从Accept-Language头中提取语言代码

    Args:
        accept_language: Accept-Language头的值

    Returns:
        str: 提取的语言代码
    """
    if not accept_language:
        return "zh-CN"

    # 提取第一个语言代码
    lang = accept_language.split(",")[0].strip()
    # 标准化语言代码格式
    lang = lang.split(";")[0].replace("_", "-")
    # 确保返回的语言代码在支持列表中
    supported_langs = ["zh-CN", "en-US"]
    return lang if lang in supported_langs else "zh-CN"


app = FastAPI(lifespan=lifespan)

# 添加CORS中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册数据处理API路由
app.include_router(collector_router)

# 注册系统设置API路由
app.include_router(settings_router)

# 注册因子计算API路由
app.include_router(factor_router)

# 注册模型训练API路由
app.include_router(model_router)

# 注册策略服务API路由
app.include_router(strategy_router)

# 注册回测服务API路由
app.include_router(backtest_router)

# 注册实时引擎API路由
from realtime.routes import realtime_router

app.include_router(realtime_router)

# 注册WebSocket路由
app.include_router(websocket_router)

# 插件路由注册会在应用启动时通过lifespan函数完成
# 这里不需要提前注册，插件会在应用启动时动态加载和注册


@app.get("/")
async def read_root(accept_language: str = "zh-CN"):
    """根路径的处理函数

    Args:
        accept_language: 请求头中的Accept-Language值

    Returns:
        dict: 返回一个包含问候语的字典
    """
    try:
        # 从请求头中提取语言代码
        if not accept_language:
            lang = "zh-CN"
        else:
            # 提取第一个语言代码
            lang = accept_language.split(",")[0].strip()
            # 标准化语言代码格式
            lang = lang.split(";")[0].replace("_", "-")

        # 直接返回硬编码的翻译内容，避免任何外部依赖
        if lang == "en-US":
            return {
                "message": "Welcome to Quantitative Trading System",
                "current_locale": "en-US",
            }
        else:
            return {"message": "欢迎使用量化交易系统", "current_locale": "zh-CN"}
    except Exception as e:
        logger.exception(f"国际化处理错误: {e}")
        return {"message": "内部服务器错误", "error": str(e), "status_code": 500}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    """获取指定item_id的项目信息

    Args:
        item_id: 项目ID
        q: 可选的查询参数

    Returns:
        dict: 返回包含项目ID和查询参数的字典
    """
    return {"item_id": item_id, "q": q}


@app.get("/api/config/plugin/{plugin_name}")
def get_plugin_config(plugin_name: str):
    """获取指定插件的所有配置

    Args:
        plugin_name: 插件名称

    Returns:
        dict: 包含插件配置的响应
    """
    try:
        logger.info(f"开始获取插件配置: {plugin_name}")

        # 导入系统配置业务逻辑
        from collector.db import SystemConfigBusiness as SystemConfig

        # 获取所有配置的详细信息
        all_configs = SystemConfig.get_all_with_details()

        # 过滤出与指定插件相关的配置
        plugin_configs = {}
        for key, config in all_configs.items():
            if config.get("plugin") == plugin_name:
                plugin_configs[key] = config["value"]

        logger.info(f"成功获取插件配置，共 {len(plugin_configs)} 项")

        return {"code": 0, "message": "获取插件配置成功", "data": plugin_configs}
    except Exception as e:
        logger.error(f"获取插件配置失败: {e}")
        return {"code": 500, "message": f"获取插件配置失败: {str(e)}", "data": {}}


if __name__ == "__main__":
    """当直接运行此文件时启动FastAPI应用服务器

    使用uvicorn作为ASGI服务器，在本地主机的8000端口启动应用
    禁用自动重载功能，避免DuckDB锁冲突
    """
    from collector.db import init_db

    # 只在主进程中初始化数据库，避免热重载时的锁冲突
    init_db()
    import uvicorn

    uvicorn.run(
        "main:app",  # 指定应用路径
        host="localhost",  # 主机地址
        port=8000,  # 端口号
        reload=False,  # 禁用热重载，避免DuckDB锁冲突
    )
