"""Exchange Adapter — axon_quant.exchange 交易所适配器

包装 axon_quant.exchange.BinanceAdapter 和 OkxAdapter，
提供统一的交易所接口。

设计文档: docs/compose/specs/2026-06-24-core-trading-engine-design.md
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant.exchange import (
        BinanceAdapter as _BinanceAdapter,
    )
    from axon_quant.exchange import (
        ExchangeConfig as _ExchangeConfig,
    )
    from axon_quant.exchange import (
        ExchangeId as _ExchangeId,
    )
    from axon_quant.exchange import (
        OkxAdapter as _OkxAdapter,
    )
    from axon_quant.exchange import (
        binance_testnet_config as _binance_testnet_config,
    )
    from axon_quant.exchange import (
        okx_testnet_config as _okx_testnet_config,
    )

    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _BinanceAdapter = None
    _OkxAdapter = None
    _ExchangeConfig = None
    _ExchangeId = None
    _binance_testnet_config = None
    _okx_testnet_config = None


class ExchangeAdapter:
    """交易所适配器

    包装 axon_quant.exchange.BinanceAdapter 和 OkxAdapter，
    提供统一的交易所接口。

    Args:
        exchange_id: 交易所 ID ("binance" 或 "okx")
        testnet: 是否使用测试网
        api_key: API Key（可选，优先使用环境变量）
        api_secret: API Secret（可选，优先使用环境变量）

    Example:
        >>> adapter = ExchangeAdapter("binance", testnet=True)
        >>> adapter.connect()
        >>> ticker = adapter.get_ticker("BTCUSDT")
        >>> adapter.disconnect()
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        testnet: bool = True,
        api_key: str | None = None,
        api_secret: str | None = None,
    ):
        """初始化交易所适配器

        Args:
            exchange_id: 交易所 ID ("binance" 或 "okx")
            testnet: 是否使用测试网
            api_key: API Key（可选）
            api_secret: API Secret（可选）
        """
        if not AXON_AVAILABLE:
            msg = "axon_quant.exchange 不可用，请安装 axon_quant: pip install axon_quant"
            raise RuntimeError(msg)

        self._exchange_id = exchange_id
        self._testnet = testnet
        self._adapter = None

        # 创建适配器配置
        if exchange_id == "binance":
            if testnet:
                config = _binance_testnet_config()
            else:
                config = _ExchangeConfig(
                    exchange_id=_ExchangeId.BINANCE,
                    testnet=testnet,
                )
            self._adapter = _BinanceAdapter(config)
        elif exchange_id == "okx":
            config = _okx_testnet_config() if testnet else _ExchangeConfig(exchange_id=_ExchangeId.OKX, testnet=testnet)
            self._adapter = _OkxAdapter(config)
        else:
            msg = f"不支持的交易所: {exchange_id}"
            raise ValueError(msg)

        logger.info(f"ExchangeAdapter 已创建: {exchange_id}, testnet={testnet}")

    def connect(self) -> None:
        """连接交易所"""
        if self._adapter:
            self._adapter.connect()
            logger.info(f"已连接到 {self._exchange_id}")

    def disconnect(self) -> None:
        """断开交易所连接"""
        if self._adapter:
            self._adapter.disconnect()
            logger.info(f"已断开 {self._exchange_id}")

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        """获取行情

        Args:
            symbol: 交易对符号（如 "BTCUSDT"）

        Returns:
            行情字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_ticker(symbol)

    def place_order(self, order_dict: dict[str, Any]) -> dict[str, Any]:
        """下单

        Args:
            order_dict: 订单字典，包含:
                - symbol: 交易对符号
                - side: "Buy" 或 "Sell"
                - type: "limit" 或 "market"
                - quantity: 数量
                - price: 价格（限价单必填）
                - tif: 有效期（默认 "GTC"）

        Returns:
            订单结果字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.place_order(order_dict)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """撤单

        Args:
            order_id: 订单 ID

        Returns:
            撤单结果字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.cancel_order(order_id)

    def get_balance(self) -> dict[str, Any]:
        """获取余额

        Returns:
            余额字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_balance()

    def get_positions(self) -> list[dict[str, Any]]:
        """获取持仓

        Returns:
            持仓列表
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_positions()

    def subscribe(self, symbols: list[str]) -> None:
        """订阅行情

        Args:
            symbols: 交易对列表
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        self._adapter.subscribe(symbols)

    def get_depth(self, symbol: str) -> dict[str, Any]:
        """获取深度

        Args:
            symbol: 交易对符号

        Returns:
            深度字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_depth(symbol)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆

        Args:
            symbol: 交易对符号
            leverage: 杠杆倍数
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        self._adapter.set_leverage(symbol, leverage)

    def set_margin_type(self, symbol: str, margin_type: str) -> None:
        """设置保证金类型

        Args:
            symbol: 交易对符号
            margin_type: "isolated" 或 "cross"
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        self._adapter.set_margin_type(symbol, margin_type)

    def set_position_mode(self, hedge_mode: bool) -> None:
        """设置持仓模式

        Args:
            hedge_mode: 是否对冲模式
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        self._adapter.set_position_mode(hedge_mode)

    def get_account_info(self) -> dict[str, Any]:
        """获取账户信息

        Returns:
            账户信息字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_account_info()

    def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        """获取资金费率

        Args:
            symbol: 交易对符号

        Returns:
            资金费率字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_funding_rate(symbol)

    def get_open_interest(self, symbol: str) -> dict[str, Any]:
        """获取持仓量

        Args:
            symbol: 交易对符号

        Returns:
            持仓量字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_open_interest(symbol)

    def get_long_short_ratio(self, symbol: str) -> dict[str, Any]:
        """获取多空比

        Args:
            symbol: 交易对符号

        Returns:
            多空比字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_long_short_ratio(symbol)

    def get_leverage_brackets(self, symbol: str) -> dict[str, Any]:
        """获取杠杆档位

        Args:
            symbol: 交易对符号

        Returns:
            杠杆档位字典
        """
        if not self._adapter:
            msg = "交易所未连接"
            raise RuntimeError(msg)
        return self._adapter.get_leverage_brackets(symbol)


class ExchangeAdapterProxy:
    """交易所适配器代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        testnet: bool = True,
    ):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._adapter = ExchangeAdapter(exchange_id, testnet)
            except Exception as e:
                logger.error(f"创建 ExchangeAdapter 失败: {e}")
                self._available = False
                self._adapter = None
        else:
            self._adapter = None
            logger.warning("axon_quant.exchange 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.exchange 是否可用"""
        return self._available

    def connect(self) -> None:
        """连接交易所"""
        if self._available and self._adapter:
            self._adapter.connect()

    def disconnect(self) -> None:
        """断开交易所连接"""
        if self._available and self._adapter:
            self._adapter.disconnect()

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        """获取行情"""
        if not self._available or not self._adapter:
            return {}
        return self._adapter.get_ticker(symbol)

    def place_order(self, order_dict: dict[str, Any]) -> dict[str, Any]:
        """下单"""
        if not self._available or not self._adapter:
            return {"error": "exchange not available"}
        return self._adapter.place_order(order_dict)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """撤单"""
        if not self._available or not self._adapter:
            return {"error": "exchange not available"}
        return self._adapter.cancel_order(order_id)

    def get_balance(self) -> dict[str, Any]:
        """获取余额"""
        if not self._available or not self._adapter:
            return {}
        return self._adapter.get_balance()

    def get_positions(self) -> list[dict[str, Any]]:
        """获取持仓"""
        if not self._available or not self._adapter:
            return []
        return self._adapter.get_positions()

    def subscribe(self, symbols: list[str]) -> None:
        """订阅行情"""
        if self._available and self._adapter:
            self._adapter.subscribe(symbols)

    def get_depth(self, symbol: str) -> dict[str, Any]:
        """获取深度"""
        if not self._available or not self._adapter:
            return {}
        return self._adapter.get_depth(symbol)
