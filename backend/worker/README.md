# QuantCell Worker 进程管理模块

## 概述

Worker 进程管理模块提供了独立进程运行交易策略的能力，基于 ZeroMQ 实现高效的进程间通信。

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────────────┐
│                        主进程 (Main Process)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │WorkerManager│  │  DataBroker │  │      ProcessPool        │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────────┘  │
│         │                │                                       │
│         └────────────────┴──────────────────┐                    │
│                                              │                    │
│                    ┌─────────────────────────┘                    │
│                    ▼                                              │
│            ┌───────────────┐                                      │
│            │  ZMQManager   │                                      │
│            └───────┬───────┘                                      │
│                    │                                              │
│    ┌───────────────┼───────────────┐                              │
│    │               │               │                              │
│    ▼               ▼               ▼                              │
│ ┌──────┐      ┌────────┐      ┌──────────┐                       │
│ │ PUB  │      │ ROUTER │      │   PULL   │                       │
│ │(数据)│      │(控制)  │      │ (状态)   │                       │
│ └──┬───┘      └───┬────┘      └────┬─────┘                       │
└────┼──────────────┼────────────────┼──────────────────────────────┘
     │              │                │
     └──────────────┴────────────────┘
                    │
     ┌──────────────┼──────────────┐
     │              │              │
     ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Worker 进程池                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Worker 1   │  │   Worker 2   │  │   Worker N   │          │
│  │  ┌────────┐  │  │  ┌────────┐  │  │  ┌────────┐  │          │
│  │  │  SUB   │  │  │  │  SUB   │  │  │  │  SUB   │  │          │
│  │  │(接收数据)│  │  │  │(接收数据)│  │  │  │(接收数据)│  │          │
│  │  ├────────┤  │  │  ├────────┤  │  │  ├────────┤  │          │
│  │  │ DEALER │  │  │  │ DEALER │  │  │  │ DEALER │  │          │
│  │  │(接收控制)│  │  │  │(接收控制)│  │  │  │(接收控制)│  │          │
│  │  ├────────┤  │  │  ├────────┤  │  │  ├────────┤  │          │
│  │  │  PUSH  │  │  │  │  PUSH  │  │  │  │  PUSH  │  │          │
│  │  │(发送状态)│  │  │  │(发送状态)│  │  │  │(发送状态)│  │          │
│  │  └────────┘  │  │  └────────┘  │  │  └────────┘  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### ZeroMQ 通信模式

| 用途     | 模式            | 说明                 |
| ------ | ------------- | ------------------ |
| 实时数据分发 | PUB/SUB       | 广播市场数据到所有订阅 Worker |
| 控制命令   | ROUTER/DEALER | 异步双向通信             |
| 状态上报   | PUSH/PULL     | Worker 上报状态和心跳     |

## 模块结构

```
backend/worker/
├── __init__.py              # 模块入口
├── state.py                 # 状态机和状态定义
├── worker_process.py        # Worker 进程实现
├── manager.py               # Worker 管理器
├── pool.py                  # 进程池
├── supervisor.py            # 进程监控器
├── test_basic.py            # 基础测试
├── README.md                # 本文档
└── ipc/                     # 进程间通信模块
    ├── __init__.py
    ├── protocol.py          # 消息协议定义
    ├── zmq_manager.py       # ZMQ 管理器
    └── data_broker.py       # 数据代理
```

## 核心类说明

### 1. WorkerManager

中央管理器，负责管理所有 Worker 进程的生命周期。

```python
from worker import WorkerManager

manager = WorkerManager(max_workers=10)
await manager.start()

# 启动策略
worker_id = await manager.start_strategy(
    strategy_path="/path/to/strategy.py",
    config={
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "data_types": ["kline"],
        "params": {"n1": 10, "n2": 20}
    }
)

# 停止策略
await manager.stop_worker(worker_id)

# 发布市场数据
await manager.publish_market_data(
    symbol="BTC/USDT",
    data_type="kline",
    data={"open": 50000, "high": 51000, "low": 49000, "close": 50500}
)

await manager.stop()
```

### 2. WorkerProcess

在独立进程中运行策略的 Worker 类。

```python
from worker import WorkerProcess

worker = WorkerProcess(
    worker_id="worker-1",
    strategy_path="/path/to/strategy.py",
    config={"symbols": ["BTC/USDT"]},
)

worker.start()  # 启动进程
worker.join()   # 等待进程结束
```

### 3. DataBroker

管理数据订阅和分发。

