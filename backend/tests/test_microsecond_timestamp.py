#!/usr/bin/env python3
# 测试微秒级时间戳转换

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

import pandas as pd

from exchange.binance.collector import BinanceCollector


def test_microsecond_timestamp():
    """测试微秒级时间戳转换"""
    print("开始测试微秒级时间戳转换...")
    
    try:
        # 创建测试数据，包含微秒级时间戳
        test_data = {
            'open_time': [1735689600000000, 1735776000000000, 1735862400000000],  # 微秒级时间戳
            'open': [42000, 43000, 44000],
            'high': [43000, 44000, 45000],
            'low': [41000, 42000, 43000],
            'close': [43000, 44000, 45000],
            'volume': [100, 200, 300],
            'close_time': [1735776000000000, 1735862400000000, 1735948800000000],
            'quote_volume': [4300000, 8800000, 13500000],
            'count': [1000, 2000, 3000],
            'taker_buy_volume': [50, 100, 150],
            'taker_buy_quote_volume': [2150000, 4400000, 6750000],
            'ignore': [0, 0, 0]
        }
        
        # 创建DataFrame
        df = pd.DataFrame(test_data)
        
        print("\n创建测试数据...")
        print(f"原始数据行数: {len(df)}")
        print("测试数据:")
        print(df)
        
        print("\n数据类型:")
        print(df.dtypes)
        
        # 测试pd.to_datetime转换
        print("\n测试pd.to_datetime转换...")
        
        # 尝试不同的单位
        for unit in ['ms', 'us', 'ns']:
            df[f'date_{unit}'] = pd.to_datetime(df['open_time'], unit=unit, errors='coerce')
            valid_count = df[f'date_{unit}'].notna().sum()
            print(f"单位 {unit}: 有效日期 {valid_count} 个，无效日期 {len(df) - valid_count} 个")
        
        print("\n转换结果:")
        print(df[['open_time', 'date_ms', 'date_us', 'date_ns']])
        
        # 测试BinanceCollector.get_data方法
        print("\n测试BinanceCollector.get_data方法...")
        
        # 创建BinanceCollector实例
        collector = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-02",
            interval="1d"
        )
        
        # 模拟downloader.download返回测试数据
        from unittest.mock import patch
        
        with patch('backend.collector.crypto.binance.downloader.BinanceDownloader.download') as mock_download:
            # 设置mock返回值
            mock_download.return_value = df
            
            # 创建测试时间范围
            start_datetime = pd.Timestamp("2024-01-01")
            end_datetime = pd.Timestamp("2024-01-02")
            
            # 调用get_data方法
            result_df = collector.get_data("BTCUSDT", "1d", start_datetime, end_datetime)
            
            print(f"\nget_data方法返回数据行数: {len(result_df)}")
            print("返回数据:")
            print(result_df)
        
        print("\n✓ 微秒级时间戳转换测试完成！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_microsecond_timestamp()
    sys.exit(0 if success else 1)
