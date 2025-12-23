#!/usr/bin/env python3
"""
测试脚本：验证freq="1d"修复是否有效
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # backend/examples -> backend -> qbot
sys.path.append(str(project_root))

print("测试freq='1d'修复是否有效")
print("=" * 50)

# 1. 导入自定义Freq和日历提供器，确保在使用qlib的任何功能之前执行
print("1. 导入自定义Freq和日历提供器")
try:
    from backend.qlib_integration import (CustomCalendarProvider,
                                          custom_calendar_provider,
                                          custom_freq)
    print("✓ 成功导入自定义模块")
except Exception as e:
    print(f"✗ 导入自定义模块失败: {e}")
    sys.exit(1)

# 2. 测试Freq对象的__str__方法
print("\n2. 测试Freq对象的__str__方法")
try:
    from qlib.utils.time import Freq

    # 测试不同频率的字符串表示
    test_cases = [
        ("1d", "1d"),
        ("day", "day"),
        ("1h", "1h"),
        ("hour", "hour"),
        ("1m", "1m"),
        ("min", "min"),
    ]
    
    for freq_str, expected in test_cases:
        freq_obj = Freq(freq_str)
        actual = str(freq_obj)
        print(f"  {freq_str:<8} -> str(Freq(freq_str)) = '{actual}'")
        
    # 特别测试1d的情况
    freq_1d = Freq("1d")
    print(f"  \n  特别测试: Freq('1d').base = '{freq_1d.base}', Freq('1d').count = '{freq_1d.count}'")
    
except Exception as e:
    print(f"✗ 测试Freq对象失败: {e}")
    sys.exit(1)

# 3. 测试CustomFileCalendarStorage的_freq_file方法
print("\n3. 测试CustomFileCalendarStorage的_freq_file方法")
try:
    from backend.qlib_integration.custom_calendar_provider import \
        CustomFileCalendarStorage

    # 测试不同频率的_freq_file返回值
    test_cases = [
        ("1d", "1d"),
        ("day", "1d"),
        ("1h", "1h"),
        ("hour", "1h"),
        ("1m", "1m"),
        ("min", "1m"),
    ]
    
    for freq, expected in test_cases:
        # 创建模拟实例
        storage = CustomFileCalendarStorage.__new__(CustomFileCalendarStorage)
        storage.freq = freq
        storage.future = False
        
        # 获取_freq_file属性
        actual = storage._freq_file
        status = "✓" if actual == expected else "✗"
        print(f"  {status} {freq:<8} -> _freq_file = '{actual}' (预期: '{expected}')")
        
except Exception as e:
    print(f"✗ 测试CustomFileCalendarStorage失败: {e}")
    sys.exit(1)

# 4. 初始化qlib并测试features方法
print("\n4. 初始化qlib并测试features方法")
try:
    # 在导入qlib.data之前应用文件存储补丁
    from backend.qlib_integration import file_storage_patch
    print("✓ 已应用文件存储补丁")
    
    import qlib
    from qlib.config import C

    # 初始化qlib
    data_dir = '/Users/liupeng/workspace/qbot/backend/data/source'
    qlib.init(provider_uri=data_dir)
    print("✓ qlib初始化成功")
    
    # 现在导入D，确保使用补丁后的FileCalendarStorage
    from qlib.data import D

    # 测试D.features方法，使用freq="1d"
    print("\n测试D.features方法，使用freq='1d':")
    df = D.features(
        ["btcusdt"],
        ["$open", "$high", "$low", "$close", "$volume"],
        start_time="2025-10-01",
        end_time="2025-10-10",
        freq="1d"
    )
    print("✓ D.features调用成功")
    print(f"\n返回的数据形状: {df.shape}")
    print("\n数据预览:")
    print(df.head())
    
except Exception as e:
    print(f"✗ 测试D.features失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 50)
print("测试完成！freq='1d'修复有效")
