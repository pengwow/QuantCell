#!/usr/bin/env python3
"""
测试 Worker 创建功能
"""

import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.db.database import init_database_config, SessionLocal
from worker import crud, schemas


def test_create_worker():
    """测试创建 Worker"""
    # 初始化数据库
    init_database_config()

    # 创建测试数据
    db = SessionLocal()
    try:
        # 测试 1: 使用 symbol（单数形式，前端格式）
        print("测试 1: 使用 symbol（单数形式）...")
        worker_data1 = schemas.WorkerCreate(
            name='测试Worker-单数',
            description='测试描述',
            strategy_id=1,
            exchange='binance',
            symbol='BTCUSDT',  # 使用单数形式
            timeframe='1h',
            market_type='spot',
            trading_mode='paper'
        )

        worker1 = crud.create_worker(db, worker_data1)
        print(f"  ✓ Worker 创建成功: ID={worker1.id}, Name={worker1.name}")
        print(f"  Trading Config: {worker1.trading_config}")

        # 清理
        db.delete(worker1)
        db.commit()
        print("  ✓ 测试数据已清理")

        # 测试 2: 使用 symbols（复数形式）
        print("\n测试 2: 使用 symbols（复数形式）...")
        worker_data2 = schemas.WorkerCreate(
            name='测试Worker-复数',
            description='测试描述',
            strategy_id=1,
            exchange='binance',
            symbols=['BTCUSDT', 'ETHUSDT'],  # 使用复数形式
            timeframe='1h',
            market_type='spot',
            trading_mode='paper'
        )

        worker2 = crud.create_worker(db, worker_data2)
        print(f"  ✓ Worker 创建成功: ID={worker2.id}, Name={worker2.name}")
        print(f"  Trading Config: {worker2.trading_config}")

        # 清理
        db.delete(worker2)
        db.commit()
        print("  ✓ 测试数据已清理")

        # 测试 3: 不提供 symbol/symbols（使用默认值）
        print("\n测试 3: 不提供 symbol/symbols（使用默认值）...")
        worker_data3 = schemas.WorkerCreate(
            name='测试Worker-默认',
            description='测试描述',
            strategy_id=1,
            exchange='binance',
            # 不提供 symbol 或 symbols
            timeframe='1h',
            market_type='spot',
            trading_mode='paper'
        )

        worker3 = crud.create_worker(db, worker_data3)
        print(f"  ✓ Worker 创建成功: ID={worker3.id}, Name={worker3.name}")
        print(f"  Trading Config: {worker3.trading_config}")

        # 清理
        db.delete(worker3)
        db.commit()
        print("  ✓ 测试数据已清理")

        print("\n✅ 所有测试通过！")
        return True

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_create_worker()
    sys.exit(0 if success else 1)
