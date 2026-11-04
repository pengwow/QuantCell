"""决策硬门（PRD §4.3 / §9）。

深研 trial 只有同时满足三道门才标记 decision=True：
1. 样本内 IC_IR ≥ icir_floor
2. 样本外方向一致（oos_flag == "ok"）
3. 与现有 SOTA / 因子库的截面 rank 相关 |corr| < corr_threshold

第 3 门的数据由 loop 在评估完成时持久化（corr_sota / corr_library），续跑时直接复用；
缺失时不再默认放行，而是给出 status="unknown"（decision 仍然为 False，宁可拦下也不放过）。

只做纯函数，方便单测；LLM 无投票权。
"""

from __future__ import annotations

import math
from typing import Any


def _finite(value: Any) -> float | None:
    """NaN/inf 一律当成缺失值，避免污染 judge_json 与等值比较。"""
    if value is None:
        return None
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def evaluate_gates(
    *,
    ic_ir: float | None,
    oos_flag: str | None,
    corr_vs_sota: float | None,
    icir_floor: float,
    corr_threshold: float,
    corr_vs_library: float | None = None,
    sota_expected: bool = False,
) -> dict:
    """返回可直接落库的 judge_json。

    gate 3 的对比对象：当前 SOTA（best_trial_id 对应因子）与因子库参考因子。
    - `sota_expected=False` 表示本次评估时还没有 SOTA（首轮），SOTA 侧不参与判定；
    - 只要某一侧“应当有值”却拿到 None（例如续跑缺少持久化 corr），corr 门记为 unknown，
      绝不静默视为通过；unknown 的 decision 也是 False。
    """
    ic_ir = _finite(ic_ir)
    corr_vs_sota = _finite(corr_vs_sota)
    corr_vs_library = _finite(corr_vs_library)
    icir_pass = ic_ir is not None and ic_ir >= icir_floor
    oos_pass = oos_flag == "ok"

    unknown: list[str] = []
    sota_pass = True
    library_pass = True
    if sota_expected:
        if corr_vs_sota is None:
            unknown.append("SOTA")
        else:
            sota_pass = abs(corr_vs_sota) < corr_threshold
    if corr_vs_library is None:
        unknown.append("因子库")
    else:
        library_pass = abs(corr_vs_library) < corr_threshold

    if unknown:
        corr_status = "unknown"
        corr_pass = False
    else:
        corr_pass = sota_pass and library_pass
        corr_status = "pass" if corr_pass else "fail"

    gates = {
        "icir": {"pass": icir_pass, "value": ic_ir, "floor": icir_floor},
        "oos": {"pass": oos_pass, "value": oos_flag},
        "corr": {
            "pass": corr_pass,
            "status": corr_status,
            "value": corr_vs_sota,
            "sota_value": corr_vs_sota,
            "sota_expected": sota_expected,
            "sota_pass": sota_pass,
            "library_value": corr_vs_library,
            "library_pass": library_pass,
            "threshold": corr_threshold,
            "unknown": unknown,
        },
    }
    failed: list[str] = []
    for name, gate in gates.items():
        if gate["pass"]:
            continue
        if name == "corr":
            if unknown:
                failed.append("corr(无法判定：缺少 " + "/".join(unknown) + " 对比)")
            else:
                failed.append("corr(sota)" if not sota_pass else "corr(library)")
        else:
            failed.append(name)
    decision = not failed
    if decision:
        reason = "三道硬门均通过"
    else:
        reason = "未通过：" + "、".join(failed)
    return {"decision": decision, "gates": gates, "reason": reason}
