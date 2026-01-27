#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复数据库表结构，添加缺失的data_source列
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# 添加backend目录到Python路径
sys.path.append(str(project_root / "backend"))


def fix_crypto_spot_klines_table():
    """
    修复crypto_spot_klines表，添加缺失的data_source列
    """
    print("开始修复crypto_spot_klines表...")
    
    try:
        import sys
        import os
        from pathlib import Path
        
        # 添加backend目录到Python路径
        backend_dir = Path(__file__).parent / "backend"
        sys.path.insert(0, str(backend_dir))
        
        from collector.db.database import init_database_config, engine, db_type
        from sqlalchemy import text
        from sqlalchemy.orm import Session
        
        # 初始化数据库配置
        init_database_config()
        
        # 使用Session执行修复
        with Session(engine) as session:
            # 检查表是否存在
            print("检查crypto_spot_klines表是否存在...")
            table_exists = False
            if db_type == "sqlite":
                table_exists = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_spot_klines'")
                ).fetchone()
            elif db_type == "duckdb":
                table_exists = session.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_name='crypto_spot_klines'")
                ).fetchone()
            
            if not table_exists:
                print("crypto_spot_klines表不存在，跳过修复")
                return
            
            print("crypto_spot_klines表存在")
            
            # 检查data_source列是否存在
            print("检查data_source列是否存在...")
            column_exists = False
            if db_type == "sqlite":
                column_exists = session.execute(
                    text("SELECT name FROM pragma_table_info('crypto_spot_klines') WHERE name='data_source'")
                ).fetchone()
            elif db_type == "duckdb":
                column_exists = session.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name='crypto_spot_klines' AND column_name='data_source'")
                ).fetchone()
            
            if column_exists:
                print("data_source列已存在，跳过修复")
            else:
                print("data_source列不存在，开始添加...")
                
                # 添加data_source列
                session.execute(
                    text("ALTER TABLE crypto_spot_klines ADD COLUMN data_source VARCHAR(50) NOT NULL DEFAULT 'unknown'")
                )
                
                # 创建索引
                session.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_crypto_spot_klines_data_source ON crypto_spot_klines(data_source)")
                )
                
                # 提交更改
                session.commit()
                
                print("data_source列添加成功！")
                print("索引创建成功！")
        
        print("crypto_spot_klines表修复完成！")
        
        # 验证修复结果
        print("\n验证修复结果...")
        with Session(engine) as session:
            # 检查data_source列是否存在
            column_exists = session.execute(
                text("SELECT name FROM pragma_table_info('crypto_spot_klines') WHERE name='data_source'")
            ).fetchone()
            
            if column_exists:
                print("✓ data_source列已成功添加")
            else:
                print("✗ data_source列添加失败")
            
            # 测试查询
            print("\n测试查询K线数据...")
            try:
                result = session.execute(
                    text("SELECT * FROM crypto_spot_klines LIMIT 1")
                ).fetchone()
                
                if result:
                    print("✓ K线数据查询成功")
                    print(f"样本数据包含的列: {len(result)}")
                else:
                    print("✗ K线数据查询失败：表中没有数据")
            except Exception as e:
                print(f"✗ K线数据查询失败: {e}")
        
    except Exception as e:
        print(f"\n修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = fix_crypto_spot_klines_table()
    
    if success:
        print("\n\n修复成功！")
    else:
        print("\n\n修复失败！")