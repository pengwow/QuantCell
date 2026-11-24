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


def test_list_marks_current_snapshot_by_disk_hash(env):
    first = source("1.0.0", "a")
    second = source("1.1.0", "b")
    env.service.save_strategy("probe", first)
    env.service.save_strategy("probe", second)

    versions = env.service.list_strategy_versions("probe")
    # 列表项必须有 id（操作定位用）与 is_current（磁盘内容匹配）
    assert versions[0]["id"] and versions[0]["is_current"] is True
    assert versions[1]["is_current"] is False

    # 外部直接改文件（不经保存入口）→ 没有任何快照等于当前文件
    (env.strategies_dir / "probe.py").write_text("external edit\n", encoding="utf-8")
    assert all(v["is_current"] is False for v in env.service.list_strategy_versions("probe"))


def test_only_latest_matching_snapshot_is_current(env):
    """历史里可能有多条同内容快照，只把最新那条标成当前。"""
    first = source("1.0.0", "a")
    second = source("1.1.0", "b")
    env.service.save_strategy("probe", first)
    env.service.save_strategy("probe", second)
    old_id = env.service.list_strategy_versions("probe")[1]["id"]
    env.service.restore_strategy_version("probe", old_id)  # 写回 A，留一条新的 A 快照

    versions = env.service.list_strategy_versions("probe")
    current = [v for v in versions if v["is_current"]]
    assert len(current) == 1
    assert current[0]["id"] == versions[0]["id"]
    assert current[0]["code_hash"] == hashlib.sha256(first.encode("utf-8")).hexdigest()


def test_get_version_returns_code_and_scopes_to_strategy(env):
    code = source("1.0.0", "a")
    env.service.save_strategy("probe", code)
    snapshot_id = env.service.list_strategy_versions("probe")[0]["id"]

    snapshot = env.service.get_strategy_version("probe", snapshot_id)
    assert snapshot["code"] == code
    assert snapshot["code_hash"] == hashlib.sha256(code.encode("utf-8")).hexdigest()

    # 同名 id 挂到别的策略名下不能读出来
    env.service.save_strategy("other", source("1.0.0", "o"))
    assert env.service.get_strategy_version("other", snapshot_id) is None
    assert env.service.get_strategy_version("ghost", snapshot_id) is None


def test_restore_writes_back_and_keeps_history(env):
    first = source("1.0.0", "a")
    second = source("1.1.0", "b")
    env.service.save_strategy("probe", first)
    env.service.save_strategy("probe", second)
    old_id = env.service.list_strategy_versions("probe")[1]["id"]

    restored = env.service.restore_strategy_version("probe", old_id)

    assert restored["code"] == first
    assert restored["new_snapshot"] is True
    assert (env.strategies_dir / "probe.py").read_text(encoding="utf-8") == first
    versions = env.service.list_strategy_versions("probe")
    # 历史不删：旧两条 + 恢复产生的新一条
    assert len(versions) == 3
    assert versions[0]["is_current"] is True
    assert versions[0]["version"] == "1.0.0"


def test_restore_same_content_does_not_bump_count(env):
    code = source("1.0.0", "a")
    env.service.save_strategy("probe", code)
    snapshot_id = env.service.list_strategy_versions("probe")[0]["id"]

    restored = env.service.restore_strategy_version("probe", snapshot_id)

    assert restored["new_snapshot"] is False
    assert len(env.service.list_strategy_versions("probe")) == 1


def test_restore_keeps_user_version_when_content_declares_none(env):
    """内容没声明版本时沿用 DB 现值，不能落 upload 的 1.0.0 默认值。"""
    plain = '"""no declared version"""\n\n\nclass ProbeStrategy:\n    def on_bar(self, bar):\n        return None\n'
    env.service.save_strategy("probe", plain)
    snapshot_id = env.service.list_strategy_versions("probe")[0]["id"]

    from strategy.models import Strategy

    db = env.factory()
    try:
        db.add(Strategy(name="probe", version="v9", file_name="probe.py"))
        db.commit()
    finally:
        db.close()

    restored = env.service.restore_strategy_version("probe", snapshot_id)
    assert restored["version"] == "v9"

    db = env.factory()
    try:
        assert db.query(Strategy).filter_by(name="probe").first().version == "v9"
    finally:
        db.close()
