# Agent前后端功能映射文档

## 概述

本文档建立了前端Agent页面与后端Worker模块之间的功能映射关系，确保前后端功能一致性和行为统一性。

## 架构对应关系

| 前端概念 | 后端概念 | 说明 |
|---------|---------|------|
| Agent | Worker | 策略代理实例 |
| Agent状态 | Worker状态 | stopped/running/paused等 |
| Agent指标 | Worker指标 | CPU/内存/网络使用率 |
| Agent日志 | Worker日志 | 运行日志记录 |
| 策略部署 | Strategy部署 | 在Worker上部署策略 |

## API接口映射

### 基础管理API

| 前端功能 | 前端API函数 | 后端API端点 | HTTP方法 | 说明 |
|---------|------------|------------|---------|------|
| 获取Agent列表 | `listAgents()` | `/api/workers` | GET | 分页获取所有Agent |
| 获取Agent详情 | `getAgent(id)` | `/api/workers/{id}` | GET | 获取单个Agent详情 |
| 创建Agent | `createAgent(data)` | `/api/workers` | POST | 创建新Agent |
| 更新Agent | `updateAgent(id, data)` | `/api/workers/{id}` | PUT | 更新Agent信息 |
| 更新Agent配置 | `updateAgentConfig(id, config)` | `/api/workers/{id}/config` | PATCH | 部分更新配置 |
| 删除Agent | `deleteAgent(id)` | `/api/workers/{id}` | DELETE | 删除Agent |
| 克隆Agent | `cloneAgent(id, name)` | `/api/workers/{id}/clone` | POST | 克隆Agent |
| 批量操作 | `batchOperation(data)` | `/api/workers/batch` | POST | 批量启动/停止/重启 |

### 生命周期管理API

| 前端功能 | 前端API函数 | 后端API端点 | HTTP方法 | 说明 |
|---------|------------|------------|---------|------|
| 启动Agent | `startAgent(id)` | `/api/workers/{id}/lifecycle/start` | POST | 启动Agent |
| 停止Agent | `stopAgent(id)` | `/api/workers/{id}/lifecycle/stop` | POST | 停止Agent |
| 重启Agent | `restartAgent(id)` | `/api/workers/{id}/lifecycle/restart` | POST | 重启Agent |
| 暂停Agent | `pauseAgent(id)` | `/api/workers/{id}/lifecycle/pause` | POST | 暂停Agent |
| 恢复Agent | `resumeAgent(id)` | `/api/workers/{id}/lifecycle/resume` | POST | 恢复Agent |
| 获取状态 | `getAgentStatus(id)` | `/api/workers/{id}/lifecycle/status` | GET | 获取实时状态 |
| 健康检查 | `healthCheck(id)` | `/api/workers/{id}/lifecycle/health` | GET | 健康检查 |

### 监控数据API

| 前端功能 | 前端API函数 | 后端API端点 | HTTP方法 | 说明 |
|---------|------------|------------|---------|------|
| 获取实时指标 | `getAgentMetrics(id)` | `/api/workers/{id}/monitoring/metrics` | GET | CPU/内存/网络指标 |
| 获取历史指标 | `getMetricsHistory(id, params)` | `/api/workers/{id}/monitoring/metrics/history` | GET | 历史性能数据 |
| 获取日志 | `getAgentLogs(id, params)` | `/api/workers/{id}/monitoring/logs` | GET | 运行日志 |
| 获取绩效 | `getAgentPerformance(id, days)` | `/api/workers/{id}/monitoring/performance` | GET | 绩效统计 |
| 获取交易记录 | `getAgentTrades(id, params)` | `/api/workers/{id}/monitoring/trades` | GET | 交易历史 |

### 策略代理API

| 前端功能 | 前端API函数 | 后端API端点 | HTTP方法 | 说明 |
|---------|------------|------------|---------|------|
| 部署策略 | `deployStrategy(id, data)` | `/api/workers/{id}/strategy/deploy` | POST | 部署策略到Agent |
| 卸载策略 | `undeployStrategy(id)` | `/api/workers/{id}/strategy/undeploy` | POST | 卸载策略 |
| 获取策略参数 | `getStrategyParameters(id)` | `/api/workers/{id}/strategy/parameters` | GET | 获取参数列表 |
| 更新策略参数 | `updateStrategyParameters(id, params)` | `/api/workers/{id}/strategy/parameters` | PUT | 更新参数值 |
| 获取持仓 | `getPositions(id)` | `/api/workers/{id}/strategy/positions` | GET | 当前持仓 |
| 获取订单 | `getOrders(id, status)` | `/api/workers/{id}/strategy/orders` | GET | 订单列表 |
| 发送交易信号 | `sendTradingSignal(id, signal)` | `/api/workers/{id}/strategy/signal` | POST | 发送信号 |

