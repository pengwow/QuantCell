"""RL 回测入口的 `engine` 字段（trading_env / kernel 两条口径）。

覆盖：
1. 默认走 `TradingEnv` 评估时响应带 `engine="trading_env"`；
2. 显式 `engine="kernel"` 时走 `worker.Kernel` + RL host，响应带 `engine="kernel"`；
3. 未知 engine 明确报错，不静默回退。

不训练真模型：SB3 模型、数据源、内核全部用假对象替换。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from services.rl_service import RLService


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """最小 OHLCV：时间列用 datetime，覆盖内核路径的 `_df_to_rust_bars` 换算。"""
    n = 4
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [10.0] * n,
        }
    )


def test_run_backtest_default_engine_is_trading_env(monkeypatch, ohlcv_df):
    svc = RLService()
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines",
        lambda self, *args, **kwargs: ohlcv_df.copy(),
    )
    monkeypatch.setattr(svc, "create_env", lambda *args, **kwargs: object())
    monkeypatch.setattr(svc, "load_model", lambda path: object())
    monkeypatch.setattr(
        "rl.evaluation.evaluate_model",
        lambda model, env: SimpleNamespace(
            total_pnl=12.0,
            total_return_pct=0.12,
            sharpe_ratio=0.8,
            max_drawdown_pct=3.0,
            win_rate=0.5,
            num_trades=2,
            profit_factor=1.5,
        ),
    )

    result = svc.run_backtest("fake.zip", "BTCUSDT")

    assert result["engine"] == "trading_env"
    assert result["total_pnl"] == 12.0


def test_run_backtest_kernel_engine_registers_rl_host(monkeypatch, ohlcv_df):
    # `worker` 是 axon_quant 在 __init__ 里挂出来的子模块对象，不是可 import 的
    # 模块路径，所以这里按属性取，而不是 importorskip("axon_quant.worker")
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    svc = RLService()
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines",
        lambda self, *args, **kwargs: ohlcv_df.copy(),
    )
    monkeypatch.setattr(svc, "load_model", lambda path: object())

    calls: dict[str, object] = {}

    class FakeKernel:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def add_rl_strategy(self, *args, **kwargs):
            calls["register"] = args

        def run(self, bars_by_symbol, **kwargs):
            calls["bars"] = bars_by_symbol
            return SimpleNamespace(
                total_pnl=250.0,
                sharpe_ratio=1.2,
                max_drawdown_pct=0.05,
                win_rate=0.5,
                fills=3,
                final_nav=100_250.0,
            )

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)

    result = svc.run_backtest("data/models/demo_ppo_1.zip", "BTCUSDT", engine="kernel")

    assert result["engine"] == "kernel"
    assert result["num_trades"] == 3
    assert result["total_return_pct"] == 0.25
    assert result["max_drawdown_pct"] == pytest.approx(5.0)
    # 注册参数顺序：predict / model_id / spec_version / window / features / action_space / symbol
    register = calls["register"]
    assert register[1] == "demo_ppo_1"
    assert register[6] == "BTC/USDT", "内核按 BASE/QUOTE 建 instrument"
    assert calls["bars"].keys() == {"BTC/USDT"}


def test_run_backtest_rejects_unknown_engine(monkeypatch, ohlcv_df):
    svc = RLService()
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines",
        lambda self, *args, **kwargs: ohlcv_df.copy(),
    )

    with pytest.raises(ValueError, match="未知 engine"):
        svc.run_backtest("fake.zip", "BTCUSDT", engine="unknown")


def test_kernel_backtest_runs_real_kernel(monkeypatch, ohlcv_df):
    """真跑一次内核：假模型固定输出 0.5 占比，4 根 bar 必须产生成交。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    import numpy as np

    class FixedModel:
        def predict(self, obs, deterministic=True):
            return np.array([0.5], dtype=np.float32), None

    svc = RLService()
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines",
        lambda self, *args, **kwargs: ohlcv_df.copy(),
    )
    monkeypatch.setattr(svc, "load_model", lambda path: FixedModel())

    result = svc.run_backtest("fake.zip", "BTCUSDT", interval="1h", engine="kernel")

    assert result["engine"] == "kernel"
    assert result["num_trades"] >= 1, "0.5 权益占比必须真的成交"
    assert result["data_bars"] == len(ohlcv_df)


# =============================================================================
# StrategyManager: RL 分支的模型校验（不经过 StrategyLoaderService）
# =============================================================================


def _write_model_with_meta(tmp_path: Path, spec_version: str = "v1") -> Path:
    """伪造 SB3 产物：模型文件 + 观测规格元数据旁车。"""
    model_path = tmp_path / "demo_ppo.zip"
    model_path.write_bytes(b"fake-sb3-model")
    Path(f"{model_path}.meta.json").write_text(
        json.dumps({"model_id": "demo_ppo", "spec_version": spec_version, "window_size": 1}),
        encoding="utf-8",
    )
    return model_path


def test_build_rl_kernel_rejects_bad_model_or_spec(tmp_path):
    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path, spec_version="v1")
    mgr = StrategyManager(max_workers=1)
    try:
        with pytest.raises(ValueError, match="模型文件不存在"):
            mgr.build_rl_kernel(1, {"model_path": str(tmp_path / "missing.zip")}, "1h", ["BTCUSDT"])

        with pytest.raises(ValueError, match="spec_version 不匹配"):
            mgr.build_rl_kernel(1, {"model_path": str(model_path), "spec_version": "v2"}, "1h", ["BTCUSDT"])
    finally:
        mgr.shutdown()


def test_build_rl_kernel_registers_rl_host(monkeypatch, tmp_path):
    """校验通过后必须调用 add_rl_strategy 注册 host，而不是回退到规则策略。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path)
    registered: dict[str, tuple] = {}

    class FakeKernel:
        def __init__(self, **kwargs):
            registered["init"] = kwargs

        def add_rl_strategy(self, *args):
            registered["register"] = args

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())

    mgr = StrategyManager(max_workers=1)
    try:
        mgr.build_rl_kernel(1, {"model_path": str(model_path)}, "1h", ["BTCUSDT"])
    finally:
        mgr.shutdown()

    assert registered["init"]["interval"] == "1h"
    args = registered["register"]
    assert args[1] == "demo_ppo"
    assert args[2] == "v1", "spec_version 取自元数据校验结果"
    assert args[6] == "BTC/USDT"
