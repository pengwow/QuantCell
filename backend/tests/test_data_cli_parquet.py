#!/usr/bin/env python3
"""
测试 data_cli.py 的 Parquet 导出功能

这个脚本独立测试核心功能，避免依赖完整的 CLI 启动流程。
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd


def test_query_function_exists():
    """测试共享验证函数是否存在且可调用

    注：原 _query_kline_data_from_db 已在历史重构中从 cli.data 移除，
    仅保留仍存在的 _validate_parquet_export。
    """
    from cli.data import _validate_parquet_export

    assert callable(_validate_parquet_export)


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
        assert _validate_parquet_export(output_path, test_df)


def test_parquet_utils_integration():
    """测试 parquet_utils 集成"""
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
        assert save_to_parquet(test_df, output_path)

        # 加载并验证
        loaded = load_from_parquet(output_path)
        assert len(loaded) == len(test_df)

        # 获取文件信息
        info = get_parquet_info(output_path)
        assert info and "num_rows" in info


def main():
    """运行所有测试（失败直接抛异常，由非零退出码体现）"""
    test_query_function_exists()
    test_parquet_utils_integration()
    test_validate_function()
    return 0


if __name__ == "__main__":
    sys.exit(main())
