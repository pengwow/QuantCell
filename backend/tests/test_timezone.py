#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时区测试脚本
用于验证FastAPI应用的时区处理是否正确
"""

import sys
import os
from datetime import datetime
import pytz

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 测试1: 检查datetime.now()和带时区的datetime.now()的差异
print("=== 测试1: 日期时间对象创建 ===")
now_naive = datetime.now()
now_with_tz = datetime.now(pytz.timezone('Asia/Shanghai'))
now_utc = datetime.now(pytz.utc)

print(f"当前时间(无时区): {now_naive}")
print(f"当前时间(上海时区): {now_with_tz}")
print(f"当前时间(UTC): {now_utc}")
print(f"UTC转换为上海时区: {now_utc.astimezone(pytz.timezone('Asia/Shanghai'))}")

# 测试2: 模拟数据库中存储的UTC时间转换
print("\n=== 测试2: 时区转换 ===")
# 模拟数据库中存储的UTC时间（无时区信息）
db_time_naive = datetime(2024, 1, 26, 12, 0, 0)  # 假设这是数据库中存储的时间
print(f"数据库原始时间(无时区): {db_time_naive}")

# 假设数据库中存储的是UTC时间，添加UTC时区信息
db_time_utc = db_time_naive.replace(tzinfo=pytz.utc)
print(f"添加UTC时区后: {db_time_utc}")

# 转换为上海时区
db_time_shanghai = db_time_utc.astimezone(pytz.timezone('Asia/Shanghai'))
print(f"转换为上海时区: {db_time_shanghai}")
print(f"格式化后: {db_time_shanghai.strftime('%Y-%m-%d %H:%M:%S')}")

# 测试3: 测试SQLAlchemy模型中的datetime字段
print("\n=== 测试3: 测试SQLAlchemy模型 ===")
from collector.db.database import get_current_time
print(f"get_current_time()返回值: {get_current_time()}")
print(f"get_current_time()类型: {type(get_current_time())}")
print(f"get_current_time()是否带时区: {get_current_time().tzinfo is not None}")

# 测试4: 测试SystemConfigBusiness.get_with_details()方法
print("\n=== 测试4: 测试SystemConfigBusiness.get_with_details() ===")
from collector.db import SystemConfigBusiness as SystemConfig

# 先设置一个测试配置
SystemConfig.set("test_key", "test_value", "测试配置")

# 获取配置详情
config = SystemConfig.get_with_details("test_key")
print(f"配置详情: {config}")
if config:
    print(f"created_at: {config['created_at']}")
    print(f"updated_at: {config['updated_at']}")

# 测试5: 测试TaskBusiness.get_all()方法
print("\n=== 测试5: 测试TaskBusiness.get_all() ===")
from collector.db import TaskBusiness

tasks = TaskBusiness.get_all()
print(f"任务数量: {len(tasks)}")
for task_id, task in list(tasks.items())[:2]:  # 只显示前2个任务
    print(f"任务ID: {task_id}")
    print(f"  start_time: {task['start_time']} (类型: {type(task['start_time'])})")
    print(f"  end_time: {task['end_time']} (类型: {type(task['end_time'])})")
    print(f"  created_at: {task['created_at']} (类型: {type(task['created_at'])})")
    print(f"  updated_at: {task['updated_at']} (类型: {type(task['updated_at'])})")

# 测试6: 测试FastAPI的JSON编码器
print("\n=== 测试6: 测试FastAPI的JSON编码器 ===")
from fastapi.encoders import jsonable_encoder

# 测试不同类型的datetime对象
test_data = {
    "naive_datetime": datetime.now(),
    "shanghai_datetime": datetime.now(pytz.timezone('Asia/Shanghai')),
    "utc_datetime": datetime.now(pytz.utc),
    "db_naive_datetime": datetime(2024, 1, 26, 12, 0, 0)
}

print("原始测试数据:")
for key, value in test_data.items():
    print(f"  {key}: {value} (类型: {type(value)}, 时区: {value.tzinfo})")

print("\n使用jsonable_encoder编码后:")
encoded = jsonable_encoder(test_data)
for key, value in encoded.items():
    print(f"  {key}: {value} (类型: {type(value)})")

# 测试7: 测试自定义JSON编码器
print("\n=== 测试7: 测试自定义JSON编码器 ===")
from main import custom_json_encoder
import json

def test_custom_encoder(obj):
    return custom_json_encoder(obj)

# 测试自定义编码器
for key, value in test_data.items():
    try:
        encoded = test_custom_encoder(value)
        print(f"  {key}: {encoded}")
    except Exception as e:
        print(f"  {key}: 编码失败 - {e}")

# 测试完整的JSON序列化
print("\n完整JSON序列化测试:")
data_with_datetime = {
    "name": "test",
    "created_at": datetime.now(),
    "updated_at": datetime.now(pytz.timezone('Asia/Shanghai'))
}

json_str = json.dumps(data_with_datetime, default=test_custom_encoder)
print(f"JSON序列化结果: {json_str}")
