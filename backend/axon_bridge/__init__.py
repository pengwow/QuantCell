"""axon_quant 适配层(③ 桥) — 顶层重导出 + 业务适配函数

所有 QuantCell 业务代码统一 `from axon_bridge import X`。

依赖说明:
- axon_quant 通过 PyPI 安装(`pip install --upgrade axon-quant`)
- 永远跟随最新版本,不锁版本

包名说明:本目录命名为 axon_bridge 而非 axon_quant,避免与
site-packages 的 axon_quant 同名导致循环导入。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# —— 远程版本: credentials ——
# —— 远程版本: 核心类型重导出 ——
from axon_quant import (
    Action,
    ActionType,
    BacktestEngine,
    BacktestError,
    ComplianceError,
    DataError,
    DataRequest,
    DataService,
    DefiError,
    ExchangeConfig,
    ExchangeError,
    ExchangeId,
    Frequency,
    InferenceEngine,
    InferenceError,
    MockSource,
    Observation,
    OmsError,
    Order,
    OrderManager,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    RunResult,
    Side,
    agent,
    backtest,
    compliance,
    data,
    distributed,
    ensemble,
    exchange,
    explain,
    harness,
    hpo,
    inference,
    llm,
    oms,
    registry,
    risk,
    rl,
    tracker,
    walk_forward,
)
from axon_quant.agent import (
    MockTrader,
    RandomTrader,
    ReActAgent,
    RuleTrader,
    SwarmResult,
    SwarmRunner,
    TradingTools,
    TrajectoryRecorder,
)

# —— 合并自 8 个空壳子模块的重导出 ——
from axon_quant.ensemble import (
    ActionProbabilities,
    EnsembleError,
    EnsembleManager,
    EnsembleStrategy,
    HardVoteStrategy,
    MetaModel,
    ModelType,
    ModelWeight,
    SoftVoteStrategy,
    StackingEnsemble,
    WeightedVoteStrategy,
)
from axon_quant.exchange import (
    AxonError,
    BinanceAdapter,
    OkxAdapter,
    OrderLifecycleManager,
    RateLimitConfig,
    ReconnectConfig,
    TokenBucketRateLimiter,
    binance_testnet_config,
    okx_testnet_config,
)
from axon_quant.inference import (
    BatchConfig,
    BatchInferencePipeline,
    Device,
    InferenceBackend,
    InferenceStats,
    ModelConfig,
    ModelHotReloader,
    create_candle_engine,
    create_inference_engine,
    create_onnx_engine,
)
from axon_quant.llm import (
    AgentRole,
    LLMConfig,
    LLMMessage,
    MarketSignal,
    OllamaBackend,
    SignalType,
    make_backend,
)
from axon_quant.oms import (
    make_order_status,
    market_order,
)
from axon_quant.risk import (
    CircuitBreaker,
    DefaultRiskEngine,
    OrderDict,
    OrderTypeStr,
    PortfolioDict,
    RiskConfig,
    RiskError,
    RiskMetrics,
    RiskReason,
    RiskReasonKindStr,
    RiskResult,
    SideStr,
    TifStr,
    make_circuit_breaker,
    make_order,
    make_portfolio,
    make_portfolio_with_positions,
    make_risk_config,
)
from axon_quant.rl import (
    VERSION,
    TradingEnv,
)
from axon_quant.trading import (
    CancelOrderTool,
    MockTradingBackend,
    PlaceOrderTool,
    QueryPortfolioTool,
    ReplaceOrderTool,
    RiskLimits,
    TradingMetrics,
)

from ._credentials import credentials
from ._errors import AxonQuantError, map_error

# —— backtest 子模块重导出 ——
from .backtest import (
    PushFundingHelper,
    limit_order,
    spot_instrument,
    swap_instrument,
)
from .llm import (
    accumulate_stream,
    chat_to_dict,
    classify_llm_error,
    create_llm_backend,
    flatten_tools,
    normalize_chat_response,
    parse_tool_calls,
    to_axon_messages,
)


# —— core.events shim (上游 axon_quant 尚未暴露这些事件类) ——
class OrderAccepted:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


class OrderCanceled:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


class OrderRejected:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


class OrderFilled:
    """Shim — 等 axon_quant 真正提供时替换为重导出。"""


# ========== 延迟导入 axon_quant ==========
def _get_aq():
    """延迟导入 axon_quant 模块，避免启动时加载"""
    import axon_quant as aq

    return aq


# ========== 交易品种创建 (业务适配层) ==========
def create_spot_instrument(base: str, quote: str) -> dict[str, Any]:
    """创建现货交易品种"""
    aq = _get_aq()
    return aq.spot_instrument(base, quote)


def create_swap_instrument(
    base: str,
    quote: str,
    settle: str = "usd_margin",
    contract_size: float = 1.0,
) -> dict[str, Any]:
    """创建永续合约交易品种（完全对应 axon-quant 0.11+ 新签名）"""
    aq = _get_aq()
    return aq.swap_instrument(base, quote, settle=settle, contract_size=contract_size)


# ========== 订单创建 ==========
def create_market_order(
    symbol: str,
    side: str,
    quantity: float,
    order_id: int,
    instrument: dict[str, Any],
) -> dict[str, Any]:
    """创建市价订单字典"""
    return {
        "id": order_id,
        "order_id": str(order_id),
        "symbol": symbol,
        "side": side,
        "type": "market",
        "order_type": "Market",
        "quantity": float(quantity),
        "price": 0.0,
        "tif": "GTC",
        "status": "New",
        "idempotency_key": f"order_{order_id:08d}",
        "instrument": instrument,
    }


def create_limit_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    order_id: int,
    instrument: dict[str, Any],
    tif: str = "GTC",
) -> dict[str, Any]:
    """创建限价订单字典"""
    return {
        "id": order_id,
        "order_id": str(order_id),
        "symbol": symbol,
        "side": side,
        "type": "limit",
        "order_type": "Limit",
        "quantity": float(quantity),
        "price": float(price),
        "tif": tif,
        "status": "New",
        "idempotency_key": f"order_{order_id:08d}",
        "instrument": instrument,
    }


def create_cancel_order_event(
    order_id: int,
    instrument: dict[str, Any],
    timestamp_ns: int,
) -> dict[str, Any]:
    """创建取消订单事件字典"""
    return {
        "id": order_id,
        "type": "order_cancelled",
        "timestamp_ns": timestamp_ns,
        "order": {
            "id": order_id,
            "order_id": str(order_id),
            "instrument": instrument,
        },
    }


# ========== 事件构建 ==========
def build_order_submitted_event(
    order_dict: dict[str, Any],
    timestamp_ns: int,
) -> dict[str, Any]:
    """构建订单提交事件"""
    return {
        "id": order_dict["id"],
        "type": "order_submitted",
        "timestamp_ns": timestamp_ns,
        "order": order_dict,
    }


# ========== BacktestEngine 配置 ==========
class EngineConfig:
    """回测引擎配置"""

    def __init__(
        self,
        initial_cash: float = 100000.0,
        half_spread: float = 0.01,
        depth_levels: int = 5,
        size_per_level: float = 1.0,
        auto_rebalance_threshold: float = 0.01,
        funding_interval_ns: int = 8 * 3600 * 1_000_000_000,
        funding_rate: float = 0.0001,
        mark_aware: bool = True,
    ):
        self.initial_cash = initial_cash
        self.half_spread = half_spread
        self.depth_levels = depth_levels
        self.size_per_level = size_per_level
        self.auto_rebalance_threshold = auto_rebalance_threshold
        self.funding_interval_ns = funding_interval_ns
        self.funding_rate = funding_rate
        self.mark_aware = mark_aware


def create_backtest_engine(config: EngineConfig | None = None):
    """创建并配置回测引擎"""
    aq = _get_aq()
    cfg = config or EngineConfig()

    engine = aq.BacktestEngine(initial_cash=cfg.initial_cash)
    engine.with_seed_liquidity(
        half_spread=cfg.half_spread,
        depth_levels=cfg.depth_levels,
        size_per_level=cfg.size_per_level,
    )
    engine.with_auto_rebalance(threshold=cfg.auto_rebalance_threshold)

    return engine


def add_funding_schedule(
    engine,
    instrument: dict[str, Any],
    interval_ns: int,
    fixed_rate: float,
    mark_aware: bool = True,
):
    """为引擎添加资金费率调度"""
    engine.with_funding_schedule(
        instrument=instrument,
        interval_ns=interval_ns,
        fixed_rate=fixed_rate,
        mark_aware=mark_aware,
    )


# ========== 结果提取 ==========
def extract_run_result(result: Any) -> dict[str, Any]:
    """从 RunResult 提取回测结果"""
    if result is None:
        return {}

    try:
        return {
            "final_nav": float(result.final_nav) if hasattr(result, "final_nav") else 0.0,
            "nav_peak": float(result.nav_peak) if hasattr(result, "nav_peak") else 0.0,
            "total_pnl": float(result.total_pnl) if hasattr(result, "total_pnl") else 0.0,
            "total_fees": float(result.total_fees) if hasattr(result, "total_fees") else 0.0,
            "total_funding_pnl": float(result.total_funding_pnl) if hasattr(result, "total_funding_pnl") else 0.0,
            "trades": list(result.trades) if hasattr(result, "trades") and result.trades else [],
            "positions": list(result.positions) if hasattr(result, "positions") and result.positions else [],
            "equity_curve": list(result.equity_curve)
            if hasattr(result, "equity_curve") and result.equity_curve
            else [],
            "events_processed": int(result.events_processed) if hasattr(result, "events_processed") else 0,
            "fills": int(result.fills) if hasattr(result, "fills") else 0,
            "orders_accepted": int(result.orders_accepted) if hasattr(result, "orders_accepted") else 0,
            "orders_rejected": int(result.orders_rejected) if hasattr(result, "orders_rejected") else 0,
            "sharpe_ratio": float(result.sharpe_ratio) if hasattr(result, "sharpe_ratio") else 0.0,
            "max_drawdown_pct": float(result.max_drawdown_pct) if hasattr(result, "max_drawdown_pct") else 0.0,
            "win_rate": float(result.win_rate) if hasattr(result, "win_rate") else 0.0,
            "duration_secs": float(result.duration_secs) if hasattr(result, "duration_secs") else 0.0,
        }
    except Exception as e:
        logger.error(f"提取回测结果失败: {e}")
        return {}


def extract_run_stats(stats: Any) -> dict[str, Any]:
    """从 RunStats 提取统计信息"""
    if stats is None:
        return {}

    try:
        return {
            "events_processed": int(stats.events_processed) if hasattr(stats, "events_processed") else 0,
            "fills": int(stats.fills) if hasattr(stats, "fills") else 0,
            "orders_accepted": int(stats.orders_accepted) if hasattr(stats, "orders_accepted") else 0,
            "orders_rejected": int(stats.orders_rejected) if hasattr(stats, "orders_rejected") else 0,
            "orders_cancelled": int(stats.orders_cancelled) if hasattr(stats, "orders_cancelled") else 0,
            "orders_modified": int(stats.orders_modified) if hasattr(stats, "orders_modified") else 0,
            "pnl_peak": float(stats.pnl_peak) if hasattr(stats, "pnl_peak") else 0.0,
            "total_pnl": float(stats.total_pnl) if hasattr(stats, "total_pnl") else 0.0,
        }
    except Exception as e:
        logger.error(f"提取运行统计失败: {e}")
        return {}


# ========== 辅助函数 ==========
def to_ns_timestamp(ts: Any) -> int:
    """将时间戳转换为纳秒"""
    if isinstance(ts, (int, float)):
        if ts > 1e18:
            return int(ts)
        elif ts > 1e15:
            return int(ts * 1000)
        elif ts > 1e12:
            return int(ts * 1_000_000)
        elif ts > 1e9:
            return int(ts * 1_000_000_000)
        else:
            return int(ts * 1_000_000_000)
    elif hasattr(ts, "timestamp"):
        return int(ts.timestamp() * 1_000_000_000)
    elif isinstance(ts, str):
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(ts)
            return int(dt.timestamp() * 1_000_000_000)
        except ValueError, TypeError:
            return 0
    return 0


def get_current_ns_timestamp() -> int:
    """获取当前时间的纳秒时间戳"""
    return int(time.time() * 1_000_000_000)


def get_instrument_id(instrument: dict[str, Any]) -> str:
    """从品种字典获取标识符"""
    if isinstance(instrument, dict):
        base = instrument.get("base", "")
        quote = instrument.get("quote", "")
        if base and quote:
            return f"{base}{quote}"
        return str(instrument)
    return str(instrument)


# ========== 导出列表 ==========
__all__ = [
    "VERSION",
    "Action",
    "ActionProbabilities",
    "ActionType",
    "AgentRole",
    "AxonError",
    "AxonQuantError",
    "BacktestEngine",
    "BacktestError",
    "BatchConfig",
    "BatchInferencePipeline",
    "BinanceAdapter",
    "CancelOrderTool",
    "CircuitBreaker",
    "ComplianceError",
    "DataError",
    "DataRequest",
    "DataService",
    "DefaultRiskEngine",
    "DefiError",
    "Device",
    "EngineConfig",
    "EnsembleError",
    "EnsembleManager",
    "EnsembleStrategy",
    "ExchangeConfig",
    "ExchangeError",
    "ExchangeId",
    "Frequency",
    "HardVoteStrategy",
    "InferenceBackend",
    "InferenceEngine",
    "InferenceError",
    "InferenceStats",
    "LLMConfig",
    "LLMMessage",
    "MarketSignal",
    "MetaModel",
    "MockSource",
    "MockTrader",
    "MockTradingBackend",
    "ModelConfig",
    "ModelHotReloader",
    "ModelType",
    "ModelWeight",
    "Observation",
    "OkxAdapter",
    "OllamaBackend",
    "OmsError",
    "Order",
    "OrderAccepted",
    "OrderCanceled",
    "OrderDict",
    "OrderFilled",
    "OrderLifecycleManager",
    "OrderManager",
    "OrderRejected",
    "OrderStatus",
    "OrderType",
    "OrderTypeStr",
    "PlaceOrderTool",
    "Portfolio",
    "PortfolioDict",
    "Position",
    "PushFundingHelper",
    "QueryPortfolioTool",
    "RandomTrader",
    "RateLimitConfig",
    "ReActAgent",
    "ReconnectConfig",
    "ReplaceOrderTool",
    "RiskConfig",
    "RiskError",
    "RiskLimits",
    "RiskMetrics",
    "RiskReason",
    "RiskReasonKindStr",
    "RiskResult",
    "RuleTrader",
    "RunResult",
    "Side",
    "SideStr",
    "SignalType",
    "SoftVoteStrategy",
    "StackingEnsemble",
    "SwarmResult",
    "SwarmRunner",
    "TifStr",
    "TokenBucketRateLimiter",
    "TradingEnv",
    "TradingMetrics",
    "TradingTools",
    "TrajectoryRecorder",
    "WeightedVoteStrategy",
    "accumulate_stream",
    "add_funding_schedule",
    "binance_testnet_config",
    "build_order_submitted_event",
    "chat_to_dict",
    "classify_llm_error",
    "create_backtest_engine",
    "create_cancel_order_event",
    "create_candle_engine",
    "create_inference_engine",
    "create_limit_order",
    "create_llm_backend",
    "create_market_order",
    "create_onnx_engine",
    "create_spot_instrument",
    "create_swap_instrument",
    "credentials",
    "extract_run_result",
    "extract_run_stats",
    "flatten_tools",
    "get_current_ns_timestamp",
    "get_instrument_id",
    "limit_order",
    "make_backend",
    "make_circuit_breaker",
    "make_order",
    "make_order_status",
    "make_portfolio",
    "make_portfolio_with_positions",
    "make_risk_config",
    "map_error",
    "market_order",
    "normalize_chat_response",
    "okx_testnet_config",
    "parse_tool_calls",
    "spot_instrument",
    "swap_instrument",
    "to_axon_messages",
    "to_ns_timestamp",
]
