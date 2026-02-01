#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API时区测试脚本
测试修复后的API响应是否正确处理时区
"""

import requests
import time
from datetime import datetime
import pytz

# 测试配置
BASE_URL = "http://localhost:8000"

# 测试1: 获取系统配置列表
print("=== 测试1: 获取系统配置列表 ===")
try:
    response = requests.get(f"{BASE_URL}/api/config/list")
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"响应: {data}")
    
    if data.get("code") == 0 and data.get("data"):
        print("\n配置项示例:")
        # 取第一个配置项查看时间字段
        config_items = list(data["data"].values())
        if config_items:
            config = config_items[0]
            print(f"  key: {config.get('key')}")
            print(f"  created_at: {config.get('created_at')}")
            print(f"  updated_at: {config.get('updated_at')}")
            print(f"  created_at类型: {type(config.get('created_at'))}")
except Exception as e:
    print(f"测试1失败: {e}")

# 测试2: 获取任务列表
print("\n=== 测试2: 获取任务列表 ===")
try:
    response = requests.get(f"{BASE_URL}/api/tasks/list")
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"响应: {data}")
    
    if data.get("code") == 0 and data.get("data"):
        print("\n任务示例:")
        # 取第一个任务查看时间字段
        tasks = list(data["data"].values())
        if tasks:
            task = tasks[0]
            print(f"  task_id: {task.get('task_id')}")
            print(f"  created_at: {task.get('created_at')}")
            print(f"  updated_at: {task.get('updated_at')}")
            print(f"  start_time: {task.get('start_time')}")
            print(f"  end_time: {task.get('end_time')}")
except Exception as e:
    print(f"测试2失败: {e}")

# 测试3: 获取资产池列表
print("\n=== 测试3: 获取资产池列表 ===")
try:
    response = requests.get(f"{BASE_URL}/api/data-pools/list")
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"响应: {data}")
    
    if data.get("code") == 0 and data.get("data"):
        print("\n资产池示例:")
        # 取第一个资产池查看时间字段
        pools = data["data"]
        if pools:
            pool = pools[0]
            print(f"  id: {pool.get('id')}")
            print(f"  name: {pool.get('name')}")
            print(f"  created_at: {pool.get('created_at')}")
            print(f"  updated_at: {pool.get('updated_at')}")
except Exception as e:
    print(f"测试3失败: {e}")

# 测试4: 获取定时任务列表
print("\n=== 测试4: 获取定时任务列表 ===")
try:
    response = requests.get(f"{BASE_URL}/api/scheduled-tasks/list")
    print(f"状态码: {response.status_code}")
    data = response.json()
    print(f"响应: {data}")
    
    if data.get("code") == 0 and data.get("data"):
        print("\n定时任务示例:")
        # 取第一个定时任务查看时间字段
        tasks = list(data["data"].values())
        if tasks:
            task = tasks[0]
            print(f"  id: {task.get('id')}")
            print(f"  name: {task.get('name')}")
            print(f"  created_at: {task.get('created_at')}")
            print(f"  updated_at: {task.get('updated_at')}")
            print(f"  start_time: {task.get('start_time')}")
            print(f"  end_time: {task.get('end_time')}")
            print(f"  last_run_time: {task.get('last_run_time')}")
            print(f"  next_run_time: {task.get('next_run_time')}")
except Exception as e:
    print(f"测试4失败: {e}")

# 测试5: 验证时间戳是否正确
print("\n=== 测试5: 验证时间戳是否正确 ===")
try:
    # 获取当前时间
    current_time = datetime.now(pytz.timezone('Asia/Shanghai'))
    current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"当前上海时间: {current_time_str}")
    
    # 获取API响应时间戳
    response = requests.get(f"{BASE_URL}/api/config/list")
    data = response.json()
    api_timestamp = data.get("timestamp")
    print(f"API响应时间戳: {api_timestamp}")
    
    if api_timestamp:
        # 比较时间差（应该在1分钟内）
        api_time = datetime.strptime(api_timestamp, '%Y-%m-%d %H:%M:%S')
        time_diff = abs((current_time - api_time).total_seconds())
        print(f"时间差: {time_diff}秒")
        if time_diff < 60:
            print("✅ API时间戳正确，与当前时间差在1分钟内")
        else:
            print("❌ API时间戳错误，与当前时间差超过1分钟")
except Exception as e:
    print(f"测试5失败: {e}")

print("\n=== 测试完成 ===")
