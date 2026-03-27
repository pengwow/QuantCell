# -*- coding: utf-8 -*-
"""
Binance 实盘交易适配器模块

提供 Binance 交易所与 NautilusTrader 框架之间的适配功能，包括：
- BinanceAdapterConfig: 统一的配置管理类
- BinanceDataClientFactory: 数据客户端工厂
- BinanceExecClientFactory: 执行客户端工厂
- 配置构建函数: 构建 Nautilus Binance 配置
- 辅助函数: 账户类型解析、环境解析、凭证验证

支持多账户配置，支持现货和合约交易，支持测试网和生产网。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-27
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.API)


# =============================================================================
# 枚举定义
# =============================================================================

class BinanceAccountType(str, Enum):
    """
    Binance 账户类型枚举

    定义了 Binance 支持的不同账户类型，包括现货、杠杆、合约等。
    """
    SPOT = "SPOT"
    MARGIN = "MARGIN"
    USDT_FUTURE = "USDT_FUTURE"
    COIN_FUTURE = "COIN_FUTURE"
    PORTFOLIO_MARGIN = "PORTFOLIO_MARGIN"


class BinanceEnvironment(str, Enum):
    """
    Binance 环境类型枚举

    定义了 Binance 支持的不同环境，包括测试网和生产网。
    """
    LIVE = "LIVE"
    TESTNET = "TESTNET"


# =============================================================================
# 异常定义
# =============================================================================

class BinanceAdapterError(Exception):
    """Binance 适配器异常基类"""
    pass


class BinanceConfigError(BinanceAdapterError):
    """配置错误异常"""
    pass


class BinanceCredentialError(BinanceAdapterError):
    """凭证验证错误异常"""
    pass


class BinanceClientError(BinanceAdapterError):
    """客户端创建错误异常"""
    pass


# =============================================================================
# BinanceAdapterConfig 配置类
# =============================================================================

@dataclass
class BinanceAdapterConfig:
    """
    Binance 适配器配置类

    统一管理 Binance 交易所连接所需的所有配置参数，
    支持多账户配置和不同交易模式。

    Attributes
    ----------
    api_key : str
        Binance API Key
    api_secret : str
        Binance API Secret
    account_type : BinanceAccountType
        账户类型（现货、杠杆、合约等）
    environment : BinanceEnvironment
        交易环境（测试网或生产网）
    is_us : bool
        是否使用 Binance US（美国版）
    base_url : Optional[str]
        可选的自定义基础 URL
    proxy_url : Optional[str]
        可选的代理 URL
    testnet : bool
        是否使用测试网（与 environment 保持一致）
    use_ssl : bool
        是否使用 SSL 连接
    timeout : int
        请求超时时间（秒）
    recv_window : int
        请求接收窗口（毫秒）
    max_retries : int
        最大重试次数
    retry_delay : float
        重试延迟（秒）
    rate_limit : bool
        是否启用速率限制
    extra_params : Dict[str, Any]
        额外参数

    Examples
    --------
    >>> config = BinanceAdapterConfig(
    ...     api_key="your_api_key",
    ...     api_secret="your_api_secret",
    ...     account_type=BinanceAccountType.SPOT,
    ...     environment=BinanceEnvironment.TESTNET,
    ... )
    """

    api_key: str = ""
    api_secret: str = ""
    account_type: BinanceAccountType = BinanceAccountType.SPOT
    environment: BinanceEnvironment = BinanceEnvironment.TESTNET
    is_us: bool = False
    base_url: Optional[str] = None
    proxy_url: Optional[str] = None
    testnet: bool = True
    use_ssl: bool = True
    timeout: int = 30
    recv_window: int = 5000
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit: bool = True
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """初始化后处理，确保 testnet 与 environment 一致"""
        if self.environment == BinanceEnvironment.TESTNET:
            self.testnet = True
        else:
            self.testnet = False

    @property
    def is_spot(self) -> bool:
        """是否为现货账户"""
        return self.account_type == BinanceAccountType.SPOT

    @property
    def is_margin(self) -> bool:
        """是否为杠杆账户"""
        return self.account_type == BinanceAccountType.MARGIN

    @property
    def is_futures(self) -> bool:
        """是否为合约账户（USDT 或币本位）"""
        return self.account_type in (
            BinanceAccountType.USDT_FUTURE,
            BinanceAccountType.COIN_FUTURE,
        )

    @property
    def is_usdt_futures(self) -> bool:
        """是否为 USDT 合约账户"""
        return self.account_type == BinanceAccountType.USDT_FUTURE

    @property
    def is_coin_futures(self) -> bool:
        """是否为币本位合约账户"""
        return self.account_type == BinanceAccountType.COIN_FUTURE

    @property
    def is_live(self) -> bool:
        """是否为生产环境"""
        return self.environment == BinanceEnvironment.LIVE

    @property
    def is_testnet(self) -> bool:
        """是否为测试网环境"""
        return self.environment == BinanceEnvironment.TESTNET

    def to_dict(self) -> Dict[str, Any]:
        """
        将配置转换为字典

        Returns
        -------
        Dict[str, Any]
            配置字典
        """
        return {
            "api_key": self.api_key[:8] + "***" if self.api_key else "",
            "api_secret": "***" if self.api_secret else "",
            "account_type": self.account_type.value,
            "environment": self.environment.value,
            "is_us": self.is_us,
            "base_url": self.base_url,
            "proxy_url": self.proxy_url,
            "testnet": self.testnet,
            "use_ssl": self.use_ssl,
            "timeout": self.timeout,
            "recv_window": self.recv_window,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "rate_limit": self.rate_limit,
            "extra_params": self.extra_params,
        }

    def validate(self) -> bool:
        """
        验证配置是否有效

        Returns
        -------
        bool
            配置是否有效

        Raises
        ------
        BinanceConfigError
            配置无效时抛出异常
        """
        if not self.api_key:
            raise BinanceConfigError("API Key 不能为空")

        if not self.api_secret:
            raise BinanceConfigError("API Secret 不能为空")

        if self.timeout <= 0:
            raise BinanceConfigError("超时时间必须大于 0")

        if self.recv_window <= 0:
            raise BinanceConfigError("接收窗口必须大于 0")

        return True


# =============================================================================
# BinanceDataClientFactory 数据客户端工厂
# =============================================================================

class BinanceDataClientFactory:
    """
    Binance 数据客户端工厂类

    负责创建和管理 Binance 数据客户端，支持现货和合约市场，
    支持测试网和生产网环境。

    Attributes
    ----------
    config : BinanceAdapterConfig
        适配器配置
    client : Optional[Any]
        数据客户端实例

    Examples
    --------
    >>> config = BinanceAdapterConfig(
    ...     api_key="your_api_key",
    ...     api_secret="your_api_secret",
    ...     account_type=BinanceAccountType.SPOT,
    ... )
    >>> factory = BinanceDataClientFactory(config)
    >>> client = factory.create_data_client()
    """

    def __init__(self, config: BinanceAdapterConfig):
        """
        初始化数据客户端工厂

        Parameters
        ----------
        config : BinanceAdapterConfig
            Binance 适配器配置
        """
        self.config = config
        self._client: Optional[Any] = None
        self._instrument_provider: Optional[Any] = None

        logger.info(
            f"Binance 数据客户端工厂已初始化: "
            f"账户类型={config.account_type.value}, "
            f"环境={config.environment.value}"
        )

    @property
    def client(self) -> Optional[Any]:
        """获取当前数据客户端实例"""
        return self._client

    def create_data_client(
        self,
        instrument_ids: Optional[List[str]] = None,
        use_agg_trade: bool = True,
    ) -> Any:
        """
        创建 Binance 数据客户端

        根据配置创建合适的数据客户端，支持现货和合约市场。

        Parameters
        ----------
        instrument_ids : Optional[List[str]]
            交易品种 ID 列表，如 ["BTCUSDT", "ETHUSDT"]
        use_agg_trade : bool
            是否使用聚合交易数据

        Returns
        -------
        Any
            Nautilus Binance 数据客户端实例

        Raises
        ------
        BinanceClientError
            创建客户端失败时抛出异常

        Examples
        --------
        >>> factory = BinanceDataClientFactory(config)
        >>> client = factory.create_data_client(
        ...     instrument_ids=["BTCUSDT", "ETHUSDT"],
        ...     use_agg_trade=True,
        ... )
        """
        try:
            config.validate()
        except BinanceConfigError as e:
            raise BinanceClientError(f"配置验证失败: {e}") from e

        try:
            # 延迟导入 Nautilus Binance 适配器
            # 避免在模块加载时就导入，提高启动速度
            from nautilus_trader.adapters.binance.factories import (
                BinanceLiveDataClientFactory,
            )
            from nautilus_trader.adapters.binance.config import (
                BinanceDataClientConfig,
            )
            from nautilus_trader.adapters.binance.common.enums import (
                BinanceAccountType as NautilusAccountType,
            )

            # 构建 Nautilus 数据客户端配置
            data_config = build_binance_data_config(
                config=self.config,
                instrument_ids=instrument_ids,
                use_agg_trade=use_agg_trade,
            )

            # 创建数据客户端
            # 注意：实际创建需要在 Nautilus Trader 环境中执行
            # 这里返回配置对象，由调用方在适当时机创建客户端
            self._client = data_config

            logger.info(
                f"Binance 数据客户端配置已创建: "
                f"账户类型={config.account_type.value}, "
                f"品种数量={len(instrument_ids) if instrument_ids else 0}"
            )

            return self._client

        except ImportError as e:
            logger.error(f"Nautilus Binance 适配器导入失败: {e}")
            raise BinanceClientError(
                "无法导入 Nautilus Binance 适配器，请确保已安装 nautilus_trader[binance]"
            ) from e

        except Exception as e:
            logger.error(f"创建 Binance 数据客户端失败: {e}")
            raise BinanceClientError(f"创建数据客户端失败: {e}") from e

    def create_instrument_provider(self) -> Any:
        """
        创建交易品种信息提供者

        Returns
        -------
        Any
            交易品种信息提供者配置

        Raises
        ------
        BinanceClientError
            创建失败时抛出异常
        """
        try:
            from nautilus_trader.adapters.binance.config import (
                BinanceInstrumentProviderConfig,
            )

            # 构建交易品种提供者配置
            provider_config = BinanceInstrumentProviderConfig(
                account_type=self.config.account_type.value,
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                api_secret=self.config.api_secret,
                use_testnet=self.config.testnet,
            )

            self._instrument_provider = provider_config

            logger.info("Binance 交易品种提供者配置已创建")

            return self._instrument_provider

        except ImportError as e:
            logger.error(f"Nautilus Binance 适配器导入失败: {e}")
            raise BinanceClientError(
                "无法导入 Nautilus Binance 适配器"
            ) from e

        except Exception as e:
            logger.error(f"创建交易品种提供者失败: {e}")
            raise BinanceClientError(f"创建交易品种提供者失败: {e}") from e

    def get_ws_url(self) -> str:
        """
        获取 WebSocket URL

        Returns
        -------
        str
            WebSocket 连接 URL
        """
        if self.config.is_us:
            # Binance US
            if self.config.is_futures:
                return (
                    "wss://stream.binance.us:9443/ws"
                    if self.config.is_live
                    else "wss://testnet.binance.vision/ws"
                )
            else:
                return (
                    "wss://stream.binance.us:9443/ws"
                    if self.config.is_live
                    else "wss://testnet.binance.vision/ws"
                )
        else:
            # Binance Global
            if self.config.is_futures:
                if self.config.is_usdt_futures:
                    return (
                        "wss://fstream.binance.com/ws"
                        if self.config.is_live
                        else "wss://stream.binancefuture.com/ws"
                    )
                else:  # COIN_FUTURE
                    return (
                        "wss://dstream.binance.com/ws"
                        if self.config.is_live
                        else "wss://dstream.binancefuture.com/ws"
                    )
            else:
                return (
                    "wss://stream.binance.com:9443/ws"
                    if self.config.is_live
                    else "wss://testnet.binance.vision/ws"
                )

    def get_rest_url(self) -> str:
        """
        获取 REST API URL

        Returns
        -------
        str
            REST API 基础 URL
        """
        if self.config.base_url:
            return self.config.base_url

        if self.config.is_us:
            # Binance US
            if self.config.is_futures:
                return (
                    "https://api.binance.us"
                    if self.config.is_live
                    else "https://testnet.binance.vision"
                )
            else:
                return (
                    "https://api.binance.us"
                    if self.config.is_live
                    else "https://testnet.binance.vision"
                )
        else:
            # Binance Global
            if self.config.is_futures:
                if self.config.is_usdt_futures:
                    return (
                        "https://fapi.binance.com"
                        if self.config.is_live
                        else "https://testnet.binancefuture.com"
                    )
                else:  # COIN_FUTURE
                    return (
                        "https://dapi.binance.com"
                        if self.config.is_live
                        else "https://testnet.binancefuture.com"
                    )
            else:
                return (
                    "https://api.binance.com"
                    if self.config.is_live
                    else "https://testnet.binance.vision"
                )


# =============================================================================
# BinanceExecClientFactory 执行客户端工厂
# =============================================================================

class BinanceExecClientFactory:
    """
    Binance 执行客户端工厂类

    负责创建和管理 Binance 执行客户端，支持现货和合约交易，
    支持测试网和生产网环境。

    Attributes
    ----------
    config : BinanceAdapterConfig
        适配器配置
    client : Optional[Any]
        执行客户端实例

    Examples
    --------
    >>> config = BinanceAdapterConfig(
    ...     api_key="your_api_key",
    ...     api_secret="your_api_secret",
    ...     account_type=BinanceAccountType.SPOT,
    ... )
    >>> factory = BinanceExecClientFactory(config)
    >>> client = factory.create_exec_client()
    """

    def __init__(self, config: BinanceAdapterConfig):
        """
        初始化执行客户端工厂

        Parameters
        ----------
        config : BinanceAdapterConfig
            Binance 适配器配置
        """
        self.config = config
        self._client: Optional[Any] = None
        self._order_manager: Optional[Any] = None

        logger.info(
            f"Binance 执行客户端工厂已初始化: "
            f"账户类型={config.account_type.value}, "
            f"环境={config.environment.value}"
        )

    @property
    def client(self) -> Optional[Any]:
        """获取当前执行客户端实例"""
        return self._client

    def create_exec_client(
        self,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> Any:
        """
        创建 Binance 执行客户端

        根据配置创建合适的执行客户端，支持现货和合约交易。

        Parameters
        ----------
        max_retries : Optional[int]
            最大重试次数，默认使用配置中的值
        retry_delay : Optional[float]
            重试延迟（秒），默认使用配置中的值

        Returns
        -------
        Any
            Nautilus Binance 执行客户端配置

        Raises
        ------
        BinanceClientError
            创建客户端失败时抛出异常

        Examples
        --------
        >>> factory = BinanceExecClientFactory(config)
        >>> client = factory.create_exec_client(
        ...     max_retries=5,
        ...     retry_delay=2.0,
        ... )
        """
        try:
            self.config.validate()
        except BinanceConfigError as e:
            raise BinanceClientError(f"配置验证失败: {e}") from e

        try:
            # 延迟导入 Nautilus Binance 适配器
            from nautilus_trader.adapters.binance.factories import (
                BinanceLiveExecClientFactory,
            )
            from nautilus_trader.adapters.binance.config import (
                BinanceExecClientConfig,
            )

            # 构建 Nautilus 执行客户端配置
            exec_config = build_binance_exec_config(
                config=self.config,
                max_retries=max_retries,
                retry_delay=retry_delay,
            )

            # 存储配置对象
            self._client = exec_config

            logger.info(
                f"Binance 执行客户端配置已创建: "
                f"账户类型={self.config.account_type.value}"
            )

            return self._client

        except ImportError as e:
            logger.error(f"Nautilus Binance 适配器导入失败: {e}")
            raise BinanceClientError(
                "无法导入 Nautilus Binance 适配器，请确保已安装 nautilus_trader[binance]"
            ) from e

        except Exception as e:
            logger.error(f"创建 Binance 执行客户端失败: {e}")
            raise BinanceClientError(f"创建执行客户端失败: {e}") from e

    def create_order_manager(
        self,
        use_position_ids: bool = True,
    ) -> Any:
        """
        创建订单管理器

        Parameters
        ----------
        use_position_ids : bool
            是否使用持仓 ID

        Returns
        -------
        Any
            订单管理器配置字典

        Raises
        ------
        BinanceClientError
            创建失败时抛出异常
        """
        try:
            order_manager_config = {
                "use_position_ids": use_position_ids,
                "account_type": self.config.account_type.value,
                "testnet": self.config.testnet,
                "max_retries": self.config.max_retries,
                "retry_delay": self.config.retry_delay,
            }

            self._order_manager = order_manager_config

            logger.info("Binance 订单管理器配置已创建")

            return self._order_manager

        except Exception as e:
            logger.error(f"创建订单管理器失败: {e}")
            raise BinanceClientError(f"创建订单管理器失败: {e}") from e


# =============================================================================
# 配置构建函数
# =============================================================================

def build_binance_data_config(
    config: BinanceAdapterConfig,
    instrument_ids: Optional[List[str]] = None,
    use_agg_trade: bool = True,
    handle_revised_bars: bool = True,
) -> Any:
    """
    构建 BinanceDataClientConfig

    根据 BinanceAdapterConfig 构建 Nautilus 数据客户端配置。

    Parameters
    ----------
    config : BinanceAdapterConfig
        Binance 适配器配置
    instrument_ids : Optional[List[str]]
        交易品种 ID 列表
    use_agg_trade : bool
        是否使用聚合交易数据
    handle_revised_bars : bool
        是否处理修订后的 K 线数据

    Returns
    -------
    Any
        Nautilus BinanceDataClientConfig 实例

    Raises
    ------
    BinanceConfigError
        构建配置失败时抛出异常

    Examples
    --------
    >>> config = BinanceAdapterConfig(
    ...     api_key="your_api_key",
    ...     api_secret="your_api_secret",
    ...     account_type=BinanceAccountType.SPOT,
    ... )
    >>> data_config = build_binance_data_config(
    ...     config=config,
    ...     instrument_ids=["BTCUSDT", "ETHUSDT"],
    ... )
    """
    try:
        from nautilus_trader.adapters.binance.config import (
            BinanceDataClientConfig,
        )
        from nautilus_trader.adapters.binance.common.enums import (
            BinanceAccountType as NautilusAccountType,
        )

        # 映射账户类型
        account_type_map = {
            BinanceAccountType.SPOT: NautilusAccountType.SPOT,
            BinanceAccountType.MARGIN: NautilusAccountType.MARGIN,
            BinanceAccountType.USDT_FUTURE: NautilusAccountType.USDT_FUTURE,
            BinanceAccountType.COIN_FUTURE: NautilusAccountType.COIN_FUTURE,
        }

        nautilus_account_type = account_type_map.get(
            config.account_type,
            NautilusAccountType.SPOT,
        )

        # 构建配置
        data_config = BinanceDataClientConfig(
            account_type=nautilus_account_type,
            api_key=config.api_key,
            api_secret=config.api_secret,
            base_url=config.base_url,
            testnet=config.testnet,
            use_agg_trade=use_agg_trade,
            handle_revised_bars=handle_revised_bars,
        )

        logger.debug(
            f"BinanceDataClientConfig 构建成功: "
            f"账户类型={nautilus_account_type.value}"
        )

        return data_config

    except ImportError as e:
        logger.error(f"Nautilus Binance 配置导入失败: {e}")
        raise BinanceConfigError(
            "无法导入 Nautilus Binance 配置模块"
        ) from e

    except Exception as e:
        logger.error(f"构建 BinanceDataClientConfig 失败: {e}")
        raise BinanceConfigError(f"构建数据客户端配置失败: {e}") from e


def build_binance_exec_config(
    config: BinanceAdapterConfig,
    max_retries: Optional[int] = None,
    retry_delay: Optional[float] = None,
    use_position_ids: bool = True,
) -> Any:
    """
    构建 BinanceExecClientConfig

    根据 BinanceAdapterConfig 构建 Nautilus 执行客户端配置。

    Parameters
    ----------
    config : BinanceAdapterConfig
        Binance 适配器配置
    max_retries : Optional[int]
        最大重试次数
    retry_delay : Optional[float]
        重试延迟（秒）
    use_position_ids : bool
        是否使用持仓 ID

    Returns
    -------
    Any
        Nautilus BinanceExecClientConfig 实例

    Raises
    ------
    BinanceConfigError
        构建配置失败时抛出异常

    Examples
    --------
    >>> config = BinanceAdapterConfig(
    ...     api_key="your_api_key",
    ...     api_secret="your_api_secret",
    ...     account_type=BinanceAccountType.SPOT,
    ... )
    >>> exec_config = build_binance_exec_config(
    ...     config=config,
    ...     max_retries=5,
    ... )
    """
    try:
        from nautilus_trader.adapters.binance.config import (
            BinanceExecClientConfig,
        )
        from nautilus_trader.adapters.binance.common.enums import (
            BinanceAccountType as NautilusAccountType,
        )

        # 映射账户类型
        account_type_map = {
            BinanceAccountType.SPOT: NautilusAccountType.SPOT,
            BinanceAccountType.MARGIN: NautilusAccountType.MARGIN,
            BinanceAccountType.USDT_FUTURE: NautilusAccountType.USDT_FUTURE,
            BinanceAccountType.COIN_FUTURE: NautilusAccountType.COIN_FUTURE,
        }

        nautilus_account_type = account_type_map.get(
            config.account_type,
            NautilusAccountType.SPOT,
        )

        # 使用传入的参数或配置中的默认值
        retries = max_retries if max_retries is not None else config.max_retries
        delay = retry_delay if retry_delay is not None else config.retry_delay

        # 构建配置
        exec_config = BinanceExecClientConfig(
            account_type=nautilus_account_type,
            api_key=config.api_key,
            api_secret=config.api_secret,
            base_url=config.base_url,
            testnet=config.testnet,
            use_position_ids=use_position_ids,
            max_retries=retries,
            retry_delay=delay,
        )

        logger.debug(
            f"BinanceExecClientConfig 构建成功: "
            f"账户类型={nautilus_account_type.value}"
        )

        return exec_config

    except ImportError as e:
        logger.error(f"Nautilus Binance 配置导入失败: {e}")
        raise BinanceConfigError(
            "无法导入 Nautilus Binance 配置模块"
        ) from e

    except Exception as e:
        logger.error(f"构建 BinanceExecClientConfig 失败: {e}")
        raise BinanceConfigError(f"构建执行客户端配置失败: {e}") from e


def get_binance_venue(is_us: bool = False, is_futures: bool = False) -> str:
    """
    获取 Binance Venue 标识符

    根据配置返回合适的 Venue 标识符字符串。

    Parameters
    ----------
    is_us : bool
        是否使用 Binance US
    is_futures : bool
        是否为合约市场

    Returns
    -------
    str
        Venue 标识符

    Examples
    --------
    >>> venue = get_binance_venue(is_us=False, is_futures=False)
    >>> print(venue)
    "BINANCE"
    >>> venue = get_binance_venue(is_us=True, is_futures=False)
    >>> print(venue)
    "BINANCE_US"
    """
    if is_us:
        return "BINANCE_US"
    elif is_futures:
        return "BINANCE_FUTURES"
    else:
        return "BINANCE"


# =============================================================================
# 辅助函数
# =============================================================================

def resolve_binance_account_type(
    account_type: Union[str, BinanceAccountType]
) -> BinanceAccountType:
    """
    解析账户类型字符串为枚举值

    Parameters
    ----------
    account_type : Union[str, BinanceAccountType]
        账户类型字符串或枚举值

    Returns
    -------
    BinanceAccountType
        账户类型枚举值

    Raises
    ------
    BinanceConfigError
        无效的账户类型时抛出异常

    Examples
    --------
    >>> account_type = resolve_binance_account_type("SPOT")
    >>> print(account_type)
    BinanceAccountType.SPOT
    >>> account_type = resolve_binance_account_type(BinanceAccountType.FUTURES)
    >>> print(account_type)
    BinanceAccountType.USDT_FUTURE
    """
    if isinstance(account_type, BinanceAccountType):
        return account_type

    account_type_upper = account_type.upper()

    mapping = {
        "SPOT": BinanceAccountType.SPOT,
        "MARGIN": BinanceAccountType.MARGIN,
        "FUTURES": BinanceAccountType.USDT_FUTURE,
        "USDT_FUTURE": BinanceAccountType.USDT_FUTURE,
        "USDT-FUTURE": BinanceAccountType.USDT_FUTURE,
        "COIN_FUTURE": BinanceAccountType.COIN_FUTURE,
        "COIN-FUTURE": BinanceAccountType.COIN_FUTURE,
        "PORTFOLIO_MARGIN": BinanceAccountType.PORTFOLIO_MARGIN,
        "PORTFOLIO-MARGIN": BinanceAccountType.PORTFOLIO_MARGIN,
    }

    result = mapping.get(account_type_upper)
    if result is None:
        valid_types = ", ".join(mapping.keys())
        raise BinanceConfigError(
            f"无效的账户类型: {account_type}. "
            f"有效的类型包括: {valid_types}"
        )

    return result


def resolve_binance_environment(
    environment: Union[str, BinanceEnvironment]
) -> BinanceEnvironment:
    """
    解析环境类型字符串为枚举值

    Parameters
    ----------
    environment : Union[str, BinanceEnvironment]
        环境类型字符串或枚举值

    Returns
    -------
    BinanceEnvironment
        环境类型枚举值

    Raises
    ------
    BinanceConfigError
        无效的环境类型时抛出异常

    Examples
    --------
    >>> env = resolve_binance_environment("LIVE")
    >>> print(env)
    BinanceEnvironment.LIVE
    >>> env = resolve_binance_environment("TESTNET")
    >>> print(env)
    BinanceEnvironment.TESTNET
    """
    if isinstance(environment, BinanceEnvironment):
        return environment

    environment_upper = environment.upper()

    mapping = {
        "LIVE": BinanceEnvironment.LIVE,
        "PRODUCTION": BinanceEnvironment.LIVE,
        "PROD": BinanceEnvironment.LIVE,
        "TESTNET": BinanceEnvironment.TESTNET,
        "TEST": BinanceEnvironment.TESTNET,
        "SANDBOX": BinanceEnvironment.TESTNET,
    }

    result = mapping.get(environment_upper)
    if result is None:
        valid_envs = ", ".join(mapping.keys())
        raise BinanceConfigError(
            f"无效的环境类型: {environment}. "
            f"有效的类型包括: {valid_envs}"
        )

    return result


def validate_binance_credentials(
    api_key: str,
    api_secret: str,
    account_type: Optional[BinanceAccountType] = None,
    testnet: bool = True,
) -> Dict[str, Any]:
    """
    验证 Binance API 凭证

    验证 API Key 和 Secret 的格式是否正确，并可选择性地测试连接。

    Parameters
    ----------
    api_key : str
        API Key
    api_secret : str
        API Secret
    account_type : Optional[BinanceAccountType]
        账户类型，用于确定验证端点
    testnet : bool
        是否使用测试网

    Returns
    -------
    Dict[str, Any]
        验证结果字典，包含以下字段：
        - valid: 是否有效
        - message: 验证消息
        - account_type: 账户类型
        - permissions: 权限列表（如果验证成功）

    Raises
    ------
    BinanceCredentialError
        凭证格式无效时抛出异常

    Examples
    --------
    >>> result = validate_binance_credentials(
    ...     api_key="your_api_key",
    ...     api_secret="your_api_secret",
    ...     account_type=BinanceAccountType.SPOT,
    ...     testnet=True,
    ... )
    >>> print(result["valid"])
    True
    """
    result = {
        "valid": False,
        "message": "",
        "account_type": account_type.value if account_type else None,
        "permissions": [],
    }

    # 验证 API Key 格式
    if not api_key:
        result["message"] = "API Key 不能为空"
        return result

    if len(api_key) < 10:
        result["message"] = "API Key 格式无效（长度不足）"
        return result

    # 验证 API Secret 格式
    if not api_secret:
        result["message"] = "API Secret 不能为空"
        return result

    if len(api_secret) < 10:
        result["message"] = "API Secret 格式无效（长度不足）"
        return result

    # 基础格式验证通过
    result["valid"] = True
    result["message"] = "凭证格式有效"

    # 如果安装了 python-binance，可以尝试验证连接
    try:
        from binance.client import Client

        # 创建客户端（不验证连接）
        client = Client(api_key, api_secret, testnet=testnet)

        # 尝试获取服务器时间验证连接
        try:
            server_time = client.get_server_time()
            result["message"] = "凭证有效，连接成功"
            result["server_time"] = server_time

            # 尝试获取账户信息以验证权限
            if account_type == BinanceAccountType.SPOT:
                try:
                    account_info = client.get_account()
                    result["permissions"] = account_info.get("permissions", [])
                except Exception as e:
                    result["permissions_error"] = str(e)

        except Exception as e:
            result["valid"] = False
            result["message"] = f"连接验证失败: {str(e)}"
            logger.warning(f"Binance 凭证连接验证失败: {e}")

    except ImportError:
        # python-binance 未安装，跳过连接验证
        result["message"] = "凭证格式有效（未安装 python-binance，跳过连接验证）"
        logger.debug("python-binance 未安装，跳过连接验证")

    except Exception as e:
        logger.error(f"验证 Binance 凭证时发生错误: {e}")
        result["message"] = f"验证过程发生错误: {str(e)}"

    return result


def create_binance_config_from_dict(
    config_dict: Dict[str, Any]
) -> BinanceAdapterConfig:
    """
    从字典创建 BinanceAdapterConfig

    便捷函数，用于从配置字典创建配置对象。

    Parameters
    ----------
    config_dict : Dict[str, Any]
        配置字典，包含以下字段：
        - api_key: API Key
        - api_secret: API Secret
        - account_type: 账户类型（字符串或枚举）
        - environment: 环境类型（字符串或枚举）
        - is_us: 是否使用 Binance US
        - base_url: 自定义基础 URL
        - proxy_url: 代理 URL
        - 其他可选参数

    Returns
    -------
    BinanceAdapterConfig
        配置对象

    Raises
    ------
    BinanceConfigError
        配置无效时抛出异常

    Examples
    --------
    >>> config = create_binance_config_from_dict({
    ...     "api_key": "your_api_key",
    ...     "api_secret": "your_api_secret",
    ...     "account_type": "SPOT",
    ...     "environment": "TESTNET",
    ... })
    """
    try:
        # 解析账户类型
        account_type_str = config_dict.get("account_type", "SPOT")
        account_type = resolve_binance_account_type(account_type_str)

        # 解析环境类型
        environment_str = config_dict.get("environment", "TESTNET")
        environment = resolve_binance_environment(environment_str)

        # 创建配置对象
        config = BinanceAdapterConfig(
            api_key=config_dict.get("api_key", ""),
            api_secret=config_dict.get("api_secret", ""),
            account_type=account_type,
            environment=environment,
            is_us=config_dict.get("is_us", False),
            base_url=config_dict.get("base_url"),
            proxy_url=config_dict.get("proxy_url"),
            testnet=config_dict.get("testnet", environment == BinanceEnvironment.TESTNET),
            use_ssl=config_dict.get("use_ssl", True),
            timeout=config_dict.get("timeout", 30),
            recv_window=config_dict.get("recv_window", 5000),
            max_retries=config_dict.get("max_retries", 3),
            retry_delay=config_dict.get("retry_delay", 1.0),
            rate_limit=config_dict.get("rate_limit", True),
            extra_params=config_dict.get("extra_params", {}),
        )

        return config

    except Exception as e:
        logger.error(f"从字典创建配置失败: {e}")
        raise BinanceConfigError(f"创建配置失败: {e}") from e


# =============================================================================
# 模块导出
# =============================================================================

__all__ = [
    # 枚举类
    "BinanceAccountType",
    "BinanceEnvironment",
    # 异常类
    "BinanceAdapterError",
    "BinanceConfigError",
    "BinanceCredentialError",
    "BinanceClientError",
    # 配置类
    "BinanceAdapterConfig",
    # 工厂类
    "BinanceDataClientFactory",
    "BinanceExecClientFactory",
    # 配置构建函数
    "build_binance_data_config",
    "build_binance_exec_config",
    "get_binance_venue",
    # 辅助函数
    "resolve_binance_account_type",
    "resolve_binance_environment",
    "validate_binance_credentials",
    "create_binance_config_from_dict",
]
