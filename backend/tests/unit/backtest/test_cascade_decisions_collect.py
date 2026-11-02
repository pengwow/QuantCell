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
