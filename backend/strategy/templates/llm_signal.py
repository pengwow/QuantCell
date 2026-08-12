"""LLM 信号策略 — 基于 axon_quant MarketSignal 的 AI 信号模板。

两种模式:
  1. heuristic (默认): 双均线交叉启发式(已验证可盈利),无需网络/API Key,可复现 baseline
  2. llm: 注入 llm_provider callable,调用真实 LLM 输出 MarketSignal(JSON 格式)

ponytail: 默认 heuristic 复用已 proven 的双均线逻辑,避免重复调参
         llm_provider 是 Callable[[str], str],与 axon_quant.ReActAgent 签名一致
         策略只关心 signal → Action 映射,不感知 LLM 后端细节
"""
from __future__ import annotations

import json
from typing import Any, Callable

from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from strategy.loader import register
from axon_bridge import Action, MarketSignal, SignalType


_SIGNAL_TO_ACTION = {
    SignalType.Buy: "buy",
    SignalType.Sell: "sell",
    SignalType.Hold: "hold",
}


def _ma(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _heuristic_signal(closes: list[float], fast: int, slow: int) -> MarketSignal:
    """双均线交叉信号(确定性,可复现)。

    金叉(快线上穿慢线)→Buy, 死叉→Sell, 否则 Hold。
    首次信号(无前一状态)返回 Hold 避免冷启动噪音。
    """
    if len(closes) < slow + 1:
        return MarketSignal(
            signal_type=SignalType.Hold, symbol="", confidence=0.0,
            reasoning="warmup",
        )

    # 上一根和当前的快慢均线
    fast_ma_now = _ma(closes[-fast:])
    slow_ma_now = _ma(closes[-slow:])
    fast_ma_prev = _ma(closes[-fast - 1:-1])
    slow_ma_prev = _ma(closes[-slow - 1:-1])

    above_now = fast_ma_now > slow_ma_now
    above_prev = fast_ma_prev > slow_ma_prev

    if not above_prev and above_now:
        confidence = min(1.0, abs(fast_ma_now - slow_ma_now) / slow_ma_now * 50)
        return MarketSignal(
            signal_type=SignalType.Buy, symbol="", confidence=confidence,
            reasoning=f"golden_cross fast={fast_ma_now:.2f} slow={slow_ma_now:.2f}",
        )
    if above_prev and not above_now:
        confidence = min(1.0, abs(fast_ma_now - slow_ma_now) / slow_ma_now * 50)
        return MarketSignal(
            signal_type=SignalType.Sell, symbol="", confidence=confidence,
            reasoning=f"death_cross fast={fast_ma_now:.2f} slow={slow_ma_now:.2f}",
        )
    return MarketSignal(
        signal_type=SignalType.Hold, symbol="", confidence=0.0,
        reasoning="no_cross",
    )


@register("llm_signal")
class LLMSignalStrategy(BaseStrategy):
    """LLM/Heuristic 信号策略。

    config.params 可配:
      - mode: "heuristic"(默认) | "llm"
      - fast/slow: 启发式均线窗口 (默认10/30)
      - signal_interval: 每隔多少根 bar 允许一次新信号 (默认1,即每根K线检查)
      - llm_provider: Callable[[str], str], mode="llm" 时注入
      - position_pct: 开仓占 equity 比例 (默认0.1)
    """

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._last_signal: MarketSignal | None = None

    def on_start(self, ctx: StrategyContext) -> None:
        self._last_signal = None

    def _call_llm(self, bar: dict, ctx: StrategyContext) -> MarketSignal:
        """调用 LLM provider 并解析为 MarketSignal;失败降级为 Hold。"""
        provider: Callable[[str], str] | None = self.config.params.get("llm_provider")
        if not provider:
            return MarketSignal(
                signal_type=SignalType.Hold, symbol="", confidence=0.0,
                reasoning="no_llm_provider",
            )
        lookback = int(self.config.params.get("lookback", 30))
        recent = ctx.closes[-lookback:] if len(ctx.closes) >= lookback else ctx.closes
        o, h, l, c = bar.get("open", 0), bar.get("high", 0), bar.get("low", 0), bar.get("close", 0)
        prompt = (
            "你是量化交易分析师。分析以下K线,输出JSON信号。\n"
            '格式: {"action":"Buy"|"Sell"|"Hold","confidence":0.0-1.0,"reasoning":"..."}\n'
            f"只输出JSON。最近收盘价: {recent}\n"
            f"最新: O={o} H={h} L={l} C={c}"
        )
        try:
            reply = provider(prompt)
            start = reply.find("{")
            end = reply.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(reply[start:end])
                amap = {"Buy": SignalType.Buy, "Sell": SignalType.Sell, "Hold": SignalType.Hold}
                return MarketSignal(
                    signal_type=amap.get(data.get("action", "Hold"), SignalType.Hold),
                    symbol="",
                    confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
                    reasoning=str(data.get("reasoning", ""))[:200],
                )
        except Exception:
            pass
        return MarketSignal(
            signal_type=SignalType.Hold, symbol="", confidence=0.0,
            reasoning="llm_parse_error",
        )

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        model_id = self.config.name
        position_pct = float(self.config.params.get("position_pct", self.config.position_limit))
        mode = self.config.params.get("mode", "heuristic")
        signal_interval = int(self.config.params.get("signal_interval", 1))
        fast = int(self.config.params.get("fast", 10))
        slow = int(self.config.params.get("slow", 30))

        # 维护价格历史(与其他模板一致)
        ctx.closes.append(bar["close"])

        # 每 signal_interval 根 bar 生成新信号
        need_new = (
            self._last_signal is None
            or len(ctx.closes) % signal_interval == 0
            or (self._last_signal.signal_type == SignalType.Hold and len(ctx.closes) >= slow)
        )

        if need_new:
            if mode == "llm":
                self._last_signal = self._call_llm(bar, ctx)
            else:
                self._last_signal = _heuristic_signal(ctx.closes, fast, slow)

        sig = self._last_signal
        action_type = _SIGNAL_TO_ACTION.get(sig.signal_type, "hold")
        target = position_pct if action_type == "buy" else 0.0

        return Action(
            action_type=action_type,
            confidence=sig.confidence,
            target_position=target,
            model_id=model_id,
            inference_time_us=0,
        )

