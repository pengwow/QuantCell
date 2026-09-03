# 数据处理API路由定义


from fastapi import APIRouter, HTTPException

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)

from .api.archive import router as archive_router
from .api.data import router as data_router
from .api.data_pool import router as data_pool_router
from .api.deriv import router as deriv_router
from .api.exchanges import router as exchanges_router
from .api.market_data import router as market_data_router
from .api.scheduled_tasks import router as scheduled_tasks_router
from .api.system import router as system_router
from .schemas import ApiResponse

# 创建API路由实例
router = APIRouter(prefix="/api")

# 注册数据加载API路由
router.include_router(data_router)

# 注册资产池管理API路由
router.include_router(data_pool_router)

# 注册定时任务管理API路由
router.include_router(scheduled_tasks_router)

# 注册市场数据API路由
router.include_router(market_data_router)

# 注册交易所管理API路由
router.include_router(exchanges_router)

# 注册系统管理API路由
router.include_router(system_router)

# 注册归档数据API路由
router.include_router(archive_router)

# 注册衍生数据API路由
router.include_router(deriv_router)

# 创建数据处理API路由子路由
router_data = APIRouter(prefix="/data", tags=["data-processing"])


@router_data.get("/status", response_model=ApiResponse)
def get_data_service_status():
    """获取数据服务状态API

    返回数据服务的当前状态信息

    Returns:
        ApiResponse: API响应，包含服务状态信息
    """
    try:
        logger.info("获取数据服务状态")

        # 返回服务状态
        return ApiResponse(
            code=0,
            message="数据服务运行正常",
            data={"status": "running", "services": ["data-download", "data-convert"]},
        )
    except Exception as e:
        logger.error(f"获取数据服务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册数据处理API路由
router.include_router(router_data)
