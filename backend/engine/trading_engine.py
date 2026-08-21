"""TradingEngine — 核心交易引擎（向后兼容门面）

内部委托给 StrategyManager，保持原有 API 兼容性。
"""

from __future__ import annotations

import logging
import time
import uuid
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from .config import EngineConfig

if TYPE_CHECKING:
    import pandas as pd

    from backtest.backtest_loop import BacktestResult, RuleStrategy

logger = logging.getLogger(__name__)

# WebSocket 事件推送 topic（保留以保持兼容性）
_WS_TOPIC = "strategy"


@lru_cache(maxsize=1)
def get_risk_service() -> Any:
    """获取 RiskService 单例（包装 axon_bridge.risk.DefaultRiskEngine）。"""
    from services.risk_service import RiskService

    return RiskService()


def _ws_emit(event_type: str, data: dict[str, Any]) -> None:
    """线程安全地将事件推送到 WebSocket 消息队列。"""
    try:
        from websocket.manager import manager

        if manager.message_queue is None:
            return
        message = {
            "type": event_type,
            "topic": _WS_TOPIC,
            "timestamp": int(time.time() * 1000),
            "data": data,
        }
        manager.message_queue.put_nowait(message)
    except Exception:
        # WebSocket 不可用时不阻塞交易逻辑
        pass


_trading_engine_instance: TradingEngine | None = None


def get_trading_engine(config: EngineConfig | None = None) -> TradingEngine:
    """获取 TradingEngine 单例（向后兼容，内部委托给 StrategyManager）。"""
    global _trading_engine_instance
    if _trading_engine_instance is None:
        _trading_engine_instance = TradingEngine(config=config)
    return _trading_engine_instance


