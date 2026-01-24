# 系统设置API路由

import os
import sys
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

# 导入配置管理相关模块
from settings.models import SystemConfigBusiness as SystemConfig
from settings.services import SystemService

# 导入详细的Schema模型
from settings.schemas import (
    ApiResponse,
    ConfigBatchUpdateRequest,
    ConfigUpdateRequest,
    SystemConfigItem,
    SystemConfigSimple,
    SystemInfo
)

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from config_manager import load_system_configs

# 创建API路由实例
router = APIRouter()

# 创建配置管理API路由子路由
config_router = APIRouter(prefix="/api/config", tags=["config-management"])

# 创建系统信息API路由子路由
system_router = APIRouter(prefix="/api/system", tags=["system-info"])


@config_router.get("/", response_model=ApiResponse)
def get_all_configs():
    """获取所有系统配置
    
    Returns:
        ApiResponse[Dict[str, str]]: 包含所有配置的响应，值为敏感配置时返回"******"
        
    Responses:
        200: 成功获取所有配置
        500: 获取配置失败
    """
    try:
        logger.info("开始获取所有系统配置")
        
        # 获取所有配置的详细信息，包括插件配置
        configs = SystemConfig.get_all_with_details()
        
        # 构建简单的键值对映射，用于前端使用
        simple_configs = {}
        for key, config in configs.items():
            # 如果是敏感配置，返回"******"
            if config.get("is_sensitive", False):
                simple_configs[key] = "******"
            else:
                simple_configs[key] = config["value"]
        
        logger.info(f"成功获取所有系统配置，共 {len(simple_configs)} 项")
        
        return ApiResponse(
            code=0,
            message="获取所有配置成功",
            data=simple_configs
        )
    except Exception as e:
        logger.error(f"获取所有配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.get("/{key}", response_model=ApiResponse)
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
            # 如果是敏感配置，返回"******"
            if config.get("is_sensitive", False):
                config["value"] = "******"
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


@config_router.post("/", response_model=ApiResponse)
def update_config(request: Request, config: Dict[str, Any]):
    """更新或创建系统配置
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
        config: 配置字典，包含key、value和可选的description、plugin、name、is_sensitive
    
    Returns:
        ApiResponse: 包含更新结果的响应
    """
    try:
        # 验证请求数据
        if "key" not in config or "value" not in config:
            raise HTTPException(status_code=400, detail="请求数据必须包含key和value字段")
        
        key = config["key"]
        value = config["value"]
        description = config.get("description", "")
        plugin = config.get("plugin", None)
        name = config.get("name", None)
        is_sensitive = config.get("is_sensitive", False)
        
        logger.info(f"开始更新配置: key={key}, value={value}, plugin={plugin}, name={name}, is_sensitive={is_sensitive}")
        
        # 更新配置
        success = SystemConfig.set(key, value, description, plugin, name, is_sensitive)
        
        if success:
            logger.info(f"成功更新配置: key={key}")
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info("系统配置上下文已刷新")
            
            # 如果是敏感配置，返回"******"
            response_value = "******" if is_sensitive else value
            
            return ApiResponse(
                code=0,
                message="更新配置成功",
                data={
                    "key": key,
                    "value": response_value,
                    "description": description,
                    "plugin": plugin,
                    "name": name,
                    "is_sensitive": is_sensitive
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


@config_router.delete("/{key}", response_model=ApiResponse)
def delete_config(request: Request, key: str):
    """删除指定键的系统配置
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
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
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info("系统配置上下文已刷新")
            
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


@config_router.post("/batch", response_model=ApiResponse)
def update_configs_batch(request: Request, configs: List[Dict[str, Any]]|Dict[str, Any]):
    """批量更新系统配置

    Args:
        request: FastAPI请求对象，用于访问应用实例
        configs: 配置字典，键为配置名，值为配置值，或者配置列表

    Returns:
        ApiResponse: 包含更新结果的响应
    """
    try:
        logger.info("开始批量更新系统配置")
        if isinstance(configs, dict):
            # 遍历配置，逐个更新
            updated_count = 0
            for key, value in configs.items():
                # 跳过非配置项（如__v_id等Vue内部属性）
                if not key.startswith("__v"):
                    logger.info(f"更新配置: key={key}, value={value}")
                    SystemConfig.set(key, value)
                    updated_count += 1
            logger.info(f"批量更新的配置数量: {updated_count}")
        if isinstance(configs, list):
            # 遍历配置，逐个更新
            updated_count = 0
            for config in configs:
                key = config["key"]
                value = config["value"]
                description = config.get("description", "")
                plugin = config.get("plugin", None)
                name = config.get("name", None)
                is_sensitive = config.get("is_sensitive", False)
                logger.info(f"更新配置: key={key}, value={value}, plugin={plugin}, name={name}, is_sensitive={is_sensitive}")
                SystemConfig.set(key, value, description, plugin, name, is_sensitive)
                updated_count += 1
            logger.info(f"批量更新的配置数量: {updated_count}")
        
        # 刷新应用上下文配置
        request.app.state.configs = load_system_configs()
        logger.info("系统配置上下文已刷新")
        
        return ApiResponse(
            code=0,
            message="批量更新配置成功",
            data={"updated_count": len(configs) if isinstance(configs, list) else len(configs) - sum(1 for key in configs if key.startswith("__v"))}
        )
    except Exception as e:
        logger.error(f"批量更新配置失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.get("/plugin/{plugin_name}", response_model=ApiResponse)
def get_plugin_config(plugin_name: str):
    """获取指定插件的所有配置

    Args:
        plugin_name: 插件名称

    Returns:
        ApiResponse: 包含插件配置的响应
    """
    try:
        logger.info(f"开始获取插件配置: {plugin_name}")
        
        # 获取所有配置的详细信息
        all_configs = SystemConfig.get_all_with_details()
        
        # 过滤出与指定插件相关的配置
        plugin_configs = {}
        for key, config in all_configs.items():
            if config.get("plugin") == plugin_name:
                # 如果是敏感配置，返回"******"
                if config.get("is_sensitive", False):
                    plugin_configs[key] = "******"
                else:
                    plugin_configs[key] = config["value"]
        
        logger.info(f"成功获取插件配置，共 {len(plugin_configs)} 项")
        
        return ApiResponse(
            code=0,
            message="获取插件配置成功",
            data=plugin_configs
        )
    except Exception as e:
        logger.error(f"获取插件配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@system_router.get("/info", response_model=ApiResponse)
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

# 注册子路由
router.include_router(config_router)
router.include_router(system_router)