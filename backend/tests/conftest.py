"""
pytest配置文件

配置测试环境，解决模块导入问题
"""

import os
import sqlite3
import sys
import tempfile
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

# =============================================================================
# 测试存储隔离（防止集成测试向真实数据目录写垃圾数据）
#

# 1) SQLite 重定向：collector.db.database 在 import 时读取 DB_FILE 环境变量，
#    本文件是最顶层 conftest（先于所有测试模块加载），在此设置即可生效。
#    不隔离的话，TestClient 调用 POST /backtest/run 会向 backend/data/quantcell_sqlite.db
#    写入真实的 pending 任务行（已产生数千行 SmaCross 垃圾记录）。
#    注意：部分单测模块在 import 时就读真实库的 seed 数据（如 factor_catalog），
#    所以不能指向空库——先做一致性快照复制到临时测试库，再指向该副本；
#    测试产生的所有写操作（含垃圾行）都落在副本上，真实库零污染，每次 pytest 重新复制。
_TEST_DB_DIR = tempfile.mkdtemp(prefix="quantcell_test_db_")
_TEST_DB_FILE = os.path.join(_TEST_DB_DIR, "quantcell_test.db")
_real_db = backend_dir / "data" / "quantcell_sqlite.db"
if _real_db.exists():
    _src = sqlite3.connect(str(_real_db))
    _dst = sqlite3.connect(_TEST_DB_FILE)
    _src.backup(_dst)  # SQLite backup API：一致性快照，不受运行中服务并发写影响
    _src.close()
    _dst.close()
os.environ.setdefault("DB_FILE", _TEST_DB_FILE)


@pytest.fixture(autouse=True)
def _isolate_backtest_task_storage(monkeypatch, tmp_path):
    """隔离回测任务的文件落盘到 pytest 临时目录。

    backtest/routes.py 的 /run 在后台线程里 create_task() 写 task_*.json，
    测试只 mock run_backtest 拦不住这个副作用，残留文件永远停在 pending——
    这是回测记录页出现大量 SmaCross pending 垃圾的根因，因此统一重定向。
    只 patch routes 单例实例属性；task 目录由 results_dir 推导，一并被隔离。
    """
    from backtest.routes import backtest_service

    results_dir = tmp_path / "backtest_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(backtest_service, "results_dir", results_dir)


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
