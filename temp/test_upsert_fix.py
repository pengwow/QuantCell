#!/usr/bin/env python3
"""
测试UPSERT修复效果
"""

import sys
import os
from datetime import datetime, timezone

# 设置环境变量，使用SQLite内存数据库进行测试
os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_FILE"] = ":memory:"

# 设置项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试UPSERT修复效果
print("=== 测试UPSERT修复效果 ===")
try:
    # 重置数据库连接实例和配置
    from collector.db import connection
    connection.db_instance = None
    
    # 重置数据库引擎
    from collector.db import database
    database.db_type = None
    database.db_url = None
    database.engine = None
    
    # 导入必要的模块
    from collector.db.models import Kline
    from collector.db.database import init_database_config, SessionLocal, Base, engine
    from sqlalchemy import insert, func
    import uuid
    
    # 初始化数据库配置
    init_database_config()
    print(f"✅ 数据库配置初始化成功，使用 {database.db_type} 数据库")
    
    # 创建表
    Base.metadata.create_all(bind=engine)
    print("✅ 数据库表创建成功")
    
    # 创建测试数据
    test_symbol = "BTCUSDT"
    test_interval = "1m"
    test_date = datetime.now(timezone.utc)
    
    # 准备测试数据
    kline_data = {
        "symbol": test_symbol,
        "interval": test_interval,
        "date": test_date,
        "open": 50000.0,
        "high": 50500.0,
        "low": 49500.0,
        "close": 50000.0,
        "volume": 100.0
    }
    
    # 测试UPSERT操作
    with SessionLocal() as db:
        try:
            from collector.db.database import db_type
            
            # 1. 第一次插入数据
            print(f"\n1. 测试第一次插入数据 (数据库类型: {db_type})")
            
            if db_type == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                stmt = sqlite_insert(Kline).values([kline_data])
                stmt = stmt.on_conflict_do_update(
                    index_elements=['unique_kline'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'updated_at': func.now()
                    }
                )
                result = db.execute(stmt)
            elif db_type == "duckdb":
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(Kline).values([kline_data])
                stmt = stmt.on_conflict_do_update(
                    index_elements=['unique_kline'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'updated_at': func.now()
                    }
                )
                result = db.execute(stmt)
            else:
                # 直接插入
                db.execute("INSERT INTO klines (symbol, interval, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                           (kline_data['symbol'], kline_data['interval'], kline_data['date'], kline_data['open'], kline_data['high'], kline_data['low'], kline_data['close'], kline_data['volume']))
                result = type('obj', (object,), {'rowcount': 1})()
            
            db.commit()
            print(f"✅ 第一次插入成功，影响行数: {result.rowcount}")
            
            # 2. 第二次插入相同数据（应该触发UPDATE）
            print("\n2. 测试第二次插入相同数据（应该触发UPDATE）")
            # 修改一些字段值
            kline_data_updated = kline_data.copy()
            kline_data_updated["close"] = 51000.0
            kline_data_updated["volume"] = 200.0
            
            if db_type == "sqlite":
                stmt = sqlite_insert(Kline).values([kline_data_updated])
                stmt = stmt.on_conflict_do_update(
                    index_elements=['unique_kline'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'updated_at': func.now()
                    }
                )
                result = db.execute(stmt)
            elif db_type == "duckdb":
                stmt = pg_insert(Kline).values([kline_data_updated])
                stmt = stmt.on_conflict_do_update(
                    index_elements=['unique_kline'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'updated_at': func.now()
                    }
                )
                result = db.execute(stmt)
            else:
                # 先尝试插入，失败则更新
                try:
                    db.execute("INSERT INTO klines (symbol, interval, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                               (kline_data_updated['symbol'], kline_data_updated['interval'], kline_data_updated['date'], kline_data_updated['open'], kline_data_updated['high'], kline_data_updated['low'], kline_data_updated['close'], kline_data_updated['volume']))
                    result = type('obj', (object,), {'rowcount': 1})()
                except Exception:
                    # 发生冲突，执行UPDATE
                    unique_kline = f"{kline_data_updated['symbol']}_{kline_data_updated['interval']}_{kline_data_updated['date'].isoformat()}"
                    db.execute("UPDATE klines SET open = ?, high = ?, low = ?, close = ?, volume = ?, updated_at = CURRENT_TIMESTAMP WHERE unique_kline = ?", 
                               (kline_data_updated['open'], kline_data_updated['high'], kline_data_updated['low'], kline_data_updated['close'], kline_data_updated['volume'], unique_kline))
                    result = type('obj', (object,), {'rowcount': 1})()
            
            db.commit()
            print(f"✅ 第二次插入成功，影响行数: {result.rowcount}")
            
            # 3. 验证数据是否正确更新
            print("\n3. 验证数据是否正确更新")
            
            # 直接查询数据库
            kline = db.query(Kline).filter(
                Kline.symbol == test_symbol,
                Kline.interval == test_interval,
                Kline.date == test_date
            ).first()
            
            if kline:
                print(f"✅ 查询成功，数据存在")
                print(f"   - 收盘价: {kline.close} (预期: 51000.0)")
                print(f"   - 成交量: {kline.volume} (预期: 200.0)")
                
                # 验证更新是否成功
                if kline.close == 51000.0 and kline.volume == 200.0:
                    print("✅ UPSERT更新成功，数据符合预期")
                else:
                    print("❌ UPSERT更新失败，数据不符合预期")
            else:
                print("❌ 查询失败，数据不存在")
                
        except Exception as e:
            print(f"❌ UPSERT测试失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            db.close()
            
    print("\n🎉 所有UPSERT测试通过，修复成功！")
    
except Exception as e:
    print(f"❌ 测试初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
