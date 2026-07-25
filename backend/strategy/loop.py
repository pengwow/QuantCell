# -*- coding: utf-8 -*-
"""StrategyLoop — 实盘策略循环

使用 axon_quant.exchange adapter 获取行情，
执行策略生成的 Action 订单，强制经过风控检查。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from axon_bridge import Action

logger = logging.getLogger(__name__)


class StrategyLoop:
    """实盘策略循环

    Args:
        adapter: 交易所适配器（axon_quant.exchange.*Adapter）
        strategy: 策略实例（实现 on_bar → Action）
        symbol: 交易对符号
        interval: 轮询间隔（秒）
        risk_engine: 风控引擎（需实现 check_order(order, portfolio) -> {"passed": bool, "reason": str}）
        account_equity: 账户净值（用于 target_position → qty 转换）
        event_callback: 事件回调 fn(event_type: str, data: dict)，用于 WebSocket 推送和状态更新
    """

    def __init__(
        self,
        adapter: Any,
        strategy: Any,
        symbol: str,
        interval: float = 1.0,
        risk_engine: Any = None,
        account_equity: float = 100_000.0,
        event_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ):
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._risk_engine = risk_engine
        self._account_equity = account_equity
        self._event_callback = event_callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._order_count = 0
        self._rejected_count = 0
        self._fill_count = 0
        self._last_price = 0.0
        self._last_action: Optional[str] = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "order_count": self._order_count,
            "fill_count": self._fill_count,
            "rejected_count": self._rejected_count,
            "last_price": self._last_price,
            "last_action": self._last_action,
        }

    def start(self) -> None:
        self._adapter.connect()
        if hasattr(self._adapter, "subscribe"):
            self._adapter.subscribe([self._symbol])

        self._strategy.on_start()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"StrategyLoop 已启动: {self._symbol}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._strategy.on_stop()
        self._adapter.disconnect()
        logger.info(f"StrategyLoop 已停止: {self._symbol}")

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """发出事件回调（线程安全）"""
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"事件回调失败 ({event_type}): {e}")

    def _run_loop(self) -> None:
        while self._running:
            try:
                ticker = self._adapter.get_ticker(self._symbol)
                close_price = float(ticker.get("last", 0.0))
                bar = {
                    "open": float(ticker.get("open", close_price)),
                    "high": float(ticker.get("high", close_price)),
                    "low": float(ticker.get("low", close_price)),
                    "close": close_price,
                    "volume": float(ticker.get("volume", 0.0)),
                    "symbol": self._symbol,
                    "timestamp_ns": int(time.time() * 1_000_000_000),
                }
                self._last_price = close_price

                action = self._strategy.on_bar(bar)
                action_type_str = str(action.action_type)
                self._last_action = action_type_str
                if action_type_str in ("buy", "sell"):
                    self._execute_action(action, close_price)

                self._emit("bar.processed", {
                    "symbol": self._symbol,
                    "price": close_price,
                    "action": action_type_str,
                    "timestamp": bar["timestamp_ns"],
                })

            except Exception as e:
                logger.error(f"StrategyLoop 错误: {e}", exc_info=True)

            time.sleep(self._interval)

    def _execute_action(self, action: Action, current_price: float) -> None:
        """执行 Action：置信度过滤 → qty 计算 → 风控检查 → 下单"""
        try:
            # 1. 置信度过滤
            confidence = float(getattr(action, "confidence", 1.0) or 0.0)
            if confidence < 0.3:
                logger.debug(f"信号置信度 {confidence:.2f} < 0.3，跳过")
                return

            # 2. qty 计算：target_position 是仓位比例（与 BacktestLoop 一致）
            ratio = float(getattr(action, "target_position", 0.0) or 0.0)
            action_type_str = str(action.action_type)
            if current_price <= 0:
                logger.warning(f"当前价格无效: {current_price}")
                return
            qty = abs(ratio) * self._account_equity / current_price
            if qty <= 0:
                return

            side = "Buy" if action_type_str == "buy" else "Sell"

            order_dict = {
                "symbol": self._symbol,
                "side": side,
                "type": "market",
                "quantity": qty,
                "price": current_price,
            }

            # 3. 风控检查
            if self._risk_engine is not None:
                portfolio_state = {"cash": {"USD": self._account_equity}}
                check = self._risk_engine.check_order(order_dict, portfolio_state)
                if not check.get("passed"):
                    self._rejected_count += 1
                    reason = check.get("reason", "unknown")
                    self._emit("order.rejected", {
                        "symbol": self._symbol,
                        "side": side,
                        "quantity": qty,
                        "price": current_price,
                        "reason": reason,
                    })
                    logger.warning(f"风控拒绝订单: {reason}")
                    return

            # 4. 执行下单
            result = self._adapter.place_order(order_dict)
            self._order_count += 1

            self._emit("order.placed", {
                "symbol": self._symbol,
                "side": side,
                "quantity": qty,
                "price": current_price,
                "order_id": result.get("order_id", "") if isinstance(result, dict) else "",
                "confidence": confidence,
            })
            logger.info(f"订单已执行: {order_dict} -> {result}")

        except Exception as e:
            logger.error(f"订单执行失败: {e}")
