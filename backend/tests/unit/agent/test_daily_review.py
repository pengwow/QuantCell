"""P4-4 每日复盘单测：数据聚合 / 模板报告 / LLM 降级 / 端点契约 / 会话注入。

复用 conftest 的 in-memory 库夹具（SessionLocal 已被替换，daily_review 的
get_db_session 运行期从同一模块取 SessionLocal，故自动打到测试库）；
决策录制与模型旁车用 tmp_path，不依赖真实 data 目录。
"""

import asyncio
import json
from datetime import date, datetime, time

import pytest

from agent.core import daily_review as dr
from worker import models as wm

DAY = date(2026, 11, 17)


@pytest.fixture
def review_db(agent_session_factory, monkeypatch):
    """把会话入口指向 in-memory 库并清空 worker 相关表。

    不能只替换 collector.db.database.SessionLocal：utils.db_session.get_db_session
    会调 init_database_config()，后者把模块属性重绑到文件库。故直接替换
    utils.db_session.get_db_session —— daily_review 与 worker.service 都在函数内
    import 该名字，运行期读取模块属性，一处 patch 覆盖两者。
    """
    from contextlib import contextmanager

    @contextmanager
    def _session():
        db = agent_session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr("utils.db_session.get_db_session", _session)
    with agent_session_factory() as db:
        db.query(wm.WorkerPosition).delete()
        db.query(wm.WorkerOrder).delete()
        db.query(wm.WorkerTrade).delete()
        db.query(wm.Worker).delete()
        db.commit()
    return agent_session_factory


@pytest.fixture
def clean_models(monkeypatch, tmp_path):
    """模型旁车目录指向 tmp_path（默认空，可写入 meta.json）。"""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(dr, "_models_dir", lambda: models_dir)
    return models_dir


@pytest.fixture
def replay_dir(monkeypatch, tmp_path):
    """决策录制目录指向 tmp_path（worker_replay_path 按环境变量解析）。"""
    path = tmp_path / "decision_replay"
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(path))
    return path


def _seed_worker(factory, *, name="w-agg", status="running", strategy_type="rule"):
    with factory() as db:
        worker = wm.Worker(name=name, status=status, strategy_type=strategy_type)
        db.add(worker)
        db.commit()
        db.refresh(worker)
        return worker.id


def _add_trade(factory, worker_id, *, pnl, when):
    with factory() as db:
        db.add(
            wm.WorkerTrade(
                worker_id=worker_id,
                fill_id=f"paper:{worker_id}:{when.isoformat()}:{pnl}",
                symbol="BTCUSDT",
                side="buy",
                position_side="both",
                reduce_only=False,
                order_type="market",
                quantity=1.0,
                price=100.0,
                notional=100.0,
                fee=0.1,
                realized_pnl=pnl,
                created_at=when,
            )
        )
        db.commit()


def _add_order(factory, worker_id, *, client_order_id, status, when):
    with factory() as db:
        db.add(
            wm.WorkerOrder(
                worker_id=worker_id,
                client_order_id=client_order_id,
                symbol="BTCUSDT",
                side="buy",
                position_side="both",
                reduce_only=False,
                order_type="market",
                quantity=1.0,
                price=100.0,
                filled_quantity=1.0,
                avg_fill_price=100.0,
                status=status,
                created_at=when,
            )
        )
        db.commit()


def _add_position(factory, worker_id, *, position_id, symbol="BTCUSDT", unrealized_pnl, entry=100.0, current=80.0):
    with factory() as db:
        db.add(
            wm.WorkerPosition(
                worker_id=worker_id,
                position_id=position_id,
                symbol=symbol,
                position_side="long",
                quantity=1.0,
                entry_price=entry,
                current_price=current,
                unrealized_pnl=unrealized_pnl,
                status="OPEN",
            )
        )
        db.commit()


