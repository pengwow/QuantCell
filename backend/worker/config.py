# -*- coding: utf-8 -*-
"""
Worker 配置模块

提供构建 TradingNode 配置的功能，包括：
- TradingNodeConfig 构建（支持多种交易所和账户类型）
- 数据引擎配置 (LiveDataEngineConfig)
- 风险引擎配置 (LiveRiskEngineConfig)
- 执行引擎配置 (LiveExecEngineConfig)
- 交易所特定配置（Binance、OKX）
- 配置验证

使用示例：
    from worker.config import build_trading_node_config

    # 构建 Binance 配置
    config, factories = build_trading_node_config(
        exchange="binance",
        account_type="spot",
        trading_mode="demo",
        api_key="your_api_key",
        api_secret="your_api_secret",
    )
"""

from __future__ import annotations

import os
from typing import Any, Dict, Literal, Optional, Tuple, Type

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.SYSTEM)

# 尝试导入 Nautilus 配置类
try:
    from nautilus_trader.config import (
        CacheConfig,
        LoggingConfig,
        TradingNodeConfig,
    )
    from nautilus_trader.live.config import (
        LiveDataEngineConfig,
        LiveExecEngineConfig,
        LiveRiskEngineConfig,
    )
    from nautilus_trader.common import Environment
    from nautilus_trader.model.identifiers import ClientId, TraderId

    # Binance 适配器
    from nautilus_trader.adapters.binance import (
        BINANCE,
        BinanceAccountType,
        BinanceDataClientConfig,
        BinanceExecClientConfig,
        BinanceInstrumentProviderConfig,
        BinanceLiveDataClientFactory,
        BinanceLiveExecClientFactory,
    )

    # OKX 适配器
    from nautilus_trader.adapters.okx import (
        OKX,
        OKXDataClientConfig,
        OKXExecClientConfig,
        OKXLiveDataClientFactory,
        OKXLiveExecClientFactory,
    )
    from nautilus_trader.core.nautilus_pyo3 import OKXInstrumentType

    NAUTILUS_AVAILABLE = True
except ImportError as e:
    NAUTILUS_AVAILABLE = False
    logger.warning(f"Nautilus Trader 未安装或导入失败: {e}，相关功能将不可用")
    TradingNodeConfig = None
    LiveDataEngineConfig = None
    LiveExecEngineConfig = None
    LiveRiskEngineConfig = None
    CacheConfig = None
    LoggingConfig = None
    Environment = None
    TraderId = None
    ClientId = None

# 类型定义
ExchangeConfig = Dict[str, Any]
ClientFactories = Tuple[Type, Type, str]


# =============================================================================
# 新的配置构建器 API（推荐）
# =============================================================================

