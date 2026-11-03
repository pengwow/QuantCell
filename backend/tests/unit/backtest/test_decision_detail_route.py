"""decisions/detail 端点：seq+fingerprint 双校验定位录制行，文件即事实来源（不查任务库）"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backtest.routes import router
from strategy import decision_recording


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _write(tmp_path, rid="t1", fp="a" * 64):
    p = decision_recording.default_replay_dir() / f"{rid}.jsonl"
    record = {
        "fingerprint": fp,
        "decision": {
            "action": "hold",
            "source": "fallback",
            "confidence": 0.5,
            "fallback_reason": "low_confidence: buy: 0.5",
        },
        "state": {"price": 1.0},
        "questions": {"q1": "x"},
        "ts": "2026-01-01T00:00:00.000000000Z",
        "_decider": "规则",
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return record


def test_detail_hit(client, tmp_path):
    _write(tmp_path)
    resp = client.get("/api/v1/backtest/t1/decisions/detail", params={"seq": 0, "fingerprint": "a" * 64})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["decision"]["action"] == "hold"
    assert body["data"]["_decider"] == "规则"


def test_detail_file_missing(client, tmp_path):
    resp = client.get("/api/v1/backtest/ghost/decisions/detail", params={"seq": 0, "fingerprint": "a" * 64})
    body = resp.json()
    assert body["code"] == 1
    assert "录制文件不存在" in body["message"]


def test_detail_fingerprint_mismatch(client, tmp_path):
    _write(tmp_path)
    resp = client.get("/api/v1/backtest/t1/decisions/detail", params={"seq": 0, "fingerprint": "e" * 64})
    body = resp.json()
    assert body["code"] == 1
    assert "未命中" in body["message"]


def test_detail_seq_out_of_range(client, tmp_path):
    _write(tmp_path)
    resp = client.get("/api/v1/backtest/t1/decisions/detail", params={"seq": 9, "fingerprint": "a" * 64})
    body = resp.json()
    assert body["code"] == 1
    assert "未命中" in body["message"]
