#!/usr/bin/env python3
"""
示例脚本：展示如何使用自定义日历提供者
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

print("自定义日历提供者使用示例:")
print("=" * 50)

# 示例1：基本使用
print("\n1. 基本使用:")
print("=" * 30)

# 初始化qlib
import qlib

# 导入自定义日历提供者，自动触发monkey patching
# 导入自定义Freq类，确保支持更多频率格式
# 注意：这个导入需要在使用qlib的任何功能之前执行，并且要在custom_calendar_provider之前导入
from backend.qlib_integration import custom_calendar_provider, custom_freq

qlib.init(
    provider_uri='~/.qlib/crypto_data/qlib_data',
    region='us'
)

# 使用日历功能
from qlib.data import D

# 测试不同频率格式
freq_formats = ["1m", "1min", "1h", "1d"]

for freq in freq_formats:
    try:
        print(f"\n测试频率 {freq}:")
        # 获取日历数据
        result = D.calendar(start_time="2025-11-01", end_time="2025-11-02", freq=freq)
        print(f"  ✓ 成功获取日历数据，共{len(result)}条记录")
        if len(result) > 0:
            print(f"  前3条记录: {result[:3]}")
            print(f"  最后3条记录: {result[-3:]}")
    except Exception as e:
        print(f"  ✗ 错误: {e}")

# 示例2：查看Freq对象的字符串表示
print("\n2. Freq对象的字符串表示:")
print("=" * 30)

from qlib.utils.time import Freq

freq_objects = [
    Freq("1m"),
    Freq("1min"),
    Freq("5m"),
    Freq("1h"),
    Freq("2hour"),
    Freq("1d"),
]

for freq_obj in freq_objects:
    print(f"  {freq_obj} -> str(freq_obj) = '{str(freq_obj)}', count={freq_obj.count}, base={freq_obj.base}")

print("\n使用说明:")
print("=" * 50)
print("1. 导入自定义日历提供者，自动触发monkey patching:")
print("   from backend.qlib_integration import custom_calendar_provider")
print("   from backend.qlib_integration import custom_freq")
print("   # 注意：这个导入需要在使用qlib的任何功能之前执行")

print("\n2. 初始化qlib:")
print("   import qlib")
print("   qlib.init(provider_uri='~/.qlib/crypto_data/qlib_data')")

print("\n3. 使用日历功能:")
print("   from qlib.data import D")
print("   result = D.calendar(start_time='2025-11-01', end_time='2025-11-30', freq='1m')")

print("\n4. 支持的频率格式:")
print("   - 分钟: 1min, 5minute, 1m, 30m")
print("   - 小时: 1h, 2hour")
print("   - 天: 1d, 2day")
print("   - 周: 1w, 2week")
print("   - 月: 1mon, 2month")

print("\n5. 日历文件路径:")
print("   - 当freq='1m'时，会读取: provider_uri/calendars/m.txt")
print("   - 当freq='1min'时，会读取: provider_uri/calendars/m.txt")
print("   - 当freq='1h'时，会读取: provider_uri/calendars/h.txt")
print("   - 当freq='1d'时，会读取: provider_uri/calendars/day.txt")

print("\n示例完成!")