## 数据模型映射

### Agent ↔ Worker

```typescript
// 前端Agent类型
interface Agent {
  id: number;                    // ←→ Worker.id
  name: string;                  // ←→ Worker.name
  description?: string;          // ←→ Worker.description
  status: AgentStatus;           // ←→ Worker.status
  strategy_id: number;           // ←→ Worker.strategy_id
  exchange: string;              // ←→ Worker.exchange
  symbol: string;                // ←→ Worker.symbol
  timeframe: string;             // ←→ Worker.timeframe
  market_type: string;           // ←→ Worker.market_type
  trading_mode: string;          // ←→ Worker.trading_mode
  cpu_limit: number;             // ←→ Worker.cpu_limit
  memory_limit: number;          // ←→ Worker.memory_limit
  pid?: number;                  // ←→ Worker.pid
  config?: Record<string, any>;  // ←→ Worker.config (JSON)
  created_at: string;            // ←→ Worker.created_at
  updated_at: string;            // ←→ Worker.updated_at
  started_at?: string;           // ←→ Worker.started_at
  stopped_at?: string;           // ←→ Worker.stopped_at
}
```

### AgentStatus ↔ Worker.status

| 前端状态 | 后端状态值 | 说明 |
|---------|-----------|------|
| STOPPED | 'stopped' | 已停止 |
| RUNNING | 'running' | 运行中 |
| PAUSED | 'paused' | 已暂停 |
| ERROR | 'error' | 错误状态 |
| STARTING | 'starting' | 启动中 |
| STOPPING | 'stopping' | 停止中 |

### AgentMetrics ↔ WorkerMetric

```typescript
// 前端AgentMetrics类型
interface AgentMetrics {
  worker_id: number;      // ←→ WorkerMetric.worker_id
  cpu_usage: number;      // ←→ WorkerMetric.cpu_usage
  memory_usage: number;   // ←→ WorkerMetric.memory_usage
  memory_used_mb: number; // ←→ WorkerMetric.memory_used_mb
  network_in: number;     // ←→ WorkerMetric.network_in
  network_out: number;    // ←→ WorkerMetric.network_out
  active_tasks: number;   // ←→ WorkerMetric.active_tasks
  timestamp: string;      // ←→ WorkerMetric.timestamp
}
```

## 状态流转映射

### Agent生命周期状态流转

```
┌──────────┐    start     ┌──────────┐    ready    ┌──────────┐
│ STOPPED  │ ───────────→ │ STARTING │ ──────────→ │ RUNNING  │
└──────────┘              └──────────┘             └────┬─────┘
     ↑                                                  │
     │                                                  │ pause
     │                                                  ↓
     │                                            ┌──────────┐
     │           resume      ┌──────────┐        │  PAUSED  │
     └────────────────────── │ RESUMING │ ←──────┤          │
                             └──────────┘        └──────────┘
                                  │
                                  │ stop
                                  ↓
┌──────────┐    stopped   ┌──────────┐
│ STOPPED  │ ←─────────── │ STOPPING │
└──────────┘              └──────────┘
```

### 前端状态管理 ↔ 后端状态

| 前端操作 | 前端乐观更新 | 后端实际状态 | 同步机制 |
|---------|------------|------------|---------|
| 点击启动 | STARTING | starting | 轮询状态API |
| 点击停止 | STOPPING | stopping | 轮询状态API |
| 点击暂停 | PAUSED | paused | 轮询状态API |
| 点击恢复 | RUNNING | running | 轮询状态API |
| 点击重启 | STARTING | restarting → running | 轮询状态API |

## 错误码映射

### HTTP状态码处理

| HTTP状态码 | 前端错误类型 | 用户提示 | 处理策略 |
|-----------|------------|---------|---------|
| 200 | 成功 | - | 正常处理 |
| 400 | 参数错误 | 请求参数有误，请检查输入 | 显示表单验证错误 |
| 401 | 未授权 | 登录已过期，请重新登录 | 跳转登录页 |
| 403 | 权限不足 | 您没有权限执行此操作 | 禁用操作按钮 |
| 404 | 资源不存在 | Agent不存在或已被删除 | 刷新列表 |
| 409 | 资源冲突 | Agent名称已存在 | 提示修改名称 |
| 422 | 验证错误 | 数据格式不正确 | 显示字段级错误 |
| 429 | 请求频繁 | 操作太频繁，请稍后再试 | 添加防抖处理 |
| 500 | 服务器错误 | 服务器内部错误，请稍后重试 | 显示重试按钮 |
| 502/503/504 | 服务不可用 | 服务暂时不可用 | 显示离线状态 |

### 业务错误码处理

