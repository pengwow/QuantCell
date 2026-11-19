"""desktop_entry 环境变量推导的单测（不启动服务）。"""

import sys

import pytest

from desktop_entry import apply_extensions_path


def test_build_runtime_env_points_into_data_dir(tmp_path):
    from desktop_entry import build_runtime_env

    env = build_runtime_env(str(tmp_path))

    assert env["QUANTCELL_DATA_DIR"] == str(tmp_path)
    assert env["DB_FILE"] == str(tmp_path / "quantcell_sqlite.db")
    assert env["PORT_CONFIG_PATH"] == str(tmp_path / "port_config.json")
    # Tauri WebView 各平台 origin + Vite dev 端口
    assert "tauri://localhost" in env["CORS_ORIGINS"]
    assert "http://tauri.localhost" in env["CORS_ORIGINS"]
    assert "http://localhost:1420" in env["CORS_ORIGINS"]


def test_build_runtime_env_enables_desktop_local_bypass_and_dev_cors():
    from desktop_entry import build_runtime_env

    env = build_runtime_env("/tmp/whatever")

    # local 模式免登录开关，供 utils.auth._auth_disabled 读取
    assert env["QUANTCELL_DESKTOP_LOCAL"] == "1"
    # M2 dev 时前端 Vite 跑在 5173，需放行（M1 的 1420 保留）
    assert "http://localhost:5173" in env["CORS_ORIGINS"]
    assert "http://127.0.0.1:5173" in env["CORS_ORIGINS"]


@pytest.fixture
def _restore_sys_path():
    snapshot = list(sys.path)
    yield
    sys.path[:] = snapshot


def test_apply_extensions_path_inserts_site_packages(tmp_path, _restore_sys_path):
    sp = tmp_path / "extensions" / "rl" / "site-packages"
    sp.mkdir(parents=True)
    apply_extensions_path(str(tmp_path))
    assert sys.path[0] == str(sp)


def test_apply_extensions_path_noop_when_dir_missing(tmp_path, _restore_sys_path):
    before = list(sys.path)
    apply_extensions_path(str(tmp_path / "missing"))
    assert sys.path == before


def test_apply_extensions_path_skips_non_dir_glob(tmp_path, _restore_sys_path):
    # 存在扩展目录但没有 site-packages 子目录时不得注入路径
    (tmp_path / "extensions" / "rl").mkdir(parents=True)
    before = list(sys.path)
    apply_extensions_path(str(tmp_path))
    assert sys.path == before


def test_parse_system_proxy_enabled():
    from desktop_entry import _parse_system_proxy

    sample = (
        "<dictionary> {\n"
        "  HTTPEnable : 1\n"
        "  HTTPPort : 7897\n"
        "  HTTPProxy : 127.0.0.1\n"
        "  SOCKSEnable : 1\n"
        "  SOCKSPort : 7897\n"
        "  SOCKSProxy : 127.0.0.1\n"
        "}\n"
    )
    assert _parse_system_proxy(sample) == "http://127.0.0.1:7897"


def test_parse_system_proxy_disabled_or_incomplete():
    from desktop_entry import _parse_system_proxy

    assert _parse_system_proxy("HTTPEnable : 0") is None
    assert _parse_system_proxy("HTTPEnable : 1\nHTTPProxy : 127.0.0.1") is None  # 缺端口
    assert _parse_system_proxy("") is None


def test_inherit_system_proxy_explicit_env_wins(monkeypatch):
    import os

    from desktop_entry import inherit_system_proxy

    monkeypatch.setenv("PROXY_URL", "http://explicit:9999")
    inherit_system_proxy()
    assert os.environ["PROXY_URL"] == "http://explicit:9999"


def test_inherit_system_proxy_scutil_fallback(monkeypatch):
    import os

    import desktop_entry as de

    sample = "HTTPEnable : 1\nHTTPPort : 7897\nHTTPProxy : 127.0.0.1\n"
    monkeypatch.delenv("PROXY_URL", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)

    class R:
        stdout = sample

    monkeypatch.setattr(de.subprocess, "run", lambda *a, **k: R())
    de.inherit_system_proxy()
    assert os.environ["PROXY_URL"] == "http://127.0.0.1:7897"
