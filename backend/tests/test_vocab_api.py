"""命名契约词汇表测试（命名审计 P2-5 / A-4）

覆盖两件事：
1. GET /api/v1/vocab 契约形态（HTTP smoke + 关键域/枚举/banned 词表存在性）
2. vocab.py 结构化事实源的一致性（枚举与归一 frozenset 对齐、词条唯一、kind 合法）
"""

import vocab
from main import app
from vocab import VOCAB_DOMAINS, VOCAB_ENUMS


def test_vocab_api_smoke():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/v1/vocab")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    # 关键域必须存在
    names = {d["name"] for d in data["domains"]}
    assert {"direction", "account", "symbol", "interval", "position", "kline_volume"} <= names
    # 枚举值域（前端生成的 Side/PositionSide 值源）
    assert data["enums"]["side"] == ["buy", "sell"]
    assert data["enums"]["position_side"] == ["long", "short", "both"]
    # banned 词表非空且可在顶层直接取用（P2-6 lint 门禁消费口）
    banned = [t["term"] for d in data["domains"] for t in d["terms"] if t["kind"] == "banned"]
    assert banned and sorted(banned) == data["banned_terms"]


def test_vocab_enum_consistency():
    """枚举值域必须与归一函数的 frozenset 一致（否则类型生成会漂移）。"""
    assert set(VOCAB_ENUMS["side"]) == vocab._SIDES
    assert set(VOCAB_ENUMS["position_side"]) == vocab._POSITION_SIDES


def test_vocab_terms_unique_and_valid_kind():
    """词条全表唯一，kind 取值合法。"""
    valid_kinds = {"canonical", "banned", "reserved"}
    seen = []
    for domain in VOCAB_DOMAINS:
        assert domain.name and domain.terms, f"{domain.name} 词条为空"
        for t in domain.terms:
            assert t.kind in valid_kinds, f"{t.term} kind 非法: {t.kind}"
            assert t.note.strip(), f"{t.term} 缺少裁决 note"
            seen.append((domain.name, t.term))
    assert len(seen) == len(set(seen)), "词条跨域或域内重复"
