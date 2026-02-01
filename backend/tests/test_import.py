#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试导入路径
"""

import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

print(f"Python路径: {sys.path}")
print(f"当前目录: {current_dir}")

try:
    from backend.utils.timezone import to_utc_time, to_local_time, format_datetime
    print("成功导入 backend.utils.timezone")
except Exception as e:
    print(f"导入失败: {e}")

try:
    from collector.db.database import SessionLocal, init_database_config
    print("成功导入 collector.db.database")
except Exception as e:
    print(f"导入失败: {e}")