class TradingEngine:
    """核心交易引擎（向后兼容门面）

    所有方法内部委托给 StrategyManager，保持原有 API 签名不变。
    """

    def __init__(self, config: EngineConfig | None = None):
        if config is None:
            config = EngineConfig(exchange="binance", trading_mode="paper")
        self._config = config
        # ponytail: 缓存 exchange adapter，避免每次 property 访问重建
        self._exchange_cache: Any | None = None

        # 使用已有的 worker_system 单例，避免重复初始化
        from worker.strategy_manager import worker_system

        self._manager = worker_system

        # 维护自己的策略状态（保持向后兼容）
        self._strategies: dict[str, Any] = {}

        logger.info(f"TradingEngine 已初始化（委托模式）: exchange={config.exchange}, mode={config.trading_mode}")

    @property
    def exchange(self) -> Any | None:
        """返回 exchange adapter（缓存）"""
        if self._exchange_cache is not None:
            return self._exchange_cache
        # 延迟导入以避免循环依赖
        try:
            from axon_bridge import BinanceAdapter, ExchangeConfig

            exchange_config = ExchangeConfig(
                exchange_id=self._config.exchange,
                testnet=self._config.trading_mode == "paper",
            )
            self._exchange_cache = BinanceAdapter(exchange_config)
            return self._exchange_cache
        except Exception:
            return None

    @property
    def risk_engine(self) -> Any | None:
        """返回 risk engine"""
        try:
            return get_risk_service()
        except Exception:
            return None

    def engine_status(self) -> dict[str, Any]:
        """返回引擎概览状态"""
        running = sum(1 for rt in self._strategies.values() if rt.get("status") == "running")
        return {
            "exchange": self._config.exchange,
            "mode": self._config.trading_mode,
            "exchange_connected": self.exchange is not None,
            "risk_available": self.risk_engine is not None,
            "total_strategies": len(self._strategies),
            "running_strategies": running,
        }

    def register_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        mode: str = "paper",
    ) -> str:
        """注册策略（内存级别，无持久化）"""
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = {
            "strategy": strategy,
            "symbols": list(symbols),
            "strategy_name": strategy_name or strategy.__class__.__name__,
            "params": params or {},
            "mode": mode,
            "status": "stopped",
            "order_count": 0,
            "fill_count": 0,
            "rejected_count": 0,
            "last_price": 0.0,
            "last_action": None,
            "loop": None,
            "started_at": 0.0,
            "use_event_driven": False,
            "portfolio_state": {},
        }
        logger.info(f"策略已注册: {sid} {symbols}")
        _ws_emit(
            "strategy.registered",
            {
                "strategy_id": sid,
                "symbols": symbols,
                "strategy_name": strategy_name,
                "mode": mode,
            },
        )
        return sid

    def start_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        account_equity: float = 100_000.0,
        mode: str = "paper",
        use_event_driven: bool = True,
    ) -> str:
        """启动策略

        Args:
            strategy: 策略实例 (BaseStrategy 或任意 trader)
            symbols: 交易对列表
            strategy_name: 策略名称
            params: 策略参数
            account_equity: 初始资金
            mode: 交易模式
            use_event_driven: 是否使用事件驱动循环 (默认 True)
        """
        if self.exchange is None:
            msg = "exchange adapter 不可用，无法启动实盘策略。请确保 axon_quant.exchange 已安装并配置正确。"
            raise RuntimeError(msg)

        sid = self.register_strategy(strategy, symbols, strategy_name, params, mode=mode)
        runtime = self._strategies[sid]

        # 创建事件回调，更新 runtime 计数
        def event_callback(event_type: str, data: dict[str, Any]) -> None:
            if event_type == "order.placed":
                runtime["order_count"] += 1
                runtime["last_price"] = data.get("price", runtime["last_price"])
                runtime["last_action"] = data.get("side", "").lower()
            elif event_type == "order.rejected":
                runtime["rejected_count"] += 1
            elif event_type == "order.filled":
                runtime["fill_count"] += 1
            elif event_type == "bar.processed":
                runtime["last_price"] = data.get("price", runtime["last_price"])
                decision = data.get("decision", {})
                if isinstance(decision, dict):
                    runtime["last_action"] = decision.get("final_action", runtime["last_action"]).lower()
            elif event_type == "portfolio.update":
                # 更新持仓状态到 runtime
                portfolio = data.get("portfolio", {})
                runtime["portfolio_state"] = portfolio
            # 附加 strategy_id 后广播
            data["strategy_id"] = sid
            _ws_emit(event_type, data)

        if use_event_driven:
            # —— 事件驱动循环 (默认) ——
            from strategy.event_loop import EventDrivenLoop

            loop = EventDrivenLoop(
                adapter=self.exchange,
                symbol=symbols[0],
                initial_cash=account_equity,
                risk_engine=self.risk_engine,
                event_callback=event_callback,
            )

            # 将策略包装为 trader 并添加到循环
            from strategy.agent_traders import StrategyTrader

            trader = StrategyTrader(strategy)
            loop.add_trader(trader)

            loop.start()
        else:
            # —— 旧版轮询循环 (向后兼容) ——
            from strategy.loop import StrategyLoop

            loop = StrategyLoop(
                adapter=self.exchange,
                strategy=strategy,
                symbol=symbols[0],
                risk_engine=self.risk_engine,
                account_equity=account_equity,
                event_callback=event_callback,
            )
            loop.start()

        runtime["loop"] = loop
        runtime["status"] = "running"
        runtime["started_at"] = time.monotonic()
        runtime["use_event_driven"] = use_event_driven

        logger.info(f"策略已启动: {sid} {symbols} (event_driven={use_event_driven})")
        _ws_emit(
            "strategy.started",
            {
                "strategy_id": sid,
                "symbols": symbols,
                "strategy_name": runtime["strategy_name"],
                "mode": mode,
                "use_event_driven": use_event_driven,
            },
        )
        return sid

    # ─── 多智能体编排入口 (LLM Agent + 规则策略 Swarm) ──────────────────

    def start_swarm(
        self,
        *,
        symbols: list[str],
        strategies: list[Any] | None = None,
        llm_agents: list[tuple[Any, str]] | None = None,
        strategy_name: str = "swarm",
        account_equity: float = 100_000.0,
        mode: str = "paper",
        position_scale: float = 0.1,
        risk_config: dict[str, Any] | None = None,
    ) -> str:
        """启动一个多智能体 Swarm。

        这是 TradingEngine 对接 LLM Agent 交易链路的统一入口。
        内部通过 ``SwarmOrchestrator`` 组装 EventDrivenLoop。

        Args:
            symbols: 交易对列表 (目前只使用第一个)
            strategies: 规则策略列表 (元素为 BaseStrategy 实例)
            llm_agents: LLM Agent 列表, 每项为 ``(react_agent, agent_id)``;
                agent_id 可留空, 但建议传以便识别。
            strategy_name: 展示名 (用于记录与广播)
            account_equity: 初始资金
            mode: paper / live
            position_scale: 规则策略的默认仓位比例
            risk_config: 传给 RiskService 的覆盖配置, 如
                ``{"max_order_value": 30000, "max_daily_loss": 5000}``

        Returns:
            strategy_id (可通过 list_strategies / stop_strategy 管理)
        """
        from strategy.swarm_orchestrator import SwarmOrchestrator

        if self.exchange is None:
            msg = "exchange adapter 不可用，无法启动 swarm。请确保 axon_quant.exchange 已安装并配置正确。"
            raise RuntimeError(msg)
        if not symbols:
            raise ValueError("symbols 不能为空")

        # 先注册占位, 保持 list_strategies 一致
        class _SwarmAnchor:
            """标记用, 表明此 runtime 是由 start_swarm 创建的多智能体集合。"""

            def on_bar(self, bar):  # pragma: no cover - 从未真正调用
                from axon_bridge import Action, ActionType

                return Action(ActionType.Hold, 0.0, 0.0, "swarm_anchor", 0)

        sid = self.register_strategy(
            _SwarmAnchor(), symbols, strategy_name or "swarm", params=risk_config or {}, mode=mode
        )
        runtime = self._strategies[sid]

        def event_callback(event_type: str, data: dict[str, Any]) -> None:
            if event_type == "order.placed":
                runtime["order_count"] += 1
                runtime["last_price"] = data.get("price", runtime["last_price"])
                runtime["last_action"] = data.get("side", "").lower()
            elif event_type == "order.rejected":
                runtime["rejected_count"] += 1
            elif event_type == "order.filled":
                runtime["fill_count"] += 1
            elif event_type == "bar.processed":
                runtime["last_price"] = data.get("price", runtime["last_price"])
                decision = data.get("decision", {})
                if isinstance(decision, dict):
                    runtime["last_action"] = decision.get("final_action", runtime["last_action"]).lower()
            elif event_type == "portfolio.update":
                runtime["portfolio_state"] = data.get("portfolio", {})
            data["strategy_id"] = sid
            _ws_emit(event_type, data)

        orch = SwarmOrchestrator(
            adapter=self.exchange,
            symbol=symbols[0],
            initial_cash=account_equity,
            voting="weighted_majority",
            enable_trajectory=True,
            event_callback=event_callback,
        )

        for s in strategies or []:
            orch.add_strategy(s, position_scale=position_scale)

        for item in llm_agents or []:
            if isinstance(item, tuple):
                agent, agent_id = item[0], item[1] if len(item) > 1 else ""
            else:
                agent, agent_id = item, ""
            orch.add_llm_agent(agent, id=agent_id)

        # 绑定 RiskService: 优先使用用户提供的 risk_config, 否则用引擎自带
        if risk_config or self.risk_engine is None:
            orch.attach_risk_service(risk_config=risk_config or {})
        else:
            orch.attach_risk_service(instance=self.risk_engine)

        loop = orch.start()
        runtime["loop"] = loop
        runtime["orchestrator"] = orch
        runtime["status"] = "running"
        runtime["started_at"] = time.monotonic()
        runtime["use_event_driven"] = True
        runtime["is_swarm"] = True
        runtime["num_strategies"] = len(strategies or [])
        runtime["num_llm_agents"] = len(llm_agents or [])

        logger.info(
            f"Swarm 已启动: {sid} {symbols} ({runtime['num_strategies']} 策略 + {runtime['num_llm_agents']} LLM Agent)"
        )
        _ws_emit(
            "swarm.started",
            {
                "strategy_id": sid,
                "symbols": symbols,
                "strategy_name": strategy_name,
                "mode": mode,
                "num_strategies": runtime["num_strategies"],
                "num_llm_agents": runtime["num_llm_agents"],
            },
        )
        return sid

    def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        if strategy_id not in self._strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False

        runtime = self._strategies[strategy_id]
        if runtime.get("loop") is not None:
            runtime["loop"].stop()
        runtime["status"] = "stopped"
        logger.info(f"策略已停止: {strategy_id}")
        _ws_emit(
            "strategy.stopped",
            {
                "strategy_id": strategy_id,
                "strategy_name": runtime["strategy_name"],
            },
        )
        return True

    def get_strategy_status(self, strategy_id: str) -> dict[str, Any] | None:
        """获取策略状态"""
        runtime = self._strategies.get(strategy_id)
        if runtime is None:
            return None
        # 从 loop 同步最新统计
        loop = runtime.get("loop")
        if loop is not None and hasattr(loop, "stats"):
            stats = loop.stats
            runtime["order_count"] = stats.get("order_count", runtime["order_count"])
            runtime["fill_count"] = stats.get("fill_count", runtime["fill_count"])
            runtime["rejected_count"] = stats.get("rejected_count", runtime["rejected_count"])
            runtime["last_price"] = stats.get("last_price", runtime["last_price"])
            runtime["last_action"] = stats.get("last_action", runtime["last_action"])

            # EventDrivenLoop 额外信息
            if hasattr(loop, "portfolio") and loop.portfolio:
                runtime["portfolio_state"] = loop.portfolio.to_dict()
        # 计算运行时间
        duration = time.monotonic() - runtime["started_at"] if runtime["started_at"] > 0 else 0
        return {
            "strategy_id": strategy_id,
            "strategy_name": runtime["strategy_name"],
            "symbols": runtime["symbols"],
            "status": runtime["status"],
            "mode": runtime["mode"],
            "started_at": runtime["started_at"],
            "duration_secs": round(duration, 1),
            "order_count": runtime["order_count"],
            "fill_count": runtime["fill_count"],
            "rejected_count": runtime["rejected_count"],
            "last_action": runtime["last_action"],
            "last_price": runtime["last_price"],
            "use_event_driven": runtime.get("use_event_driven", False),
            "portfolio_state": runtime.get("portfolio_state", {}),
            "circuit_broken": (getattr(loop, "pipeline", None) is not None and loop.pipeline.circuit_broken)
            if loop
            else False,
        }

    def list_strategies(self) -> list[dict]:
        """列出所有策略"""
        return [self.get_strategy_status(sid) or {"strategy_id": sid, "status": "unknown"} for sid in self._strategies]

    def run_backtest(
        self,
        strategy: RuleStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
    ) -> BacktestResult:
        """运行回测（委托给 StrategyManager）"""
        return self._manager.run_backtest(strategy, data, symbol, initial_cash)
