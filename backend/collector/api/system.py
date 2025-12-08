from fastapi import APIRouter
from loguru import logger

from ..schemas import ApiResponse
from ..schemas.system import SystemInfoResponse
from ..services import SystemService


# 创建API路由实例
router = APIRouter(prefix="/api/system", tags=["system-info"])


@router.get("/info", response_model=ApiResponse)
def get_system_info():
    """获取系统信息
    
    Returns:
        ApiResponse: 包含系统信息的响应
    """
    try:
        system_service = SystemService()
        result = system_service.get_system_info()
        
        if result["success"]:
            return ApiResponse(
                code=0,
                message=result["message"],
                data=result["system_info"]
            )
        else:
            return ApiResponse(
                code=1,
                message=result["message"],
                data=result["error"]
            )
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return ApiResponse(
            code=1,
            message="获取系统信息失败",
            data=str(e)
        )
