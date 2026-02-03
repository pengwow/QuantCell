#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密货币对表迁移脚本
用于添加is_deleted字段到crypto_symbols表
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

logger = logging.getLogger('migrate_crypto_symbols')

def migrate_add_is_deleted_column():
    """
    迁移：添加is_deleted字段到crypto_symbols表
    
    Returns:
        bool: 迁移是否成功
    """
    try:
        logger.info("开始执行crypto_symbols表迁移...")
        
        # 动态导入数据库相关模块
        from collector.db.database import init_database_config
        from sqlalchemy import text
        
        # 初始化数据库配置
        init_database_config()
        
        # 重新导入engine，因为它在init_database_config()中被初始化
        from collector.db.database import engine
        
        logger.info("连接到数据库，准备执行迁移...")
        
        with engine.begin() as conn:
            # 检查crypto_symbols表是否存在
            logger.info("检查crypto_symbols表是否存在...")
            table_check = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'crypto_symbols'
            """))
            
            if not table_check.fetchone():
                logger.warning("crypto_symbols表不存在，迁移跳过")
                return True
            
            # 检查is_deleted字段是否存在
            logger.info("检查is_deleted字段是否存在...")
            column_check = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'crypto_symbols' AND column_name = 'is_deleted'
            """))
            
            if not column_check.fetchone():
                # 添加is_deleted字段
                logger.info("is_deleted字段不存在，开始添加...")
                conn.execute(text("""
                ALTER TABLE crypto_symbols 
                ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE
                """))
                logger.info("已成功添加is_deleted字段到crypto_symbols表")
            else:
                logger.info("is_deleted字段已存在，迁移跳过")
            
            # 添加索引
            logger.info("检查is_deleted字段索引是否存在...")
            index_check = conn.execute(text("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'crypto_symbols' AND indexname LIKE '%is_deleted%'
            """))
            
            if not index_check.fetchone():
                logger.info("is_deleted字段索引不存在，开始添加...")
                conn.execute(text("""
                CREATE INDEX idx_crypto_symbols_is_deleted 
                ON crypto_symbols(is_deleted)
                """))
                logger.info("已成功添加is_deleted字段索引")
            else:
                logger.info("is_deleted字段索引已存在")
        
        logger.info("crypto_symbols表迁移执行成功！")
        return True
        
    except Exception as e:
        logger.error(f"执行迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """
    主函数
    """
    logger.info("=== 开始执行数据库迁移 ===")
    
    # 执行迁移
    success = migrate_add_is_deleted_column()
    
    if success:
        logger.info("=== 迁移执行成功 ===")
        sys.exit(0)
    else:
        logger.error("=== 迁移执行失败 ===")
        sys.exit(1)

if __name__ == '__main__':
    main()
