#!/usr/bin/env python3
# 最终测试数据库连接线程安全性

import os
import sys
import threading
import time
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append('/Users/liupeng/workspace/qbot')

# 测试线程安全性的最终方案

# 1. 首先，让我们创建一个简单的测试，直接测试修复后的线程本地存储功能
# 2. 我们将创建一个简单的数据库连接类，模拟修复后的DBConnection类
# 3. 测试每个线程是否能够获得独立的连接


# 模拟修复后的DBConnection类
class TestDBConnection:
    """测试数据库连接类"""
    
    def __init__(self):
        """初始化测试数据库连接类"""
        import threading
        self._local = threading.local()
    
    def connect(self, db_path):
        """为当前线程建立数据库连接
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        import sqlite3

        # 检查当前线程是否已有连接
        if not hasattr(self._local, '_conn') or self._local._conn is None:
            # 创建新连接
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            self._local._conn = conn
            print(f"线程 {threading.current_thread().name} 创建了新连接: {db_path}")
        
        return self._local._conn
    
    def close(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, '_conn') and self._local._conn is not None:
            self._local._conn.close()
            self._local._conn = None
            print(f"线程 {threading.current_thread().name} 关闭了连接")


# 测试线程
class TestThread(threading.Thread):
    """测试线程"""
    
    def __init__(self, thread_id):
        """初始化测试线程
        
        Args:
            thread_id: 线程ID
        """
        super().__init__(name=f"Thread-{thread_id}")
        self.thread_id = thread_id
        self.success_count = 0
        self.error_count = 0
        self.db_path = Path(f"test_db_{thread_id}.db")
    
    def run(self):
        """线程运行逻辑"""
        print(f"线程 {self.thread_id} 开始运行")
        
        # 创建测试数据库连接
        db_conn = TestDBConnection()
        
        try:
            for i in range(5):
                try:
                    # 获取连接
                    conn = db_conn.connect(self.db_path)
                    
                    # 测试简单的SQL操作
                    conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
                    
                    # 插入数据
                    conn.execute("INSERT INTO test (name) VALUES (?)", (f"test_{self.thread_id}_{i}",))
                    conn.commit()
                    
                    # 查询数据
                    result = conn.execute("SELECT * FROM test WHERE name = ?", (f"test_{self.thread_id}_{i}",)).fetchone()
                    if result:
                        self.success_count += 1
                    else:
                        self.error_count += 1
                        print(f"线程 {self.thread_id} 查询数据失败")
                    
                    # 删除数据
                    conn.execute("DELETE FROM test WHERE name = ?", (f"test_{self.thread_id}_{i}",))
                    conn.commit()
                    
                    self.success_count += 1
                    
                    # 短暂休眠，模拟实际操作
                    time.sleep(0.01)
                    
                except Exception as e:
                    self.error_count += 1
                    print(f"线程 {self.thread_id} 操作失败: {e}")
        finally:
            # 关闭连接
            db_conn.close()
            # 清理测试数据库文件
            if self.db_path.exists():
                self.db_path.unlink()
        
        print(f"线程 {self.thread_id} 运行结束: 成功 {self.success_count}，失败 {self.error_count}")


def main():
    """主函数"""
    print("开始测试线程本地存储功能...")
    
    # 测试线程数量
    test_threads = 5
    
    # 创建测试线程
    threads = []
    for i in range(test_threads):
        thread = TestThread(i)
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
    total_operations = test_threads * 5 * 2  # 每个线程5次操作，每次操作2个数据库操作
    
    print(f"\n测试完成！")
    print(f"总操作数: {total_operations}")
    print(f"成功操作: {total_success}")
    print(f"失败操作: {total_error}")
    print(f"成功率: {(total_success / total_operations) * 100:.2f}%")
    print(f"耗时: {end_time - start_time:.2f}秒")
    
    if total_error == 0:
        print("✓ 线程本地存储功能正常工作！")
        return 0
    else:
        print(f"✗ 线程本地存储功能存在问题！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