def _write_decision(replay_dir, worker_id, *, action, ts):
    path = replay_dir / "worker" / f"worker_{worker_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "fingerprint": f"fp-{action}-{ts}",
        "decision": {"action": action, "confidence": 0.8, "source": "rl"},
        "state": {"symbol": "BTCUSDT"},
        "questions": {},
        "ts": ts,
        "_decider": "RL:test",
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_meta(models_dir, name, *, sharpe, ret, created_at):
    (models_dir / f"{name}.meta.json").write_text(
        json.dumps(
            {
                "model_id": name,
                "created_at": created_at,
                "oos": {"sharpe_ratio": sharpe, "total_return_pct": ret},
            }
        ),
        encoding="utf-8",
    )


# ---------- 数据聚合 ----------


def test_collect_sections_aggregates_workers(review_db, clean_models, replay_dir):
    running = _seed_worker(review_db, name="w-running", status="running")
    _seed_worker(review_db, name="w-stopped", status="stopped")
    noon = datetime.combine(DAY, time(12, 0))
    _add_trade(review_db, running, pnl=30.0, when=noon)
    _add_trade(review_db, running, pnl=-10.0, when=noon)
    _add_order(review_db, running, client_order_id="co-1", status="FILLED", when=noon)
    _add_position(review_db, running, position_id="pos-1", unrealized_pnl=-20.0)
    _write_decision(replay_dir, running, action="buy", ts=f"{DAY.isoformat()}T12:00:00.000000000Z")
    _write_decision(replay_dir, running, action="hold", ts=f"{DAY.isoformat()}T13:00:00.000000000Z")
    _write_decision(replay_dir, running, action="sell", ts="2026-11-18T00:01:00.000000000Z")  # 跨日，应被排除
    # 同一模型族两轮 OOS 均不达标 → blocked
    _write_meta(clean_models, "BTCUSDT_ppo_1700000000", sharpe=-1.0, ret=-2.0, created_at="2026-11-16T00:00:00Z")
    _write_meta(clean_models, "BTCUSDT_ppo_1700000100", sharpe=-0.5, ret=-1.0, created_at="2026-11-17T00:00:00Z")

    sections = dr.collect_sections(DAY)

    # overview：只统计活跃 worker，昨日窗口
    assert sections["overview"]["active_workers"] == 1
    assert sections["overview"]["total_pnl"] == 20.0
    assert sections["overview"]["total_trades"] == 2
    assert sections["overview"]["win_rate"] == 50.0
    assert sections["overview"]["orders"] == 1
    assert sections["overview"]["decisions"] == 2  # 只计当日，跨日那条被排除

    worker = sections["workers"][0]
    assert worker["worker_id"] == running
    assert worker["order_status"] == {"FILLED": 1}
    assert worker["decisions"]["by_action"] == {"buy": 1, "hold": 1}
    assert len(worker["positions"]) == 1

    # 异常：-20% 高浮亏 + 单仓 100% 集中度
    types = {a["type"] for a in sections["anomalies"]}
    assert types == {"position_loss", "position_concentration"}
    assert all(a["worker_id"] == running for a in sections["anomalies"])

    # 模型/OOS：一族两轮不达标 → 拦停
    assert sections["models"]["families"] == 1
    assert len(sections["models"]["blocked"]) == 1
    assert sections["models"]["blocked"][0]["family"] == "BTCUSDT"
    assert sections["models"]["latest_rounds"][0]["sharpe_ratio"] == -0.5


def test_collect_sections_without_data(review_db, clean_models, replay_dir):
    """无 worker / 无模型旁车：空报告而不是异常。"""
    sections = dr.collect_sections(DAY)

    assert sections["overview"]["active_workers"] == 0
    assert sections["overview"]["total_pnl"] == 0.0
    assert sections["workers"] == []
    assert sections["anomalies"] == []
    assert sections["models"] == {"families": 0, "blocked": [], "latest_rounds": []}
    assert sections["risk_advisories"] == {
        "window_days": 30,
        "workers": [],
        "advisories": [],
        "count": 0,
        "max_severity": None,
    }


