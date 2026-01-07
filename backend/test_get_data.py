#!/usr/bin/env python3
"""
测试get_data.py脚本的功能
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.scripts.get_data import GetData


def test_get_data_class():
    """测试GetData类的基本功能"""
    print("测试GetData类的基本功能...")
    
    try:
        # 实例化GetData类
        get_data = GetData()
        print("✓ GetData类实例化成功")
        
        # 检查crypto方法是否存在
        if hasattr(get_data, 'crypto'):
            print("✓ crypto方法存在")
        else:
            print("✗ crypto方法不存在")
            return False
        
        # 检查crypto_binance方法是否存在
        if hasattr(get_data, 'crypto_binance'):
            print("✓ crypto_binance方法存在")
        else:
            print("✗ crypto_binance方法不存在")
            return False
        
        # 检查crypto_okx方法是否存在
        if hasattr(get_data, 'crypto_okx'):
            print("✓ crypto_okx方法存在")
        else:
            print("✗ crypto_okx方法不存在")
            return False
        
        # 检查_write_to_database方法是否存在
        if hasattr(get_data, '_write_to_database'):
            print("✓ _write_to_database方法存在")
        else:
            print("✗ _write_to_database方法不存在")
            return False
        
        print("所有测试通过！")
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


if __name__ == "__main__":
    test_get_data_class()
