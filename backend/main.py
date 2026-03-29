# -*- coding: utf-8 -*-
"""
QuantCell 主入口文件

仅保留应用初始化和入口级功能，所有业务逻辑已迁移至：
- services/: 业务逻辑模块
- core/: 核心功能模块（生命周期、调度器）
- api/: API路由模块
- utils/: 工具模块
"""

# 首先导入策略模型和回测模型以确保正确的表结构被使用
# 这必须在导入 collector.db.models 之前完成
import strategy.models  # noqa: F401
import backtest.models  # noqa: F401

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 导入核心模块
from core import lifespan
from utils.logger import get_logger, LogType

# 获取主模块日志器
logger = get_logger(__name__, LogType.SYSTEM)

# 导入业务模块路由（标准化模块化架构）
from ai_model import router as ai_model_router
from ai_model.routes_strategy import router as ai_model_strategy_router
from backtest import router as backtest_router
from collector.routes import router as collector_router
from factor import router as factor_router
from indicators.routes import router as indicators_router
from model.routes import router as model_router
from settings.routes import router as settings_router
from strategy import router as strategy_router
from websocket.routes import router as websocket_router
from realtime.routes import realtime_router
from worker import router as worker_router
from utils.log_routes import router as log_router
from common.notifications.routes import router as notification_router


# 创建FastAPI应用实例
app = FastAPI(
    title="QuantCell API",
    description="量化交易系统API",
    version="1.0.0",
    lifespan=lifespan
)

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

# 注册业务路由（保持向后兼容）
app.include_router(ai_model_router)
app.include_router(ai_model_strategy_router)
app.include_router(collector_router)
app.include_router(settings_router)
app.include_router(factor_router)
app.include_router(indicators_router)
app.include_router(model_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(realtime_router)
app.include_router(websocket_router)
app.include_router(worker_router)
app.include_router(log_router)
app.include_router(notification_router)

# 插件路由注册会在应用启动时通过lifespan函数完成
# 这里不需要提前注册，插件会在应用启动时动态加载和注册


@app.get("/")
async def read_root():
    """根路径处理函数

    Returns:
        dict: 欢迎信息
    """
    return {
        "message": "欢迎使用量化交易系统",
        "current_locale": "zh-CN"
    }


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    """获取指定item_id的项目信息

    Args:
        item_id: 项目ID
        q: 可选的查询参数

    Returns:
        dict: 返回包含项目ID和查询参数的字典
    """
    return {"item_id": item_id, "q": q}


def get_uvicorn_log_level() -> str:
    """获取uvicorn日志级别

    从环境变量或配置文件读取日志级别，默认为INFO

    Returns:
        str: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    import os
    import tomllib
    from pathlib import Path

    # 首先检查环境变量
    env_level = os.getenv("LOG_LEVEL")
    if env_level:
        return env_level.upper()

    # 然后检查配置文件
    config_paths = [
        Path(__file__).parent / "config.toml",
        Path(__file__).parent / "config.local.toml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                    level = config.get("logging", {}).get("level", "INFO")
                    return level.upper()
            except Exception:
                pass

    return "INFO"


def parse_args():
    """解析命令行参数

    Returns:
        argparse.Namespace: 解析后的参数
    """
    import argparse

    parser = argparse.ArgumentParser(description="QuantCell API Server")
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="服务器监听地址 (默认: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="服务器监听端口 (默认: 8000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式 (设置日志级别为 DEBUG)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    """当直接运行此文件时启动FastAPI应用服务器

    使用uvicorn作为ASGI服务器，在本地主机的8000端口启动应用
    禁用自动重载功能，避免DuckDB锁冲突
    """
    from collector.db import init_db
    import uvicorn

    # 解析命令行参数
    args = parse_args()

    # 只在主进程中初始化数据库，避免热重载时的锁冲突
    init_db()

    # 获取日志级别配置
    if args.debug:
        log_level = "DEBUG"
        print("调试模式已启用")
    else:
        log_level = get_uvicorn_log_level()
    print(f"Uvicorn日志级别设置为: {log_level}")
    print(f"服务器将在 {args.host}:{args.port} 启动")

    uvicorn.run(
        "main:app",  # 指定应用路径
        host=args.host,  # 主机地址
        port=args.port,  # 端口号
        reload=False,  # 禁用热重载，避免DuckDB锁冲突
        log_level=log_level.lower(),  # 设置日志级别
    )
