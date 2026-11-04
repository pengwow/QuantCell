import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging.config import fileConfig

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from collector.db.database import Base, init_database_config

# 初始化数据库配置
init_database_config()

# 初始化后再导入engine，确保engine已被正确创建
# 导入所有模型，确保它们被注册到Base.metadata中
from collector.db.database import engine

# 设置target_metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    from collector.db.database import db_url

    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _bootstrap_empty_database(connection) -> bool:
    """空库初始化：本仓库初始迁移（1a960941d752）是 NOOP，历史 schema 由
    `Base.metadata.create_all()` 建立，因此空库直接 `alembic upgrade head` 会在
    2 号迁移处因缺表失败。这里对“除 alembic_version 外无任何表”的空库做一次
    create_all 并把版本直接标到当前 head，之后 upgrade 为幂等无操作。

    说明：这是项目历史约定（create_all 是 schema 真相源，alembic 只负责增量补丁），
    不适用于已经存在业务表的库；离线模式（--sql）跳过。
    """
    if not inspect(connection).get_table_names():
        Base.metadata.create_all(bind=connection)
        head = ScriptDirectory.from_config(config).get_current_head()
        if head is None:
            raise RuntimeError("alembic 没有可用的 head，无法初始化空库")
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        )
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head})
        connection.commit()
        print(f"[alembic] 空库已按当前模型建表，版本标记为 head={head}")
        return True
    return False


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # 使用项目的engine
    connectable = engine

    with connectable.connect() as connection:
        _bootstrap_empty_database(connection)
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()
        # SQLite 的 DDL 是非事务性的（transactional_ddl=False），版本表的 UPDATE
        # 会被 pysqlite 包进隐式事务，连接关闭即回滚：表现为“表已建好，版本还停在旧值”。
        # 这里显式提交兜住版本写入；对其它 dialect 是幂等空操作。
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
