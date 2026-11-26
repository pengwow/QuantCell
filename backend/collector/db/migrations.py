#!/usr/bin/env python3
"""
数据库表结构迁移脚本

用于管理和更新数据库表结构，确保表结构与模型定义保持一致
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 导入SessionLocal以正确创建session
try:
    from collector.db.database import SessionLocal
except ImportError:
    # 如果导入失败，使用默认的Session类
    SessionLocal = Session


def add_missing_columns_from_models(session: Session, db_type: str) -> None:
    """通用兜底迁移：对照模型 Base.metadata，为已存在的表补齐缺失列/索引。

    动机（2026-11-18 桌面打包实录）：worker.Worker 新增 owner_id 只改了模型
    没写迁移，桌面存量库 create_all 不改已存在的表 → GET /api/v1/workers
    500。逐表手写 update_xxx_table 每加一列都要记得补一行，必然再漏。

    ponytail: 天花板=仅做「加列/加索引」这类可幂等叠加的变更；改名、删列、
    改类型、约束收紧无法自动推导，仍需专用迁移
    （update_kline_volume_to_decimal、rename_kline_interval_columns 等）。
    """
    from sqlalchemy import inspect as sa_inspect

    # 与 init_db 相同的模型注册前置:metadata 必须含有全部模型,
    # 否则 sorted_tables/FK 解析会因缺表引用报 NoReferencedTableError
    import agent.models
    import backtest.models
    import factor.models
    import indicators.models  # 2026-11-20 实录：漏这一行，indicators/indicator_versions/

    # indicator_alert_rules 三表整域不进 metadata，补列通道静默跳过（该域永远拿不到新列）
    import strategy.models
    from collector.db.database import Base

    if db_type not in ("sqlite", "duckdb"):
        logger.info(f"add_missing_columns: 方言 {db_type} 不支持通用补列，跳过")
        return

    inspector = sa_inspect(session.get_bind())
    try:
        existing_tables = set(inspector.get_table_names())
    except Exception as e:
        logger.warning(f"add_missing_columns: 读取表清单失败，跳过（{e}）")
        return

    added = 0
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        try:
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            existing_ix = {ix["name"] for ix in inspector.get_indexes(table.name)}
        except Exception as e:
            logger.warning(f"add_missing_columns: 读取 {table.name} 结构失败，跳过（{e}）")
            continue

        for col in table.columns:
            if col.name in existing_cols:
                continue
            coltype = col.type.compile(inspector.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
            if col.server_default is not None:
                ddl += f" DEFAULT {_render_server_default(col.server_default.arg, inspector.dialect)}"
            elif not col.nullable:
                logger.warning(
                    f"add_missing_columns: {table.name}.{col.name} 为 NOT NULL 且无默认值，"
                    "跳过自动补列（需要专用迁移，存量行无法安全填值）"
                )
                continue
            session.execute(text(ddl))
            added += 1
            logger.info(f"add_missing_columns: 表 {table.name} 补齐缺失列 {col.name}")

        # 模型里有、旧库没有的索引（如 owner_id 的 index=True）
        for ix in table.indexes:
            if ix.name in existing_ix or not ix.columns:
                continue
            cols = ", ".join(f'"{c.name}"' for c in ix.columns)
            session.execute(text(f'CREATE INDEX IF NOT EXISTS "{ix.name}" ON "{table.name}" ({cols})'))
            logger.info(f"add_missing_columns: 表 {table.name} 补建索引 {ix.name}")

    if added:
        logger.info(f"add_missing_columns: 共补齐 {added} 个缺失列")


def _render_server_default(default_arg: object, dialect) -> str:
    """把模型的 server_default 渲染成可拼进 ALTER TABLE 的 SQL 片段。

    2026-11-20 实录：原实现把 TextClause 当 SQL、其余一律加引号，于是
    `server_default=func.now()`（Function，不是 TextClause）被写成
    `DEFAULT 'now()'` —— 一个字面量字符串。SQLite 照单全收，此后该表任何
    INSERT 都把 "now()" 填进 DATETIME 列，SQLAlchemy 读回时抛
    `Invalid isoformat string: 'now()'`，整条写入静默失败
    （indicator_versions 因此六条指标、零个版本快照）。

    修正：任何 ColumnElement（text()/func.*/常量表达式）交方言编译
    （sqlite 下 func.now() → CURRENT_TIMESTAMP），裸标量才当值加引号。
    """
    from sqlalchemy.sql.elements import ClauseElement

    if isinstance(default_arg, ClauseElement):
        return str(default_arg.compile(dialect=dialect))
    return "'" + str(default_arg).replace("'", "''") + "'"


def repair_literal_now_defaults(session: Session, db_type: str) -> None:
    """修复补列通道旧实现留下的 `DEFAULT 'now()'` 字面量默认值（存量库）。

    症状：该表任何 INSERT 都把字符串 "now()" 写进 DATETIME 列，SQLAlchemy
    读回抛 `Invalid isoformat string: 'now()'`，整条写入失败 —— 调用方通常
    只看到"保存成功但查不到"（indicator_versions 版本快照即此）。

    SQLite 不能改列默认值，只能重建表：复用 sqlite_master 里的原建表语句，
    把字面量换成 CURRENT_TIMESTAMP 建同构临时表 → 整表 COPY → 删原表 →
    改名 → 重建索引。行数据（若有）原样保留。

    ponytail: 天花板=只处理 sqlite，且只认 "DEFAULT 'now()'" 这一种畸形；
    将来若发现别的函数默认值被误引号化，往同一替换表里加一条即可。
    """
    if db_type != "sqlite":
        return
    broken = "DEFAULT 'now()'"
    tables = session.execute(
        text("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE :pat"),
        {"pat": "%DEFAULT 'now()'%"},
    ).fetchall()
    for name, ddl in tables:
        if not ddl or broken not in ddl:
            continue
        # 索引 SQL 先留档：DROP TABLE 会连带删掉它们，改名后按原文重建
        index_sql = [
            row[0]
            for row in session.execute(
                text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"),
                {"t": name},
            ).fetchall()
        ]
        tmp = f"{name}__nowfix"
        fixed = ddl.replace(broken, "DEFAULT CURRENT_TIMESTAMP")
        # 只换建表语句里的表名（首个），避免列名/约束名误伤
        quoted, bare = f'"{name}"', f"CREATE TABLE {name} "
        session.execute(text(f'DROP TABLE IF EXISTS "{tmp}"'))
        session.execute(
            text(
                fixed.replace(quoted, f'"{tmp}"', 1)
                if quoted in fixed
                else fixed.replace(bare, f'CREATE TABLE "{tmp}" ', 1)
            )
        )
        session.execute(text(f'INSERT INTO "{tmp}" SELECT * FROM "{name}"'))
        session.execute(text(f'DROP TABLE "{name}"'))
        session.execute(text(f'ALTER TABLE "{tmp}" RENAME TO "{name}"'))
        for sql in index_sql:
            session.execute(text(sql))
        logger.warning(f"repair_literal_now_defaults: 重建 {name}（DEFAULT 'now()' → CURRENT_TIMESTAMP）")


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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='data_pools' AND column_name='is_public'"
                )
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pools') WHERE name='is_public'")
            ).fetchone()

        if not column_exists:
            logger.info("添加is_public列...")
            session.execute(text("ALTER TABLE data_pools ADD COLUMN is_public BOOLEAN DEFAULT TRUE"))
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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='data_pools' AND column_name='is_default'"
                )
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('data_pools') WHERE name='is_default'")
            ).fetchone()

        if not column_exists:
            logger.info("添加is_default列...")
            session.execute(text("ALTER TABLE data_pools ADD COLUMN is_default BOOLEAN DEFAULT FALSE"))
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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='data_pool_assets' AND column_name='id'"
                )
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
                text(
                    "CREATE TABLE data_pool_assets_new (id INTEGER PRIMARY KEY AUTOINCREMENT, pool_id INTEGER NOT NULL, asset_id VARCHAR NOT NULL, asset_type VARCHAR, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (pool_id) REFERENCES data_pools(id))"
                )
            )

            # 2. 复制旧表数据到新表，只复制实际存在的列，updated_at使用默认值
            session.execute(
                text(
                    "INSERT INTO data_pool_assets_new (pool_id, asset_id, asset_type, created_at) SELECT pool_id, asset_id, asset_type, created_at FROM data_pool_assets"
                )
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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='plugin'"
                )
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='plugin'")
            ).fetchone()

        if not column_exists:
            logger.info("添加plugin列...")
            session.execute(text("ALTER TABLE system_config ADD COLUMN plugin VARCHAR"))
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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='name'"
                )
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='name'")
            ).fetchone()

        if not column_exists:
            logger.info("添加name列...")
            session.execute(text("ALTER TABLE system_config ADD COLUMN name VARCHAR"))
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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='is_sensitive'"
                )
            ).fetchone()
        else:
            # 默认使用SQLite语法，处理db_type为None的情况
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('system_config') WHERE name='is_sensitive'")
            ).fetchone()

        if not column_exists:
            logger.info("添加is_sensitive列...")
            session.execute(text("ALTER TABLE system_config ADD COLUMN is_sensitive BOOLEAN DEFAULT FALSE"))
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
                    except Exception:
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
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name='crypto_future_klines' AND column_name='data_source'"
                    )
                ).fetchone()

            if not column_exists:
                logger.info("为crypto_future_klines表添加data_source列...")
                # 添加data_source列
                session.execute(
                    text(
                        "ALTER TABLE crypto_future_klines ADD COLUMN data_source VARCHAR(50) NOT NULL DEFAULT 'unknown'"
                    )
                )
                # 创建索引
                session.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_crypto_future_klines_data_source ON crypto_future_klines(data_source)"
                    )
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
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name='stock_klines' AND column_name='data_source'"
                    )
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


def update_share_tokens_table(session: Session, db_type: str) -> None:
    """更新 share_tokens 表结构

    为分享系统补齐远端分发（quantcell.top）相关字段。
    与 backend.share.models.ShareToken 定义保持一致。
    - remote_id: 远端主键（可空）
    - short_url: 公开短链（可空）
    - remote_status: 推送状态枚举，默认 PENDING
    - remote_error: 失败时脱敏错误信息（可空）

    Args:
        session: SQLAlchemy 会话
        db_type: 数据库类型（sqlite / duckdb）
    """
    logger.info("开始更新 share_tokens 表结构...")

    # 1. 检查表是否存在
    table_exists = False
    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='share_tokens'")
            ).fetchone()
        elif db_type == "duckdb":
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='share_tokens'")
            ).fetchone()
        else:
            # 默认 sqlite 语法
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='share_tokens'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查 share_tokens 表是否存在失败: {e}")
        return

    if not table_exists:
        logger.info("share_tokens 表不存在，跳过更新（表结构由 SQLAlchemy 在首次创建时建好）")
        return

    # 2. 通用辅助：检查并添加列（幂等）
    def _ensure_column(column_name: str, ddl: str, *, has_default: bool = False) -> None:
        """若列不存在则执行 ddl 添加；添加后再补建索引（如果 ddl 中带 INDEX）"""
        try:
            exists = False
            if db_type in ("sqlite", None, ""):
                exists = session.execute(
                    text("SELECT name FROM pragma_table_info('share_tokens') WHERE name=:c"),
                    {"c": column_name},
                ).fetchone()
            elif db_type == "duckdb":
                exists = session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='share_tokens' AND column_name=:c"
                    ),
                    {"c": column_name},
                ).fetchone()
            if exists:
                logger.info(f"share_tokens.{column_name} 列已存在，跳过")
                return
            logger.info(f"为 share_tokens 添加 {column_name} 列...")
            session.execute(text(ddl))
            logger.info(f"share_tokens.{column_name} 列添加成功")
        except Exception as e:
            logger.error(f"添加 share_tokens.{column_name} 列失败: {e}")

    # remote_id: VARCHAR(64)，可空
    _ensure_column(
        "remote_id",
        "ALTER TABLE share_tokens ADD COLUMN remote_id VARCHAR(64)",
    )
    # 为 remote_id 建索引（idx_share_tokens_remote_id）
    try:
        if db_type in ("sqlite", None, ""):
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_share_tokens_remote_id ON share_tokens(remote_id)"))
    except Exception as e:
        logger.error(f"创建 idx_share_tokens_remote_id 索引失败: {e}")

    # short_url: VARCHAR(512)，可空
    _ensure_column(
        "short_url",
        "ALTER TABLE share_tokens ADD COLUMN short_url VARCHAR(512)",
    )

    # remote_status: VARCHAR(16)，NOT NULL DEFAULT 'PENDING'
    # 注意：SQLite 的 ALTER TABLE ADD COLUMN 不支持在 NOT NULL 时使用常量 DEFAULT 时带括号外的引号
    _ensure_column(
        "remote_status",
        "ALTER TABLE share_tokens ADD COLUMN remote_status VARCHAR(16) NOT NULL DEFAULT 'PENDING'",
    )

    # remote_error: VARCHAR(512)，可空
    _ensure_column(
        "remote_error",
        "ALTER TABLE share_tokens ADD COLUMN remote_error VARCHAR(512)",
    )

    logger.info("share_tokens 表结构更新完成")


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
            session.execute(
                text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password_hash VARCHAR(128) NOT NULL,
                    nickname VARCHAR(100),
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME
                )
            """)
            )
            session.execute(text("CREATE INDEX ix_users_id ON users(id)"))
            session.execute(text("CREATE INDEX ix_users_username ON users(username)"))
            session.execute(text("CREATE INDEX ix_users_is_active ON users(is_active)"))
        elif db_type == "duckdb":
            session.execute(
                text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password_hash VARCHAR(128) NOT NULL,
                    nickname VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            )
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
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='system_config' AND column_name='user_id'"
                )
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
            session.execute(
                text("""
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
            """)
            )

            # 2. 复制旧表数据到新表，user_id设为NULL（系统级配置）
            try:
                session.execute(
                    text("""
                    INSERT INTO system_config_new (key, value, description, name, plugin, is_sensitive, created_at, updated_at)
                    SELECT key, value, description, name, plugin, is_sensitive, created_at, updated_at
                    FROM system_config
                """)
                )
            except Exception as copy_e:
                logger.warning(f"复制数据时出错，尝试兼容旧表结构: {copy_e}")
                # 兼容没有name、plugin、is_sensitive列的旧表
                try:
                    session.execute(
                        text("""
                        INSERT INTO system_config_new (key, value, description, created_at, updated_at)
                        SELECT key, value, description, created_at, updated_at
                        FROM system_config
                    """)
                    )
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


