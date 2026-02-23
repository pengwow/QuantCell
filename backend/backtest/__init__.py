"""
回测模块

提供量化交易策略回测和分析功能。

主要功能:
    - 策略回测执行
    - 回测结果分析
    - 回测数据管理
    - 回测回放功能
    - 事件驱动引擎支持

使用示例:
    >>> from backtest import BacktestService, router
    >>> service = BacktestService()
    >>> result = service.run_backtest(strategy_config, backtest_config)

    >>> # 使用事件驱动引擎
    >>> from backtest import EventDrivenBacktestEngine
    >>> engine = EventDrivenBacktestEngine(config)

模块结构:
    - service.py: 回测服务实现
    - routes.py: API路由定义
    - schemas.py: 数据模型定义
    - engines/: 回测引擎实现
    - adapters/: 数据适配器
    - strategies/: 策略基类

作者: QuantCell Team
版本: 1.2.0
日期: 2026-02-12
"""

__version__ = "1.2.0"
__author__ = "QuantCell Team"

# 延迟导入，避免在--help时触发不必要的模块加载
def __getattr__(name):
    if name == "BacktestService":
        from .service import BacktestService
        return BacktestService
    if name == "router":
        from .routes import router
        return router
    if name == "EventDrivenBacktestEngine":
        from .engines.event_engine import EventDrivenBacktestEngine
        return EventDrivenBacktestEngine
    if name == "EventDrivenStrategy":
        from .strategies.event_strategy import EventDrivenStrategy
        return EventDrivenStrategy
    if name == "EventDrivenStrategyConfig":
        from .strategies.event_strategy import EventDrivenStrategyConfig
        return EventDrivenStrategyConfig
    if name == "kline_to_bars":
        from .adapters.data_adapter import kline_to_bars
        return kline_to_bars
    if name == "load_bars_from_csv":
        from .adapters.data_adapter import load_bars_from_csv
        return load_bars_from_csv
    if name == "load_bars_from_parquet":
        from .adapters.data_adapter import load_bars_from_parquet
        return load_bars_from_parquet
    # schemas 中的类
    if name in [
        "BacktestConfig", "StrategyConfig", "BacktestRunRequest",
        "BacktestRunResponse", "BacktestAnalyzeRequest", "BacktestAnalyzeResponse",
        "BacktestListRequest", "BacktestListResponse", "BacktestDeleteRequest",
        "BacktestStopRequest", "StrategyConfigRequest", "BacktestReplayRequest",
        "DataIntegrityCheckRequest", "DataIntegrityCheckResponse",
        "DataDownloadResponse", "TradeItem", "EquityPoint", "BacktestResult",
        "MultiBacktestResult", "ReplayData"
    ]:
        from . import schemas
        return getattr(schemas, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

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
    # 事件驱动组件（延迟加载）
    "EventDrivenBacktestEngine",
    "EventDrivenStrategy",
    "EventDrivenStrategyConfig",
    "kline_to_bars",
    "load_bars_from_csv",
    "load_bars_from_parquet",
]
