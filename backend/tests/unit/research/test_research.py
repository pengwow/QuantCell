"""研究模块 P0 核心单测：状态机 / 硬门 / quick 映射 / 预算 / 闭环。"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import contextmanager
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
from collector.db.database import Base
from research import agents, consts, service
from research.judge import evaluate_gates
from research.loop import (
    Budget,
    BudgetExhausted,
    CancelSignal,
    LoopDeps,
    ResearchLoop,
    _cfg_number,
    default_llm_call,
)
from research.models import ResearchEvent, ResearchKnowledge, ResearchSession, ResearchTrial
from research.quick import map_candidates_to_trials, session_cost_from_stats
from research.scenarios.base import ScenarioDefaults
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
            ResearchEvent.__table__,
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


# 假数据：loop 只按 len() 估算训练段根数，桩评估器不读内容
_ONE_BAR = pd.DataFrame({"close": [1.0]})

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
    def _call(system: str, user: str, stage: str | None = None) -> tuple[str, dict]:
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


class _StubScenario(ScenarioDefaults):
    """闭环协议测试桩：默认钩子继承 ScenarioDefaults（agents 的 factor 实现），
    只替掉依赖真实因子库/编码器的两点（build_tasks、library_corr）。"""

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


def test_quick_candidate_usage_maps_to_trial_cost():
    """quick 的每个候选要带调用次数与 token，否则 trial 级成本永远为 0。"""
    trials = map_candidates_to_trials(
        [
            {
                "candidate": 1,
                "status": "success",
                "code": "c1",
                "usage": {"total_tokens": 3974},
            }
        ]
    )
    assert trials[0]["llm_calls"] == 1
    assert trials[0]["token_used"] == 3974


def test_trial_to_dict_sanitizes_control_chars(research_db):
    """LLM 文本带控制字符时，写库与序列化都不能把接口打挂。"""
    db, _ = research_db
    sid = _create_session(db)
    row = service.add_trial(
        db,
        sid,
        {
            "loop_idx": 1,
            "candidate_idx": 1,
            "status": "evaluated",
            "hypothesis": "a\x00b\x01c",
            "exception": "boom\x07",
            "metrics_json": {"ic_ir": 0.2, "note": "x\x00y"},
        },
    )
    data = service.trial_to_dict(row)
    assert "\x00" not in data["hypothesis"]
    assert "\x07" not in data["exception"]
    assert data["metrics"]["note"] == "xy"
    json.dumps(data, ensure_ascii=False)  # 序列化不得抛异常

    # 历史行绕过 _dumps 直接落了原始控制字符：读侧 _loads 也必须清洗后解析
    row.metrics_json = '{"ic_ir": 0.2, "note": "x\x01y"}'
    db.commit()
    assert service.trial_to_dict(row)["metrics"]["ic_ir"] == 0.2


# ---------- 预算 ----------


def test_budget_short_circuit():
    budget = Budget(max_calls=1, max_tokens=100)
    budget.spend_call()
    with pytest.raises(BudgetExhausted):
        budget.spend_call()
    # 预留失败才拒绝；实际用量超出上限只结算、不抛异常（避免丢弃已拿到的产物）
    with pytest.raises(BudgetExhausted):
        budget.reserve_tokens(101)
    budget.reserve_tokens(50)
    budget.settle_tokens(120, 50)
    assert budget.tokens_used == 120
    assert budget.reserved_tokens == 0


def test_budget_actual_overage_is_settled_not_rejected():
    """实测 32804 超 30000 时不能丢弃合法代码：按实际结算，不再抛异常。"""
    budget = Budget(max_calls=10, max_tokens=30_000)
    reserved = budget.reserve_tokens(consts.EST_TOKENS_PER_CALL)
    budget.settle_tokens(32_804, reserved)
    assert budget.tokens_used == 32_804
    assert budget.reserved_tokens == 0


def test_empty_code_reason_mentions_truncation_without_repair():
    """repair_rounds=0 时不能写“修复后仍失败”，要指向未启用修复/输出截断。"""
    from research.loop import _empty_code_reason

    reason = _empty_code_reason({"finish_reason": "length"}, 0)
    assert "截断" in reason and "未启用" in reason
    assert "修复后仍未" not in reason
    assert "修复后仍" in _empty_code_reason({"finish_reason": "length"}, 2)
    assert "未启用" in _empty_code_reason({"finish_reason": "stop"}, 0)


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
        data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
    # trial 级成本：每轮 4 次调用、每次 10 tokens 都归属到该条 trial
    assert all(t.llm_calls == 4 and t.token_used == 40 for t in trials)


def test_duplicate_factor_is_marked_and_consumes_loop(research_db):
    """两轮产出同一个因子：第 2 轮判 duplicate，不再反馈/judge，但该轮照常消耗。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 2})
    prompts: list[str] = []

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call(prompts),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 1.0,  # 与历史因子完全等价（含方向翻转）
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    assert row.loop_done == 2  # 判重轮也计入进度，不会卡在同一轮重试
    trials = service.list_trials(db, sid)
    assert [t.status for t in trials] == ["judged", "duplicate"]
    assert trials[1].decision is False
    assert "高度相关" in trials[1].exception
    assert trials[1].judge_json is None  # 未进入 judge
    # 判重轮只花 propose/plan/code 三次调用，没有反馈这次调用
    assert prompts.count(agents.FEEDBACK_SYSTEM) == 1
    assert row.llm_calls == 7


