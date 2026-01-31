# WebSocket服务使用指南

本文档详细介绍了项目中WebSocket服务的架构、使用方法、通信协议和扩展指南，帮助开发人员快速集成和使用WebSocket功能。

## 1. 架构概述

### 1.1 系统架构

WebSocket服务采用了前后端分离的架构设计：

- **后端**：基于FastAPI实现的WebSocket服务端，支持多客户端连接和实时消息推送
- **前端**：基于浏览器原生WebSocket API实现的客户端，支持自动重连和消息处理

### 1.2 核心组件

#### 后端组件

| 组件 | 路径 | 功能 |
|------|------|------|
| WebSocket连接管理器 | `backend/websocket/manager.py` | 管理WebSocket连接、消息队列和广播 |
| WebSocket路由 | `backend/websocket/routes.py` | 处理WebSocket连接请求和消息 |
| 任务管理器 | `backend/collector/utils/task_manager.py` | 通过WebSocket推送任务进度和状态 |

#### 前端组件

| 组件 | 路径 | 功能 |
|------|------|------|
| WebSocket服务 | `frontend/src/services/websocketService.ts` | 管理WebSocket连接、自动重连和消息处理 |
| 数据采集页面 | `frontend/src/views/DataManagement/DataCollectionPage.tsx` | 使用WebSocket接收任务进度更新 |

## 2. 后端WebSocket服务

### 2.1 服务端配置

WebSocket服务默认配置如下：

- 主端点：`/ws`
- 任务端点：`/ws/task`
- 批处理大小：10条消息
- 批处理间隔：0.1秒
- 速率限制：100消息/秒/客户端

### 2.2 使用方法

#### 基本使用

```python
from backend.websocket.manager import manager
import asyncio

# 推送任务进度更新
async def push_task_progress(task_id, progress):
    message = {
        "type": "task_progress",
        "id": f"progress_{task_id}_{int(time.time() * 1000)}",
        "timestamp": int(time.time() * 1000),
        "data": {
            "task_id": task_id,
            "progress": progress
        }
    }
    await manager.queue_message(message, topic="task:progress")
```

#### 消息格式

```python
{
    "type": "消息类型",
    "id": "消息ID",
    "timestamp": 时间戳,
    "data": {"消息数据"},
    "topic": "消息主题"
}
```

### 2.3 支持的消息类型

| 消息类型 | 主题 | 功能 |
|---------|------|------|
| `task_progress` | `task:progress` | 任务进度更新 |
| `task_status` | `task:status` | 任务状态更新 |
| `task_list` | `task:list` | 任务列表更新 |
| `ping` | - | 心跳检测 |
| `pong` | - | 心跳响应 |
| `batch` | - | 批量消息 |
| `error` | - | 错误消息 |

## 3. 前端WebSocket客户端

### 3.1 基本使用

```typescript
import { wsService } from '@/services/websocketService';

// 连接WebSocket服务
wsService.connect();

// 监听任务进度更新
wsService.on('task:progress', (data) => {
  console.log('任务进度更新:', data);
  // 更新UI
});

// 监听任务状态更新
wsService.on('task:status', (data) => {
  console.log('任务状态更新:', data);
  // 更新UI
});

// 监听连接状态变化
wsService.onConnectionChange((connected) => {
  console.log('WebSocket连接状态:', connected);
  // 更新连接状态UI
});
```

### 3.2 客户端配置

```typescript
import { WebSocketService, WebSocketConfig } from '@/services/websocketService';

const config: WebSocketConfig = {
  url: 'ws://localhost:8000/ws/task',
  topics: ['task:progress', 'task:status'],
  reconnectInterval: 3000,
  maxReconnectAttempts: 5,
  pingInterval: 30000,
};

const customWsService = new WebSocketService(config);
customWsService.connect();
```

## 4. 通信协议

### 4.1 消息结构

所有WebSocket消息都遵循以下结构：

```json
{
  "type": "消息类型",
  "id": "消息ID",
  "timestamp": 时间戳,
  "data": {
    "消息数据"
  },
  "error": {
    "code": "错误代码",
    "message": "错误消息",
    "details": "错误详情"
  },
  "topic": "消息主题"
}
```

### 4.2 批量消息

为了提高传输效率，服务端会将多条消息批量发送：

```json
{
  "type": "batch",
  "messages": [
    {
      "type": "task_progress",
      "id": "progress_123",
      "timestamp": 1769847650098,
      "data": {
        "task_id": "123",
        "progress": {
          "percentage": 50,
          "current": "BTCUSDT",
          "total": 100,
          "completed": 50
        }
      },
      "topic": "task:progress"
    },
    {
      "type": "task_status",
      "id": "status_123",
      "timestamp": 1769847650099,
      "data": {
        "task_id": "123",
        "status": "running"
      },
      "topic": "task:status"
    }
  ]
}
```

### 4.3 订阅机制

客户端可以通过订阅特定主题来接收相关消息：

```json
{
  "type": "subscribe",
  "id": "sub_1",
  "data": {
    "topics": ["task:progress", "task:status"]
  }
}
```

## 5. 扩展指南

### 5.1 后端扩展

#### 添加新的WebSocket端点

```python
# backend/websocket/routes.py

@router.websocket("/ws/custom")
async def websocket_custom_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    topics: Optional[str] = Query(None)
):
    """自定义WebSocket端点"""
    # 解析主题列表
    topic_set: Set[str] = set()
    if topics:
        topic_set = set(topics.split(","))
    
    # 处理连接
    client_id = await manager.connect(websocket, client_id, topic_set)
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message = json.loads(data)
            # 处理自定义消息
            await handle_custom_message(message, client_id)
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket处理错误: {e}")
        await manager.disconnect(client_id)
```

