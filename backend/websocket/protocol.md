# WebSocket通信协议设计

## 1. 连接管理

### 1.1 连接路径
- WebSocket连接路径: `ws://{host}:{port}/ws`
- 支持的子路径:
  - `/ws/task` - 任务相关WebSocket连接
  - `/ws/data` - 数据相关WebSocket连接
  - `/ws/strategy` - 策略相关WebSocket连接

### 1.2 连接参数
客户端连接时可以传递以下查询参数：
- `client_id` - 客户端唯一标识（可选）
- `token` - 认证令牌（可选，用于需要认证的场景）
- `topics` - 订阅的主题列表，逗号分隔（可选）

示例：`ws://localhost:8000/ws/task?client_id=abc123&topics=task:progress,task:status`

## 2. 消息格式

### 2.1 通用消息结构
所有WebSocket消息都采用JSON格式，包含以下字段：

```json
{
  "type": "string",        // 消息类型
  "id": "string",          // 消息ID，用于请求-响应配对
  "timestamp": "number",    // 时间戳（毫秒）
  "data": { ... },          // 消息数据
  "error": { ... }          // 错误信息（仅在错误响应中存在）
}
```

### 2.2 消息类型

#### 2.2.1 客户端发送的消息类型
- `ping` - 心跳检测
- `subscribe` - 订阅主题
- `unsubscribe` - 取消订阅主题
- `get_task` - 获取任务信息
- `get_tasks` - 获取任务列表

#### 2.2.2 服务器发送的消息类型
- `pong` - 心跳响应
- `task_progress` - 任务进度更新
- `task_status` - 任务状态更新
- `task_list` - 任务列表更新
- `error` - 错误响应

### 2.3 具体消息格式

#### 2.3.1 心跳检测
客户端：
```json
{
  "type": "ping",
  "id": "ping_123",
  "timestamp": 1677824400000,
  "data": {}
}
```

服务器：
```json
{
  "type": "pong",
  "id": "ping_123",
  "timestamp": 1677824400001,
  "data": {
    "server_time": 1677824400001
  }
}
```

#### 2.3.2 订阅主题
```json
{
  "type": "subscribe",
  "id": "sub_123",
  "timestamp": 1677824400000,
  "data": {
    "topics": ["task:progress", "task:status"]
  }
}
```

#### 2.3.3 任务进度更新
```json
{
  "type": "task_progress",
  "id": "progress_123",
  "timestamp": 1677824400000,
  "data": {
    "task_id": "task_123",
    "progress": {
      "total": 100,
      "completed": 45,
      "failed": 0,
      "current": "处理 BTCUSDT",
      "percentage": 45,
      "status": "Downloading 2024-01-01"
    }
  }
}
```

#### 2.3.4 任务状态更新
```json
{
  "type": "task_status",
  "id": "status_123",
  "timestamp": 1677824400000,
  "data": {
    "task_id": "task_123",
    "status": "completed",
    "start_time": "2024-01-01T00:00:00Z",
    "end_time": "2024-01-01T00:10:00Z"
  }
}
```

## 3. 交互流程

### 3.1 连接建立流程
1. 客户端发起WebSocket连接
2. 服务器接受连接并发送欢迎消息
3. 客户端发送订阅请求，指定需要的主题
4. 服务器确认订阅成功
5. 服务器开始推送相关数据

### 3.2 心跳机制
- 客户端每30秒发送一次ping消息
- 服务器收到ping后立即回复pong消息
- 如果客户端在60秒内没有收到pong，认为连接断开，尝试重连

### 3.3 任务进度推送流程
1. 客户端订阅 `task:progress` 主题
2. 服务器检测到任务进度变化
3. 服务器向所有订阅该主题的客户端推送进度更新
4. 客户端收到进度更新并更新UI

## 4. 错误处理

### 4.1 错误消息格式
```json
{
  "type": "error",
  "id": "error_123",
  "timestamp": 1677824400000,
  "error": {
    "code": "string",      // 错误代码
    "message": "string",   // 错误消息
    "details": { ... }      // 错误详情
  }
}
```

### 4.2 常见错误代码
- `INVALID_MESSAGE` - 无效的消息格式
- `UNAUTHORIZED` - 未授权访问
- `TOPIC_NOT_FOUND` - 订阅的主题不存在
- `TASK_NOT_FOUND` - 任务不存在
- `SERVER_ERROR` - 服务器内部错误

## 5. 客户端实现指南

### 5.1 连接管理
- 实现自动重连机制
- 处理连接超时
- 管理订阅状态

### 5.2 消息处理
- 实现消息ID生成和匹配
- 处理消息队列
- 实现消息重试机制

### 5.3 性能优化
- 批量处理消息
- 实现消息去重
- 优化订阅策略

## 6. 服务器实现指南

### 6.1 连接管理
- 支持多客户端连接
- 实现连接池管理
- 处理连接超时和断开

### 6.2 消息推送
- 实现发布-订阅模式
- 优化消息推送频率
- 支持消息批量发送

### 6.3 扩展性
- 设计插件化的消息处理器
- 支持动态添加新的消息类型
- 提供API用于其他模块发送WebSocket消息

## 7. 安全考虑

- 实现WebSocket连接的认证机制
- 防止消息注入攻击
- 限制单个客户端的连接数
- 实现消息速率限制

## 8. 测试计划

### 8.1 功能测试
- 连接建立和断开
- 消息发送和接收
- 订阅和取消订阅
- 心跳机制
- 错误处理

### 8.2 性能测试
- 并发连接数测试
- 消息吞吐量测试
- 延迟测试
- 稳定性测试

### 8.3 兼容性测试
- 不同浏览器的兼容性
- 不同网络环境的适应性
- 与现有HTTP API的兼容性

## 9. 未来扩展

- 支持二进制消息格式
- 实现消息加密
- 支持WebSocket压缩
- 添加更多消息类型和主题
- 实现更复杂的客户端-服务器交互模式