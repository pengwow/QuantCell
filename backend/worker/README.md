# Worker Nautilus 集成增强

## 概述

本模块增强了 Worker 进程，使其能够运行完整的 NautilusTrader，支持实盘交易、模拟盘交易和纸上交易三种模式。

## 主要功能

- **多交易所支持**：Binance (现货/合约)、OKX
- **三种交易模式**：实盘 (Live)、模拟盘 (Demo)、纸上交易 (Paper)
- **余额检查**：自动检查账户余额，支持自动调整订单数量
- **事件同步**：将 Nautilus 事件同步到主进程
- **完整生命周期**：启动、暂停、恢复、停止

## 快速开始

### 1. 使用 Worker 工厂创建 Nautilus Worker

```python
from backend.worker.factory import create_nautilus_worker

# 创建 Binance 模拟盘 Worker
worker = create_nautilus_worker(
    worker_id="test-001",
    strategy_path="strategies/sma_cross_nautilus.py",
    config={},
    exchange="binance",
    account_type="spot",  # spot, usdt_futures, coin_futures
    trading_mode="demo",  # live, demo, paper
)

# 启动 Worker
await worker.start()
```

### 2. 配置说明

#### 环境变量配置

**Binance:**
```bash
# 测试网
export BINANCE_TESTNET_API_KEY="your_testnet_api_key"
export BINANCE_TESTNET_API_SECRET="your_testnet_api_secret"

# 正式网
export BINANCE_API_KEY="your_live_api_key"
export BINANCE_API_SECRET="your_live_api_secret"
```

**OKX:**
```bash
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
export OKX_PASSPHRASE="your_passphrase"
```

#### Worker 配置

```python
config = {
    "nautilus": {
        "exchange": "binance",  # binance, okx
        "account_type": "spot",  # spot, usdt_futures, coin_futures
        "trading_mode": "demo",  # live, demo, paper
        "proxy_url": "http://127.0.0.1:7890",  # 可选
        "api_key": "your_api_key",  # 可选，优先于环境变量
        "api_secret": "your_api_secret",  # 可选
        "api_passphrase": "your_passphrase",  # OKX 需要
        "log_level": "INFO",
    },
    "balance_check": {
        "enabled": True,
        "auto_adjust": False,  # 余额不足时自动调整订单数量
        "min_buffer": 1.1,  # 10% 缓冲
    }
}
```

### 3. 交易模式说明

| 模式 | 说明 | 连接环境 | API 密钥 |
|------|------|----------|----------|
| `live` | 实盘交易 | 交易所正式环境 | 正式 API 密钥 |
| `demo` | 模拟盘交易 | 交易所测试网 | 测试网 API 密钥 |
| `paper` | 纸上交易 | 本地回测引擎 | 不需要 |

### 4. 余额检查

```python
from backend.worker.worker_process import BalanceChecker

# 创建余额检查器
checker = BalanceChecker(
    trader=trading_node.trader,
    min_balance_buffer=1.1,  # 10% 缓冲
    auto_adjust=True,  # 自动调整订单数量
)

# 检查余额
is_sufficient, message, adjusted_qty = checker.check_balance(
    instrument_id=instrument_id,
    order_qty=Decimal("0.01"),
)

if not is_sufficient:
    print(f"余额不足: {message}")
else:
    print(f"余额充足: {message}")
```

### 5. 事件处理

```python
from backend.worker.event_handler import create_event_handler

# 创建事件处理器
def on_event(event_type: str, event_data: dict):
    print(f"收到 {event_type} 事件: {event_data}")

event_handler = create_event_handler(
    trader=trading_node.trader,
    send_event_func=on_event,
)

# 订阅事件
event_handler.subscribe_events()

# 取消订阅
event_handler.unsubscribe_events()
```

## 故障排除

### API 密钥错误 (-2015)

**原因：** API 密钥无效或权限不足

**解决：**
1. 检查环境变量是否正确设置
2. 确认 API 密钥有交易权限
3. 对于测试网，使用测试网 API 密钥

### 余额不足 (-2019)

**原因：** 账户余额不足以支持下单

**解决：**
1. 给测试网账户充值
2. 减小订单数量
3. 启用自动调整功能

### 连接超时

**原因：** 网络问题或代理设置错误

**解决：**
1. 检查网络连接
2. 配置代理服务器
3. 增加超时时间

## 文件结构

```
backend/worker/
├── config.py                   # Nautilus 配置构建器
├── balance_checker.py          # 余额检查模块
├── event_handler.py            # 事件处理器
├── factory.py                  # Worker 工厂
├── worker_process.py           # Worker 进程实现
└── README.md                   # 本文档
```

## 参考

- [NautilusTrader 文档](https://nautilustrader.io/docs/)
- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [OKX API 文档](https://www.okx.com/docs-v5/)
