#!/usr/bin/env python3
from pathlib import Path

import pandas as pd

# 读取CSV文件
csv_path = Path("/Users/liupeng/.qlib/crypto_data/source/1d/BTCUSDT.csv")
df = pd.read_csv(csv_path)

# 将date列转换为datetime类型，使用mixed格式处理不同日期格式
df['date'] = pd.to_datetime(df['date'], format='mixed')

# 提取唯一的日期，只保留日期部分
dates = df['date'].dt.date.unique()

# 按日期排序
dates = sorted(dates)

# 写入日历文件
calendar_path = Path("/Users/liupeng/workspace/qbot/backend/data/source/calendars/1d.txt")
with open(calendar_path, 'w') as f:
    for date in dates:
        f.write(f"{date.strftime('%Y-%m-%d')}\n")

print(f"已生成日历文件，包含 {len(dates)} 个日期")
print(f"文件路径: {calendar_path}")
