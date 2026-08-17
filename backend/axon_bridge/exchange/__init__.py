"""axon_bridge.exchange 适配层 — 交易所适配器 / OMS / 限流。

⚠️ 本模块只做直传重导出,不在 Python 侧实现任何 exchange 逻辑。
axon_quant 0.4.0 暴露:
- 适配器:    BinanceAdapter / OkxAdapter
- 配置:      ExchangeConfig / ExchangeId / RateLimitConfig / ReconnectConfig
- 限流:      TokenBucketRateLimiter
- OMS:       OrderLifecycleManager
- 错误:      AxonError / ExchangeError
- 工厂:      binance_testnet_config / okx_testnet_config
"""
from axon_quant.exchange import (  # noqa: F401
    # 适配器
    BinanceAdapter,
    OkxAdapter,
    # 配置
    ExchangeConfig,
    ExchangeId,
    RateLimitConfig,
    ReconnectConfig,
    # 限流
    TokenBucketRateLimiter,
    # OMS
    OrderLifecycleManager,
    # 错误
    AxonError,
    ExchangeError,
    # 工厂
    binance_testnet_config,
    okx_testnet_config,
)

__all__ = [
    "BinanceAdapter",
    "OkxAdapter",
    "ExchangeConfig",
    "ExchangeId",
    "RateLimitConfig",
    "ReconnectConfig",
    "TokenBucketRateLimiter",
    "OrderLifecycleManager",
    "AxonError",
    "ExchangeError",
    "binance_testnet_config",
    "okx_testnet_config",
]
