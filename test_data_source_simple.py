#!/usr/bin/env python3
"""
简单测试脚本，验证data_source字段是否正确设置
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collector.db.database import init_database_config, SessionLocal, engine
from collector.db.models import CryptoSpotKline, CryptoFutureKline, StockKline
from collector.db.migrations import run_migrations


def test_database_migration():
    """测试数据库迁移，验证data_source字段是否添加成功"""
    print("开始测试数据库迁移...")
    
    try:
        # 运行迁移脚本
        run_migrations()
        print("数据库迁移执行成功!")
        
    except Exception as e:
        print(f"数据库迁移执行失败: {e}")
        import traceback
        traceback.print_exc()


def test_model_definition():
    """测试模型定义，验证data_source字段是否存在"""
    print("\n开始测试模型定义...")
    
    # 检查CryptoSpotKline模型
    print("检查CryptoSpotKline模型...")
    has_data_source = hasattr(CryptoSpotKline, 'data_source')
    print(f"CryptoSpotKline.has_data_source: {has_data_source}")
    
    # 检查CryptoFutureKline模型
    print("\n检查CryptoFutureKline模型...")
    has_data_source = hasattr(CryptoFutureKline, 'data_source')
    print(f"CryptoFutureKline.has_data_source: {has_data_source}")
    
    # 检查StockKline模型
    print("\n检查StockKline模型...")
    has_data_source = hasattr(StockKline, 'data_source')
    print(f"StockKline.has_data_source: {has_data_source}")


def test_table_creation():
    """测试表创建，验证data_source字段是否正确添加到表结构"""
    print("\n开始测试表创建...")
    
    # 初始化数据库配置
    init_database_config()
    
    # 创建所有表
    from collector.db.models import Base
    Base.metadata.create_all(bind=engine)
    print("所有表创建成功!")
    
    # 检查表结构
    print("\n检查表结构...")
    
    # 检查crypto_spot_klines表
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    # 检查crypto_spot_klines表的列
    print("检查crypto_spot_klines表的列...")
    columns = inspector.get_columns('crypto_spot_klines')
    for column in columns:
        if column['name'] == 'data_source':
            print(f"找到data_source列: {column}")
    
    # 检查crypto_future_klines表的列
    print("\n检查crypto_future_klines表的列...")
    columns = inspector.get_columns('crypto_future_klines')
    for column in columns:
        if column['name'] == 'data_source':
            print(f"找到data_source列: {column}")
    
    # 检查stock_klines表的列
    print("\n检查stock_klines表的列...")
    columns = inspector.get_columns('stock_klines')
    for column in columns:
        if column['name'] == 'data_source':
            print(f"找到data_source列: {column}")


def test_data_insertion():
    """测试数据插入，验证data_source字段是否正确设置"""
    print("\n开始测试数据插入...")
    
    # 初始化数据库配置
    init_database_config()
    
    # 创建数据库会话
    with SessionLocal() as db:
        try:
            # 创建测试数据
            from datetime import datetime
            import time
            
            # 创建一个测试K线数据
            test_kline = CryptoSpotKline(
                symbol="BTCUSDT",
                interval="1d",
                date=datetime.utcnow(),
                open="10000.0",
                high="11000.0",
                low="9000.0",
                close="10500.0",
                volume="100.0",
                unique_kline=f"BTCUSDT_1d_{int(time.time() * 1000)}",
                data_source="ccxt_binance"
            )
            
            # 插入数据
            db.add(test_kline)
            db.commit()
            print("测试数据插入成功!")
            
            # 查询数据，验证data_source字段
            queried_kline = db.query(CryptoSpotKline).filter(
                CryptoSpotKline.symbol == "BTCUSDT"
            ).first()
            
            if queried_kline:
                print(f"查询到的K线数据: symbol={queried_kline.symbol}, data_source={queried_kline.data_source}")
                print(f"data_source字段设置正确: {queried_kline.data_source == 'ccxt_binance'}")
            else:
                print("未查询到插入的测试数据")
                
        except Exception as e:
            print(f"数据插入测试失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()


if __name__ == "__main__":
    print("=== 测试data_source字段设置 ===")
    
    # 测试数据库迁移
    test_database_migration()
    
    # 测试模型定义
    test_model_definition()
    
    # 测试表创建
    test_table_creation()
    
    # 测试数据插入
    test_data_insertion()
    
    print("\n=== 测试完成 ===")
