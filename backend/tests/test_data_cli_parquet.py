#!/usr/bin/env python3
"""
测试 data_cli.py 的 Parquet 导出功能

这个脚本独立测试核心功能，避免依赖完整的 CLI 启动流程。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import tempfile


def test_query_function_exists():
    """测试共享查询函数是否存在且可调用"""
    try:
        from scripts.data_cli import _query_kline_data_from_db, _validate_parquet_export
        print("✓ 核心函数导入成功")
        print(f"  - _query_kline_data_from_db: {_query_kline_data_from_db.__doc__[:50]}...")
        print(f"  - _validate_parquet_export: {_validate_parquet_export.__doc__[:50]}...")
        return True
    except ImportError as e:
        print(f"❌ 函数导入失败: {e}")
        return False


def test_validate_function():
    """测试验证函数的基本功能"""
    from scripts.data_cli import _validate_parquet_export

    # 创建临时测试数据
    test_df = pd.DataFrame({
        'timestamp': [1704067200000000000, 1704067260000000000],
        'open': [42000.0, 42300.0],
        'high': [42500.0, 42400.0],
        'low': [41800.0, 42100.0],
        'close': [42300.0, 42200.0],
        'volume': [1000.5, 800.2]
    })

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 测试正常情况
        output_path = Path(tmp_dir) / "test.parquet"

        # 先保存文件
        from utils.parquet_utils import save_to_parquet
        save_to_parquet(test_df, output_path)

        # 验证文件
        result = _validate_parquet_export(output_path, test_df, verbose=True)
        if result:
            print("✓ 验证函数测试通过")
        else:
            print("❌ 验证函数返回 False")
        return result


def test_parquet_utils_integration():
    """测试 parquet_utils 集成"""
    try:
        from utils.parquet_utils import save_to_parquet, load_from_parquet, get_parquet_info
        print("✓ parquet_utils 工具函数导入成功")

        # 创建测试数据
        test_df = pd.DataFrame({
            'symbol': ['BTCUSDT', 'BTCUSDT'],
            'interval': ['1h', '1h'],
            'timestamp': [1704067200000000000, 1704067260000000000],
            'open': [42000.0, 42300.0],
            'high': [42500.0, 42400.0],
            'low': [41800.0, 42100.0],
            'close': [42300.0, 42200.0],
            'volume': [1000.5, 800.2]
        })

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 测试保存和加载
            output_path = Path(tmp_dir) / "test.parquet"
            success = save_to_parquet(test_df, output_path)
            if not success:
                print("❌ 保存 Parquet 失败")
                return False
            print(f"✓ 成功保存 Parquet 文件 ({len(test_df)} 行)")

            # 加载并验证
            loaded = load_from_parquet(output_path)
            if len(loaded) != len(test_df):
                print(f"❌ 数据行数不一致: {len(loaded)} vs {len(test_df)}")
                return False
            print(f"✓ 成功加载 Parquet 文件 ({len(loaded)} 行)")

            # 获取文件信息
            info = get_parquet_info(output_path)
            if info and 'num_rows' in info:
                print(f"✓ 文件信息获取成功 (行数: {info['num_rows']}, 大小: {info.get('file_size_mb', 0):.2f} MB)")
            else:
                print("⚠️ 无法获取文件信息")

        return True
    except Exception as e:
        print(f"❌ parquet_utils 集成测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Data CLI Parquet 导出功能测试")
    print("=" * 60)
    print()

    results = []

    # 测试 1: 函数存在性检查
    print("测试 1: 检查核心函数...")
    results.append(("函数导入", test_query_function_exists()))
    print()

    # 测试 2: parquet_utils 集成
    print("测试 2: parquet_utils 工具集成...")
    results.append(("工具集成", test_parquet_utils_integration()))
    print()

    # 测试 3: 验证函数
    print("测试 3: 文件验证功能...")
    results.append(("文件验证", test_validate_function()))
    print()

    # 输出总结
    print("=" * 60)
    print("测试结果总结:")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {name}: {status}")

    print()
    print(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！Parquet 导出功能已就绪。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试未通过，请检查。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
