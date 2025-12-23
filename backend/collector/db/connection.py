# 数据库连接管理

import os
import sqlite3
import threading
from pathlib import Path

from loguru import logger

# 数据库文件路径
default_db_path = Path(__file__).parent.parent.parent / "data" / "qbot.db"

# 确保数据库目录存在
default_db_path.parent.mkdir(parents=True, exist_ok=True)


class DBConnection:
    """数据库连接管理类
    
    实现单例模式，使用线程本地存储为每个线程创建独立的数据库连接
    支持SQLite和DuckDB数据库
    """
    _instance = None
    
    def __new__(cls):
        """创建单例实例
        
        Returns:
            DBConnection: 数据库连接实例
        """
        if cls._instance is None:
            cls._instance = super(DBConnection, cls).__new__(cls)
            # 使用线程本地存储，为每个线程创建独立的连接
            cls._instance._local = threading.local()
        return cls._instance
    
    def connect(self):
        """建立数据库连接
        
        Returns:
            数据库连接对象
        """
        # 检查当前线程是否已有连接
        if not hasattr(self._local, '_conn') or self._local._conn is None:
            # 从环境变量或配置获取数据库类型和文件路径
            # 避免循环依赖，优先使用环境变量
            import os

            # 优先从环境变量读取配置
            db_type = os.environ.get("DB_TYPE", "duckdb")  # 默认使用duckdb
            db_file = os.environ.get("DB_FILE", str(default_db_path))
            
            # 如果环境变量未设置，尝试从配置读取
            try:
                from backend.config_manager import get_config
                config_db_type = get_config("database.type")
                if config_db_type:
                    db_type = config_db_type
                
                config_db_file = get_config("database.file")
                if config_db_file:
                    db_file = config_db_file
            except Exception as e:
                logger.warning(f"从配置读取数据库信息失败，使用默认配置: {e}")
            
            logger.info(f"从配置读取数据库信息: type={db_type}, file={db_file}")
            logger.info(f"默认数据库路径: {default_db_path}")
            
            # 解析数据库文件路径
            db_path = Path(db_file).expanduser()
            if not db_path.is_absolute():
                # 相对路径相对于backend目录
                db_path = Path(__file__).parent.parent.parent / db_path
            
            # 确保数据库目录存在
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"最终数据库路径: {db_path}")
            logger.info(f"正在连接{db_type}数据库: {db_path}")
            
            if db_type == "sqlite":
                # SQLite连接
                # 设置check_same_thread=False允许连接在不同线程中使用
                # 设置timeout=30，遇到锁定时等待30秒
                # 设置autocommit=True自动提交事务，减少锁争用
                conn = sqlite3.connect(
                    str(db_path), 
                    check_same_thread=False,
                    timeout=30  # 遇到锁定时等待30秒
                )
                # 设置返回字典格式
                conn.row_factory = sqlite3.Row
                # 启用自动提交模式，减少锁争用
                conn.isolation_level = None
            elif db_type == "duckdb":
                # DuckDB连接
                import duckdb

                # 统一DuckDB连接配置，确保所有连接使用相同的配置
                conn = duckdb.connect(
                    str(db_path),
                    read_only=False,  # 确保连接是可写的
                    # 设置统一的配置选项，避免连接配置冲突
                    # 与SQLAlchemy连接使用完全相同的配置
                    config={
                        "enable_external_access": "true",
                        "enable_object_cache": "true",
                        # "locking_mode": "optimistic",  # 乐观锁模式
                    }
                )
            else:
                # 默认使用SQLite
                logger.warning(f"未知的数据库类型: {db_type}，使用SQLite")
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
            
            # 存储连接到线程本地存储
            self._local._conn = conn
            self._local._db_type = db_type
            self._local._db_path = db_path
            
            logger.info(f"{db_type}数据库连接成功: {db_path}")
        
        return self._local._conn
    
    def close(self):
        """关闭数据库连接
        """
        # 关闭当前线程的连接
        if hasattr(self._local, '_conn') and self._local._conn is not None:
            logger.info(f"正在关闭{self._local._db_type}数据库连接: {self._local._db_path}")
            self._local._conn.close()
            self._local._conn = None
            self._local._db_type = None
            self._local._db_path = None
            logger.info(f"数据库连接已关闭")


