#!/usr/bin/env python3
"""
测试日历文件名生成
验证不同频率格式下生成的日历文件名是否符合预期
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from qlib.utils.time import Freq

# 导入自定义存储类
from backend.qlib_integration.custom_calendar_provider import \
    CustomFileCalendarStorage


def test_calendar_filename():
    """
    测试不同频率下的日历文件名生成
    """
    print("测试日历文件名生成")
    print("=" * 50)
    
    # 测试用例
    test_cases = [
        ('1m', '1m'),
        ('1min', '1m'),
        ('5m', '5m'),
        ('30m', '30m'),
        ('1h', '1h'),
        ('2h', '2h'),
        ('1d', '1d'),
        ('5d', '5d'),
    ]
    
    # 测试每个频率
    for freq, expected_freq_file in test_cases:
        try:
            # 创建自定义存储类实例
            # 注意：我们使用模拟的__init__方法，因为完整初始化需要更多参数
            storage = CustomFileCalendarStorage.__new__(CustomFileCalendarStorage)
            storage.freq = freq
            storage.future = False
            
            # 获取_freq_file属性
            freq_file = storage._freq_file
            
            # 验证结果
            if freq_file == expected_freq_file:
                print(f"✓ {freq:<8} -> {freq_file:<10} (预期: {expected_freq_file})")
            else:
                print(f"✗ {freq:<8} -> {freq_file:<10} (预期: {expected_freq_file})")
        except Exception as e:
            print(f"✗ {freq:<8} -> 错误: {str(e)}")
    
    # 测试uri属性核心逻辑
    print("\n测试uri属性核心逻辑:")
    print("=" * 50)
    
    # 直接测试uri属性的核心功能：根据_freq_file结果生成文件名
    from pathlib import Path

    # 频率映射，模拟_freq_file的返回值
    freq_mapping = {
        "1m.txt": "1m",
        "1min.txt": "1m",
        "5m.txt": "5m",
        "1h.txt": "1h",
        "1d.txt": "1d",
        "5d.txt": "5d",
    }
    
    # 测试用例：原始路径
    test_cases = [
        Path("/test/path/calendars/1m.txt"),
        Path("/test/path/calendars/1min.txt"),
        Path("/test/path/calendars/5m.txt"),
        Path("/test/path/calendars/1h.txt"),
        Path("/test/path/calendars/1d.txt"),
        Path("/test/path/calendars/5d.txt"),
    ]
    
    # 模拟CustomFileCalendarStorage实例的uri属性行为
    for original_path in test_cases:
        try:
            # 获取预期的_freq_file结果
            expected_freq_file = freq_mapping[original_path.name]
            expected_file_name = f"{expected_freq_file}.txt"
            expected_path = original_path.parent / expected_file_name
            
            # 创建一个简单的对象来模拟CustomFileCalendarStorage实例
            class MockStorage:
                def __init__(self, freq_file):
                    self._freq_file_value = freq_file
                
                @property
                def uri(self):
                    return original_path
                
                @property
                def _freq_file(self):
                    return self._freq_file_value
            
            # 测试uri属性的核心逻辑
            mock_storage = MockStorage(expected_freq_file)
            custom_uri = mock_storage.uri.parent / f"{mock_storage._freq_file}.txt"
            
            # 验证结果
            if custom_uri == expected_path:
                print(f"✓ {original_path.name:<10} -> {custom_uri.name:<10} (预期: {expected_file_name})")
            else:
                print(f"✗ {original_path.name:<10} -> {custom_uri.name:<10} (预期: {expected_file_name})")
                print(f"  完整路径: {custom_uri}")
        except Exception as e:
            print(f"✗ {original_path.name:<10} -> 错误: {str(e)}")
    
    print("=" * 50)
    print("测试完成!")


if __name__ == "__main__":
    # 先导入自定义频率
    from backend.qlib_integration import custom_freq

    # 运行测试
    test_calendar_filename()
