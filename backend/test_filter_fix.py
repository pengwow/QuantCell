#!/usr/bin/env python3
"""验证时间戳过滤修复"""
import pandas as pd
from pathlib import Path
from scripts.data_cli import filter_by_date_range

file_path = Path('data/source/crypto/spot/klines/15m/ETHUSDT.parquet')
print(f'📂 加载数据文件: {file_path.name}\n')

df = pd.read_parquet(file_path)
print(f'原始数据量: {len(df)} 条记录')
print(f'时间戳范围: {df["timestamp"].min()} ~ {df["timestamp"].max()}')

# 测试过滤
start = '2026-01-09'
end = '2026-03-05'

print(f'\n🔍 测试时间过滤:')
print(f'   请求范围: {start} ~ {end}')

filtered_df = filter_by_date_range(df.copy(), start, end)

print(f'\n✅ 过滤结果:')
print(f'   剩余数据量: {len(filtered_df)} 条记录')
print(f'   过滤比例: {len(filtered_df)/len(df)*100:.2f}%')

if len(filtered_df) > 0:
    print(f'\n📊 过滤后数据示例 (前3条):')
    # 转换时间戳显示
    sample = filtered_df.head(3).copy()
    sample['datetime'] = pd.to_datetime(sample['timestamp'], unit='us')
    print(sample[['datetime', 'open', 'high', 'low', 'close']].to_string())

    print(f'\n✨ 时间范围:')
    min_ts = filtered_df['timestamp'].min()
    max_ts = filtered_df['timestamp'].max()
    min_dt = pd.to_datetime(min_ts, unit='us')
    max_dt = pd.to_datetime(max_ts, unit='us')
    print(f'   开始: {min_dt}')
    print(f'   结束: {max_dt}')
else:
    print('\n❌ 过滤后无数据！修复可能未生效。')

print('\n' + '='*60)
print('✅ 验证完成！')
