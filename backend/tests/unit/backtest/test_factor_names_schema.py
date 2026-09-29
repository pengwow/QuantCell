"""BacktestConfig.factor_names 可选字段的默认值与透传。"""

from backtest.schemas import BacktestConfig


def _config(**overrides):
    base = {
        "symbols": ["BTCUSDT"],
        "start_time": "2024-01-01 00:00:00",
        "end_time": "2024-02-01 00:00:00",
    }
    base.update(overrides)
    return BacktestConfig(**base)


def test_factor_names_default_none():
    assert _config().factor_names is None


def test_factor_names_accepted():
    assert _config(factor_names=["momentum_5d", "rsi_14d"]).factor_names == ["momentum_5d", "rsi_14d"]
