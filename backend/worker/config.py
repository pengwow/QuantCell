# -*- coding: utf-8 -*-
"""
Worker 配置模块

提供构建 TradingNode 配置的功能，包括：
- TradingNodeConfig 构建
- 数据引擎配置 (LiveDataEngineConfig)
- 风险引擎配置 (LiveRiskEngineConfig)
- 执行引擎配置 (LiveExecEngineConfig)
- 交易所特定配置（如 Binance）

使用示例：
    from worker.config import build_trading_node_config, build_binance_config

    # 构建 Binance 配置
    binance_config = build_binance_config(
        api_key="your_api_key",
        api_secret="your_api_secret",
        testnet=True
    )

    # 构建 TradingNode 配置
    config = build_trading_node_config({
        "trader_id": "QUANTCELL-001",
        "data_clients": {"binance": binance_config},
        "exec_clients": {"binance": binance_config},
    })
"""

from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)

# 尝试导入 Nautilus 配置类
try:
    from nautilus_trader.config import TradingNodeConfig
    from nautilus_trader.live.config import (
        LiveDataEngineConfig,
        LiveExecEngineConfig,
        LiveRiskEngineConfig,
    )
    from nautilus_trader.common import Environment
    from nautilus_trader.model.identifiers import TraderId
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False
    logger.warning("Nautilus Trader 未安装，相关功能将不可用")
    TradingNodeConfig = None
    LiveDataEngineConfig = None
    LiveExecEngineConfig = None
    LiveRiskEngineConfig = None
    Environment = None
    TraderId = None


def build_trading_node_config(config: Dict[str, Any]) -> Any:
    """
    构建 TradingNodeConfig 配置

    根据 QuantCell 的配置字典构建 TradingNode 配置实例，
    包含数据引擎、风险引擎、执行引擎以及客户端配置。

    参数：
        config: QuantCell 配置字典，可包含以下字段：
            - trader_id: 交易者ID，格式为 "NAME-ID"，默认为 "QUANTCELL-001"
            - environment: 运行环境，可选 "LIVE" 或 "SANDBOX"，默认为 "SANDBOX"
            - data_engine: 数据引擎配置字典
            - risk_engine: 风险引擎配置字典
            - exec_engine: 执行引擎配置字典
            - data_clients: 数据客户端配置字典，键为客户端名称，值为配置字典
            - exec_clients: 执行客户端配置字典，键为客户端名称，值为配置字典

    返回：
        TradingNodeConfig: 交易节点配置实例，如果 Nautilus 未安装则返回配置字典

    示例：
        >>> config = {
        ...     "trader_id": "QUANTCELL-001",
        ...     "environment": "SANDBOX",
        ...     "data_clients": {"binance": {...}},
        ...     "exec_clients": {"binance": {...}},
        ... }
        >>> node_config = build_trading_node_config(config)
    """
    if not NAUTILUS_AVAILABLE:
        logger.warning("Nautilus Trader 未安装，返回原始配置字典")
        return config

    # 提取或设置默认值
    trader_id_str = config.get("trader_id", "QUANTCELL-001")
    environment_str = config.get("environment", "SANDBOX")

    # 创建 TraderId
    trader_id = TraderId(trader_id_str)

    # 解析环境
    environment = Environment.SANDBOX
    if environment_str.upper() == "LIVE":
        environment = Environment.LIVE
    elif environment_str.upper() == "SANDBOX":
        environment = Environment.SANDBOX
    else:
        logger.warning(f"未知的环境类型: {environment_str}，使用默认 SANDBOX")

    # 构建数据引擎配置
    data_engine_config = _build_data_engine_config(
        config.get("data_engine", {})
    )

    # 构建风险引擎配置
    risk_engine_config = _build_risk_engine_config(
        config.get("risk_engine", {})
    )

    # 构建执行引擎配置
    exec_engine_config = _build_exec_engine_config(
        config.get("exec_engine", {})
    )

    # 获取客户端配置
    data_clients = config.get("data_clients", {})
    exec_clients = config.get("exec_clients", {})

    logger.info(
        f"构建 TradingNode 配置: trader_id={trader_id}, environment={environment}"
    )

    return TradingNodeConfig(
        trader_id=trader_id,
        environment=environment,
        data_engine=data_engine_config,
        risk_engine=risk_engine_config,
        exec_engine=exec_engine_config,
        data_clients=data_clients,
        exec_clients=exec_clients,
    )


def _build_data_engine_config(config: Dict[str, Any]) -> Any:
    """
    构建数据引擎配置

    参数：
        config: 数据引擎配置字典

    返回：
        LiveDataEngineConfig: 实时数据引擎配置实例
    """
    if not NAUTILUS_AVAILABLE:
        return config
    return LiveDataEngineConfig(
        qsize=config.get("qsize", 100_000),
        graceful_shutdown_on_exception=config.get("graceful_shutdown_on_exception", False),
    )


