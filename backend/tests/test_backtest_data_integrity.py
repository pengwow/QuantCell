# -*- coding: utf-8 -*-
"""
回测数据完整性检查测试

测试数据完整性检查模块的各种场景
"""

import pytest
from datetime import datetime
from backtest.data_integrity import DataIntegrityChecker, DataIntegrityResult


class TestDataIntegrityChecker:
    """数据完整性检查器测试类"""

    def test_check_data_completeness_with_string_datetime(self):
        """测试使用字符串时间格式调用 check_data_completeness"""
        checker = DataIntegrityChecker()
        
        # 使用字符串格式的时间（模拟实际调用场景）
        result = checker.check_data_completeness(
            symbol="BTCUSDT",
            interval="1h",
            start_time="2024-01-01T00:00:00",  # 字符串格式
            end_time="2024-01-02T00:00:00",    # 字符串格式
            market_type='crypto',
            crypto_type='spot'
        )
        
        # 验证结果
        assert isinstance(result, DataIntegrityResult)
        print(f"检查结果: is_complete={result.is_complete}, coverage={result.coverage_percent}%")
        print(f"期望数据: {result.total_expected}, 实际数据: {result.total_actual}")

    def test_check_data_completeness_with_datetime_object(self):
        """测试使用datetime对象调用 check_data_completeness"""
        checker = DataIntegrityChecker()
        
        # 使用datetime对象
        result = checker.check_data_completeness(
            symbol="BTCUSDT",
            interval="1h",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 2, 0, 0, 0),
            market_type='crypto',
            crypto_type='spot'
        )
        
        # 验证结果
        assert isinstance(result, DataIntegrityResult)
        print(f"检查结果: is_complete={result.is_complete}, coverage={result.coverage_percent}%")

    def test_check_data_completeness_with_iso_format(self):
        """测试使用ISO格式字符串时间调用"""
        checker = DataIntegrityChecker()
        
        # 使用ISO格式字符串（带Z）
        result = checker.check_data_completeness(
            symbol="ETHUSDT",
            interval="1d",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-31T00:00:00Z",
            market_type='crypto',
            crypto_type='spot'
        )
        
        # 验证结果
        assert isinstance(result, DataIntegrityResult)
        print(f"检查结果: is_complete={result.is_complete}, coverage={result.coverage_percent}%")


if __name__ == "__main__":
    # 直接运行测试
    print("=" * 60)
    print("测试1: 使用字符串时间格式")
    print("=" * 60)
    test = TestDataIntegrityChecker()
    try:
        test.test_check_data_completeness_with_string_datetime()
        print("✓ 测试1通过")
    except Exception as e:
        print(f"✗ 测试1失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试2: 使用datetime对象")
    print("=" * 60)
    try:
        test.test_check_data_completeness_with_datetime_object()
        print("✓ 测试2通过")
    except Exception as e:
        print(f"✗ 测试2失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试3: 使用ISO格式字符串（带Z）")
    print("=" * 60)
    try:
        test.test_check_data_completeness_with_iso_format()
        print("✓ 测试3通过")
    except Exception as e:
        print(f"✗ 测试3失败: {e}")
        import traceback
        traceback.print_exc()
