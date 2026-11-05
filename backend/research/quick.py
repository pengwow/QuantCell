"""quick 模式执行器适配（PRD §5）。

quick 不重写研究闭环，只把现有 run_llm_mining 的候选产物映射成 research_trials，
不自动设置 SOTA、不做决策（decision 留空，依赖人工 promote）。
"""

from __future__ import annotations


def _usage_tokens(usage: dict | None) -> int:
    """兼容 total_tokens 缺失的 usage：用 prompt + completion 兜底。"""
    if not usage:
        return 0
    total = usage.get("total_tokens")
    if total is not None:
        return int(total)
    return int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)


def session_cost_from_stats(stats: dict | None, candidate_count: int | None = None) -> tuple[int, int]:
    """把挖掘 stats 归一成 (llm_calls, total_tokens)。

    calls 只认 stats 的真实计数，不再用候选数兜底（冒充调用次数会虚高成本，
    也掩盖 llm_miner 漏统计的问题）；`candidate_count` 参数仅为兼容旧调用点保留。
    """
    del candidate_count
    stats = stats or {}
    calls = int(stats.get("llm_calls") or 0)
    tokens = int(stats.get("total_tokens") or 0)
    if tokens == 0 and stats.get("usage"):
        tokens = _usage_tokens(stats.get("usage"))
    return calls, tokens


def map_candidates_to_trials(
    candidates: list[dict],
    *,
    quick_run_id: int | None = None,
    loop_idx: int = 1,
) -> list[dict]:
    """run_llm_mining 候选 → ResearchTrial 字段字典（不含 session_id）。

    只做字段映射，不碰 DB，便于单测覆盖 quick→trial 的语义。
    judge 结构与 deep 对齐（decision/gates/reason），前端无需按 mode 分支读三种形状。
    """
    trials: list[dict] = []
    for i, cand in enumerate(candidates):
        status = "evaluated" if cand.get("status") == "success" else "failed"
        redundant = bool(cand.get("redundant"))
        gate = {
            "pass": not redundant,
            "redundant": redundant,
            "redundant_with": cand.get("redundant_with"),
            "corr": cand.get("redundant_corr"),
            "threshold": None,
        }
        judge = {
            "decision": None,
            "gates": {"redundant": gate},
            "reason": "quick 模式不自动决策；相关性去重由挖掘器判定" if not redundant else "与现有因子高度相关",
        }
        trials.append(
            {
                "loop_idx": loop_idx,
                "candidate_idx": int(cand.get("candidate") or i + 1),
                "status": status,
                "hypothesis": cand.get("hypothesis") or None,
                "task_json": None,
                "code": cand.get("code"),
                "code_hash": cand.get("code_hash"),
                "metrics_json": cand.get("metrics"),
                "metrics_oos_json": cand.get("metrics_oos"),
                "oos_flag": cand.get("oos_flag"),
                "feedback_json": None,
                "judge_json": judge,
                # quick 永远不自动决策，保持人工 promote 的口径
                "decision": None,
                "quick_run_id": quick_run_id,
                "exception": cand.get("error") or None,
                # 每个候选都由 1 次 LLM 请求生成（usage 缺失时 token 只能记 0）
                "llm_calls": 1,
                "token_used": _usage_tokens(cand.get("usage")),
            }
        )
    return trials
