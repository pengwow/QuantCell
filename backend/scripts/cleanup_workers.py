#!/usr/bin/env python3
"""
清理所有 Worker 进程和 ZMQ 端口
"""

import subprocess
import signal
import os


def kill_worker_processes():
    """终止所有 Worker 进程"""
    print("检查并终止 Worker 进程...")
    
    # 查找所有 Worker 进程
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    
    killed = []
    for line in result.stdout.split("\n"):
        if "quantcell-worker" in line and "grep" not in line:
            parts = line.split()
            if len(parts) > 1:
                pid = int(parts[1])
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed.append(pid)
                    print(f"  已终止 Worker 进程 PID={pid}")
                except ProcessLookupError:
                    pass
    
    if not killed:
        print("  没有发现 Worker 进程")
    else:
        print(f"  共终止 {len(killed)} 个 Worker 进程")
    
    return killed


def check_zmq_ports():
    """检查 ZMQ 端口是否被占用"""
    print("\n检查 ZMQ 端口 (5555, 5556, 5557, 5558)...")
    
    ports = [5555, 5556, 5557, 5558]
    for port in ports:
        result = subprocess.run(
            ["lsof", "-i", f":{port}"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f"  端口 {port} 被占用:")
            for line in result.stdout.strip().split("\n")[1:]:  # 跳过标题行
                print(f"    {line}")
        else:
            print(f"  端口 {port} 空闲")


def main():
    print("=" * 60)
    print("Worker 环境清理工具")
    print("=" * 60)
    
    # 终止 Worker 进程
    killed = kill_worker_processes()
    
    # 检查 ZMQ 端口
    check_zmq_ports()
    
    print("\n" + "=" * 60)
    print("清理完成")
    print("=" * 60)
    
    if killed:
        print(f"\n注意：已终止 {len(killed)} 个 Worker 进程")
        print("建议重新启动 FastAPI 后端以确保环境干净")


if __name__ == "__main__":
    main()
