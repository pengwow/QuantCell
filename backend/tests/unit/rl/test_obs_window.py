"""P3 ObsEncoder v1：原始 OHLCV 归一化窗口 obs（opt-in）+ 冻结统计量链。

守四件事：缺省指标向量口径零漂移、窗口 obs 数值正确、统计量缺口显式报错、
meta 记录 obs 口径与特征清单；另测内核推理路径对原始序列模型的显式拒绝。
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.rl_service import (
    OBS_CHANNELS,
    OBS_MODE_FEATURES,
    OBS_MODE_OHLCV_WINDOW,
    ObsWindowEnv,
    RLService,
    RLTrainConfig,
    compute_obs_stats,
    obs_spec_from_meta,
    require_kernel_obs,
)


def _ohlcv(rows: int = 200, *, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.5, rows))
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": rng.uniform(10.0, 20.0, rows),
        }
    )


# =============================================================================
# 缺省路径零漂移
# =============================================================================


def test_default_obs_mode_is_features_and_env_stays_native():
    svc = RLService()
    env = svc.create_env(_ohlcv())
    assert not isinstance(env, ObsWindowEnv)
    obs = env.reset()
    assert len(obs["features"]) == 2  # close ZScore + volume（现行口径）

    spec = obs_spec_from_meta({})  # 旧 meta：无 obs 键
    assert spec == {"mode": OBS_MODE_FEATURES, "window": 1, "features": ["close", "volume"], "stats": None}


def test_unknown_obs_mode_rejected_at_config():
    with pytest.raises(ValueError, match="未知 obs_mode"):
        RLTrainConfig(obs_mode="raw_ticks")
    with pytest.raises(ValueError, match="obs_window"):
        RLTrainConfig(obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=0)


# =============================================================================
# 窗口 obs 数值
# =============================================================================


def test_window_obs_shape_and_zscore():
    svc = RLService()
    data = _ohlcv(rows=50)
    window = 4
    stats = compute_obs_stats(data)
    env = ObsWindowEnv(svc.create_env(data), data, window=window, stats=stats)

    obs = env.reset()
    assert obs.shape == (window * len(OBS_CHANNELS),)
    # reset 在 bar 0：窗口前 window-1 格用首根 bar 补齐，最后一格是 bar 0 本身
    first_bar = np.array([data[c].iloc[0] for c in OBS_CHANNELS])
    mean = np.array([s["mean"] for s in stats])
    std = np.array([s["std"] for s in stats])
    expected = np.tile((first_bar - mean) / std, (window, 1)).reshape(-1).astype(np.float32)
    assert np.allclose(obs, expected)

    obs1, *_ = env.step([0.5])
    bar1 = np.array([data[c].iloc[1] for c in OBS_CHANNELS])
    expected_tail = np.vstack([np.tile((first_bar - mean) / std, (window - 1, 1)), (bar1 - mean) / std]).reshape(-1)
    assert np.allclose(obs1, expected_tail.astype(np.float32))


def test_window_obs_uses_frozen_stats_not_recomputed():
    """传入训练窗统计量后，obs 必须按它归一化（而不是按推理数据重算）。"""
    svc = RLService()
    train = _ohlcv(rows=100, seed=1)
    oos = _ohlcv(rows=100, seed=2)
    train_stats = compute_obs_stats(train)

    env = ObsWindowEnv(svc.create_env(oos), oos, window=2, stats=train_stats)
    obs = env.reset()
    mean = np.array([s["mean"] for s in train_stats])
    std = np.array([s["std"] for s in train_stats])
    bar0 = np.array([oos[c].iloc[0] for c in OBS_CHANNELS])
    assert np.allclose(obs[: len(OBS_CHANNELS)], ((bar0 - mean) / std).astype(np.float32))
    # 与按 oos 自身统计量重算的结果不同（证明没有静默重算）
    own = ObsWindowEnv(svc.create_env(oos), oos, window=2)
    assert not np.allclose(obs, own.reset())


def test_constant_channel_maps_to_zero_not_nan():
    svc = RLService()
    data = _ohlcv(rows=20)
    data["high"] = 1000.0  # 常量通道 → std=0
    env = ObsWindowEnv(svc.create_env(data), data, window=3)
    obs = env.reset()
    assert np.isfinite(obs).all()


# =============================================================================
# 冻结链边界：显式报错，不静默错误归一化
# =============================================================================


def _meta_window(**overrides) -> dict:
    meta = {
        "obs_mode": OBS_MODE_OHLCV_WINDOW,
        "obs_window": 8,
        "obs_features": list(OBS_CHANNELS),
        "obs_stats": compute_obs_stats(_ohlcv(rows=30)),
    }
    meta.update(overrides)
    return meta


def test_obs_spec_from_meta_roundtrip():
    spec = obs_spec_from_meta(_meta_window())
    assert spec["mode"] == OBS_MODE_OHLCV_WINDOW
    assert spec["window"] == 8
    assert spec["features"] == list(OBS_CHANNELS)
    assert len(spec["stats"]) == len(OBS_CHANNELS)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"obs_stats": None}, "obs_stats 缺失"),
        ({"obs_stats": [{"mean": 0.0, "std": 1.0}]}, "obs_stats 缺失"),
        ({"obs_window": 0}, "obs_window 非法"),
        ({"obs_features": []}, "obs_features"),
        ({"obs_features": ["close"], "obs_stats": [{"mean": 0.0, "std": float("nan")}]}, "数值非法"),
    ],
)
def test_obs_spec_mismatch_raises(overrides, match):
    with pytest.raises(ValueError, match=match):
        obs_spec_from_meta(_meta_window(**overrides))


def test_compute_obs_stats_rejects_bad_data():
    with pytest.raises(ValueError, match="缺少"):
        compute_obs_stats(pd.DataFrame({"close": [1.0, 2.0]}))
    bad = _ohlcv(rows=10)
    bad.loc[3, "volume"] = np.nan
    with pytest.raises(ValueError, match="非有限值"):
        compute_obs_stats(bad)


def test_kernel_path_rejects_window_obs_model():
    require_kernel_obs({})  # 旧模型（无 obs 键）放行
    with pytest.raises(ValueError, match="暂不支持内核推理"):
        require_kernel_obs(_meta_window())


def test_kernel_backtest_rejects_window_obs_model(tmp_path):
    model_path = tmp_path / "win_ppo.zip"
    model_path.write_bytes(b"fake")
    Path(f"{model_path}.meta.json").write_text(json.dumps(_meta_window()), encoding="utf-8")

    svc = RLService()
    with pytest.raises(ValueError, match="暂不支持内核推理"):
        svc._run_kernel_backtest(str(model_path), _ohlcv(rows=20), "BTCUSDT", "1h", 100_000.0)


def test_run_backtest_rebuilds_window_obs_from_meta(monkeypatch, tmp_path):
    """trading_env 回测必须按 meta 重建同一套 obs 编码（否则维度对不上模型）。"""
    model_path = tmp_path / "win_ppo.zip"
    model_path.write_bytes(b"fake")
    meta = _meta_window(obs_window=4)
    Path(f"{model_path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")

    svc = RLService()
    captured: dict[str, object] = {}

    def _fake_create_env(data, *args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(svc, "create_env", _fake_create_env)
    monkeypatch.setattr(svc, "load_model", lambda path: object())
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines", lambda self, *a, **k: _ohlcv(rows=20)
    )
    monkeypatch.setattr(
        "rl.evaluation.evaluate_model",
        lambda model, env, transaction_cost=None: type(
            "_M",
            (),
            {
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "num_trades": 0,
                "profit_factor": 0.0,
                "turnover": 0.0,
            },
        )(),
    )

    svc.run_backtest(str(model_path), "BTCUSDT")

    assert captured["obs_mode"] == OBS_MODE_OHLCV_WINDOW
    assert captured["obs_window"] == 4
    assert len(captured["obs_stats"]) == len(OBS_CHANNELS)


# =============================================================================
# meta 记录
# =============================================================================


def test_train_meta_records_obs_contract(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    data = _ohlcv(rows=60)
    result = svc.train(
        RLTrainConfig(
            data=data,
            total_timesteps=32,
            model_name="obs_window",
            obs_mode=OBS_MODE_OHLCV_WINDOW,
            obs_window=8,
        )
    )
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["obs_mode"] == OBS_MODE_OHLCV_WINDOW
    assert meta["obs_window"] == 8
    assert meta["obs_features"] == list(OBS_CHANNELS)
    assert [entry["mean"] for entry in meta["obs_stats"]] == [s["mean"] for s in compute_obs_stats(data)]
    # 模型可加载、obs 维度与 spec 一致（32 步训练只是烟测，不代表性能）
    loaded_env = svc.create_env(
        data, obs_mode=meta["obs_mode"], obs_window=meta["obs_window"], obs_stats=meta["obs_stats"]
    )
    assert loaded_env.reset().shape == (8 * len(OBS_CHANNELS),)


def test_default_train_meta_records_features_mode(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    result = svc.train(RLTrainConfig(data=_ohlcv(rows=40), total_timesteps=32, model_name="obs_default"))
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["obs_mode"] == OBS_MODE_FEATURES
    assert meta["obs_window"] == 1
    assert meta["obs_features"] == ["close", "volume"]
    assert meta["obs_stats"] is None
