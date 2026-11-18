"""BacktestConfig.margin_specs 校验单测。

覆盖信任边界：只有永续模式能带保证金配置、品种必须在本轮回测列表内、
同品种不得重复、杠杆范围 1~125（全局 legacy leverage 也不允许 0）。
"""

import pytest
from pydantic import ValidationError

from backtest.schemas import BacktestConfig, SymbolMarginSpec


def _config(**overrides):
    base = {
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "start_time": "2024-01-01 00:00:00",
        "end_time": "2024-02-01 00:00:00",
    }
    base.update(overrides)
    return BacktestConfig(**base)


def test_spot_rejects_margin_specs():
    with pytest.raises(ValidationError):
        _config(trading_mode="spot", margin_specs=[{"symbol": "BTCUSDT", "leverage": 10}])


def test_futures_accepts_margin_specs():
    cfg = _config(trading_mode="futures", margin_specs=[{"symbol": "BTCUSDT", "leverage": 10}])
    assert cfg.margin_specs[0].leverage == 10.0
    assert cfg.margin_specs[0].margin_mode == "cross"


def test_unknown_symbol_rejected():
    with pytest.raises(ValidationError):
        _config(trading_mode="futures", margin_specs=[{"symbol": "SOLUSDT", "leverage": 5}])


def test_duplicate_symbol_rejected():
    with pytest.raises(ValidationError):
        _config(
            trading_mode="futures",
            margin_specs=[
                {"symbol": "BTCUSDT", "leverage": 5},
                {"symbol": "BTCUSDT", "leverage": 10},
            ],
        )


@pytest.mark.parametrize("leverage", [0, 0.5, 126])
def test_leverage_out_of_range_rejected(leverage):
    with pytest.raises(ValidationError):
        SymbolMarginSpec(symbol="BTCUSDT", leverage=leverage)


def test_global_leverage_must_be_at_least_one():
    with pytest.raises(ValidationError):
        _config(leverage=0)