```python
from worker import DataBroker
from worker.ipc import ZMQManager

zmq_manager = ZMQManager()
await zmq_manager.start()

data_broker = DataBroker(zmq_manager)

# Worker 订阅数据
data_broker.subscribe("worker-1", ["BTC/USDT", "ETH/USDT"], ["kline"])

# 发布数据
await data_broker.publish("BTC/USDT", "kline", {"close": 50000})
```

### 4. ProcessPool

进程池，预创建 Worker 进程以减少启动延迟。

```python
from worker import ProcessPool, PoolConfig

pool = ProcessPool(
    config=PoolConfig(min_size=2, max_size=10),
)
await pool.start()

# 获取 Worker
worker = await pool.acquire("/path/to/strategy.py", config={})

# 释放 Worker
await pool.release(worker.worker_id)

await pool.stop()
```

### 5. WorkerSupervisor

监控 Worker 健康状态，支持自动重启。

```python
from worker import WorkerSupervisor, RestartPolicy, HealthCheckConfig

supervisor = WorkerSupervisor(
    restart_policy=RestartPolicy(max_restarts=3),
    health_config=HealthCheckConfig(heartbeat_timeout=30),
)
await supervisor.start()

# 注册 Worker
supervisor.register_worker("worker-1", worker_status)

# 更新心跳
supervisor.update_heartbeat("worker-1")

# 检查健康状态
is_healthy = supervisor.is_healthy("worker-1")
```

## Worker 状态机

```
INITIALIZING -> INITIALIZED -> STARTING -> RUNNING <-> PAUSED
                                              |
                                              v
                                         STOPPING -> STOPPED
                                              |
                                              v
                                             ERROR <-> RECOVERING
```

### 状态说明

| 状态            | 说明      |
| ------------- | ------- |
| INITIALIZING  | 正在初始化   |
| INITIALIZED   | 初始化完成   |
| STARTING      | 正在启动    |
| RUNNING       | 正常运行    |
| PAUSED        | 已暂停     |
| STOPPING      | 正在停止    |
| STOPPED       | 已停止     |
| ERROR         | 发生错误    |
| RECOVERING    | 正在恢复    |
| RELOADING     | 正在重载配置  |
| RESTARTING    | 正在重启    |

## 消息协议

### 消息类型

```python
from worker import MessageType

# 数据消息
MessageType.MARKET_DATA      # 市场数据
MessageType.TICK_DATA        # Tick 数据
MessageType.BAR_DATA         # K线数据

# 控制消息
MessageType.START            # 启动策略
MessageType.STOP             # 停止策略
MessageType.PAUSE            # 暂停策略
MessageType.RESUME           # 恢复策略

# 状态消息
MessageType.HEARTBEAT        # 心跳
MessageType.STATUS_UPDATE    # 状态更新
MessageType.ERROR            # 错误报告
```

### 消息示例

```python
from worker import Message, MessageType

# 创建心跳消息
heartbeat = Message.create_heartbeat("worker-1", "running")

# 创建市场数据消息
market_data = Message.create_market_data(
    symbol="BTC/USDT",
    data_type="kline",
    data={"open": 50000, "close": 51000},
)

# 创建控制消息
control = Message.create_control(
    MessageType.STOP,
    "worker-1",
    {"reason": "manual_stop"}
)

# 序列化和反序列化
json_str = heartbeat.to_json()
message = Message.from_json(json_str)
```

## 测试

运行基础测试：

```bash
cd backend
python3 worker/test_basic.py
```

## 依赖

- pyzmq >= 27.1.0
- setproctitle >= 1.3.0

## 后续开发计划

1. **与 RealtimeEngine 集成** - 将 DataBroker 连接到实时数据流
2. **LiveExecutionEngine 完善** - 实现实盘交易执行
3. **策略动态加载** - 支持运行时加载和更新策略
4. **API 接口** - 提供 RESTful API 管理 Worker
5. **WebSocket 状态推送** - 实时推送 Worker 状态到前端
6. **性能优化** - 批量数据处理、共享内存优化

## 注意事项

1. Worker 进程使用 `multiprocessing.Process` 实现，确保内存隔离
2. 策略代码在 Worker 进程内部动态加载，崩溃不影响其他进程
3. 使用 ZeroMQ 进行进程间通信，延迟低、性能高
4. 进程池可以预创建 Worker，减少策略启动延迟
5. 监控器支持自动重启，但需要配置合理的重启策略避免无限重启
