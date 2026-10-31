"""cascade 端到端离线链路：loader 注入 stub layer → on_bar → Action + 录制。

真实 Laya HTTP 联调需另起服务验证；本用例用 stub 后端覆盖装配、注入、决策、
录制与 Action 映射全链路，不触网。
"""

from backtest.strategy_loader_service import StrategyLoaderService
from strategy import StrategyContext


def _providers():
    return [
        {
            "id": "laya",
            "provider": "laya",
            "category": "system_one",
            "is_default": True,
            "is_enabled": "laya",
            "api_host": "http://127.0.0.1:8787",
            "api_key": "",
            "models": [{"id": "laya", "model_name": "laya"}],
        },
        {
            "id": "openai",
            "provider": "openai",
            "category": "system_two",
            "is_default": True,
            "is_enabled": "gpt-4o-mini",
            "api_host": "https://api.openai.com",
            "api_key": "sk-x",
            "models": [{"id": "gpt-4o-mini", "model_name": "gpt-4o-mini"}],
        },
    ]


def test_cascade_pipeline_produces_action_and_recording(monkeypatch, tmp_path):
    import strategy.decision_service as svc

    monkeypatch.setattr(svc, "get_all_providers", _providers)
    monkeypatch.setenv("QUANTCELL_DECISION_REPLAY_DIR", str(tmp_path))
    svc.reset_cache()

    instance = StrategyLoaderService.load_strategy(
        strategy_name="cascade_signal",
        strategy_params={
            "mode": "cascade",
            "s1_mode": "stub",
            "s2_mode": "replay",
            "target_ratio": 0.1,
            "replay_file": "it.jsonl",
        },
        instrument_ids=[{"symbol": "BTCUSDT"}],
        bar_types=["BTCUSDT-1h"],
        run_mode="backtest",
    )

    ctx = StrategyContext(symbol="BTCUSDT")
    last = None
    for price in [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]:
        bar = {"close": price, "open": price, "high": price, "low": price, "volume": 1.0}
        last = instance.on_bar(bar, ctx)

    assert last is not None
    assert str(last.action_type) in ("buy", "sell", "hold")
    assert (tmp_path / "it.jsonl").is_file()

    svc.reset_cache()
