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


def test_description_roundtrip(tmp_path):
    """描述随表达式一起落盘；all() 仍只返回表达式映射（旧契约不变）。"""
    from factor.factor_store import FactorStore

    path = tmp_path / "f.json"
    FactorStore(path).upsert("my_mom", "close - open", "5 日动量")
    reloaded = FactorStore(path)
    assert reloaded.all() == {"my_mom": "close - open"}
    assert reloaded.description_of("my_mom") == "5 日动量"
    assert reloaded.description_of("ghost") == ""


def test_legacy_string_format_upgraded(tmp_path):
    """旧格式 {name: "expr"} 加载时自动升级，description 视为空。"""
    from factor.factor_store import FactorStore

    path = tmp_path / "f.json"
    path.write_text('{"legacy": "close - open"}', encoding="utf-8")
    store = FactorStore(path)
    assert store.all() == {"legacy": "close - open"}
    assert store.description_of("legacy") == ""
