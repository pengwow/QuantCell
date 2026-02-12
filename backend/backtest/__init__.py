"""
回测模块

提供量化交易策略回测和分析功能。

主要功能:
    - 策略回测执行
    - 回测结果分析
    - 回测数据管理
    - 回测回放功能

使用示例:
    >>> from backtest import BacktestService, router
    >>> service = BacktestService()
    >>> result = service.run_backtest(strategy_config, backtest_config)

模块结构:
    - service.py: 回测服务实现
    - routes.py: API路由定义
    - schemas.py: 数据模型定义

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

__version__ = "1.0.0"
__author__ = "QuantCell Team"

from .service import BacktestService
from .routes import router
from .schemas import (
    BacktestConfig,
    StrategyConfig,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestAnalyzeRequest,
    BacktestAnalyzeResponse,
    BacktestListRequest,
    BacktestListResponse,
    BacktestDeleteRequest,
    BacktestStopRequest,
    StrategyConfigRequest,
    BacktestReplayRequest,
    DataIntegrityCheckRequest,
    DataIntegrityCheckResponse,
    DataDownloadResponse,
    TradeItem,
    EquityPoint,
    BacktestResult,
    MultiBacktestResult,
    ReplayData,
)

__all__ = [
    "BacktestService",
    "router",
    "BacktestConfig",
    "StrategyConfig",
    "BacktestRunRequest",
    "BacktestRunResponse",
    "BacktestAnalyzeRequest",
    "BacktestAnalyzeResponse",
    "BacktestListRequest",
    "BacktestListResponse",
    "BacktestDeleteRequest",
    "BacktestStopRequest",
    "StrategyConfigRequest",
    "BacktestReplayRequest",
    "DataIntegrityCheckRequest",
    "DataIntegrityCheckResponse",
    "DataDownloadResponse",
    "TradeItem",
    "EquityPoint",
    "BacktestResult",
    "MultiBacktestResult",
    "ReplayData",
]
