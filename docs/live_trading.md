# 实盘交易技术文档

本文档详细介绍 QuantCell 项目实盘交易功能的架构设计、部署流程、配置指南和 API 使用说明。

## 目录

1. [架构设计说明](#架构设计说明)
2. [核心组件说明](#核心组件说明)
3. [部署步骤](#部署步骤)
4. [配置指南](#配置指南)
5. [API 文档](#api-文档)
6. [监控配置](#监控配置)
7. [故障排除指南](#故障排除指南)

---

## 架构设计说明

### 整体架构图

```mermaid
graph TB
    subgraph "主进程 (Main Process)"
        API[FastAPI 服务]
        WM[TradingNodeWorkerManager]
        MON[WorkerMonitor]
        DB[(数据库)]
        API --> WM
        WM --> MON
        WM --> DB
    end

    subgraph "进程间通信 (IPC)"
        ZMQ[ZeroMQ]
        PROTO[通信协议]
    end

    subgraph "Worker 进程 (Worker Process)"
        WP[TradingNodeWorkerProcess]
        TN[TradingNode]
        NEH[EventHandler]
        QS[TradingStrategyAdapter]
        WP --> TN
        TN --> QS
        WP --> NEH
    end

    subgraph "交易所连接"
        BC[Binance Client]
        WS[WebSocket]
        REST[REST API]
    end

    WM -->|启动/停止| WP
    WP -->|状态/事件| ZMQ
    ZMQ -->|控制命令| WP
    TN -->|下单/查询| BC
    BC --> WS
    BC --> REST
```

### 组件关系说明

QuantCell 的实盘交易采用**多进程架构**，主要包含以下层级：

| 层级 | 组件 | 职责 |
|------|------|------|
| **管理层** | TradingNodeWorkerManager | 管理 Worker 生命周期、资源分配 |
| **通信层** | ZeroMQ + 自定义协议 | 进程间数据交换、命令传递 |
| **执行层** | TradingNodeWorkerProcess | 独立进程中运行 TradingNode |
| **适配层** | TradingStrategyAdapter | 桥接 QuantCell 与交易引擎策略 |
| **事件层** | EventHandler | 处理交易事件并同步到主进程 |

### 数据流说明

#### 1. 行情数据流

```
交易所 WebSocket → TradingNode → Strategy.on_bar/on_tick → 策略逻辑处理
```

#### 2. 交易事件流

```
交易所 → TradingNode → EventHandler → ZeroMQ → 主进程 → 数据库/前端
```

#### 3. 控制命令流

```
API 请求 → TradingNodeWorkerManager → ZeroMQ → TradingNodeWorkerProcess → TradingNode
```

---

## 核心组件说明

### 1. TradingNodeWorkerProcess

**文件位置**: `backend/worker/worker_process.py`

**职责**: 在独立进程中运行交易引擎 TradingNode，处理策略执行和生命周期管理。

**核心方法**:

```python
class TradingNodeWorkerProcess(WorkerProcess):
    """
    实盘交易策略工作进程

    在完全隔离的 Python 进程中运行策略，
    通过进程间通信与主进程进行交互
    """

    async def _init_trading_node(self) -> Optional[TradingNode]:
        """初始化 TradingNode"""

    async def _load_strategy(self):
        """加载策略"""

    async def _handle_start(self):
        """处理启动命令"""

    async def _handle_pause(self):
        """处理暂停命令"""

    async def _handle_resume(self):
        """处理恢复命令"""

    async def _handle_stop(self):
        """处理停止命令"""
```

**使用示例**:

```python
from worker.worker_process import TradingNodeWorkerProcess

worker = TradingNodeWorkerProcess(
    worker_id="worker_001",
    strategy_path="/path/to/strategy.py",
    config={
        "trading": {
            "trader_id": "QUANTCELL-001",
            "environment": "SANDBOX",
        }
    },
)
worker.start()
```

### 2. TradingStrategyAdapter

**文件位置**: `backend/strategy/trading_adapter.py`

**职责**: 将 QuantCell 策略包装为交易引擎 Strategy，实现两个框架之间的桥接。

**核心功能**:

- 生命周期管理（`on_start`, `on_stop`）
- 数据转换（K线、Tick）
- 订单代理（`buy`, `sell`）
- 暂停/恢复控制

**使用示例**:

```python
from strategy.trading_adapter import TradingStrategyAdapter, adapt_strategy
from trading_engine.config import StrategyConfig

# 方式1: 使用便捷函数
adapter = adapt_strategy(
    strategy_path="backend/strategies/sma_cross.py",
    qc_config={
        "instrument_ids": ["BTCUSDT.BINANCE"],
        "bar_types": ["1-HOUR"],
    },
    trading_config={
        "instrument_id": InstrumentId.from_str("BTCUSDT.BINANCE"),
        "bar_type": BarType.from_str("BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL"),
    },
)

# 方式2: 手动创建
from strategy.core.strategy import StrategyBase, StrategyConfig as QCStrategyConfig

qc_strategy = MyStrategy(QCStrategyConfig(...))
adapter = TradingStrategyAdapter(
    qc_strategy=qc_strategy,
    config=StrategyConfig(...),
)
```

### 3. EventHandler

**文件位置**: `backend/worker/event_handler.py`

**职责**: 处理交易引擎产生的交易事件，转换为 QuantCell 格式并同步到主进程。

**支持的事件类型**:

| 事件类型 | 说明 | 优先级 |
|----------|------|--------|
| OrderFilled | 订单成交 | 高（立即发送） |
| OrderCanceled | 订单取消 | 中 |
| OrderRejected | 订单拒绝 | 高 |
| PositionOpened | 持仓开仓 | 中 |
| PositionChanged | 持仓变更 | 中 |
| PositionClosed | 持仓平仓 | 高 |
| AccountEvent | 账户事件 | 低 |

**事件缓冲配置**:

```python
from worker.event_handler import EventBufferConfig

config = EventBufferConfig(
    buffer_size=100,      # 缓冲队列最大大小
    flush_interval=1.0,   # 自动刷新间隔（秒）
    max_batch_size=50,    # 单次批量发送最大数量
    enable_compression=False,  # 是否启用压缩
)
```

### 4. TradingNodeWorkerManager

**文件位置**: `backend/worker/manager.py`

**职责**: 专门管理 TradingNodeWorkerProcess，提供实盘交易特定的功能。

**核心功能**:

- Worker 生命周期管理（启动、停止、重启）
- 交易所适配器配置
- TradingNode 状态获取
- 性能指标收集
- 告警和自动重启

**使用示例**:

```python
from worker.manager import TradingNodeWorkerManager

manager = TradingNodeWorkerManager(
    max_workers=10,
    comm_host="127.0.0.1",
    data_port=5555,
    control_port=5556,
    status_port=5557,
    enable_monitoring=True,
)

# 启动管理器
await manager.start()

# 启动 Worker
worker_id = await manager.start_trading_worker(
    strategy_path="backend/strategies/my_strategy.py",
    config={
        "symbols": ["BTCUSDT"],
        "trading": {...}
    },
)

# 获取 Worker 状态
status = manager.get_trading_worker_status(worker_id)

# 停止 Worker
await manager.stop_trading_worker(worker_id)
```

---

## 部署步骤

### 1. 环境依赖说明

#### Python 版本要求

| 要求项 | 版本 | 说明 |
|--------|------|------|
| Python | >= 3.12 | 项目最低要求 |
| 推荐版本 | 3.12.x | 经过完整测试 |

检查 Python 版本:

```bash
python --version
# 或
python3 --version
```

#### 交易引擎安装

项目使用 `uv` 作为包管理工具，依赖已在 `pyproject.toml` 中声明:

```toml
# backend/pyproject.toml
dependencies = [
    "nautilus_trader>=1.222.0",
    # ... 其他依赖
]
```

安装步骤:

```bash
cd backend

# 使用 uv 安装依赖
uv sync

# 验证安装
uv run python -c "import trading_engine; print(trading_engine.__version__)"
```

#### 其他依赖

| 依赖包 | 用途 | 版本 |
|--------|------|------|
| pyzmq | 进程间通信 | >=27.1.0 |
| psutil | 系统监控 | >=7.1.3 |
| uvicorn | ASGI 服务器 | >=0.38.0 |
| fastapi | Web 框架 | >=0.121.3 |
| aiohttp | 异步 HTTP | >=3.13.2 |
| pandas | 数据处理 | >=2.3.3 |
| torch | 深度学习 | >=2.9.1 |

### 2. 配置准备

#### 2.1 环境变量配置

创建 `.env` 文件:

```bash
# 后端服务配置
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info

# 数据库配置
DATABASE_URL=postgresql://user:password@localhost:5432/quantcell

# Redis 配置（如使用）
REDIS_URL=redis://localhost:6379/0

# Binance API 配置（测试网）
BINANCE_TESTNET_API_KEY=your_testnet_api_key
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret

# Binance API 配置（生产环境）
BINANCE_API_KEY=your_live_api_key
BINANCE_API_SECRET=your_live_api_secret

# 交易引擎配置
TRADING_ENGINE_ID=QUANTCELL-001
TRADING_ENVIRONMENT=SANDBOX

# Worker 通信配置
WORKER_COMM_HOST=127.0.0.1
WORKER_DATA_PORT=5555
WORKER_CONTROL_PORT=5556
WORKER_STATUS_PORT=5557
```

#### 2.2 交易引擎配置文件

创建 `config/trading.yaml`:

```yaml
# 交易引擎全局配置
trader_id: "QUANTCELL-001"
environment: "SANDBOX"  # 或 "LIVE"

# 数据引擎配置
data_engine:
  time_bars_enabled: true
  time_bars_interval: 60
  time_bars_timestamp_on_close: true

# 风险引擎配置
risk_engine:
  max_order_rate: [100, 60]  # 60秒内最多100个订单
  max_notional_per_order:
    BTCUSDT.BINANCE: 100000.0
    ETHUSDT.BINANCE: 50000.0

# 执行引擎配置
exec_engine:
  reconciliation: true
  reconciliation_lookback_mins: 1440

# 数据客户端配置
data_clients:
  binance:
    api_key: ${BINANCE_TESTNET_API_KEY}
    api_secret: ${BINANCE_TESTNET_API_SECRET}
    testnet: true
    use_usdt_margin: true

# 执行客户端配置
exec_clients:
  binance:
    api_key: ${BINANCE_TESTNET_API_KEY}
    api_secret: ${BINANCE_TESTNET_API_SECRET}
    testnet: true
    use_usdt_margin: true
```

#### 2.3 策略目录准备

```bash
# 创建策略目录
mkdir -p backend/strategies

# 确保策略文件存在
ls backend/strategies/
# 输出示例:
# sma_cross.py
# bollinger_bands.py
# custom_strategy.py
```

### 3. 启动 Worker

#### 3.1 启动后端服务

```bash
cd backend

# 开发模式启动
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 生产模式启动
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 3.2 通过 API 启动 Worker

```python
import asyncio
import httpx

async def start_worker():
    async with httpx.AsyncClient() as client:
        # 启动 Worker
        response = await client.post(
            "http://localhost:8000/api/workers/trading/start",
            json={
                "strategy_path": "backend/strategies/sma_cross.py",
                "config": {
                    "symbols": ["BTCUSDT"],
                    "bar_type": "1-HOUR",
                    "trading": {
                        "trader_id": "QUANTCELL-001",
                        "environment": "SANDBOX",
                    }
                }
            }
        )
        result = response.json()
        print(f"Worker ID: {result['worker_id']}")
        return result['worker_id']

asyncio.run(start_worker())
```

#### 3.3 编程方式启动 Worker

```python
import asyncio
from worker.manager import TradingNodeWorkerManager
from worker.config import build_binance_config

async def main():
    # 创建管理器
    manager = TradingNodeWorkerManager(
        max_workers=5,
        enable_monitoring=True,
    )

    # 启动管理器
    await manager.start()

    # 构建交易所配置
    binance_config = build_binance_config(
        api_key="your_api_key",
        api_secret="your_api_secret",
        testnet=True,
    )

    # 启动 Worker
    worker_id = await manager.start_trading_worker(
        strategy_path="backend/strategies/sma_cross.py",
        config={
            "symbols": ["BTCUSDT"],
            "trading": {
                "trader_id": "QUANTCELL-001",
                "environment": "SANDBOX",
                "data_clients": {"binance": binance_config},
                "exec_clients": {"binance": binance_config},
            },
        },
    )

    print(f"Worker 启动成功: {worker_id}")

    # 保持运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await manager.stop_trading_worker(worker_id)
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 配置指南

### TradingNodeConfig 配置

**文件位置**: `backend/worker/config.py`

```python
from worker.config import build_trading_config

config = build_trading_config({
    # 交易者ID，格式为 "NAME-ID"
    "trader_id": "QUANTCELL-001",

    # 运行环境: LIVE 或 SANDBOX
    "environment": "SANDBOX",

    # 数据引擎配置
    "data_engine": {
        "time_bars_enabled": True,
        "time_bars_interval": 60,
        "time_bars_timestamp_on_close": True,
    },

    # 风险引擎配置
    "risk_engine": {
        "max_order_rate": (100, 60),  # 60秒内最多100个订单
        "max_notional_per_order": {
            "BTCUSDT.BINANCE": 100000.0,
        },
    },

    # 执行引擎配置
    "exec_engine": {
        "reconciliation": True,
        "reconciliation_lookback_mins": 1440,
    },

    # 数据客户端配置
    "data_clients": {
        "binance": {...}
    },

    # 执行客户端配置
    "exec_clients": {
        "binance": {...}
    },
})
```

### Binance 配置

#### 测试网配置

```python
from worker.config import build_binance_config

binance_config = build_binance_config(
    api_key="your_testnet_api_key",
    api_secret="your_testnet_api_secret",
    testnet=True,
    use_usdt_margin=True,  # USDT 本位合约
)
```

#### 生产环境配置

```python
from worker.config import build_binance_live_config

binance_config = build_binance_live_config(
    api_key="your_live_api_key",
    api_secret="your_live_api_secret",
    use_usdt_margin=True,
)
```

#### 配置参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| api_key | str | 必填 | Binance API 密钥 |
| api_secret | str | 必填 | Binance API 密钥 |
| testnet | bool | True | 是否使用测试网 |
| use_usdt_margin | bool | True | 是否使用 USDT 本位合约 |
| base_url_http | str | None | 自定义 HTTP API URL |
| base_url_ws | str | None | 自定义 WebSocket URL |

### 风险引擎配置

```python
from trading_engine.live.config import LiveRiskEngineConfig

risk_config = LiveRiskEngineConfig(
    # 订单频率限制: (最大订单数, 时间窗口秒数)
    max_order_rate=(100, 60),

    # 单笔订单最大名义价值
    max_notional_per_order={
        "BTCUSDT.BINANCE": 100000.0,
        "ETHUSDT.BINANCE": 50000.0,
    },
)
```

---

## API 文档

### 主要类和方法

#### TradingNodeWorkerManager

```python
class TradingNodeWorkerManager(WorkerManager):
    """实盘交易 Worker 管理器"""

    def __init__(
        self,
        max_workers: int = 10,
        comm_host: str = "127.0.0.1",
        data_port: int = 5555,
        control_port: int = 5556,
        status_port: int = 5557,
        enable_monitoring: bool = True,
    )

    async def start(self) -> bool
    """启动管理器"""

    async def stop(self) -> bool
    """停止管理器"""

    async def start_trading_worker(
        self,
        strategy_path: str,
        config: Dict[str, Any],
        worker_id: Optional[str] = None,
        exchange_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]
    """启动交易 Worker"""

    async def stop_trading_worker(
        self,
        worker_id: str,
        timeout: float = 30.0,
    ) -> bool
    """停止交易 Worker"""

    def get_trading_worker_status(
        self,
        worker_id: str,
    ) -> Optional[Dict[str, Any]]
    """获取 Worker 状态"""

    def set_trading_config(self, config: Dict[str, Any]) -> None
    """设置交易引擎全局配置"""

    def register_exchange_adapter(
        self,
        exchange_name: str,
        adapter_config: Dict[str, Any],
    ) -> None
    """注册交易所适配器"""
```

#### TradingStrategyAdapter

```python
class TradingStrategyAdapter(Strategy):
    """QuantCell 策略适配器"""

    def __init__(
        self,
        qc_strategy: QCStrategyBase,
        config: StrategyConfig,
    ) -> None

    def on_start(self) -> None
    """策略启动时调用"""

    def on_stop(self) -> None
    """策略停止时调用"""

    def on_bar(self, bar: Bar) -> None
    """收到 K 线数据时调用"""

    def on_tick(self, tick: Union[QuoteTick, TradeTick]) -> None
    """收到 Tick 数据时调用"""

    def pause(self) -> None
    """暂停策略执行"""

    def resume(self) -> None
    """恢复策略执行"""

    def buy(
        self,
        instrument_id: QCInstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None
    """买入下单"""

    def sell(
        self,
        instrument_id: QCInstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None
    """卖出下单"""

    def get_stats(self) -> Dict[str, Any]
    """获取适配器统计信息"""
```

#### EventHandler

```python
class EventHandler(Actor):
    """交易事件处理器"""

    def __init__(
        self,
        worker_id: str,
        comm_client: Any,
        buffer_config: Optional[EventBufferConfig] = None,
    )

    def on_start(self) -> None
    """Actor 启动时调用"""

    def on_stop(self) -> None
    """Actor 停止时调用"""

    def on_order_event(self, event: OrderEvent) -> None
    """处理订单状态变更事件"""

    def on_fill_event(self, event: OrderFilled) -> None
    """处理成交事件"""

    def on_position_event(self, event: PositionEvent) -> None
    """处理持仓变更事件"""

    async def send_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> bool
    """发送单个事件到主进程"""

    async def batch_send_events(
        self,
        events: List[Dict[str, Any]],
    ) -> bool
    """批量发送事件到主进程"""

    def get_event_stats(self) -> Dict[str, int]
    """获取事件统计信息"""
```

### 数据转换函数

```python
# K线数据转换
from strategy.trading_adapter import convert_bar_to_qc

qc_bar = convert_bar_to_qc(trading_bar)

# Tick 数据转换
from strategy.trading_adapter import convert_tick_to_qc

qc_tick = convert_tick_to_qc(trading_tick)

# 订单转换
from strategy.trading_adapter import convert_order_to_trading

trading_order = convert_order_to_trading(qc_order)

# 持仓转换
from strategy.trading_adapter import convert_position_to_qc

qc_position = convert_position_to_qc(trading_position)
```

### 使用示例

#### 完整启动流程

```python
import asyncio
from worker.manager import TradingNodeWorkerManager
from worker.config import build_binance_config, build_trading_config

async def main():
    # 1. 创建管理器
    manager = TradingNodeWorkerManager(
        max_workers=5,
        enable_monitoring=True,
    )

    # 2. 启动管理器
    await manager.start()

    # 3. 构建交易所配置
    binance_config = build_binance_config(
        api_key="your_api_key",
        api_secret="your_api_secret",
        testnet=True,
    )

    # 4. 启动 Worker
    worker_id = await manager.start_trading_worker(
        strategy_path="backend/strategies/sma_cross.py",
        config={
            "symbols": ["BTCUSDT"],
            "trading": {
                "trader_id": "QUANTCELL-001",
                "environment": "SANDBOX",
                "data_clients": {"binance": binance_config},
                "exec_clients": {"binance": binance_config},
            },
        },
    )

    print(f"Worker 启动成功: {worker_id}")

    # 5. 获取状态
    status = manager.get_trading_worker_status(worker_id)
    print(f"Worker 状态: {status}")

    # 6. 运行一段时间后停止
    await asyncio.sleep(60)

    await manager.stop_trading_worker(worker_id)
    await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 策略适配示例

```python
from strategy.core.strategy import StrategyBase, StrategyConfig
from strategy.trading_adapter import TradingStrategyAdapter
from trading_engine.config import StrategyConfig as TradingStrategyConfig

class MyQuantCellStrategy(StrategyBase):
    """自定义 QuantCell 策略"""

    def on_start(self):
        print("策略启动")

    def on_stop(self):
        print("策略停止")

    def on_bar(self, bar):
        print(f"收到 K 线: {bar.close}")
        # 策略逻辑...

# 创建 QuantCell 策略
qc_config = StrategyConfig(
    instrument_ids=["BTCUSDT.BINANCE"],
    bar_types=["1-HOUR"],
)
qc_strategy = MyQuantCellStrategy(qc_config)

# 创建适配器
trading_config = TradingStrategyConfig(
    instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    bar_type=BarType.from_str("BTCUSDT.BINANCE-1-HOUR-LAST-EXTERNAL"),
)
adapter = TradingStrategyAdapter(qc_strategy, trading_config)

# 添加到 TradingNode
trading_node.add_strategy(adapter)
```

---

## 监控配置

### 性能指标监控

TradingNodeWorkerManager 内置性能监控，自动收集以下指标:

| 指标类别 | 指标名称 | 说明 |
|----------|----------|------|
| CPU | cpu_percent | CPU 使用率 |
| 内存 | memory_percent | 内存使用率 |
| 内存 | memory_rss_mb | 实际使用内存 |
| 延迟 | avg_latency_ms | 平均延迟 |
| 延迟 | p95_latency_ms | P95 延迟 |
| 吞吐量 | events_per_second | 每秒事件数 |
| 交易 | orders_per_second | 每秒订单数 |
| 错误 | error_rate | 错误率 |
| 交易 | active_strategies | 活跃策略数 |
| 交易 | open_positions | 持仓数量 |

获取指标示例:

```python
# 获取 Worker 指标
metrics = await manager.monitor.collect_metrics(worker_id)
print(f"CPU: {metrics.cpu_percent}%")
print(f"内存: {metrics.memory_percent}%")
print(f"延迟: {metrics.avg_latency_ms}ms")
```

### 告警配置

```python
from worker.manager import (
    AlertConfig,
    AlertRule,
    AlertSeverity,
    AlertRuleType,
)

# 创建告警配置
config = AlertConfig(
    worker_id="worker_001",
    enabled=True,
    auto_restart_enabled=True,
    max_restart_attempts=3,
    restart_cooldown=60,
    webhook_url="https://hooks.slack.com/services/...",
    email_recipients=["admin@example.com"],
)

# 添加告警规则
config.add_rule(AlertRule(
    rule_type=AlertRuleType.ERROR_RATE,
    name="high_error_rate",
    threshold=0.1,  # 错误率超过 10%
    duration=60,
    severity=AlertSeverity.ERROR,
))

config.add_rule(AlertRule(
    rule_type=AlertRuleType.MEMORY_USAGE,
    name="high_memory_usage",
    threshold=80.0,  # 内存使用率超过 80%
    severity=AlertSeverity.WARNING,
))

config.add_rule(AlertRule(
    rule_type=AlertRuleType.CPU_USAGE,
    name="high_cpu_usage",
    threshold=90.0,  # CPU 使用率超过 90%
    severity=AlertSeverity.WARNING,
))

config.add_rule(AlertRule(
    rule_type=AlertRuleType.HEARTBEAT_TIMEOUT,
    name="heartbeat_timeout",
    threshold=60.0,  # 心跳超时 60 秒
    severity=AlertSeverity.CRITICAL,
))

# 设置告警配置
manager.monitor.set_alert_config("worker_001", config)
```

### 日志配置

项目使用统一的日志系统，配置位于 `backend/utils/logger.py`:

```python
# 日志级别设置
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# 日志输出配置
LOG_HANDLERS = {
    "console": True,      # 控制台输出
    "file": True,         # 文件输出
    "rotation": "500 MB", # 日志轮转大小
    "retention": "30 days", # 日志保留时间
}
```

日志文件位置:

```
backend/logs/
├── application.log      # 应用日志
├── trade.log           # 交易日志
├── strategy.log        # 策略日志
├── system.log          # 系统日志
└── error.log           # 错误日志
```

查看实时日志:

```bash
# 查看所有日志
tail -f backend/logs/*.log

# 查看特定 Worker 日志
tail -f backend/logs/worker_001.log

# 查看错误日志
tail -f backend/logs/error.log
```

---

## 故障排除指南

### 常见问题

#### 1. Worker 启动失败

**症状**: Worker 启动后立即退出或无法启动

**排查步骤**:

```bash
# 1. 检查日志
tail -n 100 backend/logs/error.log

# 2. 检查 Python 版本
python --version  # 应 >= 3.12

# 3. 检查依赖安装
uv run python -c "import trading_engine; print(trading_engine.__version__)"

# 4. 检查策略文件是否存在
ls -la backend/strategies/your_strategy.py

# 5. 检查 API 密钥配置
echo $BINANCE_TESTNET_API_KEY
```

**常见原因**:

| 原因 | 解决方案 |
|------|----------|
| Python 版本过低 | 升级到 Python 3.12+ |
| 依赖未安装 | 运行 `uv sync` |
| 策略文件不存在 | 检查文件路径 |
| API 密钥无效 | 检查密钥配置 |
| 端口被占用 | 更换通信端口 |

#### 2. 连接交易所失败

**症状**: 无法连接 Binance 或数据无法接收

**排查步骤**:

```python
# 测试网络连接
import asyncio
import aiohttp

async def test_connection():
    # 测试 REST API
    async with aiohttp.ClientSession() as session:
        async with session.get("https://testnet.binancefuture.com/fapi/v1/ping") as resp:
            print(f"REST API 状态: {resp.status}")

    # 测试 WebSocket
    # ...

asyncio.run(test_connection())
```

**解决方案**:

```python
# 检查代理设置
import os
os.environ["HTTP_PROXY"] = "http://proxy:port"
os.environ["HTTPS_PROXY"] = "http://proxy:port"

# 检查防火墙设置
# 确保端口 443 (HTTPS) 和 WebSocket 端口开放
```

#### 3. 内存占用过高

**症状**: Worker 进程内存持续增长

**排查步骤**:

```python
# 监控内存使用
import psutil

process = psutil.Process(worker_pid)
print(f"内存使用: {process.memory_info().rss / 1024 / 1024:.2f} MB")
print(f"内存百分比: {process.memory_percent():.2f}%")
```

**解决方案**:

```python
# 1. 调整事件缓冲配置
from worker.event_handler import EventBufferConfig

config = EventBufferConfig(
    buffer_size=50,      # 减小缓冲区
    flush_interval=0.5,  # 加快刷新频率
)

# 2. 设置内存告警
config.add_rule(AlertRule(
    rule_type=AlertRuleType.MEMORY_USAGE,
    name="memory_warning",
    threshold=70.0,
    severity=AlertSeverity.WARNING,
))

# 3. 启用自动重启
config.auto_restart_enabled = True
config.max_restart_attempts = 3
```

#### 4. 订单执行失败

**症状**: 下单被拒绝或执行异常

**排查步骤**:

```python
# 检查账户余额
# 检查订单参数
order = {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "LIMIT",
    "quantity": 0.001,
    "price": 50000,
}

# 检查最小下单量
# BTCUSDT 最小下单量为 0.001
```

**解决方案**:

```python
# 1. 检查风险引擎配置
risk_config = LiveRiskEngineConfig(
    max_order_rate=(100, 60),
    max_notional_per_order={
        "BTCUSDT.BINANCE": 100000.0,
    },
)

# 2. 检查账户权限
# 确保 API Key 有交易权限
# 确保账户有足够保证金
```

### 调试方法

#### 1. 启用调试日志

```python
# 在配置中设置日志级别
import logging

logging.basicConfig(level=logging.DEBUG)

# 或在环境变量中设置
import os
os.environ["LOG_LEVEL"] = "DEBUG"
```

#### 2. 使用调试模式启动 Worker

```python
# 创建测试配置
test_config = {
    "trading": {
        "trader_id": "QUANTCELL-TEST",
        "environment": "SANDBOX",
        "log_level": "DEBUG",
    }
}

# 启动测试 Worker
worker_id = await manager.start_trading_worker(
    strategy_path="backend/strategies/test_strategy.py",
    config=test_config,
)
```

#### 3. 本地调试策略

```python
# 使用回测引擎调试
from backtest.engines.trading_engine import TradingBacktestEngine

engine = TradingBacktestEngine()
engine.run(
    strategy_path="backend/strategies/my_strategy.py",
    start_date="2024-01-01",
    end_date="2024-01-31",
    symbols=["BTCUSDT"],
)
```

### 错误处理

#### 常见错误代码

| 错误代码 | 说明 | 解决方案 |
|----------|------|----------|
| WORKER_INIT_ERROR | Worker 初始化失败 | 检查配置和依赖 |
| TRADING_NODE_ERROR | TradingNode 错误 | 检查交易引擎配置 |
| STRATEGY_LOAD_ERROR | 策略加载失败 | 检查策略文件 |
| CONNECTION_ERROR | 连接错误 | 检查网络和 API 密钥 |
| ORDER_ERROR | 订单错误 | 检查订单参数和余额 |
| RISK_ERROR | 风险限制 | 调整风险引擎配置 |

#### 错误处理示例

```python
import asyncio
from worker.manager import TradingNodeWorkerManager

async def safe_start_worker(manager, strategy_path, config):
    """安全启动 Worker，带错误处理"""
    try:
        worker_id = await manager.start_trading_worker(
            strategy_path=strategy_path,
            config=config,
        )

        if worker_id is None:
            print("Worker 启动失败")
            return None

        # 等待 Worker 就绪
        for _ in range(30):  # 最多等待 30 秒
            await asyncio.sleep(1)
            status = manager.get_trading_worker_status(worker_id)
            if status and status.get("process_alive"):
                print(f"Worker {worker_id} 启动成功")
                return worker_id

        print("Worker 启动超时")
        await manager.stop_trading_worker(worker_id)
        return None

    except Exception as e:
        print(f"启动异常: {e}")
        return None

# 使用示例
manager = TradingNodeWorkerManager()
await manager.start()

worker_id = await safe_start_worker(
    manager,
    "backend/strategies/sma_cross.py",
    config={...},
)
```

#### 优雅关闭

```python
async def graceful_shutdown(manager, worker_id, timeout=30):
    """优雅关闭 Worker"""
    try:
        # 发送停止命令
        await manager.stop_trading_worker(worker_id, timeout=timeout)
        print(f"Worker {worker_id} 已停止")

    except asyncio.TimeoutError:
        print(f"Worker {worker_id} 停止超时，强制终止")
        # 强制终止
        worker = manager.get_worker(worker_id)
        if worker and worker.is_alive():
            worker.terminate()
            worker.join(timeout=5)

    except Exception as e:
        print(f"关闭异常: {e}")
```

---

## 生产环境部署检查清单

### 部署前检查

- [ ] Python 版本 >= 3.12
- [ ] 所有依赖已安装 (`uv sync`)
- [ ] 数据库连接正常
- [ ] API 密钥有效且有足够权限
- [ ] 防火墙端口已开放
- [ ] 日志目录已创建且有写入权限
- [ ] 策略文件已验证

### 部署时检查

- [ ] 使用生产环境配置
- [ ] 启用监控和告警
- [ ] 配置自动重启
- [ ] 设置资源限制 (CPU/内存)
- [ ] 配置日志轮转

### 部署后检查

- [ ] Worker 启动成功
- [ ] 数据连接正常
- [ ] 订单可以正常提交
- [ ] 事件可以正常接收
- [ ] 监控指标正常
- [ ] 告警可以正常触发

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `backend/worker/worker_process.py` | Worker 进程实现 |
| `backend/worker/manager.py` | Worker 管理器 |
| `backend/worker/event_handler.py` | 事件处理器 |
| `backend/worker/config.py` | 配置构建器 |
| `backend/strategy/trading_adapter.py` | 策略适配器 |
| `backend/exchange/binance/live_adapter.py` | Binance 适配器 |
| `backend/pyproject.toml` | 依赖配置 |
