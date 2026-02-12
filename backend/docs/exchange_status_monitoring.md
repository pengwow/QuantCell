# 交易所连接状态监测功能文档

本文档介绍QuantCell项目中交易所连接状态监测功能的使用方法。

## 功能概述

交易所连接状态监测功能提供了以下能力：

1. **实时状态监测** - 监测交易所连接状态（已连接、断开、错误、重连中）
2. **自动状态更新** - 在连接、断开、错误时自动更新状态
3. **WebSocket推送** - 实时推送状态到前端系统
4. **异常处理** - 捕获并记录连接错误信息
5. **多交易所支持** - 支持同时监测多个交易所

## 核心组件

### ExchangeStatus (枚举)

定义交易所连接状态：

- `DISCONNECTED` - 已断开
- `CONNECTING` - 连接中
- `CONNECTED` - 已连接
- `ERROR` - 错误
- `RECONNECTING` - 重连中

### ExchangeConnectionInfo (数据类)

存储交易所连接信息：

```python
@dataclass
class ExchangeConnectionInfo:
    exchange_name: str          # 交易所名称
    status: ExchangeStatus      # 连接状态
    last_connected_at: datetime # 最后连接时间
    last_disconnected_at: datetime  # 最后断开时间
    last_error: str             # 最后错误信息
    last_error_at: datetime     # 最后错误时间
    reconnect_count: int        # 重连次数
    latency_ms: float           # 延迟（毫秒）
    message_count: int          # 消息计数
```

### ExchangeConnectionMonitor (监测器)

核心监测类，提供以下方法：

- `register_exchange(exchange_name)` - 注册交易所
- `update_status(exchange_name, status, error, latency_ms)` - 更新状态
- `get_connection_info(exchange_name)` - 获取连接信息
- `get_all_connections()` - 获取所有连接
- `get_connections_summary()` - 获取连接摘要

### SystemService 扩展方法

- `register_exchange(exchange_name)` - 注册交易所
- `update_exchange_status(exchange_name, status, error, latency_ms)` - 更新状态
- `get_exchange_connections_status()` - 获取连接状态
- `start_exchange_status_push()` - 启动状态推送
- `stop_exchange_status_push()` - 停止状态推送

## 使用示例

### 基本使用

```python
from collector.services.system_service import SystemService

# 创建系统服务
service = SystemService()

# 注册交易所
await service.register_exchange('binance')

# 更新连接状态
await service.update_exchange_status('binance', 'connected')

# 更新为错误状态
await service.update_exchange_status(
    'binance', 
    'error', 
    error='Connection timeout'
)

# 获取连接状态
status = service.get_exchange_connections_status()
print(status)
```

### 在Binance客户端中集成

```python
from exchange.binance import BinanceClient, BinanceConfig
from collector.services.system_service import SystemService

class MonitoredBinanceClient:
    def __init__(self, system_service: SystemService):
        self.system_service = system_service
        self.client = None
        
    async def connect(self):
        # 注册交易所
        await self.system_service.register_exchange('binance')
        
        # 更新状态为连接中
        await self.system_service.update_exchange_status(
            'binance', 'connecting'
        )
        
        try:
            # 创建客户端并连接
            self.client = BinanceClient(BinanceConfig())
            connected = await self.client.connect_async()
            
            if connected:
                # 更新为已连接
                await self.system_service.update_exchange_status(
                    'binance', 'connected'
                )
            else:
                # 更新为错误
                await self.system_service.update_exchange_status(
                    'binance', 'error', error='Connection failed'
                )
                
        except Exception as e:
            # 更新为错误
            await self.system_service.update_exchange_status(
                'binance', 'error', error=str(e)
            )
            raise
```

### 启动状态推送

```python
# 启动交易所状态推送（每5秒推送一次）
await service.start_exchange_status_push()

# 运行一段时间后停止
await asyncio.sleep(60)
await service.stop_exchange_status_push()
```

### 完整示例

参考文件：`exchange/binance/status_integration_example.py`

