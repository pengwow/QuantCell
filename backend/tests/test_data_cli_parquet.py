#!/usr/bin/env python3
"""
测试 data_cli.py 的 Parquet 导出功能

这个脚本独立测试核心功能，避免依赖完整的 CLI 启动流程。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile

import pandas as pd


def test_query_function_exists():
    """测试共享查询函数是否存在且可调用"""
    try:
        from cli.data import _query_kline_data_from_db, _validate_parquet_export

        return True
    except ImportError:
        return False


def test_validate_function():
    """测试验证函数的基本功能"""
    from cli.data import _validate_parquet_export

    # 创建临时测试数据
    test_df = pd.DataFrame(
        {
            "timestamp": [1704067200000000000, 1704067260000000000],
            "open": [42000.0, 42300.0],
            "high": [42500.0, 42400.0],
            "low": [41800.0, 42100.0],
            "close": [42300.0, 42200.0],
            "volume": [1000.5, 800.2],
        }
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 测试正常情况
        output_path = Path(tmp_dir) / "test.parquet"

        # 先保存文件
        from utils.parquet_utils import save_to_parquet

        save_to_parquet(test_df, output_path)

        # 验证文件
        result = _validate_parquet_export(output_path, test_df)
        if result:
            pass
        else:
            pass
        return result


def test_parquet_utils_integration():
    """测试 parquet_utils 集成"""
    try:
        from utils.parquet_utils import (
            get_parquet_info,
            load_from_parquet,
            save_to_parquet,
        )

        # 创建测试数据
        test_df = pd.DataFrame(
            {
                "symbol": ["BTCUSDT", "BTCUSDT"],
                "interval": ["1h", "1h"],
                "timestamp": [1704067200000000000, 1704067260000000000],
                "open": [42000.0, 42300.0],
                "high": [42500.0, 42400.0],
                "low": [41800.0, 42100.0],
                "close": [42300.0, 42200.0],
                "volume": [1000.5, 800.2],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 测试保存和加载
            output_path = Path(tmp_dir) / "test.parquet"
            success = save_to_parquet(test_df, output_path)
            if not success:
                return False

            # 加载并验证
            loaded = load_from_parquet(output_path)
            if len(loaded) != len(test_df):
                return False

            # 获取文件信息
            info = get_parquet_info(output_path)
            if info and "num_rows" in info:
                pass
            else:
                pass

        return True
    except Exception:
        return False


def main():
    """运行所有测试"""

    results = []

    # 测试 1: 函数存在性检查
    results.append(("函数导入", test_query_function_exists()))

    # 测试 2: parquet_utils 集成
    results.append(("工具集成", test_parquet_utils_integration()))

    # 测试 3: 验证函数
    results.append(("文件验证", test_validate_function()))

    # 输出总结
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for _name, _result in results:
        pass

    if passed == total:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
