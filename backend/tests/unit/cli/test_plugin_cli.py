"""plugin CLI 行为测试。

覆盖 clean 三类残留判定、create 脚手架文件树、pack 排除规则、
enable/disable 状态翻转，以及 create -> pack -> install 的 ZIP 闭环。

隔离手法：tmp_path 真目录 + 临时 SQLite（只建 plugins 表）替代全局 DB，
用 monkeypatch 把 cli.plugin._plugin_manager 指向 tmp PluginManager。
"""

import json
import os
import stat
import tempfile
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.plugin as plugin_cli
from cli.plugin import app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """把全局 PluginStore 指向一次性 SQLite 库（仅 plugins 表）。"""
    from sqlalchemy import create_engine

    import collector.db.database as database
    from collector.db.models import Plugin

    # 只导入模型、不初始化真实 engine；mapper 需要全部模型可见
    database._import_all_models()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'plugin_cli_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Plugin.__table__.create(engine)

    prev_bind = database.SessionLocal.kw.get("bind")
    monkeypatch.setattr(database, "engine", engine)
    database.SessionLocal.configure(bind=engine)
    try:
        yield
    finally:
        database.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


@pytest.fixture
def pm(tmp_path, isolated_db, monkeypatch):
    """真实 PluginManager，plugin_dir 指向 tmp 目录。"""
    from plugins.plugin_manager import PluginManager

    plugin_dir = tmp_path / "installed_plugins"
    plugin_dir.mkdir()
    manager = PluginManager(app=None, plugin_dir=str(plugin_dir))
    monkeypatch.setattr(plugin_cli, "_plugin_manager", manager)
    # 卸载/清理会把目录移进 backend/.trash，测试里改到 tmp 下，避免污染仓库
    monkeypatch.setattr(plugin_cli, "backend_path", tmp_path)
    return manager


def _add_manifest(plugin_dir, name):
    target = Path(plugin_dir) / name
    target.mkdir()
    (target / "manifest.json").write_text(json.dumps({"name": name, "version": "0.1.0"}), encoding="utf-8")
    return target


# ==================== clean ====================


def test_clean_three_residue_kinds_dry_run_then_force(runner, pm, tmp_path, monkeypatch):
    from plugins.plugin_store import PluginStore

    # 1) DB 有记录、目录不存在
    assert PluginStore.save_plugin({"name": "ghost", "version": "0.1.0"})

    # 2) 目录有 manifest、DB 无记录
    orphan = _add_manifest(pm.plugin_dir, "orphan")

    # 3) 临时目录残留（把 gettempdir 指到隔离目录，避免扫真 /tmp）
    fake_tmp = tmp_path / "sys_tmp"
    fake_tmp.mkdir()
    install_tmp = fake_tmp / "plugin_install_abc123"
    git_tmp = fake_tmp / "plugin_git_def456"
    install_tmp.mkdir()
    git_tmp.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fake_tmp))

    dry = runner.invoke(app, ["clean", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "ghost" in dry.stdout
    assert "orphan" in dry.stdout
    assert "plugin_install_abc123" in dry.stdout
    assert "plugin_git_def456" in dry.stdout
    assert "dry-run" in dry.stdout
    # 零改动
    assert PluginStore.get_plugin("ghost") is not None
    assert orphan.is_dir()
    assert install_tmp.is_dir()
    assert git_tmp.is_dir()

    forced = runner.invoke(app, ["clean", "--force"])
    assert forced.exit_code == 0, forced.output
    assert "共清理 4 个项目" in forced.stdout
    assert PluginStore.get_plugin("ghost") is None
    assert not orphan.exists()
    assert not install_tmp.exists()
    assert not git_tmp.exists()
    # 残留目录进 .trash（backend_path 已指向 tmp_path）
    trash_entries = list((tmp_path / ".trash").iterdir())
    assert any(p.name.startswith("orphan_") for p in trash_entries)


def test_clean_no_residue(runner, pm, tmp_path, monkeypatch):
    fake_tmp = tmp_path / "sys_tmp"
    fake_tmp.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fake_tmp))

    result = runner.invoke(app, ["clean", "--dry-run"])
    assert result.exit_code == 0
    assert "未发现需要清理的残留数据" in result.stdout


# ==================== create ====================