# 创建全局数据库连接实例
db_instance = DBConnection()


def get_db_connection():
    """获取数据库连接
    
    Returns:
        数据库连接对象
    """
    return db_instance.connect()


def init_db():
    """初始化数据库，创建所需的表
    
    使用SQLAlchemy创建系统配置表和任务表，并插入默认配置
    
    Raises:
        Exception: 初始化失败时抛出异常
    """
    try:
        logger.info("开始初始化数据库...")
        
        # 先初始化数据库配置和引擎
        from .database import init_database_config
        init_database_config()
        
        # 然后再导入engine变量，确保它已经被初始化
        from . import models
        from .database import Base, engine
        
        logger.info("使用SQLAlchemy创建数据库表...")
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("数据库表创建成功")
        
        # 验证表是否存在
        logger.info("验证表是否存在...")
        
        # 直接使用SQLAlchemy引擎进行表验证，避免创建新连接导致的配置冲突
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        from .database import db_type

        # 使用Session进行表验证
        with Session(engine) as session:
            if db_type == "sqlite":
                # SQLite使用sqlite_master表
                system_config_exists = session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='system_config'")).fetchone()
                tasks_exists = session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")).fetchone()
            else:
                # DuckDB使用information_schema.tables视图
                system_config_exists = session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name='system_config'")).fetchone()
                tasks_exists = session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name='tasks'")).fetchone()
        
        logger.info(f"system_config表存在: {system_config_exists is not None}")
        logger.info(f"tasks表存在: {tasks_exists is not None}")
        
        if not system_config_exists or not tasks_exists:
            logger.error("表创建失败，数据库初始化失败")
            raise Exception("表创建失败，数据库初始化失败")
        
        # 插入默认配置（保留原有逻辑）
        logger.info("插入默认配置...")
        # 先从配置文件读取相关配置
        from backend.config import get_config

        # 配置映射：配置文件key -> (system_config_key, 默认值, 描述)
        config_mapping = {
            "quant.qlib_data_dir": ("qlib_data_dir", "data/source", "QLib数据目录"),
            "app.max_workers": ("max_workers", "4", "最大工作线程数"),
        }
        
        # 构建默认配置列表
        default_configs = []
        
        # 1. 处理从配置文件映射的配置
        for config_key, (db_key, default_value, description) in config_mapping.items():
            # 从配置文件读取值，如果没有则使用默认值
            value = get_config(config_key, default_value)
            default_configs.append((db_key, str(value), description))
        
        # 2. 添加固定默认配置（没有在配置文件中定义的）
        fixed_defaults = [
            ("data_download_dir", "data/source", "数据下载目录"),
            ("current_market_type", "crypto", "当前交易模式: crypto(加密货币) 或 stock(股票)"),
            ("crypto_trading_mode", "spot", "加密货币蜡烛图类型: spot(现货) 或 futures(期货)"),
            ("default_exchange", "binance", "默认交易所"),
            ("default_interval", "1d", "默认时间间隔"),
            ("data_write_to_db", "false", "是否将下载的数据写入数据库，true为写入，false为不写入"),
        ]
        default_configs.extend(fixed_defaults)
        
        # 使用INSERT插入默认配置
        inserted_count = 0
        with Session(engine) as session:
            for key, value, description in default_configs:
                try:
                    # 先检查配置是否存在
                    existing_config = session.execute(
                        text("SELECT key FROM system_config WHERE key = :key"),
                        {"key": key}
                    ).fetchone()
                    
                    if not existing_config:
                        # 配置不存在，插入新配置
                        session.execute(
                            text("INSERT INTO system_config (key, value, description) VALUES (:key, :value, :description)"),
                            {
                                "key": key,
                                "value": value,
                                "description": description
                            }
                        )
                        inserted_count += 1
                except Exception as e:
                    logger.error(f"插入配置失败: key={key}, value={value}, error={e}")
            
            # 提交事务
            session.commit()
        
        logger.info(f"默认配置插入完成，新增配置数: {inserted_count}")
        
        # 验证默认配置是否插入成功
        with Session(engine) as session:
            config_count = session.execute(text("SELECT COUNT(*) FROM system_config")).fetchone()[0]
        logger.info(f"系统配置表中配置数量: {config_count}")
        
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        logger.exception(e)  # 记录完整的异常堆栈
        raise
