"""RL kernel 回测 ensemble_id 分支测试:内核参数组装正确、engine 校验拦截。"""

import numpy as np
import pandas as pd
import pytest
from gymnasium import spaces

from services.ensemble_service import PredictMemberSpecs
from services.rl_service import KERNEL_ACTION_SPACE, KERNEL_SPEC_VERSION

META = {
    "spec_version": KERNEL_SPEC_VERSION,
    "window_size": 3,
    # features 对齐真实落盘形态(rl_service.KERNEL_FEATURES):特征定义 dict 列表
    "features": [
        {"name": "f1", "source": {"PriceField": "f1"}, "normalizer": "ZScore", "clip_range": None},
        {"name": "f2", "source": {"PriceField": "f2"}, "normalizer": "ZScore", "clip_range": None},
        {"name": "f3", "source": {"PriceField": "f3"}, "normalizer": "ZScore", "clip_range": None},
    ],
    "observation_stats": {"f1": {"mean": 0.0, "std": 1.0}},
}

BARS = pd.DataFrame(
    {
        "timestamp": [1, 2, 3],
        "open": [1.0, 1.1, 1.2],
        "high": [1.2, 1.3, 1.4],
        "low": [0.9, 1.0, 1.1],
        "close": [1.1, 1.2, 1.3],
        "volume": [10.0, 10.0, 10.0],
    }
)


class FakeResult:
    total_pnl = 5.0
    max_drawdown_pct = 0.02
    sharpe_ratio = 1.0
    win_rate = 0.5
    fills = 3
    total_fees = 0.1
    total_funding_pnl = 0.0
    fills_detail = None


class FakeKernel:
    added: dict = {}

    def __init__(self, **kwargs):
        FakeKernel.kwargs = kwargs

    def add_rl_strategy(
        self, predict_fn, model_id, spec_version, window_size, features, action_space, symbol, stats=None
    ):
        FakeKernel.added = {
            "predict_fn": predict_fn,
            "model_id": model_id,
            "spec_version": spec_version,
            "window_size": window_size,
            "features": features,
            "action_space": action_space,
            "stats": stats,
        }

    def run(self, bars_by_symbol):
        return FakeResult()


class FakeProvider:
    def __init__(self):
        pass

    def load_klines(self, symbol, interval, candle_type="spot"):
        return BARS.copy()


def _fake_member_specs():
    from services.ensemble_aggregator import member_ratio_predict_fn

    class _FakeBoxModel:
        action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        def predict(self, obs, deterministic=True):
            return np.array([0.4], dtype=np.float32), None

    return PredictMemberSpecs(
        member_predict_fns=[member_ratio_predict_fn(_FakeBoxModel())],
        meta=dict(META),
        model_id="ens_bt",
        representative_path="/tmp/m1.zip",
    )


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    monkeypatch.setattr("backtest.data_provider.BacktestDataProvider", FakeProvider)
    monkeypatch.setattr("axon_quant.worker.Kernel", FakeKernel)
    import services.ensemble_service as es

    monkeypatch.setattr(es, "load_ensemble_spec", lambda eid, **kw: _fake_member_specs())


def test_kernel_backtest_uses_ensemble_spec():
    from services.rl_service import RLService

    FakeKernel.added = {}
    metrics = RLService().run_backtest("", "BTC/USDT:USDT", engine="kernel", ensemble_id="ens_bt")
    assert FakeKernel.added["model_id"] == "ens_bt"
    # 内核收到的 features 就是 meta 原始特征定义 list[dict](真实落盘口径)
    assert FakeKernel.added["features"] == META["features"]
    assert FakeKernel.added["action_space"] == KERNEL_ACTION_SPACE
    assert FakeKernel.added["stats"] is not None
    assert metrics["engine"] == "kernel"
    assert metrics["total_pnl"] == pytest.approx(5.0)


def test_run_backtest_rejects_ensemble_with_trading_env():
    from services.rl_service import RLService

    with pytest.raises(ValueError, match="kernel"):
        RLService().run_backtest("", "BTC/USDT:USDT", engine="trading_env", ensemble_id="ens_bt")
