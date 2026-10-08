"""离线评测编排器。

关键设计：
- 每个样本的 Jev 调用只发生一次，结果（含异常）缓存后供主阈值与
  阈值网格扫描复用，保证所有阈值比较的是同一批 Jev 判断。
- 60/40 按时间顺序切分：前段扫阈值，后段做不劣化验证。
- 推荐带 min_samples 硬门槛：样本不足直接不给建议，防止小样本过拟合。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from decision.cascade import CascadeConfig, FallbackDecider, JevCascadeDecisionLayer
from decision.client import DecisionClient, StubDecisionClient
from decision.evaluation.dataset import build_labeled_samples
from decision.evaluation.metrics import (
    accuracy,
    confusion_and_recall,
    cost_summary,
    expected_calibration_error,
)
from decision.questions import ACTIONS, request_fingerprint
from decision.types import ChoiceAnswer, DecisionResponse

# 阈值扫描网格：0.50 → 0.95，步长 0.05，开仓/观望各 10 档
_GRID = [round(0.50 + 0.05 * i, 2) for i in range(10)]
_TRAIN_RATIO = 0.6


@dataclass
class EvalConfig:
    bars: pd.DataFrame
    client: DecisionClient
    fallback: FallbackDecider
    window: int = 20
    horizon: int = 1
    cost_threshold: float = 0.002
    open_threshold: float = 0.80
    hold_threshold: float = 0.70
    fallback_cost_usd: float = 0.002
    min_samples: int = 50
    symbol: str = "BTCUSDT"
    bar_type: str = "1h"
    csv_path: str | Path | None = None
    fixtures_path: str | Path | None = None


class _CachedReplay:
    """fingerprint → 已获取响应/异常的内存回放，供多轮门控复用。"""

    def __init__(self, cache: dict[str, DecisionResponse | Exception]):
        self._cache = cache

    def decide(self, state: dict, questions: dict) -> DecisionResponse:
        result = self._cache[request_fingerprint(state, questions)]
        if isinstance(result, Exception):
            raise result
        return result


def _raw_choice(raw: Any) -> tuple[str | None, float | None]:
    """从缓存结果中提取 Jev 原始胜选项与置信度（异常/非法时为 None）。"""
    if not isinstance(raw, DecisionResponse):
        return None, None
    choice = raw.answers.get("next_direction")
    if not isinstance(choice, ChoiceAnswer) or choice.choice not in ACTIONS:
        return None, None
    return choice.choice, choice.confidence


def _run_layer(samples, cache, fallback, open_t, hold_t, fallback_unit) -> list[dict]:
    """用指定阈值跑一遍级联并产出评测记录（不触发新的 Jev 调用）。"""
    layer = JevCascadeDecisionLayer(_CachedReplay(cache), fallback, CascadeConfig(open_t, hold_t))
    records = []
    for sample in samples:
        decision = layer.decide(sample.state, sample.questions)
        raw = cache[sample.fingerprint]
        jev_action, jev_conf = _raw_choice(raw)
        records.append(
            {
                "index": sample.index,
                "label": sample.label,
                "jev_action": jev_action,
                "jev_confidence": jev_conf,
                "source": decision.source,
                "fallback_reason": decision.fallback_reason,
                "final_action": decision.action,
                "confidence": decision.confidence,
                "probabilities": decision.probabilities,
                "correct": decision.action == sample.label,
                "jev_cost_usd": decision.jev_usage.cost_usd if decision.jev_usage else 0.0,
                "fallback_cost_usd": fallback_unit if decision.source == "fallback" else 0.0,
                "sub_signals": decision.sub_signals,
            }
        )
    return records


def _slice_metrics(records: list[dict]) -> dict:
    matrix, recall = confusion_and_recall(records)
    return {
        "samples": len(records),
        "accuracy": accuracy(records),
        "confusion": matrix,
        "recall": recall,
        "ece": expected_calibration_error(records),
        "cost": cost_summary(records),
    }


def _scan(samples, cache, fallback, fallback_unit) -> list[dict]:
    """全网格扫描：返回每组阈值在给定样本上的准确率与成本。"""
    results = []
    for open_t in _GRID:
        for hold_t in _GRID:
            records = _run_layer(samples, cache, fallback, open_t, hold_t, fallback_unit)
            results.append(
                {
                    "open_threshold": open_t,
                    "hold_threshold": hold_t,
                    "accuracy": accuracy(records),
                    "cost": cost_summary(records)["total_cost_usd"],
                    "fallback_rate": sum(1 for r in records if r["source"] == "fallback") / len(records),
                }
            )
    return results


def _recommend(train, val, cache, fallback, cfg: EvalConfig) -> dict | None:
    """前段选低成本且不劣化的阈值，后段验证；样本不足返回 None。"""
    if len(train) < cfg.min_samples or len(val) < cfg.min_samples:
        return None

    base_train = _run_layer(train, cache, fallback, cfg.open_threshold, cfg.hold_threshold, cfg.fallback_cost_usd)
    base_val = _run_layer(val, cache, fallback, cfg.open_threshold, cfg.hold_threshold, cfg.fallback_cost_usd)
    train_acc_base = accuracy(base_train)
    val_acc_base = accuracy(base_val)
    val_cost_base = cost_summary(base_val)["total_cost_usd"]

    # 训练段：准确率不劣化的前提下成本最低
    candidates = [c for c in _scan(train, cache, fallback, cfg.fallback_cost_usd) if c["accuracy"] >= train_acc_base]
    candidates.sort(key=lambda c: (c["cost"], -c["accuracy"]))
    best = candidates[0]

    val_records = _run_layer(
        val, cache, fallback, best["open_threshold"], best["hold_threshold"], cfg.fallback_cost_usd
    )
    val_acc = accuracy(val_records)
    val_cost = cost_summary(val_records)["total_cost_usd"]
    if val_acc < val_acc_base:
        # 后段准确率劣化，推荐不成立
        return None

    return {
        "open_threshold": best["open_threshold"],
        "hold_threshold": best["hold_threshold"],
        "train_accuracy": best["accuracy"],
        "val_accuracy": val_acc,
        "baseline_val_accuracy": val_acc_base,
        "estimated_saving_usd": val_cost_base - val_cost,
        "min_samples": cfg.min_samples,
    }


def _sha256_of(path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_evaluation(cfg: EvalConfig) -> tuple[dict, list[dict]]:
    """执行离线评测，返回 (汇总报告, 逐样本 trace)。"""
    samples = build_labeled_samples(
        cfg.bars,
        window=cfg.window,
        horizon=cfg.horizon,
        cost_threshold=cfg.cost_threshold,
        symbol=cfg.symbol,
        bar_type=cfg.bar_type,
    )

    # Jev 调用只发生这一次；异常也缓存，保证扫描时行为一致
    cache: dict[str, DecisionResponse | Exception] = {}
    for sample in samples:
        try:
            cache[sample.fingerprint] = cfg.client.decide(sample.state, sample.questions)
        except Exception as e:
            cache[sample.fingerprint] = e

    records = _run_layer(
        samples,
        cache,
        cfg.fallback,
        cfg.open_threshold,
        cfg.hold_threshold,
        cfg.fallback_cost_usd,
    )

    split = int(len(samples) * _TRAIN_RATIO)
    train, val = samples[:split], samples[split:]

    report = {
        "samples": len(samples),
        "symbol": cfg.symbol,
        "bar_type": cfg.bar_type,
        "label_distribution": {name: sum(1 for s in samples if s.label == name) for name in ACTIONS},
        "thresholds": {
            "open_threshold": cfg.open_threshold,
            "hold_threshold": cfg.hold_threshold,
        },
        "metrics": _slice_metrics(records),
        "cost": cost_summary(records),
        "slices": {
            "train": _slice_metrics(
                _run_layer(
                    train,
                    cache,
                    cfg.fallback,
                    cfg.open_threshold,
                    cfg.hold_threshold,
                    cfg.fallback_cost_usd,
                )
            ),
            "test": _slice_metrics(
                _run_layer(
                    val,
                    cache,
                    cfg.fallback,
                    cfg.open_threshold,
                    cfg.hold_threshold,
                    cfg.fallback_cost_usd,
                )
            ),
        },
        "recommendation": _recommend(train, val, cache, cfg.fallback, cfg),
        "data_fingerprint": {
            "csv_sha256": _sha256_of(cfg.csv_path),
            "fixtures_sha256": _sha256_of(cfg.fixtures_path),
        },
        # stub 结论一律标记为参考性，禁止据此调生产阈值
        "advisory_only": isinstance(cfg.client, StubDecisionClient),
    }
    return report, records
