# 配置管理API路由

from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any
from loguru import logger

from ..schemas import ApiResponse
from ..db import SystemConfig

# 创建API路由实例
router = APIRouter(prefix="/api/config", tags=["config-management"])


class ConfigUpdateRequest:
    """配置更新请求模型
    
    Attributes:
        value: 配置值
        description: 配置描述，可选
    """
    def __init__(self, value: str, description: Optional[str] = None):
        self.value = value
        self.description = description


@router.get("/", response_model=ApiResponse)
def get_all_configs():
    """获取所有系统配置
    
    Returns:
        ApiResponse: 包含所有配置的响应
    """
    try:
        logger.info("开始获取所有系统配置")
        
        # 获取所有配置
        configs = SystemConfig.get_all()
        
        logger.info(f"成功获取所有系统配置，共 {len(configs)} 项")
        
        return ApiResponse(
            code=0,
            message="获取所有配置成功",
            data=configs
        )
    except Exception as e:
        logger.error(f"获取所有配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key}", response_model=ApiResponse)
def get_config(key: str):
    """获取指定键的系统配置
    
    Args:
        key: 配置键名
        
    Returns:
        ApiResponse: 包含指定配置的响应
    """
    try:
        logger.info(f"开始获取配置: {key}")
        
        # 获取配置
        config = SystemConfig.get_with_details(key)
        
        if config:
            logger.info(f"成功获取配置: {key}")
            return ApiResponse(
                code=0,
                message="获取配置成功",
                data=config
            )
        else:
            logger.warning(f"配置不存在: {key}")
            return ApiResponse(
                code=1,
                message="配置不存在",
                data={"key": key}
            )
    except Exception as e:
        logger.error(f"获取配置失败: key={key}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=ApiResponse)
def update_config(config: Dict[str, Any]):
    """更新或创建系统配置
    
    Args:
        config: 配置字典，包含key、value和可选的description
        
    Returns:
        ApiResponse: 包含更新结果的响应
    """
    try:
        # 验证请求数据
        if "key" not in config or "value" not in config:
            raise HTTPException(status_code=400, detail="请求数据必须包含key和value字段")
        
        key = config["key"]
        value = config["value"]
        description = config.get("description")
        
        logger.info(f"开始更新配置: key={key}, value={value}")
        
        # 更新配置
        success = SystemConfig.set(key, value, description)
        
        if success:
            logger.info(f"成功更新配置: key={key}")
            return ApiResponse(
                code=0,
                message="更新配置成功",
                data={
                    "key": key,
                    "value": value,
                    "description": description
                }
            )
        else:
            logger.error(f"更新配置失败: key={key}")
            raise HTTPException(status_code=500, detail="更新配置失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新配置失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{key}", response_model=ApiResponse)
def delete_config(key: str):
    """删除指定键的系统配置
    
    Args:
        key: 配置键名
        
    Returns:
        ApiResponse: 包含删除结果的响应
    """
    try:
        logger.info(f"开始删除配置: {key}")
        
        # 删除配置
        success = SystemConfig.delete(key)
        
        if success:
            logger.info(f"成功删除配置: {key}")
            return ApiResponse(
                code=0,
                message="删除配置成功",
                data={"key": key}
            )
        else:
            logger.error(f"删除配置失败: {key}")
            raise HTTPException(status_code=500, detail="删除配置失败")
    except Exception as e:
        logger.error(f"删除配置失败: key={key}, error={e}")
        raise HTTPException(status_code=500, detail=str(e))
