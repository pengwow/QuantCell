"""capital_mode 参数与共享资金池聚合口径的单测。"""

import pytest
from pydantic import ValidationError

from backtest.schemas import BacktestConfig


def _base_payload(**overrides):
    payload = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "start_time": "2025-01-01 00:00:00",
        "end_time": "2025-01-31 23:59:59",
        "initial_cash": 10000.0,
    }
    payload.update(overrides)
    return payload


def test_capital_mode_defaults_to_per_symbol():
    cfg = BacktestConfig(**_base_payload())
    assert cfg.capital_mode == "per_symbol"


def test_capital_mode_accepts_shared():
    cfg = BacktestConfig(**_base_payload(capital_mode="shared"))
    assert cfg.capital_mode == "shared"


def test_capital_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        BacktestConfig(**_base_payload(capital_mode="split"))


def test_shared_mode_portfolio_replay_uses_single_curve():
    """共享模式下组合初始权益 = 一笔 init_cash，不是各品种曲线首点求和。"""
    from backtest.service import BacktestService

    shared_curve = [
        {"timestamp": 1000, "equity": 10000.0, "balance": 0.0, "margin": 0.0},
        {"timestamp": 2000, "equity": 10500.0, "balance": 0.0, "margin": 0.0},
    ]
    # 真实结果的每个品种条目都带 klines（回放网格范围依赖它）；此处给出最小可跑数据
    klines = [
        {"timestamp": 1000, "close": 100.0},
        {"timestamp": 2000, "close": 101.0},
    ]
    results = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "timeframe": "15m",
        "capital_mode": "shared",
        "results_by_symbol": {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "klines": list(klines),
                "trades": [],
                "equity_curve": list(shared_curve),
            },
            "ETHUSDT": {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "klines": list(klines),
                "trades": [],
                "equity_curve": list(shared_curve),
            },
        },
        "portfolio": {"metrics": [], "equity_curve": list(shared_curve)},
    }
    config = {"interval": "15m", "initial_cash": 10000.0, "capital_mode": "shared"}

    svc = BacktestService.__new__(BacktestService)  # 不触发 __init__ 的 IO
    data = svc.build_portfolio_replay(results, config)

    assert data["init_cash"] == 10000.0, "共享模式初始权益应为一笔 init_cash，而非 N×"


def test_shared_mode_portfolio_replay_tolerates_engine_curve_without_balance():
    """共享模式的 merged 曲线直接取自引擎 bar_nav_curve（只有 equity/timestamp），
    没有 balance/margin 键；账户序列构建必须容错，否则 /replay/portfolio 报
    KeyError('balance') 直接 500。

    回归背景：上一个用例的 fixture 给共享曲线补了 balance/margin，恰好把该
    KeyError 掩盖了（实测 HTTP 接口才暴露）。
    """
    from backtest.service import BacktestService

    # 与 _map_rust_result 产出的真实形状一致：无 balance / margin
    engine_curve = [
        {
            "datetime": "2025-01-01T00:00:00.000Z",
            "equity": 10000.0,
            "formatted_time": "2025-01-01T00:00:00.000Z",
            "timestamp": 1000,
        },
        {
            "datetime": "2025-01-01T00:15:00.000Z",
            "equity": 10050.0,
            "formatted_time": "2025-01-01T00:15:00.000Z",
            "timestamp": 2000,
        },
    ]
    klines = [
        {"timestamp": 1000, "close": 100.0},
        {"timestamp": 2000, "close": 101.0},
    ]
    results = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "timeframe": "15m",
        "capital_mode": "shared",
        "results_by_symbol": {
            sym: {
                "symbol": sym,
                "timeframe": "15m",
                "klines": list(klines),
                "trades": [],
                "equity_curve": list(engine_curve),
            }
            for sym in ("BTCUSDT", "ETHUSDT")
        },
        "portfolio": {"metrics": [], "equity_curve": list(engine_curve)},
    }
    config = {"interval": "15m", "initial_cash": 10000.0, "capital_mode": "shared"}

    svc = BacktestService.__new__(BacktestService)
    data = svc.build_portfolio_replay(results, config)

    assert data["init_cash"] == 10000.0
    assert len(data["account"]) == 2
    # account 元组 = [t, equity, balance, margin, cum_pnl, drawdown, day_pnl]
    # balance/margin 缺失 → 兜底 0（与非共享模式下 _merge_equity_curves 补的 0 一致）
    assert data["account"][0][2] == 0.0
    assert data["account"][0][3] == 0.0
