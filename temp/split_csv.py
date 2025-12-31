import pandas as pd

# 读取测试数据
df = pd.read_csv('test_crypto.csv')

# 按交易对分组并保存为单独的文件
for symbol, group in df.groupby('symbol'):
    group.to_csv(f'test_{symbol}.csv', index=False)
    print(f'Created test_{symbol}.csv')
