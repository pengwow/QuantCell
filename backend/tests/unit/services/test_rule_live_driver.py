"""规则/LLM 策略实盘（testnet）接线：start_crypto_live + _do_start_strategy 路由。

覆盖：
1. start_crypto_live 装配参数：binance 永续 testnet 闸门、credentials_account 凭证、
   journal 落 data/live/、策略经 RustStrategyAdapter 包装挂载；
2. connect 失败线程内降级 worker error（与 RL live 同语义）；
3. _do_start_strategy 按 trading_mode 路由规则/LLM worker：
   testnet → LiveDriver、paper → PaperDriver、live → 主网闸门拒绝。

LiveDriver / PaperDriver / 凭证 / DB 全部替换为进程内假实现，不联网、不落真库。
"""

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest


def _fake_strategy() -> SimpleNamespace:
    """最小 BaseStrategy 替身：RustStrategyAdapter 构造期需要 config 与 on_start。"""
    return SimpleNamespace(
        config=SimpleNamespace(name="dual_ma", symbol="BTCUSDT"),
        on_start=lambda ctx: None,
        on_bar=lambda bar, ctx: None,
    )


def _patch_db(monkeypatch) -> None:
    """_mark_rl_live_error / _finalize_start / stop_strategy 的 DB 落库替换为 no-op。"""

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def commit(self):
            pass

    monkeypatch.setattr("worker.strategy_manager.get_db_session", lambda: _FakeSession())
    monkeypatch.setattr("worker.crud.update_worker_status", lambda *args, **kwargs: None)


def test_start_crypto_live_assembles_driver_and_stop_shutdowns(monkeypatch, tmp_path):
    """start_crypto_live 接线全链路自检：配置边界拒绝 → 装配 → connect/start/tick → stop 停机。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.state import StrategyRuntime, strategy_registry
    from worker.strategy_manager import StrategyManager

    calls: dict[str, object] = {}
    first_tick_done = threading.Event()

    class FakeLiveDriver:
        def __init__(self, config, symbols, **kwargs):
            calls["config"] = config
            calls["symbols"] = symbols
            calls["init"] = kwargs

        def add_strategy(self, adapter, **kwargs):
            calls["adapter"] = adapter
            calls["register_symbol"] = kwargs.get("symbol")

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
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    _patch_db(monkeypatch)

    # 配置边界：market_type / 交易所 / 凭证缺省必须入口即拒，不静默装配。
    # 凭证解析支持「credentials_account 缺省 → 回退系统配置测试网 Key」，
    # 这里清空系统配置，让「两处都没配」的报错边界不依赖开发库里的真实配置
    monkeypatch.setattr("settings.models.SystemConfigBusiness.get_all", staticmethod(lambda: {}))
    mgr = StrategyManager(max_workers=1)
    good = {"credentials_account": "acct-1"}
    with pytest.raises(ValueError, match="仅支持永续合约"):
        mgr.start_crypto_live(7, dict(good), _fake_strategy(), "1h", ["BTCUSDT"], "binance", "spot")
    with pytest.raises(ValueError, match="暂只支持 binance"):
        mgr.start_crypto_live(7, dict(good), _fake_strategy(), "1h", ["BTCUSDT"], "okx", "swap")
    with pytest.raises(ValueError, match="credentials_account"):
        mgr.start_crypto_live(7, {}, _fake_strategy(), "1h", ["BTCUSDT"], "binance", "swap")

    runtime = StrategyRuntime(worker_id=7, strategy_id=0, name="live-test", status="starting")
    strategy_registry.register(runtime)
    try:
        journal = mgr._live_journal_path(7)
        assert journal.startswith(str(tmp_path)) and "/live/" in journal.replace("\\", "/"), (
            "规则/LLM journal 必须落在 data/live/ 并随 QUANTCELL_DATA_DIR 重定向"
        )

        strategy_instance = _fake_strategy()
        mgr.start_crypto_live(7, dict(good), strategy_instance, "1h", ["BTCUSDT"], "binance", "swap")

        assert first_tick_done.wait(timeout=10), "驱动线程应在超时前完成首次 tick"
        cfg = calls["config"]
        # 合约 testnet URL（binance_testnet_config 是现货 URL，不能用）
        assert "testnet.binancefuture.com" in cfg.rest_base_url
        assert "binancefuture" in cfg.ws_url
        assert cfg.api_key == "key-1"
        assert calls["credential"] == "acct-1"
        assert calls["symbols"] == ["BTC/USDT"]
        assert calls["start"] == journal, "journal 不存在时走全新 start"
        # 费率走引擎默认（与 paper/回测同口径），不传训练环境费率
        assert "fee_rate" not in calls["init"]
        adapter = calls["adapter"]
        assert adapter.symbol == "BTC/USDT", "适配器按 BASE/QUOTE 归一化品种"
        assert calls["register_symbol"] == "BTC/USDT"

        # 停机：事件唤醒 tick 循环 → join → driver.shutdown → 运行态清理
        asyncio.run(mgr.stop_strategy(7))
        assert calls["shutdown"] is True
        assert 7 not in mgr._kernel_runs
    finally:
        # stop 没跑到也要兜底收线，避免测试进程悬挂驱动线程
        live = mgr._kernel_runs.pop(7, None)
        if live is not None:
            live["stop_event"].set()
            live["thread"].join(timeout=5)
            driver = live["driver"]
            driver.shutdown = lambda: None
            driver.shutdown()
        strategy_registry.unregister(7)


def test_start_crypto_live_connect_failure_degrades_to_error(monkeypatch, tmp_path):
    """connect 抛异常时线程内降级为 worker error 状态（registry），不向外抛。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.state import StrategyRuntime, strategy_registry
    from worker.strategy_manager import StrategyManager

    class FakeLiveDriver:
        def __init__(self, *args, **kwargs):
            pass

        def add_strategy(self, *args, **kwargs):
            pass

        def connect(self):
            raise RuntimeError("network down")

        def shutdown(self):
            pass

    class FakeCredentials:
        def get_credential(self, name):
            return "k", "s"

    monkeypatch.setattr(axon_quant.worker, "LiveDriver", FakeLiveDriver)
    monkeypatch.setattr("credentials.service.CredentialsService", FakeCredentials)
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    _patch_db(monkeypatch)

    mgr = StrategyManager(max_workers=1)
    runtime = StrategyRuntime(worker_id=8, strategy_id=0, name="live-err-test", status="starting")
    strategy_registry.register(runtime)
    try:
        mgr.start_crypto_live(
            8, {"credentials_account": "acct-1"}, _fake_strategy(), "1h", ["BTCUSDT"], "binance", "swap"
        )
        deadline = time.time() + 10
        while time.time() < deadline and runtime.status != "error":
            time.sleep(0.05)
        assert runtime.status == "error", "connect 失败必须降级为 error 状态"
        assert "network down" in (runtime.error_message or "")
        assert 8 not in mgr._kernel_runs, "驱动线程失败退出后不应残留运行态"
    finally:
        live = mgr._kernel_runs.pop(8, None)
        if live is not None:
            live["stop_event"].set()
            live["thread"].join(timeout=5)
        strategy_registry.unregister(8)


