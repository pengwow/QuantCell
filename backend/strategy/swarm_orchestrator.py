"""SwarmOrchestrator — 规则策略 + LLM Agent 多智能体交易编排器

将 QuantCell 的各类能力 (BaseStrategy、ReActAgent、自定义 Trader)
统一按模板装载到 EventDrivenLoop 里, 完成:
    1. 规则策略集 (单/多) 注册
    2. LLM Trader (ReActTrader) 注册
    3. 风控引擎 (RiskService) 绑定
    4. EventDrivenLoop 构建 + 启动/停止

一句话入口:
    orch = SwarmOrchestrator.from_config(config)
    orch.start()

用户侧不需要自己手动接 EventDrivenLoop / TraderRegistry / SwarmRunner。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from services.risk_service import RiskService

from .agent_traders import ReActTrader, StrategyTrader, TraderRegistry
from .event_loop import EventDrivenLoop

logger = logging.getLogger(__name__)


# ===================================================================
# 配置数据类
# ===================================================================


@dataclass
class StrategySpec:
    """一个规则策略的配置。"""

    strategy: Any
    position_scale: float = 0.1
    weight: float = 1.0  # 预留: SwarmRunner.weighted_majority 加权


@dataclass
class LLMAgentSpec:
    """一个 LLM Agent (ReActAgent) 的配置。

    Args:
        react_agent: axon_quant.llm.ReactAgent 实例 (任意实现了 run_step(history, obs) 的对象)
        id: 在 Swarm 内的唯一标识, 默认自动生成
        weight: 预留投票权重
    """

    react_agent: Any
    id: str = ""
    weight: float = 1.0


@dataclass
class OrchestratorConfig:
    """SwarmOrchestrator 配置。

    Args:
        adapter: 交易所适配器 (BinanceAdapter / MockAdapter)
        symbol: 交易对
        initial_cash: 初始资金 (USD)
        strategies: 规则策略列表
        llm_agents: LLM Agent 列表
        risk_config: 传入 RiskService 的 dict 配置 (max_order_value / max_daily_loss 等)
        voting: SwarmRunner 投票策略, 默认 weighted_majority
        enable_trajectory: 是否写轨迹文件到磁盘
        event_callback: 全局事件回调 fn(event_type, data)
    """

    adapter: Any = None
    symbol: str = "BTCUSDT"
    initial_cash: float = 100_000.0
    strategies: list[StrategySpec] = field(default_factory=list)
    llm_agents: list[LLMAgentSpec] = field(default_factory=list)
    risk_config: dict[str, Any] = field(default_factory=dict)
    voting: str = "weighted_majority"
    enable_trajectory: bool = True
    trajectory_dir: str = "output/trajectories"
    event_callback: Any = None


# ===================================================================
# Orchestrator
# ===================================================================


class SwarmOrchestrator:
    """多智能体交易编排器。

    用法 1 — 程序化构造:
        orch = SwarmOrchestrator(adapter, symbol="BTCUSDT", initial_cash=100_000)
        orch.add_strategy(DualEMACrossover())
        orch.add_llm_agent(my_react_agent, id="ollama-qwen")
        orch.attach_risk_service(risk_config={"max_order_value": 30000})
        loop = orch.build()
        loop.start()

    用法 2 — 从配置一次性构建:
        orch = SwarmOrchestrator.from_config(cfg)
        orch.start()
    """

    def __init__(
        self,
        adapter: Any = None,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
        voting: str = "weighted_majority",
        enable_trajectory: bool = True,
        trajectory_dir: str = "output/trajectories",
        event_callback: Any = None,
    ):
        self._adapter = adapter
        self._symbol = symbol
        self._initial_cash = initial_cash
        self._voting = voting
        self._enable_trajectory = enable_trajectory
        self._trajectory_dir = trajectory_dir
        self._event_callback = event_callback

        self._strategy_specs: list[StrategySpec] = []
        self._llm_specs: list[LLMAgentSpec] = []
        self._risk_service: RiskService | None = None
        self._loop: EventDrivenLoop | None = None

    # ─── Builder API ────────────────────────────────────────────────

    def add_strategy(
        self,
        strategy: Any,
        *,
        position_scale: float = 0.1,
        weight: float = 1.0,
    ) -> SwarmOrchestrator:
        """注册一个规则策略 (需实现 on_bar(bar) -> Action)。"""
        self._strategy_specs.append(StrategySpec(strategy=strategy, position_scale=position_scale, weight=weight))
        return self

    def add_llm_agent(
        self,
        react_agent: Any,
        *,
        id: str = "",
        weight: float = 1.0,
    ) -> SwarmOrchestrator:
        """注册一个 LLM Agent (需实现 run_step(history, observation))。"""
        self._llm_specs.append(LLMAgentSpec(react_agent=react_agent, id=id, weight=weight))
        return self

    def attach_risk_service(
        self,
        risk_config: dict[str, Any] | None = None,
        instance: RiskService | None = None,
    ) -> SwarmOrchestrator:
        """绑定 RiskService (实例优先, 否则按 config 创建)。"""
        if instance is not None:
            self._risk_service = instance
        else:
            try:
                self._risk_service = RiskService(risk_config or {})
            except RuntimeError as e:  # axon_quant 不可用时降级为 None
                logger.warning(f"RiskService 不可用, 将仅使用本地风控: {e}")
                self._risk_service = None
        return self

    @classmethod
    def from_config(cls, cfg: OrchestratorConfig) -> SwarmOrchestrator:
        """从配置对象一次性构造已绑定所有组件的 Orchestrator。"""
        orch = cls(
            adapter=cfg.adapter,
            symbol=cfg.symbol,
            initial_cash=cfg.initial_cash,
            voting=cfg.voting,
            enable_trajectory=cfg.enable_trajectory,
            trajectory_dir=cfg.trajectory_dir,
            event_callback=cfg.event_callback,
        )
        for s in cfg.strategies:
            orch.add_strategy(s.strategy, position_scale=s.position_scale, weight=s.weight)
        for a in cfg.llm_agents:
            orch.add_llm_agent(a.react_agent, id=a.id, weight=a.weight)
        orch.attach_risk_service(cfg.risk_config or None)
        return orch

    # ─── Build / Run ────────────────────────────────────────────────

    def build(self) -> EventDrivenLoop:
        """构建 EventDrivenLoop 并装载所有 trader / 风控。

        Returns:
            已装配好的 EventDrivenLoop, 调用方可以 start() 或手动 process_bar()
        """
        from axon_bridge import SwarmRunner

        loop = EventDrivenLoop(
            adapter=self._adapter,
            symbol=self._symbol,
            initial_cash=self._initial_cash,
            risk_engine=self._risk_service,
            event_callback=self._event_callback,
            voting=self._voting,
            enable_trajectory=self._enable_trajectory,
            trajectory_dir=self._trajectory_dir,
        )

        # 装载规则策略
        for spec in self._strategy_specs:
            loop.add_strategy(spec.strategy, position_scale=spec.position_scale)

        # 装载 LLM Agent 为 ReActTrader
        for spec in self._llm_specs:
            react_agent = spec.react_agent
            trader = ReActTrader(react_agent=react_agent, id=spec.id)
            loop.add_trader(trader)

        # 保证 SwarmRunner 已构建 (测试直接 process_bar 时需要, 否则要 start() 触发)
        traders = loop._trader_registry.get_all()
        if traders:
            loop._swarm = SwarmRunner(traders=traders)
        return loop

    @property
    def loop(self) -> EventDrivenLoop | None:
        """返回已构建的 loop (build 后可用)。"""
        return self._loop

    def start(self) -> EventDrivenLoop:
        """构建并启动实盘循环, 返回 loop 引用以便外部检查状态。"""
        self._loop = self.build()
        self._loop.start()
        return self._loop

    def stop(self) -> None:
        """停止实盘循环。"""
        if self._loop is not None:
            self._loop.stop()
            self._loop = None

    @property
    def stats(self) -> dict[str, Any]:
        """代理到 EventDrivenLoop.stats, 便于外层监控。"""
        if self._loop is None:
            return {"status": "not_started"}
        return self._loop.stats
