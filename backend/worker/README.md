# Worker 工作进程

## 概述

Worker 管理策略的完整生命周期，支持实盘（Live）、模拟盘（Demo）与纸上交易（Paper）
三种模式；回测、paper、live 共用同一条 per-bar 主回路，差异只在执行层装配。

每个 Worker 由 StrategyManager 的驱动线程在主进程内运行（进程内直调模型，
历史上存在过 ZMQ 多进程 daemon 编排层，已随统一内核方案移除）。

## 主要组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `StrategyManager` / `worker_system` | `worker/strategy_manager.py` | 统一策略执行引擎（模块级单例），paper / live 泵线程 |
| `TradingNodeWorkerManager` | `worker/manager.py` | Worker 生命周期协调（启动 / 暂停 / 恢复 / 停止） |
| `WorkerCoreService` | `worker/core_service.py` | Worker 启停编排 + 状态收口（`worker_state_manager`，DB 事实源） |
| `router` | `worker/routes.py` | Worker 管理 API（带 RBAC + 归属校验） |

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

## 状态机

Worker 运行状态统一由 `worker/worker_state.py` 管理：DB 是事实源，
内存缓存 30s 陈旧自愈；启停后台任务完成后向状态机补 transition，
非法转换（如 stopped → running 直达）会被拒绝。

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
├── core_service.py       # Worker 启停编排 + 状态收口
├── worker_state.py       # 状态机（DB 事实源 + 缓存自愈）
├── config.py             # 运行环境配置
├── routes.py             # Worker 管理 API
└── README.md             # 本文档
```

## 参考

- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [OKX API 文档](https://www.okx.com/docs-v5/)
