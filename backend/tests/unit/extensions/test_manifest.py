"""extensions.manifest 单测：静态白名单、安装态/版本扫描、PyPI 大小估算与回退。"""

from __future__ import annotations

import platform

import pytest

from extensions import manifest
from extensions.manifest import (
    EXTENSIONS,
    get_extension,
    installed_versions,
    is_installed,
    live_total_size_mb,
    site_packages_dir,
)


def test_rl_extension_whitelist():
    rl = get_extension("rl")
    assert rl is not None
    # 安装参数只允许来自这份白名单
    assert rl.deps == ("torch", "stable-baselines3", "gymnasium")
    assert rl.approx_size_mb == 600


def test_extension_ids_unique_and_nonempty():
    ids = [e.id for e in EXTENSIONS]
    assert all(ids)
    assert len(set(ids)) == len(ids)


def test_get_unknown_extension_returns_none():
    assert get_extension("nope") is None


def test_installed_state_and_version_scan(tmp_path):
    assert is_installed(tmp_path, "rl") is False
    sp = site_packages_dir(tmp_path, "rl")
    sp.mkdir(parents=True)
    assert is_installed(tmp_path, "rl") is False  # 空目录不算已装
    (sp / "torch").mkdir()
    (sp / "torch-2.5.1.dist-info").mkdir()
    assert is_installed(tmp_path, "rl") is True
    assert installed_versions(tmp_path, "rl") == {"torch": "2.5.1"}


@pytest.fixture
def pypi_payload():
    return {
        "urls": [
            {"packagetype": "bdist_wheel", "filename": "demo-1.0-py3-none-any.whl", "size": 2_000_000},
            {
                "packagetype": "bdist_wheel",
                "filename": "demo-1.0-cp314-cp314-macosx_11_0_arm64.whl",
                "size": 10 * 1024 * 1024,
            },
            {
                "packagetype": "bdist_wheel",
                "filename": "demo-1.0-cp314-cp314-manylinux_2_28_x86_64.whl",
                "size": 999 * 1024 * 1024,
            },
            {"packagetype": "sdist", "filename": "demo-1.0.tar.gz", "size": 1_000_000},
        ]
    }


def test_pick_wheel_macos_arm64(monkeypatch, pypi_payload):
    monkeypatch.setattr(manifest.sys, "platform", "darwin")
    monkeypatch.setattr(manifest.platform, "machine", lambda: "arm64")
    assert manifest._pick_download_size(pypi_payload["urls"]) == 10 * 1024 * 1024


def test_pick_wheel_linux_x64(monkeypatch, pypi_payload):
    monkeypatch.setattr(manifest.sys, "platform", "linux")
    monkeypatch.setattr(manifest.platform, "machine", lambda: "x86_64")
    assert manifest._pick_download_size(pypi_payload["urls"]) == 999 * 1024 * 1024


def test_live_size_sums_per_pkg(monkeypatch):
    def fake_json(_name: str) -> dict:
        return {"urls": [{"packagetype": "bdist_wheel", "filename": "x-1-py3-none-any.whl", "size": manifest._MIB}]}

    monkeypatch.setattr(manifest, "_pypi_json", fake_json)
    assert live_total_size_mb(("a", "b", "c")) == 3


def test_live_size_fallback_on_network_error(monkeypatch):
    def _raise(_name: str):
        raise OSError("timeout")

    monkeypatch.setattr(manifest, "_pypi_json", _raise)
    assert live_total_size_mb(("demo",)) is None


def test_live_size_fallback_when_no_urls(monkeypatch):
    monkeypatch.setattr(manifest, "_pypi_json", lambda _n: {"urls": []})
    assert live_total_size_mb(("demo",)) is None