def test_sections_include_risk_advisories_per_active_worker(review_db, clean_models, replay_dir):
    """P4-2：风控建议作为 report 的新 section，对活跃 worker 逐个评估。

    空表持仓会由 get_positions_sync 从未配对成交推导（与该端点既有口径一致），
    这里单笔买入即形成 100% 单品种集中度 → 触发 concentration advisory。
    """
    worker = _seed_worker(review_db, name="w-risk")
    _add_trade(review_db, worker, pnl=5.0, when=datetime.combine(DAY, time(10, 0)))

    sections = dr.collect_sections(DAY)

    adv = sections["risk_advisories"]
    assert adv["window_days"] == 30
    assert adv["count"] >= 1
    assert adv["count"] == len(adv["advisories"])
    assert adv["max_severity"] == "crit"
    assert [w["worker_id"] for w in adv["workers"]] == [worker]

    concentration = [a for a in adv["advisories"] if a["metric"] == "concentration"]
    assert concentration, adv["advisories"]
    assert concentration[0]["severity"] == "crit"
    assert concentration[0]["suggested_notional_cap"] == 60.0  # 100 × 60%
    assert "风控建议" in dr.render_template_text(sections)


def test_template_renders_risk_advisory_entries(review_db, clean_models, replay_dir, monkeypatch):
    """模板文本必须带上风控建议段（advisory 非空时逐条列出，含建议额度）。"""
    _seed_worker(review_db, name="w-risk-text")

    fake_section = {
        "window_days": 30,
        "workers": [],
        "advisories": [
            {
                "worker_id": 1,
                "worker_name": "w-risk-text",
                "metric": "volatility",
                "severity": "warn",
                "value": 0.04,
                "threshold": 0.03,
                "reason": "w-risk-text 近 30 日 EWMA 日波动率 4.00% 达 warn 档，建议名义敞口上限降至 75000.00",
                "suggested_notional_cap": 75_000.0,
                "suggested_ratio": 0.75,
            }
        ],
        "count": 1,
        "max_severity": "warn",
    }
    monkeypatch.setattr("services.risk_advisory.collect_risk_advisories", lambda workers: fake_section)

    text = dr.build_report(DAY)["template_text"]

    assert "风控建议 1 条（最高 warn）" in text
    assert "EWMA 日波动率" in text
    assert "建议名义敞口上限" in text


def test_risk_advisory_failure_degrades_without_breaking_review(review_db, clean_models, replay_dir, monkeypatch):
    """建议层异常只降级该 section 并暴露 error，不复盘整体失败、不静默。"""
    _seed_worker(review_db, name="w-risk-broken")

    def boom(_workers):
        raise RuntimeError("advisory exploded")

    monkeypatch.setattr("services.risk_advisory.collect_risk_advisories", boom)

    report = dr.build_report(DAY)

    assert "advisory exploded" in report["sections"]["risk_advisories"]["error"]
    assert "风控建议计算失败" in report["template_text"]
    assert report["summary_text"]  # 报告仍然完整


# ---------- 模板报告 ----------


def test_template_text_contains_key_facts(review_db, clean_models, replay_dir):
    worker = _seed_worker(review_db, name="w-template")
    _add_trade(review_db, worker, pnl=12.5, when=datetime.combine(DAY, time(9, 0)))
    _add_position(review_db, worker, position_id="pos-t", unrealized_pnl=-30.0)
    _write_meta(clean_models, "ETHUSDT_ppo_1700000000", sharpe=-2.0, ret=-3.0, created_at="2026-11-16T00:00:00Z")

    report = dr.build_report(DAY)
    text = report["template_text"]

    assert report["summary_text"] == text  # 未请求 LLM 时摘要即模板文本
    assert report["meta"]["mode"] == "template"
    assert report["meta"]["degraded"] is False
    assert "2026-11-17" in text
    assert "12.50" in text
    assert "浮动亏损" in text
    assert "OOS 门槛" in text


# ---------- LLM 增强 / 降级 ----------


def test_llm_summary_used_when_available(review_db, clean_models, replay_dir):
    _seed_worker(review_db, name="w-llm")
    captured: list[str] = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return "  今日盈亏平稳，未见异常持仓。  "

    report = dr.build_report(DAY, use_llm=True, llm=fake_llm)

    assert report["summary_text"] == "今日盈亏平稳，未见异常持仓。"
    assert report["meta"]["mode"] == "llm"
    assert report["meta"]["llm"]["used"] is True
    assert report["meta"]["degraded"] is False
    assert captured and "复盘助手" in captured[0]


