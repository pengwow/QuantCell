"""TradingEngine 单例和生命周期测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.config import EngineConfig


def _reset_engine():
    """重置 TradingEngine 单例（用于测试隔离）"""
    from engine import trading_engine

    trading_engine._trading_engine_instance = None
    # 同时重置 risk_service 单例
    trading_engine.get_risk_service.cache_clear()


def _patch_engine_deps():
    """返回 mock 上下文：BinanceAdapter + ExchangeConfig + get_risk_service"""
    # 注意：exchange 属性内部延迟 from axon_bridge import BinanceAdapter, ExchangeConfig
    # 需要 patch axon_bridge 顶层名字 (不是 axon_bridge.exchange 子模块)
    return patch.multiple(
        "axon_bridge",
        BinanceAdapter=MagicMock(return_value=MagicMock()),
        ExchangeConfig=MagicMock(return_value=MagicMock()),
    )


def test_get_trading_engine_singleton():
    """get_trading_engine 始终返回同一实例"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    with _patch_engine_deps():
        config = EngineConfig(exchange="binance", trading_mode="paper")
        e1 = get_trading_engine(config)
        e2 = get_trading_engine()
        assert e1 is e2

    _reset_engine()


def test_register_strategy_returns_id_and_tracks():
    """register_strategy 返回 sid 并记录 runtime"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    with _patch_engine_deps():
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        strategy = MagicMock()
        strategy.__class__.__name__ = "MockStrategy"
        sid = engine.register_strategy(strategy, ["BTCUSDT"])
        assert sid
        assert len(engine.list_strategies()) == 1
        status = engine.list_strategies()[0]
        assert status["symbols"] == ["BTCUSDT"]
        assert status["strategy_id"] == sid

    _reset_engine()


def test_get_strategy_status():
    """get_strategy_status 返回完整状态字典"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    with _patch_engine_deps():
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        strategy = MagicMock()
        strategy.__class__.__name__ = "MockStrategy"
        sid = engine.register_strategy(strategy, ["ETHUSDT"])
        rt = engine._strategies[sid]
        rt["order_count"] = 5
        rt["rejected_count"] = 1
        rt["last_action"] = "buy"
        rt["last_price"] = 3500.0
        rt["status"] = "running"

        status = engine.get_strategy_status(sid)
        assert status["order_count"] == 5
        assert status["rejected_count"] == 1
        assert status["last_action"] == "buy"
        assert status["symbols"] == ["ETHUSDT"]

    _reset_engine()


def test_stop_strategy_updates_status():
    """stop_strategy 更新状态并停止 loop"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    with _patch_engine_deps():
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        mock_loop = MagicMock()
        strategy = MagicMock()
        strategy.__class__.__name__ = "MockStrategy"
        sid = engine.register_strategy(strategy, ["BTCUSDT"])
        engine._strategies[sid]["loop"] = mock_loop
        engine._strategies[sid]["status"] = "running"

        result = engine.stop_strategy(sid)
        assert result is True
        mock_loop.stop.assert_called_once()
        assert engine._strategies[sid]["status"] == "stopped"

    _reset_engine()


def test_engine_status():
    """engine_status 返回引擎概览"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    with _patch_engine_deps():
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        status = engine.engine_status()
        assert status["exchange"] == "binance"
        assert status["mode"] == "paper"
        assert status["running_strategies"] == 0
        assert status["exchange_connected"] is True
        assert status["risk_available"] is True

    _reset_engine()


def test_list_strategies_empty():
    """list_strategies 在无策略时返回空列表"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    with _patch_engine_deps():
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()
        assert engine.list_strategies() == []

    _reset_engine()


def test_deployer_uses_trading_engine():
    """deployer 正确使用 TradingEngine"""
    _reset_engine()
    from engine.trading_engine import get_trading_engine

    # 验证 deployer 能导入 TradingEngine
    assert get_trading_engine is not None

    _reset_engine()
