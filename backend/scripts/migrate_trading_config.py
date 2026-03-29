#!/usr/bin/env python3
"""
迁移 workers 表，添加 trading_config 列并迁移旧数据
"""
import json
import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

from collector.db.database import init_database_config
init_database_config()

from collector.db.database import engine
from sqlalchemy import text


def migrate():
    with engine.connect() as conn:
        # 检查是否已经有 trading_config 列
        result = conn.execute(text("PRAGMA table_info(workers)"))
        columns = [row[1] for row in result.fetchall()]

        if 'trading_config' in columns:
            print("trading_config column already exists, skipping migration")
            return

        # 1. 添加 trading_config 列
        conn.execute(text('ALTER TABLE workers ADD COLUMN trading_config TEXT DEFAULT "{}"'))
        conn.commit()
        print("Added trading_config column")

        # 2. 迁移旧数据到新的 trading_config 字段
        result = conn.execute(text('SELECT id, exchange, symbol, timeframe, market_type, trading_mode FROM workers'))
        workers = result.fetchall()

        for worker in workers:
            worker_id, exchange, symbol, timeframe, market_type, trading_mode = worker

            trading_config = {
                'exchange': exchange or 'binance',
                'symbols_config': {
                    'type': 'symbols',
                    'symbols': [symbol] if symbol else ['BTCUSDT'],
                    'pool_id': None,
                    'pool_name': None
                },
                'timeframe': timeframe or '1h',
                'market_type': market_type or 'spot',
                'trading_mode': trading_mode or 'paper'
            }

            conn.execute(
                text('UPDATE workers SET trading_config = :config WHERE id = :id'),
                {'config': json.dumps(trading_config), 'id': worker_id}
            )

        conn.commit()
        print(f"Migrated {len(workers)} workers to new trading_config format")

        # 3. 验证
        result = conn.execute(text('PRAGMA table_info(workers)'))
        columns = result.fetchall()
        print("\nUpdated columns in workers table:")
        for col in columns:
            print(f"  {col[1]}: {col[2]}")


if __name__ == "__main__":
    migrate()
