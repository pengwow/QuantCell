"""trial → 回测 端点契约：promote 幂等复用、参数只取真实记录、错误显式。

promote 与 DB 读写真跑（只把落文件目录挪到 tmp），只把「真跑回测」的两步
（后台线程 + 引擎执行）换成同步 no-op，因此断言到的是 create_task 实际收到的参数。
路由函数直接调用而不经 TestClient：全局替换 threading.Thread 会让 TestClient 的
portal 线程自己变成内联执行而死锁，而这里要测的不是 HTTP 框架。
"""

from __future__ import annotations

import contextlib
import json
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backtest.routes as backtest_routes
import research.routes as research_routes
import research.scenarios.strategy as strategy_scenario_module
import strategy.models  # 注册 Strategy，保证 Worker 关系的 mapper 可初始化
import utils.db_session as db_session_module
from backtest.models import BacktestTask
from collector.db.database import Base
from research import service
from research.models import ResearchEvent, ResearchKnowledge, ResearchSession, ResearchTrial

STRATEGY_CODE = """
from axon_quant import Action, ActionType
from strategy.base import BaseStrategy

class AlwaysLong(BaseStrategy):
    def on_bar(self, bar, ctx=None):
        return Action(ActionType.Buy, 1.0, 1.0, "always_long", 0)
"""

WINDOW = {
    "symbols": ["BTCUSDT"],
    "interval": "1h",
    "candle_type": "spot",
    "start": "2025-01-01",
    "end": "2025-03-01",
}


class _InlineThread:
    """把后台执行线程换成同步调用：create_task 的入参因此可直接断言。"""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture()
