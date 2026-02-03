#!/usr/bin/env python3
# 测试下载数据格式

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from exchange.binance.downloader import BinanceDownloader


def test_download_data_format():
    """测试下载数据格式"""
    print("开始测试下载数据格式...")
    
    try:
        # 创建BinanceDownloader实例
        downloader = BinanceDownloader(candle_type='spot')
        
        # 下载少量数据进行测试
        print("\n下载ETHUSDT 1d数据...")
        df = downloader.download("ETHUSDT", "1d", "2024-01-01", "2024-01-02")
        
        print(f"\n下载数据行数: {len(df)}")
        print("下载数据:")
        print(df)
        
        print("\n数据类型:")
        print(df.dtypes)
        
        # 检查open_time列的值
        print("\nopen_time列的值:")
        for i, open_time in enumerate(df['open_time']):
            print(f"{i}: {open_time} (类型: {type(open_time).__name__})")
        
        # 测试pd.to_datetime转换
        print("\n测试pd.to_datetime转换...")
        import pandas as pd

        # 测试转换
        df['date'] = pd.to_datetime(df['open_time'], unit='ms', errors='coerce')
        print("转换后的数据:")
        print(df)
        
        # 检查转换结果
        print("\n转换结果检查:")
        print(f"有效日期数量: {df['date'].notna().sum()}")
        print(f"无效日期数量: {df['date'].isna().sum()}")
        
        # 测试不同的转换参数
        print("\n测试不同的转换参数...")
        
        # 测试不使用unit参数
        df['date_no_unit'] = pd.to_datetime(df['open_time'], errors='coerce')
        print("不使用unit参数转换结果:")
        print(df[['open_time', 'date_no_unit']])
        
        # 测试转换为int64
        print("\n测试转换为int64...")
        df['open_time_int'] = pd.to_numeric(df['open_time'], errors='coerce')
        print("转换为int64结果:")
        print(df[['open_time', 'open_time_int']])
        
        # 测试使用int64值进行转换
        print("\n测试使用int64值进行转换...")
        df['date_from_int'] = pd.to_datetime(df['open_time_int'], unit='ms', errors='coerce')
        print("使用int64值转换结果:")
        print(df[['open_time', 'open_time_int', 'date_from_int']])
        
        print("\n✓ 数据格式测试完成！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_download_data_format()
    sys.exit(0 if success else 1)
