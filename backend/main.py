import asyncio
from contextlib import asynccontextmanager
from typing import Union

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# 配置日志
from loguru import logger

from backtest.routes import router as backtest_router
from collector.routes import router as collector_router
from factor.routes import router as factor_router
from model.routes import router as model_router

# 导入插件系统
from plugins import init_plugin_system, global_plugin_manager

# 导入国际化配置
from pathlib import Path
import json
from typing import Dict, Any


def init_database():
    """初始化数据库
    
    Returns:
        None: 无返回值
    """
    from collector.db import init_db
    init_db()
    
    # 初始化任务管理器，确保数据库表已创建
    from collector.utils.task_manager import task_manager
    task_manager.init()
    
    # 初始化定时任务管理器，确保数据库表已创建
    from collector.utils.scheduled_task_manager import scheduled_task_manager
    logger.info("初始化定时任务管理器")


def init_qlib():
    """初始化QLib数据加载器
    
    Returns:
        None: 无返回值
    """
    from collector.data_loader import data_loader
    from collector.db import SystemConfigBusiness as SystemConfig
    
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


# 导入系统配置加载函数
from config_manager import load_system_configs


def start_scheduler(
    proxy_enabled: bool = False,
    proxy_url: str = None,
    proxy_username: str = None,
    proxy_password: str = None
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
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    from scripts.sync_crypto_symbols import sync_crypto_symbols
    from scripts.update_features import main as update_features_main

    # 创建后台调度器
    scheduler = BackgroundScheduler()
    
    # 添加定时任务：每天凌晨1点执行一次
    scheduler.add_job(
        func=update_features_main,
        trigger=CronTrigger(hour=1, minute=0),
        id='update_features',
        name='Update features information',
        replace_existing=True
    )
    
    # 添加立即执行一次的任务，用于初始化特征信息
    scheduler.add_job(
        func=update_features_main,
        trigger='date',
        run_date=None,  # 立即执行
        id='update_features_init',
        name='Initialize features information',
        replace_existing=True
    )
    
    # 添加定时任务：每周日凌晨2点执行一次，同步加密货币对
    scheduler.add_job(
        func=lambda: sync_crypto_symbols(
            proxy_enabled=proxy_enabled,
            proxy_url=proxy_url,
            proxy_username=proxy_username,
            proxy_password=proxy_password
        ),
        trigger=CronTrigger(day_of_week=6, hour=2, minute=0),  # 每周日凌晨2点
        id='sync_crypto_symbols',
        name='Sync cryptocurrency symbols',
        replace_existing=True
    )
    
    # 添加立即执行一次的任务，用于初始化货币对数据
    scheduler.add_job(
        func=lambda: sync_crypto_symbols(
            proxy_enabled=proxy_enabled,
            proxy_url=proxy_url,
            proxy_username=proxy_username,
            proxy_password=proxy_password
        ),
        trigger='date',
        run_date=None,  # 立即执行
        id='sync_crypto_symbols_init',
        name='Initialize cryptocurrency symbols',
        replace_existing=True
    )
    
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
    # 启动时异步初始化数据库
    await asyncio.to_thread(init_database)
    
    # 异步初始化QLib数据加载器
    await asyncio.to_thread(init_qlib)
    
    # 异步加载系统配置到应用上下文
    app.state.configs = await asyncio.to_thread(load_system_configs)
    
    # 从配置中提取代理信息
    proxy_enabled = app.state.configs.get("proxy_enabled", False)
    proxy_url = app.state.configs.get("proxy_url", None)
    proxy_username = app.state.configs.get("proxy_username", None)
    proxy_password = app.state.configs.get("proxy_password", None)
    
    logger.info(f"代理配置: enabled={proxy_enabled}, url={proxy_url}")
    
    # 异步启动传统定时任务，传递代理配置
    traditional_scheduler = await asyncio.to_thread(
        start_scheduler,
        proxy_enabled=proxy_enabled,
        proxy_url=proxy_url,
        proxy_username=proxy_username,
        proxy_password=proxy_password
    )
    
    # 异步启动新的定时任务管理器
    from collector.utils.scheduled_task_manager import scheduled_task_manager
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
    
    yield
    
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
        "zh-CN": {
            "welcome": "欢迎使用量化交易系统",
            "current_locale": "当前语言"
        },
        "en-US": {
            "welcome": "Welcome to Quantitative Trading System",
            "current_locale": "Current Language"
        }
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
        "http://127.0.0.1:5174"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册数据处理API路由
app.include_router(collector_router)

# 注册因子计算API路由
app.include_router(factor_router)

# 注册模型训练API路由
app.include_router(model_router)

# 注册回测服务API路由
app.include_router(backtest_router)

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
            return {"message": "Welcome to Quantitative Trading System", "current_locale": "en-US"}
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
        host="127.0.0.1",  # 主机地址
        port=8000,  # 端口号
        reload=False  # 禁用热重载，避免DuckDB锁冲突
    )
    