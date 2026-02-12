# Binance交易所集成文档

本文档介绍QuantCell项目中Binance交易所连接模块的使用方法。

## 功能概述

Binance连接模块提供以下功能：

1. **REST API客户端** - 账户管理、市场行情、订单操作
2. **WebSocket实时数据** - K线、深度、交易数据实时推送
3. **模拟盘交易** - 无需真实资金即可测试交易策略

## 安装依赖

确保已安装python-binance库：

```bash
pip install python-binance
```

## 快速开始

### 1. 配置API密钥

复制配置文件模板：

```bash
cp config/binance_example.yaml config/binance.yaml
```

编辑 `config/binance.yaml`，填入您的API密钥：

```yaml
binance:
  api_key: "YOUR_API_KEY"
  api_secret: "YOUR_API_SECRET"
  testnet: true  # 使用测试网进行开发
```

### 2. REST API客户端使用

```python
from exchange.binance import BinanceClient, BinanceConfig
from exchange.binance.config import OrderSide, OrderType, TimeInForce

# 创建配置
config = BinanceConfig(
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET",
    testnet=True,
)

# 创建客户端
client = BinanceClient(config)

# 连接
client.connect()

# 获取账户余额
balances = client.get_balance()
for balance in balances:
    print(f"{balance.asset}: {balance.free} (locked: {balance.locked})")

# 获取最新价格
ticker = client.get_ticker("BTCUSDT")
print(f"BTC/USDT: {ticker.price}")

# 获取K线数据
klines = client.get_klines("BTCUSDT", "1h", limit=100)

# 创建市价买单
from exchange.binance.config import OrderRequest
order = OrderRequest(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=0.001,
)
response = client.create_order(order)
print(f"Order created: {response.order_id}")

# 断开连接
client.disconnect()
```

### 3. WebSocket实时数据

```python
import asyncio
from exchange.binance import BinanceWebSocketManager, BinanceConfig

async def main():
    config = BinanceConfig(testnet=True)
    ws_manager = BinanceWebSocketManager(config)
    
    # 连接
    await ws_manager.connect()
    
    # 定义回调函数
    def on_kline(data):
        print(f"Kline: {data['symbol']} O:{data['open']} H:{data['high']} L:{data['low']} C:{data['close']}")
    
    def on_trade(data):
        print(f"Trade: {data['symbol']} Price:{data['price']} Qty:{data['quantity']}")
    
    # 注册回调
    ws_manager.register_callback("kline", on_kline)
    ws_manager.register_callback("trade", on_trade)
    
    # 订阅数据
    await ws_manager.subscribe_kline("BTCUSDT", "1m")
    await ws_manager.subscribe_trade("BTCUSDT")
    
    # 运行一段时间
    await asyncio.sleep(60)
    
    # 断开连接
    await ws_manager.disconnect()

asyncio.run(main())
```

### 4. 模拟盘交易

```python
from exchange.binance import PaperTradingAccount
from exchange.binance.config import OrderSide, OrderType

# 创建模拟账户
account = PaperTradingAccount(
    initial_balance={"USDT": 10000.0, "BTC": 0.5},
    maker_fee=0.001,
    taker_fee=0.001,
)

# 更新市场价格
account.update_market_price("BTCUSDT", 50000.0)

# 创建市价买单
order = account.create_order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=0.01,
)
print(f"Order filled: {order.order_id}")

# 创建限价卖单
limit_order = account.create_order(
    symbol="BTCUSDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    quantity=0.01,
    price=55000.0,
)

# 获取账户摘要
summary = account.get_account_summary()
print(f"Total Equity: {summary['total_equity']}")
print(f"Unrealized PnL: {summary['unrealized_pnl']}")
```

## API参考

### BinanceClient

#### 账户相关

- `get_account()` - 获取账户信息
- `get_balance(asset=None)` - 获取余额

#### 市场行情

- `get_ticker(symbol)` - 获取最新价格
- `get_klines(symbol, interval, **kwargs)` - 获取K线数据
- `get_order_book(symbol, limit=100)` - 获取订单簿
- `get_recent_trades(symbol, limit=500)` - 获取最近成交

#### 订单操作

- `create_order(order)` - 创建订单
- `cancel_order(symbol, order_id)` - 取消订单
- `get_order(symbol, order_id)` - 查询订单
- `get_open_orders(symbol=None)` - 获取当前挂单
- `get_all_orders(symbol, **kwargs)` - 获取所有订单

### BinanceWebSocketManager

#### 订阅方法

- `subscribe_kline(symbol, interval="1m")` - 订阅K线
- `subscribe_depth(symbol, depth="20")` - 订阅深度
- `subscribe_trade(symbol)` - 订阅交易
- `subscribe_ticker(symbol)` - 订阅ticker
- `subscribe_user_data()` - 订阅用户数据流
- `unsubscribe(subscription_id)` - 取消订阅

#### 回调注册

- `register_callback(data_type, callback)` - 注册回调
- `unregister_callback(data_type, callback)` - 注销回调

### PaperTradingAccount

#### 订单操作

- `create_order(**kwargs)` - 创建订单
- `cancel_order(order_id)` - 取消订单
- `get_order(order_id)` - 获取订单
- `get_open_orders(symbol=None)` - 获取未成交订单

#### 账户信息

- `get_balance(asset)` - 获取余额
- `get_position(symbol)` - 获取持仓
- `get_all_positions()` - 获取所有持仓
- `get_account_summary()` - 获取账户摘要

#### 市场数据

- `update_market_price(symbol, price)` - 更新市场价格

## 错误处理

模块提供了以下异常类：

```python
from exchange.binance.exceptions import (
    BinanceError,              # 基础异常
    BinanceConnectionError,    # 连接错误
    BinanceAPIError,           # API错误
    BinanceWebSocketError,     # WebSocket错误
    BinanceOrderError,         # 订单错误
    BinanceAuthenticationError,# 认证错误
    BinanceRateLimitError,     # 速率限制
)
```

## 最佳实践

1. **使用测试网开发** - 始终先在测试网(testnet)上测试代码
2. **错误处理** - 始终包装API调用在try-except块中
3. **速率限制** - 注意API速率限制，使用适当延迟
4. **资源清理** - 确保正确关闭连接和取消订阅
5. **日志记录** - 启用日志以便于调试

## 测试

运行单元测试：

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
python -m pytest tests/exchange/test_binance/ -v
```

## 注意事项

1. 保护好您的API密钥，不要提交到代码仓库
2. 使用环境变量或配置文件管理敏感信息
3. 生产环境建议使用IP白名单
4. 定期轮换API密钥

## 更多信息

- [Binance API文档](https://binance-docs.github.io/apidocs/spot/en/)
- [python-binance文档](https://python-binance.readthedocs.io/)
