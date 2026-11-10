"""首页连接状态真实探测 + CPU 采样的最小验证（全部 mock，不发真实网络请求）。"""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from collector.services.system_service import SystemService


class _FakeAccount:
    def __init__(self, exchange: str):
        self.exchange = exchange


def _patch_env(monkeypatch, accounts, health: bool | dict[str, bool], created: list[str]):
    """统一打桩：凭据账户列表 + 交易所构造（health 按 dict 精确控制，bool 则统一值）"""

    def fake_create(exchange_name, **_kwargs):
        created.append(exchange_name)
        probe = health.get(exchange_name, True) if isinstance(health, dict) else health
        ex = MagicMock()
        ex.health_check.return_value = probe
        return ex

    monkeypatch.setattr(
        "collector.services.system_service.CredentialsService",
        lambda: SimpleNamespace(list_accounts=lambda: accounts),
    )
    monkeypatch.setattr("collector.services.system_service.create_exchange_instance", fake_create)


async def test_same_exchange_accounts_dedup(monkeypatch):
    """两个同交易所账户只应探测一次"""
    svc = SystemService()
    created: list[str] = []
    _patch_env(
        monkeypatch,
        [_FakeAccount("binance"), _FakeAccount("binance")],
        True,
        created,
    )
    assert await svc.get_connection_status() == "connected"
    assert created.count("binance") == 1


async def test_no_accounts_falls_back_to_default(monkeypatch):
    """未配置账户时退化为默认 binance 探测"""
    svc = SystemService()
    created: list[str] = []
    _patch_env(monkeypatch, [], True, created)
    assert await svc.get_connection_status() == "connected"
    assert created == ["binance"]


async def test_credentials_error_falls_back_to_default(monkeypatch):
    """凭据库读取失败不应导致探测失败，退化为默认 binance"""
    svc = SystemService()

    def boom():
        raise RuntimeError("db broken")

    created: list[str] = []

    def fake_create(exchange_name, **_kwargs):
        created.append(exchange_name)
        ex = MagicMock()
        ex.health_check.return_value = True
        return ex

    monkeypatch.setattr("collector.services.system_service.CredentialsService", boom)
    monkeypatch.setattr("collector.services.system_service.create_exchange_instance", fake_create)
    assert await svc.get_connection_status() == "connected"
    assert created == ["binance"]


async def test_all_probes_failed_disconnected(monkeypatch):
    """全部探测失败 → disconnected"""
    svc = SystemService()
    _patch_env(monkeypatch, [_FakeAccount("binance")], False, [])
    assert await svc.get_connection_status() == "disconnected"


async def test_partial_failure_still_connected(monkeypatch):
    """部分交易所可达即视为系统在线"""
    svc = SystemService()
    _patch_env(
        monkeypatch,
        [_FakeAccount("binance"), _FakeAccount("okx")],
        {"binance": True, "okx": False},
        [],
    )
    assert await svc.get_connection_status() == "connected"


async def test_ttl_cache_within_window(monkeypatch):
    """60s TTL 内第二次请求直接用缓存，不重复探测"""
    svc = SystemService()
    created: list[str] = []
    _patch_env(monkeypatch, [_FakeAccount("binance")], True, created)

    assert await svc.get_connection_status() == "connected"
    # 翻转健康状态并清空 created：若缓存未生效，第二次探测会得到 disconnected
    monkeypatch.setattr(
        "collector.services.system_service.create_exchange_instance",
        lambda name, **_: MagicMock(health_check=MagicMock(return_value=False)),
    )
    created.clear()
    assert await svc.get_connection_status() == "connected"
    assert created == []


def test_cpu_usage_reuses_recent_sample(monkeypatch):
    """1s 内重复请求复用上次采样结果，不重复调用 psutil"""
    svc = SystemService()
    calls: list[float | None] = []

    def fake_cpu_percent(interval=None):
        calls.append(interval)
        return 33.0

    monkeypatch.setattr("collector.services.system_service.psutil.cpu_percent", fake_cpu_percent)
    assert svc._sample_cpu_usage() == 33.0
    assert svc._sample_cpu_usage() == 33.0
    assert len(calls) == 1


def test_cpu_usage_keeps_last_value_when_counter_not_refreshed(monkeypatch):
    """macOS 计数器未刷新导致采样为 0 时保留上次有效值，不显示 0%"""
    svc = SystemService()
    seq = iter([41.0, 0.0])
    monkeypatch.setattr(
        "collector.services.system_service.psutil.cpu_percent",
        lambda interval=None: next(seq),
    )
    assert svc._sample_cpu_usage() == 41.0
    # 模拟已超过 1s 采样窗口，允许重新采样
    svc._cpu_usage_cache = (time.monotonic() - 2.0, 41.0)
    assert svc._sample_cpu_usage() == 41.0
