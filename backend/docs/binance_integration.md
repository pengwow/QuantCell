# Binance交易所集成文档

本文档介绍QuantCell项目中Binance交易所连接模块的使用方法。

## 功能概述

Binance连接模块提供以下功能：

1. **REST API客户端** - 账户管理、市场行情、订单操作
2. **WebSocket实时数据** - K线、深度、交易数据实时推送（`BinanceWebSocketClient`）

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

存活的 WebSocket 客户端是 `exchange.binance.websocket_client.BinanceWebSocketClient`，
通过 `subscribe(channels)` 订阅频道、`add_message_callback(callback)` 注册回调：

```python
import asyncio
from exchange.binance.websocket_client import BinanceWebSocketClient
from exchange.binance.config import BinanceConfig

async def main():
    config = BinanceConfig(testnet=True)
    client = BinanceWebSocketClient(config)

    # 注册消息回调，接收所有已订阅频道的推送
    def on_message(data):
        print(f"Message: {data.get('channel')} -> {data}")

    client.add_message_callback(on_message)

    # 连接
    await client.connect()

    # 订阅数据（频道格式: "<symbol>@<stream>"）
    await client.subscribe([
        "BTCUSDT@kline_1m",
        "BTCUSDT@trade",
    ])

    # 运行一段时间
    await asyncio.sleep(60)

    # 断开连接
    await client.disconnect()

asyncio.run(main())
```

### 4. 模拟盘交易

> 说明：模拟盘交易模块及其账户实现已归档，当前无存活的模拟盘实现。
> 需要无真实资金的回测请使用 `backtest/backtest_loop.py` 的 `BacktestLoop`。

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

### BinanceWebSocketClient

#### 连接与订阅

- `connect()` - 建立 WebSocket 连接
- `disconnect()` - 断开连接
- `subscribe(channels)` - 订阅频道列表，格式如 `["BTCUSDT@kline_1m", "ETHUSDT@depth"]`
- `unsubscribe(channels)` - 取消订阅
- `is_connected()` - 检查连接状态
- `get_connection_status()` - 获取连接状态信息

#### 回调注册

- `add_message_callback(callback)` - 注册消息回调
- `remove_message_callback(callback)` - 注销消息回调

> 注意：`subscribe` 的频道名不区分订阅类型前缀，K线/深度/交易/ticker 由频道名中的
> stream 类型（`kline_1m`/`depth`/`trade`/`ticker`）决定。

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
