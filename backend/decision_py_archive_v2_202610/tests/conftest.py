"""decision 测试共享夹具：确定性合成 K 线工厂。"""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def bars_factory():
    """返回构造函数 _bars(n=25, drift=0.0)：close 等距 + 线性漂移。"""

    def _bars(n: int = 25, *, drift: float = 0.0) -> pd.DataFrame:
        ts = [1700000000000 + i * 3_600_000 for i in range(n)]
        close = [100.0 + i + drift * i for i in range(n)]
        return pd.DataFrame(
            {
                "timestamp": ts,
                "open": [c - 1.0 for c in close],
                "high": [c + 1.0 for c in close],
                "low": [c - 1.5 for c in close],
                "close": close,
                "volume": [1000.0 + i for i in range(n)],
            }
        )

    return _bars
