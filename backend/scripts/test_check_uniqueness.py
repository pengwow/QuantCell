#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试check_kline_health.py中的check_uniqueness功能

用于验证K线数据唯一性检查功能的正确性
"""

import sys
import pandas as pd
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

from backend.scripts.check_kline_health import KlineHealthChecker


def test_no_duplicates():
    """测试1: 无重复数据的情况"""
    print("\n" + "="*60)
    print("测试1: 无重复数据的情况")
    print("="*60)
    
    # 创建无重复的测试数据
    data = {
        'id': [1, 2, 3, 4, 5],
        'date': pd.date_range(start='2024-01-01', periods=5, freq='1d'),
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0],
        'close': [104.0, 105.0, 106.0, 107.0, 108.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }
    df = pd.DataFrame(data)
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "pass", "无重复数据时状态应该是pass"
    assert result["duplicate_records"] == 0, "无重复数据时重复记录数应该是0"
    assert len(result["duplicate_periods"]) == 0, "无重复数据时重复时间戳列表应该是空的"
    assert len(result["duplicate_details"]) == 0, "无重复数据时重复详情应该是空的"
    
    print("\n✅ 测试1通过: 无重复数据的情况检测正确")


def test_duplicate_timestamps():
    """测试2: 有重复时间戳的情况"""
    print("\n" + "="*60)
    print("测试2: 有重复时间戳的情况")
    print("="*60)
    
    # 创建有重复时间戳的测试数据
    data = {
        'id': [1, 2, 3, 4, 5],
        'date': [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-02'),  # 重复的时间戳
            pd.Timestamp('2024-01-03'),
            pd.Timestamp('2024-01-04')
        ],
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0],
        'close': [104.0, 105.0, 106.0, 107.0, 108.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }
    df = pd.DataFrame(data)
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "fail", "有重复数据时状态应该是fail"
    assert result["duplicate_records"] == 2, f"应该检测到2条重复记录，实际检测到{result['duplicate_records']}条"
    assert len(result["duplicate_periods"]) == 1, f"应该检测到1个重复时间戳，实际检测到{len(result['duplicate_periods'])}个"
    assert len(result["duplicate_details"]) == 1, f"应该有1组重复详情，实际有{len(result['duplicate_details'])}组"
    
    # 验证重复详情
    duplicate_detail = result["duplicate_details"][0]
    assert duplicate_detail["group_type"] == "timestamp_duplicate", "重复类型应该是timestamp_duplicate"
    assert duplicate_detail["count"] == 2, f"重复记录数应该是2，实际是{duplicate_detail['count']}"
    assert len(duplicate_detail["records"]) == 2, f"重复详情应该包含2条记录，实际包含{len(duplicate_detail['records'])}条"
    
    print("\n✅ 测试2通过: 有重复时间戳的情况检测正确")


def test_multiple_duplicate_timestamps():
    """测试3: 多个重复时间戳的情况"""
    print("\n" + "="*60)
    print("测试3: 多个重复时间戳的情况")
    print("="*60)
    
    # 创建有多个重复时间戳的测试数据
    data = {
        'id': [1, 2, 3, 4, 5, 6, 7],
        'date': [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-02'),  # 重复
            pd.Timestamp('2024-01-03'),
            pd.Timestamp('2024-01-04'),
            pd.Timestamp('2024-01-04'),  # 重复
            pd.Timestamp('2024-01-05')
        ],
        'open': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 101.0],
        'close': [104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        'volume': [1000, 1100, 1200, 1300, 1400, 1500, 1600]
    }
    df = pd.DataFrame(data)
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "fail", "有重复数据时状态应该是fail"
    assert result["duplicate_records"] == 4, f"应该检测到4条重复记录，实际检测到{result['duplicate_records']}条"
    assert len(result["duplicate_periods"]) == 2, f"应该检测到2个重复时间戳，实际检测到{len(result['duplicate_periods'])}个"
    assert len(result["duplicate_details"]) == 2, f"应该有2组重复详情，实际有{len(result['duplicate_details'])}组"
    
    print("\n✅ 测试3通过: 多个重复时间戳的情况检测正确")


def test_duplicate_code_date():
    """测试4: 重复的code+date组合"""
    print("\n" + "="*60)
    print("测试4: 重复的code+date组合")
    print("="*60)
    
    # 创建有重复code+date组合的测试数据
    data = {
        'id': [1, 2, 3, 4, 5],
        'code': ['AAPL', 'AAPL', 'AAPL', 'GOOG', 'GOOG'],
        'date': [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-02'),  # 重复的code+date组合
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02')
        ],
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0],
        'close': [104.0, 105.0, 106.0, 107.0, 108.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }
    df = pd.DataFrame(data)
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "fail", "有重复code+date组合时状态应该是fail"
    assert result["duplicate_records"] > 0, "应该检测到重复记录"
    assert len(result["duplicate_code_timestamp"]) > 0, "应该检测到重复的code+date组合"
    
    print("\n✅ 测试4通过: 重复的code+date组合检测正确")


def test_empty_dataframe():
    """测试5: 空DataFrame的情况"""
    print("\n" + "="*60)
    print("测试5: 空DataFrame的情况")
    print("="*60)
    
    # 创建空的DataFrame
    df = pd.DataFrame()
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "pass", "空DataFrame时状态应该是pass"
    assert result["duplicate_records"] == 0, "空DataFrame时重复记录数应该是0"
    
    print("\n✅ 测试5通过: 空DataFrame的情况处理正确")


def test_timestamp_field():
    """测试6: 使用timestamp字段而不是date字段"""
    print("\n" + "="*60)
    print("测试6: 使用timestamp字段而不是date字段")
    print("="*60)
    
    # 创建使用timestamp字段的测试数据
    data = {
        'id': [1, 2, 3, 4, 5],
        'timestamp': [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-02'),  # 重复的时间戳
            pd.Timestamp('2024-01-03'),
            pd.Timestamp('2024-01-04')
        ],
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0],
        'close': [104.0, 105.0, 106.0, 107.0, 108.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }
    df = pd.DataFrame(data)
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "fail", "有重复数据时状态应该是fail"
    assert result["duplicate_records"] == 2, f"应该检测到2条重复记录，实际检测到{result['duplicate_records']}条"
    
    print("\n✅ 测试6通过: 使用timestamp字段的情况检测正确")


def test_triple_duplicate():
    """测试7: 同一时间戳有3条重复记录"""
    print("\n" + "="*60)
    print("测试7: 同一时间戳有3条重复记录")
    print("="*60)
    
    # 创建同一时间戳有3条重复记录的测试数据
    data = {
        'id': [1, 2, 3, 4, 5],
        'date': [
            pd.Timestamp('2024-01-01'),
            pd.Timestamp('2024-01-02'),
            pd.Timestamp('2024-01-02'),  # 重复
            pd.Timestamp('2024-01-02'),  # 重复
            pd.Timestamp('2024-01-03')
        ],
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0],
        'close': [104.0, 105.0, 106.0, 107.0, 108.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    }
    df = pd.DataFrame(data)
    
    # 执行检查
    checker = KlineHealthChecker()
    result = checker.check_uniqueness(df)
    
    # 验证结果
    print(f"测试数据:\n{df}")
    print(f"\n检查结果: {result}")
    
    assert result["status"] == "fail", "有重复数据时状态应该是fail"
    assert result["duplicate_records"] == 3, f"应该检测到3条重复记录，实际检测到{result['duplicate_records']}条"
    
    # 验证重复详情
    duplicate_detail = result["duplicate_details"][0]
    assert duplicate_detail["count"] == 3, f"重复记录数应该是3，实际是{duplicate_detail['count']}"
    assert len(duplicate_detail["records"]) == 3, f"重复详情应该包含3条记录，实际包含{len(duplicate_detail['records'])}条"
    
    print("\n✅ 测试7通过: 同一时间戳有3条重复记录的情况检测正确")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始运行check_uniqueness功能测试")
    print("="*60)
    
    try:
        test_no_duplicates()
        test_duplicate_timestamps()
        test_multiple_duplicate_timestamps()
        test_duplicate_code_date()
        test_empty_dataframe()
        test_timestamp_field()
        test_triple_duplicate()
        
        print("\n" + "="*60)
        print("🎉 所有测试通过！")
        print("="*60)
        print("\n测试总结:")
        print("✅ 测试1: 无重复数据的情况")
        print("✅ 测试2: 有重复时间戳的情况")
        print("✅ 测试3: 多个重复时间戳的情况")
        print("✅ 测试4: 重复的code+date组合")
        print("✅ 测试5: 空DataFrame的情况")
        print("✅ 测试6: 使用timestamp字段的情况")
        print("✅ 测试7: 同一时间戳有3条重复记录")
        print("\ncheck_uniqueness功能验证完成！")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()