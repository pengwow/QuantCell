"""axon_quant.risk 适配层 — 风控引擎,QuantCell 业务代码唯一入口。

⚠️ 本模块只做直传重导出 + 工厂函数转发,不在 Python 侧实现任何风控逻辑。
axon_quant 0.4.0 暴露:
- 类:   DefaultRiskEngine / CircuitBreaker / RiskConfig / RiskMetrics
        RiskResult / RiskReason / RiskError
- 工厂: make_risk_config / make_circuit_breaker
        make_order / make_portfolio / make_portfolio_with_positions
- 类型: OrderDict / PortfolioDict / SideStr / TifStr / OrderTypeStr / RiskReasonKindStr
"""
from axon_quant.risk import (  # noqa: F401
    # 核心类
    CircuitBreaker,
    DefaultRiskEngine,
    RiskConfig,
    RiskError,
    RiskMetrics,
    RiskReason,
    RiskResult,
    # 工厂
    make_circuit_breaker,
    make_order,
    make_portfolio,
    make_portfolio_with_positions,
    make_risk_config,
    # 类型别名(给 IDE / type checker 用,运行时是字符串)
    OrderDict,
    OrderTypeStr,
    PortfolioDict,
    RiskReasonKindStr,
    SideStr,
    TifStr,
)

__all__ = [
    # 核心类
    "CircuitBreaker",
    "DefaultRiskEngine",
    "RiskConfig",
    "RiskError",
    "RiskMetrics",
    "RiskReason",
    "RiskResult",
    # 工厂
    "make_circuit_breaker",
    "make_order",
    "make_portfolio",
    "make_portfolio_with_positions",
    "make_risk_config",
    # 类型别名
    "OrderDict",
    "OrderTypeStr",
    "PortfolioDict",
    "RiskReasonKindStr",
    "SideStr",
    "TifStr",
]
