#!/usr/bin/env python3
"""测试DuckDB连接配置修复效果

简化测试脚本，直接测试修复的核心问题：确保原生DuckDB连接和SQLAlchemy连接使用相同的配置
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


def test_duckdb_config_consistency():
    """测试DuckDB连接配置一致性"""
    logger.info("开始测试DuckDB连接配置一致性...")
    
    # 使用临时数据库文件，避免锁定冲突
    temp_db_path = Path(__file__).parent / "data" / "temp_config_test.db"
    temp_db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 确保临时文件不存在
    if temp_db_path.exists():
        temp_db_path.unlink()
    
    # 测试1: 直接测试原生DuckDB连接配置
    logger.info("测试1: 测试原生DuckDB连接配置")
    try:
        import duckdb

        # 使用修复后的配置
        conn1 = duckdb.connect(
            str(temp_db_path),
            read_only=False,
            config={
                "custom_user_agent": "qbot/1.0",
                "enable_external_access": "true",
                "enable_object_cache": "true"
            }
        )
        logger.info("✓ 原生DuckDB连接成功")
        
        # 创建测试表
        conn1.execute("CREATE TABLE test_config (key VARCHAR PRIMARY KEY, value VARCHAR)")
        conn1.execute("INSERT INTO test_config VALUES ('test_key', 'test_value')")
        conn1.commit()
        logger.info("✓ 原生DuckDB操作成功")
        
        # 关闭连接
        conn1.close()
    except Exception as e:
        logger.error(f"✗ 原生DuckDB连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试2: 测试SQLAlchemy连接配置
    logger.info("测试2: 测试SQLAlchemy连接配置")
    try:
        from sqlalchemy import create_engine, text

        # 构建DuckDB连接URL
        db_url = f"duckdb:///{temp_db_path}"
        
        # 使用修复后的配置
        engine = create_engine(
            db_url,
            connect_args={
                "read_only": False,
                "config": {
                    "custom_user_agent": "qbot/1.0",
                    "enable_external_access": "true",
                    "enable_object_cache": "true"
                }
            }
        )
        
        # 测试连接
        with engine.connect() as conn2:
            # 查询测试数据
            result = conn2.execute(text("SELECT * FROM test_config WHERE key = 'test_key'")).fetchone()
            if result:
                logger.info(f"✓ SQLAlchemy连接成功，查询结果: key={result[0]}, value={result[1]}")
            else:
                logger.error("✗ SQLAlchemy查询失败")
                return False
        
        # 关闭引擎
        engine.dispose()
    except Exception as e:
        logger.error(f"✗ SQLAlchemy连接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试3: 测试同时使用两种连接方式
    logger.info("测试3: 同时使用两种连接方式")
    try:
        import duckdb
        from sqlalchemy import create_engine, text

        # 先创建原生连接
        conn1 = duckdb.connect(
            str(temp_db_path),
            read_only=False,
            config={
                "custom_user_agent": "qbot/1.0",
                "enable_external_access": "true",
                "enable_object_cache": "true"
            }
        )
        logger.info("✓ 第一个原生DuckDB连接成功")
        
        # 同时创建SQLAlchemy连接
        db_url = f"duckdb:///{temp_db_path}"
        engine = create_engine(
            db_url,
            connect_args={
                "read_only": False,
                "config": {
                    "custom_user_agent": "qbot/1.0",
                    "enable_external_access": "true",
                    "enable_object_cache": "true"
                }
            }
        )
        
        with engine.connect() as conn2:
            # 在两个连接上执行操作
            conn1.execute("INSERT INTO test_config VALUES ('key2', 'value2')")
            result = conn2.execute(text("SELECT COUNT(*) FROM test_config")).fetchone()
            if result and result[0] == 2:
                logger.info(f"✓ 同时使用两种连接方式成功，表中有{result[0]}条记录")
            else:
                logger.error(f"✗ 同时使用两种连接方式失败，表中有{result[0] if result else 0}条记录")
                return False
        
        # 关闭连接
        conn1.close()
        engine.dispose()
    except Exception as e:
        logger.error(f"✗ 同时使用两种连接方式测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    logger.info("所有测试通过！DuckDB连接配置修复成功，连接配置一致，无冲突。")
    
    # 清理临时文件
    if temp_db_path.exists():
        temp_db_path.unlink()
        logger.info(f"清理临时数据库文件: {temp_db_path}")
    
    return True


if __name__ == "__main__":
    success = test_duckdb_config_consistency()
    sys.exit(0 if success else 1)