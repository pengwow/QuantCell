#!/usr/bin/env python3
# 简单测试SQLite数据库线程安全性

import os
import sys
import threading
import time
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/quantcell')

from collector.db.connection import get_db_connection, init_db
from collector.db.models import SystemConfig, Task

# 测试线程数量
TEST_THREADS = 5
# 每个线程执行的操作次数
TEST_OPERATIONS = 10

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
                # 获取数据库连接
                conn = get_db_connection()
                
                # 测试简单的SQL操作
                conn.execute("CREATE TABLE IF NOT EXISTS test_thread_safety (id INTEGER PRIMARY KEY, name TEXT)")
                
                # 插入数据
                conn.execute("INSERT INTO test_thread_safety (name) VALUES (?)", (f"test_{self.thread_id}_{i}",))
                
                # 查询数据
                result = conn.execute("SELECT * FROM test_thread_safety WHERE name = ?", (f"test_{self.thread_id}_{i}",)).fetchone()
                if result:
                    self.success_count += 1
                else:
                    self.error_count += 1
                    print(f"线程 {self.thread_id} 查询数据失败")
                
                # 删除数据
                conn.execute("DELETE FROM test_thread_safety WHERE name = ?", (f"test_{self.thread_id}_{i}",))
                
                self.success_count += 1
                
                # 短暂休眠，模拟实际操作
                time.sleep(0.01)
                
            except Exception as e:
                self.error_count += 1
                print(f"线程 {self.thread_id} 操作失败: {e}")
        
        print(f"线程 {self.thread_id} 运行结束: 成功 {self.success_count}，失败 {self.error_count}")

def main():
    """主函数"""
    print(f"开始测试SQLite数据库线程安全性...")
    print(f"测试线程数量: {TEST_THREADS}")
    print(f"每个线程操作次数: {TEST_OPERATIONS}")
    
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
    total_operations = TEST_THREADS * TEST_OPERATIONS * 2  # 每个操作包含2个数据库操作
    
    print(f"\n测试完成！")
    print(f"总操作数: {total_operations}")
    print(f"成功操作: {total_success}")
    print(f"失败操作: {total_error}")
    print(f"成功率: {(total_success / total_operations) * 100:.2f}%")
    print(f"耗时: {end_time - start_time:.2f}秒")
    
    if total_error == 0:
        print("✓ 所有操作都成功，SQLite数据库连接线程安全！")
        return 0
    else:
        print(f"✗ 有 {total_error} 个操作失败，SQLite数据库连接可能存在线程安全问题！")
        return 1

if __name__ == "__main__":
    sys.exit(main())