def test_create_fullstack_scaffold_file_tree(runner, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    result = runner.invoke(
        app,
        [
            "create",
            "demo_plugin",
            "--output",
            str(out),
            "--description",
            "示例插件",
            "--author",
            "tester",
            "--type",
            "fullstack",
            "--load-type",
            "restart",
        ],
    )
    assert result.exit_code == 0, result.output

    project = out / "demo_plugin"
    expected = {
        "manifest.json",
        "plugin.py",
        "build.sh",
        "frontend/package.json",
        "frontend/vite.config.ts",
        "frontend/tsconfig.json",
        "frontend/tsconfig.node.json",
        "frontend/index.html",
        "frontend/src/main.tsx",
        "frontend/src/App.tsx",
        "frontend/src/vite-env.d.ts",
        "frontend/src/hooks/useTheme.ts",
        "frontend/src/hooks/useLocale.ts",
    }
    actual = {str(p.relative_to(project)) for p in project.rglob("*") if p.is_file()}
    assert actual == expected

    manifest = json.loads((project / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "demo_plugin"
    assert manifest["version"] == "0.1.0"
    assert manifest["load_type"] == "restart"
    assert manifest["frontend_entry"] == "frontend/src/main.tsx"
    assert manifest["description"] == "示例插件"
    assert manifest["author"] == "tester"
    assert "class DemoPluginPlugin(PluginBase)" in (project / "plugin.py").read_text(encoding="utf-8")
    assert os.stat(project / "build.sh").st_mode & stat.S_IXUSR


def test_create_backend_only_has_no_frontend(runner, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    result = runner.invoke(app, ["create", "pure", "--output", str(out), "--type", "backend"])
    assert result.exit_code == 0, result.output

    project = out / "pure"
    assert not (project / "frontend").exists()
    assert {p.name for p in project.iterdir()} == {"manifest.json", "plugin.py", "build.sh"}
    manifest = json.loads((project / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["frontend_entry"] is None


def test_create_rejects_bad_name_and_existing_dir(runner, tmp_path):
    out = tmp_path / "out"
    out.mkdir()

    bad = runner.invoke(app, ["create", "bad name!", "--output", str(out)])
    assert bad.exit_code == 1

    (out / "dup").mkdir()
    dup = runner.invoke(app, ["create", "dup", "--output", str(out)])
    assert dup.exit_code == 1


# ==================== pack ====================


def test_pack_excludes_junk_and_keeps_expected_files(runner, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert runner.invoke(app, ["create", "packme", "--output", str(out), "--type", "backend"]).exit_code == 0
    project = out / "packme"

    # 应被排除的垃圾
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "x.pyc").write_bytes(b"junk")
    (project / ".DS_Store").write_bytes(b"junk")
    (project / "cache.db").write_text("junk", encoding="utf-8")
    (project / "notes.pyo").write_bytes(b"junk")

    zip_path = tmp_path / "packme.zip"
    result = runner.invoke(app, ["pack", str(project), "--output", str(zip_path)])
    assert result.exit_code == 0, result.output
    assert zip_path.is_file()
    assert "打包完成" in result.stdout

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert names == {"packme/manifest.json", "packme/plugin.py", "packme/build.sh"}
        manifest = json.loads(zf.read("packme/manifest.json"))
        assert manifest["name"] == "packme"


def test_pack_rejects_missing_dir_and_output_collision(runner, tmp_path):
    assert runner.invoke(app, ["pack", str(tmp_path / "nope")]).exit_code == 1

    project = tmp_path / "p"
    project.mkdir()
    (project / "manifest.json").write_text(json.dumps({"name": "p", "version": "0.1.0", "main": "plugin.py"}))
    existing = tmp_path / "already.zip"
    existing.write_bytes(b"x")
    assert runner.invoke(app, ["pack", str(project), "--output", str(existing)]).exit_code == 1


# ==================== enable / disable ====================


def test_enable_disable_flips_status(runner, pm):
    from plugins.plugin_store import PluginStore

    assert PluginStore.save_plugin({"name": "toggle", "version": "0.1.0", "status": "installed"})

    enabled = runner.invoke(app, ["enable", "toggle"])
    assert enabled.exit_code == 0, enabled.output
    assert "已启用" in enabled.stdout
    # 未加载进内存的插件启用后是待重启，而非直接 enabled
    assert PluginStore.get_plugin("toggle")["status"] == "pending_restart"

    disabled = runner.invoke(app, ["disable", "toggle"])
    assert disabled.exit_code == 0, disabled.output
    assert "已禁用" in disabled.stdout
    assert PluginStore.get_plugin("toggle")["status"] == "disabled"


def test_enable_missing_plugin_exits_1(runner, pm):
    assert runner.invoke(app, ["enable", "ghost"]).exit_code == 1
    assert runner.invoke(app, ["disable", "ghost"]).exit_code == 1


# ==================== create -> pack -> install 闭环 ====================


def test_create_pack_install_zip_roundtrip(runner, pm, tmp_path):
    from plugins.plugin_store import PluginStore

    out = tmp_path / "out"
    out.mkdir()
    assert runner.invoke(app, ["create", "roundtrip", "--output", str(out), "--type", "backend"]).exit_code == 0

    zip_path = tmp_path / "roundtrip.zip"
    assert runner.invoke(app, ["pack", str(out / "roundtrip"), "-o", str(zip_path)]).exit_code == 0

    result = runner.invoke(app, ["install", "--zip", str(zip_path)])
    assert result.exit_code == 0, result.output
    assert "安装成功" in result.stdout
    installed_dir = Path(pm.plugin_dir) / "roundtrip"
    assert (installed_dir / "manifest.json").is_file()

    record = PluginStore.get_plugin("roundtrip")
    assert record is not None
    assert record["install_source"] == "zip"
    assert record["status"] == "pending_restart"
    assert record["install_path"] == str(installed_dir)

    # 重复安装同一插件被拒绝
    again = runner.invoke(app, ["install", "--zip", str(zip_path)])
    assert again.exit_code == 1


def test_install_requires_exactly_one_source_and_existing_file(runner, pm, tmp_path):
    assert runner.invoke(app, ["install"]).exit_code == 1
    assert runner.invoke(app, ["install", "--zip", "a.zip", "--dir", "b"]).exit_code == 1
    assert runner.invoke(app, ["install", "--zip", str(tmp_path / "missing.zip")]).exit_code == 1
