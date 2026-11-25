"""P3-2：派生微结构通道接进 obs（bookDepth/bookTicker 特征列 + tick 类 OHLCV）。

用合成 tick / 盘口数据跑真实 data_adapters 聚合，验证「适配器列名 → obs 通道」
映射正确、缺列显式拒绝、NaN 防御、config/meta 契约。
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.rl_service import (
    OBS_CHANNELS,
    OBS_EXTRA_CHANNELS,
    OBS_MODE_FEATURES,
    OBS_MODE_OHLCV_WINDOW,
    ObsWindowEnv,
    RLService,
    RLTrainConfig,
    obs_spec_from_meta,
)

# =============================================================================
# 合成数据 → 真实适配器聚合
# =============================================================================


def _raw_book_ticker(ticks: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=ticks, freq="min", tz="UTC")
    mid = 100.0 + np.sin(np.arange(ticks) / 7.0)
    # spread 必须逐 tick 变化：常量 spread 会被当成常量通道归一化为 0，测不出映射
    half_spread = 0.05 + 0.01 * np.cos(np.arange(ticks) / 5.0)
    return pd.DataFrame(
        {
            "timestamp": idx,
            "bidPrice": mid - half_spread,
            "askPrice": mid + half_spread,
            "bidQty": np.linspace(1.0, 3.0, ticks),
        }
    )


def _raw_book_depth(ticks: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=ticks, freq="min", tz="UTC")
    mid = 100.0 + np.cos(np.arange(ticks) / 9.0)
    return pd.DataFrame(
        {
            "timestamp": idx,
            "bid_price": mid - 0.02,
            "ask_price": mid + 0.02,
            "bid_qty": np.linspace(5.0, 8.0, ticks),
            "ask_qty": np.linspace(4.0, 6.0, ticks),
        }
    )


def _raw_trades(ticks: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=ticks, freq="min", tz="UTC")
    price = 100.0 + np.arange(ticks) * 0.01
    return pd.DataFrame({"timestamp": idx, "price": price, "quantity": np.full(ticks, 2.0)})


def _aggregate_book_ticker() -> pd.DataFrame:
    from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

    return OrderBookAdapter()._process_book_ticker(_raw_book_ticker(), "5min")


def _aggregate_book_depth() -> pd.DataFrame:
    from backtest.data_adapters.orderbook_adapter import OrderBookAdapter

    return OrderBookAdapter()._process_book_depth(_raw_book_depth(), "5min")


def _aggregate_trades() -> pd.DataFrame:
    from backtest.data_adapters.tick_adapter import TickAdapter

    return TickAdapter()._aggregate_to_ohlcv(_raw_trades(), "timestamp", "price", "quantity", "5min")


# =============================================================================
# 映射表 = 适配器实际列名
# =============================================================================


def test_channel_registry_matches_adapter_columns():
    book_ticker = _aggregate_book_ticker()
    book_depth = _aggregate_book_depth()
    trades = _aggregate_trades()

    for spec in OBS_EXTRA_CHANNELS.values():
        column = spec["column"]
        assert column in {c.lower() for c in book_ticker.columns}
    # bookDepth 只产 mid 价特征（没有 spread）；tick 类只有 OHLCV
    assert OBS_EXTRA_CHANNELS["spread"]["column"] not in {c.lower() for c in book_depth.columns}
    assert all(c.lower() in {"open", "high", "low", "close", "volume", "timestamp"} for c in trades.columns)


# =============================================================================
# 通道计算
# =============================================================================


def test_book_ticker_extra_channels_join_window_obs():
    svc = RLService()
    frame = _aggregate_book_ticker()
    window = 4
    env = svc.create_env(
        frame,
        obs_mode=OBS_MODE_OHLCV_WINDOW,
        obs_window=window,
        obs_extra_channels=["mid_price", "spread"],
    )
    obs = env.reset()
    channels = [*list(OBS_CHANNELS), "mid_price", "spread"]
    assert obs.shape == (window * len(channels),)

    # 最后一格是 bar0 的 spread，按训练窗统计量 z-score
    stats = env._stats
    assert [s["mean"] for s in stats[5:]] == pytest.approx(
        [frame["feature_mid_price"].mean(), frame["feature_spread"].mean()]
    )
    spread_z = (frame["feature_spread"].iloc[0] - stats[6]["mean"]) / stats[6]["std"]
    assert obs[-1] == pytest.approx(spread_z, rel=1e-5, abs=1e-6)


def test_book_depth_extra_channel_mid_price_only():
    svc = RLService()
    frame = _aggregate_book_depth()
    env = svc.create_env(frame, obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3, obs_extra_channels=["mid_price"])
    assert env.reset().shape == ((len(OBS_CHANNELS) + 1) * 3,)


def test_trades_aggregated_bars_use_base_channels_only():
    svc = RLService()
    frame = _aggregate_trades()
    env = svc.create_env(frame, obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3)
    assert env.reset().shape == (len(OBS_CHANNELS) * 3,)


# =============================================================================
# 缺列 / NaN 显式防御
# =============================================================================


def test_book_depth_missing_spread_is_rejected():
    svc = RLService()
    frame = _aggregate_book_depth()
    with pytest.raises(ValueError, match="feature_spread"):
        svc.create_env(frame, obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3, obs_extra_channels=["spread"])


def test_trades_frame_rejecting_mid_price():
    svc = RLService()
    frame = _aggregate_trades()
    with pytest.raises(ValueError, match="feature_mid_price"):
        svc.create_env(frame, obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3, obs_extra_channels=["mid_price"])


def test_unknown_extra_channel_rejected():
    svc = RLService()
    with pytest.raises(ValueError, match="未知 obs_extra_channels"):
        svc.create_env(
            _aggregate_trades(), obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3, obs_extra_channels=["depth_imbalance"]
        )


def test_nan_feature_column_rejected():
    svc = RLService()
    frame = _aggregate_book_ticker()
    frame.loc[3, "feature_spread"] = np.nan
    with pytest.raises(ValueError, match="非有限值"):
        svc.create_env(frame, obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3, obs_extra_channels=["spread"])


def test_constant_spread_maps_to_zero():
    svc = RLService()
    frame = _aggregate_book_ticker()
    frame["feature_spread"] = 0.1
    env = svc.create_env(frame, obs_mode=OBS_MODE_OHLCV_WINDOW, obs_window=3, obs_extra_channels=["spread"])
    obs = env.reset()
    assert np.isfinite(obs).all()
    assert np.allclose(obs[-1], 0.0)


# =============================================================================
# config / meta 契约
# =============================================================================


def test_config_extra_channels_require_window_mode():
    with pytest.raises(ValueError, match="只在 obs_mode=ohlcv_window"):
        RLTrainConfig(obs_extra_channels=["spread"])
    with pytest.raises(ValueError, match="未知 obs_extra_channels"):
        RLTrainConfig(obs_mode=OBS_MODE_OHLCV_WINDOW, obs_extra_channels=["depth_imbalance"])
    with pytest.raises(ValueError, match="重复"):
        RLTrainConfig(obs_mode=OBS_MODE_OHLCV_WINDOW, obs_extra_channels=["spread", "spread"])


def test_default_config_has_no_extra_channels_and_no_drift():
    config = RLTrainConfig()
    assert config.obs_extra_channels is None
    assert config.data_type == "kline"
    env = RLService().create_env(_aggregate_trades())
    assert not isinstance(env, ObsWindowEnv)
    assert obs_spec_from_meta({})["extra_channels"] == []


def test_obs_spec_from_meta_derives_extra_channels():
    stats = [{"mean": 0.0, "std": 1.0}] * (len(OBS_CHANNELS) + 2)
    meta = {
        "obs_mode": OBS_MODE_OHLCV_WINDOW,
        "obs_window": 8,
        "obs_features": [*list(OBS_CHANNELS), "mid_price", "spread"],
        "obs_stats": stats,
    }
    spec = obs_spec_from_meta(meta)
    assert spec["extra_channels"] == ["mid_price", "spread"]

    # 旧契约（只有基座通道）仍兼容
    old = {**meta, "obs_features": list(OBS_CHANNELS), "obs_stats": stats[: len(OBS_CHANNELS)]}
    assert obs_spec_from_meta(old)["extra_channels"] == []


def test_train_meta_records_extra_channels(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    frame = _aggregate_book_ticker()
    result = svc.train(
        RLTrainConfig(
            data=frame,
            total_timesteps=32,
            model_name="obs_extra",
            obs_mode=OBS_MODE_OHLCV_WINDOW,
            obs_window=6,
            obs_extra_channels=["mid_price", "spread"],
        )
    )
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["obs_features"] == [*list(OBS_CHANNELS), "mid_price", "spread"]
    assert len(meta["obs_stats"]) == len(meta["obs_features"])

    # 按 meta 重建：维度一致、可继续训练/回测
    spec = obs_spec_from_meta(meta)
    env = svc.create_env(
        frame,
        obs_mode=spec["mode"],
        obs_window=spec["window"],
        obs_stats=spec["stats"],
        obs_extra_channels=spec["extra_channels"],
    )
    assert env.reset().shape == (6 * len(meta["obs_features"]),)


def test_run_backtest_passes_extra_channels(monkeypatch, tmp_path):
    model_path = tmp_path / "extra_ppo.zip"
    model_path.write_bytes(b"fake")
    stats = [{"mean": 0.0, "std": 1.0}] * (len(OBS_CHANNELS) + 1)
    meta = {
        "obs_mode": OBS_MODE_OHLCV_WINDOW,
        "obs_window": 4,
        "obs_features": [*list(OBS_CHANNELS), "spread"],
        "obs_stats": stats,
    }
    Path(f"{model_path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")

    svc = RLService()
    captured: dict[str, object] = {}

    def _fake_create_env(data, *args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(svc, "create_env", _fake_create_env)
    monkeypatch.setattr(svc, "load_model", lambda path: object())
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines", lambda self, *a, **k: _aggregate_trades()
    )
    monkeypatch.setattr(
        "rl.evaluation.evaluate_model",
        lambda model, env, transaction_cost=None: type(
            "_M",
            (),
            dict.fromkeys(
                (
                    "total_pnl",
                    "total_return_pct",
                    "sharpe_ratio",
                    "max_drawdown_pct",
                    "win_rate",
                    "num_trades",
                    "profit_factor",
                    "turnover",
                ),
                0.0,
            ),
        )(),
    )

    svc.run_backtest(str(model_path), "BTCUSDT")
    assert captured["obs_extra_channels"] == ["spread"]


def test_math_isfinite_guard_on_stats_meta():
    """meta 统计量里的 NaN 必须显式拒绝（不静默用错误归一化）。"""
    stats = [{"mean": 0.0, "std": 1.0}] * len(OBS_CHANNELS)
    stats[2] = {"mean": math.nan, "std": 1.0}
    meta = {
        "obs_mode": OBS_MODE_OHLCV_WINDOW,
        "obs_window": 4,
        "obs_features": list(OBS_CHANNELS),
        "obs_stats": stats,
    }
    with pytest.raises(ValueError, match="数值非法"):
        obs_spec_from_meta(meta)


def test_features_mode_ignores_window_fields():
    assert RLTrainConfig(obs_mode=OBS_MODE_FEATURES).obs_window == 64


# =============================================================================
# _load_data 路由：kline → load_klines（不变），其余 data_type → data_adapters
# =============================================================================


def test_load_data_routes_non_kline_types_through_adapters(monkeypatch):
    from backtest.data_provider import BacktestDataProvider

    calls: dict[str, object] = {}

    def _fake_load_data(self, symbol, interval, data_type="kline", market="spot", start=None, end=None):
        calls.update(symbol=symbol, interval=interval, data_type=data_type, market=market)
        return type("_Result", (), {"data": _aggregate_trades()})()

    monkeypatch.setattr(BacktestDataProvider, "load_data", _fake_load_data)
    cfg = RLTrainConfig(symbol="BTCUSDT", interval="5m", candle_type="future", data_type="aggTrades")
    frame = RLService()._load_data(cfg)

    assert calls == {"symbol": "BTCUSDT", "interval": "5m", "data_type": "aggTrades", "market": "um"}
    assert {"Open", "High", "Low", "Close", "Volume"} <= set(frame.columns)


def test_load_data_keeps_kline_path(monkeypatch):
    from backtest.data_provider import BacktestDataProvider

    called: list[str] = []
    monkeypatch.setattr(
        BacktestDataProvider,
        "load_klines",
        lambda self, symbol, interval, candle_type="spot", start=None, end=None: (
            called.append(symbol) or _aggregate_trades()
        ),
    )
    monkeypatch.setattr(
        BacktestDataProvider,
        "load_data",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("kline 不应走 adapters")),
    )
    RLService()._load_data(RLTrainConfig(symbol="BTCUSDT", interval="1h"))
    assert called == ["BTCUSDT"]


# =============================================================================
# 回测取数口径：与训练同 data_type
# =============================================================================


def test_run_backtest_loads_same_data_type_as_training(monkeypatch, tmp_path):
    model_path = tmp_path / "book_ppo.zip"
    model_path.write_bytes(b"fake")
    meta = {
        "obs_mode": OBS_MODE_OHLCV_WINDOW,
        "obs_window": 3,
        "obs_features": [*list(OBS_CHANNELS), "mid_price", "spread"],
        "obs_stats": [{"mean": 0.0, "std": 1.0}] * (len(OBS_CHANNELS) + 2),
        "data_type": "bookTicker",
    }
    Path(f"{model_path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")

    from backtest.data_provider import BacktestDataProvider

    calls: dict[str, object] = {}

    def _fake_load_data(self, symbol, interval, data_type="kline", market="spot", start=None, end=None):
        calls.update(symbol=symbol, data_type=data_type, market=market)
        return type("_Result", (), {"data": _aggregate_book_ticker()})()

    monkeypatch.setattr(BacktestDataProvider, "load_data", _fake_load_data)
    monkeypatch.setattr(
        BacktestDataProvider,
        "load_klines",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("bookTicker 模型不应回落到 kline")),
    )

    svc = RLService()
    monkeypatch.setattr(svc, "create_env", lambda *a, **k: object())
    monkeypatch.setattr(svc, "load_model", lambda path: object())
    monkeypatch.setattr(
        "rl.evaluation.evaluate_model",
        lambda model, env, transaction_cost=None: type(
            "_M",
            (),
            dict.fromkeys(
                (
                    "total_pnl",
                    "total_return_pct",
                    "sharpe_ratio",
                    "max_drawdown_pct",
                    "win_rate",
                    "num_trades",
                    "profit_factor",
                    "turnover",
                ),
                0.0,
            ),
        )(),
    )

    svc.run_backtest(str(model_path), "BTCUSDT", interval="5m", candle_type="future")
    assert calls == {"symbol": "BTCUSDT", "data_type": "bookTicker", "market": "um"}


def test_train_meta_records_data_type(monkeypatch, tmp_path):
    import services.rl_service as rl_service_mod

    monkeypatch.setattr(rl_service_mod, "MODELS_DIR", tmp_path)
    svc = rl_service_mod.RLService()
    result = svc.train(RLTrainConfig(data=_aggregate_trades(), total_timesteps=32, model_name="obs_dtype"))
    meta = json.loads((tmp_path / (result.model_path.split("/")[-1] + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["data_type"] == "kline"  # 显式 data= 时不涉及取数，仍记默认口径
