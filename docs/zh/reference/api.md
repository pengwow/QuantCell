---
title: REST API
description: /api/v1 路由组总览与接口约定
---

# REST API

所有业务路由统一挂载在 **`/api/v1`** 前缀下。接口的完整参数、Schema 与
响应模型以 Swagger 为准，本文只给路由组地图。

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
- **健康检查**：`http://localhost:8000/health`
- **Prometheus 指标**：`/metrics`（能力开关开启时）

## 路由组地图

| 路由组 | 职责 |
|--------|------|
| `/api/v1/strategy` | 策略 CRUD、生成、列表 |
| `/api/v1/backtest` | 回测任务提交、结果查询 |
| `/api/v1/factor` | 因子分析、快照 |
| `/api/v1/rl` | RL 训练、评估、生命周期 |
| `/api/v1/data` | 数据下载、导入、质量 |
| `/api/v1/marketdata` | 市场行情查询 |
| `/api/v1/agent` | AI Agent 会话 |
| `/api/v1/account` | 账户与凭证 |
| `/api/v1/plugin` | 插件管理 |
| `/api/v1/research` | 研究模块（快照等） |
| `/api/v1/worker` | Worker 状态与管理 |
| `/api/v1/credentials` | 交易所凭证 |
| `/api/v1/capabilities` | 能力开关查询 |
| `/api/v1/scheduled-tasks` | 计划任务 |
| `/api/v1/extensions` | 系统扩展/能力开关管理 |
| `/ws/research` | 研究实时通道（见 [WebSocket](websocket.md)） |

## 通用约定

### 错误处理

统一由 FastAPI `HTTPException` 抛出，携带状态码与可读错误信息：

```json
{
  "detail": "strategy 'dual_ma' not found"
}
```

常见状态码：`400` 参数错误、`404` 资源不存在、`422` Pydantic 校验失败、
`500` 服务端异常。

### 参数校验

所有请求体 / 查询参数经 Pydantic Schema 校验，非法参数直接 `422`。

### 分层约束

路由层只做参数接收与服务调用，业务逻辑在 service 层 —— 因此
REST 返回结构与回测 `BacktestResult` 等内部契约保持一致。

## 版本管理

`/api/v1` 前缀预留升级空间，后续不兼容变更 将引入 `/api/v2` 并行发布。
当前所有前端 / 桌面端 / MCP 均基于 `/api/v1`。

## MCP Server

`backend/mcp_server/` 暴露 MCP（Model Context Protocol）服务，能力与
REST API 对齐，可被 Claude Desktop 等 MCP 客户端调用。
