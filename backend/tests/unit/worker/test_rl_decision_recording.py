"""RL predict 决策录制：按 cascade 同一 schema 追加到 worker_{id}.jsonl。

背景：Worker 决策页（GET /workers/{id}/decisions）读 worker_replay_path 的 JSONL，
RL paper 此前不写该文件，决策流 Tab 恒空。本补丁在 RL predict 回调外插桩录制。

覆盖：
- 两次预测（仓位上升/下降）各追加一行，动作映射 buy/sell，schema 键与
  RecordingCascadeLayer 写出的完全一致（同一 make_decision_record 真相源）
- 录制行可用 (_seq, fingerprint) 走详情端点同一查找函数定位
- 录制抛错时 predict 仍正常返回（交易主回路不受影响）
"""

import json

import pytest

from strategy import decision_recording
from strategy.decision_recording import (
    RecordingCascadeLayer,
    load_record_by_seq,
    make_decision_record,
    worker_replay_path,
    wrap_rl_predict,
)


@pytest.fixture(autouse=True)
def replay_dir(tmp_path, monkeypatch):
    """录制目录重定向到 tmp_path（worker_replay_path 运行时读环境变量）。"""
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(tmp_path))
    return tmp_path


def _sequence(values):
    it = iter(values)
    return lambda obs: next(it)


def _read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_records_each_predict_with_cascade_schema():
    path = worker_replay_path(7)
    recorded = wrap_rl_predict(_sequence([0.8, 0.2, 0.2]), path=path, model_id="ppo-1", symbol="BTCUSDT")

    assert recorded([0.1, 0.2]) == 0.8
    assert recorded([0.2, 0.3]) == 0.2
    assert recorded([0.3, 0.4]) == 0.2

    lines = _read_lines(path)
    assert len(lines) == 3
    assert [line["decision"]["action"] for line in lines] == ["buy", "sell", "hold"]
    assert [line["decision"]["target_position"] for line in lines] == [0.8, 0.2, 0.2]
    assert all(line["_decider"] == "RL:ppo-1" for line in lines)
    assert all(line["decision"]["source"] == "rl" for line in lines)
    assert all(line["decision"]["model_id"] == "ppo-1" for line in lines)
    assert all(line["state"]["symbol"] == "BTCUSDT" for line in lines)
    assert lines[0]["state"]["obs"] == [0.1, 0.2]


def test_rl_record_uses_same_keys_as_cascade_record(replay_dir):
    rl_path = worker_replay_path(11)
    recorded = wrap_rl_predict(lambda obs: 0.5, path=rl_path, model_id="m", symbol="BTCUSDT")
    recorded([1.0])

    class _EchoLayer:
        def decide(self, state, questions):
            return {"action": "buy", "confidence": 0.9, "source": "sdm_direct"}

    cascade_path = replay_dir / "cascade.jsonl"
    layer = RecordingCascadeLayer(_EchoLayer(), cascade_path)
    layer.decide({"close": 1.0}, {})
    layer.close()

    rl_line = _read_lines(rl_path)[0]
    cascade_line = _read_lines(cascade_path)[0]

    # 同一 schema：键集合相等，且等于 make_decision_record 的产物口径
    assert set(rl_line) == set(cascade_line) == set(make_decision_record("fp", {}, {}, {}, "x"))


def test_rl_record_is_locatable_by_seq_and_fingerprint():
    path = worker_replay_path(12)
    recorded = wrap_rl_predict(lambda obs: 0.5, path=path, model_id="m", symbol="BTCUSDT")
    recorded([1.0])

    line = _read_lines(path)[0]
    detail = load_record_by_seq(path, 0, line["fingerprint"])

    assert detail is not None
    assert detail["decision"]["action"] == "buy"
    assert detail["decision"]["target_position"] == 0.5


def test_recording_failure_does_not_break_predict(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(decision_recording, "append_decision_record", _boom)
    recorded = wrap_rl_predict(lambda obs: 0.7, path=worker_replay_path(13), model_id="m")

    assert recorded([0.0]) == 0.7
    assert worker_replay_path(13).exists() is False
