"""Trading Tools Service — axon_quant.trading 交易工具服务

包装 axon_quant.trading，提供 PlaceOrderTool、QueryPortfolioTool 等工具。
当 axon_quant 不可用时提供清晰的错误信息。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# axon_bridge 导入（可选）
try:
    from axon_bridge import (
        CancelOrderTool as _CancelOrderTool,
    )
    from axon_bridge import (
        MockTradingBackend as _MockTradingBackend,
    )
    from axon_bridge import (
        PlaceOrderTool as _PlaceOrderTool,
    )
    from axon_bridge import (
        QueryPortfolioTool as _QueryPortfolioTool,
    )
    from axon_bridge import (
        ReplaceOrderTool as _ReplaceOrderTool,
    )
    from axon_bridge import (
        RiskLimits as _RiskLimits,
    )
    from axon_bridge import (
        TradingMetrics as _TradingMetrics,
    )

    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _PlaceOrderTool = None
    _QueryPortfolioTool = None
    _CancelOrderTool = None
    _ReplaceOrderTool = None
    _MockTradingBackend = None
    _RiskLimits = None
    _TradingMetrics = None


class TradingToolsServiceWrapper:
    """交易工具服务包装器

    包装 axon_quant.trading，提供交易工具功能。

    Example:
        >>> svc = TradingToolsServiceWrapper()
        >>> backend = svc.create_mock_backend()
        >>> risk = svc.create_risk_limits(["BTC-USDT"])
        >>> place = svc.create_place_order_tool(backend, "dry_run", risk)
        >>> result = place.execute({"symbol": "BTC-USDT", "side": "Buy", "quantity": 0.1, "price": 50000.0})
    """

    def __init__(self):
        """初始化交易工具服务"""
        if not AXON_AVAILABLE:
            msg = "axon_quant.trading 不可用，请安装 axon_quant: pip install axon_quant"
            raise RuntimeError(msg)
        logger.info("TradingToolsService 已初始化")

    def create_mock_backend(self) -> Any:
        """创建 Mock 交易后端

        Returns:
            MockTradingBackend 实例
        """
        return _MockTradingBackend()

    def create_risk_limits(
        self,
        allowed_symbols: list[str] | None = None,
    ) -> Any:
        """创建风控限制

        Args:
            allowed_symbols: 允许的交易对列表

        Returns:
            RiskLimits 实例
        """
        if allowed_symbols:
            return _RiskLimits(allowed_symbols=allowed_symbols)
        return _RiskLimits.permissive()

    def create_place_order_tool(
        self,
        backend: Any,
        mode: str = "dry_run",
        risk: Any | None = None,
    ) -> Any:
        """创建下单工具

        Args:
            backend: 交易后端
            mode: 模式 ("dry_run" 或 "live")
            risk: 风控限制

        Returns:
            PlaceOrderTool 实例
        """
        return _PlaceOrderTool(backend=backend, mode=mode, risk=risk)

    def create_query_portfolio_tool(self, backend: Any) -> Any:
        """创建查询持仓工具

        Args:
            backend: 交易后端

        Returns:
            QueryPortfolioTool 实例
        """
        return _QueryPortfolioTool(backend=backend)

    def create_cancel_order_tool(self, backend: Any) -> Any:
        """创建撤单工具

        Args:
            backend: 交易后端

        Returns:
            CancelOrderTool 实例
        """
        return _CancelOrderTool(backend=backend)

    def create_replace_order_tool(self, backend: Any) -> Any:
        """创建改单工具

        Args:
            backend: 交易后端

        Returns:
            ReplaceOrderTool 实例
        """
        return _ReplaceOrderTool(backend=backend)


class TradingToolsServiceProxy:
    """交易工具服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._service = TradingToolsServiceWrapper()
            except Exception as e:
                logger.error(f"创建 TradingToolsService 失败: {e}")
                self._available = False
                self._service = None
        else:
            self._service = None
            logger.warning("axon_quant.trading 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.trading 是否可用"""
        return self._available

    def create_mock_backend(self) -> Any | None:
        """创建 Mock 交易后端"""
        if not self._available or not self._service:
            return None
        return self._service.create_mock_backend()

    def create_risk_limits(
        self,
        allowed_symbols: list[str] | None = None,
    ) -> Any | None:
        """创建风控限制"""
        if not self._available or not self._service:
            return None
        return self._service.create_risk_limits(allowed_symbols)

    def create_place_order_tool(
        self,
        backend: Any,
        mode: str = "dry_run",
        risk: Any | None = None,
    ) -> Any | None:
        """创建下单工具"""
        if not self._available or not self._service:
            return None
        return self._service.create_place_order_tool(backend, mode, risk)

    def create_query_portfolio_tool(self, backend: Any) -> Any | None:
        """创建查询持仓工具"""
        if not self._available or not self._service:
            return None
        return self._service.create_query_portfolio_tool(backend)

    def create_cancel_order_tool(self, backend: Any) -> Any | None:
        """创建撤单工具"""
        if not self._available or not self._service:
            return None
        return self._service.create_cancel_order_tool(backend)

    def create_replace_order_tool(self, backend: Any) -> Any | None:
        """创建改单工具"""
        if not self._available or not self._service:
            return None
        return self._service.create_replace_order_tool(backend)