def create_leverage_brackets_table(session: Session, db_type: str) -> None:
    """创建杠杆档位表（如果不存在）

    表结构由 collector.db.models.LeverageBracket 定义；正常启动时 create_all 已建好，
    这里兜底老库升级（无 create_all 的场景）。

    Args:
        session: SQLAlchemy会话对象
        db_type: 数据库类型（sqlite或duckdb）
    """
    logger.info("检查leverage_brackets表是否存在...")

    try:
        if db_type == "sqlite":
            session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS leverage_brackets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol VARCHAR(32) NOT NULL UNIQUE,
                    market VARCHAR(8) NOT NULL DEFAULT 'um',
                    brackets_json TEXT NOT NULL,
                    collected_at DATETIME NOT NULL
                )
            """)
            )
            session.execute(text("CREATE INDEX IF NOT EXISTS ix_leverage_brackets_symbol ON leverage_brackets(symbol)"))
        elif db_type == "duckdb":
            session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS leverage_brackets (
                    id INTEGER PRIMARY KEY,
                    symbol VARCHAR(32) NOT NULL UNIQUE,
                    market VARCHAR(8) NOT NULL DEFAULT 'um',
                    brackets_json TEXT NOT NULL,
                    collected_at TIMESTAMP NOT NULL
                )
            """)
            )
        logger.info("leverage_brackets表创建成功（或已存在）")
    except Exception as e:
        logger.error(f"创建leverage_brackets表失败: {e}")


