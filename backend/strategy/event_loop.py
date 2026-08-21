"""EventDrivenLoop — 完整事件驱动实盘交易循环

替换 StrategyLoop 的 Python 轮询模式，使用:
  1. 事件驱动数据馈送 (adapter WebSocket 更新内部缓存 → 馈送线程读取 → 队列 → 主循环)
  2. axon_quant.agent.SwarmRunner 多 Agent 投票共识
  3. ExecutionPipeline 订单执行管道 (风控→OMS→交易所)
  4. TrajectoryRecorder 决策轨迹记录
  5. LivePortfolio 实时持仓追踪

说明: BinanceAdapter.connect()+subscribe() 启动 WebSocket 并在内部更新
ticker 缓存, get_ticker() 是同步读缓存。因此数据馈送线程以短间隔读取
缓存并投递到线程安全队列, 主循环阻塞等待队列, 无忙等待。

架构:
    adapter WebSocket ──▶ ticker 缓存 ──▶ 馈送线程 ──▶ Queue ──▶ 主循环
                                                                      │
                                                                      ▼
                                                     SwarmRunner.on_bar(bar)
                                       │
                                       ▼
                               多 Trader 投票共识
                                       │
                                       ▼
                               ExecutionPipeline.execute_decision()
                                       │
                              ┌─────────┼──────────┐
                              ▼         ▼          ▼
                          RiskCheck  OMSService  ExchangeAdapter
                              │         │          │
                              └─────────┼──────────┘
                                        ▼
                              LivePortfolio.update_on_fill()
                                        │
                                        ▼
                              TrajectoryRecorder.record_step()
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from typing import Any, Callable

from .agent_traders import StrategyTrader, TraderRegistry
from .execution_pipeline import ExecutionPipeline
from .live_portfolio import LivePortfolio

logger = logging.getLogger(__name__)


class EventDrivenLoop:
    """事件驱动实盘交易循环。

    Args:
        adapter: 交易所适配器 (axon_quant.exchange.*Adapter)
        symbol: 交易对符号
        initial_cash: 初始资金
        risk_engine: 风控引擎 (RiskService)
        event_callback: 事件回调 fn(event_type, data)
        voting: 投票方式 (weighted_majority / unanimous / majority)
        enable_trajectory: 是否记录决策轨迹
        trajectory_dir: 轨迹输出目录
    """

    def __init__(
        self,
        adapter: Any,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
        risk_engine: Any = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        voting: str = "weighted_majority",
        enable_trajectory: bool = True,
        trajectory_dir: str = "output/trajectories",
    ):
        self._adapter = adapter
        self._symbol = symbol
        self._initial_cash = initial_cash
        self._risk_engine = risk_engine
        self._event_callback = event_callback
        self._voting = voting
        self._enable_trajectory = enable_trajectory
        self._trajectory_dir = trajectory_dir

        # 核心组件
        self._portfolio = LivePortfolio(initial_cash=initial_cash)
        self._pipeline = ExecutionPipeline(
            adapter=adapter,
            portfolio=self._portfolio,
            risk_engine=risk_engine,
            event_callback=event_callback,
        )
        self._trader_registry = TraderRegistry()

        # SwarmRunner (延迟初始化)
        self._swarm: Any = None
        self._trajectory_recorder: Any = None

        # 运行状态
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._feed_thread: threading.Thread | None = None

        # 线程安全的 bar 队列: 馈送线程写入, 主循环读取 (替代共享变量, 避免竞态)
        self._bar_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)

        # 统计
        self._bar_count = 0
        self._decision_count = 0
        self._order_count = 0
        self._fill_count = 0
        self._rejected_count = 0
        self._last_price = 0.0
        self._last_decision: dict[str, Any] | None = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def is_running(self) -> bool:
        """是否运行中: 线程已启动且未收到停止信号。"""
        if self._thread is None:
            return False
        if not self._thread.is_alive():
            return False
        return not self._stop_event.is_set()

    @property
    def portfolio(self) -> LivePortfolio:
        return self._portfolio

    @property
    def pipeline(self) -> ExecutionPipeline:
        return self._pipeline

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "symbol": self._symbol,
            "bar_count": self._bar_count,
            "decision_count": self._decision_count,
            "order_count": self._order_count,
            "fill_count": self._fill_count,
            "rejected_count": self._rejected_count,
            "last_price": self._last_price,
            "last_decision": self._last_decision,
            "circuit_broken": self._pipeline.circuit_broken,
            "portfolio": self._portfolio.to_dict(),
        }

    # ─── Trader 管理 ───

    def add_strategy(self, strategy: Any, position_scale: float = 0.1) -> str:
        """添加一个 BaseStrategy 作为 trader。"""
        trader = StrategyTrader(strategy, position_scale=position_scale)
        return self._trader_registry.register(trader)

    def add_trader(self, trader: Any) -> str:
        """添加任意 trader (需实现 decide(bar) -> dict)。"""
        return self._trader_registry.register(trader)

    def remove_trader(self, trader_id: str) -> bool:
        """移除 trader。"""
        return self._trader_registry.unregister(trader_id)

    def _build_swarm(self) -> Any:
        """构建 SwarmRunner。"""
        traders = self._trader_registry.get_all()
        if not traders:
            logger.warning("无 trader, SwarmRunner 返回 None")
            return None

        try:
            from axon_quant.agent import SwarmRunner

            risk_config = {
                "max_position": 1.0,
                "max_daily_loss": 0.1,
                "voting_threshold": 0.5,
            }

            swarm = SwarmRunner(
                traders=traders,
                risk_config=risk_config,
                voting=self._voting,
            )
            logger.info(f"SwarmRunner 已构建: {len(traders)} traders, voting={self._voting}")
            return swarm

        except ImportError:
            logger.error("axon_quant.agent 不可用, 无法创建 SwarmRunner")
            return None

    # ─── 生命周期 ───

    def start(self) -> None:
        """启动事件驱动循环。"""
        if self._trader_registry.__len__() == 0:
            raise RuntimeError("至少需要注册一个 trader")

        # 构建 Swarm
        self._swarm = self._build_swarm()
        if self._swarm is None:
            raise RuntimeError("SwarmRunner 构建失败")

        # 初始化轨迹记录器
        if self._enable_trajectory:
            try:
                from axon_quant.agent import TrajectoryRecorder

                run_id = str(uuid.uuid4())[:8]
                self._trajectory_recorder = TrajectoryRecorder(
                    run_id=run_id,
                    instrument=self._symbol,
                    provider="quantcell",
                    model="swarm_v1",
                    seed=42,
                    output_dir=self._trajectory_dir,
                )
                logger.info(f"TrajectoryRecorder 已初始化: run_id={run_id}")
            except ImportError:
                logger.warning("TrajectoryRecorder 不可用")

        # 连接交易所 (connect + subscribe 后 adapter 内部 WebSocket 开始更新 ticker 缓存)
        self._adapter.connect()
        if hasattr(self._adapter, "subscribe"):
            self._adapter.subscribe([self._symbol])

        # 启动所有 trader
        self._trader_registry.start_all()

        self._stop_event.clear()

        # 启动主循环线程 (阻塞等待队列, 无忙等待)
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        # 启动数据馈送线程: 读取 adapter ticker 缓存并投递到队列
        self._feed_thread = threading.Thread(target=self._run_data_feed, daemon=True)
        self._feed_thread.start()

        logger.info(f"EventDrivenLoop 已启动: {self._symbol}")
        self._emit(
            "loop.started",
            {
                "symbol": self._symbol,
                "traders": len(self._trader_registry),
                "voting": self._voting,
                "portfolio": self._portfolio.to_dict(),
            },
        )

    def stop(self) -> None:
        """停止事件驱动循环。"""
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.error(f"主循环线程未能在 5s 内停止: {self._symbol}")

        if self._feed_thread:
            self._feed_thread.join(timeout=3)
            if self._feed_thread.is_alive():
                logger.error(f"数据馈送线程未能在 3s 内停止: {self._symbol}")

        # 停止所有 trader
        self._trader_registry.stop_all()

        # 断开交易所
        self._adapter.disconnect()

        # 保存轨迹
        if self._trajectory_recorder:
            try:
                self._trajectory_recorder.save()
                self._trajectory_recorder = None
            except Exception as e:
                logger.error(f"保存轨迹失败: {e}")

        logger.info(f"EventDrivenLoop 已停止: {self._symbol}")
        self._emit("loop.stopped", {"symbol": self._symbol, "stats": self.stats})

    # ─── 核心循环 ───

    def _run_event_loop(self) -> None:
        """主事件循环: 阻塞等待队列中的 bar 事件并处理 (无忙等待)。"""
        while not self._stop_event.is_set():
            try:
                # 阻塞等待 bar, 超时后重新检查停止信号
                bar = self._bar_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process_bar(bar)
            except Exception as e:
                logger.error(f"事件循环错误: {e}", exc_info=True)
                self._stop_event.wait(0.5)

    def _run_data_feed(self) -> None:
        """数据馈送线程: 读取 adapter ticker 缓存并投递到队列。

        adapter 的 WebSocket 在内部更新 ticker 缓存, get_ticker() 为同步读。
        这里以短间隔读取缓存, 检测到价格变化时生成 bar 投递到队列。
        """
        last_price = 0.0
        while not self._stop_event.is_set():
            try:
                ticker = None
                if hasattr(self._adapter, "get_ticker"):
                    ticker = self._adapter.get_ticker(self._symbol)
                if ticker:
                    bar = self._ticker_to_bar(ticker)
                    # 仅在价格变化时投递, 避免重复处理同一快照
                    if bar["close"] != last_price:
                        last_price = bar["close"]
                        try:
                            self._bar_queue.put_nowait(bar)
                        except queue.Full:
                            # 队列满说明主循环处理不过来, 丢弃旧快照只保留最新
                            try:
                                self._bar_queue.get_nowait()
                            except queue.Empty:
                                pass
                            self._bar_queue.put_nowait(bar)
                self._stop_event.wait(0.1)
            except Exception as e:
                logger.error(f"数据馈送错误: {e}")
                self._stop_event.wait(1.0)

    def _ticker_to_bar(self, ticker: dict) -> dict[str, Any]:
        """将 ticker 转换为 bar 格式。"""
        close = float(ticker.get("last", ticker.get("price", 0.0)))
        return {
            "open": float(ticker.get("open", close)),
            "high": float(ticker.get("high", close)),
            "low": float(ticker.get("low", close)),
            "close": close,
            "volume": float(ticker.get("volume", 0.0)),
            "symbol": self._symbol,
            "timestamp_ns": int(time.time() * 1_000_000_000),
        }

    def _process_bar(self, bar: dict[str, Any]) -> None:
        """处理单根 bar: 策略评估 + 订单执行。"""
        self._bar_count += 1
        current_price = float(bar.get("close", 0.0))
        self._last_price = current_price

        # 1. 先直接从 TraderRegistry 收集原始决策 (保留 target_position 等扩展字段,
        #    因为 SwarmRunner votes 会丢 target_position / 自定义元数据)
        raw_decisions = self._trader_registry.collect_decisions(bar)
        aggregated_tp = self._trader_registry.aggregate_target_position(raw_decisions)

        # 2. Swarm 投票共识 (action 类型 + confidence 由 Swarm 做 majority / weighted)
        decision = self._swarm.on_bar(bar)
        self._last_decision = decision
        self._decision_count += 1

        # 3. 补齐 symbol / target_position 等扩展字段
        if isinstance(decision, dict):
            decision["symbol"] = self._symbol
            # 若 Swarm 没聚合出 target_position, 用前一步自己聚合的值覆盖
            existing_tp = float(decision.get("target_position", 0.0) or 0.0)
            if existing_tp <= 0 and aggregated_tp > 0:
                decision["target_position"] = aggregated_tp
            # raw_decisions 作为轨迹附加, 便于事后排查每个 trader 的真实意图
            decision["raw_decisions"] = raw_decisions

        # 2. 推送上游
        self._emit(
            "bar.processed",
            {
                "symbol": self._symbol,
                "price": current_price,
                "decision": decision,
                "bar_index": self._bar_count,
            },
        )

        # 3. 执行订单
        result = self._pipeline.execute_decision(decision, current_price)

        if result.accepted:
            self._order_count += 1
            self._fill_count += 1
            self._emit(
                "order.executed",
                {
                    "symbol": self._symbol,
                    "side": result.side,
                    "quantity": result.quantity,
                    "price": result.price,
                    "order_id": result.order_id,
                    "portfolio": self._portfolio.to_dict(),
                },
            )
        elif result.reason not in ("hold", "qty_zero"):
            self._rejected_count += 1
            self._emit(
                "order.rejected",
                {
                    "symbol": self._symbol,
                    "reason": result.reason,
                    "decision": decision,
                },
            )

        # 4. 记录轨迹 (包含执行结果, 保证轨迹完整: bar → 决策 → 执行)
        if self._trajectory_recorder:
            try:
                self._trajectory_recorder.record_step(
                    {
                        "bar": bar,
                        "decision": decision,
                        "execution": result.to_dict(),
                        "timestamp": time.time(),
                    }
                )
            except Exception as e:
                logger.error(f"轨迹记录失败: {e}")

        # 5. 日亏损熔断 — 基于 LivePortfolio 的真实盈亏触发
        try:
            self._pipeline.check_daily_loss_circuit_breaker({self._symbol: current_price})
        except Exception as e:  # pragma: no cover - 防御性分支
            logger.error(f"日亏损熔断检查异常: {e}")

        # 6. 定期推送持仓状态
        if self._bar_count % 10 == 0:
            self._emit(
                "portfolio.update",
                {
                    "symbol": self._symbol,
                    "portfolio": self._portfolio.to_dict(),
                    "bar_count": self._bar_count,
                },
            )

    # ─── 事件 ───

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """发出事件回调。"""
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"事件回调失败 ({event_type}): {e}")

    # ─── 手动触发 ───

    def process_bar(self, bar: dict[str, Any]) -> dict[str, Any]:
        """手动触发单根 bar 处理 (用于测试或手动触发)。"""
        self._process_bar(bar)
        return self.stats
