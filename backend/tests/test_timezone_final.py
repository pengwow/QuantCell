#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终时区测试脚本
专注于测试核心时区转换逻辑和Pydantic模型
"""

from datetime import datetime
import pytz

# 测试1: 核心时区转换逻辑
print("=== 测试1: 核心时区转换逻辑 ===")

# 模拟数据库中存储的UTC时间（无时区信息）
db_time_naive = datetime(2026, 1, 26, 13, 0, 0)  # 假设这是数据库中存储的时间
print(f"数据库原始时间(无时区): {db_time_naive}")
print(f"数据库原始时间类型: {type(db_time_naive)}")
print(f"数据库原始时间是否带时区: {db_time_naive.tzinfo is not None}")

# 关键修复：假设数据库中存储的是UTC时间，先添加UTC时区信息
db_time_utc = db_time_naive.replace(tzinfo=pytz.utc)
print(f"添加UTC时区后: {db_time_utc}")
print(f"添加UTC时区后类型: {type(db_time_utc)}")
print(f"添加UTC时区后是否带时区: {db_time_utc.tzinfo is not None}")

# 转换为上海时区
db_time_shanghai = db_time_utc.astimezone(pytz.timezone('Asia/Shanghai'))
print(f"转换为上海时区: {db_time_shanghai}")
print(f"上海时区时间类型: {type(db_time_shanghai)}")
print(f"格式化后: {db_time_shanghai.strftime('%Y-%m-%d %H:%M:%S')}")

# 测试2: 验证无时区信息的datetime转换
print("\n=== 测试2: 验证无时区信息的datetime转换 ===")

def fix_timezone(dt):
    """修复datetime对象的时区问题
    
    Args:
        dt: datetime对象，可能带或不带时区信息
        
    Returns:
        str: 格式化后的本地时间字符串
    """
    if dt is None:
        return None
    # 如果datetime对象没有时区信息，添加UTC时区
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    # 转换为UTC+8时间并格式化为字符串
    return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')

# 测试不同情况
test_cases = [
    datetime(2026, 1, 26, 0, 0, 0),  # 00:00 UTC -> 08:00 上海
    datetime(2026, 1, 26, 12, 0, 0),  # 12:00 UTC -> 20:00 上海
    datetime(2026, 1, 26, 16, 0, 0),  # 16:00 UTC -> 00:00 上海（次日）
    datetime.now(),  # 当前时间
    None  # None值
]

for test_dt in test_cases:
    result = fix_timezone(test_dt)
    print(f"{test_dt} -> {result}")

# 测试3: 测试Pydantic模型的timestamp字段
print("\n=== 测试3: 测试Pydantic模型的timestamp字段 ===")

from pydantic import BaseModel, Field

class TestApiResponse(BaseModel):
    """测试用API响应模型"""
    code: int
    message: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S'),
        description="响应时间戳"
    )

# 创建实例
response = TestApiResponse(code=0, message="操作成功")
print(f"API响应: {response}")
print(f"时间戳: {response.timestamp}")
print(f"时间戳类型: {type(response.timestamp)}")

# 测试4: 测试JSON序列化
print("\n=== 测试4: 测试JSON序列化 ===")
import json

# 自定义JSON编码器
def custom_json_encoder(obj):
    if isinstance(obj, datetime):
        # 如果datetime对象没有时区信息，添加UTC时区
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=pytz.utc)
        # 转换为UTC+8时间并格式化为字符串
        return obj.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# 测试数据
data = {
    "name": "test",
    "created_at": datetime(2026, 1, 26, 13, 0, 0),  # 无时区
    "updated_at": datetime.now(pytz.timezone('Asia/Shanghai')),  # 有上海时区
    "event_time": datetime.now(pytz.utc)  # 有UTC时区
}

print("原始数据:")
for key, value in data.items():
    print(f"  {key}: {value} (类型: {type(value)})")

# 测试JSON序列化
json_str = json.dumps(data, default=custom_json_encoder, ensure_ascii=False)
print(f"\nJSON序列化结果: {json_str}")

# 测试5: 模拟业务逻辑中的datetime处理
print("\n=== 测试5: 模拟业务逻辑中的datetime处理 ===")

# 模拟从数据库查询到的数据（无时区信息）
db_record = {
    "id": 1,
    "name": "test_record",
    "created_at": datetime(2026, 1, 26, 13, 0, 0),
    "updated_at": datetime(2026, 1, 26, 14, 0, 0)
}

print(f"数据库查询结果: {db_record}")

# 业务逻辑处理
def process_db_record(record):
    """处理数据库记录，修复时区问题"""
    processed = record.copy()
    # 处理所有datetime字段
    for key, value in processed.items():
        if isinstance(value, datetime):
            processed[key] = fix_timezone(value)
    return processed

processed_record = process_db_record(db_record)
print(f"处理后的数据: {processed_record}")

# 测试6: 验证修复后的时间是否正确
print("\n=== 测试6: 验证修复后的时间是否正确 ===")

# 模拟数据库中存储的时间（UTC）
db_time = datetime(2026, 1, 26, 13, 0, 0)
print(f"数据库中存储的时间(UTC): {db_time}")

# 修复时区
fixed_time = fix_timezone(db_time)
print(f"修复后显示的时间(上海): {fixed_time}")

# 验证是否相差8小时
import time
current_time = datetime.now()
current_shanghai = datetime.now(pytz.timezone('Asia/Shanghai'))
print(f"\n当前系统时间: {current_time}")
print(f"当前上海时间: {current_shanghai.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"当前UTC时间: {datetime.now(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')}")
