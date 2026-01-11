#!/usr/bin/env python3
"""
数据库表结构迁移脚本

用于管理和更新数据库表结构，确保表结构与模型定义保持一致
"""

from sqlalchemy import text
from sqlalchemy.orm import Session
from loguru import logger



def update_data_pools_table(session: Session, db_type: str) -> None:
    """更新data_pools表结构，添加缺失的列
    
    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("开始更新data_pools表结构...")
    
    # 检查表是否存在
    table_exists = False
    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='data_pools'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='data_pools'")
            ).fetchone()
        else:
            # 默认使用sqlite语法
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='data_pools'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查表是否存在失败: {e}")
        return
    
    if not table_exists:
        logger.info("data_pools表不存在，跳过更新")
        return
    
    # 检查并添加is_public列
    logger.info("检查is_public列是否存在...")
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pools') WHERE name='is_public'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='data_pools' AND column_name='is_public'")
            ).fetchone()
        
        if not column_exists:
            logger.info("添加is_public列...")
            session.execute(
                text("ALTER TABLE data_pools ADD COLUMN is_public BOOLEAN DEFAULT TRUE")
            )
            logger.info("is_public列添加成功")
        else:
            logger.info("is_public列已存在，跳过")
    except Exception as e:
        logger.error(f"添加is_public列失败: {e}")
    
    # 检查并添加is_default列
    logger.info("检查is_default列是否存在...")
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pools') WHERE name='is_default'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='data_pools' AND column_name='is_default'")
            ).fetchone()
        
        if not column_exists:
            logger.info("添加is_default列...")
            session.execute(
                text("ALTER TABLE data_pools ADD COLUMN is_default BOOLEAN DEFAULT FALSE")
            )
            logger.info("is_default列添加成功")
        else:
            logger.info("is_default列已存在，跳过")
    except Exception as e:
        logger.error(f"添加is_default列失败: {e}")
    
    logger.info("data_pools表结构更新完成")



def update_data_pool_assets_table(session: Session, db_type: str) -> None:
    """更新data_pool_assets表结构，确保id列是自增主键
    
    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("开始更新data_pool_assets表结构...")
    
    # 检查表是否存在
    table_exists = False
    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='data_pool_assets'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='data_pool_assets'")
            ).fetchone()
        else:
            # 默认使用sqlite语法
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='data_pool_assets'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查表是否存在失败: {e}")
        return
    
    if not table_exists:
        logger.info("data_pool_assets表不存在，跳过更新")
        return
    
    # 检查id列是否存在
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pool_assets') WHERE name='id'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='data_pool_assets' AND column_name='id'")
            ).fetchone()
        
        if not column_exists:
            logger.info(f"添加id列...当前数据库类型: {db_type}")
            # 无论数据库类型是什么，都使用创建新表的方式添加id列，因为SQLite不支持直接添加主键列
            
            # 0. 如果临时表已存在，先删除它
            logger.info("检查临时表是否存在...")
            session.execute(text("DROP TABLE IF EXISTS data_pool_assets_new"))
            
            # 1. 创建临时表，包含所有现有列和新的id主键列
            # 根据实际表结构，只包含存在的列
            logger.info("通过创建新表方式添加id列...")
            session.execute(
                text("CREATE TABLE data_pool_assets_new (id INTEGER PRIMARY KEY AUTOINCREMENT, pool_id INTEGER NOT NULL, asset_id VARCHAR NOT NULL, asset_type VARCHAR, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (pool_id) REFERENCES data_pools(id))")
            )
            
            # 2. 复制旧表数据到新表，只复制实际存在的列，updated_at使用默认值
            session.execute(
                text("INSERT INTO data_pool_assets_new (pool_id, asset_id, asset_type, created_at) SELECT pool_id, asset_id, asset_type, created_at FROM data_pool_assets")
            )
            
            # 3. 删除旧表
            session.execute(text("DROP TABLE data_pool_assets"))
            
            # 4. 将新表重命名为旧表名称
            session.execute(text("ALTER TABLE data_pool_assets_new RENAME TO data_pool_assets"))
            logger.info("id列添加成功")
        else:
            logger.info("id列已存在，跳过")
    except Exception as e:
        logger.error(f"更新data_pool_assets表id列失败: {e}")
    
    logger.info("data_pool_assets表结构更新完成")



def update_strategies_table(session: Session, db_type: str) -> None:
    """更新strategies表结构，添加content列用于存储策略内容
    
    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("开始更新strategies表结构...")
    
    # 检查表是否存在
    table_exists = False
    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='strategies'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='strategies'")
            ).fetchone()
        else:
            # 默认使用sqlite语法
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='strategies'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查表是否存在失败: {e}")
        return
    
    if not table_exists:
        logger.info("strategies表不存在，跳过更新")
        return
    
    # 检查并添加content列
    logger.info("检查content列是否存在...")
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('strategies') WHERE name='content'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='strategies' AND column_name='content'")
            ).fetchone()
        
        if not column_exists:
            logger.info("添加content列...")
            # 使用ALTER TABLE语句添加列
            session.execute(
                text("ALTER TABLE strategies ADD COLUMN content TEXT")
            )
            logger.info("content列添加成功")
        else:
            logger.info("content列已存在，跳过")
    except Exception as e:
        logger.error(f"添加content列失败: {e}")
        # 如果是SQLite，尝试使用创建新表的方式添加列
        if db_type == "sqlite":
            try:
                logger.info("尝试使用创建新表的方式添加content列...")
                
                # 0. 如果临时表已存在，先删除它
                session.execute(text("DROP TABLE IF EXISTS strategies_new"))
                
                # 1. 创建临时表，包含所有现有列和新的content列
                session.execute(
                    text("""CREATE TABLE strategies_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(255) UNIQUE,
                        filename VARCHAR(255) NOT NULL,
                        content TEXT,
                        description TEXT,
                        parameters TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )""")
                )
                
                # 2. 复制旧表数据到新表
                session.execute(
                    text("""INSERT INTO strategies_new (id, name, filename, description, parameters, created_at, updated_at) 
                           SELECT id, name, filename, description, parameters, created_at, updated_at FROM strategies""")
                )
                
                # 3. 删除旧表
                session.execute(text("DROP TABLE strategies"))
                
                # 4. 将新表重命名为旧表名称
                session.execute(text("ALTER TABLE strategies_new RENAME TO strategies"))
                logger.info("使用创建新表的方式添加content列成功")
            except Exception as sqlite_e:
                logger.error(f"使用创建新表的方式添加content列失败: {sqlite_e}")
                raise
    
    logger.info("strategies表结构更新完成")


def run_migrations() -> None:
    """运行所有迁移脚本
    
    在应用程序启动时调用，确保所有表结构都是最新的
    """
    logger.info("开始运行数据库迁移脚本...")
    
    try:
        # 延迟导入，避免循环导入问题
        from collector.db.database import init_database_config, engine, db_type
        
        # 初始化数据库配置
        init_database_config()
        
        # 使用Session执行迁移
        with Session(engine) as session:
            # 更新data_pools表结构
            update_data_pools_table(session, db_type)
            
            # 更新data_pool_assets表结构
            update_data_pool_assets_table(session, db_type)
            
            # 更新strategies表结构，添加content列
            update_strategies_table(session, db_type)
            
            # 提交所有更改
            session.commit()
            logger.info("所有迁移脚本执行成功")
    except Exception as e:
        logger.error(f"执行迁移脚本失败: {e}")
        # 回滚事务
        if 'session' in locals():
            session.rollback()
        raise
