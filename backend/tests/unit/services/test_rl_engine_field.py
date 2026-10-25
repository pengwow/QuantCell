"""RL 回测入口的 `engine` 字段（trading_env / kernel 两条口径）。

覆盖：
1. 默认走 `TradingEnv` 评估时响应带 `engine="trading_env"`；
2. 显式 `engine="kernel"` 时走 `worker.Kernel` + RL host，响应带 `engine="kernel"`；
3. 未知 engine 明确报错，不静默回退。

不训练真模型：SB3 模型、数据源、内核全部用假对象替换。
"""

import asyncio
import json
import threading
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
        lambda model, env, transaction_cost=None: SimpleNamespace(
            total_pnl=12.0,
            total_return_pct=0.12,
            sharpe_ratio=0.8,
            max_drawdown_pct=3.0,
            win_rate=0.5,
            num_trades=2,
            profit_factor=1.5,
            turnover=12_000.0,
        ),
    )

    result = svc.run_backtest("fake.zip", "BTCUSDT")

    assert result["engine"] == "trading_env"
    assert result["total_pnl"] == 12.0
    # 成交名义总额透传到响应，供 `attribute_engine_diff` 折算费率
    assert result["turnover"] == 12_000.0


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
                total_fees=0.6,
                total_funding_pnl=0.0,
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


def _write_model_with_meta(
    tmp_path: Path,
    spec_version: str = "v1",
    observation_stats: list[dict] | None = None,
) -> Path:
    """伪造 SB3 产物：模型文件 + 观测规格元数据旁车。"""
    model_path = tmp_path / "demo_ppo.zip"
    model_path.write_bytes(b"fake-sb3-model")
    meta = {"model_id": "demo_ppo", "spec_version": spec_version, "window_size": 1}
    if observation_stats is not None:
        meta["observation_stats"] = observation_stats
    Path(f"{model_path}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
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

        def add_rl_strategy(self, *args, **kwargs):
            registered["register"] = args
            registered["stats"] = kwargs.get("stats")

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())

    mgr = StrategyManager(max_workers=1)
    try:
        mgr.build_rl_kernel(1, {"model_path": str(model_path)}, "1h", ["BTCUSDT"])
    finally:
        mgr.shutdown()

    assert registered["init"]["interval"] == "1h"
    # 费率必须与 RL 训练环境同源，而不是吃内核默认 0.001
    from services.rl_service import RL_TRANSACTION_COST

    assert registered["init"]["fee_rate"] == RL_TRANSACTION_COST
    args = registered["register"]
    assert args[1] == "demo_ppo"
    assert args[2] == "v1", "spec_version 取自元数据校验结果"
    assert args[6] == "BTC/USDT"
    # 伪造的 meta 没有 observation_stats → 传 None，不伪造空统计量
    assert registered["stats"] is None


# =============================================================================
# 观测归一化统计量的落盘 / 灌回
# =============================================================================

DEMO_STATS = [
    {"mean": 100.0, "m2": 50.0, "min": 90.0, "max": 110.0, "count": 20, "median_buffer": []},
    {"mean": 10.0, "m2": 0.0, "min": 10.0, "max": 10.0, "count": 20, "median_buffer": []},
]


def test_export_observation_stats_parses_json_string():
    """训练环境返回 JSON 字符串 → 落盘前解析成 list，`"null"` 归一成 None。"""
    from services.rl_service import export_observation_stats

    class StringEnv:
        def observation_stats(self):
            return json.dumps(DEMO_STATS)

    class NullEnv:
        def observation_stats(self):
            return "null"

    class ColdEnv:
        """统计条目存在但 count 全 0：训练期从未预热，等价于没有统计量。"""

        def observation_stats(self):
            return json.dumps(
                [
                    {"mean": 0.0, "m2": 0.0, "min": 0.0, "max": 0.0, "count": 0, "median_buffer": []},
                    {"mean": 0.0, "m2": 0.0, "min": 0.0, "max": 0.0, "count": 0, "median_buffer": []},
                ]
            )

    assert export_observation_stats(StringEnv()) == DEMO_STATS
    assert export_observation_stats(NullEnv()) is None
    assert export_observation_stats(ColdEnv()) is None
    assert export_observation_stats(object()) is None, "环境没有该方法时不能崩"


