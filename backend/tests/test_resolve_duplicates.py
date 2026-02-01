#!/usr/bin/env python3
"""
测试 resolve_kline_duplicates 接口的逻辑
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from scripts.check_kline_health import KlineHealthChecker
from collector.db.database import SessionLocal
from collector.db.models import CryptoSpotKline

if __name__ == "__main__":
    # 创建 KlineHealthChecker 实例
    checker = KlineHealthChecker()
    
    # 调用 get_kline_data 方法
    df = checker.get_kline_data(symbol="BTCUSDT", interval="15m")
    
    # 获取重复记录（基于date列）
    duplicate_index = df.duplicated(subset=['date'], keep=False)
    duplicate_dates = df[duplicate_index]['date'].unique()
    
    print(f"发现 {duplicate_index.sum()} 条重复记录")
    print(f"涉及 {len(duplicate_dates)} 个日期")
    
    # 选择第一个重复日期进行测试
    if len(duplicate_dates) > 0:
        test_date = duplicate_dates[0]
        print(f"\n测试日期: {test_date}")
        
        # 获取该日期下的所有记录
        duplicate_rows = df[df['date'] == test_date]
        print(f"该日期下的记录数: {len(duplicate_rows)}")
        print("记录详情:")
        print(duplicate_rows)
        
        # 根据策略选择要保留的记录
        strategy = "keep_first"
        if strategy == "keep_first":
            rows_to_keep = duplicate_rows.head(1)
        elif strategy == "keep_last":
            rows_to_keep = duplicate_rows.tail(1)
        elif strategy == "keep_max_volume":
            rows_to_keep = duplicate_rows[duplicate_rows['volume'] == duplicate_rows['volume'].max()].head(1)
        elif strategy == "keep_min_volume":
            rows_to_keep = duplicate_rows[duplicate_rows['volume'] == duplicate_rows['volume'].min()].head(1)
        
        print(f"\n要保留的记录 (策略: {strategy}):")
        print(rows_to_keep)
        
        # 获取要删除的记录
        keep_ids = rows_to_keep['id'].tolist()
        rows_to_delete = duplicate_rows[~duplicate_rows['id'].isin(keep_ids)]
        print(f"\n要删除的记录数: {len(rows_to_delete)}")
        print("要删除的记录:")
        print(rows_to_delete)
        
        # 获取要删除的记录的id列表
        ids_to_delete = rows_to_delete['id'].tolist()
        print(f"\n要删除的id列表: {ids_to_delete}")
        
        # 测试删除操作
        db = SessionLocal()
        try:
            # 先查询这些id是否存在
            existing_records = db.query(CryptoSpotKline).filter(
                CryptoSpotKline.id.in_(ids_to_delete)
            ).all()
            print(f"\n数据库中存在 {len(existing_records)} 条要删除的记录")
            for record in existing_records:
                print(f"  ID: {record.id}, Date: {record.date}, Symbol: {record.symbol}, Interval: {record.interval}")
            
            # 执行删除操作
            if existing_records:
                deleted = db.query(CryptoSpotKline).filter(
                    CryptoSpotKline.id.in_(ids_to_delete)
                ).delete()
                print(f"\n删除了 {deleted} 条记录")
                db.commit()
            
            # 再次查询，确认删除
            remaining_records = db.query(CryptoSpotKline).filter(
                CryptoSpotKline.id.in_(ids_to_delete)
            ).all()
            print(f"\n删除后剩余 {len(remaining_records)} 条记录")
        except Exception as e:
            print(f"\n删除操作失败: {e}")
            db.rollback()
        finally:
            db.close()
