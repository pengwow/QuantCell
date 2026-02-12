# -*- coding: utf-8 -*-
"""
QuantCell 主入口文件

仅保留应用初始化和入口级功能，所有业务逻辑已迁移至：
- services/: 业务逻辑模块
- core/: 核心功能模块（生命周期、调度器）
- api/: API路由模块
- utils/: 工具模块
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# 导入核心模块
from core import lifespan

# 导入API路由
from api import system_router

# 导入业务模块路由（标准化模块化架构）
from backtest import router as backtest_router
from collector.routes import router as collector_router
from factor import router as factor_router
from model.routes import router as model_router
from settings.routes import router as settings_router
from strategy import router as strategy_router
from websocket.routes import router as websocket_router
from realtime.routes import realtime_router


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

# 注册系统管理API路由（新增重构后的路由）
app.include_router(system_router)

# 注册原有业务路由（保持向后兼容）
app.include_router(collector_router)
app.include_router(settings_router)
app.include_router(factor_router)
app.include_router(model_router)
app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(realtime_router)
app.include_router(websocket_router)

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


if __name__ == "__main__":
    """当直接运行此文件时启动FastAPI应用服务器

    使用uvicorn作为ASGI服务器，在本地主机的8000端口启动应用
    禁用自动重载功能，避免DuckDB锁冲突
    """
    from collector.db import init_db
    import uvicorn

    # 只在主进程中初始化数据库，避免热重载时的锁冲突
    init_db()

    uvicorn.run(
        "main:app",  # 指定应用路径
        host="localhost",  # 主机地址
        port=8000,  # 端口号
        reload=False,  # 禁用热重载，避免DuckDB锁冲突
    )
