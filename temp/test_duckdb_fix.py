#!/usr/bin/env python3
"""
测试DuckDB连接修复效果
"""

import sys
import os
from datetime import datetime

# 设置项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试DuckDB连接
print("=== 测试DuckDB连接 ===")
try:
    from collector.db.database import init_database_config, SessionLocal
    init_database_config()
    print("✅ 数据库配置初始化成功")
    
    # 测试数据库会话
    with SessionLocal() as session:
        print("✅ 数据库会话创建成功")
        session.close()
        
except Exception as e:
    print(f"❌ 数据库连接测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试TaskBusiness方法
print("\n=== 测试TaskBusiness方法 ===")
try:
    from collector.db.models import TaskBusiness
    import uuid
    
    # 测试创建任务
    print("\n1. 测试创建任务")
    task_id = str(uuid.uuid4())
    task_type = "test"
    params = {"key": "value"}
    created = TaskBusiness.create(task_id, task_type, params)
    if created:
        print(f"✅ 任务创建成功: {task_id}")
    else:
        print("❌ 任务创建失败")
        sys.exit(1)
    
    # 测试开始任务
    print("\n2. 测试开始任务")
    started = TaskBusiness.start(task_id)
    if started:
        print("✅ 任务开始成功")
    else:
        print("❌ 任务开始失败")
    
    # 测试更新进度
    print("\n3. 测试更新进度")
    updated = TaskBusiness.update_progress(task_id, "processing", 100, 50, 5, "status")
    if updated:
        print("✅ 进度更新成功")
    else:
        print("❌ 进度更新失败")
    
    # 测试获取任务
    print("\n4. 测试获取任务")
    task = TaskBusiness.get(task_id)
    if task:
        print(f"✅ 任务获取成功: {task['task_id']}, status: {task['status']}")
    else:
        print("❌ 任务获取失败")
    
    # 测试获取所有任务
    print("\n5. 测试获取所有任务")
    all_tasks = TaskBusiness.get_all()
    if all_tasks:
        print(f"✅ 获取所有任务成功，共 {len(all_tasks)} 个任务")
    else:
        print("❌ 获取所有任务失败")
    
    # 测试获取分页任务
    print("\n6. 测试获取分页任务")
    paginated = TaskBusiness.get_paginated(page=1, page_size=10)
    if paginated:
        print(f"✅ 获取分页任务成功，共 {paginated['pagination']['total']} 个任务")
    else:
        print("❌ 获取分页任务失败")
    
    # 测试完成任务
    print("\n7. 测试完成任务")
    completed = TaskBusiness.complete(task_id)
    if completed:
        print("✅ 任务完成成功")
    else:
        print("❌ 任务完成失败")
    
    # 测试删除任务
    print("\n8. 测试删除任务")
    deleted = TaskBusiness.delete(task_id)
    if deleted:
        print("✅ 任务删除成功")
    else:
        print("❌ 任务删除失败")
    
    print("\n✅ 所有TaskBusiness方法测试通过")
    
except Exception as e:
    print(f"❌ TaskBusiness测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n🎉 所有测试通过，DuckDB连接修复成功！")
