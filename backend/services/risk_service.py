"""RiskService — axon_bridge.risk 业务封装。

QuantCell 业务代码统一从 ``axon_bridge`` 入口拿 axon_quant 能力,
不在 services 层直接 import 第三方包。
"""

from __future__ import annotations

from typing import Any

try:
    # 走适配层,不直接 import axon_quant
    from axon_bridge import (
        DefaultRiskEngine,
        RiskConfig,
        make_order,
        make_portfolio,
    )

    AVAILABLE = True
except ImportError:
    AVAILABLE = False


class RiskService:
    """Risk service wrapping axon_quant.risk.DefaultRiskEngine (via axon_bridge)."""

    def __init__(self, config: dict[str, Any] | None = None):
        if not AVAILABLE:
            msg = "axon_quant.risk not available"
            raise RuntimeError(msg)
        risk_config = RiskConfig(**(config or {}))
        self._engine = DefaultRiskEngine(risk_config)

    def _to_axon_portfolio(self, portfolio: dict[str, Any] | None = None) -> Any:
        """将任意 portfolio 格式转换为 axon_quant 原生 portfolio。

        支持两种格式 (与 check_order 保持一致):
        - QuantCell 业务格式 (LivePortfolio.to_dict): ``cash`` 是 float
        - axon_quant 原生格式: ``cash`` 是 {currency: amount} dict
        """
        raw_cash = (portfolio or {}).get("cash", 0.0)
        if isinstance(raw_cash, (int, float)):
            cash_dict = {"USD": float(raw_cash)}
        elif isinstance(raw_cash, dict):
            cash_dict = {k: float(v) for k, v in raw_cash.items()}
        else:
            cash_dict = {"USD": 0.0}
        base_currency = next(iter(cash_dict.keys())) if cash_dict else "USD"
        return make_portfolio(base_currency=base_currency, cash=cash_dict)

    def check_order(
        self,
        order: dict[str, Any],
        portfolio: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if order passes risk controls.

        支持两种 portfolio 格式:
        - QuantCell 业务格式 (LivePortfolio.to_dict): ``cash`` 是 float,
          ``positions`` 是 {symbol: {quantity, avg_price, side, ...}}.
        - axon_quant 原生格式: ``cash`` 是 {currency: amount} dict.
        """
        # 对齐订单字段
        # NOTE: axon_quant.risk 对 type='market' 订单会跳过 max_order_value 检查,
        # 风控层统一以 'limit' 形式过检, 交易所下单时仍可选择市价/限价。
        risk_order_type = "limit"
        axon_order = make_order(
            id=int(order.get("id", 0) or 0),
            symbol=order.get("symbol", "BTC-USDT"),
            side=str(order.get("side", "Buy")).capitalize(),
            type=risk_order_type,
            quantity=float(order.get("quantity", 0.0)),
            price=float(order.get("price", 0.0)) if order.get("price") else None,
        )

        # 从 QuantCell 格式构造 axon 持仓 dict: {symbol: qty*avg_price}
        positions_value = portfolio.get("positions", {}) or {}
        if isinstance(positions_value, dict):
            positions_dict: dict[str, float] = {}
            for sym, p in positions_value.items():
                if isinstance(p, dict):
                    qty = float(p.get("quantity", 0.0))
                    avg = float(p.get("avg_price", 0.0))
                    positions_dict[sym] = qty * avg
                else:
                    positions_dict[sym] = float(p)
        else:
            positions_dict = {}

        axon_portfolio = self._to_axon_portfolio(portfolio)
        # ponytail: axon_quant.make_portfolio 不接受 positions 参数,
        # 目前 axon_quant 端风控仅基于 cash + max_order_value / max_daily_loss 等,
        # 持仓维度 (concentration / drawdown) 由 pipeline 本地风控补足。
        # 升级路径: 等上游 make_portfolio_with_positions 可用时改用它。

        result = self._engine.check_order(axon_order, axon_portfolio)
        return {
            "passed": result.is_allow,
            "reason": str(result.reason) if result.reason else None,
        }

    def get_metrics(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get current risk metrics."""
        axon_portfolio = self._to_axon_portfolio(portfolio)
        return self._engine.metrics(axon_portfolio)

    def reset_daily(self) -> None:
        """Reset daily counters."""
        self._engine.reset_daily()
