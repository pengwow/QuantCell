"""Agent Traders — SwarmRunner 兼容的交易者适配器

axon_quant.agent.SwarmRunner 要求每个 trader 实现 decide(bar: dict) -> dict。
本模块将 QuantCell 现有的 BaseStrategy 包装为 Swarm 兼容的 trader，
同时提供 LLM 驱动的 ReActTrader。

所有 trader 返回格式:
    {
        "action": "buy" | "sell" | "hold",
        "confidence": 0.0 ~ 1.0,
        "reasoning": "策略逻辑描述",
        "target_position": 0.0 ~ 1.0,  # 可选
    }
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class StrategyTrader:
    """将 BaseStrategy 适配为 SwarmRunner 兼容的 trader。

    用法:
        strategy = DualEMACrossover(config)
        trader = StrategyTrader(strategy, id="dual_ema_1")
        decision = trader.decide(bar_dict)
    """

    def __init__(self, strategy: Any, id: str = "", position_scale: float = 0.1):
        self._strategy = strategy
        self.id = id or strategy.__class__.__name__.lower()
        self._position_scale = position_scale
        self._last_action: str = "hold"
        self._last_confidence: float = 0.5

    def decide(self, bar: dict) -> dict:
        """调用策略 on_bar 并转换为 Swarm 兼容格式。"""
        try:
            # 确保 bar 有正确的键
            normalized_bar = {
                "open": float(bar.get("open", 0)),
                "high": float(bar.get("high", 0)),
                "low": float(bar.get("low", 0)),
                "close": float(bar.get("close", 0)),
                "volume": float(bar.get("volume", 0)),
                "symbol": bar.get("symbol", "BTCUSDT"),
                "timestamp_ns": bar.get("timestamp_ns", int(time.time() * 1e9)),
            }

            # 调用策略
            action = self._strategy.on_bar(normalized_bar)
            action_type = str(action.action_type).lower() if hasattr(action, "action_type") else str(action).lower()
            confidence = float(getattr(action, "confidence", 0.5) or 0.5)
            target_position = float(getattr(action, "target_position", 0.0) or 0.0)

            # 转换为 Swarm 格式
            if action_type in ("buy", "Buy"):
                sw_action = "buy"
            elif action_type in ("sell", "Sell"):
                sw_action = "sell"
            else:
                sw_action = "hold"

            # 若策略没给 target_position, 用 confidence * position_scale
            if target_position == 0 and sw_action != "hold":
                target_position = confidence * self._position_scale

            self._last_action = sw_action
            self._last_confidence = confidence

            return {
                "action": sw_action,
                "confidence": confidence,
                "reasoning": f"{self._strategy.__class__.__name__} 发出 {sw_action} 信号",
                "target_position": target_position,
            }

        except Exception as e:
            logger.error(f"StrategyTrader {self.id} 决策失败: {e}")
            return {
                "action": "hold",
                "confidence": 0.0,
                "reasoning": f"error: {e}",
                "target_position": 0.0,
            }

    def on_start(self) -> None:
        """启动策略。"""
        if hasattr(self._strategy, "on_start"):
            self._strategy.on_start()

    def on_stop(self) -> None:
        """停止策略。"""
        if hasattr(self._strategy, "on_stop"):
            self._strategy.on_stop()


class ReActTrader:
    """LLM 驱动的 ReAct Trader。

    使用 axon_quant.llm.ReActAgent 的决策循环:
        observation → LLM推理 → 工具调用 → 决策

    由于 ReActAgent 需要 llm_provider 和 tools，
    此 trader 接受一个预配置的 ReActAgent 实例。

    用法:
        from axon_quant.llm import ReActAgent
        llm_provider = lambda prompt: call_ollama(prompt)
        agent = ReActAgent(llm_provider=llm_provider, tools=[])
        trader = ReActTrader(agent, id="llm_1")
        decision = trader.decide(bar_dict)
    """

    def __init__(
        self,
        react_agent: Any = None,
        id: str = "llm_trader",
        llm_provider: Any = None,
        tools: list[dict[str, Any]] | None = None,
        trajectory_recorder: Any = None,
    ):
        self.id = id
        self._agent = react_agent
        self._trajectory_recorder = trajectory_recorder
        self._history: list[dict[str, Any]] = []
        # LLM 上下文历史最大长度, 防止 prompt 无限膨胀
        self._max_history = 20

        # 若无预配置 agent, 尝试从参数创建
        if self._agent is None and llm_provider is not None:
            try:
                from axon_quant.llm import ReActAgent

                self._agent = ReActAgent(
                    llm_provider=llm_provider,
                    tools=tools or [],
                    trajectory_recorder=trajectory_recorder,
                )
            except Exception as e:
                logger.warning(f"无法创建 ReActAgent: {e}, LLM trader 将返回 hold")

    def decide(self, bar: dict) -> dict:
        """LLM 决策单根 bar。"""
        if self._agent is None:
            return {
                "action": "hold",
                "confidence": 0.0,
                "reasoning": "no_llm_agent",
                "target_position": 0.0,
            }

        try:
            observation = self._build_observation(bar)
            # 传历史快照, 避免引用被后续 append 篡改
            step_result = self._agent.run_step(list(self._history), observation)

            # 维护历史上下文: 追加本轮 observation 与结果, 供 LLM 获得连续性
            self._history.append({"observation": observation, "result": step_result})
            # 限制历史长度, 防止 prompt 无限膨胀
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

            # 解析 step_result
            action = step_result.get("action", {})
            if isinstance(action, dict):
                tool_name = action.get("tool", "")
                tool_args = action.get("args", {})

                # 将工具调用映射为交易决策
                action_type = self._map_tool_to_action(tool_name, tool_args)
                confidence = self._estimate_confidence(step_result)

                return {
                    "action": action_type,
                    "confidence": confidence,
                    "reasoning": step_result.get("thought", "")[:200],
                    "target_position": float(tool_args.get("target_position", confidence * 0.1) or 0.0),
                }
            else:
                return {
                    "action": "hold",
                    "confidence": 0.5,
                    "reasoning": str(step_result.get("thought", ""))[:200],
                    "target_position": 0.0,
                }

        except Exception as e:
            logger.error(f"ReActTrader {self.id} 决策失败: {e}")
            return {
                "action": "hold",
                "confidence": 0.0,
                "reasoning": f"error: {e}",
                "target_position": 0.0,
            }

    def _build_observation(self, bar: dict) -> str:
        """构建 LLM observation 文本。"""
        return (
            f"Market data: O={bar.get('open', 0):.2f} H={bar.get('high', 0):.2f} "
            f"L={bar.get('low', 0):.2f} C={bar.get('close', 0):.2f} "
            f"V={bar.get('volume', 0):.2f} Symbol={bar.get('symbol', 'BTCUSDT')}"
        )

    def _map_tool_to_action(self, tool_name: str, tool_args: dict) -> str:
        """将 ReAct 工具调用映射为交易 action。"""
        tool_action_map = {
            "place_order": tool_args.get("side", "hold"),
            "buy": "buy",
            "sell": "sell",
            "hold": "hold",
            "do_nothing": "hold",
        }
        return tool_action_map.get(tool_name, "hold")

    def _estimate_confidence(self, step_result: dict) -> float:
        """根据 step_result 估算置信度。"""
        # 简化版: 基于 thought 长度和是否有工具调用来估算
        thought = step_result.get("thought", "")
        action = step_result.get("action", {})
        base_conf = 0.6 if thought else 0.3
        if action and isinstance(action, dict) and action.get("tool"):
            base_conf += 0.15
        return min(base_conf, 1.0)

    def on_start(self) -> None:
        self._history.clear()

    def on_stop(self) -> None:
        pass


class EnsembleTrader:
    """Ensemble 策略适配器 — 包装 axon_quant.ensemble.EnsembleManager。

    将 EnsembleManager 的 predict() 输出转换为 Swarm 兼容的决策。
    """

    def __init__(self, ensemble_manager: Any, id: str = "ensemble"):
        self.id = id
        self._ensemble = ensemble_manager

    def decide(self, bar: dict) -> dict:
        """Ensemble 决策。"""
        try:
            if self._ensemble is None:
                return {
                    "action": "hold",
                    "confidence": 0.0,
                    "reasoning": "no_ensemble",
                    "target_position": 0.0,
                }

            observation = self._bar_to_observation(bar)
            probs = self._ensemble.predict(observation)

            # probs 格式: {"Buy": 0.6, "Hold": 0.2, "Sell": 0.2} (或类似)
            if hasattr(probs, "__dict__"):
                probs_dict = vars(probs)
            elif isinstance(probs, dict):
                probs_dict = probs
            else:
                probs_dict = {}

            buy_prob = float(probs_dict.get("Buy", probs_dict.get("buy", 0.0)))
            sell_prob = float(probs_dict.get("Sell", probs_dict.get("sell", 0.0)))
            hold_prob = float(probs_dict.get("Hold", probs_dict.get("hold", 0.0)))

            if buy_prob >= sell_prob and buy_prob >= hold_prob:
                return {
                    "action": "buy",
                    "confidence": buy_prob,
                    "reasoning": f"ensemble Buy={buy_prob:.2f}",
                    "target_position": buy_prob * 0.1,
                }
            elif sell_prob > buy_prob and sell_prob >= hold_prob:
                return {
                    "action": "sell",
                    "confidence": sell_prob,
                    "reasoning": f"ensemble Sell={sell_prob:.2f}",
                    "target_position": -sell_prob * 0.1,
                }
            else:
                return {
                    "action": "hold",
                    "confidence": max(buy_prob, sell_prob, hold_prob),
                    "reasoning": f"ensemble Hold={hold_prob:.2f}",
                    "target_position": 0.0,
                }

        except Exception as e:
            logger.error(f"EnsembleTrader {self.id} 决策失败: {e}")
            return {
                "action": "hold",
                "confidence": 0.0,
                "reasoning": f"error: {e}",
                "target_position": 0.0,
            }

    def _bar_to_observation(self, bar: dict) -> dict:
        """转换 bar 为 Ensemble observation。"""
        return {
            "open": float(bar.get("open", 0)),
            "high": float(bar.get("high", 0)),
            "low": float(bar.get("low", 0)),
            "close": float(bar.get("close", 0)),
            "volume": float(bar.get("volume", 0)),
        }

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass


class TraderRegistry:
    """Trader 注册表 — 管理多个 trader 的生命周期。"""

    def __init__(self):
        self._traders: dict[str, Any] = {}

    def register(self, trader: Any) -> str:
        """注册一个 trader, 返回 id。"""
        trader_id = getattr(trader, "id", "") or str(len(self._traders))
        self._traders[trader_id] = trader
        logger.info(f"Trader 已注册: {trader_id} ({type(trader).__name__})")
        return trader_id

    def unregister(self, trader_id: str) -> bool:
        """注销 trader。"""
        if trader_id in self._traders:
            trader = self._traders.pop(trader_id)
            if hasattr(trader, "on_stop"):
                trader.on_stop()
            logger.info(f"Trader 已注销: {trader_id}")
            return True
        return False

    def get_all(self) -> list[Any]:
        """获取所有 trader。"""
        return list(self._traders.values())

    def start_all(self) -> None:
        """启动所有 trader。"""
        for trader in self._traders.values():
            if hasattr(trader, "on_start"):
                trader.on_start()

    def stop_all(self) -> None:
        """停止所有 trader。"""
        for trader in self._traders.values():
            if hasattr(trader, "on_stop"):
                trader.on_stop()

    def collect_decisions(self, bar: dict[str, Any]) -> list[dict[str, Any]]:
        """直接调用所有 trader.decide(bar) 并返回原始决策列表。

        说明: axon_quant.agent.SwarmRunner 在聚合 votes 时会丢弃
        `target_position` 等非白名单字段, 因此需要在 SwarmRunner 外
        额外收集决策, 以便正确计算目标仓位。
        """
        results: list[dict[str, Any]] = []
        for trader in self._traders.values():
            try:
                d = trader.decide(bar) if hasattr(trader, "decide") else None
                if isinstance(d, dict):
                    d.setdefault("agent_id", getattr(trader, "id", ""))
                    results.append(d)
            except Exception as e:  # pragma: no cover - 防御性分支
                logger.error(f"Trader {getattr(trader, 'id', '?')} 决策失败: {e}")
        return results

    def aggregate_target_position(self, decisions: list[dict[str, Any]]) -> float:
        """按 confidence 加权聚合 target_position。"""
        total_conf = 0.0
        weighted = 0.0
        for d in decisions:
            if not isinstance(d, dict):
                continue
            c = float(d.get("confidence", 0.0) or 0.0)
            tp = float(d.get("target_position", 0.0) or 0.0)
            weighted += c * tp
            total_conf += c
        if total_conf <= 0:
            return 0.0
        return round(weighted / total_conf, 6)

    def __len__(self) -> int:
        return len(self._traders)
