#!/usr/bin/env python3
# 测试实际下载数据，验证无效时间戳处理

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

from backend.collector.crypto.binance.collector import BinanceCollector


def test_actual_download():
    """测试实际下载数据，验证无效时间戳处理"""
    print("开始测试实际下载数据...")
    
    try:
        # 创建BinanceCollector实例
        collector = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-02",
            interval="1d",
            symbols=["ETHUSDT"],
            max_workers=1
        )
        
        # 执行数据收集，不转换为QLib格式
        result = collector.collect_data(convert_to_qlib=False)
        
        print(f"\n数据收集结果: {result}")
        print("✓ 实际下载测试完成！")
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_actual_download()
    sys.exit(0 if success else 1)
