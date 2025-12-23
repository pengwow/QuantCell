#!/usr/bin/env python3
"""测试DuckDB连接配置修复效果

使用新的临时数据库文件，避免锁定冲突，验证修复后的连接配置是否正常工作
"""

import os
import sys
from pathlib import Path

from loguru import logger

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def test_duckdb_connection():
    """测试DuckDB连接配置"""
    logger.info("开始测试DuckDB连接配置...")
    
    # 使用临时数据库文件，避免锁定冲突
    temp_db_path = Path(__file__).parent / "data" / "temp_test.db"
    temp_db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 设置环境变量，使用临时数据库
    os.environ["DB_TYPE"] = "duckdb"
    os.environ["DB_FILE"] = str(temp_db_path)
    
    # 确保之前的导入不会影响测试
    if "collector.db.connection" in sys.modules:
        del sys.modules["collector.db.connection"]
    if "collector.db.database" in sys.modules:
        del sys.modules["collector.db.database"]
    if "collector.db.models" in sys.modules:
        del sys.modules["collector.db.models"]
    if "collector.db.crud" in sys.modules:
        del sys.modules["collector.db.crud"]
    
    try:
        # 测试1: 初始化数据库配置
        logger.info("测试1: 初始化数据库配置")
        from collector.db.database import Base, engine, init_database_config
        init_database_config()
        logger.info("✓ 数据库配置初始化成功")
        
        # 创建数据库表
        logger.info("创建数据库表...")
        from collector.db import models  # 导入模型，确保Base包含所有表定义
        Base.metadata.create_all(bind=engine)
        logger.info("✓ 数据库表创建成功")
        
        # 测试2: 使用SQLAlchemy连接
        logger.info("测试2: 使用SQLAlchemy连接")
        from collector.db import crud, schemas
        from collector.db.database import SessionLocal
        
        db = SessionLocal()
        try:
            # 创建测试配置
            test_config = schemas.SystemConfigCreate(
                key="test_key",
                value="test_value",
                description="Test configuration"
            )
            
            # 使用crud操作，验证SQLAlchemy连接正常
            created_config = crud.create_system_config(db, test_config)
            logger.info(f"✓ SQLAlchemy连接正常，创建配置成功: key={created_config.key}")
            
            # 查询配置，验证读取正常
            retrieved_config = crud.get_system_config(db, "test_key")
            logger.info(f"✓ SQLAlchemy读取正常，配置值: {retrieved_config.value}")
        finally:
            db.close()
        
        # 测试3: 使用原生DuckDB连接
        logger.info("测试3: 使用原生DuckDB连接")
        from collector.db.connection import get_db_connection
        
        conn = get_db_connection()
        try:
            # 执行原生SQL查询
            result = conn.execute("SELECT * FROM system_config WHERE key = 'test_key'")
            row = result.fetchone()
            if row:
                logger.info(f"✓ 原生DuckDB连接正常，查询结果: key={row[0]}, value={row[1]}")
            else:
                logger.error("✗ 原生DuckDB查询失败")
        finally:
            conn.close()
        
        # 测试4: 同时使用两种连接方式
        logger.info("测试4: 同时使用两种连接方式")
        
        # 打开SQLAlchemy连接
        db1 = SessionLocal()
        try:
            # 同时打开原生连接
            conn2 = get_db_connection()
            try:
                # 在两个连接上执行操作
                db1.execute("SELECT 1")
                conn2.execute("SELECT 1")
                logger.info("✓ 同时使用两种连接方式成功，没有配置冲突")
            finally:
                conn2.close()
        finally:
            db1.close()
        
        logger.info("所有测试通过！DuckDB连接配置修复成功。")
        
        # 清理临时文件
        if temp_db_path.exists():
            temp_db_path.unlink()
            logger.info(f"清理临时数据库文件: {temp_db_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理环境变量
        if "DB_TYPE" in os.environ:
            del os.environ["DB_TYPE"]
        if "DB_FILE" in os.environ:
            del os.environ["DB_FILE"]


if __name__ == "__main__":
    success = test_duckdb_connection()
    sys.exit(0 if success else 1)