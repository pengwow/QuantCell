"""
AI模型配置工具模块

提供获取默认提供商和模型配置的公共方法，被多个路由模块共享使用。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-08
"""

import json
from typing import Any, Dict, List, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# AI模型配置名称常量
AI_MODELS_CONFIG_NAME = "ai_models"


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
        from settings.models import SystemConfigBusiness as SystemConfig

        all_configs = SystemConfig.get_all_with_details()

        if not all_configs:
            logger.warning("系统配置为空")
            return None

        default_provider_id = None
        providers_config = None

        # 查找默认提供商ID和providers配置
        for key, config in all_configs.items():
            if not isinstance(config, dict):
                continue
            if config.get("name") == AI_MODELS_CONFIG_NAME:
                if key == "default_provider":
                    default_provider_id = config.get("value", "")
                elif key == "providers":
                    try:
                        providers_config = json.loads(config.get("value", "[]"))
                    except json.JSONDecodeError:
                        logger.warning("解析providers配置失败")

        if not default_provider_id or not providers_config:
            logger.warning("未找到默认提供商配置或providers配置")
            return None

        # 查找默认提供商的配置
        default_provider = None
        for provider in providers_config:
            if isinstance(provider, dict) and provider.get("id") == default_provider_id:
                default_provider = provider
                break

        if not default_provider:
            logger.warning(f"未找到默认提供商: {default_provider_id}")
            return None

        # 获取启用的模型列表
        models = default_provider.get("models", [])
        logger.info(f"从配置读取的models: {models}")
        enabled_models = [
            {
                "id": model.get("id"),
                "name": model.get("name"),
            }
            for model in models
            if isinstance(model, dict) and model.get("is_enabled", False)
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
        return None
