# Agent命名规范文档

## 概述

本文档定义了前端项目中"策略代理"（Agent）相关的命名规范，确保代码一致性、可读性和可维护性。

## 命名原则

1. **统一性**：所有"策略代理"相关命名统一使用英文"agent"
2. **清晰性**：命名应当清晰表达其用途和含义
3. **一致性**：相同概念使用相同命名，避免混用
4. **简洁性**：在保证清晰的前提下，尽量简洁

## 文件命名规范

### 组件文件
- ✅ **正确**：`Agent.tsx`, `AgentList.tsx`, `AgentDetail.tsx`
- ❌ **错误**：`StrategyAgent.tsx`, `StrategyAgentList.tsx`

### 样式文件
- ✅ **正确**：`Agent.css`, `Agent.module.css`
- ❌ **错误**：`StrategyAgent.css`, `strategy-agent.css`

### 工具文件
- ✅ **正确**：`exportAgent.ts`, `agentUtils.ts`
- ❌ **错误**：`exportStrategyAgent.ts`, `strategyAgentUtils.ts`

### 类型定义文件
- ✅ **正确**：`agent.ts` (存放Agent相关类型)
- ❌ **错误**：`strategyAgent.ts`, `worker.ts`

## 变量命名规范

### 组件命名
- ✅ **正确**：`const Agent = () => {...}`
- ❌ **错误**：`const StrategyAgent = () => {...}`

### Hook命名
- ✅ **正确**：`useAgentStore`, `useAgentStatus`
- ❌ **错误**：`useStrategyAgentStore`, `useWorkerStore`

### 变量命名
```typescript
// ✅ 正确
const agent = { id: 1, name: 'Test Agent' };
const agentList = [agent1, agent2];
const currentAgent = agent;
const selectedAgentId = 1;

// ❌ 错误
const strategyAgent = { id: 1, name: 'Test Agent' };
const worker = { id: 1, name: 'Test Agent' };
const proxy = { id: 1, name: 'Test Agent' };
```

### 函数命名
```typescript
// ✅ 正确
const fetchAgents = () => {...};
const createAgent = (data) => {...};
const updateAgent = (id, data) => {...};
const deleteAgent = (id) => {...};
const startAgent = (id) => {...};
const stopAgent = (id) => {...};

// ❌ 错误
const fetchStrategyAgents = () => {...};
const createWorker = (data) => {...};
const updateProxy = (id, data) => {...};
```

## API相关命名

### API函数命名
```typescript
// ✅ 正确
import { listAgents, getAgent, createAgent } from '../api/agentApi';

// ❌ 错误
import { listWorkers, getWorker, createWorker } from '../api/workerApi';
```

### API模块命名
- ✅ **正确**：`agentApi.ts`
- ❌ **错误**：`workerApi.ts`, `strategyAgentApi.ts`

## Store状态管理命名

### Store命名
```typescript
// ✅ 正确
import { useAgentStore } from '../store/agentStore';

// ❌ 错误
import { useStrategyStore } from '../store/strategyStore';
import { useWorkerStore } from '../store/workerStore';
```

### 状态命名
```typescript
// ✅ 正确
interface AgentState {
  agents: Agent[];
  currentAgent: Agent | null;
  agentMetrics: Record<number, AgentMetrics>;
  agentLogs: Record<number, AgentLog[]>;
}

// ❌ 错误
interface WorkerState {
  workers: Worker[];
  currentWorker: Worker | null;
}
```

## 路由命名

### 路由路径
```typescript
// ✅ 正确
{
  path: '/agent',
  element: <Agent />
}

// ❌ 错误
{
  path: '/strategy-agent',
  element: <StrategyAgent />
}
{
  path: '/worker',
  element: <Worker />
}
```

### 导航菜单
```typescript
// ✅ 正确
{
  path: '/agent',
  name: t('agent'),
  icon: <RobotOutlined />
}

// ❌ 错误
{
  path: '/agent/StrategyAgent',
  name: t('strategy_agent'),
  icon: <RobotOutlined />
}
```

## 类型命名

