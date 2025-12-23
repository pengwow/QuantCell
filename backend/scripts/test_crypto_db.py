#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试加密货币数据库功能

用于测试CryptoSymbol模型的数据库操作，包括表创建、数据插入和查询
"""

import logging
import os
import sys
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('test_crypto_db')


def test_crypto_db():
    """
    测试加密货币数据库功能
    
    Returns:
        bool: 测试是否成功
    """
    try:
        logger.info("开始测试加密货币数据库功能...")
        
        # 1. 初始化数据库配置
        from collector.db.database import SessionLocal, init_database_config
        logger.info("初始化数据库配置...")
        init_database_config()
        
        # 2. 导入所需模块
        import json

        from sqlalchemy import text

        from collector.db.database import engine

        # 3. 表迁移：使用原始SQL创建表，使用序列实现自增主键，兼容DuckDB
        logger.info("开始表迁移...")
        
        with engine.begin() as conn:
            from sqlalchemy import text

            # 先删除旧表
            conn.execute(text("DROP TABLE IF EXISTS crypto_symbols CASCADE"))
            logger.info("旧表删除成功")
            
            # 创建序列用于id自增
            conn.execute(text("DROP SEQUENCE IF EXISTS crypto_symbols_id_seq CASCADE"))
            conn.execute(text("CREATE SEQUENCE crypto_symbols_id_seq START 1"))
            logger.info("序列创建成功")
            
            # 创建新表，使用序列的nextval作为id的默认值
            conn.execute(text("""
            CREATE TABLE crypto_symbols (
                id INTEGER PRIMARY KEY DEFAULT nextval('crypto_symbols_id_seq'),
                symbol VARCHAR NOT NULL,
                base VARCHAR NOT NULL,
                quote VARCHAR NOT NULL,
                exchange VARCHAR NOT NULL,
                active BOOLEAN DEFAULT TRUE,
                precision TEXT,
                limits TEXT,
                type VARCHAR,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                CONSTRAINT unique_symbol_exchange UNIQUE (symbol, exchange)
            )
            """))
            logger.info("数据库表创建成功")
        
        # 4. 测试数据插入
        logger.info("开始测试数据插入...")
        
        # 创建测试数据
        test_symbols = [
            {
                'symbol': 'BTC/USDT',
                'base': 'BTC',
                'quote': 'USDT',
                'exchange': 'binance',
                'active': True,
                'precision': {'amount': 6, 'price': 2},
                'limits': {'amount': {'min': 0.000001, 'max': 1000}, 'price': {'min': 0.01}},
                'type': 'spot'
            },
            {
                'symbol': 'ETH/USDT',
                'base': 'ETH',
                'quote': 'USDT',
                'exchange': 'binance',
                'active': True,
                'precision': {'amount': 4, 'price': 2},
                'limits': {'amount': {'min': 0.0001, 'max': 10000}, 'price': {'min': 0.01}},
                'type': 'spot'
            },
            {
                'symbol': 'SOL/USDT',
                'base': 'SOL',
                'quote': 'USDT',
                'exchange': 'binance',
                'active': True,
                'precision': {'amount': 2, 'price': 2},
                'limits': {'amount': {'min': 0.01, 'max': 100000}, 'price': {'min': 0.01}},
                'type': 'spot'
            }
        ]
        
        # 插入测试数据
        db = SessionLocal()
        try:
            # 先删除可能存在的测试数据
            db.execute(text("DELETE FROM crypto_symbols WHERE exchange = :exchange"), {'exchange': 'binance'})
            
            # 批量插入测试数据
            logger.info(f"开始插入{len(test_symbols)}条测试数据...")
            for symbol_info in test_symbols:
                db.execute(text("""
                INSERT INTO crypto_symbols (symbol, base, quote, exchange, active, precision, limits, type)
                VALUES (:symbol, :base, :quote, :exchange, :active, :precision, :limits, :type)
                """), {
                    'symbol': symbol_info['symbol'],
                    'base': symbol_info['base'],
                    'quote': symbol_info['quote'],
                    'exchange': symbol_info['exchange'],
                    'active': symbol_info['active'],
                    'precision': json.dumps(symbol_info['precision']),
                    'limits': json.dumps(symbol_info['limits']),
                    'type': symbol_info['type']
                })
            
            db.commit()
            logger.info("测试数据插入成功")
        finally:
            db.close()
        
        # 5. 测试数据查询
        logger.info("开始测试数据查询...")
        
        db = SessionLocal()
        try:
            # 查询所有binance的货币对
            result = db.execute(text("SELECT * FROM crypto_symbols WHERE exchange = :exchange"), {'exchange': 'binance'})
            symbols = result.fetchall()
            logger.info(f"查询到{len(symbols)}条binance货币对数据")
            
            # 打印查询结果
            for symbol in symbols:
                logger.info(f"货币对: {symbol.symbol}, 基础货币: {symbol.base}, 报价货币: {symbol.quote}")
                logger.info(f"  活跃状态: {symbol.active}, 类型: {symbol.type}")
            
            # 测试分页查询
            result = db.execute(text("SELECT * FROM crypto_symbols WHERE exchange = :exchange OFFSET :offset LIMIT :limit"), 
                              {'exchange': 'binance', 'offset': 1, 'limit': 1})
            paginated_symbols = result.fetchall()
            logger.info(f"分页查询结果: {[s.symbol for s in paginated_symbols]}")
            
            # 测试过滤查询
            result = db.execute(text("SELECT * FROM crypto_symbols WHERE exchange = :exchange AND symbol LIKE :filter"), 
                              {'exchange': 'binance', 'filter': '%ETH%'})
            filtered_symbols = result.fetchall()
            logger.info(f"过滤查询结果: {[s.symbol for s in filtered_symbols]}")
            
        finally:
            db.close()
        
        # 6. 测试数据更新
        logger.info("开始测试数据更新...")
        
        db = SessionLocal()
        try:
            # 更新一条记录
            result = db.execute(text("UPDATE crypto_symbols SET active = :active WHERE symbol = :symbol AND exchange = :exchange"), 
                              {'active': False, 'symbol': 'BTC/USDT', 'exchange': 'binance'})
            updated_count = result.rowcount
            db.commit()
            logger.info(f"成功更新{updated_count}条记录")
            
            # 验证更新
            result = db.execute(text("SELECT active FROM crypto_symbols WHERE symbol = :symbol AND exchange = :exchange"), 
                              {'symbol': 'BTC/USDT', 'exchange': 'binance'})
            updated_record = result.fetchone()
            logger.info(f"验证更新结果: BTC/USDT 活跃状态: {updated_record.active}")
        finally:
            db.close()
        
        # 7. 测试数据删除
        logger.info("开始测试数据删除...")
        
        db = SessionLocal()
        try:
            # 删除一条记录
            result = db.execute(text("DELETE FROM crypto_symbols WHERE symbol = :symbol AND exchange = :exchange"), 
                              {'symbol': 'SOL/USDT', 'exchange': 'binance'})
            deleted_count = result.rowcount
            db.commit()
            logger.info(f"成功删除{deleted_count}条记录")
            
            # 验证删除
            result = db.execute(text("SELECT COUNT(*) FROM crypto_symbols WHERE exchange = :exchange"), {'exchange': 'binance'})
            remaining_count = result.fetchone()[0]
            logger.info(f"删除后剩余{remaining_count}条记录")
        finally:
            db.close()
        
        logger.info("所有测试通过！加密货币数据库功能正常")
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_crypto_db()
    sys.exit(0 if success else 1)