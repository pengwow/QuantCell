"""ExecutionPipeline — 事件驱动订单执行管道

决策(dict) → 风控 → 订单管理 → 交易所执行 → 持仓更新

替代 StrategyLoop._execute_action() 中的手动逻辑，
统一走: RiskEngine → OMSService → ExchangeAdapter → LivePortfolio
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .live_portfolio import LivePortfolio

logger = logging.getLogger(__name__)

# 已终结订单 (成交/拒绝) 的最大保留条数, 防止长时间运行内存无限增长
_MAX_HISTORY_ORDERS = 1000


@dataclass
class ExecutionResult:
    """执行结果。"""

    accepted: bool = True
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    reason: str = ""
    exchange_result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "reason": self.reason,
        }


class ExecutionPipeline:
    """订单执行管道。

    Args:
        adapter: 交易所适配器 (axon_quant.exchange.*Adapter)
        portfolio: LivePortfolio 实例
        risk_engine: 风控引擎 (RiskService 或 axon_quant.risk.DefaultRiskEngine)
        event_callback: 事件回调 fn(event_type, data)
        max_position_ratio: 单一品种最大仓位比例 (默认 0.5 = 50% 初始资金, 对齐 axon_quant RiskConfig 保守默认)
        enable_circuit_breaker: 是否启用熔断
    """

    def __init__(
        self,
        adapter: Any,
        portfolio: LivePortfolio | None = None,
        risk_engine: Any = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        max_position_ratio: float = 0.5,
        enable_circuit_breaker: bool = True,
        max_daily_loss: float | None = None,
        circuit_break_cooldown_secs: int = 300,
    ):
        self._adapter = adapter
        self._portfolio = portfolio or LivePortfolio()
        self._risk_engine = risk_engine
        self._event_callback = event_callback
        self._max_position_ratio = max_position_ratio
        self._enable_circuit_breaker = enable_circuit_breaker
        # 日亏损熔断阈值: 优先级 显式传入 > RiskConfig 默认 > 兜底 10000
        if max_daily_loss is not None:
            self._max_daily_loss: float = float(max_daily_loss)
        else:
            try:
                from axon_bridge import RiskConfig

                self._max_daily_loss = float(RiskConfig().max_daily_loss)
            except Exception:
                self._max_daily_loss = 10_000.0
        self._circuit_break_cooldown_secs = int(circuit_break_cooldown_secs)

        # 内存中订单状态追踪
        # 挂单用 dict (需按 id 查找更新状态); 已终结订单用 deque 限制内存
        self._pending_orders: dict[str, dict[str, Any]] = {}
        self._filled_orders: deque[tuple[str, dict[str, Any]]] = deque(maxlen=_MAX_HISTORY_ORDERS)
        self._rejected_orders: deque[tuple[str, dict[str, Any]]] = deque(maxlen=_MAX_HISTORY_ORDERS)

        # 熔断状态
        self._circuit_broken = False
        self._circuit_break_until: float = 0.0

    @property
    def portfolio(self) -> LivePortfolio:
        return self._portfolio

    @property
    def circuit_broken(self) -> bool:
        if not self._enable_circuit_breaker:
            return False
        if not self._circuit_broken:
            return False
        if time.time() > self._circuit_break_until:
            # 自动恢复
            self._circuit_broken = False
            self._emit("circuit.recovered", {"reason": "timeout"})
            return False
        return True

    def execute_decision(self, decision: dict[str, Any], current_price: float) -> ExecutionResult:
        """执行 SwarmRunner/Agent 的决策结果。

        decision 格式 (SwarmRunner.on_bar 返回):
            {
                "final_action": "Buy" | "Sell" | "Hold",
                "final_confidence": 0.8,
                "votes": [...],
                "aggregated": {...},
                "risk_verdict": {"approved": True, "reason": None},
            }

        Returns:
            ExecutionResult
        """
        action = decision.get("final_action", "Hold")
        confidence = decision.get("final_confidence", 0.0)
        risk_verdict = decision.get("risk_verdict", {"approved": True})

        # 1. Hold = 不执行
        if action in ("Hold", "hold"):
            return ExecutionResult(accepted=False, reason="hold")

        # 2. 风控检查 (SwarmRunner 已做一层，这里做更严格的)
        if not risk_verdict.get("approved", True):
            return ExecutionResult(
                accepted=False,
                symbol=decision.get("symbol", ""),
                reason=risk_verdict.get("reason", "risk_rejected"),
            )

        # 3. 熔断检查
        if self.circuit_broken:
            return ExecutionResult(
                accepted=False,
                reason=f"circuit_broken_until={self._circuit_break_until}",
            )

        # 4. 构造订单
        # symbol 缺失时拒绝执行, 避免静默交易错误品种
        symbol = decision.get("symbol", "")
        if not symbol:
            logger.warning("决策缺少 symbol 字段, 拒绝执行")
            return ExecutionResult(accepted=False, reason="missing_symbol")
        side = action.capitalize()  # "Buy" / "Sell"
        # target_position 优先从 decision 获取, 没有则用 final_confidence * 默认比例
        ratio = float(decision.get("target_position", 0.0) or 0.0)
        if ratio <= 0:
            conf_fallback = float(decision.get("final_confidence", 0.0) or 0.0)
            ratio = conf_fallback * 0.1  # 默认 10% 仓位比例
        qty = self._calc_qty(ratio, current_price, symbol)

        if qty <= 0:
            return ExecutionResult(accepted=False, symbol=symbol, reason="qty_zero")

        # 5. 本地风控 (仓位限制、最大下单金额、现金充足性等)
        local_check = self._local_risk_check(symbol, side, qty, current_price)
        if not local_check["passed"]:
            return ExecutionResult(
                accepted=False,
                symbol=symbol,
                side=side,
                reason=local_check.get("reason", "local_risk_rejected"),
            )

        # 6. 外部风控引擎检查
        if self._risk_engine is not None:
            order_dict = {
                "symbol": symbol,
                "side": side,
                "type": "market",
                "quantity": qty,
                "price": current_price,
            }
            # RiskService 接受 dict, 内部调用 axon_quant.risk
            risk_result = self._call_risk_engine(order_dict)
            if not risk_result.get("passed", True):
                self._rejected_orders.append(
                    (
                        str(uuid.uuid4())[:8],
                        {
                            **order_dict,
                            "reason": risk_result.get("reason", "unknown"),
                            "timestamp": time.time(),
                        },
                    )
                )
                self._portfolio.total_orders += 1
                return ExecutionResult(
                    accepted=False,
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=current_price,
                    reason=risk_result.get("reason", "risk_rejected"),
                )

        # 7. 执行下单
        order_id = str(uuid.uuid4())[:8]
        order_dict = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "quantity": qty,
            "price": current_price,
            "order_id": order_id,
        }

        try:
            result = self._adapter.place_order(order_dict)
            self._portfolio.total_orders += 1
            self._pending_orders[order_id] = {
                **order_dict,
                "status": "pending",
                "timestamp": time.time(),
            }

            # 8. 模拟成交 (实盘应监听 websocket 用户数据流)
            fill_price = self._simulate_fill_price(current_price, side)
            self._on_fill(order_dict, fill_price, fee=0.0004)

            self._emit(
                "order.placed",
                {
                    "symbol": symbol,
                    "side": side,
                    "quantity": qty,
                    "price": current_price,
                    "order_id": order_id,
                    "confidence": confidence,
                },
            )

            return ExecutionResult(
                accepted=True,
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=qty,
                price=current_price,
                exchange_result=result if isinstance(result, dict) else {"result": str(result)},
            )

        except Exception as e:
            logger.error(f"下单失败: {e}")
            return ExecutionResult(
                accepted=False,
                symbol=symbol,
                side=side,
                quantity=qty,
                price=current_price,
                reason=f"submit_error: {e}",
            )

    def _calc_qty(self, ratio: float, price: float, symbol: str) -> float:
        """根据 target_position 比例计算实际下单数量。"""
        if ratio <= 0 or price <= 0:
            return 0.0

        # 获取当前权益
        equity = self._portfolio.mark_to_market({symbol: price})
        notional = abs(ratio) * equity
        qty = notional / price

        # 最小下单量检查 (比特币 0.00001)
        min_qty = 0.00001
        if qty < min_qty:
            return 0.0

        return round(qty, 6)

    def _local_risk_check(self, symbol: str, side: str, qty: float, price: float) -> dict[str, Any]:
        """本地风控检查 (现金、单笔上限、最大仓位等)。

        与 axon_quant RiskConfig 默认值对齐, 但不依赖其内部对 market/limit
        的差异化处理, 保证任何类型订单都受相同限制。
        """
        notional = qty * price

        # 单笔订单金额上限 (RiskConfig 默认 50000 USD)
        max_order_value = 50_000.0
        if notional > max_order_value:
            return {
                "passed": False,
                "reason": f"max_order_value_exceeded: {notional:.2f} > {max_order_value:.2f}",
            }

        # 现金检查
        if side.lower() == "buy" and notional > self._portfolio.cash:
            return {"passed": False, "reason": "insufficient_cash"}

        # 最大仓位检查
        pos = self._portfolio.get_position(symbol)
        current_pos_value = abs(pos.quantity) * price
        new_pos_value = current_pos_value + notional
        max_allowed = self._max_position_ratio * self._portfolio.initial_cash

        if new_pos_value > max_allowed:
            return {
                "passed": False,
                "reason": f"position_limit_exceeded: {new_pos_value:.2f} > {max_allowed:.2f}",
            }

        return {"passed": True}

    def _call_risk_engine(self, order_dict: dict[str, Any]) -> dict[str, Any]:
        """调用外部风控引擎。"""
        try:
            # RiskService.check_order 接受 dict 并返回 {"passed": bool, "reason": str}
            portfolio_state = self._portfolio.to_dict()
            if hasattr(self._risk_engine, "check_order"):
                return self._risk_engine.check_order(order_dict, portfolio_state)
            elif hasattr(self._risk_engine, "check"):
                return self._risk_engine.check(order_dict)
            else:
                return {"passed": True}
        except Exception as e:
            logger.warning(f"风控引擎调用失败，默认放行: {e}")
            return {"passed": True}

    def _simulate_fill_price(self, price: float, side: str) -> float:
        """模拟成交价 (简化版: 按 0.02% 滑点计算)。

        ponytail: paper trading 简化 — 假设市价单立即全部成交。
        实盘应监听 adapter 用户数据流获取真实成交回报 (可能部分成交/被拒),
        升级路径: 订阅订单状态事件后按实际 fill 回调 _on_fill。
        """
        if side.lower() == "buy":
            return price * 1.0002
        else:
            return price * 0.9998

    def _on_fill(self, order_dict: dict[str, Any], fill_price: float, fee: float) -> None:
        """成交回写: 更新持仓和现金。"""
        symbol = order_dict["symbol"]
        side = order_dict["side"]
        qty = order_dict["quantity"]

        self._portfolio.update_on_fill(symbol, side, qty, fill_price, fee)

        order_id = order_dict.get("order_id", "")
        if order_id and order_id in self._pending_orders:
            self._pending_orders[order_id]["status"] = "filled"
            self._pending_orders[order_id]["fill_price"] = fill_price
            self._filled_orders.append((order_id, self._pending_orders.pop(order_id)))

        self._emit(
            "order.filled",
            {
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "fill_price": fill_price,
                "fee": fee,
                "order_id": order_id,
                "portfolio": self._portfolio.to_dict(),
            },
        )

    def trigger_circuit_breaker(self, reason: str = "manual") -> None:
        """触发熔断 (手动或由日亏损检测调用)。"""
        self._circuit_broken = True
        self._circuit_break_until = time.time() + self._circuit_break_cooldown_secs
        self._emit(
            "circuit.triggered",
            {"reason": reason, "until": self._circuit_break_until, "cooldown_secs": self._circuit_break_cooldown_secs},
        )
        logger.warning(f"熔断触发: {reason}, 持续 {self._circuit_break_cooldown_secs}s")

    def check_daily_loss_circuit_breaker(self, price_map: dict[str, float] | None = None) -> bool:
        """基于 LivePortfolio 盈亏触发日亏损熔断 (返回 True 表示触发了熔断)。

        这是深化风控集成的关键入口: 不再依赖代码中零散的 daily_loss 计数,
        而是直接读取 LivePortfolio 已实现/未实现盈亏, 与 max_daily_loss 比对。

        Args:
            price_map: 未实现盈亏的 mark-to-market 价格表 {symbol: price}。
                       缺省时只使用已实现盈亏判断。
        """
        if not self._enable_circuit_breaker:
            return False
        if self.circuit_broken:
            return True  # 已经熔断了

        realized = self._portfolio.total_realized_pnl
        if price_map is not None:
            unrealized = (
                float(self._portfolio.mark_to_market(price_map)) - float(self._portfolio.initial_cash) - realized
            )
        else:
            unrealized = self._portfolio.total_unrealized_pnl
        total_pnl = realized + unrealized

        # 总亏损超过 max_daily_loss → 熔断 (用负数比较: total_pnl < -threshold)
        threshold = float(self._max_daily_loss)
        if threshold > 0 and total_pnl < -threshold:
            self.trigger_circuit_breaker(f"daily_loss_exceeded: total_pnl={total_pnl:.2f} < -{threshold:.2f}")
            return True
        return False

    @property
    def max_daily_loss(self) -> float:
        return self._max_daily_loss

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"事件回调失败 ({event_type}): {e}")