#### 添加新的消息类型

```python
# backend/websocket/routes.py

async def handle_custom_message(message: dict, client_id: str):
    """处理自定义消息"""
    message_type = message.get("type")
    
    if message_type == "custom_action":
        # 处理自定义操作
        await handle_custom_action(message, client_id)
    else:
        # 处理未知消息类型
        await manager.send_personal_message(
            {
                "type": "error",
                "id": message.get("id"),
                "timestamp": int(time.time() * 1000),
                "error": {
                    "code": "UNKNOWN_MESSAGE_TYPE",
                    "message": f"未知的消息类型: {message_type}"
                }
            },
            client_id
        )
```

### 5.2 前端扩展

#### 添加新的消息监听器

```typescript
// 监听自定义消息
wsService.on('custom:message', (data) => {
  console.log('自定义消息:', data);
  // 处理自定义消息
});

// 发送自定义消息
wsService.send({
  type: 'custom_action',
  data: {
    action: 'do_something',
    params: {}
  }
});
```

#### 扩展WebSocket服务

```typescript
// 创建扩展的WebSocket服务
class ExtendedWebSocketService extends WebSocketService {
  // 扩展方法
  sendCustomAction(action: string, params: any): string {
    return this.send({
      type: 'custom_action',
      data: {
        action,
        params
      }
    });
  }
}

// 使用扩展服务
const extendedWsService = new ExtendedWebSocketService(config);
extendedWsService.connect();
```

## 6. 性能优化

### 6.1 后端优化

1. **消息批处理**：服务端会批量处理和发送消息，减少网络往返次数
2. **速率限制**：对每个客户端实施消息速率限制，防止滥用
3. **连接管理**：定期清理无效连接，释放资源
4. **消息队列**：使用异步消息队列，避免阻塞主线程

### 6.2 前端优化

1. **消息节流**：对频繁的UI更新进行节流处理
2. **连接状态管理**：合理处理连接状态，避免无效操作
3. **错误处理**：完善的错误处理机制，提高用户体验
4. **内存管理**：及时清理不需要的监听器，避免内存泄漏

## 7. 性能测试结果

### 7.1 并发连接测试

| 测试项 | 结果 |
|--------|------|
| 并发连接数 | 20 |
| 成功率 | 100% |
| 平均连接时间 | 0.299秒/连接 |
| 总测试时间 | 5.97秒 |

### 7.2 消息吞吐量测试

| 测试项 | 结果 |
|--------|------|
| 消息数量 | 100条 |
| 测试时间 | 0.02秒 |
| 吞吐量 | 5860条/秒 |
| 成功率 | 100% |

## 8. 常见问题和解决方案

### 8.1 连接问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 连接失败 | 网络问题或服务未启动 | 检查网络连接和服务状态 |
| 自动重连失败 | 重连次数达到上限 | 检查服务状态，手动重新连接 |
| 连接断开 | 网络不稳定或服务重启 | 依赖自动重连机制，确保重连逻辑正确 |

### 8.2 消息问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 消息丢失 | 网络中断或服务重启 | 实现消息确认机制，重要消息持久化 |
| 消息延迟 | 网络拥塞或服务负载高 | 优化消息批处理，减少消息数量 |
| 消息格式错误 | 前后端消息格式不一致 | 严格遵循通信协议，使用TypeScript类型定义 |

### 8.3 性能问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 连接数限制 | 服务器资源限制 | 增加服务器资源，优化连接管理 |
| 消息处理慢 | 客户端处理逻辑复杂 | 优化客户端代码，使用Web Workers处理复杂计算 |
| 内存占用高 | 长时间运行导致内存泄漏 | 及时清理监听器和引用，避免内存泄漏 |

## 9. 代码示例

### 9.1 后端推送消息示例

```python
from backend.websocket.manager import manager
import asyncio
import time

async def push_notification(user_id, message):
    """推送通知给特定用户"""
    notification_message = {
        "type": "notification",
        "id": f"notify_{user_id}_{int(time.time() * 1000)}",
        "timestamp": int(time.time() * 1000),
        "data": {
            "user_id": user_id,
            "message": message,
            "read": False
        }
    }
    
    # 推送给特定用户
    await manager.queue_message(notification_message, topic=f"user:{user_id}")

# 在同步代码中使用
loop = asyncio.get_event_loop()
loop.run_until_complete(push_notification("user123", "您有一条新消息"))
```

### 9.2 前端接收消息示例

```typescript
import { wsService } from '@/services/websocketService';

// 组件挂载时
useEffect(() => {
  // 连接WebSocket服务
  wsService.connect();
  
  // 订阅用户通知
  wsService.subscribe([`user:${userId}`]);
  
  // 监听通知
  const handleNotification = (data) => {
    console.log('收到通知:', data);
    // 显示通知
    setNotifications(prev => [...prev, data]);
  };
  
  wsService.on('notification', handleNotification);
  
  // 清理函数
  return () => {
    wsService.off('notification', handleNotification);
  };
}, [userId]);

// 发送消息
const sendMessage = () => {
  wsService.send({
    type: 'send_message',
    data: {
      recipient: 'user456',
      content: message
    }
  });
};
```

## 10. 总结

WebSocket服务为项目提供了实时通信能力，通过本文档的指导，开发人员可以：

1. 快速集成WebSocket功能到自己的模块
2. 了解WebSocket服务的内部工作原理
3. 按照最佳实践优化WebSocket性能
4. 扩展WebSocket功能以满足特定需求

WebSocket服务的设计考虑了可扩展性和性能，为项目的实时通信需求提供了可靠的解决方案。

---

**文档更新时间**：2026-01-31
**版本**：1.0.0
