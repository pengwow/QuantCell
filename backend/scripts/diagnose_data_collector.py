#!/usr/bin/env python3
"""
DataCollector 诊断工具

用于诊断 DataCollector 服务无法启动的问题。
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


async def diagnose_data_collector():
    """诊断 DataCollector 启动问题"""
    
    print("=" * 60)
    print("DataCollector 诊断工具")
    print("=" * 60)
    
    # 1. 检查依赖导入
    print("\n[1/5] 检查依赖模块...")
    try:
        import zmq.asyncio
        print("  ✓ zmq.asyncio 导入成功")
        print(f"    版本: {zmq.zmq_version()}")
    except ImportError as e:
        print(f"  ✗ zmq 导入失败: {e}")
        print("    解决方案: pip install pyzmq")
        return False
    
    try:
        from worker.ipc.data_collector import DataCollector
        print("  ✓ DataCollector 导入成功")
    except ImportError as e:
        print(f"  ✗ DataCollector 导入失败: {e}")
        return False
    
    try:
        from worker.ipc.sqlite_manager import SQLiteManager
        print("  ✓ SQLiteManager 导入成功")
    except ImportError as e:
        print(f"  ✗ SQLiteManager 导入失败: {e}")
        return False
    
    # 2. 检查端口占用情况
    print("\n[2/5] 检查 ZMQ 端口 (5560)...")
    import socket
    
    def is_port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0
    
    if is_port_in_use(5560):
        print("  ⚠ 端口 5560 已被占用")
        
        # 尝试识别占用进程
        try:
            import subprocess
            result = subprocess.run(
                ["lsof", "-i", ":5560"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")[1:]  # 跳过标题行
                for line in lines[:3]:  # 只显示前3条
                    parts = line.split()
                    if len(parts) > 1:
                        print(f"    进程: PID={parts[1]} 命令={' '.join(parts[10:]) if len(parts) > 10 else 'N/A'}")
            
            print("\n    解决方案:")
            print("      1. 终止占用端口的进程")
            print("      2. 或修改 DataCollector 端口配置")
        except Exception as e:
            print(f"    无法检查进程详情: {e}")
        
        return False
    else:
        print("  ✓ 端口 5560 可用")
    
    # 3. 检查 SQLite 数据库路径
    print("\n[3/5] 检查 SQLite 数据库路径...")
    db_path = "data/worker_data.db"
    
    try:
        # 检查目录是否存在
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"  ✓ 创建目录: {db_dir}")
        else:
            print(f"  ✓ 目录已存在: {db_dir}")
        
        # 检查写入权限
        test_file = os.path.join(db_dir, ".test_write")
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            print(f"  ✓ 写入权限正常")
        except Exception as e:
            print(f"  ✗ 写入权限不足: {e}")
            return False
        
        # 检查数据库文件是否存在
        if os.path.exists(db_path):
            size = os.path.getsize(db_path)
            print(f"  ✓ 数据库文件已存在: {db_path} ({size / 1024:.2f} KB)")
        else:
            print(f"  ✓ 数据库文件不存在 (将在首次启动时创建): {db_path}")
            
    except Exception as e:
        print(f"  ✗ 路径检查失败: {e}")
        return False
    
    # 4. 尝试初始化 SQLiteManager
    print("\n[4/5] 尝试初始化 SQLiteManager...")
    try:
        sqlite_manager = SQLiteManager(db_path)
        await sqlite_manager.initialize()
        print("  ✓ SQLiteManager 初始化成功")
        await sqlite_manager.close()
    except Exception as e:
        print(f"  ✗ SQLiteManager 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. 尝试启动 DataCollector
    print("\n[5/5] 尝试启动 DataCollector...")
    data_collector = None
    
    try:
        data_collector = DataCollector(
            host="127.0.0.1",
            data_port=5560,
            db_path=db_path
        )
        
        started = await data_collector.start()
        
        if started:
            print("  ✓ DataCollector 启动成功!")
            print(f"    监听地址: tcp://127.0.0.1:5560")
            print(f"    数据库路径: {os.path.abspath(db_path)}")
            
            # 测试基本功能
            stats = data_collector.get_stats()
            print(f"\n  📊 初始统计:")
            print(f"    消息接收: {stats['messages_received']}")
            print(f"    运行状态: {'运行中' if data_collector._running else '已停止'}")
            
            # 停止服务
            await data_collector.stop()
            print("\n  ✓ DataCollector 已停止 (测试完成)")
            
            print("\n" + "=" * 60)
            print("✅ 所有检查通过! DataCollector 可以正常工作")
            print("=" * 60)
            return True
            
        else:
            print("  ✗ DataCollector.start() 返回 False")
            print("    可能原因:")
            print("      - ZMQ 绑定失败 (端口被占用或权限不足)")
            print("      - SQLite 初始化失败")
            return False
            
    except Exception as e:
        print(f"  ✗ DataCollector 启动异常: {e}")
        import traceback
        traceback.print_exc()
        
        if data_collector:
            await data_collector.stop()
        
        return False


async def main():
    """主函数"""
    success = await diagnose_data_collector()
    
    if not success:
        print("\n" + "=" * 60)
        print("❌ 诊断发现问题")
        print("=" * 60)
        print("\n建议操作:")
        print("  1. 查看上方详细错误信息")
        print("  2. 根据提示解决问题")
        print("  3. 重启后端服务: uvicorn main:app --reload")
        print("\n常见问题解决:")
        print("  • 端口占用: lsof -i :5560 | kill -9 <PID>")
        print("  • 权限问题: chmod 755 data/")
        print("  • 缺失依赖: pip install pyzmq")
        sys.exit(1)
    else:
        print("\n🎉 DataCollector 就绪! 可以使用以下命令测试:")
        print("  python worker_cli.py trades 1")
        print("  python worker_cli.py positions 1")
        print("  python worker_cli.py data-sync 1")


if __name__ == "__main__":
    asyncio.run(main())
