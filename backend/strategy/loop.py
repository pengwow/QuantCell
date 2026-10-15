"""StrategyLoop — 实盘策略循环

使用 axon_quant.exchange adapter 获取行情，
执行策略生成的 Action 订单，强制经过风控检查。

支持因子注入：启动时 fetch_ohlcv 填充 KlineBuffer，逐 tick 更新，
FactorInjector 计算因子值注入 StrategyContext.features，策略通过
ctx.get_feature(name) 读取。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from axon_bridge import Action

logger = logging.getLogger(__name__)


class StrategyLoop:
    """实盘策略循环

    Args:
        adapter: 交易所适配器（axon_quant.exchange.*Adapter）
        strategy: 策略实例（实现 on_bar(bar, ctx) → Action）
        symbol: 交易对符号
        interval: 轮询间隔（秒）
        risk_engine: 风控引擎（需实现 check_order(order, portfolio) -> {"passed": bool, "reason": str}）
        account_equity: 账户净值（用于 target_position → qty 转换）
        event_callback: 事件回调 fn(event_type: str, data: dict)，用于 WebSocket 推送和状态更新
        factor_names: 需要注入的因子名列表（内置或自定义）；为空则不注入因子
        timeframe: K 线周期（"1h"/"4h"/"1d" 等），用于 KlineBuffer 和 fetch_ohlcv
        kline_buffer_len: KlineBuffer 最大长度（默认 1000）
    """

    def __init__(
        self,
        adapter: Any,
        strategy: Any,
        symbol: str,
        interval: float = 1.0,
        risk_engine: Any = None,
        account_equity: float = 100_000.0,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        factor_names: list[str] | None = None,
        timeframe: str = "1h",
        kline_buffer_len: int = 1000,
    ):
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._risk_engine = risk_engine
        self._account_equity = account_equity
        self._event_callback = event_callback
        self._factor_names = list(factor_names) if factor_names else []
        self._timeframe = timeframe
        self._kline_buffer_len = kline_buffer_len
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._order_count = 0
        self._rejected_count = 0
        self._fill_count = 0
        self._last_price = 0.0
        self._last_action: str | None = None
        # 因子注入相关（start() 中初始化）
        self._kline_buffer: Any = None
        self._factor_injector: Any = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

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

        # 初始化 KlineBuffer + FactorInjector（如果配置了因子）
        if self._factor_names:
            self._init_factor_injection()

        self._strategy.on_start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"StrategyLoop 已启动: {self._symbol}")

    def _init_factor_injection(self) -> None:
        """初始化 KlineBuffer 并加载历史 K 线，创建 FactorInjector。"""
        if not self._factor_names:
            return
        try:
            from axon_quant.backtest import KlineBuffer

            from strategy.factor_injector import FactorInjector

            self._kline_buffer = KlineBuffer(self._timeframe, self._kline_buffer_len)

            # 尝试通过 adapter.fetch_ohlcv 加载历史 K 线
            # fetch_ohlcv 返回的 timestamp 是毫秒，KlineBuffer.load_history 期望纳秒
            if hasattr(self._adapter, "fetch_ohlcv"):
                try:
                    history = self._adapter.fetch_ohlcv(self._symbol, self._timeframe, self._kline_buffer_len)
                    if history:
                        normalized = [
                            {
                                "timestamp": int(b["timestamp"]) * 1_000_000,
                                "open": float(b["open"]),
                                "high": float(b["high"]),
                                "low": float(b["low"]),
                                "close": float(b["close"]),
                                "volume": float(b["volume"]),
                            }
                            for b in history
                        ]
                        self._kline_buffer.load_history(normalized)
                        logger.info(f"KlineBuffer 已加载 {len(normalized)} 根历史 K 线: {self._symbol}")
                except Exception as e:
                    logger.warning(f"fetch_ohlcv 加载历史 K 线失败: {e}")

            self._factor_injector = FactorInjector.from_factor_names(self._factor_names)
            logger.info(f"FactorInjector 已初始化: {self._symbol}, factors={self._factor_names}")
        except Exception as e:
            logger.error(f"因子注入初始化失败，将退化为无因子模式: {e}", exc_info=True)
            self._kline_buffer = None
            self._factor_injector = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.error(f"StrategyLoop 线程未能在 5s 内停止: {self._symbol}")
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
        while not self._stop_event.is_set():
            try:
                ticker = self._adapter.get_ticker(self._symbol)
                close_price = float(ticker.get("last", 0.0))
                if close_price <= 0:
                    # 行情源未就绪（如 paper 模式无真实行情）：跳过本轮，
                    # 不把 0 价 bar 喂给策略（会污染均线/指标窗口的脏数据）
                    self._stop_event.wait(self._interval)
                    continue

                timestamp_ns = int(time.time() * 1_000_000_000)
                bar = {
                    "open": float(ticker.get("open", close_price)),
                    "high": float(ticker.get("high", close_price)),
                    "low": float(ticker.get("low", close_price)),
                    "close": close_price,
                    "volume": float(ticker.get("volume", 0.0)),
                    "symbol": self._symbol,
                    "timestamp_ns": timestamp_ns,
                }
                self._last_price = close_price

                # 更新 KlineBuffer + 计算因子（如果配置了因子）
                ctx = self._build_ctx(bar, timestamp_ns, close_price)

                # BaseStrategy 唯一契约：on_bar(bar, ctx) → Action
                action = self._strategy.on_bar(bar, ctx)
                action_type_str = str(action.action_type)
                self._last_action = action_type_str
                if action_type_str in ("buy", "sell"):
                    self._execute_action(action, close_price)

                self._emit(
                    "bar.processed",
                    {
                        "symbol": self._symbol,
                        "price": close_price,
                        "action": action_type_str,
                        "timestamp": timestamp_ns,
                        "features": ctx.features if ctx is not None else {},
                    },
                )

            except Exception as e:
                logger.error(f"StrategyLoop 错误: {e}", exc_info=True)

            # ponytail: wait 替代 sleep，stop() 可即时唤醒
            self._stop_event.wait(self._interval)

    def _build_ctx(self, bar: dict, timestamp_ns: int, close_price: float) -> Any:
        """构建 StrategyContext：更新 KlineBuffer，计算因子，填充历史序列。"""
        from strategy.base import StrategyContext

        features: dict[str, float] = {}
        closes: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        volumes: list[float] = []

        if self._kline_buffer is not None and self._factor_injector is not None:
            # 用 tick 更新 KlineBuffer（自动处理跨周期收盘）
            self._kline_buffer.push_tick(timestamp_ns, close_price)
            bars = self._kline_buffer.bars()
            # 计算因子最新值
            features = self._factor_injector.compute(bars)
            # 填充历史序列供策略使用（如均线、ATR）
            closes = [float(b["close"]) for b in bars]
            highs = [float(b["high"]) for b in bars]
            lows = [float(b["low"]) for b in bars]
            volumes = [float(b["volume"]) for b in bars]

        return StrategyContext(
            symbol=self._symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            features=features,
            account_equity=self._account_equity,
        )

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
                    self._emit(
                        "order.rejected",
                        {
                            "symbol": self._symbol,
                            "side": side,
                            "quantity": qty,
                            "price": current_price,
                            "reason": reason,
                        },
                    )
                    logger.warning(f"风控拒绝订单: {reason}")
                    return

            # 4. 执行下单
            result = self._adapter.place_order(order_dict)
            self._order_count += 1

            self._emit(
                "order.placed",
                {
                    "symbol": self._symbol,
                    "side": side,
                    "quantity": qty,
                    "price": current_price,
                    "order_id": result.get("order_id", "") if isinstance(result, dict) else "",
                    "confidence": confidence,
                },
            )
            logger.info(f"订单已执行: {order_dict} -> {result}")

        except Exception as e:
            logger.error(f"订单执行失败: {e}")
