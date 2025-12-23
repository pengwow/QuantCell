#!/usr/bin/env python3
"""
示例脚本：展示如何使用自定义频率格式
"""

# 导入自定义Freq类，触发monkey patching
# 注意：这个导入需要在使用qlib的Freq类之前执行
import custom_freq
# 现在可以正常使用qlib的Freq类，支持更多频率格式
from qlib.utils.time import Freq

print("自定义Freq类使用示例:")
print("=" * 50)

# 示例1：创建Freq实例
print("\n1. 创建Freq实例:")
freq1 = Freq("1h")
freq2 = Freq("5m")
freq3 = Freq("1d")
freq4 = Freq("1min")

print(f"   1h -> {freq1} (count={freq1.count}, base={freq1.base})")
print(f"   5m -> {freq2} (count={freq2.count}, base={freq2.base})")
print(f"   1d -> {freq3} (count={freq3.count}, base={freq3.base})")
print(f"   1min -> {freq4} (count={freq4.count}, base={freq4.base})")
print(f"   注意：1min 也会返回 'm'，因为文件名使用简写格式")

# 示例2：使用parse方法
print("\n2. 使用parse方法:")
print(f"   Freq.parse('1h') -> {Freq.parse('1h')}")
print(f"   Freq.parse('5m') -> {Freq.parse('5m')}")
print(f"   Freq.parse('1d') -> {Freq.parse('1d')}")

# 示例3：比较频率
print("\n3. 比较频率:")
freq_hour = Freq("1h")
freq_minute = Freq("60m")
print(f"   1h == 60m: {freq_hour == freq_minute}")
print(f"   1h < 60m: {Freq.get_min_delta(freq_hour, freq_minute) < 0}")

# 示例4：获取时间增量
print("\n4. 获取时间增量:")
print(f"   1h的时间增量: {Freq.get_timedelta(1, 'hour')}")
print(f"   5m的时间增量: {Freq.get_timedelta(5, 'min')}")

print("\n5. 支持的频率格式:")
print("   - 分钟: 1min, 5minute, 1m, 30m")
print("   - 小时: 1h, 2hour")
print("   - 天: 1d, 2day")
print("   - 周: 1w, 2week")
print("   - 月: 1mon, 2month")

print("\n使用说明:")
print("1. 在使用qlib的Freq类之前，导入custom_freq模块")
print("2. 然后可以正常使用qlib的D.calendar等方法，支持更多频率格式")
print("3. 例如: D.calendar(start_time='2025-11-01', end_time='2025-11-30', freq='1h')")

print("\n示例代码:")
print("""\n# 导入自定义Freq类
import custom_freq

# 然后可以正常使用qlib的D.calendar方法
from qlib.data import D
from qlib.init import init

# 初始化qlib
init()

# 使用小时格式
result = D.calendar(start_time='2025-11-01', end_time='2025-11-30', freq='1h')
print(f"获取到{len(result)}条小时级别的日历数据")
""")

print("\n示例完成!")
