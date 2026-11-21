"""策略版本历史单测（strategy_versions 表 + 保存钩子 + /versions + overview 计数）。

真实 SQLAlchemy 模型 + 内存 SQLite + 临时 strategies 目录，不桩保存逻辑。
"""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from strategy.service import StrategyService

SOURCE_TMPL = '''"""版本历史测试策略 {name}"""

VERSION = "{version}"


class {cls}Strategy:
    def on_bar(self, bar):
        return None
'''


@pytest.fixture
def env(tmp_path, monkeypatch):
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

    monkeypatch.setattr("utils.db_session.get_db_session", _session)

    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    service = StrategyService()
    service.strategy_dir = strategies_dir

    return SimpleNamespace(service=service, factory=session_factory, strategies_dir=strategies_dir)


def source(version: str, marker: str = "") -> str:
    cls = "Probe"
    return SOURCE_TMPL.format(name="probe", version=version, cls=cls) + f"# {marker}\n"


def test_two_different_saves_create_two_snapshots(env):
    env.service.save_strategy("probe", source("1.0.0", "a"))
    env.service.save_strategy("probe", source("1.1.0", "b"))

    versions = env.service.list_strategy_versions("probe")

    assert len(versions) == 2
    # 版本号取自文件声明值（不是解析默认的 1.0.0，也不是历史序号）
    assert versions[0]["version"] == "1.1.0"
    assert versions[1]["version"] == "1.0.0"


def test_same_content_is_not_recorded_twice(env):
    first = source("1.0.0", "same")
    env.service.save_strategy("probe", first)
    env.service.save_strategy("probe", first)

    assert len(env.service.list_strategy_versions("probe")) == 1


def test_versions_endpoint_returns_desc_without_code(env, monkeypatch):
    from strategy import routes as strategy_routes

    first = source("1.0.0", "a")
    second = source("1.1.0", "b")
    env.service.save_strategy("probe", first)
    env.service.save_strategy("probe", second)
    monkeypatch.setattr(strategy_routes, "get_strategy_service", lambda: env.service)

    body = strategy_routes.api_get_strategy_versions("probe").model_dump()

    assert body["code"] == 0
    assert body["data"]["count"] == 2
    versions = body["data"]["versions"]
    # created_at DESC：最新（second）在前
    assert versions[0]["code_hash"] == hashlib.sha256(second.encode("utf-8")).hexdigest()
    assert versions[0]["code_size"] == len(second)
    assert "code" not in versions[0]
    assert isinstance(versions[0]["created_at"], str)


def test_overview_version_count_matches_endpoint(env, monkeypatch):
    from strategy import routes as strategy_routes

    env.service.save_strategy("probe", source("1.0.0", "a"))
    env.service.save_strategy("probe", source("1.1.0", "b"))
    # 未保存过的策略（初始化入库口径）版本数就是 0，不是缺陷
    (env.strategies_dir / "idle.py").write_text(source("1.0.0", "z"), encoding="utf-8")
    monkeypatch.setattr(strategy_routes, "get_strategy_service", lambda: env.service)

    overview = {row["name"]: row for row in env.service.list_strategies_overview()}
    versions = env.service.list_strategy_versions("probe")

    assert overview["probe"]["version_count"] == len(versions) == 2
    assert overview["idle"]["version_count"] == 0


def test_unknown_strategy_versions_404(env, monkeypatch):
    from fastapi import HTTPException

    from strategy import routes as strategy_routes

    monkeypatch.setattr(strategy_routes, "get_strategy_service", lambda: env.service)

    with pytest.raises(HTTPException) as exc:
        strategy_routes.api_get_strategy_versions("ghost")

    assert exc.value.status_code == 404
