#!/usr/bin/env python3
"""
测试 export parquet 的默认路径生成逻辑
"""

import sys
from pathlib import Path


def test_default_path_generation():
    """测试默认路径生成逻辑"""

    # 模拟参数
    test_cases = [
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "candle_type": "spot",
            "expected_table": "crypto_spot_klines",
            "expected_filename": "BTCUSDT_1h.parquet",
        },
        {
            "symbol": "ETHUSDT",
            "interval": "5m",
            "candle_type": "future",
            "expected_table": "crypto_future_klines",
            "expected_filename": "ETHUSDT_5m.parquet",
        },
        {
            "symbol": "SOLUSDT",
            "interval": "1d",
            "candle_type": "futures",  # 测试复数形式
            "expected_table": "crypto_future_klines",
            "expected_filename": "SOLUSDT_1d.parquet",
        },
    ]

    backend_path = Path(__file__).parent.parent

    for _i, case in enumerate(test_cases, 1):
        symbol = case["symbol"]
        interval = case["interval"]
        candle_type = case["candle_type"]

        # 生成路径（与 export_parquet 函数中的逻辑一致）
        table_name = "crypto_future_klines" if candle_type.lower() in ["future", "futures"] else "crypto_spot_klines"

        data_dir = backend_path / "data" / table_name
        output_path = data_dir / f"{symbol.upper()}_{interval}.parquet"

        # 验证结果
        expected_path = backend_path / "data" / case["expected_table"] / case["expected_filename"]

        if output_path == expected_path:
            pass
        else:
            return False

    # 显示使用示例

    return True


if __name__ == "__main__":
    success = test_default_path_generation()
    sys.exit(0 if success else 1)