def env(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'research.db'}")
    Base.metadata.create_all(
        eng,
        tables=[
            ResearchSession.__table__,
            ResearchTrial.__table__,
            ResearchKnowledge.__table__,
            ResearchEvent.__table__,
            BacktestTask.__table__,
        ],
    )
    db = sessionmaker(bind=eng)()

    @contextlib.contextmanager
    def fake_db():
        yield db

    # 路由与 strategy 场景各自在 import 期绑定了 get_db_session；
    # run_backtest 内部是调用期 import，改 utils.db_session 即可覆盖
    monkeypatch.setattr(research_routes, "get_db_session", fake_db)
    monkeypatch.setattr(strategy_scenario_module, "get_db_session", fake_db)
    monkeypatch.setattr(db_session_module, "get_db_session", fake_db)
    # 进度跟踪器单例 __init__ 会起一个 5 分钟清理线程：先预热，避免下面替换 Thread 后
    # 那个清理线程被内联执行（time.sleep(300) 会把请求卡死）
    backtest_routes.get_progress_tracker()
    monkeypatch.setattr(threading, "Thread", _InlineThread)

    class _StubStrategyService:
        """落文件重定向到临时目录，promote 逻辑本身（provenance/回填）仍真跑。"""

        def __init__(self):
            self.strategy_dir = tmp_path

        def save_strategy(self, name, content):
            Path(self.strategy_dir, f"{name}.py").write_text(content, encoding="utf-8")
            return {"name": name}

    monkeypatch.setattr(strategy_scenario_module, "StrategyService", _StubStrategyService)

    calls: dict[str, dict] = {}

    # create_task 保留原实现（真写任务文件），只记录入参；文件落到 tmp，不污染 data/。
    # 这样 _run_backtest_task 的真实构造 + 真实校验 + 真实落库都在覆盖范围内。
    backtest_routes.backtest_service.results_dir = tmp_path / "backtest_results"
    backtest_routes.backtest_service.results_dir.mkdir(parents=True, exist_ok=True)
    real_create_task = backtest_routes.backtest_service.create_task

    def recording_create_task(**kwargs):
        calls["create_task"] = kwargs
        return real_create_task(**kwargs)

    monkeypatch.setattr(backtest_routes.backtest_service, "create_task", recording_create_task)
    # 只摘掉链路最末的引擎执行（_ensure_kline_data 与撮合都在 BacktestService.run_backtest 里）
    monkeypatch.setattr(backtest_routes.backtest_service, "run_backtest", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr(backtest_routes, "notify_backtest_result", lambda *args, **kwargs: None)

    try:
        yield db, tmp_path, calls
    finally:
        db.close()


def _seed(
    db,
    *,
    scenario: str = "strategy",
    config: dict | None = None,
    code: str | None = STRATEGY_CODE,
    task: dict | None = None,
) -> tuple[ResearchSession, ResearchTrial]:
    session = service.create_session(
        db,
        owner_id="u1",
        name="deep-strategy",
        mode="deep",
        scenario=scenario,
        config={"scenario": scenario, **WINDOW} if config is None else config,
        n_candidates=1,
    )
    service.set_session_status(db, session, "running")
    trial = service.add_trial(
        db,
        session.id,
        {
            "loop_idx": 1,
            "candidate_idx": 1,
            "status": "judged",
            "hypothesis": "趋势跟随",
            "code": code,
            "code_hash": "stub",
            "task_json": task if task is not None else {"name": "ma", "description": "d", "params": {"fast": 5.0}},
        },
    )
    return session, trial


def _call(session_id: int, trial_id: int):
    return research_routes.trial_to_backtest(session_id, trial_id, current_user={"user_id": "u1"})


def test_creates_task_with_trial_params_and_session_window(env):
    db, strategy_dir, calls = env
    session, trial = _seed(db)

    data = _call(session.id, trial.id).data
    assert data["task_id"]
    assert data["reused_promotion"] is False
    assert data["strategy_name"] == f"rs_{session.id}_{trial.id}"

    kwargs = calls["create_task"]
    assert kwargs["strategy_name"] == data["strategy_name"]
    assert kwargs["strategy_params"] == {"fast": 5.0}
    assert kwargs["symbols"] == ["BTCUSDT"]
    assert kwargs["timeframes"] == ["1h"]
    assert kwargs["config"]["start_time"] == "2025-01-01"
    assert kwargs["config"]["end_time"] == "2025-03-01"
    assert kwargs["task_id"] == data["task_id"]

    # promote 真跑：文件落盘 + 回填 promoted_factor_name
    assert (strategy_dir / f"{data['strategy_name']}.py").exists()
    db.refresh(trial)
    assert trial.promoted_factor_name == data["strategy_name"]


def test_promoted_trial_reuses_name_without_second_file(env):
    db, strategy_dir, calls = env
    session, trial = _seed(db)

    first = _call(session.id, trial.id).data
    second = _call(session.id, trial.id).data

    assert second["reused_promotion"] is True
    assert second["strategy_name"] == first["strategy_name"]
    assert len(list(strategy_dir.glob("*.py"))) == 1
    # 复用入库名建新任务，参数仍来自 trial/会话记录
    assert calls["create_task"]["strategy_name"] == first["strategy_name"]


def test_missing_params_yields_empty_dict(env):
    db, _, calls = env
    session, trial = _seed(db, task={"name": "no-params", "description": "d"})

    _call(session.id, trial.id)
    assert calls["create_task"]["strategy_params"] == {}


def test_trial_without_code_is_400(env):
    db, _, calls = env
    session, trial = _seed(db, code=None)

    with pytest.raises(HTTPException) as exc:
        _call(session.id, trial.id)
    assert exc.value.status_code == 400
    assert "没有可回测的代码" in exc.value.detail
    assert "create_task" not in calls


def test_factor_scenario_is_400(env):
    db, _, calls = env
    session, trial = _seed(db, scenario="factor")

    with pytest.raises(HTTPException) as exc:
        _call(session.id, trial.id)
    assert exc.value.status_code == 400
    assert "factor" in exc.value.detail
    assert "create_task" not in calls


def test_missing_window_names_the_missing_fields(env):
    db, _, calls = env
    session, trial = _seed(db, config={"scenario": "strategy", "symbols": ["BTCUSDT"], "interval": "1h"})

    with pytest.raises(HTTPException) as exc:
        _call(session.id, trial.id)
    assert exc.value.status_code == 400
    assert "start" in exc.value.detail and "end" in exc.value.detail
    assert "create_task" not in calls


def test_trial_from_other_session_is_404(env):
    db, _, calls = env
    session, _ = _seed(db)
    other_session, other_trial = _seed(db)

    with pytest.raises(HTTPException) as exc:
        _call(session.id, other_trial.id)
    assert exc.value.status_code == 404
    assert other_trial.session_id == other_session.id
    assert "create_task" not in calls


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-01-01", "2026-03-01"),  # 前端表单的日期串（会话 config_json 的真实形态）
        ("2026-01-01T00:00:00+08:00", "2026-03-01T00:00:00+08:00"),  # 带时区的 ISO 串
    ],
)
def test_run_backtest_task_keeps_real_validation_and_persists(env, start, end):
    """真构造 BacktestRunRequest + 真落库：只把线程与引擎执行换成 no-op。

    run_backtest 的 pydantic 校验（BacktestConfig 标的来源/保证金/字段类型）、
    BacktestTask 落库、create_task 真实写任务文件、策略参数透传全都在链路上，
    因此会话窗口串若被校验拒绝或参数被改写，这条会先炸。
    """
    db, _, calls = env
    session, trial = _seed(
        db,
        config={
            "scenario": "strategy",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "interval": "4h",
            "candle_type": "future",
            "start": start,
            "end": end,
            "initial_cash": 250000.0,
        },
    )
    cfg = service.session_config(session)
    params = service.trial_to_dict(service.get_trial_row(db, trial.id))["task"]["params"]

    resp = research_routes._run_backtest_task(
        strategy_name="rs_probe",
        params=params,
        symbols=cfg["symbols"],
        interval=cfg["interval"],
        start=cfg["start"],
        end=cfg["end"],
        cfg=cfg,
    )

    assert resp.code == 0
    task_id = resp.data["task_id"]
    assert task_id

    row = db.query(BacktestTask).filter_by(id=task_id).one()
    stored = json.loads(row.backtest_config)
    # 窗口/标的/周期/资金逐字段等于会话记录，没被转换或默认值替换
    assert stored["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert stored["interval"] == "4h"
    assert stored["start_time"] == start
    assert stored["end_time"] == end
    assert stored["initial_cash"] == 250000.0
    assert stored["capital_mode"] == "per_symbol"
    assert stored["trading_mode"] == "futures"  # candle_type=future 的同义映射
    # 策略参数就是 trial 的 task.params，不多不少
    assert stored["strategy_params"] == params == {"fast": 5.0}
    assert row.strategy_name == "rs_probe"
    assert calls["create_task"]["task_id"] == task_id
