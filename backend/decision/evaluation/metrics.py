"""离线评测指标（纯函数，输入为 evaluator 产出的记录列表）。

记录字段口径：
- final_action/label/confidence/correct：门控后的最终动作与标签
- source：jev_direct | fallback
- jev_cost_usd：该样本实际产生的 Jev 费用（低置信兜底也计费，异常兜底为 0）
- fallback_cost_usd：兜底决策费用（仅 source=fallback 时非 0）
"""

from __future__ import annotations

from decision.questions import ACTIONS


def accuracy(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r["correct"]) / len(records)


def confusion_and_recall(records: list[dict]) -> tuple[dict[str, dict[str, int]], dict[str, float | None]]:
    """返回 (混淆矩阵[pred][label], 各类召回率)。某类无真实样本时召回为 None。"""
    matrix = {pred: {label: 0 for label in ACTIONS} for pred in ACTIONS}
    for r in records:
        matrix[r["final_action"]][r["label"]] += 1

    recall: dict[str, float | None] = {}
    for label in ACTIONS:
        total = sum(matrix[pred][label] for pred in ACTIONS)
        recall[label] = matrix[label][label] / total if total else None
    return matrix, recall


def expected_calibration_error(
    records: list[dict],
    n_bins: int = 5,
    min_bin_samples: int = 10,
) -> float | None:
    """ECE：置信度分箱均值与实际正确率的加权差距。

    任一非空箱样本数 < min_bin_samples 时返回 None（小样本下 ECE 不可信）；
    空箱不参与计算。
    """
    bins: list[list[dict]] = [[] for _ in range(n_bins)]
    for r in records:
        idx = min(int(float(r["confidence"]) * n_bins), n_bins - 1)
        bins[idx].append(r)

    populated = [b for b in bins if b]
    if not populated or any(len(b) < min_bin_samples for b in populated):
        return None

    total = len(records)
    ece = 0.0
    for b in populated:
        avg_conf = sum(float(r["confidence"]) for r in b) / len(b)
        acc = sum(1 for r in b if r["correct"]) / len(b)
        ece += len(b) / total * abs(avg_conf - acc)
    return ece


def cost_summary(records: list[dict]) -> dict:
    """区分 Jev 与兜底两路花费；jev_calls 按实际计费次数统计。"""
    n = len(records)
    jev_calls = sum(1 for r in records if r["jev_cost_usd"] > 0)
    fallback_calls = sum(1 for r in records if r["source"] == "fallback")
    total_jev = sum(float(r["jev_cost_usd"]) for r in records)
    total_fb = sum(float(r["fallback_cost_usd"]) for r in records)
    return {
        "samples": n,
        "jev_calls": jev_calls,
        "fallback_calls": fallback_calls,
        "jev_direct_rate": (n - fallback_calls) / n if n else 0.0,
        "total_jev_cost_usd": total_jev,
        "total_fallback_cost_usd": total_fb,
        "total_cost_usd": total_jev + total_fb,
    }
