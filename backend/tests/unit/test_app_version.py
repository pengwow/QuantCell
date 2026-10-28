"""app_version 单源测试：QUANTCELL_VERSION 环境变量覆盖与 dev 兜底。"""

import pytest

from config.settings import get_settings
from settings.services import SystemService


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """get_settings 是 lru_cache 单例，每个用例前后清缓存，保证 env 变更生效"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fallback_dev_when_env_missing(monkeypatch):
    """未注入 QUANTCELL_VERSION（源码直跑 / CI 单测）时兜底 dev"""
    monkeypatch.delenv("QUANTCELL_VERSION", raising=False)
    assert get_settings().app_version == "dev"


def test_env_override_from_desktop_shell(monkeypatch):
    """桌面端 Rust spawn_sidecar 会注入 QUANTCELL_VERSION，settings 必须读到"""
    monkeypatch.setenv("QUANTCELL_VERSION", "9.9.9")
    assert get_settings().app_version == "9.9.9"


def test_settings_service_reports_same_version(monkeypatch):
    """settings 服务的 system_version 必须引用 settings，而不是硬编码字符串"""
    monkeypatch.setenv("QUANTCELL_VERSION", "8.8.8")
    result = SystemService().get_system_info()
    assert result["success"] is True
    assert result["system_info"]["version"]["system_version"] == "8.8.8"
