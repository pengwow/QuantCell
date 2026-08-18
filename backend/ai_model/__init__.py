# AI模型配置模块
# 用于管理AI大模型厂商配置信息

from .prompts import PromptCategory, PromptManager
from .routes import router
from .schemas_strategy import (
    CodeValidationRequest,
    CodeValidationResponse,
    PerformanceStatsResponse,
    StrategyGenerateFromTemplateRequest,
    StrategyGenerateRequest,
    StrategyGenerateResponse,
    StrategyGenerateStreamResponse,
    StrategyHistoryCreate,
    StrategyHistoryResponse,
    StrategyHistoryUpdate,
    StrategyTemplateResponse,
    StrategyValidateRequest,
    StrategyValidateResponse,
)
from .strategy_generator import StrategyGenerator

__all__ = [
    "CodeValidationRequest",
    "CodeValidationResponse",
    "PerformanceStatsResponse",
    "PromptCategory",
    "PromptManager",
    "StrategyGenerateFromTemplateRequest",
    # Schemas
    "StrategyGenerateRequest",
    "StrategyGenerateResponse",
    "StrategyGenerateStreamResponse",
    "StrategyGenerator",
    "StrategyHistoryCreate",
    "StrategyHistoryResponse",
    "StrategyHistoryUpdate",
    "StrategyTemplateResponse",
    "StrategyValidateRequest",
    "StrategyValidateResponse",
    "router",
]
