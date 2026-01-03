#!/usr/bin/env python3
"""
运行数据库迁移脚本
"""

from collector.db.database import init_database_config, SessionLocal
from collector.db.migrations import update_data_pools_table, update_data_pool_assets_table
from collector.db.database import db_type

def main():
    """运行迁移"""
    init_database_config()
    db = SessionLocal()
    try:
        update_data_pools_table(db, db_type)
        update_data_pool_assets_table(db, db_type)
        db.commit()
        print("迁移成功")
    except Exception as e:
        db.rollback()
        print(f"迁移失败: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
