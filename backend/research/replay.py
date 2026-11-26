"""历史 trial 回放（P2 阶段 1）。

回放只重跑「评估」这一步：原 trial 已落库的代码 + 会话配置里的数据窗口/评估参数，
评估直接委托 factor 场景的 FactorService（内部走 FactorSandbox），**不另造执行器**。

LLM 生成阶段无法复现（模型输出不确定），所以 model / prompt_hash / temperature
只作为 provenance 原样带到回放记录，不参与执行；corr(SOTA) 依赖当时的最优因子
序列，未持久化，同样无法重算，只在对比处展示原值。

缺字段口径：
- 阻断（409）：原 trial 没有代码、会话配置缺 symbols / interval；
- 部分复现（200 + partial）：缺 start / end / candle_type / test_ratio / wf_folds，
  回放按引擎默认值执行并在 replay_meta 里明确列出缺失项，不静默套用。
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from factor.engine import code_hash, load_raw_ohlcv
from factor.llm_miner import _metrics_from_analysis, _oos_metrics
from research import service
from research.models import ResearchTrial
from research.scenario import get_scenario
from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

# 同参数回放的 IC_IR 允许误差：同一份代码/数据/参数下沙箱是确定性的，
# 仅浮点累加顺序可能带来 1e-12 级差异，这里留 1e-6 的余量。
IC_IR_TOLERANCE = 1e-6

# 回放行固定 loop_idx=0：不占用正常轮次编号，避免撞 run 的
# (session_id, loop_idx, candidate_idx) 唯一索引。
REPLAY_LOOP_IDX = 0

# 这些字段缺失时仍能跑，但结果只能算“部分复现”
_OPTIONAL_FIELDS = ("start", "end", "candle_type", "test_ratio", "wf_folds")


def _missing(cfg: dict[str, Any], key: str) -> bool:
    return key not in cfg or cfg[key] is None or cfg[key] == ""


def _diff(left: Any, right: Any) -> float | None:
    try:
        if left is None or right is None:
            return None
        return abs(float(left) - float(right))
    except TypeError, ValueError:
        return None


def _next_replay_index(db: Session, session_id: int) -> int:
    """回放行的 candidate_idx 在 loop_idx=0 内自增，重试/并发时也能拿到空位。"""
    rows = (
        db.query(ResearchTrial)
        .filter(ResearchTrial.session_id == session_id)
        .filter(ResearchTrial.loop_idx == REPLAY_LOOP_IDX)
        .all()
    )
    return max((row.candidate_idx for row in rows), default=0) + 1


def replay_trial(db: Session, *, session_id: int, trial_id: int, owner_id: str) -> dict[str, Any]:
    """重跑原 trial 的评估，落一条 replay_of_id 关联的新 trial（不覆盖原记录）。"""
    session_row = service.get_session_row(db, session_id, owner_id)
    trial = service.get_trial_row(db, trial_id)
    if trial.session_id != session_id:
        raise service.ResearchError("not_found", f"试验 {trial_id} 不属于会话 {session_id}")

    code = (trial.code or "").strip()
    if not code:
        # 没有代码时重新生成 = 另一次 LLM 采样，不叫回放
        raise service.ResearchError("bad_state", "原 trial 没有可执行的代码，无法回放")

    cfg = service.session_config(session_row)
    scenario_name = str(cfg.get("scenario") or "factor")
    if scenario_name != "factor":
        raise service.ResearchError("bad_state", f"场景 {scenario_name} 暂不支持回放")

    blocking = [key for key in ("symbols", "interval") if _missing(cfg, key)]
    if blocking:
        raise service.ResearchError("bad_state", f"无法回放：会话配置缺少 {', '.join(blocking)}")
    missing = [key for key in _OPTIONAL_FIELDS if _missing(cfg, key)]

    started_at = time.monotonic()
    try:
        raw_map = load_raw_ohlcv(
            cfg["symbols"],
            str(cfg["interval"]),
            str(cfg.get("candle_type") or "spot"),
            cfg.get("start"),
            cfg.get("end"),
        )
        scenario = get_scenario("factor")
        analysis = scenario.evaluate(code, raw_map, cfg)
        train = analysis.get("train")
        if not train:
            raise RuntimeError("评估结果缺少 train 段")
        metrics = _metrics_from_analysis(train)
        # 与 loop.py 同一口径；缺 test_ratio 时引擎本身按 0.0 处理，这里显式标注
        metrics_oos, flag, note, _folds = _oos_metrics(analysis, metrics, float(cfg.get("test_ratio") or 0.0))
        metrics["oos"] = metrics_oos
        corr_library = None
        library_corr = getattr(scenario, "library_corr", None)
        if callable(library_corr):
            try:
                corr_library = library_corr(analysis.get("train_factor"), raw_map)
            except Exception:
                logger.exception("[回放] 因子库相关性计算失败，corr(library) 记 None")
    except service.ResearchError:
        raise
    except Exception as exc:
        logger.exception(f"[回放] trial {trial_id} 执行失败")
        raise service.ResearchError("replay_failed", f"回放执行失败：{str(exc)[:200]}") from exc

    original_metrics = service._loads(trial.metrics_json, {})
    ic_ir_diff = _diff(original_metrics.get("ic_ir"), metrics.get("ic_ir"))
    corr_library_diff = _diff(trial.corr_library, corr_library)
    oos_changed = (trial.oos_flag or None) != (flag or None)
    consistent = ic_ir_diff is not None and ic_ir_diff <= IC_IR_TOLERANCE and not oos_changed

    notes: list[str] = []
    if missing:
        notes.append(f"部分复现：会话配置缺少 {', '.join(missing)}，回放按引擎默认值执行")
    if trial.corr_sota is not None:
        # 原始 SOTA 因子序列没有持久化，回放无法重建；对比处保留原值
        notes.append("corr(SOTA) 依赖当时的最优因子序列，未持久化，无法重算")

    meta: dict[str, Any] = {
        "original_trial_id": trial.id,
        "partial": bool(missing),
        "missing": missing,
        "notes": notes,
        "tolerance": {"ic_ir": IC_IR_TOLERANCE},
        "diff": {
            "ic_ir": ic_ir_diff,
            "oos_changed": oos_changed,
            "corr_library": corr_library_diff,
        },
        "consistent": consistent,
        # corr(SOTA) 不可复现，单列出来避免前端误以为回放值为 0
        "unreproducible": ["corr_sota"] if trial.corr_sota is not None else [],
    }

    fields: dict[str, Any] = {
        "loop_idx": REPLAY_LOOP_IDX,
        "status": "evaluated",
        "hypothesis": trial.hypothesis,
        "code": code,
        "code_hash": code_hash(code),
        "metrics_json": metrics,
        "metrics_oos_json": metrics_oos,
        "oos_flag": flag,
        "oos_note": note,
        "corr_sota": None,
        "corr_library": corr_library,
        "replay_of_id": trial.id,
        "model": trial.model,
        "prompt_hash": trial.prompt_hash,
        "temperature": trial.temperature,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        # 回放不调用 LLM，成本必须如实记 0，不能沿用原 trial 的消耗
        "token_used": 0,
        "llm_calls": 0,
        "replay_meta_json": meta,
    }

    new_row = None
    for attempt in range(3):
        try:
            new_row = service.add_trial(db, session_id, {**fields, "candidate_idx": _next_replay_index(db, session_id)})
            break
        except service.ResearchError as exc:
            # 并发回放撞唯一键时换下一个空位，而不是把 409 抛给用户
            if exc.kind != "duplicate_trial" or attempt == 2:
                raise
    if new_row is None:
        raise service.ResearchError("replay_failed", "回放记录落库失败，请重试")

    try:
        service.append_event(
            db,
            session_id,
            "info",
            "trial.replay",
            f"回放 trial {trial.id} → {new_row.id} partial={meta['partial']} consistent={consistent}",
        )
    except Exception:
        logger.exception("[回放] 事件落库失败，已忽略")

    return {
        "trial": service.trial_to_dict(new_row),
        "original": service.trial_to_dict(trial, include_code=False),
        "replay_meta": meta,
    }