def _build_risk_engine_config(config: Dict[str, Any]) -> Any:
    """
    构建风险引擎配置

    参数：
        config: 风险引擎配置字典

    返回：
        LiveRiskEngineConfig: 实时风险引擎配置实例
    """
    if not NAUTILUS_AVAILABLE:
        return config
    return LiveRiskEngineConfig(
        qsize=config.get("qsize", 100_000),
        graceful_shutdown_on_exception=config.get("graceful_shutdown_on_exception", False),
    )


def _build_exec_engine_config(config: Dict[str, Any]) -> Any:
    """
    构建执行引擎配置

    参数：
        config: 执行引擎配置字典

    返回：
        LiveExecEngineConfig: 实时执行引擎配置实例
    """
    if not NAUTILUS_AVAILABLE:
        return config
    return LiveExecEngineConfig(
        reconciliation=config.get("reconciliation", True),
        reconciliation_lookback_mins=config.get("reconciliation_lookback_mins", 1440),
    )


def build_binance_config(
    api_key: str,
    api_secret: str,
    testnet: bool = True,
    base_url_http: Optional[str] = None,
    base_url_ws: Optional[str] = None,
    use_usdt_margin: bool = True,
) -> Dict[str, Any]:
    """
    构建 Binance 交易所配置

    根据提供的 API 密钥和其他参数构建 Binance 特定的配置字典，
    支持现货、USDT 本位合约和币本位合约。

    参数：
        api_key: Binance API 密钥
        api_secret: Binance API 密钥
        testnet: 是否使用测试网，默认为 True
        base_url_http: 可选的 HTTP API 基础 URL
        base_url_ws: 可选的 WebSocket 基础 URL
        use_usdt_margin: 是否使用 USDT 本位合约，默认为 True

    返回：
        Dict[str, Any]: Binance 配置字典，可直接用于 data_clients 或 exec_clients

    示例：
        >>> binance_config = build_binance_config(
        ...     api_key="your_api_key",
        ...     api_secret="your_api_secret",
        ...     testnet=True,
        ...     use_usdt_margin=True,
        ... )
        >>> config = {
        ...     "data_clients": {"binance": binance_config},
        ...     "exec_clients": {"binance": binance_config},
        ... }
    """
    result_config: Dict[str, Any] = {
        "api_key": api_key,
        "api_secret": api_secret,
        "testnet": testnet,
    }

    # 设置基础 URL
    if base_url_http:
        result_config["base_url_http"] = base_url_http
    elif testnet:
        if use_usdt_margin:
            result_config["base_url_http"] = "https://testnet.binancefuture.com"
        else:
            result_config["base_url_http"] = "https://testnet.binance.vision"

    if base_url_ws:
        result_config["base_url_ws"] = base_url_ws
    elif testnet:
        if use_usdt_margin:
            result_config["base_url_ws"] = "wss://stream.binancefuture.com"
        else:
            result_config["base_url_ws"] = "wss://testnet.binance.vision"

    # 账户类型设置
    result_config["use_usdt_margin"] = use_usdt_margin

    logger.info(
        f"构建 Binance 配置: testnet={testnet}, usdt_margin={use_usdt_margin}"
    )

    return result_config


def build_binance_live_config(
    api_key: str,
    api_secret: str,
    use_usdt_margin: bool = True,
) -> Dict[str, Any]:
    """
    构建 Binance 生产环境配置

    这是 build_binance_config 的便捷包装，用于构建生产环境配置。

    参数：
        api_key: Binance API 密钥
        api_secret: Binance API 密钥
        use_usdt_margin: 是否使用 USDT 本位合约，默认为 True

    返回：
        Dict[str, Any]: Binance 生产环境配置字典

    示例：
        >>> binance_config = build_binance_live_config(
        ...     api_key="your_api_key",
        ...     api_secret="your_api_secret",
        ... )
    """
    result_config = build_binance_config(
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
        use_usdt_margin=use_usdt_margin,
    )

    # 生产环境使用默认的 Binance 官方 URL
    if use_usdt_margin:
        result_config["base_url_http"] = "https://fapi.binance.com"
        result_config["base_url_ws"] = "wss://fstream.binance.com"
    else:
        result_config["base_url_http"] = "https://api.binance.com"
        result_config["base_url_ws"] = "wss://stream.binance.com:9443"

    logger.info("构建 Binance 生产环境配置")

    return result_config


__all__ = [
    "build_trading_node_config",
    "build_binance_config",
    "build_binance_live_config",
]
