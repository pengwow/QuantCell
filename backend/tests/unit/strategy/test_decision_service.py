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


def test_s2_empty_api_key_uses_local_placeholder(monkeypatch):
    """本地 ollama/llama-server 无鉴权：空 api_key 必须换成占位值，否则 axon-llm 拒装配"""
    calls = {}
    real_make_backend = svc.make_backend

    def spy(cfg):
        calls.update(cfg["backends"][0])
        return real_make_backend(cfg)

    monkeypatch.setattr(svc, "make_backend", spy)
    svc._s2_backend({**GEN, "model": "gpt-4o-mini", "api_key": "", "api_host": "http://127.0.0.1:8020"})
    assert calls["api_key"] == "local"
    assert calls["base_url"] == "http://127.0.0.1:8020/v1"


def test_cache_hit_and_key_differs_by_threshold(monkeypatch, tmp_path):
    _patch_providers(monkeypatch, [LAYA, GEN])
    base = {"s1_mode": "stub", "s2_mode": "replay", "open_threshold": 0.8, "hold_threshold": 0.7}
    a1 = svc.build_cascade_layer(base, run_mode="backtest", replay_dir=tmp_path)
    a2 = svc.build_cascade_layer(dict(base), run_mode="backtest", replay_dir=tmp_path)
    b = svc.build_cascade_layer({**base, "open_threshold": 0.9}, run_mode="backtest", replay_dir=tmp_path)
    assert a1 is a2
    assert a1 is not b


def test_force_rule_bypasses_cache(monkeypatch, tmp_path):
    # force_rule 影响缓存键（装配时 S2 是否并入不同）
    _patch_providers(monkeypatch, [LAYA, GEN])
    base = {"s1_mode": "stub", "s2_mode": "replay"}
    normal = svc.build_cascade_layer(base, run_mode="paper", replay_dir=tmp_path)
    forced = svc.build_cascade_layer({**base, "force_rule": True}, run_mode="paper", replay_dir=tmp_path)
    assert normal is not forced


def test_backtest_respects_explicit_s1_mode(monkeypatch, tmp_path):
    """回测不再强制离线：装配语义与 paper/live 一致。

    - 显式 s1_mode 被尊重（如 stub 离线复跑）；
    - 未显式指定时缺省走 http（live Laya），让回测产出真实 S1 决策数据。
    """
    _patch_providers(monkeypatch, [LAYA, GEN])
    seen_modes: list[str] = []
    real_make_backend = svc.make_decision_backend

    def spy(cfg):
        seen_modes.append(str(cfg.get("mode")))
        return real_make_backend(cfg)

    monkeypatch.setattr(svc, "make_decision_backend", spy)

    # 显式 stub：尊重用户，装配离线后端
    svc.build_cascade_layer({"s1_mode": "stub"}, run_mode="backtest", replay_dir=tmp_path)
    assert seen_modes == ["stub"]

    # 未显式指定：缺省 http(live)，s2 缺省 live 需要 GEN 配置在位
    layer = svc.build_cascade_layer({}, run_mode="backtest", replay_dir=tmp_path)
    assert seen_modes == ["stub", "http"]
    assert layer is not None


def test_cache_key_includes_replay_path(monkeypatch, tmp_path):
    """不同录制文件不能复用同一 layer 实例，否则会串写文件"""
    _patch_providers(monkeypatch, [LAYA, GEN])
    base = {"s1_mode": "stub", "s2_mode": "replay"}
    a = svc.build_cascade_layer({**base, "replay_file": "a.jsonl"}, run_mode="backtest", replay_dir=tmp_path)
    b = svc.build_cascade_layer({**base, "replay_file": "b.jsonl"}, run_mode="backtest", replay_dir=tmp_path)
    assert a is not b
    assert a.path != b.path


def test_decision_replay_skips_assembly(monkeypatch, tmp_path):
    replay_file = tmp_path / "d.jsonl"
    replay_file.write_text("", encoding="utf-8")
    assert svc.build_cascade_layer({"decision_replay": str(replay_file)}, run_mode="backtest") is None


def test_meta_carries_thresholds(monkeypatch, tmp_path):
    """录制 meta 落 open/hold 阈值：前端概率条参考线与置信度差值的数据源"""
    _patch_providers(monkeypatch, [LAYA, GEN])
    layer = svc.build_cascade_layer(
        {"s1_mode": "stub", "open_threshold": 0.75, "hold_threshold": 0.60},
        run_mode="backtest",
        replay_dir=tmp_path,
    )
    assert layer._meta["open_threshold"] == 0.75
    assert layer._meta["hold_threshold"] == 0.60
