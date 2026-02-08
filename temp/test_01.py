import vectorbt as vbt

data = vbt.YFData.download("BTC-USD")
price = data.get("Close")

pf = vbt.Portfolio.from_holding(price, init_cash=100)
print(pf.total_profit())

fast_ma = vbt.MA.run(price, 10)
slow_ma = vbt.MA.run(price, 50)
entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=100)
print(pf.total_profit())

import numpy as np

symbols = ["BTC-USD", "ETH-USD"]
data = vbt.YFData.download(symbols, missing_index="drop")
price = data.get("Close")

n = np.random.randint(10, 101, size=1000).tolist()
pf = vbt.Portfolio.from_random_signals(price, n=n, init_cash=100, seed=42)

mean_expectancy = pf.trades.expectancy().groupby(["randnx_n", "symbol"]).mean()
fig = mean_expectancy.unstack().vbt.scatterplot(xaxis_title="randnx_n", yaxis_title="mean_expectancy")
fig.show()