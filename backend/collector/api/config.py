# 配置管理API路由

import os
# 导入系统配置加载函数
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from ..db import SystemConfigBusiness as SystemConfig
from ..schemas import ApiResponse

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from config_manager import load_system_configs

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
        
        # 结构化处理，将system字符串转换为对象
        # if "system" in configs:
        #     try:
        #         import json
        #         import re
                
        #         # 处理system字段
        #         system_str = configs["system"]
                
        #         # 自定义解析器，处理非标准格式的配置字符串
        #         def parse_system_config(config_str):
        #             # 移除首尾的大括号
        #             config_str = config_str.strip().strip('{}')
                    
        #             # 分割配置项
        #             config_items = []
        #             current_item = ''
        #             inside_quotes = False
        #             quote_char = ''
                    
        #             for char in config_str:
        #                 if char in ['"', "'"] and (not current_item or current_item[-1] != '\\'):
        #                     if inside_quotes and char == quote_char:
        #                         inside_quotes = False
        #                         quote_char = ''
        #                     elif not inside_quotes:
        #                         inside_quotes = True
        #                         quote_char = char
        #                 current_item += char
        #                 if char == ',' and not inside_quotes:
        #                     config_items.append(current_item.strip().rstrip(',').strip())
        #                     current_item = ''
                    
        #             if current_item.strip():
        #                 config_items.append(current_item.strip())
                    
        #             # 解析每个配置项
        #             result = {}
        #             for item in config_items:
        #                 if ':' in item:
        #                     # 分割键值对
        #                     key_part, value_part = item.split(':', 1)
        #                     key = key_part.strip().strip('"').strip("'")
        #                     value = value_part.strip()
                            
        #                     # 处理值
        #                     if value.startswith('"') and value.endswith('"'):
        #                         value = value.strip('"')
        #                     elif value.startswith("'") and value.endswith("'"):
        #                         value = value.strip("'")
        #                     elif value.isdigit():
        #                         value = int(value)
        #                     elif value.lower() in ['true', 'false']:
        #                         value = value.lower() == 'true'
        #                     # 否则保留为字符串
                            
        #                     result[key] = value
                    
        #             return result
                
                # 解析system配置
                # system_dict = parse_system_config(system_str)
                # configs["system"] = system_dict
            #     logger.info("成功转换system配置为结构化对象")
            # except Exception as e:
            #     logger.warning(f"转换system配置失败: {e}")
            #     logger.warning(f"原始system配置: {configs['system']}")
            #     # 删除无效的system字段，使用默认值
            #     del configs["system"]
        # 
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
def update_config(request: Request, config: Dict[str, Any]):
    """更新或创建系统配置
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
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
        description = config.get("description", "")
        
        logger.info(f"开始更新配置: key={key}, value={value}")
        
        # 更新配置
        success = SystemConfig.set(key, value, description)
        
        if success:
            logger.info(f"成功更新配置: key={key}")
            # 刷新应用上下文配置
            request.app.state.configs = load_system_configs()
            logger.info("系统配置上下文已刷新")
            
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


@router.post("/batch", response_model=ApiResponse)
def update_configs_batch(request: Request, configs: Dict[str, Any]):
    """批量更新系统配置
    
    Args:
        request: FastAPI请求对象，用于访问应用实例
        configs: 配置字典，键为配置名，值为配置值
        
    Returns:
        ApiResponse: 包含更新结果的响应
    """
    try:
        logger.info("开始批量更新系统配置")
        logger.info(f"批量更新的配置数量: {len(configs)}")
        
        # 遍历配置，逐个更新
        for key, value in configs.items():
            # 跳过非配置项（如__v_id等Vue内部属性）
            if not key.startswith("__v"):
                logger.info(f"更新配置: key={key}, value={value}")
                SystemConfig.set(key, value)
        
        # 刷新应用上下文配置
        request.app.state.configs = load_system_configs()
        logger.info("系统配置上下文已刷新")
        
        return ApiResponse(
            code=0,
            message="批量更新配置成功",
            data={"updated_count": len(configs)}
        )
    except Exception as e:
        logger.error(f"批量更新配置失败: error={e}")
        raise HTTPException(status_code=500, detail=str(e))
