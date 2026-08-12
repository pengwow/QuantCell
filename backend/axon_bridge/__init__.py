"""axon_quant 适配层(③ 桥) — 顶层重导出,避免散落 import 路径。

所有 QuantCell 业务代码统一 `from backend.axon_bridge import X`。

依赖说明:
- axon_quant 通过 PyPI 安装(`pip install --upgrade axon-quant`)
- 永远跟随最新版本,不锁版本
- /Users/liupeng/workspace/quant/axon 源码仓库仅作参考文档,
  绝不 sys.path.insert 加载

包名说明:本目录命名为 axon_bridge 而非 axon_quant,避免与
site-packages 的 axon_quant 同名导致循环导入。
"""
from ._credentials import credentials  # noqa: F401

# 核心数据类(直接重导出,零转译)
# 这些是 axon_quant 顶层实际暴露的类
from axon_quant import (  # noqa: F401
    # 核心动作 / 观测
    Action, ActionType, Observation, RunResult,
    # data
    DataService, MockSource, Frequency, DataRequest, DataError,
    # backtest
    BacktestEngine, BacktestError,
    # oms
    OrderManager, Order, OrderStatus, OrderType, Side, Portfolio, Position, OmsError,
    # exchange(顶层部分,其他在子模块)
    ExchangeConfig, ExchangeId, ExchangeError,
    # inference(顶层部分)
    InferenceEngine, InferenceError,
    # errors
    ComplianceError, DefiError,
)

# risk 顶层类(axon_quant risk 子模块)
from axon_quant.risk import (  # noqa: F401
    DefaultRiskEngine, CircuitBreaker, RiskConfig, RiskError,
    RiskResult, RiskReason, RiskMetrics,
    make_risk_config, make_circuit_breaker,
    make_order, make_portfolio, make_portfolio_with_positions,
)

# 子模块保留路径(供 deep use)
# 注意:axon_quant 不暴露 monitor 子模块(从子模块 import 失败)
from axon_quant import (  # noqa: F401
    rl, llm, hpo, registry, ensemble, walk_forward,
    tracker, compliance, explain, distributed, harness,
    risk, exchange, data, backtest, oms, inference,
)

# —— axon_quant LLM/Agent 类型重导出 (0.10.0+) ——
# ReAct Agent + 信号 + 轨迹
from axon_quant.llm import (  # noqa: F401
    LLMConfig, LLMMessage, make_backend,
    OllamaBackend,
    ReActAgent, TradingTools, TrajectoryRecorder,
    MarketSignal, SignalType, AgentRole,
)
# 交易工具(PlaceOrder/Cancel/Query/Replace)在 trading 子模块
from axon_quant.trading import (  # noqa: F401
    PlaceOrderTool, CancelOrderTool, QueryPortfolioTool, ReplaceOrderTool,
    MockTradingBackend,
)

# —— axon_quant 0.6.0 多 leg API 重导出 ——
# Instrument 工厂 + PushFundingHelper
from .backtest import (  # noqa: F401
    spot_instrument,
    swap_instrument,
    limit_order,
    PushFundingHelper,
)