def build_trading_node_config(
    exchange: Literal["binance", "okx"],
    account_type: Literal["spot", "usdt_futures", "coin_futures"] = "spot",
    trading_mode: Literal["live", "demo", "paper"] = "demo",
    trader_id: str = "WORKER-001",
    log_level: str = "INFO",
    proxy_url: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    api_passphrase: str | None = None,
    cache_config: Any | None = None,
    exec_engine_config: Any | None = None,
    data_engine_config: Any | None = None,
    log_directory: str | None = None,
    log_file_name: str | None = None,
) -> Tuple[TradingNodeConfig, ClientFactories]:
    """
    构建 TradingNodeConfig

    Parameters
    ----------
    exchange : Literal["binance", "okx"]
        交易所名称
    account_type : Literal["spot", "usdt_futures", "coin_futures"]
        账户类型，默认为 "spot"
    trading_mode : Literal["live", "demo", "paper"]
        交易模式：live=实盘, demo=模拟盘, paper=纸上交易
    trader_id : str
        交易者ID
    log_level : str
        日志级别
    proxy_url : str | None
        代理URL
    api_key : str | None
        API Key，如果为None则从环境变量读取
    api_secret : str | None
        API Secret，如果为None则从环境变量读取
    api_passphrase : str | None
        API Passphrase（仅OKX），如果为None则从环境变量读取
    cache_config : Any | None
        缓存配置
    exec_engine_config : Any | None
        执行引擎配置
    data_engine_config : Any | None
        数据引擎配置
    log_directory : str | None
        日志输出目录，默认为None（输出到控制台）
    log_file_name : str | None
        日志文件名，默认为None（使用默认名称）

    Returns
    -------
    Tuple[TradingNodeConfig, ClientFactories]
        TradingNodeConfig 和客户端工厂元组 (data_factory, exec_factory, venue)
    """
    if not NAUTILUS_AVAILABLE:
        raise RuntimeError("Nautilus Trader 未安装，无法构建配置")

    # 根据交易所和账户类型设置配置
    if exchange == "binance":
        data_clients, exec_clients, data_factory, exec_factory, venue = _setup_binance(
            account_type=account_type,
            trading_mode=trading_mode,
            proxy_url=proxy_url,
            api_key=api_key,
            api_secret=api_secret,
        )
    elif exchange == "okx":
        data_clients, exec_clients, data_factory, exec_factory, venue = _setup_okx(
            trading_mode=trading_mode,
            proxy_url=proxy_url,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        )
    else:
        raise ValueError(f"不支持的交易所: {exchange}")

    # 使用默认或自定义的执行引擎配置
    if exec_engine_config is None:
        exec_engine_config = LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=1440,
            purge_closed_orders_interval_mins=1,
            purge_closed_orders_buffer_mins=0,
            purge_closed_positions_interval_mins=1,
            purge_closed_positions_buffer_mins=0,
            purge_account_events_interval_mins=1,
            purge_account_events_lookback_mins=0,
            purge_from_database=True,
            graceful_shutdown_on_exception=True,
        )

    # 使用默认或自定义的数据引擎配置
    if data_engine_config is None:
        data_engine_config = LiveDataEngineConfig(
            external_clients=[ClientId(venue)],
        )

    # 使用默认或自定义的缓存配置
    if cache_config is None:
        cache_config = CacheConfig(
            timestamps_as_iso8601=True,
            flush_on_start=False,
        )

    # 配置日志
    logging_config = LoggingConfig(
        log_level=log_level,
        log_colors=True,
        use_pyo3=True,
    )

    # 如果指定了日志目录，配置文件日志
    if log_directory:
        logging_config.log_directory = log_directory
        logging_config.log_file_name = log_file_name or f"{trader_id}.log"
        logging_config.log_level_file = log_level

    # 创建 TradingNodeConfig
    config = TradingNodeConfig(
        trader_id=TraderId(trader_id),
        logging=logging_config,
        data_engine=data_engine_config,
        exec_engine=exec_engine_config,
        cache=cache_config,
        data_clients=data_clients,
        exec_clients=exec_clients,
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    return config, (data_factory, exec_factory, venue)


def _setup_binance(
    account_type: Literal["spot", "usdt_futures", "coin_futures"],
    trading_mode: Literal["live", "demo", "paper"],
    proxy_url: str | None,
    api_key: str | None,
    api_secret: str | None,
) -> Tuple[ExchangeConfig, ExchangeConfig, Type, Type, str]:
    """
    设置 Binance 交易所配置

    Parameters
    ----------
    account_type : Literal["spot", "usdt_futures", "coin_futures"]
        账户类型
    trading_mode : Literal["live", "demo", "paper"]
        交易模式
    proxy_url : str | None
        代理URL
    api_key : str | None
        API Key
    api_secret : str | None
        API Secret

    Returns
    -------
    Tuple[ExchangeConfig, ExchangeConfig, Type, Type, str]
        (data_clients, exec_clients, data_factory, exec_factory, venue)
    """
    # 确定是否使用测试网
    testnet = trading_mode == "demo"

    # 如果没有提供 API 密钥，从环境变量读取
    if api_key is None:
        api_key = os.environ.get("BINANCE_TESTNET_API_KEY") if testnet else os.environ.get("BINANCE_API_KEY")
    if api_secret is None:
        api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET") if testnet else os.environ.get("BINANCE_API_SECRET")

    # 映射账户类型字符串到枚举
    account_type_map = {
        "spot": BinanceAccountType.SPOT,
        "usdt_futures": BinanceAccountType.USDT_FUTURES,
        "coin_futures": BinanceAccountType.COIN_FUTURES,
    }
    binance_account_type = account_type_map.get(account_type, BinanceAccountType.SPOT)

    # 创建 Binance 专用的 instrument provider 配置
    instrument_provider_config = BinanceInstrumentProviderConfig(
        load_all=True,
    )

    # 构建数据客户端配置
    data_clients = {
        BINANCE: BinanceDataClientConfig(
            api_key=api_key,
            api_secret=api_secret,
            account_type=binance_account_type,
            testnet=testnet,
            proxy_url=proxy_url,
            instrument_provider=instrument_provider_config,
        ),
    }

    # 构建执行客户端配置
    exec_clients = {
        BINANCE: BinanceExecClientConfig(
            api_key=api_key,
            api_secret=api_secret,
            account_type=binance_account_type,
            testnet=testnet,
            proxy_url=proxy_url,
            instrument_provider=instrument_provider_config,
            max_retries=3,
        ),
    }

    return data_clients, exec_clients, BinanceLiveDataClientFactory, BinanceLiveExecClientFactory, BINANCE


def _setup_okx(
    trading_mode: Literal["live", "demo", "paper"],
    proxy_url: str | None,
    api_key: str | None,
    api_secret: str | None,
    api_passphrase: str | None,
) -> Tuple[ExchangeConfig, ExchangeConfig, Type, Type, str]:
    """
    设置 OKX 交易所配置

    Parameters
    ----------
    trading_mode : Literal["live", "demo", "paper"]
        交易模式
    proxy_url : str | None
        代理URL
    api_key : str | None
        API Key
    api_secret : str | None
        API Secret
    api_passphrase : str | None
        API Passphrase

    Returns
    -------
    Tuple[ExchangeConfig, ExchangeConfig, Type, Type, str]
        (data_clients, exec_clients, data_factory, exec_factory, venue)
    """
    # 确定是否使用模拟盘
    is_demo = trading_mode == "demo"

    # 如果没有提供 API 密钥，从环境变量读取
    if api_key is None:
        api_key = os.environ.get("OKX_API_KEY")
    if api_secret is None:
        api_secret = os.environ.get("OKX_API_SECRET")
    if api_passphrase is None:
        api_passphrase = os.environ.get("OKX_PASSPHRASE")

    # 构建数据客户端配置
    data_clients = {
        OKX: OKXDataClientConfig(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            instrument_types=(OKXInstrumentType.SPOT,),
            is_demo=is_demo,
            http_proxy_url=proxy_url,
        ),
    }

    # 构建执行客户端配置
    exec_clients = {
        OKX: OKXExecClientConfig(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            instrument_types=(OKXInstrumentType.SPOT,),
            is_demo=is_demo,
            http_proxy_url=proxy_url,
            max_retries=3,
        ),
    }

    return data_clients, exec_clients, OKXLiveDataClientFactory, OKXLiveExecClientFactory, OKX


def validate_config(
    exchange: str,
    trading_mode: str,
    api_key: str | None,
    api_secret: str | None,
    api_passphrase: str | None = None,
) -> Tuple[bool, str]:
    """
    验证配置是否有效

    Parameters
    ----------
    exchange : str
        交易所
    trading_mode : str
        交易模式
    api_key : str | None
        API Key
    api_secret : str | None
        API Secret
    api_passphrase : str | None
        API Passphrase（仅OKX）

    Returns
    -------
    Tuple[bool, str]
        (是否有效, 错误信息)
    """
    # 验证交易所
    if exchange not in ["binance", "okx"]:
        return False, f"不支持的交易所: {exchange}"

    # 验证交易模式
    if trading_mode not in ["live", "demo", "paper"]:
        return False, f"不支持的交易模式: {trading_mode}"

    # 验证 API 密钥
    if trading_mode != "paper":
        if not api_key:
            return False, "API Key 不能为空"
        if not api_secret:
            return False, "API Secret 不能为空"

        # OKX 需要 passphrase
        if exchange == "okx" and not api_passphrase:
            return False, "OKX 需要 API Passphrase"

    return True, ""


# =============================================================================
# 旧的配置构建器 API（向后兼容）
# =============================================================================

def build_trading_node_config_legacy(config: Dict[str, Any]) -> Any:
    """
    构建 TradingNodeConfig 配置（旧版API，向后兼容）

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
        >>> node_config = build_trading_node_config_legacy(config)
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
    # 新的配置构建器 API
    "build_trading_node_config",
    "validate_config",
    # 旧的配置构建器 API（向后兼容）
    "build_trading_node_config_legacy",
    "build_binance_config",
    "build_binance_live_config",
]
