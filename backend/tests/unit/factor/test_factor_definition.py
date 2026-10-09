# get_factor_definition：三形态从各自真相源取定义；不存在抛 FactorNotFoundError
import pytest

from factor.code_store import CodeFactorStore
from factor.composite_store import CompositeFactorStore
from factor.factor_store import FactorStore
from factor.service import FactorNotFoundError, FactorService

MOM_CODE = 'factor = df["close"].pct_change(5)'
OTHER_CODE = 'factor = df["close"] / df["open"]'


@pytest.fixture
def svc(tmp_path):
    # 三个 store 全部指向临时文件，测试绝不污染 data/factor/*.json
    return FactorService(
        code_store=CodeFactorStore(tmp_path / "code.json"),
        composite_store=CompositeFactorStore(tmp_path / "composite.json"),
        factor_store=FactorStore(tmp_path / "custom.json"),
    )


def test_definition_of_builtin_expression(svc):
    d = svc.get_factor_definition("close")
    assert d["kind"] == "expression"
    assert d["builtin"] is True
    assert d["expression"]


def test_definition_of_custom_expression(svc):
    svc.add_factor("my_e", "close - open")
    d = svc.get_factor_definition("my_e")
    assert d == {
        "kind": "expression",
        "name": "my_e",
        "expression": "close - open",
        "builtin": False,
    }


def test_definition_of_code_factor(svc):
    svc._code_store.upsert("llm_x", MOM_CODE, description="测试动量")
    d = svc.get_factor_definition("llm_x")
    assert d["kind"] == "code"
    assert d["name"] == "llm_x"
    assert d["code"] == MOM_CODE
    assert len(d["code_hash"]) == 16
    assert d["description"] == "测试动量"


def test_definition_of_composite_factor(svc):
    svc._composite_store.upsert(
        "comp_x",
        description="合成测试",
        train_window={"start": "2026-01-01", "end": "2026-02-01", "interval": "1h", "candle_type": "spot"},
        constituents=[{"code": MOM_CODE, "code_hash": "aaaaaaaaaaaaaaaa", "weight": 0.6}],
    )
    d = svc.get_factor_definition("comp_x")
    assert d["kind"] == "composite"
    assert d["method"] == "ic_zscore_v1"
    assert d["train_window"]["interval"] == "1h"
    (c,) = d["constituents"]
    assert c["code"] == MOM_CODE
    assert c["code_hash"] == "aaaaaaaaaaaaaaaa"
    assert c["weight"] == pytest.approx(0.6)


def test_definition_composite_constituent_without_hash_is_computed(svc):
    # 老合成条目成分可能缺 code_hash：按全项目统一口径（factor.code_store.code_hash）现算
    svc._composite_store.upsert(
        "comp_old",
        train_window={},
        constituents=[{"code": OTHER_CODE, "weight": 1.0}],  # 故意不给 code_hash
    )
    d = svc.get_factor_definition("comp_old")
    (c,) = d["constituents"]
    from factor.code_store import code_hash

    assert c["code_hash"] == code_hash(OTHER_CODE)
    assert len(c["code_hash"]) == 16


def test_definition_not_found(svc):
    with pytest.raises(FactorNotFoundError):
        svc.get_factor_definition("ghost_factor")
