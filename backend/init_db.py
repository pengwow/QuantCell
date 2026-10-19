#!/usr/bin/env python3
"""初始化数据库脚本（全新环境一键建库：建表 + 迁移 + 补齐独立 Base 的表）

为什么不能只调 init_db()：思维链（thinking_chains）和策略历史（strategy_history）
两个模型模块为了避免循环导入各自新建了 declarative Base，不在
collector.db.database.Base.metadata 里，init_db() 的 create_all 覆盖不到；
全新库上这两个模块的接口会直接报 "no such table"。此前只在开发者本机
（历史 alembic 迁移建过表）才正常，本脚本负责把这个缺口补上。
"""

import sys


def create_aux_tables() -> None:
    """创建共享 Base 之外的两张表（create_all 幂等，可重复执行）"""
    # 延迟导入：ai.strategy 包的 __init__ 会拉起路由/生成器等业务模块，
    # 必须在 init_db() 建好主表之后再导入，避免导入期就访问还不存在的表。
    from ai.strategy.strategy_history_models import Base as StrategyHistoryBase
    from ai.strategy.thinking_chain_models import Base as ThinkingChainBase
    from collector.db.database import engine

    ThinkingChainBase.metadata.create_all(bind=engine)
    StrategyHistoryBase.metadata.create_all(bind=engine)


if __name__ == "__main__":
    try:
        from collector.db import init_db

        init_db()
        create_aux_tables()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
