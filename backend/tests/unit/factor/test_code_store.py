# 代码因子 JSON 持久化测试
import json

from factor.code_store import CodeFactorStore


def test_upsert_and_get(tmp_path):
    store = CodeFactorStore(tmp_path / "code_factors.json")
    store.upsert(
        "llm_mom_1",
        "factor = df['close'].pct_change(5)",
        description="动量",
        provenance={"model": "gpt-test", "fitness": 12.3},
    )
    entry = store.get("llm_mom_1")
    assert entry["code"].startswith("factor =")
    assert entry["description"] == "动量"
    assert entry["provenance"]["model"] == "gpt-test"
    assert "created_at" in entry


def test_all_and_delete(tmp_path):
    store = CodeFactorStore(tmp_path / "code_factors.json")
    store.upsert("a", "factor = df['close']")
    store.upsert("b", "factor = df['open']")
    assert set(store.all()) == {"a", "b"}
    assert store.delete("a") is True
    assert store.delete("missing") is False
    assert "a" not in store.all()


def test_reload_persists(tmp_path):
    path = tmp_path / "code_factors.json"
    CodeFactorStore(path).upsert("a", "factor = df['close']")
    assert CodeFactorStore(path).get("a")["code"] == "factor = df['close']"


def test_corrupt_file_loads_empty(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    assert CodeFactorStore(path).all() == {}


def test_atomic_write_no_tmp_left(tmp_path):
    path = tmp_path / "code_factors.json"
    store = CodeFactorStore(path)
    store.upsert("a", "factor = df['close']")
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_find_by_hash(tmp_path):
    from factor.code_store import code_hash

    store = CodeFactorStore(tmp_path / "code_factors.json")
    store.upsert("a", "factor = df['close']")
    h = code_hash("factor = df['close']")
    # upsert 落盘 code_hash
    assert store.get("a")["code_hash"] == h
    # 命中
    assert store.find_by_hash(h) == "a"
    # 排除自身（同名覆盖场景）→ 视为未命中
    assert store.find_by_hash(h, exclude_name="a") is None
    # 未命中
    assert store.find_by_hash("0" * 16) is None