def test_duplicate_threshold_is_configurable(research_db):
    """阈值走 cfg duplicate_corr_threshold，默认值集中在 consts。"""
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 2, "duplicate_corr_threshold": 0.5}
    sid = _create_session(db, mode="deep", cfg=cfg)

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.6,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    assert [t.status for t in service.list_trials(db, sid)] == ["judged", "duplicate"]


def test_deep_trial_failure_does_not_kill_session(research_db):
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 2, "repair_rounds": 0}
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
    # 创建阶段会拦截明显不够的预算，这里先按合法预算建会话，再手动压到 1 次，
    # 验证运行期 Budget 的短路行为
    sid = _create_session(db, mode="deep", cfg=DEEP_CFG)
    service.update_session_fields(db, sid, config_json=json.dumps({**DEEP_CFG, "max_llm_calls": 1}))
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
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


def test_deep_repair_loop_rewrites_code_and_records_summary(research_db):
    """评估失败时回灌错误摘要重写代码，修复轮次与摘要落库。"""
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 1, "repair_rounds": 2}
    sid = _create_session(db, mode="deep", cfg=cfg)
    calls = {"n": 0}

    def flaky_evaluator(code, raw_map, cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("沙箱超时：calc 未返回 Series")
        return _fake_evaluator(code, raw_map, cfg)

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=flaky_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    row = db.get(ResearchSession, sid)
    assert row.status == "completed"
    trial = service.list_trials(db, sid)[0]
    assert trial.status == "judged", trial.exception
    repair = json.loads(trial.repair_json)
    assert len(repair) == 1
    assert repair[0]["kind"] == "runtime_error"
    assert "沙箱超时" in repair[0]["error"]
    # 修复轮也要计一次调用：propose+plan+code+repair+feedback = 5
    assert row.llm_calls == 5


# ---------- 失败签名知识复用 ----------


def test_failure_signature_ignores_volatile_values():
    """同种错误只是行号/取值不同，必须归一到同一签名。"""
    a = service.failure_signature("runtime_error", "沙箱超时：calc 未返回 Series at bar 123")
    b = service.failure_signature("runtime_error", "沙箱超时：calc 未返回 Series at bar 987654")
    assert a == b
    assert a.startswith("runtime_error|")
    assert service.failure_signature("timeout", "超时 30s") != a


def test_record_failure_hits_existing_knowledge(research_db):
    """同签名第二次出现时命中已存知识（hit_count 累加，不堆新行）。"""
    db, _ = research_db
    first = service.record_failure(
        db, owner_id="u1", session_id=None, trial_id=None, kind="runtime_error", error="calc 返回 None at bar 12"
    )
    second = service.record_failure(
        db, owner_id="u1", session_id=None, trial_id=None, kind="runtime_error", error="calc 返回 None at bar 345"
    )
    assert second.id == first.id
    assert second.hit_count == 2
    assert db.query(ResearchKnowledge).count() == 1
    rows = service.list_failure_knowledge(db, "u1")
    assert rows[0]["hit_count"] == 2
    # 其他 owner 的知识不串用
    assert service.list_failure_knowledge(db, "u2") == []


def test_render_context_injects_knowledge():
    ctx = agents.render_context(
        [],
        None,
        knowledge=[{"signature": "runtime_error|calc 返回 #", "hit_count": 3, "hint": "价量背离"}],
    )
    assert "已知失败模式" in ctx
    assert "runtime_error|calc 返回 #" in ctx
    assert "命中 3 次" in ctx


def test_failed_loop_knowledge_appears_in_next_loop_context(research_db):
    """第一轮失败沉淀签名，第二轮 propose/plan 的上下文里必须能看到它。"""
    db, factory = research_db
    cfg = {**DEEP_CFG, "loop_n": 2, "repair_rounds": 0}
    sid = _create_session(db, mode="deep", cfg=cfg)
    user_prompts: list[str] = []
    calls = {"n": 0}

    def llm_call(system: str, user: str, stage: str | None = None) -> tuple[str, dict]:
        user_prompts.append(user)
        return _fake_llm_call([])(system, user, stage)

    def flaky_evaluator(code, raw_map, cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("沙箱超时：calc 未返回 Series at bar 123")
        return _fake_evaluator(code, raw_map, cfg)

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=llm_call,
            evaluator=flaky_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    assert [t.status for t in service.list_trials(db, sid)] == ["failed", "judged"]
    knowledge = service.list_failure_knowledge(db, "u1")
    assert knowledge and knowledge[0]["hit_count"] == 1
    # 第二轮（假设/规划）的 prompt 里带上了第一轮的失败签名
    # 第一轮在评估失败时退出，只发了 propose/plan/code 三次调用
    second_loop_prompts = user_prompts[3:]
    assert any("已知失败模式" in p for p in second_loop_prompts)


def test_knowledge_short_circuit_skips_repeated_failed_task(research_db):
    """失败签名命中阈值后，相同任务直接标 skipped，不再发起 code LLM 调用。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    task_desc = "价量背离"
    # 同一失败签名累计命中阈值（record_failure 同签名去重累加 hit_count 到一行）
    for _ in range(consts.KNOWLEDGE_BLOCK_THRESHOLD):
        service.record_failure(
            db,
            owner_id="u1",
            session_id=None,
            trial_id=None,
            kind="eval_error",
            error="因子窗口超出数据长度",
            hint=task_desc,
        )
    db.commit()

    prompts: list[str] = []
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call(prompts),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    trial = service.list_trials(db, sid)[0]
    assert trial.status == "skipped"
    assert not trial.decision
    assert not trial.code
    # 短路发生在 code 之前：code 调用（系统提示含"顶级加密"）从未发出
    assert "顶级加密" not in "".join(prompts)


def test_knowledge_short_circuit_not_triggered_below_threshold(research_db):
    """同任务提示词但签名未达阈值（或 hint 不同）时不拦，code 照常执行。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    # 同 hint 但不同签名（另一种 kind），hit_count=1 未达阈值
    service.record_failure(
        db,
        owner_id="u1",
        session_id=None,
        trial_id=None,
        kind="shape_error",
        error="窗口不足",
        hint="价量背离",
    )
    db.commit()

    prompts: list[str] = []
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call(prompts),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()

    trial = service.list_trials(db, sid)[0]
    assert trial.status != "skipped"
    assert trial.code
    assert "顶级加密" in "".join(prompts)


# ---------- 创建时预算前置校验 ----------


def test_estimate_budget_by_candidates_and_loops():
    calls, tokens = service.estimate_budget("deep", {"loop_n": 3, "repair_rounds": 0}, 1)
    assert calls == 3 * 4
    assert tokens == calls * consts.EST_TOKENS_PER_CALL
    calls, _ = service.estimate_budget("quick", {"loop_n": 1}, 4)
    assert calls == 5  # 4 个候选各 1 次 + 1 次收尾
    calls, _ = service.estimate_budget("deep", {"loop_n": 2, "repair_rounds": 2}, 1)
    assert calls == 2 * (4 + 2)


def test_create_allows_budget_below_estimate(research_db):
    """估算低于上限只提示不拦截：60k + loop_n=2 必须能创建并返回 budget_hint。"""
    db, _ = research_db
    row = service.create_session(
        db,
        owner_id="u1",
        name="deep-low-budget",
        mode="deep",
        scenario="factor",
        config={**DEEP_CFG, "loop_n": 2, "repair_rounds": 1, "max_llm_calls": 10, "max_tokens": 60_000},
        n_candidates=1,
    )
    assert row.status == "pending"
    data = service.session_to_dict(row, best_trial=None)
    assert data["estimated_calls"] == 2 * (consts.DEEP_CALLS_PER_LOOP + 1)
    assert data["estimated_tokens"] == data["estimated_calls"] * consts.EST_TOKENS_PER_CALL
    assert data["estimated_tokens"] > data["max_tokens"]
    assert "仅提示" in (data["budget_hint"] or "")


# ---------- 排队位次（PRD §9）----------


def test_queue_position_pending_and_running(research_db):
    """pending 会话显示同 owner 队列位次；运行后位次重新计算、running 本身无位次。"""
    db, _ = research_db
    s1 = service.create_session(
        db, owner_id="u1", name="q-1", mode="deep", scenario="factor", config={}, n_candidates=1
    )
    s2 = service.create_session(
        db, owner_id="u1", name="q-2", mode="deep", scenario="factor", config={}, n_candidates=1
    )
    s3 = service.create_session(
        db, owner_id="u2", name="q-3", mode="quick", scenario="factor", config={}, n_candidates=1
    )

    assert service.session_to_dict(s1, db=db)["queue_position"] == 1
    assert service.session_to_dict(s2, db=db)["queue_position"] == 2
    # 位次按 owner 隔离：u2 只看自己的队列
    assert service.session_to_dict(s3, db=db)["queue_position"] == 1

    # 先提交的转 running 后：自己脱离队列，后者顶上
    service.set_session_status(db, s1, "running")
    data = service.session_to_dict(s1, db=db)
    assert data["queue_position"] is None
    assert service.session_to_dict(s2, db=db)["queue_position"] == 1


def test_queue_position_none_without_db():
    """不传 db（序列化复用场景）时位次为 None，不能 Query 出错。"""
    row = service.ResearchSession(owner_id="u1", name="q", status="pending", mode="deep", scenario="factor")
    assert service.session_to_dict(row)["queue_position"] is None


# ---------- 过程事件持久化 ----------


def test_event_retention_prunes_oldest(research_db, monkeypatch):
    """事件表按会话裁剪，只保留最近 EVENTS_RETENTION 条。"""
    db, _ = research_db
    monkeypatch.setattr(consts, "EVENTS_RETENTION", 3)
    sid = _create_session(db)
    for i in range(5):
        service.append_event(db, sid, "info", "loop", f"e{i}")
    rows = db.query(ResearchEvent).order_by(ResearchEvent.id).all()
    assert [row.msg for row in rows] == ["e2", "e3", "e4"]


# ---------- quick → extend：追加轮次走 deep 并从已有 SOTA 继续 ----------


def test_extended_quick_runs_deep_from_sota_and_judges_redundant(research_db):
    db, factory = research_db
    sid = _create_session(db, mode="quick", cfg={**DEEP_CFG, "loop_n": 1})
    # 模拟 quick 轮跑完留下的最佳候选
    best = ResearchTrial(
        session_id=sid,
        loop_idx=1,
        candidate_idx=1,
        status="evaluated",
        code="def calc(df):\n    return df['close']",
        metrics_json=json.dumps({"ic_ir": 0.4}),
    )
    db.add(best)
    db.commit()
    service.update_session_fields(
        db,
        sid,
        loop_done=1,
        best_trial_id=best.id,
        config_json=json.dumps({**DEEP_CFG, "loop_n": 2, "extend_deep": True}),
    )

    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=_fake_llm_call([]),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.8,  # 高于 judge 阈值 0.7、低于判重阈值 0.9 → 仍走 judge 判冗余
            scenario=_StubScenario(0.4),
            db_session_factory=factory,
        ),
    ).run()

    # quick 的候选不重跑，追加轮次落在 loop 2；mode 保持 quick
    assert [row.loop_idx for row in service.list_trials(db, sid)] == [1, 2]
    trial = service.find_trial(db, sid, 2, 1)
    assert trial.status == "judged"
    assert trial.decision is False  # 仍能判冗余
    assert db.get(ResearchSession, sid).mode == "quick"