def update_ai_models_table(session: Session, db_type: str) -> None:
    """为 ai_models 增加 category 列（system_one / system_two 分型）。

    存量行由 DEFAULT 归入 system_two（生成式语义不变），幂等可重跑。
    """
    logger.info("开始更新 ai_models 表结构（category 列）...")

    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_models'")
            ).fetchone()
        else:
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='ai_models'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查 ai_models 表是否存在失败: {e}")
        return

    if not table_exists:
        logger.info("ai_models 表不存在（首次建库由 create_all 负责），跳过 category 迁移")
        return

    try:
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('ai_models') WHERE name='category'")
            ).fetchone()
        else:
            column_exists = session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='ai_models' AND column_name='category'"
                )
            ).fetchone()

        if column_exists:
            logger.info("ai_models.category 列已存在，跳过")
            return

        session.execute(text("ALTER TABLE ai_models ADD COLUMN category VARCHAR(16) DEFAULT 'system_two'"))
        session.commit()
        logger.info("ai_models.category 列添加成功（存量行默认 system_two）")
    except Exception as e:
        logger.error(f"添加 ai_models.category 列失败: {e}")


def update_worker_positions_table(session: Session, db_type: str) -> None:
    """为 worker_positions 增加交易所富化列（杠杆/两平价/强平价/保证金比率）。

    live/testnet 由 LiveTradeSync.sync_positions 填充，paper 恒 NULL（前端显示 —）。
    幂等可重跑；第一次跑交易 tab 仓位页签上线时执行。
    """
    logger.info("开始更新 worker_positions 表结构（交易所富化列）...")

    try:
        if db_type == "sqlite":
            table_exists = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='worker_positions'")
            ).fetchone()
        else:
            table_exists = session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='worker_positions'")
            ).fetchone()
    except Exception as e:
        logger.error(f"检查 worker_positions 表是否存在失败: {e}")
        return

    if not table_exists:
        logger.info("worker_positions 表不存在（首次建库由 create_all 负责），跳过富化列迁移")
        return

    # (列名, SQLite DDL)——PriceAsFloat 数值口径用 REAL，NULL 允许缺失
    columns = [
        ("leverage", "ALTER TABLE worker_positions ADD COLUMN leverage REAL"),
        ("breakeven_price", "ALTER TABLE worker_positions ADD COLUMN breakeven_price REAL"),
        ("liquidation_price", "ALTER TABLE worker_positions ADD COLUMN liquidation_price REAL"),
        ("margin_ratio", "ALTER TABLE worker_positions ADD COLUMN margin_ratio REAL"),
    ]
    for name, ddl in columns:
        try:
            if db_type == "sqlite":
                column_exists = session.execute(
                    text(f"SELECT name FROM pragma_table_info('worker_positions') WHERE name='{name}'")
                ).fetchone()
            else:
                column_exists = session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name='worker_positions' AND column_name='{name}'"
                    )
                ).fetchone()

            if column_exists:
                logger.info(f"worker_positions.{name} 列已存在，跳过")
                continue

            session.execute(text(ddl))
            session.commit()
            logger.info(f"worker_positions.{name} 列添加成功")
        except Exception as e:
            logger.error(f"添加 worker_positions.{name} 列失败: {e}")


