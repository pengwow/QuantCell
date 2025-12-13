#!/usr/bin/env python3
"""
测试自定义日历提供者是否能正常工作
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

# 导入自定义日历提供者
from backend.qlib_integration.custom_calendar_provider import CustomCalendarProvider

# 导入自定义Freq类，确保支持更多频率格式
from backend.qlib_integration import custom_freq

# 初始化qlib
import qlib
from qlib.config import C

# 设置qlib配置
qlib.init(
    provider_uri='~/.qlib/crypto_data/qlib_data',
    region='us'
)

# 测试自定义日历提供者直接使用
print("测试自定义日历提供者直接使用:")
print("=" * 50)

# 创建自定义日历提供者实例
custom_calendar_provider = CustomCalendarProvider()

test_cases = [
    ("1m", "分钟简写格式"),
    ("1min", "分钟完整格式"),
    ("1h", "小时格式"),
    ("1d", "天格式"),
]

for freq_str, desc in test_cases:
    try:
        print(f"\n测试{desc} {freq_str}:")
        result = custom_calendar_provider.calendar(start_time="2025-11-01", end_time="2025-11-02", freq=freq_str)
        print(f"✓ 成功获取日历数据，共{len(result)}条记录")
        if len(result) > 0:
            print(f"  前5条记录: {result[:5]}")
            print(f"  最后5条记录: {result[-5:]}")
    except Exception as e:
        print(f"✗ 错误: {e}")

print("\n测试完成!")
