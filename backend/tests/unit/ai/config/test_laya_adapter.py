"""Laya adapter：裸地址归一化、空 api_key 兜底、provider 注册"""

from ai.config.services import AIModelService, LayaAdapter


def test_laya_registered_in_adapters():
    assert "laya" in AIModelService.ADAPTERS
    assert AIModelService.ADAPTERS["laya"] is LayaAdapter


def test_base_url_appends_v1_once():
    a = LayaAdapter("", "http://127.0.0.1:8787")
    assert a.base_url == "http://127.0.0.1:8787/v1"
    b = LayaAdapter("", "http://127.0.0.1:8787/v1")
    assert b.base_url == "http://127.0.0.1:8787/v1"


def test_empty_api_key_uses_placeholder():
    # OpenAI SDK 拒绝空 key，自托管 laya 无鉴权时用占位符保证构造成功
    a = LayaAdapter("")
    assert a.api_key == "laya"
    assert a.base_url == LayaAdapter.DEFAULT_API_HOST + "/v1"


def test_get_adapter_returns_laya():
    adapter = AIModelService.get_adapter("laya", "", "http://127.0.0.1:8787")
    assert isinstance(adapter, LayaAdapter)