def update_indicator_alert_rules_table(session, db_type: str) -> None:
    """indicator_alert_rules 增加 builtin_id 列（系统内置指标提醒，indicators/builtin_alerts.py）。"""
    table_exists = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='indicator_alert_rules'")
        if db_type == "sqlite"
        else text("SELECT table_name FROM information_schema.tables WHERE table_name='indicator_alert_rules'")
    ).fetchone()
    if not table_exists:
        logger.info("indicator_alert_rules 表不存在（首次建库由 create_all 负责），跳过 builtin_id 迁移")
        return

    try:
        if db_type == "sqlite":
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('indicator_alert_rules') WHERE name='builtin_id'")
            ).fetchone()
        else:
            column_exists = session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='indicator_alert_rules' AND column_name='builtin_id'"
                )
            ).fetchone()

        if column_exists:
            logger.info("indicator_alert_rules.builtin_id 列已存在，跳过")
            return

        session.execute(text("ALTER TABLE indicator_alert_rules ADD COLUMN builtin_id VARCHAR(50)"))
        session.commit()
        logger.info("indicator_alert_rules.builtin_id 列添加成功")
    except Exception as e:
        logger.error(f"添加 indicator_alert_rules.builtin_id 列失败: {e}")


def rename_kline_interval_columns(session: Session, db_type: str) -> None:
    """历史 K线周期列统一改名 interval：features.freq → interval、indicator_alert_rules.period → interval。

    vocab.py P2-10：应用面 ORM 属性早已是 interval，本迁移把存量库的物理列名一并对齐。
    表不存在（首次建库由 create_all 以 interval 直建）或新列已存在时幂等跳过。
    """
    renames = [
        ("features", "freq"),
        ("indicator_alert_rules", "period"),
    ]
    for table, legacy_col in renames:
        table_exists = session.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if db_type == "sqlite"
            else text(f"SELECT table_name FROM information_schema.tables WHERE table_name='{table}'")
        ).fetchone()
        if not table_exists:
            logger.info(f"{table} 表不存在（新库由 create_all 直建 interval），跳过 {legacy_col} 改名")
            continue

        try:
            if db_type == "sqlite":
                old_col = session.execute(
                    text(f"SELECT name FROM pragma_table_info('{table}') WHERE name='{legacy_col}'")
                ).fetchone()
            else:
                old_col = session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name='{table}' AND column_name='{legacy_col}'"
                    )
                ).fetchone()

            if not old_col:
                logger.info(f"{table}.{legacy_col} 列不存在（已改名为 interval），跳过")
                continue

            # SQLite(>=3.25)/DuckDB/PG 均支持 RENAME COLUMN；interval 引号防 DuckDB 保留字
            session.execute(text(f'ALTER TABLE {table} RENAME COLUMN {legacy_col} TO "interval"'))
            session.commit()
            logger.info(f"{table}.{legacy_col} 列已改名为 interval")
        except Exception as e:
            logger.error(f"重命名 {table}.{legacy_col} → interval 失败: {e}")
            raise


