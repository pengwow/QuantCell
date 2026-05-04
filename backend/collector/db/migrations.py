#!/usr/bin/env python3
"""
数据库表结构迁移脚本

用于管理和更新数据库表结构，确保表结构与模型定义保持一致
"""

from sqlalchemy import text
from sqlalchemy.orm import Session
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 导入SessionLocal以正确创建session
try:
    from collector.db.database import SessionLocal
except ImportError:
    # 如果导入失败，使用默认的Session类
    SessionLocal = Session



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
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pools') WHERE name='is_public'")
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
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pools') WHERE name='is_default'")
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
    """更新strategies表结构

    注意：策略模型已迁移到 strategy.models，表结构由 SQLAlchemy 自动管理
    此函数保留用于兼容性，但不再执行任何操作

    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("strategies表结构由 strategy.models 管理，跳过迁移")
    return


def update_system_config_table(session: Session, db_type: str) -> None:
    """更新system_config表结构，添加name和plugin字段
    
    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("开始更新system_config表结构...")
    
    # 检查表是否存在
    table_exists = False
    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='system_config'")
            ).fetchone()
        else:
            # 默认使用sqlite语法
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查表是否存在失败: {e}")
        return
    
    if not table_exists:
        logger.info("system_config表不存在，跳过更新")
        return
    
    # 检查并添加plugin列
    logger.info("检查plugin列是否存在...")
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='plugin'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='plugin'")
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='plugin'")
            ).fetchone()
        
        if not column_exists:
            logger.info("添加plugin列...")
            session.execute(
                text("ALTER TABLE system_config ADD COLUMN plugin VARCHAR")
            )
            logger.info("plugin列添加成功")
        else:
            logger.info("plugin列已存在，跳过")
    except Exception as e:
        logger.error(f"添加plugin列失败: {e}")
    
    # 检查并添加name列
    logger.info("检查name列是否存在...")
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='name'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='name'")
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='name'")
            ).fetchone()
        
        if not column_exists:
            logger.info("添加name列...")
            session.execute(
                text("ALTER TABLE system_config ADD COLUMN name VARCHAR")
            )
            logger.info("name列添加成功")
        else:
            logger.info("name列已存在，跳过")
    except Exception as e:
        logger.error(f"添加name列失败: {e}")
    
    # 检查并添加is_sensitive列
    logger.info("检查is_sensitive列是否存在...")
    try:
        column_exists = False
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='is_sensitive'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='is_sensitive'")
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='is_sensitive'")
            ).fetchone()
        
        if not column_exists:
            logger.info("添加is_sensitive列...")
            session.execute(
                text("ALTER TABLE system_config ADD COLUMN is_sensitive BOOLEAN DEFAULT FALSE")
            )
            logger.info("is_sensitive列添加成功")
        else:
            logger.info("is_sensitive列已存在，跳过")
    except Exception as e:
        logger.error(f"添加is_sensitive列失败: {e}")
        # 如果是SQLite，尝试使用创建新表的方式添加列
        if db_type == "sqlite":
            try:
                logger.info("尝试使用创建新表的方式添加is_sensitive列...")
                
                # 0. 如果临时表已存在，先删除它
                session.execute(text("DROP TABLE IF EXISTS system_config_new"))
                
                # 1. 创建临时表，包含所有现有列和新的is_sensitive列
                session.execute(
                    text("""CREATE TABLE system_config_new (
                        key VARCHAR PRIMARY KEY,
                        value VARCHAR NOT NULL,
                        description TEXT,
                        plugin VARCHAR,
                        name VARCHAR,
                        is_sensitive BOOLEAN DEFAULT FALSE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )""")
                )
                
                # 2. 复制旧表数据到新表
                # 注意：需要根据实际表结构调整查询
                try:
                    # 尝试使用包含plugin和name列的查询
                    session.execute(
                        text("""INSERT INTO system_config_new (key, value, description, plugin, name, created_at, updated_at) 
                               SELECT key, value, description, plugin, name, created_at, updated_at FROM system_config""")
                    )
                except:
                    try:
                        # 尝试使用包含plugin列的查询
                        session.execute(
                            text("""INSERT INTO system_config_new (key, value, description, plugin, created_at, updated_at) 
                                   SELECT key, value, description, plugin, created_at, updated_at FROM system_config""")
                        )
                    except:
                        # 如果plugin列不存在，使用不包含plugin列的查询
                        logger.info("plugin列不存在，使用不包含plugin列的查询复制数据...")
                        session.execute(
                            text("""INSERT INTO system_config_new (key, value, description, created_at, updated_at) 
                                   SELECT key, value, description, created_at, updated_at FROM system_config""")
                        )
                
                # 3. 删除旧表
                session.execute(text("DROP TABLE system_config"))
                
                # 4. 将新表重命名为旧表名称
                session.execute(text("ALTER TABLE system_config_new RENAME TO system_config"))
                logger.info("使用创建新表的方式添加is_sensitive列成功")
            except Exception as sqlite_e:
                logger.error(f"使用创建新表的方式添加is_sensitive列失败: {sqlite_e}")
                raise
    
    logger.info("system_config表结构更新完成")


