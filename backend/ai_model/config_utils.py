"""
AI模型配置工具模块

提供获取默认提供商和模型配置的公共方法，被多个路由模块共享使用。

作者: QuantCell Team
版本: 1.1.0
日期: 2026-03-14
"""

import json
from typing import Any, Dict, List, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# AI模型配置名称常量
AI_MODELS_CONFIG_NAME = "ai_model"


def parse_ai_model_configs(all_configs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析新的 ai_model 配置格式
    
    将扁平化的配置键值对解析为结构化的提供商列表
    
    Args:
        all_configs: 所有系统配置的字典
        
    Returns:
        List[Dict[str, Any]]: 提供商配置列表
    """
    providers = {}
    
    # 导入常量
    AI_MODELS_CONFIG_NAME = "ai_model"
    
    for key, config in all_configs.items():
        if not isinstance(config, dict):
            continue
            
        # 检查是否是 ai_model 相关的配置
        if key.startswith("ai_model."):
            # 解析键名: ai_model.{provider_id}.{field}
            parts = key.split(".")
            if len(parts) >= 3:
                provider_id = parts[1]
                field = ".".join(parts[2:])  # 支持带点的字段名
                
                if provider_id not in providers:
                    providers[provider_id] = {"id": provider_id}
                
                # 获取配置值
                value = config.get("value")
                
                # 特殊字段的解析
                if field == "models" and value:
                    try:
                        providers[provider_id][field] = json.loads(value)
                    except json.JSONDecodeError:
                        logger.warning(f"解析 {key} 的 models 失败")
                        providers[provider_id][field] = []
                elif field in ["is_default", "proxy_enabled"]:
                    # 布尔字段 - 支持 "1"/"0" 和 "true"/"false"
                    parsed_value = value in ("true", "1", True)
                    providers[provider_id][field] = parsed_value
                    logger.debug(f"解析 {key}: value={value}, parsed={parsed_value}")
                elif field == "is_enabled":
                    # is_enabled 现在是字符串，存储启用的模型ID
                    providers[provider_id][field] = value if value else None
                    logger.debug(f"解析 {key}: value={value}")
                else:
                    providers[provider_id][field] = value
    
    # 添加调试日志
    for provider_id, provider in providers.items():
        logger.info(f"解析提供商 {provider_id}: is_default={provider.get('is_default')}, is_enabled={provider.get('is_enabled')}")
    
    return list(providers.values())


def get_default_provider_and_models() -> Optional[Dict[str, Any]]:
    """获取默认提供商及其启用的模型

    从系统配置中读取默认提供商的配置信息，包括提供商详情和启用的模型列表。
    这是一个公共方法，被 routes_strategy 和 routes 模块使用。

    Returns:
        Optional[Dict[str, Any]]: 包含以下字段的字典:
            - provider (Dict): 提供商信息，包含 id, name, provider, api_key, api_host
            - enabled_models (List[Dict]): 启用的模型列表，每个模型包含 id, name
        如果未配置或配置无效则返回None

    示例:
        >>> result = get_default_provider_and_models()
        >>> if result:
        ...     print(f"提供商: {result['provider']['name']}")
        ...     print(f"启用模型数: {len(result['enabled_models'])}")
    """
    try:
        # 延迟导入以避免循环导入问题
        from settings.models import SystemConfigBusiness as SystemConfig

        all_configs = SystemConfig.get_all_with_details()

        if not all_configs:
            logger.warning("系统配置为空")
            return None

        # 解析新的配置格式
        providers = parse_ai_model_configs(all_configs)
        
        if not providers:
            logger.warning("未找到任何 AI 模型提供商配置")
            return None
        
        # 查找默认提供商
        default_provider = None
        for provider in providers:
            if provider.get("is_default", False):
                default_provider = provider
                break
        
        # 如果没有默认提供商，使用第一个启用的提供商（is_enabled 不为空）
        if not default_provider:
            for provider in providers:
                if provider.get("is_enabled"):  # is_enabled 现在是字符串（模型ID）
                    default_provider = provider
                    break
        
        # 如果还是没有，使用第一个提供商
        if not default_provider:
            default_provider = providers[0]

        if not default_provider:
            logger.warning("未找到可用的 AI 模型提供商")
            return None
        
        # 检查提供商是否启用（is_enabled 不为空）
        enabled_model_id = default_provider.get("is_enabled")
        if not enabled_model_id:
            logger.warning(f"默认提供商 {default_provider.get('id')} 未启用")
            return None

        # 获取启用的模型列表（根据 is_enabled 字段值匹配模型ID）
        models = default_provider.get("models", [])
        logger.info(f"从配置读取的models: {models}")
        logger.info(f"启用的模型ID: {enabled_model_id}")
        enabled_models = [
            {
                "id": model.get("id"),
                "name": model.get("name"),
                "model_name": model.get("model_name"),  # 用于API调用的实际模型名称
            }
            for model in models
            if isinstance(model, dict) and model.get("id") == enabled_model_id
        ]
        logger.info(f"处理后的enabled_models: {enabled_models}")

        return {
            "provider": {
                "id": default_provider.get("id"),
                "name": default_provider.get("name"),
                "provider": default_provider.get("provider"),
                "api_key": default_provider.get("api_key", ""),
                "api_host": default_provider.get("api_host", ""),
            },
            "enabled_models": enabled_models,
        }
    except Exception as e:
        logger.error(f"获取默认提供商和模型失败: {e}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return None


def get_all_providers() -> List[Dict[str, Any]]:
    """获取所有 AI 模型提供商配置
    
    Returns:
        List[Dict[str, Any]]: 所有提供商配置列表
    """
    try:
        from settings.models import SystemConfigBusiness as SystemConfig

        all_configs = SystemConfig.get_all_with_details()

        if not all_configs:
            return []

        return parse_ai_model_configs(all_configs)
    except Exception as e:
        logger.error(f"获取所有提供商失败: {e}")
        return []


def get_provider_by_id(provider_id: str) -> Optional[Dict[str, Any]]:
    """根据 ID 获取提供商配置
    
    Args:
        provider_id: 提供商 ID
        
    Returns:
        Optional[Dict[str, Any]]: 提供商配置，未找到则返回 None
    """
    providers = get_all_providers()
    for provider in providers:
        if provider.get("id") == provider_id:
            return provider
    return None
