"""
添加 strategy_name 列到 workers 表
"""
import sys
sys.path.insert(0, '.')

import os
os.environ.setdefault('DATABASE_TYPE', 'sqlite')

from collector.db.database import SessionLocal, Base, engine as db_engine
from worker.models import Worker
from sqlalchemy import text, inspect

def upgrade():
    """执行数据库迁移：添加 strategy_name 列"""

    # 使用已有的 engine 或者创建新的
    if db_engine is None:
        print('⚠️ 数据库引擎未初始化，尝试从环境变量初始化...')
        # 尝试手动初始化
        from collector.db.database import init_database_config
        init_database_config()
        from collector.db.database import engine as initialized_engine
        if initialized_engine is None:
            print('❌ 无法初始化数据库引擎')
            return False
        target_engine = initialized_engine
    else:
        target_engine = db_engine

    print(f'✅ 数据库引擎已就绪: {target_engine.url}')

    try:
        # 检查列是否存在
        inspector = inspect(target_engine)
        columns = [col['name'] for col in inspector.get_columns('workers')]

        print('\n📋 当前 workers 表列：')
        for col in columns:
            print(f'  - {col}')

        if 'strategy_name' not in columns:
            print('\n🔄 正在添加 strategy_name 列...')

            with target_engine.connect() as conn:
                try:
                    # 根据数据库类型选择合适的 SQL
                    url_str = str(target_engine.url).lower()

                    if 'sqlite' in url_str or 'duckdb' in url_str:
                        sql = "ALTER TABLE workers ADD COLUMN strategy_name VARCHAR(200)"
                    elif 'mysql' in url_str or 'mariadb' in url_str:
                        sql = "ALTER TABLE workers ADD COLUMN strategy_name VARCHAR(200) NULL"
                    elif 'postgresql' in url_str or 'postgres' in url_str:
                        sql = "ALTER TABLE workers ADD COLUMN IF NOT EXISTS strategy_name VARCHAR(200)"
                    else:
                        sql = "ALTER TABLE workers ADD COLUMN strategy_name VARCHAR(200)"

                    conn.execute(text(sql))
                    conn.commit()
                    print('✅ strategy_name 列已添加！')
                except Exception as e:
                    error_msg = str(e)
                    print(f'❌ 添加列失败: {error_msg}')

                    # 如果是 SQLite，可能需要特殊处理
                    if 'duplicate column name' in error_msg.lower():
                        print('⚠️ 列已存在，跳过')
                        return True

                    return False

            # 创建索引（如果不存在）
            print('🔄 正在创建索引...')
            with target_engine.connect() as conn:
                try:
                    index_sql = """
                        CREATE INDEX IF NOT EXISTS idx_worker_strategy_name 
                        ON workers(strategy_name)
                    """
                    conn.execute(text(index_sql))
                    conn.commit()
                    print('✅ 索引 idx_worker_strategy_name 已创建！')
                except Exception as e:
                    error_msg = str(e)
                    if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                        print('⚠️ 索引已存在，跳过创建')
                    else:
                        print(f'⚠️ 创建索引时出错: {error}')
        else:
            print('\n✅ strategy_name 列已存在')

        # 验证更新后的表结构
        print('\n📊 验证更新后的表结构...')
        inspector = inspect(target_engine)
        columns = [col['name'] for col in inspector.get_columns('workers')]
        
        if 'strategy_name' in columns:
            print(f"✅ 确认：strategy_name 字段已存在")
            
            # 检查索引
            indexes = [idx['name'] for idx in inspector.get_indexes('workers')]
            if 'idx_worker_strategy_name' in indexes:
                print(f"✅ 确认：索引 idx_worker_strategy_name 已存在")
            else:
                print(f"⚠️ 警告：索引 idx_worker_strategy_name 未找到")
        else:
            print(f"❌ 错误：strategy_name 字段仍未存在")
            return False

        print('\n🎉 数据库迁移成功完成！')
        return True

    except Exception as e:
        print(f'\n❌ 迁移过程中发生错误: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = upgrade()
    exit(0 if success else 1)
