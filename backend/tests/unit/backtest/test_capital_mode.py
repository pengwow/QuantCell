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
