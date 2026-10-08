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
    """fingerprint → 原始 Jev 响应 JSON 的精确回放。"""

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
    """特征 → 类型化响应的确定性模拟器（model="jev-stub"）。

    ponytail: 用极简线性强度 x（双均线偏离 + 短周期收益，按波动率归一）
    驱动 softmax，天花板是它不模拟真实 Jev 的判断偏差；用途仅限打通链路
    与 CI，任何 stub 报告都带 advisory_only=true，升级路径是录制真实响应。
    """

    model = "jev-stub"

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

        raw = {
            "model": self.model,
            "answers": {
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
            },
            "usage": {"input_tokens": 0, "cost_usd": 0.0},
        }
        return parse_response(raw)
