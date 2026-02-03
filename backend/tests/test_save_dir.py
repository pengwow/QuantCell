#!/usr/bin/env python3
# 测试save_dir路径获取逻辑

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from collector.scripts.get_data import GetData


def test_save_dir():
    """测试save_dir路径获取逻辑"""
    print("开始测试save_dir路径获取逻辑...")
    
    try:
        # 创建GetData实例
        get_data = GetData()
        
        # 测试crypto_binance方法，不指定save_dir参数
        print("\n测试crypto_binance方法，不指定save_dir参数...")
        # 只测试save_dir获取逻辑，不实际执行下载
        # 重写collect_data方法，避免实际下载
        from unittest.mock import patch
        
        with patch('backend.collector.crypto.binance.collector.BinanceCollector.collect_data') as mock_collect:
            # 设置mock返回值
            mock_collect.return_value = None
            
            # 调用方法，不指定save_dir
            get_data.crypto_binance(
                start="2024-01-01",
                end="2024-01-02",
                interval="1d",
                symbols=["BTCUSDT"],
                max_workers=1
            )
            
        print("\n✓ crypto_binance方法测试完成")
        
        # 测试crypto_okx方法，不指定save_dir参数
        print("\n测试crypto_okx方法，不指定save_dir参数...")
        
        with patch('backend.collector.crypto.okx.collector.OKXCollector.collect_data') as mock_collect:
            # 设置mock返回值
            mock_collect.return_value = None
            
            # 调用方法，不指定save_dir
            get_data.crypto_okx(
                start="2024-01-01",
                end="2024-01-02",
                interval="1d",
                symbols=["BTC-USDT"],
                max_workers=1
            )
            
        print("\n✓ crypto_okx方法测试完成")
        
        # 测试stock方法，不指定save_dir参数
        print("\n测试stock方法，不指定save_dir参数...")
        get_data.stock(
            exchange="test",
            start="2024-01-01",
            end="2024-01-02",
            interval="1d"
        )
        
        print("\n✓ stock方法测试完成")
        
        print("\n所有测试完成！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_save_dir()
    sys.exit(0 if success else 1)