def test_do_start_strategy_routes_rule_modes(monkeypatch, tmp_path):
    """规则/LLM worker 按 trading_mode 路由：testnet → LiveDriver、paper → PaperDriver、live → 拒绝。"""
    axon_quant = pytest.importorskip("axon_quant")
    if not hasattr(axon_quant, "worker"):
        pytest.skip("axon_quant.worker 不可用")

    from worker.state import StrategyRuntime, strategy_registry
    from worker.strategy_manager import StrategyManager

    calls: dict[str, object] = {}
    first_tick_done = threading.Event()

    class FakeLiveDriver:
        def __init__(self, *args, **kwargs):
            pass

        def add_strategy(self, *args, **kwargs):
            pass

        def connect(self):
            pass

        def start(self, journal):
            calls["live_start"] = journal

        def tick(self):
            first_tick_done.set()

        def shutdown(self):
            calls["live_shutdown"] = True

    class FakePaperDriver:
        def __init__(self, symbols, **kwargs):
            calls["paper_symbols"] = symbols

        def add_strategy(self, *args, **kwargs):
            pass

        def start(self):
            calls["paper_start"] = True

        def tick(self):
            first_tick_done.set()

        def shutdown(self):
            calls["paper_shutdown"] = True

    class FakeCredentials:
        def get_credential(self, name):
            return "k", "s"

    monkeypatch.setattr(axon_quant.worker, "LiveDriver", FakeLiveDriver)
    monkeypatch.setattr(axon_quant.worker, "PaperDriver", FakePaperDriver)
    monkeypatch.setattr("credentials.service.CredentialsService", FakeCredentials)
    monkeypatch.setenv("QUANTCELL_DATA_DIR", str(tmp_path))
    _patch_db(monkeypatch)
    # paper 泵行情假拉取：返回空列表，线程空转不喂 bar
    monkeypatch.setattr(StrategyManager, "_paper_fetch_klines", lambda self, *args, **kwargs: [])

    captured: dict[str, object] = {}

    def fake_load_strategy(**kwargs):
        captured.update(kwargs)
        return _fake_strategy()

    monkeypatch.setattr(
        "backtest.strategy_loader_service.StrategyLoaderService.load_strategy",
        staticmethod(fake_load_strategy),
    )

    def _worker(mode: str) -> SimpleNamespace:
        """worker ORM 替身：_do_start_strategy 只触这批属性。"""
        return SimpleNamespace(
            id=9,
            name="w9",
            exchange="binance",
            trading_mode=mode,
            strategy_id=1,
            get_trading_config_dict=lambda: {"trading_mode": mode, "timeframe": "1h", "market_type": "swap"},
            get_symbols=lambda: ["BTCUSDT"],
            strategy=SimpleNamespace(
                strategy_type="rule",
                strategy_name="dual_ma",
                name="dual_ma",
                parameters={"credentials_account": "acct-1"},
            ),
        )

    mgr = StrategyManager(max_workers=1)

    # live → 主网闸门拒绝（与 RL 分支同语义）
    strategy_registry.register(StrategyRuntime(worker_id=10, strategy_id=1, name="w10", status="starting"))
    try:
        with pytest.raises(ValueError, match="主网闸门"):
            asyncio.run(mgr._do_start_strategy(10, _worker("live"), None))
    finally:
        strategy_registry.unregister(10)

    # testnet → start_crypto_live（LiveDriver），run_mode 标 live
    strategy_registry.register(StrategyRuntime(worker_id=9, strategy_id=1, name="w9", status="starting"))
    try:
        first_tick_done.clear()
        assert asyncio.run(mgr._do_start_strategy(9, _worker("testnet"), None)) is True
        assert first_tick_done.wait(timeout=10), "testnet 路由应启动 LiveDriver tick 循环"
        assert "live_start" in calls
        assert captured["run_mode"] == "live"
        run = mgr._kernel_runs[9]
        assert run["journal_path"].replace("\\", "/").endswith("/live/worker_9.jsonl")
        asyncio.run(mgr.stop_strategy(9))
        assert calls.get("live_shutdown") is True
    finally:
        run = mgr._kernel_runs.pop(9, None)
        if run is not None:
            run["stop_event"].set()
            run["thread"].join(timeout=5)
        strategy_registry.unregister(9)

    # paper → PaperDriver 演练，run_mode 标 paper
    strategy_registry.register(StrategyRuntime(worker_id=11, strategy_id=1, name="w11", status="starting"))
    try:
        first_tick_done.clear()
        assert asyncio.run(mgr._do_start_strategy(11, _worker("paper"), None)) is True
        assert first_tick_done.wait(timeout=10), "paper 路由应启动行情泵并完成首轮"
        assert calls.get("paper_start") is True
        assert captured["run_mode"] == "paper"
        asyncio.run(mgr.stop_strategy(11))
        assert calls.get("paper_shutdown") is True
    finally:
        run = mgr._kernel_runs.pop(11, None)
        if run is not None:
            run["stop_event"].set()
            run["thread"].join(timeout=5)
        strategy_registry.unregister(11)


def test_resolve_live_credentials_falls_back_to_system_config(monkeypatch):
    """credentials_account 缺省时回退系统配置的测试网 Key（GUI 用户免 CLI 配凭证）。

    口径与 market_data_factory 一致：按 exchange.{id}. 前缀过滤，
    只取 testnet_api_key / testnet_api_secret 两个字段。
    """
    from worker.strategy_manager import _resolve_live_credentials

    monkeypatch.setattr(
        "settings.models.SystemConfigBusiness.get_all",
        staticmethod(
            lambda: {
                "exchange.binance.testnet_api_key": "cfg-key",
                "exchange.binance.testnet_api_secret": "cfg-secret",
                "exchange.binance.paper_initial_balance": "10000",
                "exchange.okx.testnet_api_key": "not-binance",
            }
        ),
    )
    # 前缀过滤只认 binance 的 testnet key/secret，其余配置项被忽略
    assert _resolve_live_credentials(1, "binance", {}) == ("cfg-key", "cfg-secret")