### 接口命名
```typescript
// ✅ 正确
interface Agent {
  id: number;
  name: string;
  status: AgentStatus;
}

interface AgentMetrics {
  cpuUsage: number;
  memoryUsage: number;
}

interface CreateAgentRequest {
  name: string;
  strategyId: number;
}

// ❌ 错误
interface Worker {
  id: number;
  name: string;
}

interface StrategyAgent {
  id: number;
  name: string;
}
```

### 枚举命名
```typescript
// ✅ 正确
enum AgentStatus {
  STOPPED = 'stopped',
  RUNNING = 'running',
  PAUSED = 'paused'
}

// ❌ 错误
enum WorkerStatus {
  STOPPED = 'stopped',
  RUNNING = 'running'
}
```

## CSS类名命名

### BEM命名规范
```css
/* ✅ 正确 */
.agent {}
.agent__header {}
.agent__content {}
.agent__status {}
.agent__status--running {}
.agent__status--stopped {}

/* ❌ 错误 */
.strategy-agent {}
.worker {}
.agentContainer {}
```

## 国际化命名

### 翻译键名
```json
{
  "agent": "Agent",
  "agent_list": "Agent列表",
  "agent_detail": "Agent详情",
  "agent_status": "Agent状态",
  "agent_metrics": "Agent指标",
  "create_agent": "创建Agent",
  "edit_agent": "编辑Agent",
  "delete_agent": "删除Agent",
  "start_agent": "启动Agent",
  "stop_agent": "停止Agent"
}
```

## 命名对照表

| 中文概念 | 英文命名 | 禁用命名 |
|---------|---------|---------|
| Agent | agent | worker, strategyAgent, proxy |
| Agent列表 | agentList | workerList, strategyAgents |
| Agent详情 | agentDetail | workerDetail, strategyAgentDetail |
| Agent状态 | agentStatus | workerStatus, strategyStatus |
| Agent指标 | agentMetrics | workerMetrics |
| 创建Agent | createAgent | createWorker, createStrategyAgent |
| 更新Agent | updateAgent | updateWorker, updateStrategyAgent |
| 删除Agent | deleteAgent | deleteWorker, deleteStrategyAgent |
| 启动Agent | startAgent | startWorker, startStrategyAgent |
| 停止Agent | stopAgent | stopWorker, stopStrategyAgent |

## 迁移指南

### 从旧命名迁移到新命名

1. **文件重命名**
   ```bash
   git mv StrategyAgent.tsx Agent.tsx
   git mv StrategyAgent.css Agent.css
   ```

2. **导入路径更新**
   ```typescript
   // 旧代码
   import StrategyAgent from '../views/StrategyAgent';
   
   // 新代码
   import Agent from '../views/Agent';
   ```

3. **变量名替换**
   ```typescript
   // 旧代码
   const strategyAgent = {...};
   const workers = [...];
   
   // 新代码
   const agent = {...};
   const agents = [...];
   ```

4. **函数名替换**
   ```typescript
   // 旧代码
   const fetchWorkers = () => {...};
   const createWorker = (data) => {...};
   
   // 新代码
   const fetchAgents = () => {...};
   const createAgent = (data) => {...};
   ```

## 代码审查检查项

在代码审查时，请检查以下命名规范：

- [ ] 文件名是否使用Agent命名
- [ ] 组件名是否使用Agent命名
- [ ] 变量名是否使用agent命名
- [ ] 函数名是否使用Agent相关命名
- [ ] 类型定义是否使用Agent命名
- [ ] Store是否使用useAgentStore命名
- [ ] API模块是否使用agentApi命名
- [ ] 路由路径是否使用/agent
- [ ] CSS类名是否遵循BEM规范

## ESLint规则建议

推荐添加以下ESLint规则来强制执行命名规范：

```javascript
// .eslintrc.js
module.exports = {
  rules: {
    // 禁止使用旧命名
    'no-restricted-syntax': [
      'error',
      {
        selector: 'Identifier[name=/^(worker|strategyAgent|proxy)$/i]',
        message: '请使用"agent"替代"worker"或"strategyAgent"'
      }
    ]
  }
};
```

## 相关文档

- [Agent API接口文档](./agent-api.md)
- [Agent类型定义文档](./agent-types.md)
- [前后端功能映射文档](./agent-backend-mapping.md)
