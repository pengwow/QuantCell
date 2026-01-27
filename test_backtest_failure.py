#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试回测失败原因分析脚本
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# 直接导入BacktestService，避免导入__init__.py中的routes模块
sys.path.append(str(project_root / "backend"))
from backtest.service import BacktestService


def test_backtest_failure_analysis():
    """
    测试回测失败原因分析
    """
    print("开始分析回测失败原因...")
    
    # 初始化回测服务
    backtest_service = BacktestService()
    
    # 测试失败的回测ID
    failed_backtest_id = "aaaf99f3-5216-4e92-8532-9f0ba50c048f"
    
    print(f"\n分析回测ID: {failed_backtest_id}")
    
    # 加载回测结果
    result = backtest_service.load_backtest_result(failed_backtest_id)
    
    if result:
        print(f"\n回测结果状态: {result.get('status')}")
        print(f"回测结果消息: {result.get('message')}")
        
        # 检查货币对回测结果
        if "currencies" in result:
            print(f"\n货币对回测结果:")
            for symbol, currency_result in result["currencies"].items():
                print(f"\n  货币对: {symbol}")
                print(f"    状态: {currency_result.get('status')}")
                print(f"    消息: {currency_result.get('message')}")
                
                # 检查是否有详细的错误信息
                if "error" in currency_result:
                    print(f"    错误: {currency_result.get('error')}")
        
        # 检查是否有其他错误信息
        if "error" in result:
            print(f"\n回测错误: {result.get('error')}")
        
        # 检查是否有异常信息
        if "exception" in result:
            print(f"\n回测异常: {result.get('exception')}")
    else:
        print(f"\n无法加载回测结果文件: {failed_backtest_id}")
    
    # 测试数据获取功能
    print("\n\n测试数据获取功能...")
    
    try:
        from collector.services.data_service import DataService
        data_service = DataService()
        
        # 测试获取BTC/USDT的K线数据
        print("\n测试获取BTC/USDT的K线数据...")
        btc_data = data_service.get_kline_data(
            symbol="BTC/USDT",
            interval="1h",
            limit=100
        )
        
        if btc_data is not None and len(btc_data) > 0:
            print(f"成功获取BTC/USDT的K线数据，共 {len(btc_data)} 条记录")
            print(f"数据列: {list(btc_data.columns) if hasattr(btc_data, 'columns') else 'N/A'}")
            print(f"前5条数据:")
            print(btc_data.head() if hasattr(btc_data, 'head') else btc_data[:5])
        else:
            print(f"无法获取BTC/USDT的K线数据")
            print(f"返回数据: {btc_data}")
        
        # 测试获取ETH/USDT的K线数据
        print("\n测试获取ETH/USDT的K线数据...")
        eth_data = data_service.get_kline_data(
            symbol="ETH/USDT",
            interval="1h",
            limit=100
        )
        
        if eth_data is not None and len(eth_data) > 0:
            print(f"成功获取ETH/USDT的K线数据，共 {len(eth_data)} 条记录")
            print(f"数据列: {list(eth_data.columns) if hasattr(eth_data, 'columns') else 'N/A'}")
            print(f"前5条数据:")
            print(eth_data.head() if hasattr(eth_data, 'head') else eth_data[:5])
        else:
            print(f"无法获取ETH/USDT的K线数据")
            print(f"返回数据: {eth_data}")
        
    except Exception as e:
        print(f"\n数据获取测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n\n分析完成!")


if __name__ == "__main__":
    test_backtest_failure_analysis()