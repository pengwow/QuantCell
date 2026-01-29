#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：将K线数据表的date字段迁移到timestamp字段

将所有K线相关表（crypto_spot_klines、crypto_future_klines、stock_klines）的date字段从DateTime类型
迁移为String类型的timestamp字段，存储毫秒级时间戳字符串。
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.collector.db.database import init_database_config, SessionLocal
from backend.collector.db.models import CryptoSpotKline, CryptoFutureKline, StockKline


class DatabaseMigrator:
    """数据库迁移器
    
    用于将K线数据表的date字段迁移到timestamp字段
    """
    
    def __init__(self):
        """初始化迁移器"""
        init_database_config()
        self.engine = SessionLocal().bind
        self.SessionLocal = SessionLocal
    
    def _backup_tables(self) -> Dict[str, str]:
        """备份现有数据
        
        Returns:
            Dict[str, str]: 备份文件路径映射
        """
        logger.info("开始备份现有数据...")
        
        backup_dir = Path.home() / ".qlib" / "backups" / f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_files = {}
        
        for table_name in ['crypto_spot_klines', 'crypto_future_klines', 'stock_klines']:
            try:
                # 备份表数据到CSV文件
                query = text(f"SELECT * FROM {table_name}")
                df = pd.read_sql(query, self.engine)
                
                if not df.empty:
                    backup_file = backup_dir / f"{table_name}.csv"
                    df.to_csv(backup_file, index=False)
                    backup_files[table_name] = str(backup_file)
                    logger.info(f"已备份 {table_name} 表数据到 {backup_file}，共 {len(df)} 条记录")
                else:
                    logger.warning(f"{table_name} 表为空，跳过备份")
            except Exception as e:
                logger.error(f"备份 {table_name} 表数据失败: {e}")
                backup_files[table_name] = ""
        
        return backup_files
    
    def _migrate_table(self, table_name: str, model_class) -> Dict[str, Any]:
        """迁移单个表
        
        Args:
            table_name: 表名
            model_class: 模型类
            
        Returns:
            Dict[str, Any]: 迁移结果
        """
        logger.info(f"开始迁移表: {table_name}")
        
        session = self.SessionLocal()
        try:
            # 查询现有数据
            query = text(f"SELECT id, symbol, interval, date, open, high, low, close, volume, unique_kline, data_source, created_at, updated_at FROM {table_name}")
            df = pd.read_sql(query, self.engine)
            
            if df.empty:
                logger.info(f"{table_name} 表为空，跳过迁移")
                return {
                    "table_name": table_name,
                    "status": "skipped",
                    "message": "表为空，无需迁移",
                    "migrated_count": 0,
                    "error_count": 0
                }
            
            # 转换date字段为timestamp字段
            logger.info(f"开始转换 {table_name} 表的date字段为timestamp字段...")
            
            # 将date字段转换为DateTime对象（如果还不是的话）
            if df['date'].dtype == 'object':
                # 如果date字段是字符串，先转换为DateTime
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # 将DateTime类型的date转换为毫秒级时间戳字符串
            df['timestamp'] = df['date'].apply(lambda x: str(int(x.timestamp() * 1000)) if pd.notna(x) else '')
            
            # 删除旧的date列
            df = df.drop(columns=['date'])
            
            # 统计转换结果
            total_count = len(df)
            converted_count = df['timestamp'].notna().sum()
            error_count = total_count - converted_count
            
            logger.info(f"{table_name} 表转换统计: 总记录数={total_count}, 成功转换={converted_count}, 转换失败={error_count}")
            
            if error_count > 0:
                logger.warning(f"{table_name} 表有 {error_count} 条记录转换失败")
            
            # 创建新表结构（使用timestamp字段）
            logger.info(f"创建新表结构: {table_name}_new")
            
            # 保存转换后的数据到新表
            df.to_sql(f"{table_name}_new", self.engine, if_exists='replace', index=False)
            
            logger.info(f"已将转换后的数据保存到 {table_name}_new 表，共 {converted_count} 条记录")
            
            # 验证新表数据
            verify_query = text(f"SELECT COUNT(*) FROM {table_name}_new")
            verify_result = pd.read_sql(verify_query, self.engine)
            new_count = verify_result.iloc[0, 0] if not verify_result.empty else 0
            
            logger.info(f"验证 {table_name}_new 表数据: 共 {new_count} 条记录")
            
            session.commit()
            
            return {
                "table_name": table_name,
                "status": "success",
                "message": f"成功迁移 {converted_count} 条记录",
                "migrated_count": converted_count,
                "error_count": error_count,
                "new_table_count": new_count
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"迁移 {table_name} 表失败: {e}")
            return {
                "table_name": table_name,
                "status": "error",
                "message": f"迁移失败: {str(e)}",
                "migrated_count": 0,
                "error_count": 0,
                "new_table_count": 0
            }
        finally:
            session.close()
    
    def _swap_tables(self, table_name: str) -> bool:
        """交换表
        
        Args:
            table_name: 表名
            
        Returns:
            bool: 交换是否成功
        """
        logger.info(f"开始交换表: {table_name}")
        
        session = self.SessionLocal()
        try:
            # 重命名旧表
            session.execute(text(f"ALTER TABLE {table_name} RENAME TO {table_name}_old"))
            
            # 重命名新表
            session.execute(text(f"ALTER TABLE {table_name}_new RENAME TO {table_name}"))
            
            # 删除旧表
            session.execute(text(f"DROP TABLE {table_name}_old"))
            
            session.commit()
            logger.info(f"成功交换表: {table_name}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"交换表 {table_name} 失败: {e}")
            return False
        finally:
            session.close()
    
    def migrate_all(self) -> Dict[str, Any]:
        """迁移所有K线表
        
        Returns:
            Dict[str, Any]: 迁移结果汇总
        """
        logger.info("="*60)
        logger.info("开始K线数据表迁移")
        logger.info("="*60)
        
        # 备份现有数据
        backup_files = self._backup_tables()
        
        # 迁移各个表
        tables_to_migrate = [
            ('crypto_spot_klines', CryptoSpotKline),
            ('crypto_future_klines', CryptoFutureKline),
            ('stock_klines', StockKline)
        ]
        
        results = {}
        for table_name, model_class in tables_to_migrate:
            result = self._migrate_table(table_name, model_class)
            results[table_name] = result
        
        # 交换表
        swap_results = {}
        for table_name, _ in tables_to_migrate:
            if results[table_name]['status'] == 'success':
                swap_success = self._swap_tables(table_name)
                swap_results[table_name] = {
                    "success": swap_success,
                    "backup_file": backup_files.get(table_name, "")
                }
            else:
                swap_results[table_name] = {
                    "success": False,
                    "backup_file": backup_files.get(table_name, ""),
                    "error": results[table_name].get('message', '迁移失败')
                }
        
        # 汇总结果
        total_migrated = sum(r.get('migrated_count', 0) for r in results.values() if r.get('status') == 'success')
        total_errors = sum(r.get('error_count', 0) for r in results.values() if r.get('status') == 'success')
        
        summary = {
            "backup_files": backup_files,
            "migration_results": results,
            "swap_results": swap_results,
            "total_migrated": total_migrated,
            "total_errors": total_errors,
            "overall_status": "success" if all(s.get('success') for s in swap_results.values()) else "partial"
        }
        
        logger.info("="*60)
        logger.info("K线数据表迁移完成")
        logger.info("="*60)
        logger.info(f"迁移汇总: 成功迁移 {total_migrated} 条记录，{total_errors} 条转换失败")
        logger.info(f"总体状态: {summary['overall_status']}")
        
        return summary


def main():
    """主函数"""
    migrator = DatabaseMigrator()
    result = migrator.migrate_all()
    
    print("\n" + "="*60)
    print("K线数据表迁移结果")
    print("="*60)
    print(f"\n总体状态: {result['overall_status']}")
    print(f"成功迁移记录总数: {result['total_migrated']}")
    print(f"转换失败记录总数: {result['total_errors']}")
    print("\n详细结果:")
    print("-"*60)
    
    for table_name, swap_result in result['swap_results'].items():
        print(f"\n{table_name}:")
        print(f"  交换状态: {'成功' if swap_result['success'] else '失败'}")
        print(f"  备份文件: {swap_result['backup_file']}")
        if not swap_result['success']:
            print(f"  错误信息: {swap_result.get('error', '未知错误')}")
    
    print("-"*60)
    print("\n备份文件位置:")
    for table_name, backup_file in result['backup_files'].items():
        if backup_file:
            print(f"  {table_name}: {backup_file}")
    
    print("="*60)


if __name__ == "__main__":
    main()