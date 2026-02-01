#!/usr/bin/env python3
"""
测试 get_kline_data 方法返回的 DataFrame 结构
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from scripts.check_kline_health import KlineHealthChecker

if __name__ == "__main__":
    # 创建 KlineHealthChecker 实例
    checker = KlineHealthChecker()
    
    # 调用 get_kline_data 方法
    df = checker.get_kline_data(symbol="BTCUSDT", interval="15m")
    
    # 打印 DataFrame 结构
    print("DataFrame 列名:", df.columns.tolist())
    print("\nDataFrame 前 5 行:")
    print(df.head())
    
    # 检查是否包含 id 字段
    if 'id' in df.columns:
        print("\n包含 id 字段")
        print("id 列前 5 个值:", df['id'].head().tolist())
    else:
        print("\n不包含 id 字段")
    
    # 检查重复记录
    duplicate_index = df.duplicated(subset=['date'], keep=False)
    if duplicate_index.any():
        print(f"\n发现 {duplicate_index.sum()} 条重复记录")
        print("前 5 条重复记录:")
        print(df[duplicate_index].head())
    else:
        print("\n没有发现重复记录")
