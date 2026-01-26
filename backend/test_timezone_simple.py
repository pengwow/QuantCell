#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单时区测试脚本
专注于测试FastAPI的JSON序列化和自定义编码器
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

# 测试3: 测试main.py中的自定义JSON编码器
print("\n=== 测试3: 测试自定义JSON编码器 ===")
from main import custom_json_encoder, CustomJSONResponse
import json

# 测试数据
test_data = {
    "name": "test",
    "created_at": datetime.now(),  # 无时区
    "updated_at": datetime.now(pytz.timezone('Asia/Shanghai')),  # 有上海时区
    "event_time": datetime.now(pytz.utc)  # 有UTC时区
}

print("原始数据:")
for key, value in test_data.items():
    print(f"  {key}: {value} (类型: {type(value)}, 时区: {value.tzinfo})")

# 测试自定义编码器
print("\n使用自定义编码器编码:")
for key, value in test_data.items():
    if isinstance(value, datetime):
        try:
            encoded = custom_json_encoder(value)
            print(f"  {key}: {encoded}")
        except Exception as e:
            print(f"  {key}: 编码失败 - {e}")

# 测试完整的JSON序列化
print("\n完整JSON序列化测试:")
json_str = json.dumps(test_data, default=custom_json_encoder, ensure_ascii=False)
print(f"JSON序列化结果: {json_str}")

# 测试4: 测试ApiResponse模型
print("\n=== 测试4: 测试ApiResponse模型 ===")
from common.schemas import ApiResponse

# 创建ApiResponse实例
api_response = ApiResponse(
    code=0,
    message="操作成功",
    data=test_data
)

print(f"ApiResponse实例: {api_response}")
print(f"ApiResponse.timestamp: {api_response.timestamp}")

# 转换为字典
api_response_dict = api_response.model_dump()
print(f"\nApiResponse转换为字典:")
print(f"  code: {api_response_dict['code']}")
print(f"  message: {api_response_dict['message']}")
print(f"  timestamp: {api_response_dict['timestamp']}")
print(f"  data: {api_response_dict['data']}")

# 测试5: 测试FastAPI的json_encoders配置
print("\n=== 测试5: 测试FastAPI的json_encoders配置 ===")
from fastapi.encoders import jsonable_encoder
from main import app

# 测试jsonable_encoder
print("使用jsonable_encoder编码test_data:")
encoded = jsonable_encoder(test_data)
for key, value in encoded.items():
    print(f"  {key}: {value} (类型: {type(value)})")

# 测试6: 测试不同时区的datetime对象转换
print("\n=== 测试6: 测试不同时区的datetime对象转换 ===")

# 模拟数据库中存储的UTC时间（无时区信息）
db_time_naive = datetime(2026, 1, 26, 13, 0, 0)  # 假设这是数据库中存储的时间
print(f"数据库原始时间(无时区): {db_time_naive}")
print(f"预期上海时间: 2026-01-26 21:00:00")

# 模拟FastAPI的JSON序列化过程
if app.json_encoders and datetime in app.json_encoders:
    print(f"\n使用FastAPI的json_encoders编码:")
    encoded_time = app.json_encoders[datetime](db_time_naive)
    print(f"  编码结果: {encoded_time}")
    print(f"  类型: {type(encoded_time)}")
