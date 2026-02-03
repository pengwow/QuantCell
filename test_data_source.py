#!/usr/bin/env python3
"""
测试数据采集功能，验证data_source字段是否正确设置
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from collector.db.database import init_database_config, SessionLocal, engine
from collector.services.kline_factory import KlineDataFactory


def test_data_collection():
    """测试数据采集功能"""
    print("开始测试数据采集功能...")
    
    # 初始化数据库配置
    init_database_config()
    
    # 创建数据库会话
    with SessionLocal() as db:
        try:
            # 创建K线数据获取器
            factory = KlineDataFactory()
            fetcher = factory.create_fetcher(market_type="crypto", crypto_type="spot")
            
            # 测试获取K线数据
            print("正在获取BTCUSDT的K线数据...")
            result = fetcher.fetch_kline_data(
                db=db,
                symbol="BTCUSDT",
                interval="1d",
                limit=10
            )
            
            print(f"获取结果: success={result['success']}, message={result['message']}")
            print(f"获取到{len(result['kline_data'])}条K线数据")
            
            # 检查数据是否包含data_source字段
            print("\n检查数据库中的data_source字段...")
            
            # 直接查询数据库
            from collector.db.models import CryptoSpotKline
            
            # 查询最近的K线数据
            recent_klines = db.query(CryptoSpotKline).filter(
                CryptoSpotKline.symbol == "BTCUSDT",
                CryptoSpotKline.interval == "1d"
            ).order_by(CryptoSpotKline.date.desc()).limit(5).all()
            
            print(f"查询到{len(recent_klines)}条最近的K线数据")
            
            for kline in recent_klines:
                print(f"日期: {kline.date}, 数据源: {kline.data_source}")
            
            print("\n测试完成!")
            
        except Exception as e:
            print(f"测试过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()


if __name__ == "__main__":
    test_data_collection()
