import sys
from pathlib import Path

# 方法2：手动构建路径
project_root = Path("/Users/liupeng/workspace/quantcell")

sys.path.append(str(project_root))
from collector.scripts.get_data import GetData

GetData().crypto_binance(
    start="2025-10-01",
    end="2025-12-10",
    interval="1d",
    symbols="BTCUSDT,ETHUSDT",
    convert_to_qlib=True,
    save_dir="/Users/liupeng/workspace/quantcell/backend/data/source",
    qlib_dir="/Users/liupeng/workspace/quantcell/backend/data/qlib_data",
    exists_skip=True,
)