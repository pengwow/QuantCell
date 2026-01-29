#!/usr/bin/env python3
# 测试数据库切换功能

import os
import sys

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from backend.collector.db.connection import get_db_connection, init_db
from backend.collector.db.models import SystemConfig, Task


def test_db_connection():
    """测试数据库连接"""
    print("测试数据库连接...")
    try:
        conn = get_db_connection()
        print("✓ 数据库连接成功")
        return conn
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return None


def test_db_init():
    """测试数据库初始化"""
    print("测试数据库初始化...")
    try:
        init_db()
        print("✓ 数据库初始化成功")
        return True
    except Exception as e:
        print(f"✗ 数据库初始化失败: {e}")
        return False


def test_system_config():
    """测试系统配置功能"""
    print("测试系统配置功能...")
    
    # 测试设置配置
    try:
        SystemConfig.set("test_key", "test_value", "测试配置")
        print("✓ 设置配置成功")
    except Exception as e:
        print(f"✗ 设置配置失败: {e}")
        return False
    
    # 测试获取配置
    try:
        value = SystemConfig.get("test_key")
        if value == "test_value":
            print("✓ 获取配置成功")
        else:
            print(f"✗ 获取配置失败: 期望'test_value'，实际'{value}'")
            return False
    except Exception as e:
        print(f"✗ 获取配置失败: {e}")
        return False
    
    # 测试获取所有配置
    try:
        all_configs = SystemConfig.get_all()
        if "test_key" in all_configs:
            print("✓ 获取所有配置成功")
        else:
            print("✗ 获取所有配置失败: 未找到'test_key'")
            return False
    except Exception as e:
        print(f"✗ 获取所有配置失败: {e}")
        return False
    
    return True


def test_task():
    """测试任务功能"""
    print("测试任务功能...")
    
    # 测试创建任务
    task_id = "test_task_123"
    try:
        Task.create(task_id, "test_type", {"param1": "value1"})
        print("✓ 创建任务成功")
    except Exception as e:
        print(f"✗ 创建任务失败: {e}")
        return False
    
    # 测试获取任务
    try:
        task = Task.get(task_id)
        if task and task["task_id"] == task_id:
            print("✓ 获取任务成功")
        else:
            print("✗ 获取任务失败: 未找到任务")
            return False
    except Exception as e:
        print(f"✗ 获取任务失败: {e}")
        return False
    
    # 测试更新任务进度
    try:
        Task.update_progress(task_id, "test_item", 1, 10)
        print("✓ 更新任务进度成功")
    except Exception as e:
        print(f"✗ 更新任务进度失败: {e}")
        return False
    
    # 测试完成任务
    try:
        Task.complete(task_id)
        print("✓ 完成任务成功")
    except Exception as e:
        print(f"✗ 完成任务失败: {e}")
        return False
    
    # 测试删除任务
    try:
        Task.delete(task_id)
        print("✓ 删除任务成功")
    except Exception as e:
        print(f"✗ 删除任务失败: {e}")
        return False
    
    return True


def main():
    """主函数"""
    print("开始测试数据库切换功能...\n")
    
    # 测试数据库连接
    conn = test_db_connection()
    if not conn:
        return 1
    
    # 测试数据库初始化
    if not test_db_init():
        return 1
    
    # 测试系统配置功能
    if not test_system_config():
        return 1
    
    # 测试任务功能
    if not test_task():
        return 1
    
    print("\n✓ 所有测试通过！数据库切换成功！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
