#!/usr/bin/env python3
"""
测试缺口检测功能
"""

import sys
import os
import tempfile
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from collector.base.base_collector import BaseCollector


class MockCollector(BaseCollector):
    """
    模拟收集器，用于测试缺口检测功能
    """
    
    def get_instrument_list(self):
        """获取标的列表"""
        return ["TEST"]
    
    def normalize_symbol(self, symbol):
        """标准化标的代码"""
        return symbol
    
    def get_data(self, symbol, interval, start_datetime, end_datetime, progress_callback=None):
        """模拟获取数据"""
        print(f"模拟下载数据: {symbol}, {interval}, {start_datetime} 至 {end_datetime}")
        # 生成模拟数据
        freq = self._get_interval_freq()
        date_range = pd.date_range(start=start_datetime, end=end_datetime, freq=freq)
        
        # 生成模拟的OHLCV数据
        data = {
            'date': date_range,
            'open': [100.0] * len(date_range),
            'high': [101.0] * len(date_range),
            'low': [99.0] * len(date_range),
            'close': [100.5] * len(date_range),
            'volume': [1000.0] * len(date_range)
        }
        
        return pd.DataFrame(data)


def test_gap_detection():
    """
    测试缺口检测功能
    """
    print("开始测试缺口检测功能...")
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        
        # 创建模拟数据文件，包含缺口
        mock_symbol = "TEST"
        mock_file_path = temp_dir_path / f"{mock_symbol}.csv"
        
        # 生成带有缺口的数据
        # 第一部分：2025-01-01 至 2025-01-10
        dates1 = pd.date_range(start="2025-01-01", end="2025-01-10", freq="D")
        # 第二部分：2025-01-20 至 2025-01-30
        dates2 = pd.date_range(start="2025-01-20", end="2025-01-30", freq="D")
        
        # 合并日期
        all_dates = dates1.union(dates2)
        
        # 生成模拟数据
        data = {
            'date': all_dates,
            'open': [100.0] * len(all_dates),
            'high': [101.0] * len(all_dates),
            'low': [99.0] * len(all_dates),
            'close': [100.5] * len(all_dates),
            'volume': [1000.0] * len(all_dates),
            'symbol': [mock_symbol] * len(all_dates)
        }
        
        mock_df = pd.DataFrame(data)
        mock_df['date'] = mock_df['date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        mock_df.to_csv(mock_file_path, index=False)
        
        print(f"创建模拟数据文件: {mock_file_path}")
        print(f"模拟数据日期范围: {dates1.min()} 至 {dates1.max()}，然后 {dates2.min()} 至 {dates2.max()}")
        print(f"模拟数据缺口: 2025-01-11 至 2025-01-19")
        
        # 创建收集器
        collector = MockCollector(
            save_dir=temp_dir_path,
            start="2025-01-01",
            end="2025-01-30",
            interval="1d",
            mode="inc"
        )
        
        # 测试缺口检测
        print("\n测试缺口检测...")
        
        # 读取现有数据
        existing_df = pd.read_csv(mock_file_path)
        existing_df['date'] = pd.to_datetime(existing_df['date'])
        existing_dates = pd.DatetimeIndex(existing_df['date'])
        
        # 计算缺失范围
        missing_ranges = collector._calculate_missing_ranges(existing_dates)
        
        print(f"检测到的缺失范围数量: {len(missing_ranges)}")
        for i, (start, end) in enumerate(missing_ranges):
            print(f"缺失范围 {i+1}: {start} 至 {end}")
        
        # 验证结果
        expected_gap_count = 1
        expected_gap_start = pd.Timestamp("2025-01-11")
        expected_gap_end = pd.Timestamp("2025-01-19")
        
        if len(missing_ranges) == expected_gap_count:
            gap_start, gap_end = missing_ranges[0]
            if gap_start == expected_gap_start and gap_end == expected_gap_end:
                print("✓ 缺口检测成功！")
                print(f"  检测到预期的缺失范围: {gap_start} 至 {gap_end}")
                
                # 测试 _simple_collector 方法
                print("\n测试 _simple_collector 方法...")
                result = collector._simple_collector("TEST")
                print(f"_simple_collector 结果: {result}")
                
                # 验证合并后的数据
                merged_df = pd.read_csv(mock_file_path)
                merged_df['date'] = pd.to_datetime(merged_df['date'])
                merged_dates = pd.DatetimeIndex(merged_df['date'])
                
                # 生成完整的日期范围
                complete_range = pd.date_range(start="2025-01-01", end="2025-01-30", freq="D")
                
                # 检查是否所有日期都存在
                if merged_dates.equals(complete_range):
                    print("✓ 数据合并成功！所有日期都已包含在文件中")
                    print(f"  合并后的数据包含 {len(merged_dates)} 条记录")
                    return True
                else:
                    print("✗ 数据合并失败！仍有缺失日期")
                    missing = complete_range.difference(merged_dates)
                    print(f"  仍然缺失 {len(missing)} 个日期")
                    return False
            else:
                print(f"✗ 缺口检测失败！预期的缺失范围是 {expected_gap_start} 至 {expected_gap_end}")
                return False
        else:
            print(f"✗ 缺口检测失败！预期检测到 {expected_gap_count} 个缺口，实际检测到 {len(missing_ranges)} 个")
            return False


if __name__ == "__main__":
    test_gap_detection()