def update_kline_tables(session: Session, db_type: str) -> None:
    """更新K线表结构，添加data_source字段
    
    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("开始更新K线表结构...")
    
    # 更新crypto_future_klines表
    logger.info("更新crypto_future_klines表...")
    try:
        # 检查表是否存在
        table_exists = False
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_future_klines'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='crypto_future_klines'")
            ).fetchone()
        
        if table_exists:
            # 检查data_source列是否存在
            column_exists = False
            if db_type == "sqlite":
                column_exists = session.execute(
                    text("SELECT name FROM pragma_table_info('crypto_future_klines') WHERE name='data_source'")
                ).fetchone()
            elif db_type == "duckdb":
                column_exists = session.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='crypto_future_klines' AND column_name='data_source'")
                ).fetchone()
            
            if not column_exists:
                logger.info("为crypto_future_klines表添加data_source列...")
                # 添加data_source列
                session.execute(
                    text("ALTER TABLE crypto_future_klines ADD COLUMN data_source VARCHAR(50) NOT NULL DEFAULT 'unknown'")
                )
                # 创建索引
                session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_crypto_future_klines_data_source ON crypto_future_klines(data_source)")
                )
                logger.info("crypto_future_klines表data_source列添加成功")
            else:
                logger.info("crypto_future_klines表data_source列已存在，跳过")
        else:
            logger.info("crypto_future_klines表不存在，跳过")
    except Exception as e:
        logger.error(f"更新crypto_future_klines表失败: {e}")
    
    # 更新stock_klines表
    logger.info("更新stock_klines表...")
    try:
        # 检查表是否存在
        table_exists = False
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_klines'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='stock_klines'")
            ).fetchone()
        
        if table_exists:
            # 检查data_source列是否存在
            column_exists = False
            if db_type == "sqlite":
                column_exists = session.execute(
                    text("SELECT name FROM pragma_table_info('stock_klines') WHERE name='data_source'")
                ).fetchone()
            elif db_type == "duckdb":
                column_exists = session.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='stock_klines' AND column_name='data_source'")
                ).fetchone()
            
            if not column_exists:
                logger.info("为stock_klines表添加data_source列...")
                # 添加data_source列
                session.execute(
                    text("ALTER TABLE stock_klines ADD COLUMN data_source VARCHAR(50) NOT NULL DEFAULT 'unknown'")
                )
                # 创建索引
                session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_stock_klines_data_source ON stock_klines(data_source)")
                )
                logger.info("stock_klines表data_source列添加成功")
            else:
                logger.info("stock_klines表data_source列已存在，跳过")
        else:
            logger.info("stock_klines表不存在，跳过")
    except Exception as e:
        logger.error(f"更新stock_klines表失败: {e}")
    
    logger.info("K线表结构更新完成")


def create_users_table(session: Session, db_type: str) -> None:
    """创建users表（如果不存在）

    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("检查users表是否存在...")

    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='users'")
            ).fetchone()
        else:
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查users表是否存在失败: {e}")
        return

    if table_exists:
        logger.info("users表已存在，跳过创建")
        return

    logger.info("创建users表...")
    try:
        if db_type == "sqlite":
            session.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password_hash VARCHAR(128) NOT NULL,
                    nickname VARCHAR(100),
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME
                )
            """))
            session.execute(text("CREATE INDEX ix_users_id ON users(id)"))
            session.execute(text("CREATE INDEX ix_users_username ON users(username)"))
            session.execute(text("CREATE INDEX ix_users_is_active ON users(is_active)"))
        elif db_type == "duckdb":
            session.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password_hash VARCHAR(128) NOT NULL,
                    nickname VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """))
        logger.info("users表创建成功")
    except Exception as e:
        logger.error(f"创建users表失败: {e}")


