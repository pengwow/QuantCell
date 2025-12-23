#!/usr/bin/env python3
"""
测试D.calendar方法是否能正常使用自定义频率格式
"""

# 导入自定义Freq类，触发monkey patching
import custom_freq
# 测试用户提供的代码
from qlib.data import D

print("测试D.calendar方法:")
print("=" * 50)

test_cases = [
    ("1h", "小时格式"),
    ("1m", "分钟简写格式"),
    ("1min", "分钟完整格式"),
    ("1d", "天格式"),
]

for freq_str, desc in test_cases:
    try:
        print(f"\n测试{desc} {freq_str}:")
        result = D.calendar(start_time="2025-11-01", end_time="2025-11-02", freq=freq_str)
        print(f"✓ 成功获取日历数据，共{len(result)}条记录")
        if len(result) > 0:
            print(f"  前5条记录: {result[:5]}")
            print(f"  最后5条记录: {result[-5:]}")
    except Exception as e:
        print(f"✗ 错误: {e}")

print("\n测试完成!")
