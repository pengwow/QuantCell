"""SQLAlchemy数据库连接配置

按照FastAPI官方文档标准结构，配置SQLAlchemy数据库连接
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# 数据库文件默认路径
default_db_path = Path(__file__).parent.parent.parent / "data" / "qbot.db"

# 确保数据库目录存在
default_db_path.parent.mkdir(parents=True, exist_ok=True)

# 延迟初始化的全局变量
db_type = None
db_url = None
engine = None

# 创建会话工厂
# autocommit=False: 不自动提交事务
# autoflush=False: 不自动刷新会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False)

# 初始化数据库配置

def init_database_config():
    """初始化数据库配置
    
    延迟加载配置，避免循环导入问题
    支持从环境变量或默认配置读取数据库类型
    """
    # 声明global变量
    global db_type, db_url, engine
    
    # 只初始化一次
    if engine is not None:
        return
    
    # 从环境变量读取数据库类型和文件路径，支持配置文件覆盖
    # 避免调用get_config()，防止循环导入
    import os
    
    # 优先从环境变量读取配置
    db_type = os.environ.get("DB_TYPE", "duckdb")  # 默认使用duckdb
    db_file = os.environ.get("DB_FILE", str(default_db_path))
    
    # 构建数据库URL
    if db_type == "sqlite":
        # SQLite数据库URL格式
        db_url = f"sqlite:///{db_file}"
    elif db_type == "duckdb":
        # DuckDB数据库URL格式
        db_url = f"duckdb:///{db_file}"
    else:
        # 默认使用SQLite
        db_url = f"sqlite:///{db_file}"
    
    # 创建SQLAlchemy引擎
    # 根据数据库类型动态设置connect_args
    connect_args = {}
    if db_type == "sqlite":
        # SQLite特定配置，允许同一连接在不同线程中使用
        connect_args["check_same_thread"] = False
    elif db_type == "duckdb":
        # DuckDB特定配置，只使用最基本的配置
        connect_args = {
            "read_only": False,
            "config": {
                "enable_external_access": "true",
                "enable_object_cache": "true",
            }
        }
    
    engine = create_engine(
        db_url,
        connect_args=connect_args
    )
    
    # 配置SessionLocal的bind参数
    SessionLocal.configure(bind=engine)

# 创建基础模型类
# 所有SQLAlchemy模型都将继承自这个类
Base = declarative_base()



def get_db():
    """获取数据库会话依赖
    
    用于FastAPI路径操作函数中获取数据库会话
    确保会话在使用后正确关闭
    
    Yields:
        Session: SQLAlchemy数据库会话
    """
    # 确保数据库配置已初始化
    init_database_config()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()