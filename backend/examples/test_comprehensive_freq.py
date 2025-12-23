#!/usr/bin/env python3
"""
全面测试频率格式处理，特别是1d频率的处理
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到sys.path
current_dir = Path(os.getcwd())
project_root = current_dir.parent.parent  # backend/examples -> backend -> qbot
sys.path.append(str(project_root))

# 在导入qlib之前应用补丁
from backend.qlib_integration import file_storage_patch

print("✓ 已应用文件存储补丁")

import qlib
# 导入必要的库
from qlib.data import D

# 初始化qlib
data_dir = os.path.join(project_root, 'backend/data/source')
print(f"数据目录: {data_dir}")
qlib.init(provider_uri=data_dir)
print("✓ QLib初始化成功")

# 测试频率格式列表
test_freqs = [
    "1d",
    "day",
    "1m",
    "min",
    "15m",
    "30min",
    "1h",
    "hour",
    "2h",
    "3hour",
    "7d",
    "14day"
]

def test_calendar_freqs():
    """
    测试不同频率格式的日历获取
    """
    print("\n=== 测试不同频率格式的日历获取 ===")
    
    # 只测试1d和day频率，其他频率可能没有日历文件
    test_calendar_freqs = ["1d", "day"]
    
    for freq in test_calendar_freqs:
        try:
            print(f"\n测试频率: {freq}")
            calendar = D.calendar(freq=freq)
            print(f"  ✓ 成功获取日历数据，长度: {len(calendar)}")
            print(f"  ✓ 日历数据前5条: {calendar[:5]}")
        except Exception as e:
            print(f"  ✗ 获取日历失败: {e}")
            print(f"  错误类型: {type(e).__name__}")

def test_features_freqs():
    """
    测试不同频率格式的features方法
    """
    print("\n=== 测试不同频率格式的features方法 ===")
    
    # 只测试1d和day频率，其他频率可能没有数据
    test_features_freqs = ["1d", "day"]
    
    for freq in test_features_freqs:
        try:
            print(f"\n测试频率: {freq}")
            df = D.features(
                ["btcusdt"],
                ["$open", "$high", "$low", "$close", "$volume"],
                start_time="2025-10-01",
                end_time="2025-10-05",
                freq=freq
            )
            print(f"  ✓ 成功获取数据，形状: {df.shape}")
            print(f"  ✓ 数据预览:")
            print(df.head())
        except Exception as e:
            print(f"  ✗ 获取数据失败: {e}")
            print(f"  错误类型: {type(e).__name__}")

def test_instruments_freqs():
    """
    测试不同频率格式的instruments方法
    """
    print("\n=== 测试不同频率格式的instruments方法 ===")
    
    # 只测试1d和day频率
    test_instruments_freqs = ["1d", "day"]
    
    for freq in test_instruments_freqs:
        try:
            print(f"\n测试频率: {freq}")
            # 获取所有可用的交易对
            instruments = D.instruments()
            print(f"  ✓ 成功获取交易对列表，数量: {len(instruments)}")
            
            # 测试list_instruments方法
            instrument_list = D.list_instruments(instruments=instruments, as_list=True, freq=freq)[:2]
            print(f"  ✓ 成功获取list_instruments，前2个交易对: {instrument_list}")
            
            # 测试组合使用
            if instrument_list:
                df = D.features(
                    instrument_list,
                    ["$open", "$high", "$low", "$close", "$volume"],
                    start_time="2025-10-01",
                    end_time="2025-10-03",
                    freq=freq
                )
                print(f"  ✓ 成功组合使用D.instruments()与D.features()，数据形状: {df.shape}")
        except Exception as e:
            print(f"  ✗ 测试失败: {e}")
            print(f"  错误类型: {type(e).__name__}")

def test_freq_str_parsing():
    """
    测试频率字符串解析
    """
    print("\n=== 测试频率字符串解析 ===")
    
    from qlib.utils.time import Freq

    from backend.qlib_integration.custom_freq import CustomFreq

    # 测试原始Freq和自定义Freq的解析
    for freq_str in test_freqs:
        try:
            # 测试自定义Freq
            freq_obj = CustomFreq(freq_str)
            print(f"\n频率字符串: {freq_str}")
            print(f"  ✓ 自定义Freq解析成功")
            print(f"  ✓ base: {freq_obj.base}, count: {freq_obj.count}")
            print(f"  ✓ str(Freq): {str(freq_obj)}")
            print(f"  ✓ repr(Freq): {repr(freq_obj)}")
            
            # 测试原始Freq
            from backend.qlib_integration.custom_freq import OriginalFreq
            original_freq_obj = OriginalFreq.parse(freq_str)
            print(f"  ✓ 原始Freq.parse(): {original_freq_obj}")
        except Exception as e:
            print(f"\n频率字符串: {freq_str}")
            print(f"  ✗ 解析失败: {e}")
            print(f"  错误类型: {type(e).__name__}")

def test_file_name_generation():
    """
    测试文件名生成
    """
    print("\n=== 测试文件名生成 ===")
    
    from qlib.data.storage.file_storage import FileCalendarStorage
    from qlib.utils.time import Freq

    # 创建一个测试用的FileCalendarStorage实例
    try:
        # 获取数据路径管理器
        from qlib.data.storage import DPM
        dpm = DPM(data_dir)
        
        for freq_str in test_freqs:
            try:
                print(f"\n频率: {freq_str}")
                
                # 测试字符串频率
                calendar_storage_str = FileCalendarStorage(dpm, "calendar", freq_str)
                file_name_str = calendar_storage_str.file_name
                uri_str = calendar_storage_str.uri
                print(f"  ✓ 字符串频率 - file_name: {file_name_str}")
                print(f"  ✓ 字符串频率 - uri: {uri_str}")
                
                # 测试Freq对象频率
                freq_obj = Freq(freq_str)
                calendar_storage_obj = FileCalendarStorage(dpm, "calendar", freq_obj)
                file_name_obj = calendar_storage_obj.file_name
                uri_obj = calendar_storage_obj.uri
                print(f"  ✓ Freq对象频率 - file_name: {file_name_obj}")
                print(f"  ✓ Freq对象频率 - uri: {uri_obj}")
                
                # 验证文件名是否正确
                if freq_str in ["1d", "day"]:
                    assert "1d.txt" in file_name_str or "1d_future.txt" in file_name_str, f"文件名应该包含1d.txt或1d_future.txt，实际是{file_name_str}"
                    print(f"  ✓ 文件名验证通过")
            except Exception as e:
                print(f"  ✗ 测试失败: {e}")
                print(f"  错误类型: {type(e).__name__}")
    except Exception as e:
        print(f"✗ 创建FileCalendarStorage实例失败: {e}")
        print(f"错误类型: {type(e).__name__}")

# 运行所有测试
def run_all_tests():
    """
    运行所有测试
    """
    print("\n=== 运行所有测试 ===")
    
    test_calendar_freqs()
    test_features_freqs()
    test_instruments_freqs()
    test_freq_str_parsing()
    test_file_name_generation()
    
    print("\n=== 所有测试完成 ===")

if __name__ == "__main__":
    run_all_tests()
