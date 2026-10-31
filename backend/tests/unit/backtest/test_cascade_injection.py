"""load_strategy 对 mode=cascade 注入 _cascade_layer"""

import pytest

from backtest.strategy_loader_service import StrategyLoaderService


@pytest.fixture
def isolated_register():
    """隔离 @register 全局注册表。

    cascade_signal / llm_signal 模板在模块顶层用 @register 装饰器注册；同一进程里
    StrategyLoader 可能已自动注册过同名策略，loader 再以裸模块名重复导入会抛
    「策略名重复」。先清掉同名项，使本次导入成为首次注册，避免测试受执行顺序影响。
    """
    import strategy.loader as loader_module

    for name in ("cascade_signal", "llm_signal"):
        loader_module._REGISTRY.pop(name, None)
    yield


def test_cascade_mode_injects_layer(monkeypatch, isolated_register):
    sentinel = object()

    import strategy.decision_service as svc

    monkeypatch.setattr(svc, "build_cascade_layer", lambda params, run_mode=None, replay_dir=None: sentinel)

    instance = StrategyLoaderService.load_strategy(
        strategy_name="cascade_signal",
        strategy_params={"mode": "cascade"},
        instrument_ids=[{"symbol": "BTCUSDT"}],
        bar_types=["BTCUSDT-1h"],
        run_mode="backtest",
    )
    assert instance.config.params["_cascade_layer"] is sentinel


def test_non_cascade_mode_does_not_inject(monkeypatch):
    import strategy.decision_service as svc

    monkeypatch.setattr(svc, "build_cascade_layer", lambda *a, **k: object())

    instance = StrategyLoaderService.load_strategy(
        strategy_name="dual_ma",
        strategy_params={"mode": "heuristic"},
        instrument_ids=[{"symbol": "BTCUSDT"}],
        bar_types=["BTCUSDT-1h"],
        run_mode="backtest",
    )
    assert "_cascade_layer" not in instance.config.params


def test_llm_mode_still_wrapped_by_llm_replay(monkeypatch, tmp_path, isolated_register):
    """mode=llm 的既有语义不受 cascade 分支影响"""
    from strategy import llm_replay

    path = tmp_path / "r.jsonl"
    path.write_text('{"fingerprint":"x","response":"{}"}\n', encoding="utf-8")
    instance = StrategyLoaderService.load_strategy(
        strategy_name="llm_signal",
        strategy_params={"mode": "llm", "llm_provider": lambda p: "{}", "llm_replay_path": str(path)},
        instrument_ids=[{"symbol": "BTCUSDT"}],
        bar_types=["BTCUSDT-1h"],
        run_mode="backtest",
    )
    assert callable(instance.config.params["llm_provider"])
    assert "_cascade_layer" not in instance.config.params
