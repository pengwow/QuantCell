"""Paper 泵 typed client 测试（P2-09 三轨收敛）。"""

import json

import pytest

from worker import pump_client
from worker.pump_client import PaperKline, as_kline, fetch_paper_klines

# binance 原始行形态（值是字符串），与 services 测试 monkeypatch 注入形态一致
_RAW_ROWS = [
    ["1700000000000", "50000.0", "50100.0", "49900.0", "50050.0", "10.0"],
    ["1700003600000", "50050.0", "50300.0", "50000.0", "50200.0", "12.0"],
]


class TestAsKline:
    def test_raw_row_converted(self):
        kline = as_kline(_RAW_ROWS[0])
        assert kline == PaperKline(
            open_time=1700000000000, open=50000.0, high=50100.0, low=49900.0, close=50050.0, volume=10.0
        )
        assert isinstance(kline["open_time"], int)
        assert isinstance(kline["close"], float)

    def test_typed_dict_idempotent(self):
        typed = as_kline(_RAW_ROWS[0])
        assert as_kline(dict(typed)) == typed

    def test_raw_row_missing_field_raises(self):
        with pytest.raises((IndexError, KeyError, TypeError, ValueError)):
            as_kline(["1700000000000", "50000.0"])


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeOpener:
    """替身 opener：不触网，原样返回预置 payload（校验 URL 拼装参数）。"""

    def __init__(self, payload: bytes):
        self._payload = payload
        self.last_url: str | None = None

    def open(self, url, timeout):
        self.last_url = url
        return _FakeResp(self._payload)


def _patch_opener(monkeypatch, rows) -> _FakeOpener:
    fake = _FakeOpener(json.dumps(rows).encode("utf-8"))
    monkeypatch.setattr(pump_client, "PAPER_NO_PROXY_OPENER", fake)
    return fake


class TestFetchPaperKlines:
    def test_fetch_returns_typed_rows(self, monkeypatch):
        fake = _patch_opener(monkeypatch, _RAW_ROWS)
        rows = fetch_paper_klines("BTCUSDT", "1h", 2)
        assert fake.last_url == f"{pump_client.PAPER_KLINES_URL}?symbol=BTCUSDT&interval=1h&limit=2"
        assert rows[0]["open_time"] == 1700000000000
        assert rows[1]["close"] == pytest.approx(50200.0)

    def test_error_payload_raises(self, monkeypatch):
        # 端点错误响应是 {"code": ..., "msg": ...} dict 而非 list → 显式失败
        _patch_opener(monkeypatch, {"code": -1121, "msg": "Invalid symbol."})
        with pytest.raises(ValueError, match="非 list"):
            fetch_paper_klines("INVALID", "1h", 2)
