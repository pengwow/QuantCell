"""P1-01 停机链路超时统一：派生预算与开关测试

链式余量不变式：lifespan 停机总预算(total) < uvicorn 优雅窗口(+5s) < 看门狗(+10s)，
保证 uvicorn / 看门狗不会早于 lifespan 侧 worker 停机流程完成就强杀。
"""

from worker.graceful_shutdown import (
    ShutdownConfig,
    shutdown_watchdog_timeout,
    uvicorn_graceful_timeout,
    worker_stop_budget,
)


def test_worker_stop_budget_default():
    """默认配置(total=30)下单 worker 停机预算 = max(5, 30/6) = 5.0s"""
    assert worker_stop_budget() == 5.0


def test_worker_stop_budget_scales_with_config():
    """total=90 → 预算等比例放大为 15s；total=12 → 命中下限 5s"""
    big = ShutdownConfig(total_timeout=90.0)
    assert worker_stop_budget(big) == 15.0
    tiny = ShutdownConfig(total_timeout=12.0)
    assert worker_stop_budget(tiny) == 5.0


def test_uvicorn_graceful_timeout():
    """uvicorn 优雅窗口 = total + 5：默认 35；total=90 → 95"""
    assert uvicorn_graceful_timeout() == 35
    assert uvicorn_graceful_timeout(ShutdownConfig(total_timeout=90.0)) == 95


def test_shutdown_watchdog_timeout():
    """看门狗 = total + 10：最后兜底，永远晚于 uvicorn 强杀"""
    assert shutdown_watchdog_timeout() == 40
    assert shutdown_watchdog_timeout(ShutdownConfig(total_timeout=90.0)) == 100


def test_budget_chain_invariant():
    """链式余量不变式 total < uvicorn < watchdog 对任意配置成立"""
    for total in (0.0, 5.0, 30.0, 90.0):
        cfg = ShutdownConfig(total_timeout=total)
        chain = (cfg.total_timeout, uvicorn_graceful_timeout(cfg), shutdown_watchdog_timeout(cfg))
        assert chain[0] < chain[1] < chain[2]


def test_stop_timeout_switch(monkeypatch):
    """lifespan 开关语义：use_config_timeouts 开启用派生预算，关闭回旧硬编码值"""
    # core/__init__ 将 lifespan 函数绑定到了包同名属性（import ... as 会被遮蔽），
    # 用 importlib 直接取子模块对象
    from importlib import import_module

    lifespan_module = import_module("core.lifespan")

    monkeypatch.setattr(lifespan_module, "get_flag", lambda key, default=True: False)
    assert lifespan_module._stop_timeout(1.0, 99.0) == 1.0

    monkeypatch.setattr(lifespan_module, "get_flag", lambda key, default=True: True)
    assert lifespan_module._stop_timeout(1.0, 99.0) == 99.0
