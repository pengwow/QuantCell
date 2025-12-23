#!/usr/bin/env python3
"""
测试自定义Freq类是否能正常工作
"""

# 导入自定义Freq类，触发monkey patching
import custom_freq
# 测试各种频率格式
from qlib.utils.time import Freq

# 测试parse方法
test_cases = [
    # 分钟格式
    ("1min", (1, "min")),
    ("5minute", (5, "min")),
    ("1m", (1, "min")),
    ("30m", (30, "min")),
    
    # 小时格式
    ("1h", (1, "hour")),
    ("2hour", (2, "hour")),
    
    # 天格式
    ("1d", (1, "day")),
    ("2day", (2, "day")),
    
    # 周格式
    ("1w", (1, "week")),
    ("2week", (2, "week")),
    
    # 月格式
    ("1mon", (1, "month")),
    ("2month", (2, "month")),
]

print("测试Freq.parse方法:")
print("=" * 50)

for freq_str, expected in test_cases:
    try:
        result = Freq.parse(freq_str)
        status = "✓" if result == expected else "✗"
        print(f"{status} {freq_str:<10} -> {result} {'(预期: ' + str(expected) + ')' if result != expected else ''}")
    except Exception as e:
        print(f"✗ {freq_str:<10} -> 错误: {e}")

print("\n测试Freq实例化:")
print("=" * 50)

for freq_str in ["1m", "5m", "1h", "2h", "1d", "2d"]:
    try:
        freq = Freq(freq_str)
        print(f"✓ {freq_str:<10} -> {freq} (count={freq.count}, base={freq.base})")
    except Exception as e:
        print(f"✗ {freq_str:<10} -> 错误: {e}")

print("\n测试get_timedelta方法:")
print("=" * 50)

for freq_str, expected_minutes in [
    ("1m", 1),
    ("5m", 5),
    ("1h", 60),
    ("2h", 120),
    ("1d", 1440),
]:
    try:
        freq = Freq(freq_str)
        timedelta = Freq.get_timedelta(freq.count, freq.base)
        minutes = timedelta.total_seconds() / 60
        status = "✓" if minutes == expected_minutes else "✗"
        print(f"{status} {freq_str:<10} -> {minutes}分钟 {'(预期: ' + str(expected_minutes) + '分钟)' if minutes != expected_minutes else ''}")
    except Exception as e:
        print(f"✗ {freq_str:<10} -> 错误: {e}")

print("\n测试get_min_delta方法:")
print("=" * 50)

for left_freq, right_freq, expected_delta in [
    ("1h", "30m", 30),  # 1小时 - 30分钟 = 30分钟
    ("2h", "1h", 60),   # 2小时 - 1小时 = 60分钟
    ("1d", "12h", 720),  # 1天 - 12小时 = 720分钟
    ("30m", "15m", 15),  # 30分钟 - 15分钟 = 15分钟
]:
    try:
        delta = Freq.get_min_delta(left_freq, right_freq)
        status = "✓" if delta == expected_delta else "✗"
        print(f"{status} {left_freq:<5} - {right_freq:<5} = {delta}分钟 {'(预期: ' + str(expected_delta) + '分钟)' if delta != expected_delta else ''}")
    except Exception as e:
        print(f"✗ {left_freq:<5} - {right_freq:<5} -> 错误: {e}")

print("\n测试完成!")
