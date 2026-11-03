"""decision 录制与查表：指纹自洽、同指纹首条为准、s2_mode 覆盖"""

import json

import pytest

from strategy.decision_recording import (
    DecisionReplayTable,
    RecordingCascadeLayer,
    default_replay_dir,
    list_decisions_from_file,
    load_record_by_seq,
    request_fingerprint,
    worker_replay_path,
)

STATE = {"features": {"sma5_vs_sma20": 0.02, "ret_1": 0.01}, "price": 100.0}
QUESTIONS = {
    "next_direction": {
        "type": "choice",
        "instructions": {"question": "方向?", "focus": "仅依据给定特征"},
        "criteria": {"buy": {"what": "涨"}, "sell": {"what": "跌"}, "hold": {"what": "震荡"}},
    }
}


class FakeLayer:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def decide(self, state, questions):
        self.calls += 1
        return dict(self.result)


def test_fingerprint_is_order_insensitive_and_utf8():
    a = request_fingerprint({"b": 2, "a": "中文"}, {"q": {"type": "noul"}})
    b = request_fingerprint({"a": "中文", "b": 2}, {"q": {"type": "noul"}})
    assert a == b and len(a) == 64


def test_record_writes_one_line_and_dedupes(tmp_path):
    path = tmp_path / "d.jsonl"
    result = {
        "action": "buy",
        "source": "sdm_direct",
        "confidence": 0.9,
        "probabilities": {"buy": 0.9, "sell": 0.05, "hold": 0.05},
        "fallback_reason": None,
        "sdm_usage": None,
        "sub_signals": {},
    }
    layer = RecordingCascadeLayer(FakeLayer(result), path)
    d1 = layer.decide(STATE, QUESTIONS)
    d2 = layer.decide(STATE, QUESTIONS)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["fingerprint"] == request_fingerprint(STATE, QUESTIONS)
    assert record["decision"]["action"] == "buy"
    assert record["ts"].endswith("Z") and len(record["ts"].split(".")[-1]) == 10  # 9位纳秒+Z
    assert d1 == d2


def test_record_carries_s1_source_meta(tmp_path):
    """录制需标注 S1 端点：本地适配层与官方 laya-serve 的 confidence 语义不同"""
    path = tmp_path / "meta.jsonl"
    layer = RecordingCascadeLayer(
        FakeLayer({"action": "hold", "source": "fallback", "confidence": 0.0}),
        path,
        meta={"s1_api_host": "http://127.0.0.1:8010", "s1_model": "laya"},
    )
    layer.decide(STATE, QUESTIONS)
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["meta"]["s1_api_host"] == "http://127.0.0.1:8010"
    assert record["meta"]["s1_model"] == "laya"


