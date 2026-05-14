#!/usr/bin/env python3
"""检查 ETHUSDT.parquet 数据的时间范围"""
import pandas as pd
from pathlib import Path

file_path = Path('data/source/crypto/spot/klines/15m/ETHUSDT.parquet')
print(f'文件: {file_path.absolute()}')
print(f'文件大小: {file_path.stat().st_size/1024:.1f} KB\n')

df = pd.read_parquet(file_path)
print(f'原始数据形状: {df.shape}')
print(f'列名: {list(df.columns)}\n')

# timestamp 列是毫秒级 Unix 时间戳
ts_col = df['timestamp']

print(f'⏰ 时间戳列信息:')
print(f'   数据类型: {ts_col.dtype}')
print(f'   最小值: {ts_col.min()}')
print(f'   最大值: {ts_col.max()}')
print(f'   前5个值: {ts_col.head().tolist()}')
print(f'   后5个值: {ts_col.tail().tolist()}\n')

# 尝试不同的单位进行转换
if ts_col.dtype == 'int64':
    print('⏰ 时间列 "timestamp" 是整数类型，尝试不同单位转换...\n')
    
    # 测试不同单位
    units_to_try = ['ms', 's', 'us', 'ns']
    
    for unit in units_to_try:
        try:
            ts_datetime = pd.to_datetime(ts_col.head(10), unit=unit)
            print(f'✅ 单位 "{unit}" 转换成功:')
            print(f'   示例时间: {ts_datetime.iloc[0]} ~ {ts_datetime.iloc[-1]}')
            
            # 如果看起来合理（在 2020-2030 年之间），使用这个单位
            if 2020 <= ts_datetime.iloc[0].year <= 2030:
                print(f'   ✅ 使用单位 "{unit}" 进行完整转换\n')
                
                # 完整转换
                ts_datetime_full = pd.to_datetime(ts_col, unit=unit)
                
                print(f'⏰ 实际时间范围:')
                print(f'   开始: {ts_datetime_full.min()}')
                print(f'   结束: {ts_datetime_full.max()}')
                print(f'   记录数: {len(df)}')
                
                # 测试过滤 - 用户请求的范围
                start = pd.Timestamp('2026-01-09')
                end = pd.Timestamp('2026-03-05')
                
                # 将 start/end 也转换为对应单位的时间戳进行比较
                if unit == 'ms':
                    start_ts = int(start.timestamp() * 1000)
                    end_ts = int(end.timestamp() * 1000)
                elif unit == 's':
                    start_ts = int(start.timestamp())
                    end_ts = int(end.timestamp())
                else:
                    # 对于 us 和 ns，先转换为毫秒再转换
                    start_ts = int(start.timestamp() * 1000)
                    end_ts = int(end.timestamp() * 1000)
                    # 需要调整单位
                    if unit == 'us':
                        start_ts *= 1000
                        end_ts *= 1000
                    elif unit == 'ns':
                        start_ts *= 1000000
                        end_ts *= 1000000
                
                print(f'\n🔍 过滤测试:')
                print(f'   请求范围: {start} ~ {end}')
                print(f'   请求范围(时间戳): {start_ts} ~ {end_ts}')
                print(f'   数据范围(时间戳): {ts_col.min()} ~ {ts_col.max()}')
                
                mask = (ts_col >= start_ts) & (ts_col <= end_ts)
                filtered_count = mask.sum()
                
                print(f'\n   匹配行数: {filtered_count} / {len(df)} ({filtered_count/len(df)*100:.2f}%)')
                
                if filtered_count > 0:
                    print(f'\n✅ 有 {filtered_count} 条匹配数据！')
                    
                    # 显示前3条
                    matched_df = df[mask].head(3)
                    matched_df['datetime'] = pd.to_datetime(matched_df['timestamp'], unit=unit)
                    print('\n前3条匹配数据:')
                    print(matched_df[['datetime', 'open', 'high', 'low', 'close', 'volume']].to_string())
                else:
                    print(f'\n❌ 无匹配数据！')
                    print(f'\n💡 原因分析:')
                    print(f'   数据时间范围: {ts_datetime_full.min().strftime("%Y-%m-%d")} ~ {ts_datetime_full.max().strftime("%Y-%m-%d")}')
                    print(f'   请求时间范围: 2026-01-09 ~ 2026-03-05')
                    
                    current_date = pd.Timestamp.now()
                    if ts_datetime_full.max() < current_date:
                        print(f'\n   ⚠️ 数据是历史数据 (当前日期: {current_date.strftime("%Y-%m-%d")})')
                        print(f'   数据只到: {ts_datetime_full.max().strftime("%Y-%m-%d")}')
                    
                    print(f'\n🔧 解决方案：使用数据实际覆盖的时间范围')
                    data_start = ts_datetime_full.min()
                    data_end = ts_datetime_full.max()
                    
                    print(f'   --time-range {data_start.strftime("%Y%m%d")}-{data_end.strftime("%Y%m%d")}')
                
                break  # 找到合适的单位就退出
        except Exception as e:
            print(f'❌ 单位 "{unit}" 转换失败: {e}\n')
