# -*- coding: utf-8 -*-
"""Compliance Service — axon_quant.compliance 合规审计服务

包装 axon_quant.compliance，提供交易合规审计功能。
当 axon_quant 不可用时提供清晰的错误信息。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# axon_quant 导入（可选）
try:
    from axon_quant.compliance import (
        ComplianceModule as _ComplianceModule,
        ComplianceConfig as _ComplianceConfig,
        TradeRecord as _TradeRecord,
        TradeSide as _TradeSide,
        OrderType as _OrderType,
        TradeStatus as _TradeStatus,
        AuditEventType as _AuditEventType,
    )
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _ComplianceModule = None
    _ComplianceConfig = None
    _TradeRecord = None
    _TradeSide = None
    _OrderType = None
    _TradeStatus = None
    _AuditEventType = None


class ComplianceServiceWrapper:
    """合规审计服务包装器

    包装 axon_quant.compliance，提供交易合规审计功能。

    Example:
        >>> svc = ComplianceServiceWrapper()
        >>> record = svc.create_trade_record(
        ...     trade_id="T1",
        ...     symbol="BTCUSDT",
        ...     side="Buy",
        ...     order_type="Limit",
        ...     price=50000.0,
        ...     quantity=0.1,
        ... )
        >>> svc.log_trade(record)
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """初始化合规审计服务

        Args:
            config: 配置字典（可选）
        """
        if not AXON_AVAILABLE:
            raise RuntimeError(
                "axon_quant.compliance 不可用，请安装 axon_quant: pip install axon_quant"
            )

        if config:
            compliance_config = _ComplianceConfig(**config)
        else:
            compliance_config = _ComplianceConfig()

        self._module = _ComplianceModule(compliance_config)
        logger.info("ComplianceService 已初始化")

    def create_trade_record(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: float,
        quantity: float,
        status: str = "Filled",
    ) -> Any:
        """创建交易记录

        Args:
            trade_id: 交易 ID
            symbol: 交易对符号
            side: "Buy" 或 "Sell"
            order_type: "Limit" 或 "Market"
            price: 价格
            quantity: 数量
            status: 状态 ("Filled", "Cancelled", "Rejected")

        Returns:
            TradeRecord 实例
        """
        side_enum = _TradeSide.BUY if side == "Buy" else _TradeSide.SELL
        type_enum = _OrderType.LIMIT if order_type == "Limit" else _OrderType.MARKET
        status_enum = getattr(_TradeStatus, status.upper(), _TradeStatus.FILLED)

        return _TradeRecord(
            trade_id=trade_id,
            symbol=symbol,
            side=side_enum,
            order_type=type_enum,
            price=price,
            quantity=quantity,
            status=status_enum,
        )

    def log_trade(self, record: Any) -> None:
        """记录交易

        Args:
            record: TradeRecord 实例
        """
        self._module.log_trade(record)
        logger.info(f"交易已记录: {record.trade_id}")

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """获取审计日志

        Returns:
            审计日志列表
        """
        return self._module.get_audit_trail()


class ComplianceServiceProxy:
    """合规审计服务代理

    当 axon_quant 不可用时提供空实现。
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        self._available = AXON_AVAILABLE
        if self._available:
            try:
                self._service = ComplianceServiceWrapper(config)
            except Exception as e:
                logger.error(f"创建 ComplianceService 失败: {e}")
                self._available = False
                self._service = None
        else:
            self._service = None
            logger.warning("axon_quant.compliance 不可用，使用空实现")

    @property
    def available(self) -> bool:
        """axon_quant.compliance 是否可用"""
        return self._available

    def create_trade_record(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: float,
        quantity: float,
        status: str = "Filled",
    ) -> Optional[Any]:
        """创建交易记录"""
        if not self._available or not self._service:
            return None
        return self._service.create_trade_record(
            trade_id, symbol, side, order_type, price, quantity, status
        )

    def log_trade(self, record: Any) -> None:
        """记录交易"""
        if self._available and self._service:
            self._service.log_trade(record)

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """获取审计日志"""
        if not self._available or not self._service:
            return []
        return self._service.get_audit_trail()
