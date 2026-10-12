# get_factor_definition：三形态从 DB 取定义；不存在抛 FactorNotFoundError
import pytest

from factor.engine import code_hash
from factor.service import FactorNotFoundError

MOM_CODE = 'factor = df["close"].pct_change(5)'
OTHER_CODE = 'factor = df["close"] / df["open"]'

TRAIN_WINDOW = {
    "start": "2026-01-01T00:00:00",
    "end": "2026-01-07T23:00:00",
    "interval": "1h",
    "candle_type": "spot",
}


def _labels(svc):
    return {d["name"]: d["label"] for d in svc.get_factor_details()}


def test_label_maintenance_expression(svc):
    """表达式因子 label：新建可设；编辑可改；None 保留原值；空串清空回退 name。"""
    svc.add_factor("lbl_expr", "close - open", label="动量因子")
    assert _labels(svc)["lbl_expr"] == "动量因子"
    # 编辑改 label
    svc.add_factor("lbl_expr", "close - open", label="新动量")
    assert _labels(svc)["lbl_expr"] == "新动量"
    # 编辑不传 label（None）→ 保留原值
    svc.add_factor("lbl_expr", "close - open")
    assert _labels(svc)["lbl_expr"] == "新动量"
    # 编辑传空串 → 清空回退 name
    svc.add_factor("lbl_expr", "close - open", label="")
    assert _labels(svc)["lbl_expr"] == "lbl_expr"


def test_label_maintenance_code_and_composite(svc):
    """代码/合成因子 label：新建可设；编辑不传则保留原值。"""
    svc.save_code_factor("lbl_code", MOM_CODE, label="代码动量")
    svc.save_composite(
        "lbl_comp",
        "",
        [MOM_CODE, OTHER_CODE],
        [0.5, 0.5],
        [{}, {}],
        TRAIN_WINDOW,
        label="合成因子",
    )
    labels = _labels(svc)
    assert labels["lbl_code"] == "代码动量"
    assert labels["lbl_comp"] == "合成因子"
    # 编辑代码因子不传 label → 保留
    svc.save_code_factor("lbl_code", MOM_CODE)
    assert _labels(svc)["lbl_code"] == "代码动量"
    # 编辑合成因子不传 label → 保留
    svc.save_composite("lbl_comp", "", [MOM_CODE, OTHER_CODE], [0.5, 0.5], [{}, {}], TRAIN_WINDOW)
    assert _labels(svc)["lbl_comp"] == "合成因子"


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
    svc.save_code_factor("llm_x", MOM_CODE, description="测试动量", provenance={"source": "test"})
    d = svc.get_factor_definition("llm_x")
    assert d["kind"] == "code"
    assert d["name"] == "llm_x"
    assert d["code"] == MOM_CODE
    assert len(d["code_hash"]) == 16
    assert d["description"] == "测试动量"


def test_definition_of_composite_factor(svc):
    svc.save_composite(
        "comp_x",
        description="合成测试",
        codes=[MOM_CODE, OTHER_CODE],
        weights=[0.6, 0.4],
        ts_stats_list=[{}, {}],
        train_window={"start": "2026-01-01", "end": "2026-02-01", "interval": "1h", "candle_type": "spot"},
    )
    d = svc.get_factor_definition("comp_x")
    assert d["kind"] == "composite"
    assert d["method"] == "ic_zscore_v1"
    assert d["train_window"]["interval"] == "1h"
    assert len(d["constituents"]) == 2
    c = d["constituents"][0]
    assert c["code"] == MOM_CODE
    assert c["code_hash"] == code_hash(MOM_CODE)
    assert c["weight"] == pytest.approx(0.6)


def test_definition_not_found(svc):
    with pytest.raises(FactorNotFoundError):
        svc.get_factor_definition("ghost_factor")


def test_details_expression_none_for_code_and_composite(svc):
    svc.save_code_factor("llm_x", MOM_CODE, provenance={"source": "test"})
    svc.save_composite(
        "comp_x",
        description="",
        codes=[MOM_CODE, OTHER_CODE],
        weights=[1.0, 0.0],
        ts_stats_list=[{}, {}],
        train_window={"start": "2026-01-01", "end": "2026-02-01", "interval": "1h", "candle_type": "spot"},
    )
    details = {d["name"]: d for d in svc.get_factor_details()}
    assert details["llm_x"]["expression"] is None
    assert details["llm_x"]["kind"] == "code"
    assert details["comp_x"]["expression"] is None
    assert details["comp_x"]["kind"] == "composite"
    assert details["comp_x"]["constituents_count"] == 2
    # 表达式因子不受影响
    assert details["close"]["expression"]


def test_definition_endpoint_200_and_404(svc, monkeypatch):
    from fastapi.testclient import TestClient

    from factor import routes
    from main import app
    from utils.auth import get_current_user

    monkeypatch.setattr(routes, "factor_service", svc)
    app.dependency_overrides[get_current_user] = lambda: {"username": "t", "id": 1}
    client = TestClient(app)
    try:
        r = client.get("/api/v1/factor/factors/close/definition")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["kind"] == "expression"

        r2 = client.get("/api/v1/factor/factors/ghost_x/definition")
        assert r2.status_code == 404
    finally:
        app.dependency_overrides.clear()
