"""quantcell backtest — 事件驱动回测(axon_quant 唯一)。"""
from __future__ import annotations

import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from backtest.cli import app  # noqa: F401

__all__ = ["app"]

if __name__ == "__main__":
    app()
