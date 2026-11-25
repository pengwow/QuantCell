# Worker 工作进程

## 概述

Worker 管理策略进程的完整生命周期，支持实盘（Live）、模拟盘（Demo）与纸上交易（Paper）
三种模式；回测、paper、live 共用同一条 per-bar 主回路，差异只在执行层装配。

## 主要组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `StrategyManager` / `worker_system` | `worker/strategy_manager.py` | 统一策略执行引擎（模块级单例），paper / live 泵线程 |
| `TradingNodeWorkerManager` | `worker/manager.py` | Worker 生命周期协调（启动 / 暂停 / 恢复 / 停止） |
| `TradingSystem` / `trading_system` | `worker/trading_system.py` | 交易系统枢纽（引擎 + 账户 + 风控装配） |
| `EventHandler` | `worker/event_handler.py` | 事件缓冲、日志与向前端推送 |
| `ZmqConfig` | `worker/config.py` | 独立进程 ZMQ 通信（事件拉 / 命令推 / 心跳） |
| `router` | `worker/routes.py` | Worker 管理 API |

## 交易模式

| 模式 | 说明 | 连接环境 | API 密钥 |
|------|------|----------|----------|
| `live` | 实盘交易 | 交易所正式环境 | 正式 API 密钥 |
| `demo` | 模拟盘交易 | 交易所测试网 | 测试网 API 密钥 |
| `paper` | 纸上交易 | 本地撮合 | 不需要 |

## 快速开始

```python
from worker import worker_system

worker_system.engine_status()        # 引擎状态概览（exchange / mode / risk / 策略数）
worker_system.list_strategies()      # 策略列表
worker_system.register_strategy(...)  # 注册策略
```

## 配置

**交易所密钥**（环境变量，或写入凭证库后由 `account` 子命令管理）：

```bash
# Binance 测试网
export BINANCE_TESTNET_API_KEY="..."
export BINANCE_TESTNET_API_SECRET="..."

# Binance 正式网
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."

# OKX
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."
```

**ZMQ 通信**（独立进程 IPC，默认地址见 `worker/config.py::ZmqConfig`）：

| 字段 | 默认值 | 含义 |
|------|--------|------|
| `event_pull_addr` | `tcp://127.0.0.1:5558` | 事件拉取 |
| `cmd_push_addr` | `tcp://127.0.0.1:5559` | 命令下发 |
| `heartbeat_interval` | 5s | 心跳间隔 |
| `offline_threshold` | 60s | 判定离线阈值 |

## 事件处理

```python
from worker.event_handler import create_event_handler

def on_event(event_type: str, event_data: dict):
    print(f"收到 {event_type} 事件: {event_data}")

event_handler = create_event_handler(trader=trading_system.trader, send_event_func=on_event)
event_handler.subscribe_events()
# ...
event_handler.unsubscribe_events()
```

## 故障排除

### API 密钥错误 (-2015)

- 检查环境变量或凭证库中的密钥是否正确
- 确认 API 密钥有交易权限
- 测试网必须用测试网密钥

### 余额不足 (-2019)

- 给测试网账户充值，或减小订单数量

### 连接超时

- 检查网络与代理配置，必要时加大超时

## 文件结构

```
backend/worker/
├── strategy_manager.py   # StrategyManager 单例 + paper/live 泵线程
├── manager.py            # Worker 生命周期协调
├── trading_system.py     # 交易系统枢纽
├── event_handler.py      # 事件处理器
├── config.py             # ZMQ / 运行环境配置
├── routes.py             # Worker 管理 API
└── README.md             # 本文档
```

## 参考

- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [OKX API 文档](https://www.okx.com/docs-v5/)