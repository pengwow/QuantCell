"""quantcell backtest — 事件驱动回测(axon_quant 唯一)。"""
from __future__ import annotations

# backtest_cli 自身是转调 shim,真正的 app 在 backtest.cli
from backtest.cli import app  # noqa: F401

__all__ = ["app"]
