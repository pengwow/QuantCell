#!/usr/bin/env python3
"""
服务管理脚本
用于管理前后端服务的启动、停止和重启
"""
import os
import sys
import argparse
import subprocess
import signal
import time

def get_backend_pid():
    """获取后端服务进程ID"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "uvicorn main:app"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
        return None
    except Exception as e:
        print(f"获取后端进程ID失败: {e}")
        return None

def get_frontend_pid():
    """获取前端服务进程ID"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "bun run dev"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
        return None
    except Exception as e:
        print(f"获取前端进程ID失败: {e}")
        return None

def stop_process(pid):
    """停止进程"""
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            # 等待进程退出
            time.sleep(2)
            # 如果还在运行，强制终止
            if os.path.exists(f"/proc/{pid}"):
                os.kill(pid, signal.SIGKILL)
            return True
        except Exception as e:
            print(f"停止进程 {pid} 失败: {e}")
            return False
    return True

def start_backend():
    """启动后端服务"""
    os.chdir("/Users/liupeng/workspace/qbot/backend")
    subprocess.Popen(["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"])
    print("后端服务启动中...")
    time.sleep(3)
    print("后端服务已启动")

def start_frontend():
    """启动前端服务"""
    os.chdir("/Users/liupeng/workspace/qbot/frontend")
    subprocess.Popen(["bun", "run", "dev"])
    print("前端服务启动中...")
    time.sleep(3)
    print("前端服务已启动")

def stop_backend():
    """停止后端服务"""
    pid = get_backend_pid()
    if stop_process(pid):
        print("后端服务已停止")
    else:
        print("后端服务停止失败")

def stop_frontend():
    """停止前端服务"""
    pid = get_frontend_pid()
    if stop_process(pid):
        print("前端服务已停止")
    else:
        print("前端服务停止失败")

def restart_backend():
    """重启后端服务"""
    stop_backend()
    start_backend()

def restart_frontend():
    """重启前端服务"""
    stop_frontend()
    start_frontend()

def main():
    parser = argparse.ArgumentParser(description="服务管理脚本")
    parser.add_argument("command", choices=["start", "stop", "restart"], help="命令")
    parser.add_argument("service", choices=["backend", "frontend", "all"], help="服务类型")
    args = parser.parse_args()
    
    if args.service in ["backend", "all"]:
        if args.command == "start":
            start_backend()
        elif args.command == "stop":
            stop_backend()
        elif args.command == "restart":
            restart_backend()
    
    if args.service in ["frontend", "all"]:
        if args.command == "start":
            start_frontend()
        elif args.command == "stop":
            stop_frontend()
        elif args.command == "restart":
            restart_frontend()

if __name__ == "__main__":
    main()