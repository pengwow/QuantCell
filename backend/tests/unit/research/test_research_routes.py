"""研究路由契约测试：创建/列表/详情/暂停/继续/取消/继续研究/并发上限。"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
from collector.db.database import Base
from research import replay, service
from research import routes as research_routes
from research.models import ResearchEvent, ResearchKnowledge, ResearchSession, ResearchTrial
from utils.auth import get_current_user


@pytest.fixture()
def client(monkeypatch):
    # TestClient 在独立线程执行请求，内存库需要允许多线程共享连接
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    def fake_db():
        yield db

    monkeypatch.setattr(research_routes, "get_db_session", fake_db)
    monkeypatch.setattr(
        research_routes,
        "_resolve_llm",
        lambda model_id=None: {"api_key": "k", "base_url": "u", "model": "m"},
    )
    monkeypatch.setattr(research_routes, "_start_job", lambda **kwargs: "job-test")

    app = FastAPI()
    app.include_router(research_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}
    try:
        yield TestClient(app), db
    finally:
        db.close()


PAYLOAD = {
    "mode": "deep",
    "symbols": ["BTCUSDT"],
    "interval": "1h",
    "candle_type": "spot",
    "start": "2026-01-01",
    "end": "2026-06-01",
}


def _create(client, **extra) -> int:
    res = client.post("/api/v1/research/sessions", json={**PAYLOAD, **extra})
    assert res.status_code == 200, res.text
    return res.json()["data"]["session_id"]


def test_create_list_detail(client):
    tc, db = client
    sid = _create(tc, mode="quick", loop_n=1)
    row = db.get(ResearchSession, sid)
    assert row.status == "running"
    assert row.backend_job_id == "job-test"

    res = tc.get("/api/v1/research/sessions")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["total"] == 1
    assert body["sessions"][0]["mode"] == "quick"

    detail = tc.get(f"/api/v1/research/sessions/{sid}").json()["data"]
    assert detail["status"] == "running"
    assert detail["trials"] == []
    assert detail["config"]["loop_n"] == 1


def test_window_and_quick_loop_validation(client):
    tc, _ = client
    bad_window = {**PAYLOAD, "start": "2026-01-01", "end": "2026-01-20"}
    assert tc.post("/api/v1/research/sessions", json=bad_window).status_code == 422
    assert tc.post("/api/v1/research/sessions", json={**PAYLOAD, "mode": "quick", "loop_n": 2}).status_code == 422


def test_pause_resume_cancel(client):
    tc, db = client
    sid = _create(tc)

    assert tc.post(f"/api/v1/research/sessions/{sid}/pause").status_code == 200
    assert db.get(ResearchSession, sid).status == "paused"

    assert tc.post(f"/api/v1/research/sessions/{sid}/resume").status_code == 200
    assert db.get(ResearchSession, sid).status == "running"

    assert tc.post(f"/api/v1/research/sessions/{sid}/cancel").status_code == 200
    assert db.get(ResearchSession, sid).status == "cancelled"
    # 终态不可再暂停
    assert tc.post(f"/api/v1/research/sessions/{sid}/pause").status_code == 409


def test_extend_keeps_mode_and_caps_loops(client):
    tc, db = client
    sid = _create(tc, mode="deep")
    service.set_session_status(db, service.get_session_row(db, sid), "completed")

    res = tc.post(f"/api/v1/research/sessions/{sid}/extend", json={"extra_loops": 2})
    assert res.status_code == 200
    row = service.get_session_row(db, sid)
    cfg = service.session_config(row)
    assert cfg["loop_n"] == 5  # 默认 3 轮 + 追加 2
    assert row.mode == "deep"  # extend 不改写 mode

    # 累计轮次不能超过 MAX_LOOP_N
    service.set_session_status(db, service.get_session_row(db, sid), "completed")
    over = tc.post(f"/api/v1/research/sessions/{sid}/extend", json={"extra_loops": 6})
    assert over.status_code == 409
    assert "累计轮次" in over.json()["detail"]

    # quick 会话也能继续研究：保留原 mode，追加轮次走 deep，并从最佳候选接 SOTA
    quick_id = _create(tc, mode="quick")
    service.set_session_status(db, service.get_session_row(db, quick_id), "completed")
    best = ResearchTrial(
        session_id=quick_id,
        loop_idx=1,
        candidate_idx=1,
        status="evaluated",
        code="def calc(df):\n    return df['close']",
        metrics_json=json.dumps({"ic_ir": 0.4}),
    )
    db.add(best)
    db.commit()
    qres = tc.post(f"/api/v1/research/sessions/{quick_id}/extend", json={"extra_loops": 2})
    assert qres.status_code == 200
    qrow = service.get_session_row(db, quick_id)
    assert qrow.mode == "quick"
    assert qrow.extended_at is not None
    assert qrow.best_trial_id == best.id
    qcfg = service.session_config(qrow)
    assert qcfg["loop_n"] == 3  # quick 已跑 1 轮 + 追加 2
    assert qcfg["extend_deep"] is True


def test_active_session_limit(client):
    tc, _ = client
    first = _create(tc)
    second = _create(tc)
    assert first != second
    third = tc.post("/api/v1/research/sessions", json=PAYLOAD)
    assert third.status_code == 429


def test_unsupported_scenario_returns_400(client):
    tc, _ = client
    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "scenario": "nonexistent"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "scenario_not_supported"


def test_model_scenario_quick_mode_rejected(client):
    """model 场景只有 deep 闭环，quick 显式 400（与 strategy 同口径）。"""
    tc, _ = client
    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "scenario": "model", "mode": "quick"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "mode_not_supported"


def test_quick_pause_is_rejected(client):
    tc, db = client
    sid = _create(tc, mode="quick", loop_n=1)
    res = tc.post(f"/api/v1/research/sessions/{sid}/pause")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "pause_unsupported"
    assert db.get(ResearchSession, sid).status == "running"


def test_events_supports_after_seq_incremental(client):
    """事件持久化后按 seq 严格增量返回，跨进程（多 worker）也能读到。"""
    tc, db = client
    sid = _create(tc)
    service.append_event(db, sid, "info", "loop", "第 1 轮开始")
    service.append_event(db, sid, "info", "trial", "候选生成完成")

    first = tc.get(f"/api/v1/research/sessions/{sid}/events", params={"after_seq": 0}).json()["data"]
    assert [e["seq"] for e in first["events"]] == [1, 2]
    assert first["next_seq"] == 2

    service.append_event(db, sid, "info", "judge", "硬门判定完成")
    second = tc.get(f"/api/v1/research/sessions/{sid}/events", params={"after_seq": first["next_seq"]}).json()["data"]
    # next_seq=2 表示 seq<=2 已消费，严格增量只返回新增的 3
    assert [e["seq"] for e in second["events"]] == [3]
    assert second["next_seq"] == 3


def test_events_unknown_job_returns_empty(client):
    tc, _ = client
    sid = _create(tc)
    data = tc.get(f"/api/v1/research/sessions/{sid}/events").json()["data"]
    assert data == {"session_id": sid, "events": [], "next_seq": 0}


def test_create_with_low_budget_succeeds(client):
    """60k + loop_n=2 低于估算但足够实跑，必须创建成功并返回提示字段。"""
    tc, _ = client
    res = tc.post(
        "/api/v1/research/sessions",
        json={**PAYLOAD, "loop_n": 2, "repair_rounds": 1, "max_llm_calls": 10, "max_tokens": 60_000},
    )
    assert res.status_code == 200, res.text
    sid = res.json()["data"]["session_id"]
    detail = tc.get(f"/api/v1/research/sessions/{sid}").json()["data"]
    assert detail["estimated_tokens"] == 2 * (4 + 1) * 12_000
    assert detail["budget_hint"]


@pytest.mark.parametrize("max_tokens", [0, -1])
def test_create_with_invalid_tokens_returns_422(client, max_tokens):
    """额度硬校验：0/负数在 schema 边界直接 422，不落会话。"""
    tc, db = client
    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "max_tokens": max_tokens})
    assert res.status_code == 422, res.text
    assert db.query(ResearchSession).count() == 0


def test_create_without_llm_returns_409_and_creates_nothing(client, monkeypatch):
    """未配置可用模型时必须在创建阶段明确拒绝，不能建完再在后台静默失败。"""
    tc, db = client
    monkeypatch.setattr(research_routes, "_resolve_llm", lambda model_id=None: None)

    res = tc.post("/api/v1/research/sessions", json={**PAYLOAD, "mode": "quick", "loop_n": 1})

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "llm_unavailable"
    assert "模型" in detail["message"]
    # 关键：不留下 pending/running 的孤儿会话，也没有启动后台作业
    assert db.query(ResearchSession).count() == 0


# ---------- 回放（P2 阶段 1） ----------

# 评估结果的最小结构：_metrics_from_analysis / _oos_metrics 需要的字段
_ANALYSIS = {
    "train": {
        "ic": {"mean": 0.05, "ir": 0.42},
        "inspection": {"coverage": 0.8, "turnover": 0.1},
        "long_short_return": 0.3,
    },
    "test": None,
    "wf": None,
    "train_factor": None,
}


class _StubScenario:
    """因子场景替身：只验证回放编排，不跑真实沙箱。"""

    def evaluate(self, code, raw_map, cfg):
        return _ANALYSIS

    def library_corr(self, series, raw_map):
        return 0.11


def _stub_replay(monkeypatch, analysis=None):
    monkeypatch.setattr(replay, "load_raw_ohlcv", lambda *args, **kwargs: {"BTCUSDT": object()})
    monkeypatch.setattr(replay, "get_scenario", lambda name: _StubScenario())


def _add_trial(db, session_id: int, *, loop_idx: int = 1, candidate_idx: int = 1, **fields) -> ResearchTrial:
    row = ResearchTrial(session_id=session_id, loop_idx=loop_idx, candidate_idx=candidate_idx, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_replay_creates_linked_trial_within_tolerance(client, monkeypatch):
    """同参数回放的 IC_IR 差异在阈值内，且落新行、不覆盖原记录。"""
    tc, db = client
    sid = _create(tc)
    original = _add_trial(
        db,
        sid,
        status="judged",
        code="def calc(df):\n    return df['close']",
        metrics_json=json.dumps({"ic_ir": 0.42, "ic_mean": 0.05}),
        corr_library=0.11,
        corr_sota=0.2,
    )
    _stub_replay(monkeypatch)

    res = tc.post(f"/api/v1/research/sessions/{sid}/trials/{original.id}/replay")
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    meta = data["replay_meta"]
    assert meta["partial"] is False
    assert meta["consistent"] is True
    assert meta["diff"]["ic_ir"] == 0
    assert meta["diff"]["ic_ir"] <= replay.IC_IR_TOLERANCE

    replayed = db.get(ResearchTrial, data["trial"]["id"])
    assert replayed.replay_of_id == original.id
    assert replayed.loop_idx == replay.REPLAY_LOOP_IDX
    # 回放不调用 LLM，成本必须为 0（不能沿用原 trial 的消耗）
    assert replayed.token_used == 0 and replayed.llm_calls == 0
    # 原记录保持原样
    db.refresh(original)
    assert original.status == "judged"
    assert json.loads(original.metrics_json)["ic_ir"] == 0.42
    # corr(SOTA) 不可重算，明确标记
    assert meta["unreproducible"] == ["corr_sota"]

    # 第二次回放换一个 candidate_idx，不撞 (loop,candidate) 唯一索引
    again = tc.post(f"/api/v1/research/sessions/{sid}/trials/{original.id}/replay")
    assert again.status_code == 200, again.text


def test_replay_flags_metric_drift_beyond_tolerance(client, monkeypatch):
    """原指标与回放不一致时 consistent=false，差异值仍如实返回。"""
    tc, db = client
    sid = _create(tc)
    original = _add_trial(
        db,
        sid,
        status="judged",
        code="def calc(df):\n    return df['close']",
        metrics_json=json.dumps({"ic_ir": 0.9}),
    )
    _stub_replay(monkeypatch)

    data = tc.post(f"/api/v1/research/sessions/{sid}/trials/{original.id}/replay").json()["data"]
    assert data["replay_meta"]["consistent"] is False
    assert abs(data["replay_meta"]["diff"]["ic_ir"] - (0.9 - 0.42)) < 1e-9


def test_replay_partial_and_blocking_missing_fields(client, monkeypatch):
    """缺非必需字段 → 部分复现；缺 symbols/interval 或没有代码 → 409。"""
    tc, db = client
    sid = _create(tc)
    original = _add_trial(db, sid, status="judged", code="def calc(df):\n    return df['close']")
    _stub_replay(monkeypatch)

    row = db.get(ResearchSession, sid)
    cfg = json.loads(row.config_json)
    for key in ("start", "end", "test_ratio", "wf_folds"):
        cfg.pop(key, None)
    row.config_json = json.dumps(cfg)
    db.commit()

    res = tc.post(f"/api/v1/research/sessions/{sid}/trials/{original.id}/replay")
    assert res.status_code == 200, res.text
    meta = res.json()["data"]["replay_meta"]
    assert meta["partial"] is True
    assert set(meta["missing"]) == {"start", "end", "test_ratio", "wf_folds"}
    assert any("部分复现" in note for note in meta["notes"])

    # 阻断字段：symbols 缺失直接 409，不落回放行
    cfg.pop("symbols", None)
    row.config_json = json.dumps(cfg)
    db.commit()
    before = db.query(ResearchTrial).count()
    blocked = tc.post(f"/api/v1/research/sessions/{sid}/trials/{original.id}/replay")
    assert blocked.status_code == 409
    assert "symbols" in blocked.json()["detail"]
    assert db.query(ResearchTrial).count() == before

    # 原 trial 没有代码 → 409（重新生成属于另一次 LLM 采样，不叫回放）
    cfg["symbols"] = ["BTCUSDT"]
    row.config_json = json.dumps(cfg)
    db.commit()
    naked = _add_trial(db, sid, loop_idx=2, status="planned", code=None)
    no_code = tc.post(f"/api/v1/research/sessions/{sid}/trials/{naked.id}/replay")
    assert no_code.status_code == 409


def test_replay_is_owner_isolated(client, monkeypatch):
    """非 owner 访问会话/回放一律 404，不泄露是否存在。"""
    tc, db = client
    sid = _create(tc)
    original = _add_trial(db, sid, status="judged", code="def calc(df):\n    return df['close']")
    _stub_replay(monkeypatch)

    tc.app.dependency_overrides[get_current_user] = lambda: {"user_id": "u2"}
    try:
        assert tc.post(f"/api/v1/research/sessions/{sid}/trials/{original.id}/replay").status_code == 404
        assert tc.get(f"/api/v1/research/sessions/{sid}").status_code == 404
    finally:
        tc.app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1"}


# ---------- 批量对比（P2 阶段 2） ----------


def test_batch_trials_enforces_count_bounds(client):
    """对比接口只接受 2–5 条，且不允许重复 id。"""
    tc, db = client
    sid = _create(tc)
    trials = [
        _add_trial(db, sid, loop_idx=idx, status="judged", code=f"def calc(df):\n    return {idx}")
        for idx in range(1, 7)
    ]
    url = f"/api/v1/research/sessions/{sid}/trials/batch"

    assert tc.post(url, json={"trial_ids": [trials[0].id]}).status_code == 422
    assert tc.post(url, json={"trial_ids": [trials[0].id] * 2}).status_code == 422
    assert tc.post(url, json={"trial_ids": [t.id for t in trials]}).status_code == 422

    res = tc.post(url, json={"trial_ids": [trials[0].id, trials[1].id]})
    assert res.status_code == 200, res.text
    assert [row["id"] for row in res.json()["data"]["trials"]] == [trials[0].id, trials[1].id]
    # 对比需要代码 diff，批量接口必须带 code
    assert res.json()["data"]["trials"][0]["code"]


def test_batch_trials_rejects_cross_session(client):
    """跨会话混选按 404 处理，不泄露其他会话的 trial。"""
    tc, db = client
    sid = _create(tc)
    other_sid = _create(tc)
    mine = _add_trial(db, sid, status="judged", code="a")
    theirs = _add_trial(db, other_sid, status="judged", code="b")

    res = tc.post(
        f"/api/v1/research/sessions/{sid}/trials/batch",
        json={"trial_ids": [mine.id, theirs.id]},
    )
    assert res.status_code == 404


def test_batch_trials_preserves_unknown_gate(client):
    """硬门未知状态原样透传，后端不得把它归一化成 pass/fail。"""
    tc, db = client
    sid = _create(tc)
    judge = {
        "decision": False,
        "reason": "未通过：corr(无法判定：缺少 SOTA)",
        "gates": {
            "icir": {"pass": True, "value": 0.5, "floor": 0.3},
            "oos": {"pass": False, "value": "insufficient"},
            "corr": {"pass": False, "status": "unknown", "unknown": ["SOTA"]},
        },
    }
    t1 = _add_trial(db, sid, loop_idx=1, status="judged", code="a", judge_json=json.dumps(judge))
    t2 = _add_trial(db, sid, loop_idx=2, status="judged", code="b", judge_json=json.dumps(judge))

    res = tc.post(f"/api/v1/research/sessions/{sid}/trials/batch", json={"trial_ids": [t1.id, t2.id]})
    assert res.status_code == 200
    for row in res.json()["data"]["trials"]:
        assert row["judge"]["gates"]["corr"]["status"] == "unknown"
        assert row["judge"]["decision"] is False


def test_detail_and_events_survive_control_chars(client):
    """LLM 文本含控制字符时（历史行可能直接落库），详情/事件接口不得 500。"""
    tc, db = client
    sid = _create(tc)
    _add_trial(
        db,
        sid,
        status="judged",
        code="pass",
        hypothesis="a\x00b",
        exception="boom\x01",
        metrics_json='{"ic_ir": 0.3, "note": "n\x02m"}',
        judge_json='{"decision": true, "reason": "ok\x03"}',
    )
    service.append_event(db, sid, "info", "loop", "progress\x04")
    db.commit()

    detail = tc.get(f"/api/v1/research/sessions/{sid}")
    assert detail.status_code == 200, detail.text
    events = tc.get(f"/api/v1/research/sessions/{sid}/events")
    assert events.status_code == 200, events.text
    assert "\x04" not in events.json()["data"]["events"][0]["msg"]
