# 数据库连接管理

import duckdb
import os
from pathlib import Path
from loguru import logger

# 数据库文件路径
db_path = Path(__file__).parent.parent.parent / "data" / "system.db"

# 确保数据库目录存在
db_path.parent.mkdir(parents=True, exist_ok=True)


class DuckDBConnection:
    """DuckDB数据库连接管理类
    
    实现单例模式，确保全局只有一个数据库连接实例
    """
    _instance = None
    
    def __new__(cls):
        """创建单例实例
        
        Returns:
            DuckDBConnection: 数据库连接实例
        """
        if cls._instance is None:
            cls._instance = super(DuckDBConnection, cls).__new__(cls)
            cls._instance._conn = None
        return cls._instance
    
    def connect(self):
        """建立数据库连接
        
        Returns:
            duckdb.DuckDBPyConnection: 数据库连接对象
        """
        if self._conn is None:
            logger.info(f"正在连接数据库: {db_path}")
            self._conn = duckdb.connect(str(db_path))
            logger.info(f"数据库连接成功: {db_path}")
        return self._conn
    
    def close(self):
        """关闭数据库连接
        """
        if self._conn is not None:
            logger.info(f"正在关闭数据库连接: {db_path}")
            self._conn.close()
            self._conn = None
            logger.info(f"数据库连接已关闭: {db_path}")


# 创建全局数据库连接实例
db_instance = DuckDBConnection()


def get_db_connection():
    """获取数据库连接
    
    Returns:
        duckdb.DuckDBPyConnection: 数据库连接对象
    """
    return db_instance.connect()


def init_db():
    """初始化数据库，创建所需的表
    
    创建系统配置表，用于存储系统配置参数
    """
    conn = get_db_connection()
    
    try:
        # 创建系统配置表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            key VARCHAR PRIMARY KEY,
            value VARCHAR NOT NULL,
            description VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # DuckDB目前不支持触发器，移除触发器创建语句
        
        # 插入默认配置
        default_configs = [
            ("data_download_dir", str(Path.home() / ".qlib" / "crypto_data" / "source"), "数据下载目录"),
            ("qlib_data_dir", str(Path.home() / ".qlib" / "crypto_data" / "qlib"), "QLib数据目录"),
            ("current_market_type", "crypto", "当前交易模式: crypto(加密货币) 或 stock(股票)"),
            ("crypto_candle_type", "spot", "加密货币蜡烛图类型: spot(现货) 或 futures(期货)"),
            ("default_exchange", "binance", "默认交易所"),
            ("default_interval", "1d", "默认时间间隔"),
            ("max_workers", "4", "最大工作线程数")
        ]
        
        # 使用UPSERT插入默认配置
        for key, value, description in default_configs:
            conn.execute("""
            INSERT INTO system_config (key, value, description)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO NOTHING
            """, (key, value, description))
        
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise
