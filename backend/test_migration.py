#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据库迁移脚本
用于验证is_deleted字段的添加逻辑
"""

import logging
import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = current_dir
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger('test_migration')

def test_add_is_deleted_field():
    """测试添加is_deleted字段"""
    try:
        logger.info("开始测试添加is_deleted字段...")
        
        # 导入数据库相关模块
        from collector.db.database import SessionLocal, init_database_config, engine
        from collector.db.models import CryptoSymbol
        from sqlalchemy import text
        
        # 初始化数据库配置
        init_database_config()
        
        # 添加字段的简单迁移逻辑
        with engine.begin() as conn:
            # 检查is_deleted字段是否存在
            logger.info("检查is_deleted字段是否存在...")
            result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'crypto_symbols' AND column_name = 'is_deleted'
            """))
            
            if not result.fetchone():
                # 添加is_deleted字段
                logger.info("is_deleted字段不存在，开始添加...")
                conn.execute(text("""
                ALTER TABLE crypto_symbols 
                ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE
                """))
                logger.info("已成功添加is_deleted字段到crypto_symbols表")
            else:
                logger.info("is_deleted字段已存在")
        
        # 验证添加的字段可以使用
        logger.info("验证is_deleted字段可以正常使用...")
        db = SessionLocal()
        try:
            # 尝试查询包含is_deleted字段的数据
            symbols = db.query(CryptoSymbol).limit(5).all()
            logger.info(f"成功查询到{len(symbols)}条数据，包含is_deleted字段")
            
            # 尝试更新is_deleted字段
            for symbol in symbols:
                symbol.is_deleted = False
                db.add(symbol)
            db.commit()
            logger.info("成功更新is_deleted字段")
            
        finally:
            db.close()
        
        logger.info("测试添加is_deleted字段成功！")
        return True
        
    except Exception as e:
        logger.error(f"测试添加is_deleted字段失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    """主函数"""
    logger.info("开始执行数据库迁移测试...")
    success = test_add_is_deleted_field()
    if success:
        logger.info("所有测试通过！")
        sys.exit(0)
    else:
        logger.error("测试失败！")
        sys.exit(1)
