"""研究模块 P0 核心单测：状态机 / 硬门 / quick 映射 / 预算 / 闭环。"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pandas as pd
import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
from collector.db.database import Base
from research import agents, service
from research.judge import evaluate_gates
from research.loop import Budget, BudgetExhausted, LoopDeps, ResearchLoop, _cfg_number
from research.models import ResearchKnowledge, ResearchSession, ResearchTrial
from research.quick import map_candidates_to_trials, session_cost_from_stats
from research.state import (
    InvalidTransition,
    ensure_session_transition,
    ensure_trial_transition,
)


@pytest.fixture()
def research_db():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        eng,
        tables=[
            ResearchSession.__table__,
            ResearchTrial.__table__,
            ResearchKnowledge.__table__,
        ],
    )
    Session = sessionmaker(bind=eng)
    db = Session()

    @contextmanager
    def factory():
        yield db

    try:
        yield db, factory
    finally:
        db.close()


def _create_session(db, *, mode="deep", cfg=None, n_candidates=1):
    cfg = cfg or {}
    row = service.create_session(
        db,
        owner_id="u1",
        name=f"{mode}-test",
        mode=mode,
        scenario="factor",
        config=cfg,
        n_candidates=n_candidates,
    )
    service.set_session_status(db, row, "running")
    return row.id


DEEP_CFG = {
    "symbols": ["BTCUSDT"],
    "interval": "1h",
    "candle_type": "spot",
    "start": "2026-01-01",
    "end": "2026-06-01",
    "loop_n": 3,
    "n_candidates": 1,
    "max_llm_calls": 30,
    "max_tokens": 200_000,
    "icir_floor": 0.15,
    "corr_threshold": 0.7,
    "test_ratio": 0.3,
    "wf_folds": 0,
    "temperature": 0.2,
}


def _fake_llm_call(prompts: list[str]):
    def _call(system: str, user: str) -> tuple[str, dict]:
        prompts.append(system)
        if "顶级加密" in system:
            return ("```python\ndef calc(df):\n    return df['close'].pct_change(5)\n```", {"total_tokens": 10})
        if "量化因子研究员" in system:
            return ('{"hypothesis": "量价背离", "reason": "价涨量缩"}', {"total_tokens": 10})
        if "量化实验规划员" in system:
            return (
                '{"tasks": [{"name": "px_vol", "description": "价量背离", "formulation": "close/pct_change - volume/pct_change"}]}',
                {"total_tokens": 10},
            )
        return ('{"observations": "ok", "evaluation": "稳定", "reason": ""}', {"total_tokens": 10})

    return _call


def _fake_evaluator(code, raw_map, cfg):
    return {
        "train": {"ic": {"mean": 0.05, "ir": 0.3}, "inspection": {"coverage": 0.8}, "bar_count": 100},
        "test": {"ic": {"mean": 0.04, "ir": 0.25}, "inspection": {"coverage": 0.8}, "bar_count": 30},
        "train_factor": pd.Series([1.0, 2.0, 3.0]),
    }


class _StubScenario:
    """只实现闭环用到的两个点：build_tasks / library_corr（避免测试依赖真实因子库）。"""

    key = "factor"

    def __init__(self, library_corr_value: float | None):
        self.library_corr_value = library_corr_value

    def build_tasks(self, *, llm_call, hypothesis, context, n):
        tasks, usage = agents.plan_tasks(llm_call, hypothesis, context)
        return tasks[: max(int(n), 1)], usage

    def library_corr(self, series, raw_map):
        return self.library_corr_value


# ---------- 状态机 ----------


def test_session_transitions():
    ensure_session_transition("pending", "running")
    ensure_session_transition("running", "paused")
    ensure_session_transition("paused", "running")
    # 暂停后剩余工作已跑完 / 暂停请求晚到：paused → completed 合法（B1）
    ensure_session_transition("paused", "completed")
    ensure_session_transition("completed", "running")  # extend
    with pytest.raises(InvalidTransition):
        ensure_session_transition("cancelled", "running")
    with pytest.raises(InvalidTransition):
        ensure_session_transition("completed", "paused")


def test_trial_transitions():
    ensure_trial_transition("planned", "coding")
    ensure_trial_transition("coding", "coded")
    ensure_trial_transition("running", "evaluated")
    ensure_trial_transition("evaluated", "judged")
    with pytest.raises(InvalidTransition):
        ensure_trial_transition("judged", "coded")
    with pytest.raises(InvalidTransition):
        ensure_trial_transition("failed", "running")


# ---------- 硬门 ----------


def test_judge_three_gates_pass():
    out = evaluate_gates(
        ic_ir=0.3,
        oos_flag="ok",
        corr_vs_sota=0.2,
        corr_vs_library=0.1,
        icir_floor=0.15,
        corr_threshold=0.7,
    )
    assert out["decision"] is True
    assert all(g["pass"] for g in out["gates"].values())
    assert out["gates"]["corr"]["status"] == "pass"


@pytest.mark.parametrize(
    ("ic_ir", "oos_flag", "corr", "failed_gate"),
    [
        (0.05, "ok", 0.2, "icir"),
        (0.3, "weak", 0.2, "oos"),
        (0.3, "ok", 0.9, "corr"),
        (None, "ok", 0.2, "icir"),
        (0.3, None, 0.2, "oos"),
    ],
)
def test_judge_each_gate_can_veto(ic_ir, oos_flag, corr, failed_gate):
    out = evaluate_gates(
        ic_ir=ic_ir,
        oos_flag=oos_flag,
        corr_vs_sota=corr,
        corr_vs_library=0.1,
        icir_floor=0.15,
        corr_threshold=0.7,
        sota_expected=True,
    )
    assert out["decision"] is False
    assert out["gates"][failed_gate]["pass"] is False


def test_judge_corr_missing_is_unknown_not_pass():
    """缺对比数据时不能静默放行：status=unknown 且 decision=False。"""
    out = evaluate_gates(
        ic_ir=0.3,
        oos_flag="ok",
        corr_vs_sota=None,
        corr_vs_library=None,
        icir_floor=0.15,
        corr_threshold=0.7,
        sota_expected=True,
    )
    assert out["gates"]["corr"]["status"] == "unknown"
    assert out["gates"]["corr"]["pass"] is False
    assert out["decision"] is False
    assert "无法判定" in out["reason"]
    assert set(out["gates"]["corr"]["unknown"]) == {"SOTA", "因子库"}


def test_judge_first_round_has_no_sota():
    """首轮没有 SOTA 是正常状态，只要求因子库对比存在。"""
    out = evaluate_gates(
        ic_ir=0.3,
        oos_flag="ok",
        corr_vs_sota=None,
        corr_vs_library=0.1,
        icir_floor=0.15,
        corr_threshold=0.7,
        sota_expected=False,
    )
    assert out["gates"]["corr"]["status"] == "pass"
    assert out["decision"] is True


def test_judge_boundaries_are_inclusive_and_exclusive():
    """IC_IR 等值 >= 通过；相关性等值 < 才通过（= threshold 视为冗余）。"""
    at_floor = evaluate_gates(
        ic_ir=0.15,
        oos_flag="ok",
        corr_vs_sota=0.0,
        corr_vs_library=0.0,
        icir_floor=0.15,
        corr_threshold=0.7,
    )
    assert at_floor["gates"]["icir"]["pass"] is True

    at_threshold = evaluate_gates(
        ic_ir=0.3,
        oos_flag="ok",
        corr_vs_sota=0.7,
        corr_vs_library=0.1,
        icir_floor=0.15,
        corr_threshold=0.7,
        sota_expected=True,
    )
    assert at_threshold["gates"]["corr"]["pass"] is False
    assert at_threshold["decision"] is False


def test_judge_nan_is_treated_as_missing():
    """NaN 不能被当成“高 IC_IR”或“低相关”，统一按缺失处理（unknown）。"""
    out = evaluate_gates(
        ic_ir=float("nan"),
        oos_flag="ok",
        corr_vs_sota=float("nan"),
        corr_vs_library=float("nan"),
        icir_floor=0.15,
        corr_threshold=0.7,
        sota_expected=True,
    )
    assert out["gates"]["icir"]["pass"] is False
    assert out["gates"]["corr"]["status"] == "unknown"
    assert out["gates"]["corr"]["pass"] is False
    assert out["decision"] is False


def test_judge_library_corr_also_vetoes():
    out = evaluate_gates(
        ic_ir=0.3,
        oos_flag="ok",
        corr_vs_sota=0.1,
        corr_vs_library=0.9,
        icir_floor=0.15,
        corr_threshold=0.7,
    )
    assert out["gates"]["corr"]["pass"] is False
    assert "corr(library)" in out["reason"]


# ---------- quick 映射 ----------


def test_quick_mapping():
    trials = map_candidates_to_trials(
        [
            {
                "candidate": 1,
                "status": "success",
                "code": "c1",
                "code_hash": "h1",
                "metrics": {"ic_mean": 0.1},
                "oos_flag": "ok",
            },
            {"candidate": 2, "status": "failed", "code": "c2", "error": "boom"},
        ]
    )
    assert [t["candidate_idx"] for t in trials] == [1, 2]
    assert trials[0]["status"] == "evaluated"
    assert trials[0]["decision"] is None
    assert trials[1]["status"] == "failed"
    assert trials[1]["exception"] == "boom"


def test_quick_cost_stats():
    assert session_cost_from_stats({"llm_calls": 3, "total_tokens": 99}, 4) == (3, 99)
    # 没有真实计数就记 0：不能用候选数冒充调用次数（I3）
    assert session_cost_from_stats({}, 4) == (0, 0)
    # token 缺失时用 prompt+completion 兜底
    assert session_cost_from_stats({"llm_calls": 1, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}, 1) == (
        1,
        15,
    )


# ---------- 预算 ----------


def test_budget_short_circuit():
    budget = Budget(max_calls=1, max_tokens=100)
    budget.spend_call()
    with pytest.raises(BudgetExhausted):
        budget.spend_call()
    with pytest.raises(BudgetExhausted):
        budget.add_tokens(101)


# ---------- quick 闭环 ----------


def test_quick_loop_end_to_end(research_db):
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 1, "max_llm_calls": 6, "max_tokens": 40_000}
    sid = _create_session(db, mode="quick", cfg=cfg, n_candidates=2)

    def mining_fn(_cfg):
        return {
            "candidates": [
                {"candidate": 1, "status": "success", "code": "c1", "metrics": {"ic_mean": 0.1}},
                {"candidate": 2, "status": "failed", "code": "c2", "error": "boom"},
            ],
            "stats": {"llm_calls": 2, "total_tokens": 30},
        }

    ResearchLoop(sid, LoopDeps(mining_fn=mining_fn, db_session_factory=factory)).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    assert row.loop_done == 1
    assert row.llm_calls == 2
    assert row.token_used == 30
    trials = service.list_trials(db, sid)
    assert len(trials) == 2
    assert {t.status for t in trials} == {"evaluated", "failed"}


# ---------- deep 闭环 ----------


def test_deep_loop_three_rounds(research_db):
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg=DEEP_CFG)
    prompts: list[str] = []
    deps = LoopDeps(
        llm_call=_fake_llm_call(prompts),
        evaluator=_fake_evaluator,
        data_loader=lambda cfg: {"BTCUSDT": object()},
        corr_fn=lambda a, b: 0.2,  # 与 SOTA 低相关，冗余门通过
        scenario=_StubScenario(0.2),
        db_session_factory=factory,
    )

    ResearchLoop(sid, deps).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    assert row.loop_done == 3
    assert row.llm_calls == 12  # 每轮 4 次 LLM
    assert row.token_used == 120
    trials = service.list_trials(db, sid)
    assert len(trials) == 3
    assert all(t.status == "judged" and t.decision is True for t in trials)
    assert row.best_trial_id == trials[-1].id


def test_deep_trial_failure_does_not_kill_session(research_db):
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 2}
    sid = _create_session(db, mode="deep", cfg=cfg)
    calls = {"n": 0}

    def flaky_evaluator(code, raw_map, cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("沙箱超时")
        return _fake_evaluator(code, raw_map, cfg)

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=flaky_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    assert row.loop_done == 2
    trials = service.list_trials(db, sid)
    assert [t.status for t in trials] == ["failed", "judged"]


def test_deep_budget_short_circuit(research_db):
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 3, "max_llm_calls": 1}
    sid = _create_session(db, mode="deep", cfg=cfg)
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            db_session_factory=factory,
        ),
    ).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    assert row.llm_calls == 1
    assert row.loop_done == 0
    assert service.list_trials(db, sid) == []


def test_schema_quick_rejects_multiple_loops():
    from pydantic import ValidationError

    from research.schemas import ResearchCreateReq

    with pytest.raises(ValidationError):
        ResearchCreateReq(
            mode="quick",
            symbols=["BTCUSDT"],
            start="2026-01-01",
            end="2026-06-01",
            loop_n=2,
        )
    with pytest.raises(ValidationError):
        ResearchCreateReq(
            mode="deep",
            symbols=["BTCUSDT"],
            start="2026-01-01",
            end="2026-01-20",  # 不足 30 天
        )


# ---------- 回归：控制面 / 续跑 / 预算落库 / CAS ----------


def test_quick_over_budget_still_persists_trials(research_db):
    """I2：钱花出去了就必须留下 trials 与成本，不能出现 trials=0。"""
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 1, "max_llm_calls": 2}
    sid = _create_session(db, mode="quick", cfg=cfg)

    def mining_fn(_cfg):
        return {
            "candidates": [
                {"candidate": 1, "status": "success", "code": "c1", "metrics": {"ic_mean": 0.1}},
                {"candidate": 2, "status": "success", "code": "c2", "metrics": {"ic_mean": 0.2}},
            ],
            "stats": {"llm_calls": 10, "total_tokens": 500},
        }

    ResearchLoop(sid, LoopDeps(mining_fn=mining_fn, db_session_factory=factory)).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"  # 预算耗尽按完成收尾
    assert len(service.list_trials(db, sid)) == 2
    assert row.llm_calls == 10
    assert row.token_used == 500


def test_pause_then_complete_is_legal(research_db):
    """B1：暂停后剩余 step 跑完 → completed 不应被判非法。"""
    db, _ = research_db
    row = service.get_session_row(db, _create_session(db, mode="deep", cfg=DEEP_CFG))
    service.set_session_status(db, row, "paused")
    service.set_session_status(db, row, "completed")
    assert row.status == "completed"


def test_resume_continues_open_trial_without_duplicate(research_db):
    """I1：续跑复用未终态 trial，不新建重复行；loop_done 补齐后进入下一轮。"""
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 3}
    sid = _create_session(db, mode="deep", cfg=cfg)
    ctrl = service.Control()

    def pausing_evaluator(code, raw_map, cfg):
        out = _fake_evaluator(code, raw_map, cfg)
        ctrl.pause.set()  # 第一次评估后暂停
        return out

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=pausing_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run(ctrl)

    first = service.list_trials(db, sid)
    assert len(first) == 1
    # 暂停发生在评估完成之后：trial 落 interrupted 终态，并记住停在 evaluated
    assert first[0].status == "interrupted"
    assert first[0].resume_status == "evaluated"
    first_trial_id = first[0].id

    row = db.get(ResearchSession, sid)
    spent_calls, spent_tokens = row.llm_calls, row.token_used
    service.set_session_status(db, row, "paused")
    service.set_session_status(db, row, "running")

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    assert row.loop_done == 3
    trials = service.list_trials(db, sid)
    assert len(trials) == 3  # 没有重复 trial
    assert trials[0].id == first_trial_id
    assert all(t.status == "judged" for t in trials)
    # 续跑复用已有反馈，不重复计费
    assert trials[0].llm_calls == first[0].llm_calls
    assert row.llm_calls > spent_calls  # 后续两轮正常产生新成本
    assert row.token_used > spent_tokens


def test_cas_blocks_stale_status_overwrite(research_db):
    """B4：读到的旧状态与 DB 不一致时 CAS 失败，返回 bad_state。"""
    db, _ = research_db
    row = service.get_session_row(db, _create_session(db, mode="deep", cfg=DEEP_CFG))
    service.set_session_status(db, row, "paused")
    # 绕过 ORM 改库，模拟另一个线程先一步改了状态
    db.execute(
        update(ResearchSession).where(ResearchSession.id == row.id).values(status="cancelled"),
        execution_options={"synchronize_session": False},
    )
    with pytest.raises(service.ResearchError) as exc:
        service.set_session_status(db, row, "completed")
    assert exc.value.kind == "bad_state"


def test_clear_control_only_matches_own_job():
    """B3：旧作业退出时不得删掉新作业的 control。"""
    sid = 9527
    ctrl = service.register_control(sid)
    service.bind_control(sid, "job-old")
    service.clear_control(sid, "job-new")  # 不匹配 → 保留
    assert service.get_control(sid) is ctrl
    service.clear_control(sid, "job-old")
    assert service.get_control(sid) is None


def test_cfg_number_keeps_explicit_zero():
    """S2：显式 0（如 icir_floor=0 / temperature=0）不能被 `or` 当成缺省。"""
    assert _cfg_number({"icir_floor": 0}, "icir_floor", 0.15) == 0.0
    assert _cfg_number({}, "icir_floor", 0.15) == 0.15


# ---------- 回归：相关性持久化 + 续跑硬门 ----------


def test_evaluate_persists_corr_columns(research_db):
    """评估完成时把 corr_sota / corr_library 落库，而不是只写进 metrics JSON。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.5),
            db_session_factory=factory,
        ),
    ).run()

    trial = service.list_trials(db, sid)[0]
    assert trial.status == "judged"
    assert trial.corr_library == 0.5
    assert trial.corr_sota is None  # 首轮无 SOTA
    assert "corr_library" not in json.loads(trial.metrics_json)


