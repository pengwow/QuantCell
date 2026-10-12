"""策略生成子模块。

包含策略代码生成（同步 + SSE 流式）、思维链管理、Prompt 模板管理、
策略生成历史、代码校验、模板库、性能监控。
"""

from .performance_monitor import PerformanceMonitor
from .prompts import PromptCategory, PromptManager
from .routes_strategy import router
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
from .thinking_chain import ThinkingChainManager

__all__ = [
    "CodeValidationRequest",
    "CodeValidationResponse",
    "PerformanceMonitor",
    "PerformanceStatsResponse",
    "PromptCategory",
    "PromptManager",
    "StrategyGenerateFromTemplateRequest",
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
    "ThinkingChainManager",
    "router",
]
