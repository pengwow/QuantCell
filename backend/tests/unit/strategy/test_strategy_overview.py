"""策略总览聚合端点单测（/api/v1/strategy/overview 的 service 层）。

用真实 SQLAlchemy 模型（strategies / workers / backtest_tasks）建内存库，
只替换 DB 会话入口与结果目录，不对聚合逻辑打桩。
"""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from strategy.service import StrategyService

STRATEGY_SOURCE = '''"""测试策略 {name}"""


class Config:
    def __init__(self, mode: str = "heuristic"):
        self.mode = mode


class {cls}Strategy:
    pass
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
    """真实模型 + 内存 SQLite；策略文件/回测结果目录都落到 tmp_path。"""
    from collector.db.database import Base, _import_all_models

    _import_all_models()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    @contextmanager
    def _session():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    # service 在函数内 import get_db_session，patch 模块属性即可覆盖
    monkeypatch.setattr("utils.db_session.get_db_session", _session)

    import strategy.service as service_module

    # 顶层 conftest 的 _isolate_backtest_task_storage 也会建同名目录
    results_dir = tmp_path / "backtest_results"
    results_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(service_module, "_BACKTEST_RESULTS_DIR", results_dir)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    service = StrategyService()
    service.strategy_dir = strategies_dir

    return SimpleNamespace(
        service=service,
        factory=session_factory,
        strategies_dir=strategies_dir,
        results_dir=results_dir,
    )


def add_strategy(env, name: str) -> None:
    cls = name.title().replace("_", "")
    (env.strategies_dir / f"{name}.py").write_text(STRATEGY_SOURCE.format(name=name, cls=cls), encoding="utf-8")


def add_worker(
    env,
    name: str,
    strategy_name: str,
    status: str,
    *,
    interval: str | None = None,
    symbols: list[str] | None = None,
    trading_mode: str = "paper",
) -> None:
    from worker.models import Worker

    config: dict = {
        "symbols_config": {"type": "symbols", "symbols": symbols or []},
        "trading_mode": trading_mode,
    }
    if interval is not None:
        config["interval"] = interval
    with env.factory() as db:
        db.add(
            Worker(
                name=name,
                strategy_name=strategy_name,
                status=status,
                trading_config=json.dumps(config),
            )
        )
        db.commit()


def add_task(
    env,
    task_id: str,
    strategy_name: str,
    status: str,
    created_at: datetime,
    result_id: str | None = None,
) -> None:
    from backtest.models import BacktestTask

    with env.factory() as db:
        db.add(
            BacktestTask(
                id=task_id,
                strategy_name=strategy_name,
                backtest_config="{}",
                status=status,
                created_at=created_at,
                result_id=result_id,
            )
        )
        db.commit()


def write_result(env, result_id: str, total_return: float | None) -> None:
    payload = {"status": "completed", "results": {}}
    if total_return is not None:
        payload["results"]["portfolio"] = {"metrics": [{"key": "total_return", "value": total_return}]}
    (env.results_dir / f"result_{result_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def item_of(env, name: str) -> dict:
    overview = env.service.list_strategies_overview()
    return next(row for row in overview if row["name"] == name)


def test_no_worker_is_undeployed(env):
    add_strategy(env, "idle")

    row = item_of(env, "idle")

    assert row["state"] == "undeployed"
    assert row["worker_count"] == 0
    assert row["interval"] is None
    assert row["symbols"] == []
    assert row["latest_backtest"] is None
    assert row["kind"] == "rule"


def test_running_paper_is_paper_and_passes_config_through(env):
    add_strategy(env, "paper_only")
    add_worker(
        env,
        "w-paper",
        "paper_only",
        "running",
        interval="1h",
        symbols=["BTC/USDT"],
        trading_mode="paper",
    )

    row = item_of(env, "paper_only")

    assert row["state"] == "paper"
    assert row["worker_count"] == 1
    assert row["interval"] == "1h"
    assert row["symbols"] == ["BTC/USDT"]


def test_running_live_wins_over_paper(env):
    add_strategy(env, "mixed_run")
    add_worker(env, "w-mixed-paper", "mixed_run", "running", interval="4h", trading_mode="paper")
    add_worker(env, "w-mixed-live", "mixed_run", "running", interval="1h", trading_mode="live")

    row = item_of(env, "mixed_run")

    assert row["state"] == "live"
    assert row["worker_count"] == 2
    # interval 取最活跃（running-live）的 worker
    assert row["interval"] == "1h"


def test_paused_worker_is_paused(env):
    add_strategy(env, "paused_s")
    add_worker(env, "w-paused", "paused_s", "paused", interval="15m", trading_mode="paper")

    row = item_of(env, "paused_s")

    assert row["state"] == "paused"
    assert row["worker_count"] == 1


def test_multi_worker_interval_most_active_and_symbols_union(env):
    add_strategy(env, "multi_w")
    # 更活跃的 running-paper 带一个标的，paused 的旧 worker 带另一个标的和 4h 周期
    add_worker(env, "w-multi-a", "multi_w", "running", interval="1h", symbols=["BTC/USDT"])
    add_worker(env, "w-multi-b", "multi_w", "paused", interval="4h", symbols=["ETH/USDT"])

    row = item_of(env, "multi_w")

    assert row["interval"] == "1h"
    assert row["symbols"] == ["BTC/USDT", "ETH/USDT"]
    assert row["worker_count"] == 2
    assert row["state"] == "paper"


def test_latest_backtest_picks_newest_task_and_reads_total_return(env):
    add_strategy(env, "bt_newest")
    now = datetime.now()
    add_task(env, "task-old", "bt_newest", "failed", now - timedelta(days=2), result_id="old-result")
    add_task(env, "task-new", "bt_newest", "completed", now, result_id="new-result")
    write_result(env, "old-result", 1.5)
    write_result(env, "new-result", 3.5)

    row = item_of(env, "bt_newest")

    assert row["latest_backtest"]["status"] == "completed"
    assert row["latest_backtest"]["total_return"] == pytest.approx(3.5)
    assert row["latest_backtest"]["created_at"].startswith(now.isoformat()[:19])
    # 详情块 footer「累计回测 N 次」用真实任务总数（不是列表样本、也不是只算最新一条）
    assert row["backtest_count"] == 2


def test_latest_backtest_total_return_is_null_when_result_missing(env):
    add_strategy(env, "bt_missing")
    add_task(env, "task-missing", "bt_missing", "completed", datetime.now(), result_id="not-on-disk")

    row = item_of(env, "bt_missing")

    assert row["latest_backtest"]["status"] == "completed"
    assert row["latest_backtest"]["total_return"] is None


def test_kind_llm_from_parameters_mode_marker(env):
    from strategy.models import Strategy

    add_strategy(env, "llm_sig")
    with env.factory() as db:
        db.add(
            Strategy(
                name="llm_sig",
                parameters=json.dumps(
                    [
                        {
                            "name": "mode",
                            "type": "str",
                            "default": "llm",
                            "description": "",
                            "required": False,
                        }
                    ]
                ),
            )
        )
        db.commit()

    row = item_of(env, "llm_sig")

    assert row["kind"] == "llm"


def test_overview_route_returns_code_message_data(env, monkeypatch):
    from strategy import routes as strategy_routes

    add_strategy(env, "route_s")
    monkeypatch.setattr(strategy_routes, "get_strategy_service", lambda: env.service)

    response = strategy_routes.get_strategy_overview()
    body = response.model_dump()

    assert body["code"] == 0
    assert isinstance(body["data"]["strategies"], list)
    assert body["data"]["strategies"][0]["name"] == "route_s"
    assert body["data"]["strategies"][0]["state"] == "undeployed"
