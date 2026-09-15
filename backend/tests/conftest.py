"""
pytest配置文件

配置测试环境，解决模块导入问题
"""

import sys
from pathlib import Path

# 将backend目录添加到Python路径（必须排在tests之前）
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# 将tests目录添加到Python路径（用于导入fixtures模块）
# 注意：必须排在backend之后，避免tests/utils/覆盖backend/utils/
tests_dir = Path(__file__).parent
if str(tests_dir) not in sys.path:
    sys.path.append(str(tests_dir))  # 使用append而不是insert，确保排在backend之后

# 打印路径信息（调试用）

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def trending_kline() -> pd.DataFrame:
    """200 根小时 K 线,稳定上涨(供 dual_ma / 趋势型回测断言)。

    复用既有测试中的合成数据模式:index = DatetimeIndex(1h 频率)。
    """
    dates = pd.date_range("2024-07-01", periods=200, freq="1h")
    closes = [100.0 + i * 0.5 for i in range(200)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * 200,
        },
        index=dates,
    )


@pytest.fixture
def flat_kline() -> pd.DataFrame:
    """180 根小时 K 线,价格恒定 —— 用于验证 funding/费用/不变量等与方向无关的断言。"""
    dates = pd.date_range("2024-07-01", periods=180, freq="1h")
    closes = [100.0] * 180
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * 180,
        },
        index=dates,
    )


@pytest.fixture
def sample_btcusdt_1h() -> pd.DataFrame:
    """消费仓库内闲置的真实样本 `tests/data/sample_btcusdt_1h.csv`(100 根 1h K 线)。

    让真实数据资产进入测试流水线(报告 5.1 建议),同时覆盖 CSV 加载路径。
    """
    csv_path = Path(__file__).parent / "data" / "sample_btcusdt_1h.csv"
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.set_index("timestamp")
