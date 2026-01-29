#!/usr/bin/env python3
# 测试数据库初始化功能

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from backend.collector.db import init_db
from backend.collector.db.models import Task


def test_db_init():
    """测试数据库初始化"""
    print("开始测试数据库初始化...")
    
    try:
        # 初始化数据库
        init_db()
        print("✓ 数据库初始化成功")
        
        # 测试创建任务
        print("测试创建任务...")
        task_id = "test_task_123"
        success = Task.create(task_id, "test_type", {"param1": "value1"})
        if success:
            print("✓ 任务创建成功")
            
            # 测试获取任务
            task = Task.get(task_id)
            if task:
                print("✓ 任务获取成功")
                
                # 测试更新任务进度
                success = Task.update_progress(task_id, "test_item", 1, 10)
                if success:
                    print("✓ 任务进度更新成功")
                    
                    # 测试完成任务
                    success = Task.complete(task_id)
                    if success:
                        print("✓ 任务完成成功")
                        
                        # 测试删除任务
                        success = Task.delete(task_id)
                        if success:
                            print("✓ 任务删除成功")
                        else:
                            print("✗ 任务删除失败")
                    else:
                        print("✗ 任务完成失败")
                else:
                    print("✗ 任务进度更新失败")
            else:
                print("✗ 任务获取失败")
        else:
            print("✗ 任务创建失败")
            
        print("\n所有测试完成！")
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_db_init()
    sys.exit(0 if success else 1)