```python
from exchange.binance.status_integration_example import BinanceStatusMonitor

# 创建监测器
monitor = BinanceStatusMonitor(system_service, 'binance')

# 初始化
await monitor.initialize(BinanceConfig(testnet=True))

# 连接并自动更新状态
await monitor.connect_rest()
await monitor.connect_websocket()

# 订阅市场数据
await monitor.subscribe_market_data('BTCUSDT')
```

## API接口数据格式

### 获取系统状态（包含交易所连接状态）

```python
GET /api/system/status

Response:
{
    "cpu_usage": 15.2,
    "cpu_usage_percent": 15.2,
    "memory_usage": "2.5GB / 16GB",
    "memory_usage_percent": 15.6,
    "disk_space": "45GB / 500GB",
    "disk_space_percent": 9.0,
    "timestamp": "2026-02-12T15:04:48.006123",
    "exchange_connections": {
        "summary": {
            "total": 2,
            "connected": 1,
            "disconnected": 0,
            "error": 1,
            "reconnecting": 0,
            "healthy": false
        },
        "connections": [
            {
                "exchange_name": "binance",
                "status": "connected",
                "status_color": "green",
                "last_connected_at": "2026-02-12T15:04:48.006123",
                "last_disconnected_at": null,
                "last_error": null,
                "last_error_at": null,
                "reconnect_count": 0,
                "latency_ms": 25.5,
                "message_count": 1523
            },
            {
                "exchange_name": "okx",
                "status": "error",
                "status_color": "red",
                "last_connected_at": null,
                "last_disconnected_at": "2026-02-12T15:03:30.123456",
                "last_error": "Connection timeout",
                "last_error_at": "2026-02-12T15:03:30.123456",
                "reconnect_count": 3,
                "latency_ms": null,
                "message_count": 0
            }
        ],
        "timestamp": "2026-02-12T15:04:48.006123"
    }
}
```

### WebSocket推送消息

```json
{
    "type": "exchange_status",
    "id": "exchange_status_1707734688006",
    "timestamp": 1707734688006,
    "data": {
        "summary": {
            "total": 2,
            "connected": 1,
            "disconnected": 0,
            "error": 1,
            "reconnecting": 0,
            "healthy": false
        },
        "connections": [...],
        "timestamp": "2026-02-12T15:04:48.006123"
    }
}
```

## 前端展示建议

### 状态颜色映射

- `connected` - 绿色（green）
- `disconnected` - 灰色（gray）
- `connecting` - 黄色（yellow）
- `error` - 红色（red）
- `reconnecting` - 橙色（orange）

### 展示字段

1. **连接状态指示器** - 使用颜色圆点展示整体健康状态
2. **交易所列表** - 展示所有交易所及其状态
3. **详细信息** - 点击可查看延迟、重连次数、错误信息等
4. **时间信息** - 最后连接/断开时间

## 异常处理

### 自动重连机制

```python
async def reconnect_with_monitoring():
    # 更新为重连中状态
    await service.update_exchange_status(
        'binance', 'reconnecting'
    )
    
    # 执行重连
    success = await reconnect()
    
    if success:
        await service.update_exchange_status(
            'binance', 'connected'
        )
    else:
        await service.update_exchange_status(
            'binance', 'error', 
            error='Reconnection failed after 3 attempts'
        )
```

### 错误记录

所有错误都会被记录到 `ExchangeConnectionInfo` 中：

- `last_error` - 错误信息
- `last_error_at` - 错误发生时间
- `reconnect_count` - 重连次数

## 性能考虑

1. **线程安全** - 使用 `asyncio.Lock()` 确保并发安全
2. **推送频率** - 默认每5秒推送一次，可根据需要调整
3. **内存使用** - 连接信息存储在内存中，定期清理无用数据

## 注意事项

1. 确保在连接前注册交易所
2. 及时更新状态变化
3. 在应用关闭时停止推送服务
4. 处理所有可能的异常情况

## 后续扩展

1. 添加连接延迟历史记录
2. 支持连接质量评分
3. 添加自动故障转移
4. 集成告警系统
