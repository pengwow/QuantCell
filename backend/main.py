from typing import Union
from contextlib import asynccontextmanager

from fastapi import FastAPI
from collector.routes import router as collector_router
from factor.routes import router as factor_router
from model.routes import router as model_router
from backtest.routes import router as backtest_router

# 配置日志
from loguru import logger


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


def start_scheduler():
    """启动定时任务调度器
    
    Returns:
        BackgroundScheduler: 后台调度器实例
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
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
    # 启动时初始化数据库
    init_database()
    
    # 初始化QLib数据加载器
    init_qlib()
    
    # 加载系统配置到应用上下文
    app.state.configs = load_system_configs()
    
    # 启动定时任务
    scheduler = start_scheduler()
    
    yield
    
    # 关闭时的清理工作
    scheduler.shutdown()



app = FastAPI(lifespan=lifespan)

# 注册数据处理API路由
app.include_router(collector_router)

# 注册因子计算API路由
app.include_router(factor_router)

# 注册模型训练API路由
app.include_router(model_router)

# 注册回测服务API路由
app.include_router(backtest_router)


@app.get("/")
def read_root():
    """根路径的处理函数
    
    Returns:
        dict: 返回一个包含问候语的字典
    """
    return {"Hello": "World"}


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
    