def update_kline_volume_to_decimal(session: Session, db_type: str) -> None:
    """K线三表 volume 列从 String 重建为 DECIMAL(40, 8)（P2-4 B-11）。

    SQLite/DuckDB 均不支持 ALTER COLUMN TYPE，且旧 String 列的存量 K 线数据
    允许丢弃（可由交易所 REST/websocket 重新拉取），因此直接 DROP 后按当前
    ORM 定义重建。新库的表已由 create_all 按 DECIMAL 建好，此处自动跳过（幂等）。

    models 在函数内导入：迁移模块先于全量模型注册执行，顶部导入会拉起
    worker 全模型链导致 mapper 过早 configure。
    """
    from sqlalchemy import Numeric
    from sqlalchemy import inspect as sa_inspect

    from . import models

    kline_tables = [
        ("crypto_spot_klines", models.CryptoSpotKline),
        ("crypto_future_klines", models.CryptoFutureKline),
        ("stock_klines", models.StockKline),
    ]
    bind = session.get_bind()
    inspector = sa_inspect(bind)
    for table_name, model in kline_tables:
        if not inspector.has_table(table_name):
            logger.info(f"{table_name} 表不存在（首次建库由 create_all 负责），跳过 volume 类型迁移")
            continue
        cols = {c["name"]: c["type"] for c in inspector.get_columns(table_name)}
        if isinstance(cols.get("volume"), Numeric):
            logger.info(f"{table_name}.volume 已是 DECIMAL，跳过")
            continue
        logger.warning(f"{table_name}.volume 为 {cols.get('volume')!r}，删除旧表并按新模型重建（存量K线数据丢弃）")
        session.execute(text(f"DROP TABLE {table_name}"))
        # SQLite 的 DDL 参与事务：先提交 DROP，create() 在新连接上才看得到旧表已删除
        session.commit()
        model.__table__.create(bind=bind)
        logger.info(f"{table_name} 重建完成（volume DECIMAL(40, 8)）")


