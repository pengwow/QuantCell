# -*- coding: utf-8 -*-
"""
QuantCell 主入口文件

仅保留应用初始化和入口级功能，所有业务逻辑已迁移至：
- services/: 业务逻辑模块
- core/: 核心功能模块（生命周期、调度器）
- api/: API路由模块
- utils/: 工具模块
"""

import os
from pathlib import Path
from typing import List

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


def get_cors_origins() -> List[str]:
    """
    获取CORS允许的源列表

    从配置文件、端口信息文件和环境变量中动态构建CORS源列表

    Returns:
        List[str]: 允许的CORS源列表
    """
    origins = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # 从端口信息文件读取前端端口
    try:
        project_root = Path(__file__).resolve().parent.parent
        ports_file = project_root / ".quantcell" / "ports.json"
        if ports_file.exists():
            import json
            with open(ports_file, "r", encoding="utf-8") as f:
                ports_data = json.load(f)

            # 添加前端端口
            if "frontend" in ports_data and "port" in ports_data["frontend"]:
                frontend_port = ports_data["frontend"]["port"]
                for host in ["localhost", "127.0.0.1"]:
                    origin = f"http://{host}:{frontend_port}"
                    if origin not in origins:
                        origins.append(origin)
                        logger.debug(f"从端口文件添加CORS源: {origin}")

            # 添加后端端口（用于直接访问）
            if "backend" in ports_data and "port" in ports_data["backend"]:
                backend_port = ports_data["backend"]["port"]
                for host in ["localhost", "127.0.0.1"]:
                    origin = f"http://{host}:{backend_port}"
                    if origin not in origins:
                        origins.append(origin)
    except Exception as e:
        logger.debug(f"读取端口信息文件失败: {e}")

    # 从配置文件读取端口范围
    try:
        config_file = Path(__file__).resolve().parent / "config.toml"
        if config_file.exists():
            import tomllib
            with open(config_file, "rb") as f:
                config = tomllib.load(f)

            ports_config = config.get("ports", {})

            # 前端端口范围
            frontend_start = ports_config.get("frontend_range_start", 5173)
            frontend_end = ports_config.get("frontend_range_end", 5183)

            for port in range(frontend_start, frontend_end + 1):
                for host in ["localhost", "127.0.0.1"]:
                    origin = f"http://{host}:{port}"
                    if origin not in origins:
                        origins.append(origin)
    except Exception as e:
        logger.debug(f"读取配置文件失败: {e}")

    # 从环境变量读取额外配置
    extra_origins = os.getenv("CORS_ORIGINS", "")
    if extra_origins:
        for origin in extra_origins.split(","):
            origin = origin.strip()
            if origin and origin not in origins:
                origins.append(origin)
                logger.debug(f"从环境变量添加CORS源: {origin}")

    return origins


# 创建FastAPI应用实例
app = FastAPI(
    title="QuantCell API",
    description="量化交易系统API",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件配置
# 使用动态获取的CORS源列表
_cors_origins = get_cors_origins()
logger.info(f"CORS允许的源: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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


@app.get("/api/system/ports")
async def get_ports_info():
    """获取端口信息

    Returns:
        dict: 前后端端口信息
    """
    from utils.port_manager import get_port_manager

    port_manager = get_port_manager()
    all_info = port_manager.get_all_port_info()

    return {
        "backend": all_info.get("backend", {}).get("port"),
        "frontend": all_info.get("frontend", {}).get("port"),
        "cors_origins": _cors_origins,
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
    import tomllib

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


if __name__ == "__main__":
    """当直接运行此文件时启动FastAPI应用服务器

    使用uvicorn作为ASGI服务器，在本地主机的8000端口启动应用
    禁用自动重载功能，避免DuckDB锁冲突
    """
    from collector.db import init_db
    import uvicorn

    # 只在主进程中初始化数据库，避免热重载时的锁冲突
    init_db()

    # 获取日志级别配置
    log_level = get_uvicorn_log_level()
    print(f"Uvicorn日志级别设置为: {log_level}")

    uvicorn.run(
        "main:app",  # 指定应用路径
        host="localhost",  # 主机地址
        port=8000,  # 端口号
        reload=False,  # 禁用热重载，避免DuckDB锁冲突
        log_level=log_level.lower(),  # 设置日志级别
    )
