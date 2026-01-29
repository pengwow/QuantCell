#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试重复记录检测和处理逻辑
"""
'q43aDIA0yzNBmaeSWt9JMdN4rYXOoJTg'
import sys
import os
import pandas as pd
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from backend.collector.db.database import init_database_config, SessionLocal
from backend.collector.db.models import CryptoSpotKline

# 初始化数据库配置
init_database_config()

def test_duplicate_records():
    """测试直接查询重复记录"""
    print("测试直接查询重复记录...")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 直接查询BTCUSDT 15m的重复记录
        print("查询BTCUSDT 15m的重复记录...")
        
        # 使用SQL查询找出重复的日期
        duplicate_dates_query = db.query(
            CryptoSpotKline.date
        ).filter(
            CryptoSpotKline.symbol == "BTCUSDT",
            CryptoSpotKline.interval == "15m"
        ).group_by(
            CryptoSpotKline.date
        ).having(
            db.func.count(CryptoSpotKline.id) > 1
        ).limit(5)
        
        duplicate_dates = duplicate_dates_query.all()
        duplicate_dates = [date[0] for date in duplicate_dates]
        
        print(f"找到 {len(duplicate_dates)} 个重复日期")
        
        if duplicate_dates:
            # 对于每个重复日期，查询所有记录
            for date in duplicate_dates:
                print(f"\n日期 {date} 的所有记录:")
                records = db.query(CryptoSpotKline).filter(
                    CryptoSpotKline.symbol == "BTCUSDT",
                    CryptoSpotKline.interval == "15m",
                    CryptoSpotKline.date == date
                ).all()
                
                for record in records:
                    print(f"  ID: {record.id}, Date: {record.date}, Volume: {record.volume}")
                
                # 测试删除逻辑
                print(f"\n测试删除逻辑 (keep_first):")
                # 保留第一条记录，删除其他记录
                keep_record = records[0]
                print(f"  要保留的记录ID: {keep_record.id}")
                
                # 获取要删除的记录ID
                ids_to_delete = [record.id for record in records if record.id != keep_record.id]
                print(f"  要删除的记录ID: {ids_to_delete}")
                
                if ids_to_delete:
                    # 执行删除操作
                    deleted = db.query(CryptoSpotKline).filter(
                        CryptoSpotKline.id.in_(ids_to_delete)
                    ).delete()
                    print(f"  实际删除的记录数量: {deleted}")
                    
                    # 提交事务
                    db.commit()
                    print(f"  事务已提交")
                    
                    # 验证删除结果
                    remaining_records = db.query(CryptoSpotKline).filter(
                        CryptoSpotKline.symbol == "BTCUSDT",
                        CryptoSpotKline.interval == "15m",
                        CryptoSpotKline.date == date
                    ).all()
                    print(f"  删除后剩余记录数量: {len(remaining_records)}")
        
        else:
            print("没有找到重复记录")
            
    except Exception as e:
        db.rollback()
        print(f"处理失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def test_resolve_duplicates_api_logic():
    """测试API中的重复记录处理逻辑"""
    print("\n" + "="*50)
    print("测试API中的重复记录处理逻辑...")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 获取所有BTCUSDT 15m数据
        query = db.query(CryptoSpotKline).filter(
            CryptoSpotKline.symbol == "BTCUSDT",
            CryptoSpotKline.interval == "15m"
        )
        
        # 执行查询
        kline_list = query.all()
        print(f"获取到 {len(kline_list)} 条记录")
        
        # 转换为DataFrame
        df = pd.DataFrame([{
            'id': k.id,
            'date': k.date,
            'open': float(k.open),
            'high': float(k.high),
            'low': float(k.low),
            'close': float(k.close),
            'volume': float(k.volume)
        } for k in kline_list])
        
        # 检测重复记录
        duplicate_index = df.duplicated(subset=['date'], keep=False)
        print(f"\n重复记录数量: {duplicate_index.sum()}")
        
        if duplicate_index.any():
            duplicate_dates = df[duplicate_index]['date'].unique()
            print(f"重复日期数量: {len(duplicate_dates)}")
            
            # 处理前1个重复日期
            duplicate_date = duplicate_dates[0]
            print(f"\n处理日期: {duplicate_date}")
            
            duplicate_rows = df[df['date'] == duplicate_date]
            print(f"该日期下的记录数量: {len(duplicate_rows)}")
            print(duplicate_rows)
            
            # 使用keep_first策略
            rows_to_keep = duplicate_rows.head(1)
            keep_ids = rows_to_keep['id'].tolist()
            print(f"要保留的ID: {keep_ids}")
            
            rows_to_delete = duplicate_rows[~duplicate_rows['id'].isin(keep_ids)]
            ids_to_delete = rows_to_delete['id'].tolist()
            print(f"要删除的ID: {ids_to_delete}")
            
            if ids_to_delete:
                # 执行删除操作
                deleted = db.query(CryptoSpotKline).filter(
                    CryptoSpotKline.id.in_(ids_to_delete)
                ).delete()
                print(f"实际删除的记录数量: {deleted}")
                
                # 提交事务
                db.commit()
                print("事务已提交")
        
    except Exception as e:
        db.rollback()
        print(f"处理失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_duplicate_records()
    test_resolve_duplicates_api_logic()