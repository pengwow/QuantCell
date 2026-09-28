"""extensions.api 单测：列表/状态/安装/进度/卸载的正常路径与 404/409/503 守卫。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from extensions import installer, manifest


def _make_app() -> FastAPI:
    from extensions.api import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture(autouse=True)
def _desktop_env(tmp_path, monkeypatch):
    # DEBUG=true 走 utils.auth 的鉴权豁免（对齐 tests/unit/api/test_rl_routes.py）
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path / "data"))
    uv = tmp_path / "uv"
    uv.write_text("#!/usr/bin/env bash\nexit 0\n")
    monkeypatch.setenv("QUANTCELL_UV_BIN", str(uv))
    # 列表接口不打真实 PyPI
    monkeypatch.setattr(manifest, "live_total_size_mb", lambda deps: None)
    installer._reset()
    yield
    installer._reset()


def test_list_uninstalled():
    with TestClient(_make_app()) as client:
        r = client.get("/api/v1/extensions")
        assert r.status_code == 200
        items = r.json()["data"]
        assert [e["id"] for e in items] == ["rl"]
        assert items[0]["deps"] == ["torch", "stable-baselines3", "gymnasium"]
        assert items[0]["installed"] is False
        assert items[0]["live_size_mb"] is None
        assert items[0]["approx_size_mb"] == 600


def test_status_unknown_extension_404():
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/extensions/nope/status").status_code == 404


def test_status_installed_reflects_fs(tmp_path):
    sp = tmp_path / "data" / "extensions" / "rl" / "site-packages"
    sp.mkdir(parents=True)
    (sp / "torch-2.5.1.dist-info").mkdir()
    with TestClient(_make_app()) as client:
        data = client.get("/api/v1/extensions/rl/status").json()["data"]
        assert data["installed"] is True
        assert data["versions"] == {"torch": "2.5.1"}


def test_list_requires_data_dir(monkeypatch):
    monkeypatch.delenv("QUANTCELL_DATA_DIR")
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/extensions").status_code == 503


def test_install_requires_uv_bin(monkeypatch):
    monkeypatch.delenv("QUANTCELL_UV_BIN")
    with TestClient(_make_app()) as client:
        assert client.post("/api/v1/extensions/rl/install").status_code == 503


def test_install_starts_task_and_progress_reads_it(monkeypatch):
    def fake_start(spec, data_dir, uv_bin):
        tid = "t-1"
        installer._tasks[tid] = installer.TaskState(status="downloading", pct=40, detail="下载中 1/2 MiB")
        installer._running[spec.id] = tid
        installer._last_task[spec.id] = tid
        return tid

    monkeypatch.setattr(installer, "start_install", fake_start)
    with TestClient(_make_app()) as client:
        r = client.post("/api/v1/extensions/rl/install")
        assert r.status_code == 200
        assert r.json()["data"]["task_id"] == "t-1"
        data = client.get("/api/v1/extensions/rl/progress").json()["data"]
        assert data == {"task_id": "t-1", "status": "downloading", "pct": 40, "detail": "下载中 1/2 MiB"}


def test_install_conflict_returns_409(monkeypatch):
    monkeypatch.setattr(installer, "running_task_id", lambda ext_id: "existing")
    with TestClient(_make_app()) as client:
        assert client.post("/api/v1/extensions/rl/install").status_code == 409


def test_install_unknown_extension_404():
    with TestClient(_make_app()) as client:
        assert client.post("/api/v1/extensions/nope/install").status_code == 404


def test_progress_idle_when_no_task():
    with TestClient(_make_app()) as client:
        data = client.get("/api/v1/extensions/rl/progress").json()["data"]
        assert data["status"] == "idle"
        assert data["task_id"] is None
        assert data["pct"] == 0


def test_progress_unknown_extension_404():
    with TestClient(_make_app()) as client:
        assert client.get("/api/v1/extensions/nope/progress").status_code == 404


def test_uninstall_blocks_while_running(monkeypatch):
    monkeypatch.setattr(installer, "running_task_id", lambda ext_id: "x")
    with TestClient(_make_app()) as client:
        assert client.post("/api/v1/extensions/rl/uninstall").status_code == 409


def test_uninstall_calls_installer_and_unknown_404(monkeypatch):
    seen = {}
    monkeypatch.setattr(installer, "uninstall", lambda data_dir, ext_id: seen.update(ext=ext_id))
    with TestClient(_make_app()) as client:
        assert client.post("/api/v1/extensions/nope/uninstall").status_code == 404
        r = client.post("/api/v1/extensions/rl/uninstall")
        assert r.status_code == 200
        assert seen["ext"] == "rl"
