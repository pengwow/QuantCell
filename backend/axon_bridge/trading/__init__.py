"""axon_bridge.trading 适配层 — AI agent 工具集 / 风控限额 / 后端 mock。

⚠️ 本模块只做直传重导出,不在 Python 侧实现任何 trading 逻辑。
axon_quant 0.4.0 暴露:
- 工具:  PlaceOrderTool / CancelOrderTool / ReplaceOrderTool / QueryPortfolioTool
- 后端:  MockTradingBackend
- 配置:  RiskLimits
- 指标:  TradingMetrics
"""

from axon_quant.trading import (
    CancelOrderTool,
    MockTradingBackend,
    PlaceOrderTool,
    QueryPortfolioTool,
    ReplaceOrderTool,
    RiskLimits,
    TradingMetrics,
)

__all__ = [
    "CancelOrderTool",
    "MockTradingBackend",
    "PlaceOrderTool",
    "QueryPortfolioTool",
    "ReplaceOrderTool",
    "RiskLimits",
    "TradingMetrics",
]
