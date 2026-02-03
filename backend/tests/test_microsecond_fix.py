#!/usr/bin/env python3
"""
测试微秒时间戳修复
专门测试16位微秒时间戳的转换问题
"""

import os
import sys

import pandas as pd

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from collector.crypto.binance.collector import BinanceCollector


def test_microsecond_timestamp_fix():
    """
    测试微秒时间戳修复
    """
    print("开始测试微秒时间戳修复...")
    
    # 创建一个模拟的DataFrame，包含16位微秒时间戳（与日志中显示的格式一致）
    # 日志中的时间戳示例：1735689600000000
    mock_data = {
        'open_time': [1735689600000000, 1735776000000000, 1735862400000000],
        'open': [42000.0, 42500.0, 43000.0],
        'high': [43000.0, 43500.0, 44000.0],
        'low': [41000.0, 41500.0, 42000.0],
        'close': [42500.0, 43000.0, 43500.0],
        'volume': [100.0, 200.0, 300.0],
        'close_time': [1735776000000000, 1735862400000000, 1735948800000000],
        'quote_volume': [4250000.0, 8600000.0, 13050000.0],
        'count': [1000, 2000, 3000],
        'taker_buy_volume': [50.0, 100.0, 150.0],
        'taker_buy_quote_volume': [2125000.0, 4300000.0, 6525000.0],
        'ignore': [0, 0, 0]
    }
    
    df = pd.DataFrame(mock_data)
    print(f"模拟数据行数: {len(df)}")
    print(f"open_time值: {df['open_time'].tolist()}")
    print(f"open_time长度: {len(str(int(df['open_time'].iloc[0])))}位")
    
    # 测试修复后的转换逻辑
    print("\n测试修复后的时间戳转换逻辑...")
    
    # 复制修复后的转换逻辑进行测试
    def test_timestamp_conversion(df_test):
        """测试时间戳转换"""
        first_open_time = df_test['open_time'].iloc[0]
        timestamp_length = len(str(int(first_open_time)))
        
        print(f"第一个时间戳: {first_open_time}，长度: {timestamp_length}")
        
        df_test['date'] = pd.Series(dtype='datetime64[ns]')
        
        # 根据时间戳长度直接计算正确的单位和转换值
        try:
            if timestamp_length == 13:  # 毫秒
                df_test['date'] = pd.to_datetime(df_test['open_time'], unit='ms', errors='coerce')
            elif timestamp_length == 16:  # 微秒
                # 先将微秒转换为秒，再转换为datetime
                df_test['date'] = pd.to_datetime(df_test['open_time'] / 1000000, unit='s', errors='coerce')
            elif timestamp_length == 19:  # 纳秒
                df_test['date'] = pd.to_datetime(df_test['open_time'], unit='ns', errors='coerce')
            else:  # 其他长度，尝试多种单位
                print(f"时间戳长度 {timestamp_length} 不常见，尝试多种转换方法...")
                
                # 尝试直接转换（适用于已格式化的字符串）
                df_test['date'] = pd.to_datetime(df_test['open_time'], errors='coerce')
                valid_count = df_test['date'].notna().sum()
                
                if valid_count == 0:
                    # 尝试除以不同的系数转换为秒
                    for divisor in [1000, 1000000, 1000000000]:
                        df_test['date'] = pd.to_datetime(df_test['open_time'] / divisor, unit='s', errors='coerce')
                        valid_count = df_test['date'].notna().sum()
                        if valid_count > 0:
                            print(f"通过除以 {divisor} 转换成功，有效日期数量: {valid_count}")
                            break
        except Exception as e:
            print(f"时间戳转换异常: {e}")
            df_test['date'] = pd.to_datetime(df_test['open_time'], errors='coerce')
        
        valid_dates = df_test['date'].notna().sum()
        invalid_dates = df_test['date'].isna().sum()
        
        print(f"转换结果: 有效日期 {valid_dates} 个，无效日期 {invalid_dates} 个")
        
        if invalid_dates > 0:
            invalid_times = df_test[df_test['date'].isna()]['open_time'].tolist()
            print(f"无效时间戳值: {invalid_times}")
        
        return df_test
    
    # 执行测试
    result_df = test_timestamp_conversion(df.copy())
    
    # 打印转换结果
    print("\n转换结果:")
    print(result_df[['open_time', 'date']])
    
    # 检查是否所有时间戳都转换成功
    if result_df['date'].notna().all():
        print("\n✓ 所有微秒时间戳都成功转换！")
        return True
    else:
        print("\n✗ 仍有无效时间戳！")
        return False

def test_actual_collector_with_mock_data():
    """
    测试实际的collector类处理微秒时间戳
    """
    print("\n开始测试实际的collector类...")
    
    # 创建collector实例
    collector = BinanceCollector(
        save_dir='/tmp/test_binance',
        interval='1d',
        candle_type='spot'
    )
    
    # 创建模拟数据，模拟downloader返回的结果
    mock_data = {
        'open_time': [1735689600000000, 1735776000000000],
        'open': [42000.0, 42500.0],
        'high': [43000.0, 43500.0],
        'low': [41000.0, 41500.0],
        'close': [42500.0, 43000.0],
        'volume': [100.0, 200.0],
        'close_time': [1735776000000000, 1735862400000000],
        'quote_volume': [4250000.0, 8600000.0],
        'count': [1000, 2000],
        'taker_buy_volume': [50.0, 100.0],
        'taker_buy_quote_volume': [2125000.0, 4300000.0],
        'ignore': [0, 0]
    }
    
    mock_df = pd.DataFrame(mock_data)
    
    # 保存原始download方法
    original_download = collector.downloader.download
    
    try:
        # 替换download方法，返回模拟数据
        def mock_download(symbol, interval, start_date, end_date):
            print(f"模拟下载: {symbol} {interval} {start_date} {end_date}")
            return mock_df
        
        collector.downloader.download = mock_download
        
        # 调用get_data方法，使用正确的时间范围（模拟数据转换后是2025-01-01至2025-01-02）
        start_dt = pd.Timestamp('2025-01-01')
        end_dt = pd.Timestamp('2025-01-03')
        
        result = collector.get_data('BTCUSDT', '1d', start_dt, end_dt)
        
        print(f"\nget_data返回结果行数: {len(result)}")
        print(f"返回的列: {list(result.columns)}")
        
        if not result.empty:
            print("\n返回的数据:")
            print(result)
            print("\n✓ collector成功处理微秒时间戳！")
            return True
        else:
            print("\n✗ collector返回空数据！")
            return False
            
    finally:
        # 恢复原始download方法
        collector.downloader.download = original_download

if __name__ == "__main__":
    # 运行测试
    test1_passed = test_microsecond_timestamp_fix()
    test2_passed = test_actual_collector_with_mock_data()
    
    if test1_passed and test2_passed:
        print("\n✓ 所有测试通过！微秒时间戳修复成功！")
        sys.exit(0)
    else:
        print("\n✗ 测试失败！微秒时间戳修复存在问题！")
        sys.exit(1)