def test_replay_table_hit_and_miss(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text(
        json.dumps(
            {
                "fingerprint": request_fingerprint(STATE, QUESTIONS),
                "decision": {
                    "action": "hold",
                    "source": "fallback",
                    "confidence": 0.5,
                    "probabilities": {"hold": 0.5, "buy": 0.25, "sell": 0.25},
                    "fallback_reason": "low_confidence: buy=0.5",
                    "sdm_usage": None,
                    "sub_signals": {},
                },
                "state": STATE,
                "questions": QUESTIONS,
                "ts": "2026-01-01T00:00:00.000000000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    table = DecisionReplayTable(path)
    hit = table.lookup(request_fingerprint(STATE, QUESTIONS))
    assert hit["action"] == "hold"
    assert table.lookup("0" * 64) is None
    assert len(table) == 1


def test_replay_table_first_entry_wins(tmp_path):
    """同指纹重复录制时读侧以首条为准（与写侧 _seen 去重语义一致）"""
    path = tmp_path / "dup.jsonl"
    fp = request_fingerprint(STATE, QUESTIONS)
    first = {"action": "buy", "source": "sdm_direct", "confidence": 0.9}
    second = {"action": "sell", "source": "sdm_direct", "confidence": 0.9}
    lines = [
        {
            "fingerprint": fp,
            "decision": first,
            "state": STATE,
            "questions": QUESTIONS,
            "ts": "2026-01-01T00:00:00.000000000Z",
        },
        {
            "fingerprint": fp,
            "decision": second,
            "state": STATE,
            "questions": QUESTIONS,
            "ts": "2026-01-01T00:00:01.000000000Z",
        },
    ]
    path.write_text("".join(json.dumps(item) + "\n" for item in lines), encoding="utf-8")

    table = DecisionReplayTable(path)
    assert len(table) == 1
    assert table.lookup(fp)["action"] == "buy"


def test_s2_replay_overrides_fallback(tmp_path):
    path = tmp_path / "d.jsonl"
    recorded = {
        "action": "hold",
        "source": "fallback",
        "confidence": 0.6,
        "probabilities": {"hold": 0.6, "buy": 0.2, "sell": 0.2},
        "fallback_reason": "low_confidence: buy=0.3",
        "sdm_usage": None,
        "sub_signals": {},
    }
    path.write_text(
        json.dumps(
            {
                "fingerprint": request_fingerprint(STATE, QUESTIONS),
                "decision": recorded,
                "state": STATE,
                "questions": QUESTIONS,
                "ts": "2026-01-01T00:00:00.000000000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rule_result = {
        "action": "buy",
        "source": "fallback",
        "confidence": 0.7,
        "probabilities": {},
        "fallback_reason": "low_confidence: hold=0.5",
        "sdm_usage": None,
        "sub_signals": {},
    }
    table = DecisionReplayTable(path)
    layer = RecordingCascadeLayer(FakeLayer(rule_result), tmp_path / "out.jsonl", s2_mode="replay", replay_table=table)
    d = layer.decide(STATE, QUESTIONS)
    assert d["action"] == "hold"  # 用录制结果覆盖规则结果
    assert "s2_replay" in d["fallback_reason"]


def test_s2_replay_miss_keeps_rule_result(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    rule_result = {
        "action": "buy",
        "source": "fallback",
        "confidence": 0.7,
        "probabilities": {},
        "fallback_reason": "low_confidence: hold=0.5",
        "sdm_usage": None,
        "sub_signals": {},
    }
    layer = RecordingCascadeLayer(
        FakeLayer(rule_result), tmp_path / "out2.jsonl", s2_mode="replay", replay_table=DecisionReplayTable(path)
    )
    assert layer.decide(STATE, QUESTIONS)["action"] == "buy"


def test_decider_is_tagged_on_record(tmp_path):
    """record 顶层 _decider 四态：S1 直判 / S2 兜底 / 规则 / 回放。

    replay 装配时 S2 恒为 None（decision_service 的 need_s2 为 False），
    命中查表的行无法知晓当年决策者，只能靠 reason 的 |s2_replay 后缀识别，
    标「回放」而不猜 S2/规则。
    """
    # S1 直判：source=sdm_direct
    path = tmp_path / "s1.jsonl"
    RecordingCascadeLayer(
        FakeLayer({"action": "hold", "source": "sdm_direct", "confidence": 0.9}),
        path,
        meta={"s1_model": "laya", "s2_model": "qwen"},
    ).decide(STATE, QUESTIONS)
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["_decider"] == "S1:laya"

    # S2 兜底：source=fallback 且 meta 带 s2_model（live 装配了生成式兜底）
    path = tmp_path / "s2.jsonl"
    RecordingCascadeLayer(
        FakeLayer(
            {"action": "hold", "source": "fallback", "confidence": 0.6, "fallback_reason": "low_confidence: buy: 0.5"}
        ),
        path,
        meta={"s1_model": "laya", "s2_model": "qwen"},
    ).decide(STATE, QUESTIONS)
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["_decider"] == "S2:qwen"

    # 规则：source=fallback 且 meta 无 s2_model（force_rule / stub 装配）
    path = tmp_path / "rule.jsonl"
    RecordingCascadeLayer(
        FakeLayer(
            {"action": "buy", "source": "fallback", "confidence": 0.7, "fallback_reason": "low_confidence: hold: 0.5"}
        ),
        path,
        meta={"s1_model": "laya"},
    ).decide(STATE, QUESTIONS)
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["_decider"] == "规则"

    # 回放：s2_mode=replay 查表命中 → reason 带 |s2_replay 后缀，且 meta 无 s2_model
    src = tmp_path / "src.jsonl"
    src.write_text(
        json.dumps(
            {
                "fingerprint": request_fingerprint(STATE, QUESTIONS),
                "decision": {
                    "action": "hold",
                    "source": "fallback",
                    "confidence": 0.6,
                    "probabilities": {},
                    "fallback_reason": "low_confidence: buy: 0.3",
                    "sdm_usage": None,
                    "sub_signals": {},
                },
                "state": STATE,
                "questions": QUESTIONS,
                "ts": "2026-01-01T00:00:00.000000000Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    path = tmp_path / "out.jsonl"
    RecordingCascadeLayer(
        FakeLayer(
            {"action": "buy", "source": "fallback", "confidence": 0.7, "fallback_reason": "low_confidence: hold: 0.5"}
        ),
        path,
        s2_mode="replay",
        replay_table=DecisionReplayTable(src),
        meta={"s1_model": "laya"},
    ).decide(STATE, QUESTIONS)
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["_decider"] == "回放"
    # replay 覆盖后的 reason 带后缀（既有行为，顺带钉住）
    assert rec["decision"]["fallback_reason"].endswith("|s2_replay")


def test_default_replay_dir_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(tmp_path / "x"))
    assert default_replay_dir() == tmp_path / "x"


def test_worker_replay_path_names_by_worker(tmp_path, monkeypatch):
    """paper/live 录制文件名以 worker 为键：写入侧与端点读取侧的唯一契约"""
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(tmp_path))
    assert worker_replay_path(7) == tmp_path / "worker" / "worker_7.jsonl"
    # int 字符串也归一：worker_id 从 query/路由来可能是 str
    assert worker_replay_path("12") == tmp_path / "worker" / "worker_12.jsonl"


def _write_record_file(path, fp="a" * 64):
    path.write_text(
        json.dumps(
            {
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
        )
        + "\n"
        + "broken line\n",
        encoding="utf-8",
    )


def test_load_record_by_seq_hit(tmp_path):
    path = tmp_path / "r.jsonl"
    _write_record_file(path)
    rec = load_record_by_seq(path, 0, "a" * 64)
    assert rec is not None
    assert rec["decision"]["action"] == "hold"
    assert rec["state"] == {"price": 1.0}


def test_load_record_by_seq_out_of_range(tmp_path):
    path = tmp_path / "r.jsonl"
    _write_record_file(path)
    assert load_record_by_seq(path, 7, "a" * 64) is None


def test_load_record_by_seq_fingerprint_mismatch(tmp_path):
    path = tmp_path / "r.jsonl"
    _write_record_file(path)
    assert load_record_by_seq(path, 0, "e" * 64) is None


def test_load_record_by_seq_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_record_by_seq(tmp_path / "nope.jsonl", 0, "a" * 64)


def test_raw_outputs_hoisted_to_top_level(tmp_path):
    """S1/S2 原始输出提升到录制行顶层：decision 本体不携带，回放查表不放大体积"""

    class _Inner:
        def decide(self, state, questions):
            return {
                "action": "sell",
                "source": "fallback",
                "confidence": 0.7,
                "fallback_reason": "low_confidence: sell: 0.7",
                "s1_raw": '{"model":"laya"}',
                "s2_raw": '思考中…{"action":"sell"}',
                "s2_thinking": "let me think",
            }

    layer = RecordingCascadeLayer(_Inner(), tmp_path / "r.jsonl", meta={"s1_model": "laya", "s2_model": "qwen"})
    layer.decide({}, {})

    record = json.loads((tmp_path / "r.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["s1_raw"] == '{"model":"laya"}'
    assert record["s2_raw"].startswith("思考")
    assert record["s2_thinking"] == "let me think"
    assert "s1_raw" not in record["decision"]

    # 回放查表拿到的 decision 无原文键
    table = DecisionReplayTable(tmp_path / "r.jsonl")
    found = table.lookup(record["fingerprint"])
    assert found is not None and "s1_raw" not in found


def test_list_decisions_from_file_flattens_and_skips_dirty(tmp_path):
    """扁平化轻列表：_seq 是原始行号（脏行占位），脏行/缺 decision 行跳过"""
    path = tmp_path / "r.jsonl"
    lines = [
        json.dumps(
            {
                "fingerprint": "a" * 64,
                "decision": {"action": "hold", "confidence": 0.1},
                "state": {},
                "questions": {},
                "ts": "t1",
                "_decider": "规则",
            }
        ),
        "not json",
        json.dumps({"fingerprint": "b" * 64, "state": {}}),  # 无 decision → 跳过
        json.dumps(
            {
                "fingerprint": "c" * 64,
                "decision": {"action": "buy", "confidence": 0.9},
                "state": {},
                "questions": {},
                "ts": "t2",
                "_decider": "S1:laya",
                "meta": {"s1_model": "laya", "s2_model": "qwen"},
            }
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = list_decisions_from_file(path)

    assert [r["action"] for r in rows] == ["hold", "buy"]  # 保持文件顺序，不排序
    assert rows[0]["_seq"] == 0 and rows[1]["_seq"] == 3
    assert rows[0]["fingerprint"] == "a" * 64
    assert rows[1]["_s1_model"] == "laya" and rows[1]["_s2_model"] == "qwen"
    assert list_decisions_from_file(tmp_path / "missing.jsonl") == []

    tail, total = list_decisions_from_file(path, max_rows=1, return_total=True)
    assert total == 2
    assert [r["_seq"] for r in tail] == [3]
    assert list_decisions_from_file(path, return_total=True) == (rows, 2)
