#!/usr/bin/env python3
"""
测试K线工厂类的功能，特别是当数据库中没有数据时从ccxt获取数据的功能
"""

import sys
import os
from sqlalchemy.orm import Session

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collector.db.database import get_db
session = next(get_db())

from collector.services.kline_factory import KlineDataFactory

def test_crypto_spot_kline_fetcher():
    """测试加密货币现货K线数据获取器"""
    print("\n=== 测试加密货币现货K线数据获取器 ===")
    
    # 创建加密货币现货K线数据获取器
    factory = KlineDataFactory()
    fetcher = factory.create_fetcher("crypto", "spot")
    
    # 测试一个可能不存在于数据库中的交易对
    symbol = "BTC/USDT"
    interval = "1m"
    limit = 10
    
    print(f"从数据库获取K线数据: symbol={symbol}, interval={interval}, limit={limit}")
    result = fetcher.fetch_kline_data(
        db=session,
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    
    print(f"结果: success={result['success']}, message={result['message']}, data_count={len(result['kline_data'])}")
    
    if result['kline_data']:
        print("数据示例:")
        for kline in result['kline_data'][:3]:
            print(f"  {kline}")
    else:
        print("未获取到任何K线数据")

def test_crypto_future_kline_fetcher():
    """测试加密货币合约K线数据获取器"""
    print("\n=== 测试加密货币合约K线数据获取器 ===")
    
    # 创建加密货币合约K线数据获取器
    factory = KlineDataFactory()
    fetcher = factory.create_fetcher("crypto", "future")
    
    # 测试一个可能不存在于数据库中的交易对
    symbol = "BTC/USDT"
    interval = "1m"
    limit = 10
    
    print(f"从数据库获取K线数据: symbol={symbol}, interval={interval}, limit={limit}")
    result = fetcher.fetch_kline_data(
        db=session,
        symbol=symbol,
        interval=interval,
        limit=limit
    )
    
    print(f"结果: success={result['success']}, message={result['message']}, data_count={len(result['kline_data'])}")
    
    if result['kline_data']:
        print("数据示例:")
        for kline in result['kline_data'][:3]:
            print(f"  {kline}")
    else:
        print("未获取到任何K线数据")

if __name__ == "__main__":
    test_crypto_spot_kline_fetcher()
    test_crypto_future_kline_fetcher()
    print("\n=== 测试完成 ===")