class _BlockingBackend:
    """模拟在飞 LLM：正常前两次调用返回合法 JSON，代码生成调用永不返回。"""

    def __init__(self, *, stall_from: int = 3):
        self.calls = 0
        self.stall_from = stall_from

    async def chat_async(self, messages: list[dict]) -> dict:
        self.calls += 1
        system = messages[0]["content"]
        if self.calls >= self.stall_from:
            await asyncio.Event().wait()  # 永不返回，靠外部取消/超时退出
        if "量化因子研究员" in system:
            content = '{"hypothesis": "量价背离", "reason": "价涨量缩"}'
        elif "量化实验规划员" in system:
            content = (
                '{"tasks": [{"name": "px_vol", "description": "价量背离",'
                ' "formulation": "close/pct_change - volume/pct_change"}]}'
            )
        else:
            content = '{"observations": "ok", "evaluation": "稳定", "reason": ""}'
        return {"content": content, "finish_reason": "Stop", "total_tokens": 10}


def test_default_llm_call_hard_timeout_aborts_inflight():
    """非流式请求也必须有硬超时：超时后只发生过一次请求。"""
    backend = _BlockingBackend(stall_from=1)
    control = service.Control()
    llm = default_llm_call(backend, control=control, timeout_secs=0.3)

    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        llm("system", "user")
    assert time.monotonic() - t0 < 3
    assert backend.calls == 1  # 超时后没有再次发起调用


