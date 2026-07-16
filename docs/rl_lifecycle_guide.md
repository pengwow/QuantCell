# RL 策略完整生命周期指南

## 1. 训练模型

### 1.1 基础训练

```bash
# CLI 方式
cd backend
python scripts/rl_cli.py train --symbol BTCUSDT --algorithm ppo --timesteps 30000

# Python 方式
from rl.service import RLService
from rl.models import RLTrainConfig

config = RLTrainConfig(
    symbol="BTCUSDT",
    algorithm="ppo",        # ppo / sac / a2c
    timesteps=30000,
    reward="pnl",           # pnl / sharpe / sortino
    interval="15m",
    lookback_days=90,
    initial_capital=100_000,
    transaction_cost=0.001,
)
result = RLService().train(config)
# result["model_path"] → 模型保存路径
```

### 1.2 自定义奖励函数训练

```python
from rl.service import RLService
from rl.models import RLTrainConfig

def my_reward(**kwargs):
    """自定义奖励：PnL + 交易惩罚"""
    pnl = kwargs["current_portfolio"] - kwargs["prev_portfolio"]
    initial = kwargs["info"].get("initial_capital", 100_000)
    reward = (pnl / initial) * 100
    if kwargs["action"] != 0:
        reward -= 0.5  # 每笔交易扣 0.5 分
    return reward

config = RLTrainConfig(symbol="BTCUSDT", algorithm="ppo", timesteps=30000)
result = RLService().train(config, reward_fn=my_reward)
```

### 1.3 Optuna 超参数优化

```bash
cd backend
python -m rl.hpo --symbol BTCUSDT --trials 30 --timesteps 10000
```

### 1.4 自定义 Gymnasium 环境训练

```python
from rl.env import TradingEnv
from rl.service import RLService
from stable_baselines3 import PPO

svc = RLService()
df = svc._fetch_market_data("BTCUSDT", "15m", 90)

env = TradingEnv(df, initial_capital=100_000, transaction_cost=0.001)
# 12维观测: 价格/成交量/SMA/EMA/RSI/MACD/Bollinger/ATR/动量

model = PPO("MlpPolicy", env, learning_rate=3e-4, device="cpu")
model.learn(total_timesteps=30000)
model.save("data/rl_models/my_model.zip")
```

---

## 2. 回测模型

### 2.1 CLI 回测

```bash
cd backend

# 基础回测
python scripts/backtest_cli.py run -s rl_ppo --sym BTCUSDT --tf 15m

# 生成图表
python scripts/backtest_cli.py run -s rl_ppo --sym BTCUSDT --tf 15m --chart

# 自定义参数
python scripts/backtest_cli.py run -s rl_ppo --sym ETHUSDT --tf 15m --chart --cash 50000
```

### 2.2 Python 回测

```python
from rl.service import RLService

svc = RLService()
result = svc.backtest(
    model_path="data/rl_models/my_model.zip",
    symbol="BTCUSDT",
    interval="15m",
    lookback_days=90,
)
print(f"PnL: ${result['total_pnl']:.2f}")
print(f"Sharpe: {result['sharpe_ratio']:.4f}")
print(f"MaxDD: {result['max_drawdown']:.2f}")
```

### 2.3 自定义环境回测

```python
from rl.env import TradingEnv
from stable_baselines3 import PPO

env = TradingEnv(df, initial_capital=100_000)
model = PPO.load("data/rl_models/my_model.zip")

obs, _ = env.reset()
for _ in range(len(df)):
    action, _ = model.predict(obs, deterministic=True)
    obs, reward, term, trunc, info = env.step(action)
    if term or trunc:
        break

print(f"Final: ${info['portfolio_value']:.2f}, Trades: {info['trades']}")
```

---

## 3. 实盘运行

### 3.1 配置交易所

```python
from axon_quant import BinanceAdapter, ExchangeConfig

# 创建交易所适配器（testnet）
config = ExchangeConfig(
    exchange_id="binance",
    api_key="your_api_key",
    api_secret="your_api_secret",
    testnet=True,  # 先用测试网
)
adapter = BinanceAdapter(config)
```

