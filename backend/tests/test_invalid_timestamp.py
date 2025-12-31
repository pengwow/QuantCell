#!/usr/bin/env python3
# 测试无效时间戳处理

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

import pandas as pd

from backend.collector.crypto.binance.collector import BinanceCollector
from backend.collector.crypto.binance.downloader import BinanceDownloader


def test_invalid_timestamp():
    """测试无效时间戳处理"""
    print("开始测试无效时间戳处理...")
    
    try:
        # 创建测试数据，包含无效时间戳
        test_data = {
            'open_time': [1609459200000, 1609545600000, 1609632000000, 1000000000000000000000],  # 最后一个是无效时间戳
            'open': [30000, 31000, 32000, 33000],
            'high': [31000, 32000, 33000, 34000],
            'low': [29000, 30000, 31000, 32000],
            'close': [31000, 32000, 33000, 34000],
            'volume': [100, 200, 300, 400],
            'close_time': [1609545599999, 1609631999999, 1609718399999, 1000000000000000000000],
            'quote_volume': [3100000, 6400000, 9900000, 13600000],
            'count': [1000, 2000, 3000, 4000],
            'taker_buy_volume': [50, 100, 150, 200],
            'taker_buy_quote_volume': [1550000, 3200000, 4950000, 6800000],
            'ignore': [0, 0, 0, 0]
        }
        
        # 创建DataFrame
        df = pd.DataFrame(test_data)
        
        print("\n创建测试数据...")
        print(f"原始数据行数: {len(df)}")
        print("测试数据:")
        print(df)
        
        # 测试pd.to_datetime处理无效时间戳
        print("\n测试pd.to_datetime处理无效时间戳...")
        df['date'] = pd.to_datetime(df['open_time'], unit='ms', errors='coerce')
        print("处理后的数据:")
        print(df)
        
        # 过滤无效时间戳
        filtered_df = df.dropna(subset=['date'])
        print(f"\n过滤后的数据行数: {len(filtered_df)}")
        print("过滤后的数据:")
        print(filtered_df)
        
        # 测试BinanceCollector.get_data方法
        print("\n测试BinanceCollector.get_data方法...")
        
        # 创建BinanceCollector实例
        collector = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-02",
            interval="1d"
        )
        
        # 创建测试时间范围
        start_datetime = pd.Timestamp("2024-01-01")
        end_datetime = pd.Timestamp("2024-01-02")
        
        # 模拟downloader.download返回测试数据
        from unittest.mock import patch
        
        with patch('backend.collector.crypto.binance.downloader.BinanceDownloader.download') as mock_download:
            # 设置mock返回值
            mock_download.return_value = df
            
            # 调用get_data方法
            result_df = collector.get_data("ETHUSDT", "1d", start_datetime, end_datetime)
            
            print(f"\nget_data方法返回数据行数: {len(result_df)}")
            print("get_data方法返回数据:")
            print(result_df)
        
        print("\n✓ 无效时间戳处理测试完成！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_invalid_timestamp()
    sys.exit(0 if success else 1)
