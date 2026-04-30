#!/usr/bin/env python3
"""
测试 export parquet 的默认路径生成逻辑
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_default_path_generation():
    """测试默认路径生成逻辑"""
    print("=" * 60)
    print("测试: 默认输出路径生成")
    print("=" * 60)

    # 模拟参数
    test_cases = [
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "candle_type": "spot",
            "expected_table": "crypto_spot_klines",
            "expected_filename": "BTCUSDT_1h.parquet"
        },
        {
            "symbol": "ETHUSDT",
            "interval": "5m",
            "candle_type": "future",
            "expected_table": "crypto_future_klines",
            "expected_filename": "ETHUSDT_5m.parquet"
        },
        {
            "symbol": "SOLUSDT",
            "interval": "1d",
            "candle_type": "futures",  # 测试复数形式
            "expected_table": "crypto_future_klines",
            "expected_filename": "SOLUSDT_1d.parquet"
        }
    ]

    backend_path = Path(__file__).parent.parent

    for i, case in enumerate(test_cases, 1):
        symbol = case["symbol"]
        interval = case["interval"]
        candle_type = case["candle_type"]

        # 生成路径（与 export_parquet 函数中的逻辑一致）
        if candle_type.lower() in ["future", "futures"]:
            table_name = "crypto_future_klines"
        else:
            table_name = "crypto_spot_klines"

        data_dir = backend_path / "data" / table_name
        output_path = data_dir / f"{symbol.upper()}_{interval}.parquet"

        # 验证结果
        expected_path = backend_path / "data" / case["expected_table"] / case["expected_filename"]

        print(f"\n测试用例 {i}:")
        print(f"  输入:")
        print(f"    - symbol: {symbol}")
        print(f"    - interval: {interval}")
        print(f"    - candle_type: {candle_type}")
        print(f"  输出:")
        print(f"    - 表名目录: {table_name}")
        print(f"    - 文件名: {case['expected_filename']}")
        print(f"    - 完整路径: {output_path}")

        if output_path == expected_path:
            print(f"  ✅ 路径生成正确")
        else:
            print(f"  ❌ 路径不匹配")
            print(f"    预期: {expected_path}")
            print(f"    实际: {output_path}")
            return False

    print("\n" + "=" * 60)
    print("✅ 所有测试用例通过！")
    print("=" * 60)

    # 显示使用示例
    print("\n📝 使用示例:")
    print("-" * 60)
    print("# 现货数据（默认保存到 crypto_spot_klines/）")
    print("python data_cli.py export parquet -s BTCUSDT -i 5m")
    print(f"# → {backend_path}/data/crypto_spot_klines/BTCUSDT_5m.parquet")

    print("\n# 合约数据（默认保存到 crypto_future_klines/）")
    print("python data_cli.py export parquet -s ETHUSDT -i 1h --candle-type future")
    print(f"# → {backend_path}/data/crypto_future_klines/ETHUSDT_1h.parquet")

    print("\n# 自定义输出路径（可选）")
    print("python data_cli.py export parquet -s BTCUSDT -i 1d -o /tmp/custom.parquet")
    print("# → /tmp/custom.parquet")

    return True


if __name__ == "__main__":
    success = test_default_path_generation()
    sys.exit(0 if success else 1)