### 3.2 运行实盘策略

```python
from strategy.loop import StrategyLoop
from strategies.rl_ppo import RLPP策略

# 加载训练好的模型
strategy = RLPP策略(model_path="data/rl_models/my_model.zip")

# 创建实盘循环
loop = StrategyLoop(
    adapter=adapter,
    strategy=strategy,
    symbol="BTCUSDT",
    interval=15,  # 15秒轮询
)

# 启动
loop.start()
# ... 运行一段时间 ...
loop.stop()
```

### 3.3 TradingEngine 统一管理

```python
from engine.trading_engine import TradingEngine
from engine.config import EngineConfig

config = EngineConfig(
    exchange="binance",
    trading_mode="paper",  # paper / live
)
engine = TradingEngine(config)

# 注册策略
sid = engine.start_strategy(strategy, ["BTCUSDT"])

# 查看状态
engine.list_strategies()

# 停止策略
engine.stop_strategy(sid)
```

### 3.4 实盘安全检查清单

```
✅ 使用 testnet 先验证
✅ 设置止损线（最大回撤限制）
✅ 监控订单执行状态
✅ 记录所有交易日志
✅ 定期检查模型性能
```

---

## 4. 实时优化模型

### 4.1 Walk-Forward 优化（推荐）

```python
from rl.service import RLService
from rl.models import RLTrainConfig

svc = RLService()

# 用最近数据重新训练
config = RLTrainConfig(
    symbol="BTCUSDT",
    algorithm="ppo",
    timesteps=10000,  # 少量步数，快速更新
    interval="15m",
    lookback_days=30,  # 只用最近30天数据
)

# 每天/每周执行一次
result = svc.train(config)
# 用新模型替换旧模型
```

### 4.2 定时重训练脚本

```python
# scripts/rl_retrain.py
import schedule
import time
from rl.service import RLService
from rl.models import RLTrainConfig

def retrain():
    config = RLTrainConfig(
        symbol="BTCUSDT",
        algorithm="ppo",
        timesteps=10000,
        interval="15m",
        lookback_days=30,
    )
    result = RLService().train(config)
    print(f"重训练完成: {result['model_path']}")

# 每天凌晨3点重训练
schedule.every().day.at("03:00").do(retrain)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### 4.3 在线学习（高级）

```python
from rl.env import TradingEnv
from stable_baselines3 import PPO

# 加载已有模型
model = PPO.load("data/rl_models/current_model.zip")

# 用最新数据微调
env = TradingEnv(new_data, initial_capital=100_000)
model.learn(total_timesteps=5000, reset_num_timesteps=False)

# 保存更新后的模型
model.save("data/rl_models/current_model.zip")
```

### 4.4 A/B 测试

```python
# 同时运行两个模型，比较表现
from rl.env import TradingEnv

env_a = TradingEnv(test_data)
env_b = TradingEnv(test_data)

model_a = PPO.load("model_v1.zip")
model_b = PPO.load("model_v2.zip")

# 各跑一遍，比较 PnL
for env, model, name in [(env_a, model_a, "v1"), (env_b, model_b, "v2")]:
    obs, _ = env.reset()
    for _ in range(len(test_data)):
        a, _ = model.predict(obs, deterministic=True)
        obs, _, term, trunc, info = env.step(a)
        if term or trunc: break
    print(f"{name}: PnL=${info['portfolio_value']-100_000:.2f}")
```

---

## 完整工作流

```
1. 训练
   rl_cli.py train --symbol BTCUSDT --timesteps 30000
   ↓
2. 回测
   backtest_cli.py run -s rl_ppo --sym BTCUSDT --tf 15m --chart
   ↓
3. 实盘（testnet）
   StrategyLoop(adapter=testnet, strategy=model, symbol=BTCUSDT)
   ↓
4. 实盘（live）
   StrategyLoop(adapter=live, strategy=model, symbol=BTCUSDT)
   ↓
5. 优化
   每周重训练 → 回测验证 → 替换模型
```
