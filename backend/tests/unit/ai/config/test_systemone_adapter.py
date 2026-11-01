"""System One（Jev 兼容）adapter：provider 注册、URL 归一化、探活与模型列表容错"""

import asyncio

import ai.config.services as services
from ai.config.services import AIModelService, SystemOneAdapter

SYSTEM_ONE_IDS = ["jev", "kev", "von", "decider", "rizzo-flow", "openthai-systemone"]


def _run(coro):
    return asyncio.run(coro)


class _FakeResponse:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _FakeClient:
    """替身：post 按构造时给的状态码与 body 返回"""

    def __init__(self, status_code: int, body):
        self._status = status_code
        self._body = body
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, headers))
        return _FakeResponse(self._status, self._body)

    async def get(self, url):
        return _FakeResponse(self._status, self._body)


def _patch_client(monkeypatch, status_code, body):
    fake = _FakeClient(status_code, body)
    monkeypatch.setattr(services.httpx, "AsyncClient", fake)
    return fake


def test_all_system_one_providers_registered():
    for pid in SYSTEM_ONE_IDS:
        assert pid in AIModelService.ADAPTERS, pid
    assert AIModelService.ADAPTERS["kev"].__mro__[1] is SystemOneAdapter


def test_systemone_url_normalizes_bare_and_v1_host():
    a = SystemOneAdapter("", "http://127.0.0.1:8787")
    assert a._systemone_url() == "http://127.0.0.1:8787/v1/systemone"
    b = SystemOneAdapter("", "http://127.0.0.1:8787/v1")
    assert b._systemone_url() == "http://127.0.0.1:8787/v1/systemone"


def test_check_available_on_valid_answers(monkeypatch):
    _patch_client(monkeypatch, 200, {"answers": {"ping": {"type": "noul", "noul": 0.5}}})
    result = _run(SystemOneAdapter("k", "http://127.0.0.1:8080").check_availability())
    assert result["available"] is True


def test_check_unavailable_when_status_not_200(monkeypatch):
    _patch_client(monkeypatch, 404, {"detail": "Not Found"})
    result = _run(SystemOneAdapter("", "http://127.0.0.1:8080").check_availability())
    assert result["available"] is False
    assert "404" in result["message"]


def test_check_unavailable_when_answers_missing(monkeypatch):
    """非 Jev 兼容服务（如 OpenAI 兼容）会返回 choices，必须判不可用而不是假阳性"""
    _patch_client(monkeypatch, 200, {"choices": [{"message": {"content": "hi"}}]})
    result = _run(SystemOneAdapter("", "http://127.0.0.1:8080").check_availability())
    assert result["available"] is False
    assert "answers" in result["message"]


def test_fetch_models_returns_empty_when_upstream_lacks_endpoint(monkeypatch):
    _patch_client(monkeypatch, 404, {"detail": "Not Found"})
    assert _run(SystemOneAdapter("", "http://127.0.0.1:8080").fetch_models()) == []


def test_fetch_models_maps_ids(monkeypatch):
    _patch_client(monkeypatch, 200, {"data": [{"id": "kev-4b"}, {"name": "no-id"}]})
    models = _run(SystemOneAdapter("", "http://127.0.0.1:8080").fetch_models())
    assert [m["id"] for m in models] == ["kev-4b"]
