# 数据处理API路由定义

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

# 导入配置管理API路由
from .api.data import router as data_router
from .api.data_pool import router as data_pool_router
from .api.scheduled_tasks import router as scheduled_tasks_router
from .db.models import Task
from .schemas import ApiResponse, DataConvertRequest, DataDownloadRequest
from .scripts.convert_to_qlib import convert_crypto_to_qlib
from .scripts.get_data import GetData

# 创建API路由实例
router = APIRouter()

# 注册数据加载API路由
router.include_router(data_router)

# 注册资产池管理API路由
router.include_router(data_pool_router)

# 注册定时任务管理API路由
router.include_router(scheduled_tasks_router)

# 创建数据处理API路由子路由
router_data = APIRouter(prefix="/api/data", tags=["data-processing"])





@router_data.post(
    "/convert/qlib", 
    response_model=ApiResponse,
    summary="将CSV数据转换为QLib格式",
    description="将指定目录下的CSV数据转换为QLib格式，支持多种参数配置，包括频率、字段映射等",
    responses={
        200: {"description": "数据转换成功", "model": ApiResponse},
        500: {"description": "数据转换失败"}
    }
)
def convert_data_to_qlib(request: DataConvertRequest):
    """将CSV数据转换为QLib格式API
    
    将指定目录下的CSV数据转换为QLib格式，支持多种参数配置
    
    Args:
        request: 数据转换请求参数，包含CSV目录、QLib目录、频率等信息
        
    Returns:
        ApiResponse: API响应，包含转换状态和结果信息
        
    Raises:
        HTTPException: 当转换过程中发生错误时抛出
    """
    try:
        logger.info(f"开始处理数据转换请求: {request.model_dump()}")
        
        # 调用转换函数
        result = convert_crypto_to_qlib(
            csv_dir=request.csv_dir,
            qlib_dir=request.qlib_dir,
            freq=request.freq,
            date_field_name=request.date_field_name,
            file_suffix=request.file_suffix,
            symbol_field_name=request.symbol_field_name,
            include_fields=request.include_fields,
            max_workers=request.max_workers,
            limit_nums=request.limit_nums
        )
        
        if result:
            logger.info("数据转换请求处理完成")
            return ApiResponse(
                code=0,
                message="数据转换为QLib格式成功",
                data={
                    "csv_dir": request.csv_dir,
                    "qlib_dir": request.qlib_dir,
                    "freq": request.freq
                }
            )
        else:
            logger.error("数据转换失败")
            return ApiResponse(
                code=1,
                message="数据转换为QLib格式失败",
                data={
                    "csv_dir": request.csv_dir,
                    "qlib_dir": request.qlib_dir,
                    "freq": request.freq
                }
            )
    except Exception as e:
        logger.error(f"数据转换过程中发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            data={
                "status": "running",
                "services": [
                    "data-download",
                    "data-convert"
                ]
            }
        )
    except Exception as e:
        logger.error(f"获取数据服务状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 注册数据处理API路由
router.include_router(router_data)
