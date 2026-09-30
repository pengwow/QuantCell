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
