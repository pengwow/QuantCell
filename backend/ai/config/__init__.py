"""AI 模型配置管理子模块。

提供 AI 大模型厂商配置（api_key / api_host / 模型列表 / 代理）的 CRUD，
以及默认模型配置的读取工具。
"""

from .config_utils import (
    get_all_providers,
    get_default_provider_and_models,
    get_provider_by_id,
    parse_ai_model_configs,
)
from .routes import router

__all__ = [
    "get_all_providers",
    "get_default_provider_and_models",
    "get_provider_by_id",
    "parse_ai_model_configs",
    "router",
]
