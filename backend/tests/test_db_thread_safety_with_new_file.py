#!/usr/bin/env python3
# 测试数据库连接线程安全性 - 使用新的测试数据库文件

import os
import sys
import threading
import time
from pathlib import Path

import yaml

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

from backend.collector.db.connection import (db_instance, get_db_connection,
                                             init_db)
from backend.collector.db.models import SystemConfig, Task

# 测试线程数量
TEST_THREADS = 5
# 每个线程执行的操作次数
TEST_OPERATIONS = 10


# 创建临时配置文件
def create_temp_config():
    """创建临时配置文件，使用新的测试数据库文件"""
    # 读取原始配置
    original_config_path = Path(__file__).parent / "config.yaml"
    with open(original_config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    
    # 修改数据库文件路径
    config["database"]["file"] = "data/test_thread_safety.db"
    
    # 保存临时配置
    temp_config_path = Path(__file__).parent / "config_temp_thread_safety.yaml"
    with open(temp_config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
    
    return temp_config_path


# 删除临时配置文件
def delete_temp_config(temp_config_path):
    """删除临时配置文件"""
    if temp_config_path.exists():
        temp_config_path.unlink()


# 删除测试数据库文件
def delete_test_db():
    """删除测试数据库文件"""
    test_db_path = Path(__file__).parent / "data" / "test_thread_safety.db"
    if test_db_path.exists():
        test_db_path.unlink()


class DatabaseTestThread(threading.Thread):
    """数据库测试线程"""
    
    def __init__(self, thread_id):
        """初始化测试线程
        
        Args:
            thread_id: 线程ID
        """
        super().__init__()
        self.thread_id = thread_id
        self.success_count = 0
        self.error_count = 0
    
    def run(self):
        """线程运行逻辑"""
        print(f"线程 {self.thread_id} 开始运行")
        
        for i in range(TEST_OPERATIONS):
            try:
                # 测试配置操作
                config_key = f"test_key_{self.thread_id}_{i}"
                config_value = f"test_value_{self.thread_id}_{i}"
                
                # 设置配置
                SystemConfig.set(config_key, config_value, f"测试配置 {self.thread_id}_{i}")
                
                # 获取配置
                value = SystemConfig.get(config_key)
                if value == config_value:
                    self.success_count += 1
                else:
                    self.error_count += 1
                    print(f"线程 {self.thread_id} 获取配置失败: 期望'{config_value}'，实际'{value}'")
                
                # 测试任务操作
                task_id = f"test_task_{self.thread_id}_{i}"
                
                # 创建任务
                Task.create(task_id, "test_type", {"param1": f"value_{self.thread_id}_{i}"})
                
                # 获取任务
                task = Task.get(task_id)
                if task and task["task_id"] == task_id:
                    self.success_count += 1
                else:
                    self.error_count += 1
                    print(f"线程 {self.thread_id} 获取任务失败")
                
                # 更新任务进度
                Task.update_progress(task_id, f"test_item_{i}", i, TEST_OPERATIONS)
                
                # 完成任务
                Task.complete(task_id)
                
                # 删除任务
                Task.delete(task_id)
                self.success_count += 1
                
                # 短暂休眠，模拟实际操作
                time.sleep(0.01)
                
            except Exception as e:
                self.error_count += 1
                print(f"线程 {self.thread_id} 操作失败: {e}")
        
        print(f"线程 {self.thread_id} 运行结束: 成功 {self.success_count}，失败 {self.error_count}")


def main():
    """主函数"""
    print(f"开始测试数据库线程安全性...")
    print(f"测试线程数量: {TEST_THREADS}")
    print(f"每个线程操作次数: {TEST_OPERATIONS}")
    
    # 创建临时配置文件
    temp_config_path = create_temp_config()
    
    try:
        # 重新加载配置
        from backend.config import ConfigManager, config_manager
        config_manager = ConfigManager(config_path=str(temp_config_path))
        
        # 关闭现有的数据库连接
        db_instance.close()
        
        # 初始化数据库
        print("\n初始化数据库...")
        try:
            init_db()
            print("✓ 数据库初始化成功")
        except Exception as e:
            print(f"✗ 数据库初始化失败: {e}")
            return 1
        
        # 创建测试线程
        threads = []
        for i in range(TEST_THREADS):
            thread = DatabaseTestThread(i)
            threads.append(thread)
        
        # 启动所有线程
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        end_time = time.time()
        
        # 统计结果
        total_success = sum(thread.success_count for thread in threads)
        total_error = sum(thread.error_count for thread in threads)
        total_operations = TEST_THREADS * TEST_OPERATIONS * 3  # 每个操作包含3个数据库操作
        
        print(f"\n测试完成！")
        print(f"总操作数: {total_operations}")
        print(f"成功操作: {total_success}")
        print(f"失败操作: {total_error}")
        print(f"成功率: {(total_success / total_operations) * 100:.2f}%")
        print(f"耗时: {end_time - start_time:.2f}秒")
        
        if total_error == 0:
            print("✓ 所有操作都成功，数据库连接线程安全！")
            return 0
        else:
            print(f"✗ 有 {total_error} 个操作失败，数据库连接可能存在线程安全问题！")
            return 1
    finally:
        # 清理资源
        db_instance.close()
        delete_temp_config(temp_config_path)
        delete_test_db()


if __name__ == "__main__":
    sys.exit(main())
