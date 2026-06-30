# -*- coding: utf-8 -*-
"""基于 axon_quant 的回测引擎适配层

设计原则：
- QuantCell 是 axon_quant 的应用层封装，回测执行逻辑统一走 BacktestLoop
- 本类只负责：管理 BacktestLoop 生命周期、参数验证、结果转换
- 撮合、回放、订单执行等核心逻辑全部下沉到 axon_quant

为什么不自己管 BacktestEngine：
- 之前自己 push_event("market_data") 被 axon_quant 拒绝（unsupported event type）
- BacktestLoop._run_with_axon 已经走对了：只 push order_submitted
- 任何"绕开 BacktestLoop 直接 push 事件"的路径都是错误的
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

try:
    from axon_quant.backtest import BacktestError as _AxonBacktestError
    AXON_AVAILABLE = True
except ImportError:
    AXON_AVAILABLE = False
    _AxonBacktestError = None


class AxonBacktestEngine:
    """axon_quant 回测引擎的 QuantCell 适配层。

    该类**不直接持有** axon_quant.BacktestEngine 实例，
    也不接收 OHLCV DataFrame（因为 axon_quant 不接受 market_data 事件）。

    唯一入口是 `run_with_strategy()`，内部委派给 `BacktestLoop.run()`，
    由 BacktestLoop 负责遍历数据 + 调用策略 + 推送 order_submitted 事件。

    Args:
        config: 配置字典，支持:
            - initial_capital: 初始资金（默认 100000.0）
            - matching_engine: "L1" | "L2" | "L3" | "Impacted"（默认 L1）
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._is_initialized = False

    def initialize(self) -> None:
        """初始化回测引擎（参数校验）"""
        if not AXON_AVAILABLE:
            raise ImportError(
                "axon_quant 未安装或无法导入。"
                "请确保 Python >= 3.14 并安装 axon_quant: "
                "cd /path/to/axon && maturin develop --release"
            )
        if self._config.get("initial_capital", 100000.0) <= 0:
            raise ValueError("initial_capital 必须 > 0")
        self._is_initialized = True

    def run_with_strategy(
        self,
        strategy: Any,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
    ) -> Dict[str, Any]:
        """执行回测 - 委派给 BacktestLoop

        Args:
            strategy: UnifiedStrategy 实例
            data: OHLCV DataFrame，索引为 DatetimeIndex
            symbol: 交易对符号

        Returns:
            结果字典，字段：
            - final_nav: 最终净值
            - total_pnl: 总盈亏
            - max_drawdown: 最大回撤
            - orders_accepted: 被接受的订单数
            - orders_rejected: 被拒绝的订单数
            - fills: 成交笔数
            - total_orders: 策略产生的订单总数
            - events_processed: 引擎处理的事件数
            - duration_secs: 回测耗时

        Raises:
            RuntimeError: 引擎未初始化
            ValueError: 参数错误
            axon_quant.backtest.BacktestError: 撮合错误
        """
        if not self._is_initialized:
            raise RuntimeError("引擎未初始化，请先调用 initialize()")

        if data is None or data.empty:
            raise ValueError("data 不能为空")

        # 延迟导入避免循环依赖
        from backtest.backtest_loop import BacktestLoop

        initial_cash = self._config.get("initial_capital", 100000.0)
        loop = BacktestLoop(initial_cash=initial_cash)

        try:
            result = loop.run(strategy=strategy, data=data, symbol=symbol)
        except _AxonBacktestError as e:
            # 包装为业务异常，附带更多上下文
            raise RuntimeError(
                f"axon_quant 回测执行失败: {e}. "
                f"strategy={type(strategy).__name__}, symbol={symbol}"
            ) from e

        return {
            "initial_capital": initial_cash,
            "final_nav": result.final_nav,
            "total_pnl": result.total_pnl,
            # max_drawdown(USD 绝对值)= nav_peak * (max_drawdown_pct / 100)
            # axon_quant 阶段 B 不暴露 USD 字段,这里用 pct 反算
            "max_drawdown": result.nav_peak * (result.max_drawdown_pct / 100.0),
            # max_drawdown_pct 优先于 max_drawdown(单位:百分比 vs USD 绝对值),
            # formatter 用它,避免误把 USD 差当百分比显示
            "max_drawdown_pct": result.max_drawdown_pct,
            "nav_peak": result.nav_peak,
            "orders_accepted": result.orders_accepted,
            "orders_rejected": result.orders_rejected,
            "fills": result.fills,
            "total_orders": result.total_orders,
            "events_processed": result.events_processed,
            "duration_secs": result.duration_secs,
            # trade-level 指标(由 backtest_loop 收集 fills 配对而成)
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_fees": result.total_fees,
            "trade_count": len(result.trade_records),
            # 序列化 trade records:PyO3 暴露的 TradeRecord 类不一定有 __dict__,
            # 不能直接 vars()(TypeError: vars() argument must have __dict__ attribute);
            # 优先用对象自己的 to_dict() 方法(axon_quant.TradeRecord 暴露),
            # 否则用 __dict__ 直接访问,最后兜底 str()
            "trades": [
                t.to_dict() if hasattr(t, "to_dict") and callable(t.to_dict)
                else (dict(t.__dict__) if hasattr(t, "__dict__") else {"repr": str(t)})
                for t in result.trade_records
            ],
            "equity_curve": [list(p) for p in result.equity_curve],
            # 回测数据时间范围(供 CLI 显示,知道覆盖了哪个时间窗口)
            "data_start_ns": result.data_start_ns,
            "data_end_ns": result.data_end_ns,
            "bar_count": result.bar_count,
        }

    def cleanup(self) -> None:
        """释放引擎资源（占位实现）"""
        self._is_initialized = False

    def add_data(self, df: pd.DataFrame, symbol: str) -> None:
        """**已废弃** — axon_quant 不接受 market_data 事件

        保留此方法仅为兼容性，调用立即抛出 NotImplementedError。
        旧代码应该迁移到 run_with_strategy(strategy, data, symbol)。
        """
        raise NotImplementedError(
            "axon_quant BacktestEngine 不接受 market_data 事件。"
            "请改用 run_with_strategy(strategy=strategy, data=df, symbol=symbol)，"
            "内部会通过 BacktestLoop 推送正确的 order_submitted 事件。"
        )

    def submit_order(self, order_dict: dict, timestamp_ns: int) -> None:
        """**已废弃** — 请通过 strategy.on_bar() 返回订单"""
        raise NotImplementedError(
            "axon_quant 不支持直接推送 order_submitted。"
            "请在 UnifiedStrategy.on_bar() 中返回 Order 列表，"
            "BacktestLoop 会自动推送给 axon_quant 引擎。"
        )

    def run(self) -> dict:
        """**已废弃** — 请使用 run_with_strategy()"""
        raise NotImplementedError(
            "请使用 run_with_strategy(strategy, data, symbol)，"
            "传入策略实例和 OHLCV DataFrame。"
        )


__all__ = ["AxonBacktestEngine"]