| 后端code | 含义 | 前端处理 |
|---------|------|---------|
| 0 | 成功 | 正常处理 |
| 1001 | Agent不存在 | 刷新列表，提示Agent不存在 |
| 1002 | Agent已在运行 | 禁用启动按钮 |
| 1003 | Agent已停止 | 禁用停止按钮 |
| 1004 | 策略不存在 | 提示选择有效策略 |
| 1005 | 参数验证失败 | 显示字段级错误 |
| 1006 | 资源不足 | 提示资源限制 |

## 实时通信映射

### WebSocket日志流

| 前端功能 | WebSocket URL | 消息格式 | 说明 |
|---------|--------------|---------|------|
| 实时日志 | `ws://host/api/workers/{id}/monitoring/logs/stream` | JSON | 实时推送日志 |

### 消息格式

```typescript
// 前端接收的日志消息
interface LogMessage {
  level: 'info' | 'warning' | 'error';
  message: string;
  source: string;
  timestamp: string;
}

// 对应后端MessageType.LOG
{
  "msg_type": "log",
  "worker_id": "123",
  "payload": {
    "level": "info",
    "message": "Strategy started",
    "source": "worker",
    "timestamp": 1234567890
  }
}
```

## 请求参数映射

### 分页参数

| 前端参数 | 后端参数 | 默认值 | 说明 |
|---------|---------|-------|------|
| page | page | 1 | 当前页码 |
| pageSize | page_size | 20 | 每页数量 |

### 筛选参数

| 前端参数 | 后端参数 | 类型 | 说明 |
|---------|---------|------|------|
| status | status | string | Agent状态筛选 |
| strategyId | strategy_id | number | 策略ID筛选 |

### 时间范围参数

| 前端参数 | 后端参数 | 格式 | 说明 |
|---------|---------|------|------|
| startTime | start_time | ISO 8601 | 开始时间 |
| endTime | end_time | ISO 8601 | 结束时间 |

## 响应数据映射

### 标准响应格式

```typescript
// 前端ApiResponse<T>
interface ApiResponse<T> {
  code: number;      // ←→ 后端统一返回code
  message: string;   // ←→ 后端返回message
  data?: T;          // ←→ 后端返回data
}

// 后端响应格式
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

### 列表响应格式

```typescript
// 前端AgentListResponse
interface AgentListResponse {
  items: Agent[];    // ←→ data.items
  total: number;     // ←→ data.total
  page: number;      // ←→ data.page
  page_size: number; // ←→ data.page_size
}
```

## 性能优化映射

### 前端优化 ↔ 后端支持

| 前端优化策略 | 后端支持 | 实现方式 |
|------------|---------|---------|
| 数据缓存 | ETag/Last-Modified | HTTP缓存头 |
| 增量更新 | 时间戳过滤 | start_time参数 |
| 分页加载 | 分页API | page/page_size参数 |
| 请求合并 | 批量API | /api/workers/batch |
| 乐观更新 | 快速响应 | 立即返回，后台处理 |

## 安全映射

### 认证机制

| 前端实现 | 后端要求 | 说明 |
|---------|---------|------|
| JWT Token | Authorization头 | Bearer token |
| Token刷新 | 401响应 | 自动刷新并重试 |
| 请求签名 | 可选 | 敏感操作签名验证 |

### 权限控制

| 前端权限 | 后端权限 | 说明 |
|---------|---------|------|
| 查看Agent | read:agents | 列表和详情查看 |
| 创建Agent | create:agent | 创建新Agent |
| 修改Agent | update:agent | 更新Agent信息 |
| 删除Agent | delete:agent | 删除Agent |
| 生命周期操作 | manage:agent | 启动/停止/重启等 |

## 测试映射

### 单元测试对应

| 前端测试 | 后端测试 | Mock数据 |
|---------|---------|---------|
| API调用测试 | API路由测试 | 相同fixture |
| 状态管理测试 | 服务层测试 | 相同状态数据 |
| 组件渲染测试 | - | Mock API响应 |

### 集成测试对应

| 测试场景 | 前端验证 | 后端验证 |
|---------|---------|---------|
| 创建Agent流程 | 表单提交→列表更新 | API调用→数据库存储 |
| 生命周期操作 | 按钮点击→状态变化 | API调用→进程管理 |
| 错误处理 | 错误提示显示 | 错误码返回 |

## 部署映射

### 环境变量

| 前端变量 | 后端变量 | 说明 |
|---------|---------|------|
| VITE_API_BASE_URL | API_HOST | API服务器地址 |
| VITE_WS_URL | WS_HOST | WebSocket服务器地址 |

### 构建配置

| 前端配置 | 后端配置 | 说明 |
|---------|---------|------|
| proxy设置 | CORS配置 | 开发环境跨域 |
| 路由模式 | URL重写 | 单页应用路由 |
