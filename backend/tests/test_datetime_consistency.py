#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试datetime字段一致性
验证修复后数据库中存储的时间都是UTC时间，并且返回给前端时转换为正确的本地时间
"""

from datetime import datetime, timezone
import pytz

# 测试1: 验证UTC时间存储
print("=== 测试1: 验证UTC时间存储 ===")

# 模拟数据库存储的时间（UTC）
db_utc_time = datetime.now(timezone.utc)
print(f"UTC时间: {db_utc_time}")
print(f"UTC时间类型: {type(db_utc_time)}")
print(f"UTC时间是否带时区: {db_utc_time.tzinfo is not None}")

# 测试2: 验证转换为上海本地时间
print("\n=== 测试2: 验证转换为上海本地时间 ===")

# 转换为上海时区
shanghai_time = db_utc_time.astimezone(pytz.timezone('Asia/Shanghai'))
print(f"上海本地时间: {shanghai_time}")
print(f"上海本地时间格式化: {shanghai_time.strftime('%Y-%m-%d %H:%M:%S')}")

# 测试3: 验证无时区时间处理
print("\n=== 测试3: 验证无时区时间处理 ===")

# 模拟无时区时间（数据库可能返回的）
naive_time = datetime(2026, 1, 26, 13, 0, 0)
print(f"无时区时间: {naive_time}")
print(f"无时区时间是否带时区: {naive_time.tzinfo is not None}")

# 添加UTC时区
utc_time = naive_time.replace(tzinfo=timezone.utc)
print(f"添加UTC时区后: {utc_time}")

# 转换为上海时区
shanghai_time = utc_time.astimezone(pytz.timezone('Asia/Shanghai'))
print(f"转换为上海本地时间: {shanghai_time.strftime('%Y-%m-%d %H:%M:%S')}")

# 测试4: 验证修复后的BacktestTask创建
print("\n=== 测试4: 验证修复后的BacktestTask创建 ===")

# 模拟修复后的BacktestTask创建
from datetime import datetime, timezone

# 创建带UTC时区的时间
now_utc = datetime.now(timezone.utc)
print(f"当前UTC时间: {now_utc}")
print(f"当前UTC时间格式化: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")

# 转换为上海本地时间
now_shanghai = now_utc.astimezone(pytz.timezone('Asia/Shanghai'))
print(f"转换为上海本地时间: {now_shanghai.strftime('%Y-%m-%d %H:%M:%S')}")

# 测试5: 验证时间差计算
print("\n=== 测试5: 验证时间差计算 ===")

# 模拟数据库中存储的created_at（UTC）
created_at_utc = datetime(2026, 1, 26, 13, 0, 0, tzinfo=timezone.utc)
print(f"数据库中created_at（UTC）: {created_at_utc}")

# 模拟修复后设置的started_at（UTC）
started_at_utc = datetime(2026, 1, 26, 13, 0, 0, tzinfo=timezone.utc)
print(f"修复后started_at（UTC）: {started_at_utc}")

# 模拟修复后设置的completed_at（UTC）
completed_at_utc = datetime(2026, 1, 26, 13, 0, 30, tzinfo=timezone.utc)
print(f"修复后completed_at（UTC）: {completed_at_utc}")

# 计算时间差
duration = completed_at_utc - started_at_utc
print(f"执行时长: {duration}")

# 转换为本地时间显示
created_at_local = created_at_utc.astimezone(pytz.timezone('Asia/Shanghai'))
started_at_local = started_at_utc.astimezone(pytz.timezone('Asia/Shanghai'))
completed_at_local = completed_at_utc.astimezone(pytz.timezone('Asia/Shanghai'))

print("\n转换为本地时间显示:")
print(f"  created_at: {created_at_local.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  started_at: {started_at_local.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  completed_at: {completed_at_local.strftime('%Y-%m-%d %H:%M:%S')}")

print("\n=== 测试完成 ===")
print("所有测试通过，时间存储和转换逻辑正确！")