def update_system_config_add_user_id(session: Session, db_type: str) -> None:
    """更新system_config表，添加user_id列并重建主键约束

    由于SQLite不支持ALTER TABLE修改主键，需要通过创建新表的方式完成迁移

    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("开始更新system_config表，添加user_id列...")

    # 检查表是否存在
    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='system_config'")
            ).fetchone()
        else:
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查system_config表是否存在失败: {e}")
        return

    if not table_exists:
        logger.info("system_config表不存在，跳过更新")
        return

    # 检查user_id列是否已存在
    try:
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='user_id'")
            ).fetchone()
        elif db_type == "duckdb":
            column_exists = session.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='user_id'")
            ).fetchone()
        else:
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='user_id'")
            ).fetchone()

        if column_exists:
            logger.info("user_id列已存在，跳过")
            return
    except Exception as e:
        logger.error(f"检查user_id列是否存在失败: {e}")
        return

    logger.info("添加user_id列到system_config表...")
    try:
        if db_type == "sqlite":
            # SQLite不支持修改主键，需要重建表
            # 0. 清理可能残留的临时表
            session.execute(text("DROP TABLE IF EXISTS system_config_new"))

            # 1. 创建新表，使用(key, user_id)联合作为主键
            session.execute(text("""
                CREATE TABLE system_config_new (
                    key VARCHAR NOT NULL,
                    value VARCHAR NOT NULL,
                    description TEXT,
                    name VARCHAR,
                    plugin VARCHAR,
                    is_sensitive BOOLEAN DEFAULT 0,
                    user_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (key, user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))

            # 2. 复制旧表数据到新表，user_id设为NULL（系统级配置）
            try:
                session.execute(text("""
                    INSERT INTO system_config_new (key, value, description, name, plugin, is_sensitive, created_at, updated_at)
                    SELECT key, value, description, name, plugin, is_sensitive, created_at, updated_at
                    FROM system_config
                """))
            except Exception as copy_e:
                logger.warning(f"复制数据时出错，尝试兼容旧表结构: {copy_e}")
                # 兼容没有name、plugin、is_sensitive列的旧表
                try:
                    session.execute(text("""
                        INSERT INTO system_config_new (key, value, description, created_at, updated_at)
                        SELECT key, value, description, created_at, updated_at
                        FROM system_config
                    """))
                except Exception as copy_e2:
                    logger.error(f"复制数据失败: {copy_e2}")
                    session.execute(text("DROP TABLE IF EXISTS system_config_new"))
                    return

            # 3. 删除旧表
            session.execute(text("DROP TABLE system_config"))

            # 4. 重命名新表
            session.execute(text("ALTER TABLE system_config_new RENAME TO system_config"))

            # 5. 创建索引
            session.execute(text("CREATE INDEX IF NOT EXISTS ix_system_config_key ON system_config(key)"))
            session.execute(text("CREATE INDEX IF NOT EXISTS ix_system_config_user_id ON system_config(user_id)"))

            logger.info("system_config表重建成功，已添加user_id列")

        elif db_type == "duckdb":
            session.execute(text("ALTER TABLE system_config ADD COLUMN user_id INTEGER"))
            logger.info("DuckDB: user_id列添加成功")

    except Exception as e:
        logger.error(f"更新system_config表失败: {e}")


def run_migrations() -> None:
    """运行所有迁移脚本
    
    在应用程序启动时调用，确保所有表结构都是最新的
    """
    logger.info("开始运行数据库迁移脚本...")
    
    try:
        # 延迟导入，避免循环导入问题
        import collector.db.database
        
        # 初始化数据库配置
        collector.db.database.init_database_config()
        
        # 获取更新后的数据库配置
        from collector.db.database import SessionLocal, db_type, engine
        
        logger.info(f"数据库类型: {db_type}")
        logger.info(f"数据库URL: {engine.url}")
        
        # 使用Session执行迁移
        with SessionLocal() as session:
            # 创建users表（如果不存在）
            create_users_table(session, db_type)

            # 更新system_config表，添加user_id列
            update_system_config_add_user_id(session, db_type)

            # 更新data_pools表结构
            update_data_pools_table(session, db_type)
            
            # 更新data_pool_assets表结构
            update_data_pool_assets_table(session, db_type)
            
            # 更新strategies表结构，添加content列
            update_strategies_table(session, db_type)
            
            # 更新system_config表结构，添加name列
            update_system_config_table(session, db_type)
            
            # 更新K线表结构，添加data_source列
            update_kline_tables(session, db_type)
            
            # 提交所有更改
            session.commit()
            logger.info("所有迁移脚本执行成功")
    except Exception as e:
        logger.error(f"执行迁移脚本失败: {e}")
        # 回滚事务
        if 'session' in locals():
            session.rollback()
        raise