def test_resume_redundant_factor_still_rejected(research_db):
    """续跑不得重算相关性：首次评估判定冗余（0.95），续跑仍应被拦下。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    ctrl = service.Control()

    def pausing_evaluator(code, raw_map, cfg):
        out = _fake_evaluator(code, raw_map, cfg)
        ctrl.pause.set()  # 评估落库后立即暂停，续跑时 trial 停在 evaluated
        return out

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=pausing_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.95),
            db_session_factory=factory,
        ),
    ).run(ctrl)

    trial = service.list_trials(db, sid)[0]
    assert trial.status == "interrupted"
    assert trial.resume_status == "evaluated"
    assert trial.corr_library == 0.95

    row = db.get(ResearchSession, sid)
    service.set_session_status(db, row, "paused")
    service.set_session_status(db, row, "running")

    # 续跑给一个“看起来不冗余”的相关值：若代码重算就会放行，必须用持久化值
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    judged = db.get(ResearchTrial, trial.id)
    assert judged.status == "judged"
    assert judged.decision is False
    gate = json.loads(judged.judge_json)["gates"]["corr"]
    assert gate["status"] == "fail"
    assert gate["library_value"] == 0.95
    assert "corr(library)" in json.loads(judged.judge_json)["reason"]


def test_resume_missing_corr_is_unknown_not_pass(research_db):
    """历史 trial 没有持久化 corr（列为空）时，续跑必须判 unknown，不能当成通过。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    trial = service.add_trial(
        db,
        sid,
        {
            "loop_idx": 1,
            "candidate_idx": 1,
            "status": "evaluated",
            "hypothesis": "量价背离",
            "task_json": {
                "name": "px_vol",
                "description": "价量背离",
                "formulation": "close/pct_change - volume/pct_change",
            },
            "code": "def calc(df):\n    return df['close'].pct_change(5)\n",
            "metrics_json": {"ic_mean": 0.05, "ic_ir": 0.3},
            "oos_flag": "ok",
        },
    )

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": object()},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    judged = db.get(ResearchTrial, trial.id)
    assert judged.status == "judged"
    assert judged.decision is False
    gossip = json.loads(judged.judge_json)
    assert gossip["gates"]["corr"]["status"] == "unknown"
    assert gossip["gates"]["corr"]["unknown"] == ["因子库"]


def test_get_or_add_trial_reuses_existing_row(research_db):
    """唯一键撞车时复用已有行，不让研究循环整轮失败。"""
    db, _ = research_db
    sid = _create_session(db, mode="deep", cfg=DEEP_CFG)
    first = service.add_trial(db, sid, {"loop_idx": 1, "candidate_idx": 1, "status": "planned"})

    row, created = service.get_or_add_trial(db, sid, {"loop_idx": 1, "candidate_idx": 1, "status": "planned"})

    assert created is False
    assert row.id == first.id
    assert len(service.list_trials(db, sid)) == 1


def test_interrupted_trial_can_resume_from_recorded_step():
    """interrupted 是终态，但允许从 resume_status 记录的步骤重新打开。"""
    ensure_trial_transition("running", "interrupted")
    ensure_trial_transition("interrupted", "evaluated")
    ensure_trial_transition("interrupted", "judged")
    with pytest.raises(InvalidTransition):
        ensure_trial_transition("judged", "interrupted")
