"""DecisionClient 协议与两个离线实现。

- ReplayDecisionClient：sha256 指纹精确匹配录制响应，miss 即报错。
- StubDecisionClient：特征 → 确定性概率响应，CI/开箱即用，零成本。
真实 HTTP 客户端在后续阶段实现同一协议，本文件与上层代码无需改动。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Protocol

from decision.questions import ACTIONS, request_fingerprint
from decision.types import DecisionResponse, parse_response


class DecisionError(Exception):
    """决策客户端通用错误。"""


class ReplayMissError(DecisionError):
    """录制库中找不到该请求指纹（模板变更后必须重新录制）。"""

    def __init__(self, fingerprint: str):
        super().__init__(f"replay miss for fingerprint={fingerprint}")
        self.fingerprint = fingerprint


class DecisionClient(Protocol):
    """决策后端协议，对应未来 axon-llm 的 DecisionBackend trait。"""

    def decide(self, state: dict, questions: dict) -> DecisionResponse: ...


class ReplayDecisionClient:
    """fingerprint → 原始 SDM 响应 JSON 的精确回放。"""

    def __init__(self, recordings: dict[str, dict]):
        self._recordings = dict(recordings)

    @classmethod
    def from_jsonl(cls, path: str | Path) -> ReplayDecisionClient:
        """读取 JSONL，每行形如 {"fingerprint": "...", "response": {...}}。"""
        recordings: dict[str, dict] = {}
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                recordings[obj["fingerprint"]] = obj["response"]
        return cls(recordings)

    def decide(self, state: dict, questions: dict) -> DecisionResponse:
        fp = request_fingerprint(state, questions)
        raw = self._recordings.get(fp)
        if raw is None:
            raise ReplayMissError(fp)
        return parse_response(raw)

    def __len__(self) -> int:
        return len(self._recordings)


def _softmax(values: list[float]) -> list[float]:
    top = max(values)
    exps = [math.exp(v - top) for v in values]
    total = sum(exps)
    return [v / total for v in exps]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class StubDecisionClient:
    """特征 → 类型化响应的确定性模拟器（model="sdm-stub"）。

    同时支持 v1 和 v2 问题模板：始终输出 v1 全部 4 个键；v2 新增的 4 个键
    仅在 questions 里存在时才生成，保持向后兼容。

    ponytail: 用极简线性强度 x（双均线偏离 + 短周期收益，按波动率归一）
    驱动 softmax，天花板是它不模拟真实 SDM 的判断偏差；用途仅限打通链路
    与 CI，任何 stub 报告都带 advisory_only=true，升级路径是录制真实响应。
    """

    model = "sdm-stub"

    def decide(self, state: dict, questions: dict) -> DecisionResponse:
        f = state["features"]
        vol = max(float(f["vol_20"]), 1e-9)
        x = _clamp(float(f["sma5_vs_sma20"]) / vol, -3.0, 3.0) + 0.5 * _clamp(float(f["ret_1"]) / vol, -2.0, 2.0)
        # 顺序与 ACTIONS 一致：buy, sell, hold
        probs = _softmax([x, -x, -abs(x) * 1.5 + 0.5])
        top_idx = max(range(3), key=lambda i: probs[i])
        choice_name = ACTIONS[top_idx]

        top_p = round(probs[top_idx], 6)
        choice_probs = {name: round(probs[i], 6) for i, name in enumerate(ACTIONS)}

        # 清晰度等级跟随胜选项概率
        level = 2 if top_p >= 0.7 else 1 if top_p >= 0.5 else 0
        score_probs = {str(i): 0.0 for i in range(3)}
        score_probs[str(level)] = 0.8
        score_probs[str(max(0, level - 1))] += 0.1
        score_probs[str(min(2, level + 1))] += 0.1

        answers: dict[str, dict] = {
            # —— v1 全部 4 个，始终输出 —— #
            "next_direction": {
                "type": "choice",
                "choice": choice_name,
                "confidence": top_p,
                "probabilities": choice_probs,
            },
            "trend_confirms": {"type": "noul", "noul": round(_sigmoid(abs(x)), 6)},
            "risk_regime_bad": {
                "type": "noul",
                "noul": round(_sigmoid(abs(float(f["volume_z"])) - 1.5), 6),
            },
            "signal_clarity": {
                "type": "score",
                "score": float(level),
                "confidence": 0.8,
                "probabilities": score_probs,
            },
        }

        # —— v2 新增 4 个，仅在 questions 里存在时才生成 —— #
        if "position_size" in questions:
            answers["position_size"] = self._mock_position_size(choice_name, top_p)
        if "volatility_regime" in questions:
            answers["volatility_regime"] = self._mock_volatility_regime(f.get("vol_20", 0.0))
        if "drawdown_risk" in questions:
            answers["drawdown_risk"] = self._mock_drawdown_risk(f)
        if "execution_urgency" in questions:
            answers["execution_urgency"] = self._mock_execution_urgency(x)

        raw = {"model": self.model, "answers": answers, "usage": {"input_tokens": 0, "cost_usd": 0.0}}
        return parse_response(raw)

    # ── v2 mock 子函数（每个独立，方便未来替换成真实逻辑） ── #

    @staticmethod
    def _mock_position_size(direction: str, confidence: float) -> dict:
        """基于 direction + confidence 驱动仓位分档。hold → 0%；方向明确且置信度高 → 100%。"""
        if direction == "hold":
            choice, probs = "0pct", {"0pct": 0.8, "25pct": 0.15, "50pct": 0.05, "100pct": 0.0}
        elif confidence < 0.5:
            choice, probs = "25pct", {"0pct": 0.1, "25pct": 0.7, "50pct": 0.18, "100pct": 0.02}
        elif confidence < 0.7:
            choice, probs = "50pct", {"0pct": 0.02, "25pct": 0.1, "50pct": 0.75, "100pct": 0.13}
        else:
            choice, probs = "100pct", {"0pct": 0.0, "25pct": 0.05, "50pct": 0.2, "100pct": 0.75}
        return {
            "type": "choice",
            "choice": choice,
            "confidence": probs[choice],
            "probabilities": {k: round(v, 6) for k, v in probs.items()},
        }

    @staticmethod
    def _mock_volatility_regime(vol_20: float) -> dict:
        """vol_20 阈值驱动：<0.5% → 0，0.5-2% → 1，>2% → 2。"""
        if vol_20 < 0.005:
            score, probs = 0, {0: 0.85, 1: 0.14, 2: 0.01}
        elif vol_20 <= 0.02:
            score, probs = 1, {0: 0.1, 1: 0.8, 2: 0.1}
        else:
            score, probs = 2, {0: 0.01, 1: 0.14, 2: 0.85}
        return {
            "type": "score",
            "score": float(score),
            "confidence": probs[score],
            "probabilities": {str(k): round(v, 6) for k, v in probs.items()},
        }

    @staticmethod
    def _mock_drawdown_risk(f: dict) -> dict:
        """RSI 超买/超卖 + close_vs_sma20 大幅偏离 → 高回撤风险。"""
        rsi = f.get("rsi_14", 50.0)
        c20 = f.get("close_vs_sma20", 0.0)
        # RSI > 70 或 < 30 → 0.7-0.8；close 远离 SMA20 > 5% → 额外 0.1
        base = 0.7 if rsi > 70 or rsi < 30 else 0.3
        if abs(c20) > 0.05:
            base = min(0.9, base + 0.15)
        return {"type": "noul", "noul": round(base, 6)}

    @staticmethod
    def _mock_execution_urgency(x: float) -> dict:
        """信号强度驱动：abs(x) 大 → immediate，小 → cancel。"""
        ax = abs(x)
        if ax > 2.0:
            choice, probs = "immediate", {"immediate": 0.8, "within_60s": 0.18, "cancel": 0.02}
        elif ax > 1.0:
            choice, probs = "within_60s", {"immediate": 0.15, "within_60s": 0.75, "cancel": 0.1}
        else:
            choice, probs = "cancel", {"immediate": 0.02, "within_60s": 0.2, "cancel": 0.78}
        return {
            "type": "choice",
            "choice": choice,
            "confidence": probs[choice],
            "probabilities": {k: round(v, 6) for k, v in probs.items()},
        }