def update_kline_ohlc_to_decimal(session: Session, db_type: str) -> None:
    """K线三表 OHLC 四列从 String 重建为 DECIMAL(40, 8)（P2-11 价格域收口）。

    策略与 update_kline_volume_to_decimal（P2-4 B-11）一致：旧 String 列的存量
    K线允许丢弃（可由交易所/数据源重新拉取），直接 DROP 后按当前 ORM 重建；
    新库已由 create_all 按 DECIMAL 建好，此处自动跳过（幂等）。timestamp 列
    仍为纳秒字符串，不在价格域范围内，不动。

    models 在函数内导入：迁移模块先于全量模型注册执行，顶部导入会拉起
    worker 全模型链导致 mapper 过早 configure。
    """
    from sqlalchemy import Numeric
    from sqlalchemy import inspect as sa_inspect

    from . import models

    kline_tables = [
        ("crypto_spot_klines", models.CryptoSpotKline),
        ("crypto_future_klines", models.CryptoFutureKline),
        ("stock_klines", models.StockKline),
    ]
    ohlc_cols = ("open", "high", "low", "close")
    bind = session.get_bind()
    inspector = sa_inspect(bind)
    for table_name, model in kline_tables:
        if not inspector.has_table(table_name):
            logger.info(f"{table_name} 表不存在（首次建库由 create_all 负责），跳过 OHLC 类型迁移")
            continue
        cols = {c["name"]: c["type"] for c in inspector.get_columns(table_name)}
        if all(isinstance(cols.get(c), Numeric) for c in ohlc_cols):
            logger.info(f"{table_name}.OHLC 已是 DECIMAL，跳过")
            continue
        logger.warning(f"{table_name} OHLC 存在非 DECIMAL 列，删除旧表并按新模型重建（存量K线数据丢弃）")
        session.execute(text(f"DROP TABLE {table_name}"))
        # SQLite 的 DDL 参与事务：先提交 DROP，create() 在新连接上才看得到旧表已删除
        session.commit()
        model.__table__.create(bind=bind)
        logger.info(f"{table_name} 重建完成（OHLC DECIMAL(40, 8)）")


