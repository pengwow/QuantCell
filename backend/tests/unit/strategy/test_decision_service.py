"""cascade layer 装配：配置缺失报错、s2_mode/force_rule 分支、缓存命中。

配置源是 system_config 的 ai_model.* （设置页写入），与 ai_models 表是两条链路。
"""

import pytest

import strategy.decision_service as svc

LAYA = {
    "id": "laya",
    "provider": "laya",
    "category": "system_one",
    "is_default": True,
    "is_enabled": "laya",
    "api_host": "http://127.0.0.1:8787",
    "api_key": "secret",
    "models": [
        {"id": "laya", "model_name": "laya"},
        {"id": "laya-multilingual", "model_name": "laya-multilingual"},
    ],
}
GEN = {
    "id": "openai",
    "provider": "openai",
    "category": "system_two",
    "is_default": True,
    "is_enabled": "gpt-4o-mini",
    "api_host": "https://api.openai.com",
    "api_key": "sk-x",
    "models": [{"id": "gpt-4o-mini", "model_name": "gpt-4o-mini"}],
}


@pytest.fixture(autouse=True)
def _reset_cache():
    svc.reset_cache()
    yield
    svc.reset_cache()


def _patch_providers(monkeypatch, providers):
    monkeypatch.setattr(svc, "get_all_providers", lambda: providers)


def test_missing_system_one_raises(monkeypatch, tmp_path):
    _patch_providers(monkeypatch, [GEN])
    with pytest.raises(ValueError, match="System 1"):
        svc.build_cascade_layer({"s1_mode": "stub"}, run_mode="backtest", replay_dir=tmp_path)


def test_missing_models_raises(monkeypatch, tmp_path):
    _patch_providers(monkeypatch, [{**LAYA, "models": []}, GEN])
    with pytest.raises(ValueError, match="模型列表"):
        svc.build_cascade_layer({"s1_mode": "stub"}, run_mode="backtest", replay_dir=tmp_path)


def test_enabled_model_is_selected(monkeypatch):
    _patch_providers(monkeypatch, [{**LAYA, "is_enabled": "laya-multilingual"}, GEN])
    assert svc._default_ai_model("system_one")["model"] == "laya-multilingual"


def test_category_default_falls_back_to_first(monkeypatch):
    # 同类型内没有 is_default 时用第一个
    _patch_providers(monkeypatch, [{**LAYA, "is_default": False}, GEN])
    assert svc._default_ai_model("system_one")["id"] == "laya"


def test_replay_mode_uses_rule_fallback(monkeypatch, tmp_path):
    _patch_providers(monkeypatch, [LAYA, GEN])
    layer = svc.build_cascade_layer(
        {"s1_mode": "stub", "s2_mode": "replay", "open_threshold": 0.8, "hold_threshold": 0.7},
        run_mode="backtest",
        replay_dir=tmp_path,
    )
    # RuleFallback 版本可直接决策，不触发任何 LLM
    d = layer.decide(
        {"features": {"sma5_vs_sma20": 0.02, "ret_1": 0.01}},
        {
            "next_direction": {
                "type": "choice",
                "instructions": {"question": "?", "focus": "仅依据给定特征"},
                "criteria": {"buy": {"what": "涨"}, "sell": {"what": "跌"}, "hold": {"what": "震荡"}},
            }
        },
    )
    assert d["source"] in ("sdm_direct", "fallback")


def test_cache_hit_and_key_differs_by_threshold(monkeypatch, tmp_path):
    _patch_providers(monkeypatch, [LAYA, GEN])
    base = {"s1_mode": "stub", "s2_mode": "replay", "open_threshold": 0.8, "hold_threshold": 0.7}
    a1 = svc.build_cascade_layer(base, run_mode="backtest", replay_dir=tmp_path)
    a2 = svc.build_cascade_layer(dict(base), run_mode="backtest", replay_dir=tmp_path)
    b = svc.build_cascade_layer({**base, "open_threshold": 0.9}, run_mode="backtest", replay_dir=tmp_path)
    assert a1 is a2
    assert a1 is not b


def test_force_rule_bypasses_cache(monkeypatch, tmp_path):
    _patch_providers(monkeypatch, [LAYA, GEN])
    base = {"s1_mode": "stub", "s2_mode": "replay"}
    normal = svc.build_cascade_layer(base, run_mode="backtest", replay_dir=tmp_path)
    forced = svc.build_cascade_layer({**base, "force_rule": True}, run_mode="backtest", replay_dir=tmp_path)
    assert normal is not forced


def test_decision_replay_skips_assembly(monkeypatch, tmp_path):
    replay_file = tmp_path / "d.jsonl"
    replay_file.write_text("", encoding="utf-8")
    assert svc.build_cascade_layer({"decision_replay": str(replay_file)}, run_mode="backtest") is None
