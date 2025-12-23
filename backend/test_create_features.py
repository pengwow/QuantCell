#!/usr/bin/env python3
"""测试create_features函数修复效果

直接测试修复后的create_features函数，验证批量插入功能是否正常工作
"""

import os
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session

from collector.db import crud, models, schemas
from collector.db.database import SessionLocal, init_database_config


def test_create_features():
    """测试create_features函数"""
    print("开始测试create_features函数...")
    
    # 初始化数据库配置
    init_database_config()
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 创建测试特征数据
        test_features = [
            schemas.FeatureCreate(
                symbol="BTCUSDT",
                feature_name="close",
                freq="day"
            ),
            schemas.FeatureCreate(
                symbol="BTCUSDT",
                feature_name="volume",
                freq="1h"
            ),
            schemas.FeatureCreate(
                symbol="ETHUSDT",
                feature_name="close",
                freq="day"
            )
        ]
        
        print(f"创建测试特征: {len(test_features)}个")
        
        # 调用修复后的create_features函数
        created_features = crud.create_features(db, test_features)
        
        print(f"成功创建特征: {len(created_features)}个")
        print(f"特征详情:")
        for feature in created_features:
            print(f"  - ID: {feature.id}, Symbol: {feature.symbol}, Feature: {feature.feature_name}, Freq: {feature.freq}, Created: {feature.created_at}")
        
        # 验证创建的特征数量
        assert len(created_features) == len(test_features), f"创建的特征数量不匹配: 预期{len(test_features)}个，实际{len(created_features)}个"
        
        # 清理测试数据
        print("清理测试数据...")
        # 使用原始SQL删除测试数据，因为返回的feature.id可能是None
        from sqlalchemy import text
        db.execute(text("DELETE FROM features WHERE symbol IN ('BTCUSDT', 'ETHUSDT') AND feature_name IN ('close', 'volume')"))
        db.commit()
        
        print("测试成功！")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 关闭数据库会话
        db.close()


if __name__ == "__main__":
    test_create_features()