def update_kline_timestamp_to_bigint(session: Session, db_type: str) -> None:
    """K线三表 timestamp 列从 String 重建为 BigInteger 纳秒整型（P2-14 数值收口）。

    策略与 update_kline_ohlc_to_decimal（P2-11）一致：旧 String 列的存量 K线
    允许丢弃（可由交易所/数据源重新拉取），直接 DROP 后按当前 ORM 重建；
    新库已由 create_all 按 BigInteger 建好，此处自动跳过（幂等）。唯一键
    unique_kline 内嵌的时间戳文本随 DataAdapter 一并按纳秒重新生成，不在
    本迁移中做数据搬迁。

    models 在函数内导入：迁移模块先于全量模型注册执行，顶部导入会拉起
    worker 全模型链导致 mapper 过早 configure。
    """
    from sqlalchemy import BigInteger
    from sqlalchemy import inspect as sa_inspect

    from . import models

    kline_tables = [
        ("crypto_spot_klines", models.CryptoSpotKline),
        ("crypto_future_klines", models.CryptoFutureKline),
        ("stock_klines", models.StockKline),
    ]
    bind = session.get_bind()
    inspector = sa_inspect(bind)
    for table_name, model in kline_tables:
        if not inspector.has_table(table_name):
            logger.info(f"{table_name} 表不存在（首次建库由 create_all 负责），跳过 timestamp 类型迁移")
            continue
        cols = {c["name"]: c["type"] for c in inspector.get_columns(table_name)}
        if isinstance(cols.get("timestamp"), BigInteger):
            logger.info(f"{table_name}.timestamp 已是 BIGINT，跳过")
            continue
        logger.warning(
            f"{table_name}.timestamp 为 {cols.get('timestamp')!r}，删除旧表并按新模型重建（存量K线数据丢弃）"
        )
        session.execute(text(f"DROP TABLE {table_name}"))
        # SQLite 的 DDL 参与事务：先提交 DROP，create() 在新连接上才看得到旧表已删除
        session.commit()
        model.__table__.create(bind=bind)
        logger.info(f"{table_name} 重建完成（timestamp BIGINT 纳秒整型）")


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

            # K线三表 volume 列 String→DECIMAL 重建（P2-4 B-11，旧数据可删）
            update_kline_volume_to_decimal(session, db_type)

            # K线三表 OHLC 四列 String→DECIMAL 重建（P2-11 价格域收口，旧数据可删）
            update_kline_ohlc_to_decimal(session, db_type)

            # K线三表 timestamp 列 String→BIGINT 纳秒整型重建（P2-14 数值收口，旧数据可删）
            update_kline_timestamp_to_bigint(session, db_type)

            # 更新 share_tokens 表结构，补齐远端分发相关列
            update_share_tokens_table(session, db_type)

            # 创建杠杆档位表（保证金回测的档位数据源）
            create_leverage_brackets_table(session, db_type)

            # 更新 ai_models 表结构，添加 category 列（system_one/system_two 分型）
            update_ai_models_table(session, db_type)

            # 作业租约影子列（多 worker 部署判活/跨进程 cancel+pause，factor/job_lease.py）
            from factor.job_lease import ensure_lease_columns

            ensure_lease_columns(session, db_type)

            # indicator_alert_rules 增加 builtin_id 列（系统内置指标提醒）
            update_indicator_alert_rules_table(session, db_type)
            update_worker_positions_table(session, db_type)

            # 历史 K线周期列统一改名 interval（features.freq / indicator_alert_rules.period）
            rename_kline_interval_columns(session, db_type)

            # 通用兜底：对照模型补齐遗漏的加列型迁移（桌面实录：owner_id 漏迁）
            add_missing_columns_from_models(session, db_type)

            # 补列通道旧实现把 func.now() 写成字符串默认值的表重建
            # （否则 INSERT 全部失败：Invalid isoformat string: 'now()'）
            repair_literal_now_defaults(session, db_type)

            # 提交所有更改
            session.commit()
            logger.info("所有迁移脚本执行成功")
    except Exception as e:
        logger.error(f"执行迁移脚本失败: {e}")
        # 回滚事务
        if "session" in locals():
            session.rollback()
        raise
