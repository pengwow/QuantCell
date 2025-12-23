import sys
from pathlib import Path

# 方法2：手动构建路径
project_root = Path("/Users/liupeng/workspace/qbot")

sys.path.append(str(project_root))
from backend.collector.scripts.get_data import GetData

GetData().crypto_binance(
    start="2025-10-01",
    end="2025-12-10",
    interval="1d",
    symbols="BTCUSDT,ETHUSDT",
    convert_to_qlib=True,
    save_dir="/Users/liupeng/workspace/qbot/backend/data/source",
    qlib_dir="/Users/liupeng/workspace/qbot/backend/data/qlib_data",
    exists_skip=True,
)