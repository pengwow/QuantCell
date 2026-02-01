#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：为crypto_symbols表添加is_deleted字段
"""

import logging
import os
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('migrate_crypto_symbols')


def migrate_crypto_symbols():
    """
    为crypto_symbols表添加is_deleted字段
    
    Returns:
        bool: 迁移是否成功
    """
    try:
        logger.info("开始迁移crypto_symbols表...")
        
        # 直接创建数据库引擎，避免导入路径问题
        from sqlalchemy import create_engine, text
        
        # 构建数据库路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = Path(current_dir) / "data" / "quantcell_sqlite.db"
        db_url = f"sqlite:///{db_path}"
        
        logger.info(f"使用数据库: {db_url}")
        
        # 创建引擎
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        
        # 检查并添加is_deleted字段
        with engine.begin() as conn:
            # 检查is_deleted字段是否存在
            try:
                result = conn.execute(text("PRAGMA table_info(crypto_symbols)"))
                columns = [row[1] for row in result]
                
                if 'is_deleted' not in columns:
                    # 添加is_deleted字段
                    conn.execute(text("ALTER TABLE crypto_symbols ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
                    logger.info("成功添加is_deleted字段")
                else:
                    logger.info("is_deleted字段已存在，跳过添加")
            except Exception as e:
                logger.error(f"检查字段时出错: {e}")
                # 如果是SQLite，表结构检查可能有不同的方法
                try:
                    # 尝试直接添加字段
                    conn.execute(text("ALTER TABLE crypto_symbols ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"))
                    logger.info("成功添加is_deleted字段")
                except Exception as add_error:
                    logger.warning(f"添加字段失败 (可能已存在): {add_error}")
        
        logger.info("crypto_symbols表迁移完成")
        return True
        
    except Exception as e:
        logger.error(f"迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = migrate_crypto_symbols()
    sys.exit(0 if success else 1)