def test_llm_failure_degrades_to_template(review_db, clean_models, replay_dir):
    _seed_worker(review_db, name="w-llm-broken")

    def broken_llm(prompt: str) -> str:
        raise RuntimeError("provider down")

    report = dr.build_report(DAY, use_llm=True, llm=broken_llm)

    assert report["meta"]["degraded"] is True
    assert report["meta"]["mode"] == "template_fallback"
    assert "provider down" in report["meta"]["llm"]["error"]
    assert report["summary_text"] == report["template_text"]
    assert report["summary_text"]  # 绝不静默返回空摘要


def test_llm_unavailable_marks_degraded(review_db, clean_models, replay_dir, monkeypatch):
    _seed_worker(review_db, name="w-no-provider")
    monkeypatch.setattr(dr, "_default_llm", lambda: (None, None))

    report = dr.build_report(DAY, use_llm=True)

    assert report["meta"]["degraded"] is True
    assert report["meta"]["llm"]["error"] == "llm_unavailable"
    assert report["summary_text"] == report["template_text"]


def test_llm_empty_response_degrades(review_db, clean_models, replay_dir):
    report = dr.build_report(DAY, use_llm=True, llm=lambda _prompt: "   ")

    assert report["meta"]["degraded"] is True
    assert report["meta"]["llm"]["error"] == "empty_response"
    assert report["summary_text"] == report["template_text"]


# ---------- 端点契约 ----------


def test_endpoint_returns_report_and_rejects_bad_date(review_db, clean_models, replay_dir, monkeypatch):
    from fastapi import HTTPException

    from agent.api import routes

    monkeypatch.setattr(routes, "get_daily_review", lambda day, **_kw: {"date": day, "sections": {}, "meta": {}})

    payload = asyncio.run(routes.get_daily_review_report(date_str="2026-11-17", llm=False))
    assert payload["success"] is True
    assert payload["date"] == "2026-11-17"

    # 日期解析错误走 400 而不是 500
    monkeypatch.setattr(routes, "get_daily_review", dr.get_daily_review)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.get_daily_review_report(date_str="2026/11/17", llm=False))
    assert exc.value.status_code == 400


def test_endpoint_defaults_to_yesterday(monkeypatch):
    from agent.api import routes

    seen: list[str | None] = []

    def fake(day, **_kw):
        seen.append(day)
        return {"date": "x", "sections": {}, "meta": {}}

    monkeypatch.setattr(routes, "get_daily_review", fake)
    payload = asyncio.run(routes.get_daily_review_report(date_str=None, llm=False))
    assert payload["success"] is True
    assert seen == [None]  # 缺省交给 get_daily_review 解析成昨天


# ---------- 会话注入 ----------


class _StubAgent:
    def __init__(self):
        import tempfile
        from pathlib import Path

        from agent.session.manager import SessionManager

        self._tmp = tempfile.TemporaryDirectory()
        self.sessions = SessionManager(Path(self._tmp.name))

    def cleanup(self):
        self._tmp.cleanup()


def test_publish_appends_assistant_message_once(review_db, clean_models, replay_dir, monkeypatch):
    stub = _StubAgent()
    monkeypatch.setattr("agent.core.factory.get_agent", lambda: stub)
    report = dr.build_report(DAY)
    try:
        first = dr.publish(report)
        second = dr.publish(report)

        assert first["published"] is True
        assert second == {"published": False, "reason": "duplicate", "session_id": "default", "date": DAY.isoformat()}

        messages = stub.sessions.get_or_create("default").messages
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "assistant"  # 不伪装成 user 输入
        assert msg["content"] == report["summary_text"]
        assert msg["meta"]["kind"] == "daily_review"
        assert msg["meta"]["date"] == DAY.isoformat()
        assert msg["meta"]["report"]["sections"]["overview"]["date"] == DAY.isoformat()

        # 落盘后可被 history 端点读回
        history = stub.sessions.get_history("default", limit=10)
        assert history["history"][0]["role"] == "assistant"
    finally:
        stub.cleanup()