def test_kernel_backtest_passes_observation_stats(monkeypatch, tmp_path, ohlcv_df):
    """meta 里有 observation_stats 时必须通过 `stats=` 灌回内核。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    model_path = _write_model_with_meta(tmp_path, observation_stats=DEMO_STATS)
    svc = RLService()
    monkeypatch.setattr(
        "backtest.data_provider.BacktestDataProvider.load_klines",
        lambda self, *args, **kwargs: ohlcv_df.copy(),
    )
    monkeypatch.setattr(svc, "load_model", lambda path: object())

    calls: dict[str, object] = {}

    class FakeKernel:
        def __init__(self, **kwargs):
            pass

        def add_rl_strategy(self, *args, **kwargs):
            calls["stats"] = kwargs.get("stats")

        def run(self, bars_by_symbol, **kwargs):
            return SimpleNamespace(
                total_pnl=0.0,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                win_rate=0.0,
                fills=0,
                final_nav=100_000.0,
                total_fees=0.0,
                total_funding_pnl=0.0,
            )

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)

    svc.run_backtest(str(model_path), "BTCUSDT", engine="kernel")

    assert calls["stats"] == DEMO_STATS


def test_build_rl_kernel_passes_observation_stats(monkeypatch, tmp_path):
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path, observation_stats=DEMO_STATS)
    registered: dict[str, object] = {}

    class FakeKernel:
        def __init__(self, **kwargs):
            pass

        def add_rl_strategy(self, *args, **kwargs):
            registered["stats"] = kwargs.get("stats")

    monkeypatch.setattr(axon_quant.worker, "Kernel", FakeKernel)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())

    mgr = StrategyManager(max_workers=1)
    try:
        mgr.build_rl_kernel(1, {"model_path": str(model_path)}, "1h", ["BTCUSDT"])
    finally:
        mgr.shutdown()

    assert registered["stats"] == DEMO_STATS


# =============================================================================
# StrategyManager: RL 实盘 LiveDriver 接线（testnet）
# =============================================================================


def test_start_rl_live_assembles_driver_and_stop_shutdowns(monkeypatch, tmp_path):
    """RL live 接线全链路自检：配置边界拒绝 → 装配 → 线程 connect/start/tick → stop 停机。

    LiveDriver / 凭证 / DB 全部替换为进程内假实现，不联网、不落真库；
    journal 通过 QUANTCELL_DATA_DIR 重定向到 tmp_path。
    """
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.state import StrategyRuntime, strategy_registry
    from worker.strategy_manager import StrategyManager

    model_path = _write_model_with_meta(tmp_path)

    calls: dict[str, object] = {}
    first_tick_done = threading.Event()

    class FakeLiveDriver:
        def __init__(self, config, symbols, **kwargs):
            calls["config"] = config
            calls["symbols"] = symbols
            calls["init"] = kwargs

        def add_rl_strategy(self, *args, **kwargs):
            calls["register"] = args
            calls["register_stats"] = kwargs.get("stats")

        def connect(self):
            calls["connect"] = True

        def start(self, journal):
            calls["start"] = journal

        def tick(self):
            calls["ticks"] = int(calls.get("ticks", 0)) + 1
            first_tick_done.set()

        def shutdown(self):
            calls["shutdown"] = True

    class FakeCredentials:
        def get_credential(self, name):
            calls["credential"] = name
            return "key-1", "secret-1"

    monkeypatch.setattr(axon_quant.worker, "LiveDriver", FakeLiveDriver)
    monkeypatch.setattr("credentials.service.CredentialsService", FakeCredentials)
    monkeypatch.setattr("services.rl_service.RLService.load_model", lambda self, path: object())
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def commit(self):
            pass

    monkeypatch.setattr("worker.strategy_manager.get_db_session", lambda: _FakeSession())
    monkeypatch.setattr("worker.crud.update_worker_status", lambda *args, **kwargs: None)

    # 配置边界：market_type / 交易所 / 凭证缺省必须入口即拒，不静默装配
    mgr = StrategyManager(max_workers=1)
    good = {"model_path": str(model_path), "credentials_account": "acct-1"}
    with pytest.raises(ValueError, match="仅支持永续合约"):
        mgr.start_rl_live(7, dict(good), "1h", ["BTCUSDT"], "binance", "spot")
    with pytest.raises(ValueError, match="暂只支持 binance"):
        mgr.start_rl_live(7, dict(good), "1h", ["BTCUSDT"], "okx", "swap")
    with pytest.raises(ValueError, match="credentials_account"):
        mgr.start_rl_live(7, {"model_path": str(model_path)}, "1h", ["BTCUSDT"], "binance", "swap")

    runtime = StrategyRuntime(worker_id=7, strategy_id=0, name="rl-live-test", status="starting")
    strategy_registry.register(runtime)
    try:
        journal = mgr._rl_live_journal_path(7)
        assert journal.startswith(str(tmp_path)), "journal 必须落在重定向的数据目录里"

        mgr.start_rl_live(7, dict(good), "1h", ["BTCUSDT"], "binance", "swap")

        assert first_tick_done.wait(timeout=10), "驱动线程应在超时前完成首次 tick"
        cfg = calls["config"]
        # 合约 testnet URL（binance_testnet_config 是现货 URL，不能用）
        assert "testnet.binancefuture.com" in cfg.rest_base_url
        assert "binancefuture" in cfg.ws_url
        assert cfg.api_key == "key-1"
        assert calls["credential"] == "acct-1"
        assert calls["symbols"] == ["BTC/USDT"]
        assert calls["start"] == journal, "journal 不存在时走全新 start"
        from services.rl_service import RL_TRANSACTION_COST

        assert calls["init"]["fee_rate"] == RL_TRANSACTION_COST
        assert calls["register"][6] == "BTC/USDT"

        # 停机：事件唤醒 tick 循环 → join → driver.shutdown → 运行态清理
        asyncio.run(mgr.stop_strategy(7))
        assert calls["shutdown"] is True
        assert 7 not in mgr._rl_live
    finally:
        # stop 没跑到也要兜底收线，避免测试进程悬挂驱动线程
        live = mgr._rl_live.pop(7, None)
        if live is not None:
            live["stop_event"].set()
            live["thread"].join(timeout=5)
            driver = live["driver"]
            driver.shutdown = lambda: None
            driver.shutdown()
        strategy_registry.unregister(7)