def test_default_llm_call_cancel_aborts_inflight():
    """cancel Event 生效后立即中止在飞请求，而不是等它自然返回。"""
    backend = _BlockingBackend(stall_from=1)
    control = service.Control()
    llm = default_llm_call(backend, control=control, timeout_secs=10)
    threading.Timer(0.3, control.cancel.set).start()

    t0 = time.monotonic()
    with pytest.raises(CancelSignal):
        llm("system", "user")
    assert time.monotonic() - t0 < 2


def test_llm_timeout_marks_trial_failed_and_books_cost(research_db):
    """单次调用超时：trial 落 failed 终态，已完成的调用成本仍记账。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    control = service.Control()

    t0 = time.monotonic()
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=default_llm_call(_BlockingBackend(stall_from=3), control=control, timeout_secs=0.3),
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run(control)
    assert time.monotonic() - t0 < 3

    row = db.get(ResearchSession, sid)
    trials = service.list_trials(db, sid)
    assert len(trials) == 1
    assert trials[0].status == "failed"
    assert "超时" in (trials[0].exception or "")
    # propose/plan 两次调用已完成 → 次数与 token 都要记账；code 阶段超时 + 重试两次都失败
    assert row.llm_calls == 4
    assert row.token_used == 20


def test_cancel_during_code_marks_trial_interrupted(research_db):
    """代码生成阶段取消：在飞调用被中断，trial 落 interrupted 而非 key 泄漏运行态。"""
    db, factory = research_db
    sid = _create_session(db, mode="deep", cfg={**DEEP_CFG, "loop_n": 1})
    control = service.Control()

    t0 = time.monotonic()
    timer = threading.Timer(0.4, control.cancel.set)
    timer.start()
    try:
        ResearchLoop(
            sid,
            LoopDeps(
                # 超时刻意放宽到 10s：验证真正生效的是取消而不是超时
                llm_call=default_llm_call(_BlockingBackend(stall_from=3), control=control, timeout_secs=10),
                evaluator=_fake_evaluator,
                data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
                corr_fn=lambda a, b: 0.2,
                scenario=_StubScenario(0.2),
                db_session_factory=factory,
            ),
        ).run(control)
    finally:
        timer.cancel()
    assert time.monotonic() - t0 < 2

    trials = service.list_trials(db, sid)
    assert len(trials) == 1
    assert trials[0].status == "interrupted"
    assert trials[0].resume_status == "coding"


# ---------- 阶段级超时 + code 阶段一次重试 ----------


def _code_retry_llm(code_behaviors: list[Any]):
    """code 阶段按顺序消费 behaviors（Exception 抛错、tuple 原样返回），其余阶段走默认真实现。"""
    base = _fake_llm_call([])
    state = {"code": 0}

    def _call(system: str, user: str, stage: str | None = None) -> tuple[str, dict]:
        if stage != "code":
            return base(system, user, stage)
        idx = state["code"]
        state["code"] += 1
        behavior = code_behaviors[min(idx, len(code_behaviors) - 1)]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    return _call


def _run_deep_once(db, factory, *, llm_call, cfg=None):
    sid = _create_session(db, mode="deep", cfg=cfg or {**DEEP_CFG, "loop_n": 1})
    ResearchLoop(
        sid,
        LoopDeps(
            llm_call=llm_call,
            evaluator=_fake_evaluator,
            data_loader=lambda cfg: {"BTCUSDT": _ONE_BAR},
            corr_fn=lambda a, b: 0.2,
            scenario=_StubScenario(0.2),
            db_session_factory=factory,
        ),
    ).run()
    return sid


def test_resolve_stage_timeouts_prefers_explicit_then_global(research_db):
    """阶段超时：显式阶段值 > 全局 llm_call_timeout_secs > consts 阶段默认；None 不算显式。"""
    from research.loop import resolve_stage_timeouts

    defaults = resolve_stage_timeouts({})
    assert defaults["code"] == consts.DEFAULT_STAGE_TIMEOUT_SECS["code"] == 300
    assert defaults["propose"] == 180

    global_only = resolve_stage_timeouts({"llm_call_timeout_secs": 240})
    assert set(global_only.values()) == {240.0}

    mixed = resolve_stage_timeouts({"llm_call_timeout_secs": 240, "llm_code_timeout_secs": 360})
    assert mixed["code"] == 360
    assert mixed["propose"] == 240
    # 显式 None 仍然沿用全局，而不是被误当成 0
    assert resolve_stage_timeouts({"llm_call_timeout_secs": 240, "llm_code_timeout_secs": None})["code"] == 240


def test_code_stage_retry_succeeds_after_timeout(research_db):
    """code 第一次超时、重试成功：trial 正常 judged，重试调用计入成本。"""
    db, factory = research_db
    code = ("```python\ndef calc(df):\n    return df['close'].pct_change(5)\n```", {"total_tokens": 10})
    sid = _run_deep_once(
        db,
        factory,
        llm_call=_code_retry_llm([TimeoutError("LLM 单次调用超时（>300s，stage=code）"), code]),
    )
    trials = service.list_trials(db, sid)
    assert trials[0].status == "judged"
    # propose/plan + code 两次 + feedback
    assert trials[0].llm_calls == 5
    # 超时那次 token=0，其余四次各 10
    assert trials[0].token_used == 40
    assert db.get(ResearchSession, sid).llm_calls == 5


def test_code_stage_retry_still_timeout_marks_failed(research_db):
    """两次都超时：trial 落 failed，exception 明确标注 timeout，且只重试一次。"""
    db, factory = research_db
    sid = _run_deep_once(
        db,
        factory,
        llm_call=_code_retry_llm([TimeoutError("LLM 单次调用超时（>300s，stage=code）")] * 5),
    )
    trials = service.list_trials(db, sid)
    assert trials[0].status == "failed"
    assert "timeout" in (trials[0].exception or "")
    assert trials[0].llm_calls == 4  # propose + plan + 两次 code
    assert db.get(ResearchSession, sid).llm_calls == 4


def test_code_stage_retry_on_empty_output(research_db):
    """空内容同样算一次失败并重试；重试拿到代码后正常继续。"""
    db, factory = research_db
    code = ("```python\ndef calc(df):\n    return df['close'].pct_change(5)\n```", {"total_tokens": 10})
    sid = _run_deep_once(
        db,
        factory,
        llm_call=_code_retry_llm([("", {"total_tokens": 10, "finish_reason": "length"}), code]),
    )
    trials = service.list_trials(db, sid)
    assert trials[0].status == "judged"
    assert trials[0].llm_calls == 5
    assert trials[0].token_used == 50  # 空输出那次也计 token


# ---------- 多品种聚合口径 ----------


def test_render_context_injects_data_facts():
    """数据事实段必须出现在上下文里：单品种契约 + 训练段根数，防止超长窗口假设。"""
    from research.agents import render_context

    text = render_context(
        [],
        None,
        data_note=(
            "- 品种数：2；训练段约 488 根 K 线\n"
            "- 代码按单品种执行（系统逐品种跑一遍再拼成截面面板），df 没有 code/date 列；"
            "不要用 np.concatenate / DataFrame.get / 跨品种拼接"
        ),
    )
    assert "## 数据事实" in text
    assert "488" in text
    assert "df 没有 code/date 列" in text


def test_library_corr_takes_max_abs_across_reference_panels():
    """多参考因子下 library_corr 取最大 |池化秩相关|（含方向翻转），不是平均。"""
    from research.scenarios.factor import FactorScenario, rank_corr

    idx = pd.MultiIndex.from_product(
        [pd.date_range("2026-01-01", periods=40, freq="1h"), ["BTCUSDT", "ETHUSDT"]],
        names=["datetime", "symbol"],
    )
    rng = np.random.default_rng(11)
    target = pd.Series(rng.normal(size=len(idx)), index=idx)
    unrelated = pd.Series(rng.normal(size=len(idx)), index=idx)
    flipped = -target

    # 只验证聚合口径：绕过 FactorService，直接给定期望的参考面板
    scenario = FactorScenario.__new__(FactorScenario)
    scenario._library_panels = [unrelated, flipped]

    assert scenario.library_corr(target, {}) == pytest.approx(1.0)
    assert abs(rank_corr(target, unrelated)) < 0.5
    # 池化样本量按 (datetime, symbol) 全部行计：40×2 ≥ min_samples(50)
    assert rank_corr(target, target) == pytest.approx(1.0)


def test_seed_text_built_once_and_reports_missing(monkeypatch, caplog):
    """「基于已有因子研究」：种子上下文首查后缓存；因子缺失时上报事件并忽略。"""
    import research.loop as loop_mod

    events: list[tuple[str, str]] = []
    calls = {"n": 0}

    def fake_load(name: str):
        calls["n"] += 1
        if name == "seed_a":
            return {
                "name": "seed_a",
                "description": "动量类",
                "code": "f = close.pct_change(5)",
                "metrics": {"ic_ir": 0.4, "label": "文本值不该进上下文"},
            }
        return None

    monkeypatch.setattr(loop_mod, "load_seed_factor", fake_load)
    loop = ResearchLoop(1, LoopDeps(event_fn=lambda stage, msg: events.append((stage, msg))))

    text = loop._seed_text({"seed_factor": "seed_a"})
    assert "seed_a" in text and "close.pct_change(5)" in text
    assert "ic_ir=0.4" in text and "文本值" not in text  # 非数值指标被过滤
    assert loop._seed_text({"seed_factor": "seed_a"}) == text
    assert calls["n"] == 1  # 每会话只查一次库

    fresh = ResearchLoop(2, LoopDeps(event_fn=lambda stage, msg: events.append((stage, msg))))
    assert fresh._seed_text({"seed_factor": "nope"}) == ""
    assert fresh._seed_text({}) == ""  # 未带种子：直接空，不查库
    stage, msg = events[-1]
    assert stage == "session.seed_missing" and "nope" in msg


def test_delete_session(research_db):
    """删除会话：非终态拦截 / 终态级联清 trials+events / owner 隔离。"""
    db, _ = research_db
    sid = _create_session(db, mode="deep", cfg=DEEP_CFG)
    db.add(ResearchTrial(session_id=sid, loop_idx=1, candidate_idx=1))
    db.add(ResearchEvent(session_id=sid, msg="stage log", ts=1.0))
    db.commit()

    # running 非终态：拒绝删除
    with pytest.raises(service.ResearchError) as ei:
        service.delete_session(db, sid, owner_id="u1")
    assert ei.value.kind == "bad_state"

    # 取消落到终态后可删，trials/events 一并清理
    row = service.get_session_row(db, sid, owner_id="u1")
    service.set_session_status(db, row, "cancelled")
    service.delete_session(db, sid, owner_id="u1")
    assert db.get(ResearchSession, sid) is None
    assert db.query(ResearchTrial).filter(ResearchTrial.session_id == sid).count() == 0
    assert db.query(ResearchEvent).filter(ResearchEvent.session_id == sid).count() == 0

    # owner 隔离：不能删别人的会话（视为不存在）
    other = service.create_session(
        db, owner_id="u2", name="u2", mode="quick", scenario="factor", config={}, n_candidates=1
    )
    with pytest.raises(service.ResearchError) as ei2:
        service.delete_session(db, other.id, owner_id="u1")
    assert ei2.value.kind == "not_found"
