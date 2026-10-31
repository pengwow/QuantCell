"""级联决策策略 — S1（Laya 快判）→ 低置信升级 S2（生成式）。

state/questions 契约受 axon-llm 硬约束（改前先读设计文档 2.1 节）：
  - 主问题键名固定 next_direction，选项只能是 buy/sell/hold；
  - state.features 必须含 sma5_vs_sma20 / ret_1，否则 RuleFallback 恒 Hold。

config.params 可配：
  - mode: "cascade"（loader 注入 layer 的判定依据）
  - target_ratio: 开仓占权益比例（默认取 config.position_limit）
  - open_threshold / hold_threshold: 门限（默认 0.80 / 0.70）
  - s1_timeout_secs: S1 超时（默认 5）
  - s2_mode: "live"(默认) | "replay"
  - s2_max_calls: S2 真调上限（超限切规则层）
  - decision_replay: 录制文件路径（整层离线复跑，不装配 layer）

注意：strategy.decision_service 依赖 ai.config（DB），在 _decide 内按需 import，
避免 strategy 包初始化阶段连带拉起 DB 依赖。
"""

from __future__ import annotations

from strategy import Action, BaseStrategy, StrategyConfig, StrategyContext
from strategy.decision_recording import DecisionReplayTable, request_fingerprint
from strategy.loader import register
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

_QUESTIONS = {
    "next_direction": {
        "type": "choice",
        "instructions": {"question": "下一根 K 线方向？", "focus": "仅依据给定特征"},
        "criteria": {
            "buy": {"what": "价格偏向上行"},
            "sell": {"what": "价格偏向下行"},
            "hold": {"what": "方向不明或震荡"},
        },
    }
}


def _hold_decision() -> dict:
    """本 bar 无法决策时的保守输出。

    每次返回新对象：嵌套的 probabilities 若复用同一 dict，
    下游修改会污染后续所有 Hold。
    """
    return {
        "action": "hold",
        "source": "fallback",
        "confidence": 0.0,
        "probabilities": {"hold": 1.0, "buy": 0.0, "sell": 0.0},
        "fallback_reason": "no_decision",
        "sdm_usage": None,
        "sub_signals": {},
    }


@register("cascade_signal")
class CascadeSignalStrategy(BaseStrategy):
    """cascade 决策策略（S1 快判 + S2 低置信升级）。"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self._layer = self.get_param("_cascade_layer")
        self._replay = None
        replay_path = self.get_param("decision_replay")
        if replay_path:
            self._replay = DecisionReplayTable(replay_path)
            logger.info(f"[cascade] 进入整层离线复跑: {replay_path}")
        self._s2_calls = 0
        self._force_rule = False
        self._rule_switched = False

    def on_start(self, ctx: StrategyContext) -> None:
        self._s2_calls = 0
        self._force_rule = False
        self._rule_switched = False

    def _build_request(self, bar: dict, ctx: StrategyContext) -> tuple[dict, dict]:
        """组装 state/questions；features 两键是 RuleFallback 的硬依赖。"""
        closes = ctx.closes
        # 参数来自前端，做下限钳制：fast<2 会除零/窗口失效，slow 必须大于 fast
        fast = max(2, int(self.get_param("fast", 5)))
        slow = max(fast + 1, int(self.get_param("slow", 20)))

        if len(closes) >= slow + 1:
            fast_ma = sum(closes[-fast:]) / fast
            slow_ma = sum(closes[-slow:]) / slow
            sma_ratio = (fast_ma - slow_ma) / slow_ma if slow_ma else 0.0
        else:
            sma_ratio = 0.0

        ret_1 = 0.0
        if len(closes) >= 2 and closes[-2]:
            ret_1 = (closes[-1] - closes[-2]) / closes[-2]

        # 键名 sma5_vs_sma20 是 Rust RuleFallback 的硬契约（C2），
        # 实际窗口由 fast/slow 决定，这里只是契约占位键
        state = {
            "features": {"sma5_vs_sma20": float(sma_ratio), "ret_1": float(ret_1)},
            "price": float(bar.get("close", 0.0)),
            "position": float(ctx.positions.get(self.config.symbol, 0.0)),
            "equity": float(ctx.account_equity),
        }
        return state, dict(_QUESTIONS)

    def _decide(self, state: dict, questions: dict) -> dict:
        if self._replay is not None:
            fp = request_fingerprint(state, questions)
            recorded = self._replay.lookup(fp)
            if recorded:
                return dict(recorded)
            logger.warning(f"[cascade] decision_replay 未命中 fingerprint={fp}，保守 Hold")
            return _hold_decision()

        if self._layer is None:
            return _hold_decision()

        if self._force_rule and not self._rule_switched:
            # 超限只重建一次：若每 bar 都调，会重复触发 DB 全量配置读取
            # 函数内 import：strategy.decision_service 会拉起 ai.config（DB 依赖），
            # 顶部引入会放大 strategy 包初始化成本
            from strategy.decision_service import build_cascade_layer

            self._layer = build_cascade_layer(
                {**self.config.params, "force_rule": True},
                run_mode=None,
            )
            self._rule_switched = True

        try:
            decision = self._layer.decide(state, questions)
        except Exception as e:
            # 单 bar 决策失败只降级为 Hold，不能炸掉泵线程
            logger.error(f"[cascade] decide 失败，本 bar 保守 Hold: {e}")
            return _hold_decision()

        if self._counts_as_s2_call(decision):
            self._s2_calls += 1
            cap = int(self.get_param("s2_max_calls", 0))
            if cap > 0 and self._s2_calls > cap and not self._force_rule:
                self._force_rule = True
                logger.warning(
                    f"[cascade] S2 调用超限({self._s2_calls}>{cap})，后续 bar 切规则兜底: strategy={self.config.name}"
                )
        return decision

    def _counts_as_s2_call(self, decision: dict) -> bool:
        """只统计「S1 低置信触发的真实 S2 升级」。

        S1 网络错误兜底不耗 S2 token；replay 模式根本不调 S2，都不计入上限。
        """
        if str(self.get_param("s2_mode", "live")) != "live":
            return False
        reason = str(decision.get("fallback_reason") or "")
        return decision.get("source") == "fallback" and reason.startswith("low_confidence")

    @staticmethod
    def _to_action(decision: dict, target_ratio: float, model_id: str) -> Action:
        action = decision.get("action", "hold")
        confidence = float(decision.get("confidence") or 0.0)
        if action == "buy":
            target = target_ratio
        elif action == "sell":
            target = 0.0
        else:
            action = "hold"
            target = 0.0
        return Action(
            action_type=action,
            confidence=confidence,
            target_position=target,
            model_id=model_id,
            inference_time_us=0,
        )

    def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
        ctx.closes.append(bar["close"])
        target_ratio = float(self.get_param("target_ratio", self.config.position_limit))

        state, questions = self._build_request(bar, ctx)
        decision = self._decide(state, questions)

        logger.debug(
            f"[cascade] action={decision.get('action')} source={decision.get('source')} "
            f"conf={decision.get('confidence')} reason={decision.get('fallback_reason')} "
            f"usage={decision.get('sdm_usage')}"
        )
        return self._to_action(decision, target_ratio, self.config.name)
