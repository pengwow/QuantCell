#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
详细诊断回测数据获取问题的脚本
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


def test_data_fetch_diagnostics():
    """
    详细诊断数据获取问题
    """
    print("开始诊断数据获取问题...")
    
    # 初始化数据库连接
    from collector.db.database import SessionLocal, init_database_config
    init_database_config()
    db = SessionLocal()
    
    try:
        # 创建带有数据库会话的DataService
        from collector.services.data_service import DataService
        data_service = DataService(db)
        
        print(f"数据库会话已初始化: {data_service.db is not None}")
        print(f"数据库会话类型: {type(data_service.db)}")
        
        # 测试获取BTC/USDT的K线数据
        print("\n测试获取BTC/USDT的K线数据...")
        
        result = data_service.get_kline_data(
            symbol="BTC/USDT",
            interval="1h",
            start_time="2024-01-01 00:00:00",
            end_time="2024-01-31 23:59:59"
        )
        
        print(f"返回结果类型: {type(result)}")
        print(f"返回结果键: {result.keys() if isinstance(result, dict) else 'N/A'}")
        
        if isinstance(result, dict):
            print(f"success: {result.get('success')}")
            print(f"message: {result.get('message')}")
            
            kline_data = result.get('kline_data', [])
            print(f"kline_data类型: {type(kline_data)}")
            print(f"kline_data长度: {len(kline_data) if hasattr(kline_data, '__len__') else 'N/A'}")
            
            if len(kline_data) > 0:
                print(f"前3条数据:")
                for i, item in enumerate(kline_data[:3]):
                    print(f"  {i+1}: {item}")
            else:
                print("kline_data为空!")
                
                # 检查数据库中是否有数据
                print("\n检查数据库中的数据...")
                from collector.db.models import CryptoSpotKline
                
                count = db.query(CryptoSpotKline).filter_by(symbol="BTCUSDT").count()
                print(f"数据库中BTCUSDT的K线数据条数: {count}")
                
                if count > 0:
                    sample = db.query(CryptoSpotKline).filter_by(symbol="BTCUSDT").first()
                    print(f"样本数据: {sample}")
        
        # 测试获取ETH/USDT的K线数据
        print("\n测试获取ETH/USDT的K线数据...")
        
        result = data_service.get_kline_data(
            symbol="ETH/USDT",
            interval="1h",
            start_time="2024-01-01 00:00:00",
            end_time="2024-01-31 23:59:59"
        )
        
        print(f"返回结果类型: {type(result)}")
        print(f"返回结果键: {result.keys() if isinstance(result, dict) else 'N/A'}")
        
        if isinstance(result, dict):
            print(f"success: {result.get('success')}")
            print(f"message: {result.get('message')}")
            
            kline_data = result.get('kline_data', [])
            print(f"kline_data类型: {type(kline_data)}")
            print(f"kline_data长度: {len(kline_data) if hasattr(kline_data, '__len__') else 'N/A'}")
            
            if len(kline_data) > 0:
                print(f"前3条数据:")
                for i, item in enumerate(kline_data[:3]):
                    print(f"  {i+1}: {item}")
            else:
                print("kline_data为空!")
                
                # 检查数据库中是否有数据
                print("\n检查数据库中的数据...")
                from collector.db.models import CryptoSpotKline
                
                count = db.query(CryptoSpotKline).filter_by(symbol="ETHUSDT").count()
                print(f"数据库中ETHUSDT的K线数据条数: {count}")
                
                if count > 0:
                    sample = db.query(CryptoSpotKline).filter_by(symbol="ETHUSDT").first()
                    print(f"样本数据: {sample}")
        
        # 检查回测配置中的货币对格式
        print("\n检查货币对格式...")
        
        test_symbols = ["BTC/USDT", "BTCUSDT", "ETH/USDT", "ETHUSDT"]
        
        for symbol in test_symbols:
            print(f"\n测试货币对: {symbol}")
            
            result = data_service.get_kline_data(
                symbol=symbol,
                interval="1h",
                limit=10
            )
            
            if isinstance(result, dict):
                kline_data = result.get('kline_data', [])
                print(f"  数据条数: {len(kline_data) if hasattr(kline_data, '__len__') else 'N/A'}")
                print(f"  成功: {result.get('success')}")
                print(f"  消息: {result.get('message')}")
        
    except Exception as e:
        print(f"\n诊断失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
    
    print("\n\n诊断完成!")


if __name__ == "__main__":
    test_data_fetch_diagnostics()