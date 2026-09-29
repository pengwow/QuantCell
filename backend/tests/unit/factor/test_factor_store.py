# 自定义因子 JSON 持久化单测（全部使用 tmp_path，不写真实数据目录）
def test_save_and_reload(tmp_path):
    from factor.factor_store import FactorStore

    path = tmp_path / "custom_factors.json"
    FactorStore(path).upsert("my_mom", "close / Ref(close, 5) - 1")
    assert FactorStore(path).all() == {"my_mom": "close / Ref(close, 5) - 1"}


def test_overwrite_and_delete(tmp_path):
    from factor.factor_store import FactorStore

    store = FactorStore(tmp_path / "f.json")
    store.upsert("a", "close")
    store.upsert("a", "open")
    assert store.all() == {"a": "open"}
    assert store.delete("a") is True
    assert store.delete("ghost") is False


def test_corrupt_file_resets(tmp_path):
    from factor.factor_store import FactorStore

    path = tmp_path / "f.json"
    path.write_text("{bad json", encoding="utf-8")
    assert FactorStore(path).all() == {}
