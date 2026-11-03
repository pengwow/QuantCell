"""_collect_cascade_decisions 扁平化契约：decision 本体 + _ts/_decider/_s1_model"""

import json
from pathlib import Path

from backtest.engine_service import EventDrivenBacktestService


class _Strat:
    """只要 get_param("_cascade_layer") 能取到 layer 即可"""

    def __init__(self, layer):
        self._layer = layer

    def get_param(self, _key):
        return self._layer


class _Layer:
    def __init__(self, path: Path):
        self.path = path

    def close(self):
        pass


def test_collect_transfers_ts_decider_and_s1_model(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text(
        json.dumps(
            {
                "fingerprint": "f" * 64,
                "decision": {
                    "action": "hold",
                    "source": "fallback",
                    "confidence": 0.6,
                    "fallback_reason": "low_confidence: buy: 0.63",
                },
                "state": {},
                "questions": {},
                "ts": "2026-01-01T00:00:00.000000000Z",
                "_decider": "S2:qwen",
                "meta": {"s1_model": "laya"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # _collect_cascade_decisions 函数体不使用 self，用 None 做 unbound 调用避免拉起整个 __init__
    rows = EventDrivenBacktestService._collect_cascade_decisions(None, strategy=_Strat(_Layer(path)))

    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "hold"
    assert row["_ts"].startswith("2026-01-01T00:00:00")
    assert row["_decider"] == "S2:qwen"
    assert row["_s1_model"] == "laya"
    assert row["_seq"] == 0
    assert row["fingerprint"] == "f" * 64


def test_seq_refers_to_raw_file_line(tmp_path):
    """_seq 是排序前 JSONL 原始行号：脏行占位不挤占下标，排序后仍指回文件；并透传 fingerprint/_s2_model"""
    path = tmp_path / "r.jsonl"
    lines = [
        json.dumps(
            {
                "fingerprint": "a" * 64,
                "decision": {
                    "action": "hold",
                    "source": "fallback",
                    "confidence": 0.1,
                    "fallback_reason": "low_confidence: buy: 0.1",
                },
                "state": {},
                "questions": {},
                "ts": "2026-01-02T00:00:00.000000000Z",
                "_decider": "规则",
            }
        ),
        "not a json line",  # 脏行占 seq=1
        json.dumps(
            {
                "fingerprint": "b" * 64,
                "decision": {"action": "buy", "source": "sdm_direct", "confidence": 0.9},
                "state": {},
                "questions": {},
                "ts": "2026-01-01T00:00:00.000000000Z",
                "_decider": "S1:laya",
                "meta": {"s1_model": "laya", "s2_model": "qwen"},
            }
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = EventDrivenBacktestService._collect_cascade_decisions(None, strategy=_Strat(_Layer(path)))

    assert rows[0]["action"] == "buy"  # 时间排序后 buy(01-01) 在前
    by_fp = {r["fingerprint"]: r for r in rows}
    assert by_fp["a" * 64]["_seq"] == 0
    assert by_fp["b" * 64]["_seq"] == 2
    assert by_fp["b" * 64]["_s1_model"] == "laya"
    assert by_fp["b" * 64]["_s2_model"] == "qwen"
    assert all(r.get("fingerprint") for r in rows)
