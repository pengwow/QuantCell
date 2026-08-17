"""凭证管理测试。"""
import os
import pytest
from pydantic_settings import BaseSettings

# 测试前清理可能的环境变量
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(os.environ.keys()):
        if key.startswith("AXON_"):
            monkeypatch.delenv(key, raising=False)
    yield


def test_credentials_loads_from_env(monkeypatch):
    """凭证应从 AXON_* 环境变量读取。"""
    monkeypatch.setenv("AXON_OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("AXON_BINANCE_API_KEY", "bin-key")

    from backend.axon_bridge._credentials import AxonQuantCredentials

    creds = AxonQuantCredentials()
    assert creds.openai_api_key == "sk-test-123"
    assert creds.binance_api_key == "bin-key"
    assert creds.anthropic_api_key is None


def test_credentials_singleton_exists():
    """应导出全局 credentials 单例。"""
    from backend.axon_bridge import credentials
    from backend.axon_bridge._credentials import AxonQuantCredentials
    assert isinstance(credentials, AxonQuantCredentials)


def test_credentials_has_exchange_fields():
    """应包含 Exchange 凭证字段。"""
    from backend.axon_bridge._credentials import AxonQuantCredentials
    creds = AxonQuantCredentials()
    assert hasattr(creds, "binance_api_secret")
    assert hasattr(creds, "okx_passphrase")
    assert hasattr(creds, "local_llm_endpoint")
